"""SPY ADX → regime classification (sub-brief 3 Chunk 3).

Shared by the shadow comparison (now) and the live scorer gate (after the Chunk 3
promote), so both apply IDENTICAL thresholds. Removes the old confident default-25
('absent feed → always trending'): absent (None) or stale ADX → 'unknown' with
neutral handling — no penalty, no trending bonus, conservative alignment cap.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Thresholds unchanged from the legacy gate (trade_ideas_scorer regime block).
TRENDING_MIN = 25.0
TRANSITIONAL_MIN = 20.0

# Alignment-multiplier caps per regime (legacy values).
CAP_TRENDING = 1.25
CAP_TRANSITIONAL = 1.15
CAP_CHOPPY = 1.10
# 'unknown' is neutral: deny the 1.25 trending amplification we can't justify,
# but apply no penalty. (Review param — flagged in the Chunk 3 shadow gate.)
CAP_UNKNOWN = 1.10


def classify_adx_regime(adx: Optional[float], *, stale: bool = False) -> Dict[str, Any]:
    """Map a SPY ADX value to a regime dict.

    None or stale → 'unknown' (penalty 0, conservative cap, reason set). No
    confident default — the dead default-25 path is gone.
    """
    if adx is None or stale:
        return {
            "label": "unknown",
            "adx": adx,
            "penalty": 0,
            "max_align": CAP_UNKNOWN,
            "chop_eligible": False,
            "reason": "stale" if stale else "no_data",
        }
    if adx >= TRENDING_MIN:
        return {
            "label": "trending", "adx": round(adx, 1), "penalty": 0,
            "max_align": CAP_TRENDING, "chop_eligible": False, "reason": "ok",
        }
    if adx >= TRANSITIONAL_MIN:
        return {
            "label": "transitional", "adx": round(adx, 1), "penalty": -5,
            "max_align": CAP_TRANSITIONAL, "chop_eligible": False, "reason": "ok",
        }
    return {
        "label": "choppy", "adx": round(adx, 1), "penalty": -10,
        "max_align": CAP_CHOPPY, "chop_eligible": True, "reason": "ok",
    }
