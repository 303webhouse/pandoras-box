"""User-configurable settings for the Stable Engine.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
Math unchanged; data layer swapped Polygon->yfinance and DuckDB->Postgres.

Threshold settings (breadth, extension cutoffs) apply at query time. Defaults match
the original hardcoded values so behavior is unchanged until customized.
"""

from __future__ import annotations

import json
from typing import Any

from . import config

SETTINGS_PATH = config.DATA_DIR / "settings.json"

DEFAULTS: dict[str, Any] = {
    "metrics": {
        "ma_periods": [20, 50, 200],          # which MAs to compute (subset of [10,20,21,50,200])
        "return_periods": [1, 5, 20, 60],
    },
    "breadth": {
        "big_move_threshold": 0.04,           # 4% = the "up 4% / down 4%" line
    },
    "extension": {
        "too_hot_atr_threshold": 8.0,
        "clean_momentum_atr_min": 1.0,
        "clean_momentum_atr_max": 5.0,
        "clean_momentum_min_vol_ratio": 1.0,
        "clean_momentum_min_ret_5d": 0.0,
    },
}

ALLOWED_MA_PERIODS = [10, 20, 21, 50, 200]


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    if not SETTINGS_PATH.exists():
        return _deep_merge(DEFAULTS, {})
    try:
        with open(SETTINGS_PATH) as f:
            user_settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _deep_merge(DEFAULTS, {})
    return _deep_merge(DEFAULTS, user_settings)


def save(settings: dict) -> dict:
    validated = validate(settings)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(validated, f, indent=2)
    return load()


def validate(settings: dict) -> dict:
    out = _deep_merge(DEFAULTS, settings or {})

    periods = out["metrics"].get("ma_periods", DEFAULTS["metrics"]["ma_periods"])
    periods = [p for p in periods if p in ALLOWED_MA_PERIODS]
    if not periods:
        periods = DEFAULTS["metrics"]["ma_periods"]
    out["metrics"]["ma_periods"] = sorted(set(periods))

    b = float(out["breadth"]["big_move_threshold"])
    out["breadth"]["big_move_threshold"] = max(0.005, min(0.20, b))

    e = out["extension"]
    e["too_hot_atr_threshold"] = max(1.0, min(20.0, float(e["too_hot_atr_threshold"])))
    e["clean_momentum_atr_min"] = max(-5.0, min(20.0, float(e["clean_momentum_atr_min"])))
    e["clean_momentum_atr_max"] = max(-5.0, min(20.0, float(e["clean_momentum_atr_max"])))
    if e["clean_momentum_atr_max"] <= e["clean_momentum_atr_min"]:
        e["clean_momentum_atr_max"] = e["clean_momentum_atr_min"] + 1.0
    e["clean_momentum_min_vol_ratio"] = max(0.0, min(10.0, float(e["clean_momentum_min_vol_ratio"])))
    e["clean_momentum_min_ret_5d"] = max(-1.0, min(1.0, float(e["clean_momentum_min_ret_5d"])))

    return out
