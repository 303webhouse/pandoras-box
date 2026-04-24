"""
Config loader — watchlist YAML + rate-limit throttle values.

Rate-limit values are set conservatively until Phase A probe results
are available. Update THROTTLE_* constants after running:
    docs/strategy-reviews/backtest/uw-rate-limit-findings.md
"""

import os
from pathlib import Path

import yaml

# ── Rate-limit throttle (from Phase A probe — 2026-04-24) ────────────────────
# Probe results: burst 429 triggers at request #13 (rapid-fire).
# Sustained 1 rps: 60/60 success (0 429s). No Retry-After header observed.
# Interpretation: sliding burst window ~12 req; no per-minute hard cap at 1 rps.
#
# Settings: 10-call burst groups (below 12-limit), 1s between calls,
# 15s pause between groups. Gives ~1.7 min for 50 calls (10 tickers × 5 types).
# Well within 30-min alert threshold even with darkpool pagination.
THROTTLE_SLEEP_BETWEEN_CALLS_S: float = 1.0   # 1 rps — matches sustained test
THROTTLE_MAX_BURST: int = 10                  # below 12-request burst limit
THROTTLE_BURST_PAUSE_S: float = 15.0          # pause after each burst group

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
