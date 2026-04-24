"""
Config loader — watchlist YAML + rate-limit throttle values.

Rate-limit values are set conservatively until Phase A probe results
are available. Update THROTTLE_* constants after running:
    docs/strategy-reviews/backtest/uw-rate-limit-findings.md
"""

import os
from pathlib import Path

import yaml

# ── Rate-limit throttle (update after Phase A probe) ─────────────────────────
# Conservative defaults: 30 req/min steady-state, 15 req burst
# These will be updated once uw-rate-limit-findings.md is written.
THROTTLE_SLEEP_BETWEEN_CALLS_S: float = 2.0   # 30 req/min
THROTTLE_MAX_BURST: int = 15                  # before a longer pause
THROTTLE_BURST_PAUSE_S: float = 5.0           # pause after each burst group

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _REPO_ROOT / "config"
_WATCHLIST_PATH = _CONFIG_DIR / "uw_logger_watchlist.yaml"

# Allow override via env var for VPS deploy flexibility
_WATCHLIST_OVERRIDE = os.environ.get("UW_LOGGER_WATCHLIST_PATH")


def load_watchlist() -> list[str]:
    """Load the ticker watchlist from YAML. Returns list of uppercase ticker strings."""
    path = Path(_WATCHLIST_OVERRIDE) if _WATCHLIST_OVERRIDE else _WATCHLIST_PATH
    if not path.exists():
        raise FileNotFoundError(f"Watchlist not found at {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    tickers = data.get("tickers", [])
    if not tickers:
        raise ValueError(f"No tickers found in watchlist at {path}")
    return [str(t).upper() for t in tickers]


def get_api_key() -> str:
    """Load UW API key from environment. Fails fast if missing."""
    key = os.environ.get("UW_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "UW_API_KEY not set. "
            "Source /etc/openclaw/openclaw.env before running this script."
        )
    return key
