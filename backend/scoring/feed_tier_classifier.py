"""
Feed Tier Classifier — ZEUS Phase 2

Classifies every signal into one of four feed tiers that control where
it surfaces in the Pandora's Box UI:

  top_feed     — Tier 1 UW flow trigger + Pythia confirmation + score >= 70
  watchlist    — WH-ACCUMULATION promotions OR signals capped by feed_tier_ceiling
  ta_feed      — TA scanner origin with decent score (>= 40), no Tier 1/2 confirmation
  research_log — Default (everything else, low score, unclassified)

Priority order:
  1. WATCHLIST_PROMOTION signal_category → always 'watchlist'
  2. feed_tier_ceiling cap applied by upstream (e.g. Pythia miss → never above 'watchlist')
  3. Tier 1 + Tier 2 + score threshold → 'top_feed'
  4. TA scanner signal type + adequate score → 'ta_feed'
  5. Default → 'research_log'
"""

from __future__ import annotations

from typing import Any, Dict

# ── Score thresholds ────────────────────────────────────────────────────────
TOP_FEED_SCORE_THRESHOLD = 70    # Minimum score to qualify for top_feed
TA_FEED_SCORE_THRESHOLD   = 40   # Minimum score to qualify for ta_feed

# ── Tier 3 signal types (TA scanners) ────────────────────────────────────────
# These are confluence *enrichers* for Tier 1 signals; their stacked bonus
# is capped at TIER3_MAX_BONUS when combined.
TIER3_SIGNAL_TYPES = {
    # CTA Scanner
    "GOLDEN_TOUCH", "TWO_CLOSE_VOLUME", "PULLBACK_ENTRY",
    "TRAPPED_LONGS", "TRAPPED_SHORTS", "BEARISH_BREAKDOWN",
    "DEATH_CROSS", "RESISTANCE_REJECTION",
    # Holy Grail
    "HOLY_GRAIL", "HOLY_GRAIL_1H", "HOLY_GRAIL_15M",
    # Scout Sniper
    "SCOUT_ALERT",
    # Sell the Rip
    "SELL_RIP_EMA", "SELL_RIP_VWAP", "SELL_RIP_EARLY",
    # Artemis
    "ARTEMIS", "ARTEMIS_LONG", "ARTEMIS_SHORT",
    # Phalanx
    "PHALANX", "PHALANX_BULL", "PHALANX_BEAR",
    # Exhaustion
    "EXHAUSTION", "EXHAUSTION_TOP", "EXHAUSTION_BOTTOM",
    # Sniper/Hunter legacy
    "SNIPER", "SNIPER_URSA", "SNIPER_TAURUS",
    "URSA_SIGNAL", "TAURUS_SIGNAL",
    # Triple Line
    "TRIPLE_LINE", "TRIPLE_LINE_TREND_RETRACEMENT", "TRIPLE LINE TREND RETRACEMENT",
}

# ── Tier 3 confluence weights ─────────────────────────────────────────────────
# Per-signal-type bonus when a TA signal confirms a Tier 1 signal.
# These are summed and then capped at TIER3_MAX_BONUS.
TIER3_CONFLUENCE_WEIGHTS: Dict[str, int] = {
    "GOLDEN_TOUCH":                     8,
    "DEATH_CROSS":                      8,
    "PULLBACK_ENTRY":                   6,
    "TWO_CLOSE_VOLUME":                 6,
    "HOLY_GRAIL_1H":                    6,
    "SELL_RIP_VWAP":                    6,
    "TRAPPED_LONGS":                    5,
    "TRAPPED_SHORTS":                   5,
    "BEARISH_BREAKDOWN":                5,
    "RESISTANCE_REJECTION":             5,
    "HOLY_GRAIL":                       5,
    "SELL_RIP_EMA":                     5,
    "PHALANX":                          5,
    "PHALANX_BULL":                     5,
    "PHALANX_BEAR":                     5,
    "HOLY_GRAIL_15M":                   4,
    "SCOUT_ALERT":                      4,
    "EXHAUSTION_TOP":                   4,
    "EXHAUSTION_BOTTOM":                4,
    "ARTEMIS":                          4,
    "ARTEMIS_LONG":                     4,
    "ARTEMIS_SHORT":                    4,
    "EXHAUSTION":                       3,
    "SELL_RIP_EARLY":                   3,
    "SNIPER":                           3,
    "SNIPER_URSA":                      3,
    "SNIPER_TAURUS":                    3,
    "URSA_SIGNAL":                      3,
    "TAURUS_SIGNAL":                    3,
    "TRIPLE_LINE":                      3,
    "TRIPLE_LINE_TREND_RETRACEMENT":    3,
    "TRIPLE LINE TREND RETRACEMENT":    3,
}

# Maximum stacked bonus from Tier 3 TA confluence
TIER3_MAX_BONUS = 20


# ── Helper: Tier 1 trigger detection ─────────────────────────────────────────

def _has_tier1_trigger(signal_data: Dict[str, Any]) -> bool:
    """
    Return True if the signal carries evidence of an active Tier 1 UW flow trigger.

    Tier 1 = strategy/signal_type begins with WH- / WH_ (Whale Hunter ZEUS)
             OR the P2C/P4A flow enrichment block produced a directional bonus > 3.
    """
    strategy    = (signal_data.get("strategy")    or "").upper()
    signal_type = (signal_data.get("signal_type") or "").upper()

    if strategy.startswith("WH-") or signal_type.startswith("WH_"):
        return True

    flow = (signal_data.get("triggering_factors") or {}).get("flow", {})
    if isinstance(flow, dict) and (flow.get("bonus") or 0) > 3:
        return True

    return False


# ── Helper: Pythia confirmation ───────────────────────────────────────────────

def _pythia_confirms(signal_data: Dict[str, Any]) -> bool:
    """
    Return True if Pythia has coverage of this ticker AND the profile position
    adjustment is >= 0 (signal is not penalized by Market Profile context).
    """
    pp = (signal_data.get("triggering_factors") or {}).get("profile_position", {})
    if not isinstance(pp, dict):
        return False
    if not pp.get("pythia_coverage", False):
        return False
    total_adj = pp.get("total_pythia_adjustment", pp.get("profile_bonus", 0)) or 0
    return total_adj >= 0


# ── Confluence cap ────────────────────────────────────────────────────────────

def apply_confluence_cap(raw_bonus: int) -> int:
    """Cap stacked Tier 3 TA confluence bonus at TIER3_MAX_BONUS (+20)."""
    return min(raw_bonus, TIER3_MAX_BONUS)


# ── Main classifier ───────────────────────────────────────────────────────────

def classify_signal_tier(signal_data: Dict[str, Any], score: float) -> str:
    """
    Classify a signal into its feed tier.

    Returns one of: 'top_feed', 'watchlist', 'ta_feed', 'research_log'

    See module docstring for tier definitions and priority order.
    """
    ceiling         = signal_data.get("feed_tier_ceiling")
    signal_category = (signal_data.get("signal_category") or "").upper()
    signal_type     = (signal_data.get("signal_type")     or "").upper()

    # ── 1. WATCHLIST_PROMOTION → always watchlist ──────────────────────────
    if signal_category == "WATCHLIST_PROMOTION":
        return "watchlist"

    # ── 2. top_feed: Tier 1 + Tier 2 + score threshold ────────────────────
    # Ceiling must not prohibit top_feed
    if ceiling not in ("watchlist", "ta_feed", "research_log"):
        if (
            _has_tier1_trigger(signal_data)
            and _pythia_confirms(signal_data)
            and score >= TOP_FEED_SCORE_THRESHOLD
        ):
            return "top_feed"

    # ── 3. Honour ceiling cap ──────────────────────────────────────────────
    if ceiling == "watchlist":
        return "watchlist"
    if ceiling == "ta_feed":
        # Fall through to ta_feed logic below
        pass
    if ceiling == "research_log":
        return "research_log"

    # ── 4. ta_feed: recognised TA scanner signal with adequate score ───────
    if signal_type in TIER3_SIGNAL_TYPES and score >= TA_FEED_SCORE_THRESHOLD:
        return "ta_feed"

    # ── 5. Default ─────────────────────────────────────────────────────────
    return "research_log"
