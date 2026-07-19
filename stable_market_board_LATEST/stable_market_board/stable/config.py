"""Centralized configuration loaded from .env."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val or val == "your_key_here":
        raise RuntimeError(
            f"Environment variable {name} is not set. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


def _get(name: str, default: str) -> str:
    return os.getenv(name, default)


# Lazy: only required when actually fetching data
def polygon_api_key() -> str:
    return _require("POLYGON_API_KEY")


HISTORY_YEARS = int(_get("HISTORY_YEARS", "5"))
DB_PATH = PROJECT_ROOT / _get("DB_PATH", "./data/market.duckdb").lstrip("./")
UNIVERSE_PATH = PROJECT_ROOT / _get("UNIVERSE_PATH", "./data/universe.csv").lstrip("./")

# Ensure data directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
