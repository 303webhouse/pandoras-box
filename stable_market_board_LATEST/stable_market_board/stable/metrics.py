"""Compute per-ticker daily metrics from the prices table.

The MA periods to compute are configurable via settings.json. The metrics table
always has columns for all five possible periods (10, 20, 21, 50, 200); periods
not in the configured set are written as NULL.

Run with:  python -m stable.metrics
"""

from __future__ import annotations

import argparse
from typing import Optional

import numpy as np
import pandas as pd
from rich.console import Console
from rich.progress import Progress

from . import db, settings as settings_mod

console = Console()

BENCHMARKS = ("QQQ", "RSP")
ALL_MA_PERIODS = [10, 20, 21, 50, 200]


def _compute_for_ticker(
    prices: pd.DataFrame,
    benches: dict[str, pd.DataFrame],
    ma_periods: list[int],
) -> pd.DataFrame:
    """Compute metrics for one ticker. ma_periods controls which MAs are populated."""
    df = prices.copy().sort_values("date").reset_index(drop=True)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    prev_close = close.shift(1)

    # ---- Returns ----
    df["ret_1d"] = close.pct_change(1)
    df["ret_5d"] = close.pct_change(5)
    df["ret_20d"] = close.pct_change(20)
    df["ret_60d"] = close.pct_change(60)

    # ---- Moving averages: compute the configured set, NULL the others ----
    for period in ALL_MA_PERIODS:
        col_ma = f"ma_{period}"
        col_dist = f"dist_ma{period}_pct"
        col_above = f"above_ma{period}"
        if period in ma_periods:
            df[col_ma] = close.rolling(period, min_periods=period).mean()
            df[col_dist] = (close / df[col_ma] - 1.0)
            df[col_above] = (close > df[col_ma]).astype("Int8")
        else:
            df[col_ma] = np.nan
            df[col_dist] = np.nan
            df[col_above] = pd.array([pd.NA] * len(df), dtype="Int8")

    # ---- ATR(14) Wilder ----
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

    # ATR extension references the 50DMA; ensure we have it even if 50 isn't
    # in the configured set (compute on the fly without storing if needed)
    if 50 in ma_periods:
        ma50 = df["ma_50"]
    else:
        ma50 = close.rolling(50, min_periods=50).mean()
    df["atr_ext_50ma"] = (close - ma50) / df["atr_14"]

    # ---- Volume ----
    df["vol_ma_20"] = vol.rolling(20, min_periods=20).mean()
    df["vol_ratio"] = vol / df["vol_ma_20"]

    # ---- Highs / breakouts ----
    df["high_20d"] = high.rolling(20, min_periods=20).max()
    df["high_52w"] = high.rolling(252, min_periods=200).max()
    df["new_high_20d"] = (high >= df["high_20d"]).astype("int8")
    df["new_high_52w"] = (high >= df["high_52w"]).astype("int8")

    # ---- Relative strength ----
    for bench_name in BENCHMARKS:
        bench = benches.get(bench_name)
        if bench is None or bench.empty:
            df[f"rs_{bench_name.lower()}_20d"] = np.nan
            df[f"rs_{bench_name.lower()}_60d"] = np.nan
            continue
        bench_idx = bench.set_index("date")["close"]
        aligned = bench_idx.reindex(df["date"]).reset_index(drop=True)
        bench_ret_20 = aligned.pct_change(20)
        bench_ret_60 = aligned.pct_change(60)
        df[f"rs_{bench_name.lower()}_20d"] = df["ret_20d"] - bench_ret_20
        df[f"rs_{bench_name.lower()}_60d"] = df["ret_60d"] - bench_ret_60

    df["ticker"] = prices["ticker"].iloc[0]

    out_cols = [
        "ticker", "date",
        "ret_1d", "ret_5d", "ret_20d", "ret_60d",
        "ma_10", "ma_20", "ma_21", "ma_50", "ma_200",
        "dist_ma10_pct", "dist_ma20_pct", "dist_ma21_pct", "dist_ma50_pct", "dist_ma200_pct",
        "above_ma10", "above_ma20", "above_ma21", "above_ma50", "above_ma200",
        "atr_14", "atr_ext_50ma",
        "vol_ma_20", "vol_ratio",
        "high_20d", "high_52w", "new_high_20d", "new_high_52w",
        "rs_qqq_20d", "rs_qqq_60d", "rs_rsp_20d", "rs_rsp_60d",
    ]
    return df[out_cols]


def compute_metrics(tickers: Optional[list] = None) -> dict:
    """Compute metrics for all tickers (or a subset) and write to DuckDB."""
    db.init_schema()  # ensures v2 columns exist on older DBs

    cfg = settings_mod.load()
    ma_periods = cfg["metrics"]["ma_periods"]
    console.print(f"[cyan]Using MA periods: {ma_periods}[/cyan]")

    with db.connect(read_only=True) as conn:
        if tickers:
            placeholders = ",".join(["?"] * len(tickers))
            prices = conn.execute(
                f"SELECT * FROM prices WHERE ticker IN ({placeholders}) ORDER BY ticker, date",
                tickers,
            ).df()
        else:
            prices = conn.execute("SELECT * FROM prices ORDER BY ticker, date").df()

        bench_frames = {}
        for b in BENCHMARKS:
            bench_frames[b] = conn.execute(
                "SELECT * FROM prices WHERE ticker = ? ORDER BY date", [b]
            ).df()

    if prices.empty:
        console.print("[yellow]No prices found. Run ingestion first.[/yellow]")
        return {"tickers_processed": 0, "rows_written": 0}

    all_tickers = prices["ticker"].unique().tolist()
    out_frames: list = []

    with Progress(console=console) as progress:
        task = progress.add_task("Computing metrics", total=len(all_tickers))
        for t in all_tickers:
            sub = prices[prices["ticker"] == t]
            if len(sub) < 20:
                progress.update(task, advance=1)
                continue
            try:
                m = _compute_for_ticker(sub, bench_frames, ma_periods)
                out_frames.append(m)
            except Exception as e:
                console.print(f"[red]error computing metrics for {t}: {e}[/red]")
            progress.update(task, advance=1)

    if not out_frames:
        return {"tickers_processed": 0, "rows_written": 0}

    metrics_df = pd.concat(out_frames, ignore_index=True)

    with db.connect() as conn:
        affected = metrics_df["ticker"].unique().tolist()
        placeholders = ",".join(["?"] * len(affected))
        conn.execute(f"DELETE FROM metrics WHERE ticker IN ({placeholders})", affected)
        conn.register("metrics_in", metrics_df)
        conn.execute("INSERT INTO metrics SELECT * FROM metrics_in")

    summary = {
        "tickers_processed": len(out_frames),
        "rows_written": len(metrics_df),
        "ma_periods_computed": ma_periods,
    }
    console.print(
        f"[green]Done.[/green] {summary['tickers_processed']} tickers, "
        f"{summary['rows_written']:,} metric rows written."
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description="Compute per-ticker metrics from prices")
    parser.add_argument(
        "--tickers",
        nargs="*",
        help="Specific tickers to recompute (default: all).",
    )
    args = parser.parse_args()
    tickers = [t.upper() for t in args.tickers] if args.tickers else None
    compute_metrics(tickers=tickers)


if __name__ == "__main__":
    main()
