"""L1a — Auction + Flow signal-quality gate (SHADOW-first).

The real "the auction accepted the level (PYTHIA) AND order flow confirmed (UW)"
gate. SHADOW: computes a decision and tags it under triggering_factors["l1_shadow"];
DIVERTS NOTHING. Inserted in the chokepoint (process_signal_unified) in the
step-3d zone — AFTER apply_scoring (which reassigns triggering_factors wholesale
~L689) and BESIDE the L0.1a l0_shadow tag, BEFORE log_signal.

Feature flag L1_GATE_SHADOW (default OFF): when off, evaluate_l1_gate returns None
(zero overhead, no tag) — deploying is fully inert until Nick flips it on to start
shadow collection. Enforce (divert) is a separate, later, separately-gated step.

Scope: the 20-ticker LIQUID_UNIVERSE (config.liquid_universe). Non-liquid signals
get a minimal {gate:"out_of_scope"} tag.

Flow (corrections per Phase-0 addendum): read RAW call/put/total from
triggering_factors["flow"]; IGNORE its pre-computed sentiment/bonus (old volume
P/C logic, observed mis-tagging premium-bullish reads as BEARISH). Confirm iff
sign(net) matches direction AND ratio=|net|/total >= L1_FLOW_DOMINANCE_RATIO
(env, default 0.15 — a self-scaling dominance ratio, NOT a dollar threshold:
per-ticker premium spans 3 orders of magnitude, so a dollar bar repeats the
_flow_aligned scale-mismatch bug). Missing/stale flow → "unavailable", never confirms.

Auction (soft PYTHIA, Nick's design): 3-state, not binary. fresh+accepted → pass;
stale OR missing → asterisk (soft → PYTHIA review); feed genuinely down (RTH) →
loud debounced alarm. Reuses the MP read-path 3-state freshness
(services/read_only/market_profile.get_market_profile). pythia_events.direction is
empty live → acceptance derived from interpretation + poor-extremes + the SIGNAL's
direction. Regime-conditioning (ADX / signals.regime) DEFERRED — sb3 not promoted
(signals.regime 100% NULL); do not fabricate day_type.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, time as _time, timezone
from typing import Any, Dict, Optional

from zoneinfo import ZoneInfo

from config.liquid_universe import is_liquid

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

LONG_DIRS = {"LONG", "BUY", "BULLISH"}
SHORT_DIRS = {"SHORT", "SELL", "BEARISH"}

# MP feed-down alarm (mirrors Chunk 3's flow watchdog; SEPARATE latch).
_MP_DEAD_LATCH = "alarm:mp_dead:active"
_MP_DEAD_LATCH_TTL = 7200          # ~2h — one alarm per dead episode
_MP_GLOBAL_STALE_S = 1800          # >30min global pythia silence during RTH = feed down


def _shadow_enabled() -> bool:
    """L1_GATE_SHADOW flag (default OFF). Off → gate is fully inert (no tag)."""
    return (os.getenv("L1_GATE_SHADOW") or "false").strip().lower() in ("1", "true", "yes", "on")


def _dominance_ratio() -> float:
    try:
        return float(os.getenv("L1_FLOW_DOMINANCE_RATIO") or "0.15")
    except (TypeError, ValueError):
        return 0.15


def _norm_dir(d: Optional[str]) -> str:
    return (d or "").strip().upper()


def _in_rth() -> bool:
    """Strict 09:30–16:00 ET (weekday). Matches the Chunk 3 watchdog gate; NOT the
    looser api/sectors._is_market_hours (which over-extends to ~16:30)."""
    now = datetime.now(_ET)
    if now.weekday() >= 5:
        return False
    return _time(9, 30) <= now.time() <= _time(16, 0)


# ── Flow half (pure) ─────────────────────────────────────────────────────────
def evaluate_flow(flow: Optional[Dict[str, Any]], direction: str) -> Dict[str, Any]:
    """Pure. Reads raw call/put/total; ignores the sub-dict's sentiment/bonus.

    confirms iff sign(net) matches direction AND ratio >= dominance threshold.
    Absent flow key → state="missing" (never confirms — the L1.0 honesty rule).
    """
    d = _norm_dir(direction)
    if not isinstance(flow, dict) or (flow.get("call_premium") is None and flow.get("put_premium") is None):
        return {"call": None, "put": None, "net": None, "total": None, "ratio": None,
                "aligned": None, "confirms": False, "contradicts": False, "state": "missing"}

    call = float(flow.get("call_premium") or 0)
    put = float(flow.get("put_premium") or 0)
    total = float(flow.get("total_premium") or (call + put))
    net = call - put
    ratio = (abs(net) / total) if total > 0 else None

    aligned: Optional[bool] = None
    if net != 0:
        if d in LONG_DIRS:
            aligned = net > 0
        elif d in SHORT_DIRS:
            aligned = net < 0

    dominant = ratio is not None and ratio >= _dominance_ratio()
    confirms = bool(aligned) and dominant
    contradicts = (aligned is False) and dominant
    return {"call": call, "put": put, "net": net, "total": total,
            "ratio": round(ratio, 4) if ratio is not None else None,
            "aligned": aligned, "confirms": confirms, "contradicts": contradicts, "state": "fresh"}


# ── Auction half ─────────────────────────────────────────────────────────────
def acceptance_from_interpretation(interp: Optional[str], direction: str,
                                   poor_high: Optional[bool], poor_low: Optional[bool]) -> Optional[bool]:
    """v1 heuristic over the plain-English `interpretation` + poor extremes + the
    SIGNAL's direction (pythia_events.direction is empty live). True=accepted,
    False=rejected/caution, None=ambiguous. Raw fields are logged so this refines
    on shadow data."""
    if not interp:
        return None
    t = interp.lower()
    d = _norm_dir(direction)
    long_acc = ("initiative buying", "breakout to upside", "institutional buying",
                "acceptance above", "buying zone")
    short_acc = ("initiative selling", "breakdown", "distribution",
                 "acceptance below", "selling zone")
    caution = ("caution", "thin extension", "watch for")

    acc: Optional[bool] = None
    if d in LONG_DIRS:
        if any(w in t for w in long_acc):
            acc = True
        if poor_high:           # rejection risk at a poor high for a long
            acc = False
    elif d in SHORT_DIRS:
        if any(w in t for w in short_acc):
            acc = True
        if poor_low:
            acc = False
    if acc is None and any(w in t for w in caution):
        acc = False
    return acc


async def _maybe_mp_feed_down_alarm() -> None:
    """Debounced, RTH-gated MP-feed-down alarm. Only consulted when a signal's
    auction is non-fresh during RTH; checks GLOBAL pythia_events freshness so a
    single quiet ticker (normal) isn't mistaken for a dead feed. Mirrors Chunk 3."""
    try:
        from database.redis_client import get_redis_client
        from database.postgres_client import get_postgres_client
        redis = await get_redis_client()
        if not redis:
            return
        latched = bool(await redis.get(_MP_DEAD_LATCH))
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT MAX(timestamp) AS m FROM pythia_events")
        m = row["m"] if row else None
        if m is not None and getattr(m, "tzinfo", None) is None:
            m = m.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - m).total_seconds() if m else None
        down = (age is None) or (age > _MP_GLOBAL_STALE_S)
        if down and not latched:
            from bias_engine.anomaly_alerts import send_alert
            await send_alert(
                "🚨 MP (PYTHIA) feed dead",
                f"No pythia_events within {_MP_GLOBAL_STALE_S}s during RTH "
                f"(global newest age={int(age) if age is not None else 'none'}s).",
                severity="warning",
            )
            await redis.set(_MP_DEAD_LATCH, "1", ex=_MP_DEAD_LATCH_TTL)
            logger.warning("MP feed-down alarm FIRED (global pythia silence)")
        elif (not down) and latched:
            from bias_engine.anomaly_alerts import send_alert
            await send_alert("✅ MP feed restored", f"pythia_events fresh again (age={int(age)}s).", severity="info")
            await redis.delete(_MP_DEAD_LATCH)
            logger.info("MP feed-down alarm CLEARED")
    except Exception as e:
        logger.warning("MP feed-down alarm check failed (non-blocking): %s", e)


async def evaluate_auction(ticker: str, direction: str) -> Dict[str, Any]:
    """3-state soft-PYTHIA auction read on the MP read-path freshness.

    closed (not RTH) / fresh_accepted / asterisk (stale OR missing OR not-accepted).
    Fires the debounced global feed-down alarm when non-fresh during RTH.
    """
    base: Dict[str, Any] = {"interpretation": None, "va_migration": None, "direction": None,
                            "poor_high": None, "poor_low": None, "accepted": None,
                            "state": None, "age_seconds": None}
    if not _in_rth():
        base["state"] = "closed"          # market closed → not-applicable (not a fault)
        return base

    try:
        from services.read_only.market_profile import get_market_profile
        mp = await get_market_profile(ticker)
    except Exception as e:
        logger.warning("L1 auction MP read failed for %s: %s", ticker, e)
        mp = None

    if mp is None:
        base["state"] = "asterisk"        # missing for this ticker (soft); maybe feed-down (global check)
        await _maybe_mp_feed_down_alarm()
        return base

    data = mp.get("data") or {}
    status = mp.get("status")
    interp = data.get("interpretation")
    base.update({
        "interpretation": interp,
        "va_migration": data.get("va_migration"),
        "poor_high": data.get("poor_high"),
        "poor_low": data.get("poor_low"),
        "age_seconds": data.get("event_age_seconds"),
    })
    accepted = acceptance_from_interpretation(interp, direction, data.get("poor_high"), data.get("poor_low"))
    base["accepted"] = accepted

    if status == "ok" and accepted:
        base["state"] = "fresh_accepted"
    else:
        base["state"] = "asterisk"        # stale, or fresh-but-not-clearly-accepted
        await _maybe_mp_feed_down_alarm()  # global check (debounced) — distinguishes down vs quiet
    return base


def _decide(flow: Dict[str, Any], auction: Dict[str, Any]) -> str:
    """Shadow gate decision. pass / asterisk / flow_unavailable / fail."""
    if flow["state"] != "fresh":
        return "flow_unavailable"          # never confirm on absent/stale flow
    if flow["contradicts"]:
        return "fail"                      # dominant flow against the signal direction
    if flow["confirms"]:
        return "pass" if auction["state"] == "fresh_accepted" else "asterisk"
    return "asterisk"                      # flow present but inconclusive (ratio < threshold)


async def evaluate_l1_gate(signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compute the L1a shadow decision for one signal, or None if the flag is off.

    Returns the triggering_factors["l1_shadow"] tag. Pure of side effects except
    the debounced MP feed-down alarm. NEVER diverts routing.
    """
    if not _shadow_enabled():
        return None

    ticker = signal_data.get("ticker")
    direction = signal_data.get("direction")

    if not is_liquid(ticker):
        return {"gate": "out_of_scope", "reason": "non_liquid_universe",
                "regime_conditioning": "deferred_sb3_null"}

    tf = signal_data.get("triggering_factors") or {}
    flow = evaluate_flow(tf.get("flow"), direction)
    auction = await evaluate_auction(ticker, direction)
    gate = _decide(flow, auction)

    return {
        "flow": {k: flow[k] for k in ("call", "put", "net", "total", "ratio", "aligned", "state")},
        "auction": {k: auction[k] for k in ("interpretation", "va_migration", "direction",
                                            "poor_high", "poor_low", "accepted", "state")},
        "gate": gate,
        "regime_conditioning": "deferred_sb3_null",
    }
