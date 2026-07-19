"""Load the universe CSV into DuckDB."""

import pandas as pd
from rich.console import Console

from . import config, db

console = Console()


def load_universe() -> pd.DataFrame:
    """Read universe.csv, validate, and upsert to DuckDB. Returns the dataframe."""
    if not config.UNIVERSE_PATH.exists():
        raise FileNotFoundError(
            f"Universe file not found at {config.UNIVERSE_PATH}. "
            f"Place your universe.csv there."
        )

    df = pd.read_csv(config.UNIVERSE_PATH)

    required_cols = {"ticker", "name", "sector", "industry",
                     "theme", "subtheme", "liquidity_tier"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Universe CSV missing columns: {missing}")

    df["ticker"] = df["ticker"].str.strip().str.upper()

    if df["ticker"].duplicated().any():
        dupes = df.loc[df["ticker"].duplicated(), "ticker"].tolist()
        raise ValueError(f"Duplicate tickers in universe: {dupes}")

    db.init_schema()
    with db.connect() as conn:
        conn.execute("DELETE FROM universe")
        conn.register("universe_df", df)
        conn.execute("INSERT INTO universe SELECT * FROM universe_df")

    console.print(f"[green]Loaded {len(df)} tickers into universe table[/green]")
    return df


def get_universe() -> pd.DataFrame:
    """Read the universe back from DuckDB."""
    with db.connect(read_only=True) as conn:
        return conn.execute("SELECT * FROM universe ORDER BY ticker").df()


if __name__ == "__main__":
    load_universe()
