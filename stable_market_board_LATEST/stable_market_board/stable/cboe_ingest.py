"""Ingest CBOE put/call ratio data from public CSV feeds.

Three series fetched daily:
  - equitypc.csv  Equity-only put/call ratio (the "retail sentiment" gauge)
  - indexpc.csv   Index put/call ratio (the "hedge demand" gauge)
  - totalpc.csv   Total put/call ratio (composite)

These are free, public, end-of-day updated CSVs from cboe.com.

Run with:  python -m stable.cboe_ingest
"""

from __future__ import annotations

import argparse
import io
from datetime import date
from typing import Optional

import pandas as pd
import requests
from rich.console import Console

from . import db

console = Console()

SOURCES = {
    "equity": "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv",
    "index":  "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpc.csv",
    "total":  "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpc.csv",
}


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cboe_pc (
    series  VARCHAR NOT NULL,    -- 'equity', 'index', or 'total'
    date    DATE    NOT NULL,
    call_vol  BIGINT,
    put_vol   BIGINT,
    total_vol BIGINT,
    pc_ratio  DOUBLE,
    PRIMARY KEY (series, date)
);

CREATE INDEX IF NOT EXISTS idx_cboe_date ON cboe_pc(date);
"""


def _parse_cboe_csv(text: str) -> pd.DataFrame:
    """The CBOE CSVs have varying leading disclaimer rows. The actual table starts
    at a row whose first cell parses as 'DATE' (case-insensitive). Parse from there.
    """
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        # Header rows look like:  "DATE,CALL,PUT,TOTAL,P/C Ratio"
        # or sometimes with leading whitespace like " DATE,..."
        first = line.split(",")[0].strip().upper()
        if first == "DATE" or first == "TRADE_DATE":
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not find header row in CBOE CSV")

    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    # Normalize column names
    df.columns = [c.strip().upper() for c in df.columns]
    # Handle both "DATE" and "TRADE_DATE"
    if "TRADE_DATE" in df.columns:
        df = df.rename(columns={"TRADE_DATE": "DATE"})
    # Standardize remaining names
    rename_map = {"P/C RATIO": "PC", "P/C": "PC", "RATIO": "PC"}
    for k, v in rename_map.items():
        if k in df.columns:
            df = df.rename(columns={k: v})

    required = {"DATE", "CALL", "PUT", "TOTAL", "PC"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CBOE CSV missing columns: {missing}, got {list(df.columns)}")

    df["date"] = pd.to_datetime(df["DATE"], errors="coerce").dt.date
    df = df.dropna(subset=["date"])
    df = df.rename(columns={"CALL": "call_vol", "PUT": "put_vol",
                            "TOTAL": "total_vol", "PC": "pc_ratio"})
    return df[["date", "call_vol", "put_vol", "total_vol", "pc_ratio"]]


def init_pc_schema() -> None:
    with db.connect() as conn:
        conn.execute(CREATE_TABLE_SQL)


def latest_date(series: str) -> Optional[date]:
    with db.connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT MAX(date) FROM cboe_pc WHERE series = ?", [series]
        ).fetchone()
    return row[0] if row and row[0] else None


def ingest_one(series: str, url: str) -> int:
    """Fetch one CBOE CSV, parse, upsert into DB. Returns rows written."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = _parse_cboe_csv(resp.text)
    df["series"] = series
    df = df[["series", "date", "call_vol", "put_vol", "total_vol", "pc_ratio"]]

    with db.connect() as conn:
        conn.register("incoming", df)
        # Upsert: delete then insert for this series
        conn.execute(
            "DELETE FROM cboe_pc WHERE series = ?", [series]
        )
        conn.execute("INSERT INTO cboe_pc SELECT * FROM incoming")
    return len(df)


def ingest_all() -> dict:
    init_pc_schema()
    summary = {}
    for series, url in SOURCES.items():
        try:
            n = ingest_one(series, url)
            summary[series] = n
            console.print(f"[green]OK[/green] {series}: {n} rows")
        except Exception as e:
            console.print(f"[red]FAIL[/red] {series}: {e}")
            summary[series] = 0
    return summary


def main():
    parser = argparse.ArgumentParser(description="Ingest CBOE put/call ratio data")
    parser.parse_args()
    ingest_all()


if __name__ == "__main__":
    main()
