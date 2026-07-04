"""Load the universe CSV into Postgres (stable_universe).

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
Math unchanged; data layer swapped Polygon->yfinance and DuckDB->Postgres.
"""

from __future__ import annotations

import pandas as pd
from psycopg2.extras import execute_values

from . import config, db

REQUIRED_COLS = {"ticker", "name", "sector", "industry", "theme", "subtheme", "liquidity_tier"}

# Addendum A1: the 11 SPDR sector ETFs are force-tagged theme='Sector ETF' so they are
# EXCLUDED from theme scoring (see scoring.EXCLUDED_THEMES) but their metrics (50/200
# DMA states) still feed the sector-divergence legend. The vendored CSV is left pristine;
# the retag lives here.
SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care", "XLY": "Discretionary",
    "XLC": "Comm Services", "XLI": "Industrials", "XLP": "Staples", "XLE": "Energy",
    "XLU": "Utilities", "XLRE": "Real Estate", "XLB": "Materials",
}


def load_universe() -> pd.DataFrame:
    """Read universe.csv, validate, and replace stable_universe. Returns the dataframe."""
    if not config.UNIVERSE_PATH.exists():
        raise FileNotFoundError(
            f"Universe file not found at {config.UNIVERSE_PATH}. Place your universe.csv there."
        )

    df = pd.read_csv(config.UNIVERSE_PATH)

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Universe CSV missing columns: {missing}")

    df["ticker"] = df["ticker"].str.strip().str.upper()

    # Retag sector ETFs -> 'Sector ETF' (excluded from scoring; feed sector-divergence)
    mask = df["ticker"].isin(SECTOR_ETFS)
    df.loc[mask, "theme"] = "Sector ETF"
    df.loc[mask, "subtheme"] = df.loc[mask, "ticker"].map(SECTOR_ETFS)

    if df["ticker"].duplicated().any():
        dupes = df.loc[df["ticker"].duplicated(), "ticker"].tolist()
        raise ValueError(f"Duplicate tickers in universe: {dupes}")

    db.init_schema()
    cols = ["ticker", "name", "sector", "industry", "theme", "subtheme", "liquidity_tier"]
    rows = [tuple(None if pd.isna(v) else v for v in r) for r in df[cols].itertuples(index=False, name=None)]
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stable_universe")
            execute_values(
                cur,
                "INSERT INTO stable_universe (ticker, name, sector, industry, theme, subtheme, liquidity_tier) VALUES %s",
                rows,
                page_size=1000,
            )
    return df


def get_universe() -> pd.DataFrame:
    """Read the universe back from Postgres."""
    return db.read_df("SELECT * FROM stable_universe ORDER BY ticker")


def universe_tickers() -> list[str]:
    return get_universe()["ticker"].tolist()


if __name__ == "__main__":
    out = load_universe()
    print(f"Loaded {len(out)} tickers into stable_universe")
