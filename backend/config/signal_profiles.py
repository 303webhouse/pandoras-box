"""
R:R profiles that vary stop/target ATR multipliers by signal type and CTA zone.
"""

from typing import Tuple

# (signal_type, cta_zone) -> (stop_atr_multiplier, target_atr_multiplier)
RR_PROFILES = {
    # GOLDEN_TOUCH: Price pulling back to 20 SMA in uptrend
    ("GOLDEN_TOUCH", "MAX_LONG"): (1.0, 3.5),
    ("GOLDEN_TOUCH", "RECOVERY"): (1.25, 2.5),
    ("GOLDEN_TOUCH", "DE_LEVERAGING"): (1.5, 2.0),

    # PULLBACK_ENTRY: Deeper pullback to 50 SMA
    ("PULLBACK_ENTRY", "MAX_LONG"): (1.25, 3.0),
    ("PULLBACK_ENTRY", "RECOVERY"): (1.5, 2.5),
    ("PULLBACK_ENTRY", "DE_LEVERAGING"): (1.75, 2.0),

    # TWO_CLOSE_VOLUME: Breakout confirmation with volume
    ("TWO_CLOSE_VOLUME", "MAX_LONG"): (1.0, 3.0),
    ("TWO_CLOSE_VOLUME", "RECOVERY"): (1.25, 2.5),
    ("TWO_CLOSE_VOLUME", "DE_LEVERAGING"): (1.5, 2.0),

    # ZONE_UPGRADE: Zone just improved (e.g., WATERFALL -> RECOVERY)
    ("ZONE_UPGRADE", "RECOVERY"): (1.5, 2.0),
    ("ZONE_UPGRADE", "MAX_LONG"): (1.25, 2.5),
    ("ZONE_UPGRADE", "DE_LEVERAGING"): (2.0, 2.0),

    # TRAPPED_LONGS (short signal): Bearish capitulation play
    ("TRAPPED_LONGS", "WATERFALL"): (1.25, 3.5),
    ("TRAPPED_LONGS", "DE_LEVERAGING"): (1.5, 3.0),
    ("TRAPPED_LONGS", "CAPITULATION"): (1.5, 2.5),

    # TRAPPED_SHORTS (long signal): Short squeeze play
    ("TRAPPED_SHORTS", "MAX_LONG"): (1.0, 3.5),
    ("TRAPPED_SHORTS", "RECOVERY"): (1.25, 3.0),
}

DEFAULT_PROFILE: Tuple[float, float] = (1.5, 3.0)


def get_rr_profile(signal_type: str, cta_zone: str) -> Tuple[float, float]:
    """
    Return (stop_atr_mult, target_atr_mult) for a given signal + zone combination.
    Falls back to DEFAULT_PROFILE if no specific profile exists.
    """
    profile = RR_PROFILES.get((signal_type, cta_zone))
    if profile:
        return profile

    # Try signal type with any zone
    for (sig, _zone), prof in RR_PROFILES.items():
        if sig == signal_type:
            return prof

    return DEFAULT_PROFILE
