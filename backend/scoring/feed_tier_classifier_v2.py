"""
Feed Tier Classifier v2 — Shadow Mode (Olympus 2026-04-24)

Four parallel qualification paths for top_feed. Runs alongside legacy
classifier under FEED_TIER_USE_V2 feature flag. During shadow mode
(flag=false) both decisions are logged; v1 stays authoritative for
routing. v2 takes over when flag flips to true (Phase B).

Sector vocabulary mapping (from scanners/sector_rs.py _classify()):
  SECTOR_STRENGTH     → active_leader  → Path C confluence ✓
  ACTIVE_DISTRIBUTION → rotation_out   → sector_rotating_against cap ✓
  POTENTIAL_ROTATION  → no-op (ambiguous direction, under-fire rule)
  NEUTRAL             → no-op (no directional read, under-fire rule)

Discovery findings (2026-04-24):
  Pythia coverage: 5.5%  — fully_confirmed badge will be rare during shadow
  Flow qualifying:  0.76% — Path C flow arm near-inert during shadow
  Path A uncapped:  ~27.5/week — circuit-breaker gate at >20/week triggers tuning

Rollback: FEED_TIER_USE_V2=false (Railway env var). Zero code change.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Feature flag ─────────────────────────────────────────────────────────────
# Controlled via Railway env var. false = shadow-only (v1 authoritative).
# true = v2 authoritative (Phase B, after ≥21 trading days validation).
FEED_TIER_USE_V2: bool = (os.getenv("FEED_TIER_USE_V2") or "false").lower() == "true"

# ── Circuit-breaker gate ──────────────────────────────────────────────────────
# If v2 produces more than this many top_feed signals in the first 7 shadow
# days, halt and tune Path A floor before continuing the 21-day window.
CIRCUIT_BREAKER_TOP_FEED_PER_WEEK = 20

# ── Score thresholds ──────────────────────────────────────────────────────────
TOP_FEED_FLOOR             = 75       # Path A / C / B minimum
PATH_D_FLOOR_NORMAL        = 85       # Path D: normal iv_regime
PATH_D_FLOOR_HIGH_VOL      = 90       # Path D: high_vol iv_regime
PYTHIA_TIEBREAKER_MIN      = 73       # Score band eligible for tiebreaker
PYTHIA_TIEBREAKER_MAX      = 74
WATCHLIST_FLOOR            = 50
TA_FEED_FLOOR              = 40
RESEARCH_LOG_FLOOR         = 30
# Signals below RESEARCH_LOG_FLOOR are dropped (return None)

# ── Flow alignment ────────────────────────────────────────────────────────────
# Configurable via env var so threshold can be tuned during shadow phase
# without redeploying. Default $500K net premium.
FLOW_NET_PREMIUM_THRESHOLD = int(os.getenv("FLOW_NET_PREMIUM_THRESHOLD", "500000"))

# ── Path A — high-quality scanner subtypes ────────────────────────────────────
# Uses actual signal_type values from DB (not the CTA_-prefixed names in brief).
# FOOTPRINT_IMBALANCE_* → actual values are FOOTPRINT_SHORT / FOOTPRINT_LONG.
# SESSION_SWEEP_* → actual value is Session_Sweep (mixed case).
PATH_A_SIGNAL_TYPES = {
    "PULLBACK_ENTRY",
    "GOLDEN_TOUCH",
    "TRAPPED_SHORTS",
    "FOOTPRINT_SHORT",
    "FOOTPRINT_LONG",
    "Session_Sweep",
    "SESSION_SWEEP",     # guard against future normalisation
}

# ── Path D — scanner whitelist (approved set from legacy classifier) ──────────
# All TIER3_SIGNAL_TYPES are eligible; WH signals also eligible.
# Blacklist is implicit: anything NOT in TIER3_SIGNAL_TYPES and not WH.
from scoring.feed_tier_classifier import TIER3_SIGNAL_TYPES as _TIER3
PATH_D_APPROVED_TYPES = _TIER3 | PATH_A_SIGNAL_TYPES

# ── Sector regime mappings ────────────────────────────────────────────────────
SECTOR_CONFLUENCE_ALLOW = {"SECTOR_STRENGTH"}        # active_leader equivalent
SECTOR_ROTATING_AGAINST = {"ACTIVE_DISTRIBUTION"}    # rotation_out equivalent
# POTENTIAL_ROTATION and NEUTRAL are no-ops (under-fire rule per discovery)

# ── Watchlist-approved scanner set (legacy pass-through) ─────────────────────
WATCHLIST_APPROVED_STRATEGIES = {
    "Holy_Grail", "CTA_Scanner", "Artemis", "sell_the_rip",
    "Crypto_Scanner", "Whale_Hunter", "Footprint", "SessionSweep",
    "Scout_Sniper", "Phalanx", "Exhaustion",
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_ceiling_capped(signal_data: Dict[str, Any]) -> bool:
    return bool(signal_data.get("feed_tier_ceiling"))


def _ceiling(signal_data: Dict[str, Any]) -> Optional[str]:
    return signal_data.get("feed_tier_ceiling")


def _pythia_confirms(signal_data: Dict[str, Any]) -> bool:
    pp = (signal_data.get("triggering_factors") or {}).get("profile_position", {})
    if not isinstance(pp, dict):
        return False
    if not pp.get("pythia_coverage", False):
        return False
    total_adj = pp.get("total_pythia_adjustment", pp.get("profile_bonus", 0)) or 0
    return total_adj >= 0


def _flow_bonus(signal_data: Dict[str, Any]) -> float:
    flow = (signal_data.get("triggering_factors") or {}).get("flow", {})
    return float(flow.get("bonus", 0) or 0) if isinstance(flow, dict) else 0.0


def _flow_aligned(signal_data: Dict[str, Any]) -> bool:
    """
    Returns True if options flow direction matches signal direction
    with net premium above threshold.
    """
    flow = (signal_data.get("triggering_factors") or {}).get("flow", {})
    if not isinstance(flow, dict):
        return False
    net_call  = float(flow.get("net_call_premium", 0) or 0)
    net_put   = float(flow.get("net_put_premium",  0) or 0)
    net_prem  = float(flow.get("net_premium",      0) or 0)
    direction = (signal_data.get("direction") or "").lower()

    if direction in ("long", "buy"):
        return net_call > net_put and net_prem > FLOW_NET_PREMIUM_THRESHOLD
    if direction in ("short", "sell"):
        return net_put > net_call and net_prem > FLOW_NET_PREMIUM_THRESHOLD
    return False


def _flow_contradicting(signal_data: Dict[str, Any]) -> bool:
    """
    Returns True if flow is active (bonus > 3) AND flow opposes signal direction.
    Used for the flow_contradicting ceiling cap.
    """
    if _flow_bonus(signal_data) <= 3:
        return False
    flow = (signal_data.get("triggering_factors") or {}).get("flow", {})
    if not isinstance(flow, dict):
        return False
    net_call  = float(flow.get("net_call_premium", 0) or 0)
    net_put   = float(flow.get("net_put_premium",  0) or 0)
    direction = (signal_data.get("direction") or "").lower()

    if direction in ("long", "buy") and net_put > net_call:
        return True
    if direction in ("short", "sell") and net_call > net_put:
        return True
    return False


def _sector_regime_for_signal(signal_data: Dict[str, Any]) -> Optional[str]:
    """
    Look up cached sector RS classification for this signal's ticker/ETF.
    Returns the raw scanner classification string or None if unavailable.
    Uses synchronous Redis via enrichment_data if already present,
    otherwise returns None (async callers use get_sector_rs directly).
    """
    enrichment = signal_data.get("enrichment_data") or {}
    return enrichment.get("sector_rs_classification") or None


def _sector_confluence_positive(signal_data: Dict[str, Any]) -> bool:
    regime = _sector_regime_for_signal(signal_data)
    return regime in SECTOR_CONFLUENCE_ALLOW if regime else False


def _sector_rotating_against(signal_data: Dict[str, Any]) -> bool:
    regime = _sector_regime_for_signal(signal_data)
    return regime in SECTOR_ROTATING_AGAINST if regime else False


def _iv_regime(signal_data: Dict[str, Any]) -> str:
    """Extract iv_regime string from enrichment data or triggering factors."""
    enrichment = signal_data.get("enrichment_data") or {}
    regime = enrichment.get("iv_regime") or ""
    if not regime:
        tf = signal_data.get("triggering_factors") or {}
        regime = tf.get("iv_regime") or ""
    return (regime or "").lower()


def _compute_confluence_badge(
    pythia: bool,
    flow: bool,
    sector: bool,
    path: str,
) -> str:
    """
    Compute the UI confluence badge value.
      fully_confirmed — Pythia + flow + sector all positive
      confirmed       — ≥1 enricher positive
      ta_confirmed    — Path A or D, no enricher confirms
      none            — everything else
    """
    if pythia and flow and sector:
        return "fully_confirmed"
    if pythia or flow or sector:
        return "confirmed"
    if path in ("A", "D"):
        return "ta_confirmed"
    return "none"


# ─────────────────────────────────────────────────────────────────────────────
# New ceiling-cap reasons (additive — existing caps untouched)
# ─────────────────────────────────────────────────────────────────────────────

def apply_v2_ceiling_caps(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply the two new v2 ceiling-cap reasons.
    Only fires if no ceiling already set (defense-in-depth, additive).
    Returns signal_data (mutated in place) with feed_tier_ceiling and
    _score_ceiling_reason set if a new cap applies.
    """
    if signal_data.get("feed_tier_ceiling"):
        return signal_data  # existing cap takes precedence

    # ── flow_contradicting → ta_feed ─────────────────────────────────────────
    if _flow_contradicting(signal_data):
        signal_data["feed_tier_ceiling"] = "ta_feed"
        signal_data["_score_ceiling_reason"] = "flow_contradicting"
        logger.debug(
            "v2 cap: flow_contradicting on %s — capped to ta_feed",
            signal_data.get("ticker", "?"),
        )
        return signal_data

    # ── sector_rotating_against → ta_feed ────────────────────────────────────
    if _sector_rotating_against(signal_data):
        direction = (signal_data.get("direction") or "").lower()
        # Only apply if signal implies sector continuation (long in rotating-out sector)
        if direction in ("long", "buy"):
            signal_data["feed_tier_ceiling"] = "ta_feed"
            signal_data["_score_ceiling_reason"] = "sector_rotating_against"
            logger.debug(
                "v2 cap: sector_rotating_against on %s — capped to ta_feed",
                signal_data.get("ticker", "?"),
            )

    return signal_data


# ─────────────────────────────────────────────────────────────────────────────
# Main v2 classifier
# ─────────────────────────────────────────────────────────────────────────────

def classify_signal_tier_v2(
    signal_data: Dict[str, Any],
    score: float,
) -> Tuple[Optional[str], str, str]:
    """
    Classify a signal using the v2 four-path logic.

    Returns (tier, path, confluence_badge):
      tier             — 'top_feed' | 'watchlist' | 'ta_feed' | 'research_log' | None (drop)
      path             — 'A' | 'B' | 'C' | 'D' | 'watchlist' | 'ta_feed' | 'research_log' | 'drop'
      confluence_badge — 'fully_confirmed' | 'confirmed' | 'ta_confirmed' | 'none'

    Returns (None, 'drop', 'none') for score < RESEARCH_LOG_FLOOR (hard floor — do not store).

    Note: Path B (multi-scanner Redis stack) is evaluated in pipeline.py before
    this function is called; pass pre_qualified_path_b=True via signal_data
    key '_path_b_qualified' to activate Path B routing here.
    """
    # ── Hard floor ────────────────────────────────────────────────────────────
    if score < RESEARCH_LOG_FLOOR:
        return None, "drop", "none"

    ceiling     = _ceiling(signal_data)
    signal_type = (signal_data.get("signal_type") or "").upper()
    signal_type_raw = (signal_data.get("signal_type") or "")
    strategy    = (signal_data.get("strategy")    or "")
    category    = (signal_data.get("signal_category") or "").upper()

    # Pre-compute enricher states (used across multiple paths)
    pythia_ok  = _pythia_confirms(signal_data)
    flow_ok    = _flow_bonus(signal_data) > 3 and _flow_aligned(signal_data)
    sector_ok  = _sector_confluence_positive(signal_data)

    # ── WATCHLIST_PROMOTION short-circuit ─────────────────────────────────────
    if category == "WATCHLIST_PROMOTION":
        return "watchlist", "watchlist", "none"

    # ── Ceiling routing (if capped, skip top_feed evaluation) ─────────────────
    if ceiling == "watchlist":
        return "watchlist", "watchlist", "none"
    if ceiling == "research_log":
        return "research_log", "research_log", "none"
    # ceiling == "ta_feed" falls through to ta_feed logic below

    # ── top_feed evaluation — paths A / B / C / D ─────────────────────────────
    if ceiling not in ("ta_feed",):

        # Path A — high-quality scanner subtype
        if signal_type_raw in PATH_A_SIGNAL_TYPES and score >= TOP_FEED_FLOOR:
            badge = _compute_confluence_badge(pythia_ok, flow_ok, sector_ok, "A")
            return "top_feed", "A", badge

        # Path B — multi-scanner stack (pre-qualified by pipeline Redis check)
        if signal_data.get("_path_b_qualified") and score >= TOP_FEED_FLOOR:
            badge = _compute_confluence_badge(pythia_ok, flow_ok, sector_ok, "B")
            return "top_feed", "B", badge

        # Path C — standard scanner + ≥1 confluence flag
        has_confluence = pythia_ok or flow_ok or sector_ok
        if score >= TOP_FEED_FLOOR and has_confluence:
            badge = _compute_confluence_badge(pythia_ok, flow_ok, sector_ok, "C")
            return "top_feed", "C", badge

        # Path D — high-score override (iv-regime aware)
        iv = _iv_regime(signal_data)
        path_d_floor = PATH_D_FLOOR_HIGH_VOL if iv == "high_vol" else PATH_D_FLOOR_NORMAL
        if score >= path_d_floor and signal_type_raw in PATH_D_APPROVED_TYPES:
            badge = _compute_confluence_badge(pythia_ok, flow_ok, sector_ok, "D")
            return "top_feed", "D", badge

        # Pythia tiebreaker — score 73-74 with Path C otherwise satisfied
        # (Redis counter check happens in pipeline.py; signal_data carries
        # '_pythia_tiebreaker_approved' = True if counter allows it)
        if (
            PYTHIA_TIEBREAKER_MIN <= score <= PYTHIA_TIEBREAKER_MAX
            and pythia_ok
            and has_confluence
            and signal_data.get("_pythia_tiebreaker_approved")
        ):
            badge = _compute_confluence_badge(pythia_ok, flow_ok, sector_ok, "C")
            return "top_feed", "C", badge

    # ── ta_feed ───────────────────────────────────────────────────────────────
    if signal_type_raw in PATH_D_APPROVED_TYPES and score >= TA_FEED_FLOOR:
        return "ta_feed", "ta_feed", "none"

    # ── watchlist ─────────────────────────────────────────────────────────────
    if score >= WATCHLIST_FLOOR and strategy in WATCHLIST_APPROVED_STRATEGIES:
        return "watchlist", "watchlist", "none"

    # ── research_log ─────────────────────────────────────────────────────────
    if score >= RESEARCH_LOG_FLOOR:
        return "research_log", "research_log", "none"

    # Should not reach here given hard-floor check at top, but be safe
    return "research_log", "research_log", "none"
