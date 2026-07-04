"""Stable Engine configuration (paths only — no Polygon).

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
Math unchanged; data layer swapped Polygon->yfinance and DuckDB->Postgres.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_ROOT / "data"

HISTORY_YEARS = int(os.getenv("STABLE_HISTORY_YEARS", "5"))
UNIVERSE_PATH = Path(os.getenv("STABLE_UNIVERSE_PATH", str(DATA_DIR / "universe.csv")))

# Benchmark / index symbols pulled alongside the universe so RS and breadth have
# their reference series. These are tagged theme='Benchmark' and excluded from
# theme scoring (see scoring.EXCLUDED_THEMES).
BENCHMARK_SYMBOLS = ["SPY", "QQQ", "RSP", "IWM", "DIA"]
