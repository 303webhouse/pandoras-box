"""User-configurable settings for the Stable Market Board.

Settings are stored in data/settings.json and loaded on demand.
- Calculation settings (MA periods) require re-running `python -m stable.metrics` to take effect.
- Threshold settings (breadth, extension cutoffs) apply at query time, no recompute needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from . import config


SETTINGS_PATH = config.PROJECT_ROOT / "data" / "settings.json"

# Defaults. Match the original hardcoded values so behavior is unchanged
# until the user customizes.
DEFAULTS: dict[str, Any] = {
    "metrics": {
        "ma_periods": [20, 50, 200],          # which MAs to compute (subset of [10,20,21,50,200])
        "return_periods": [1, 5, 20, 60],     # not currently configurable in UI but here for future
    },
    "breadth": {
        "big_move_threshold": 0.04,           # 4% = the "up 4% / down 4%" line on Daily Board
    },
    "extension": {
        "too_hot_atr_threshold": 8.0,         # ATRs above 50DMA to qualify as "too hot"
        "clean_momentum_atr_min": 1.0,        # ATR ext lower bound for clean momentum
        "clean_momentum_atr_max": 5.0,        # ATR ext upper bound
        "clean_momentum_min_vol_ratio": 1.0,  # min volume ratio for clean momentum
        "clean_momentum_min_ret_5d": 0.0,     # min 5-day return for clean momentum
    },
}

ALLOWED_MA_PERIODS = [10, 20, 21, 50, 200]


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` onto `base`. Returns a new dict."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    """Load settings from disk, merged with defaults so missing keys are filled in."""
    if not SETTINGS_PATH.exists():
        return _deep_merge(DEFAULTS, {})
    try:
        with open(SETTINGS_PATH) as f:
            user_settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _deep_merge(DEFAULTS, {})
    return _deep_merge(DEFAULTS, user_settings)


def save(settings: dict) -> dict:
    """Validate and save settings. Returns the saved (and re-loaded) settings."""
    validated = validate(settings)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(validated, f, indent=2)
    return load()


def validate(settings: dict) -> dict:
    """Sanity-check incoming settings, clamp/correct where reasonable."""
    out = _deep_merge(DEFAULTS, settings or {})

    # MA periods: must be subset of allowed, must include at least one
    periods = out["metrics"].get("ma_periods", DEFAULTS["metrics"]["ma_periods"])
    periods = [p for p in periods if p in ALLOWED_MA_PERIODS]
    if not periods:
        periods = DEFAULTS["metrics"]["ma_periods"]
    out["metrics"]["ma_periods"] = sorted(set(periods))

    # Breadth threshold: clamp 0.005 to 0.20
    b = float(out["breadth"]["big_move_threshold"])
    out["breadth"]["big_move_threshold"] = max(0.005, min(0.20, b))

    # Extension thresholds
    e = out["extension"]
    e["too_hot_atr_threshold"] = max(1.0, min(20.0, float(e["too_hot_atr_threshold"])))
    e["clean_momentum_atr_min"] = max(-5.0, min(20.0, float(e["clean_momentum_atr_min"])))
    e["clean_momentum_atr_max"] = max(-5.0, min(20.0, float(e["clean_momentum_atr_max"])))
    if e["clean_momentum_atr_max"] <= e["clean_momentum_atr_min"]:
        e["clean_momentum_atr_max"] = e["clean_momentum_atr_min"] + 1.0
    e["clean_momentum_min_vol_ratio"] = max(0.0, min(10.0, float(e["clean_momentum_min_vol_ratio"])))
    e["clean_momentum_min_ret_5d"] = max(-1.0, min(1.0, float(e["clean_momentum_min_ret_5d"])))

    return out
