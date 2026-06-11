"""Flow reconciliation — P4A-primary + P2 gap-fill + P2 read-fix (sub-brief 3 Chunk 2-R).

ONE flow bonus, never two (retires the P2/P4A double-count). Pure + unit-tested.

Design (locked rulings):
- P4A authoritative when it has a FRESH directional opinion → P2 suppressed (no
  direction vote on overlaps).
- fresh and conviction are DISTINCT flags (45-min freshness vs $2M conviction) —
  logged separately so both are tunable at promote; 'fresh-but-<$2M' is
  'recent-but-weak', not 'no opinion'.
- Where P4A is stale/absent/NEUTRAL → P2 gap-fills, but with a fixed read:
  premium-based direction, hedging-damped, and NEUTRAL-OR-POSITIVE ONLY (a
  known-error-prone yfinance gap-fill must never inflict a negative score).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

FRESHNESS_MIN = 45          # P4A freshness window (minutes) — tune at promote via 2R-b buckets
CONVICTION_USD = 2_000_000  # P4A conviction floor (directional premium)
HEDGING_PC = 3.0            # extreme put-volume threshold for the hedging damp
GAPFILL_NUDGE = 3           # small positive nudge for a confirming gap-fill (never negative)

_LONG = ("LONG", "BUY", "BULLISH")
_SHORT = ("SHORT", "SELL", "BEARISH")


def fixed_p2_read(
    pc_ratio: Optional[float],
    net_premium_direction: Optional[str],
    signal_direction: Optional[str],
) -> Dict[str, Any]:
    """P2's read-fixed, gap-fill-only contribution.

    Direction comes from PREMIUM (the sound part of P2), not the hedging-prone
    volume P/C. Hedging damp: extreme put volume (pc>3) with a BULLISH premium =
    cheap-put hedging → suppress (the XLK pc=13.31 false-bearish case). Output is
    floored at 0 — confirming flow → small positive nudge; everything else → 0.
    """
    npd = (net_premium_direction or "").lower()
    sig = (signal_direction or "").upper()
    sig_long = sig in _LONG
    sig_short = sig in _SHORT

    hedging = (pc_ratio is not None and pc_ratio > HEDGING_PC and npd == "bullish")
    if hedging:
        return {
            "bonus": 0,
            "direction": "neutral",
            "hedging_suppressed": True,
            "detail": f"pc={pc_ratio} put-volume spike vs bullish premium → hedging, P2 directional read suppressed",
        }

    confirming = (npd == "bullish" and sig_long) or (npd == "bearish" and sig_short)
    return {
        "bonus": GAPFILL_NUDGE if confirming else 0,  # neutral-or-positive ONLY
        "direction": npd or "neutral",
        "hedging_suppressed": False,
        "detail": "confirming" if confirming else "non-confirming/floored",
    }


def reconcile_flow(
    *,
    signal_direction: Optional[str],
    p4a_sentiment: Optional[str],
    p4a_call_premium: float = 0.0,
    p4a_put_premium: float = 0.0,
    p4a_age_min: Optional[float],
    p4a_raw_bonus: int = 0,
    p2_pc_ratio: Optional[float],
    p2_net_premium_direction: Optional[str],
    p2_raw_bonus: Optional[int] = None,
) -> Dict[str, Any]:
    """Reconcile P4A (primary) and P2 (gap-fill) into a single flow verdict.

    Returns the reconciled bonus + path + the DISTINCT flags 2R-b needs to bucket.
    """
    sent = (p4a_sentiment or "").upper()
    has_direction = sent in ("BULLISH", "BEARISH")
    directional_prem = (
        p4a_call_premium if sent == "BULLISH" else p4a_put_premium if sent == "BEARISH" else 0.0
    )

    p4a_fresh = p4a_age_min is not None and p4a_age_min <= FRESHNESS_MIN
    p4a_conviction = has_direction and directional_prem >= CONVICTION_USD

    fixed = fixed_p2_read(p2_pc_ratio, p2_net_premium_direction, signal_direction)

    if p4a_fresh and has_direction and p4a_conviction:
        path, bonus, suppressed = "overlap", int(p4a_raw_bonus or 0), True
    elif p4a_fresh and has_direction:
        # fresh-but-weak (<$2M): keep P4A's (weak) voice — recent, not 'no opinion'
        path, bonus, suppressed = "weak", int(p4a_raw_bonus or 0), True
    else:
        # stale, absent, or NEUTRAL → P2 gap-fills (neutral-or-positive only)
        path, bonus, suppressed = "gapfill", int(fixed["bonus"]), False

    return {
        "path": path,
        "reconciled_bonus": bonus,
        "suppressed_p2": suppressed,
        # distinct flags (tunable at promote)
        "p4a_fresh": p4a_fresh,
        "p4a_age_min": round(p4a_age_min, 1) if p4a_age_min is not None else None,
        "p4a_conviction": p4a_conviction,
        "p4a_directional_premium": directional_prem,
        "p4a_sentiment": sent or None,
        "p4a_raw_bonus": int(p4a_raw_bonus or 0),
        # P2 raw vs fixed
        "p2_raw_bonus": p2_raw_bonus,
        "p2_fixed_bonus": int(fixed["bonus"]),
        "p2_pc_ratio": p2_pc_ratio,
        "hedging_suppressed": fixed["hedging_suppressed"],
        "hedging_detail": fixed["detail"] if fixed["hedging_suppressed"] else None,
        "shadow": True,
    }
