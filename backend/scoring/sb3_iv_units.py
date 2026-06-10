"""Sub-brief 3 — iv_rank unit conversion (Chunk 1b).

UW's purpose-built iv_rank endpoint returns `iv_rank_1y` as a 0–1 FRACTION.
The scorer's iv_bonus thresholds are on a 0–100 scale. The migration MUST
multiply by 100 — this module isolates that conversion so it can be unit-tested
(the forward unit-trap guard flagged in Phase 0).
"""

from __future__ import annotations

from typing import Optional


def iv_rank_1y_to_100(raw) -> Optional[float]:
    """Convert UW iv_rank_1y (0–1 fraction) to a 0–100 rank.

    Returns None for missing/non-numeric input (→ no_data, never a fake 0).
    Bounds to [0, 100] defensively.
    """
    if raw is None:
        return None
    try:
        v = float(raw) * 100.0
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(100.0, v)), 1)


def iv_bonus_from_rank(iv_rank: Optional[float]) -> int:
    """The scorer's iv_rank banding (0–100). None → 0 (caller labels reason).

    Mirrors score_v2's existing thresholds so the shadow computes the SAME
    bonus the live scorer would, on the new (UW true-rank) value.
    """
    if iv_rank is None:
        return 0
    try:
        v = float(iv_rank)
    except (TypeError, ValueError):
        return 0
    if v <= 20:
        return 3
    elif v <= 40:
        return 1
    elif v <= 60:
        return 0
    elif v <= 80:
        return -2
    return -5
