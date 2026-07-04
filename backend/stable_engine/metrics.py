"""Compute per-ticker daily metrics from stable_daily_bars.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
Math unchanged; data layer swapped Polygon->yfinance and DuckDB->Postgres.

The MA periods to compute are configurable via settings. The metrics table always
has columns for all five possible periods (10, 20, 21, 50, 200); periods not in the
configured set are written as NULL.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values

from . import db, settings as settings_mod

logger = logging.getLogger(__name__)

BENCHMARKS = ("QQQ", "RSP")
ALL_MA_PERIODS = [10, 20, 21, 50, 200]

_OUT_COLS = [
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


def _compute_for_ticker(
    prices: pd.DataFrame,
    benches: dict[str, pd.DataFrame],
    ma_periods: Optional[list[int]] = None,
) -> pd.DataFrame:
    """Compute metrics for one ticker. ma_periods controls which MAs are populated.

    Math is byte-identical to the source engine. ma_periods defaults to the full set
    so direct callers (e.g. the synthetic unit test) get every MA populated.
    """
    if ma_periods is None:
        ma_periods = list(ALL_MA_PERIODS)

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

    return df[_OUT_COLS]


def _read_prices(tickers: Optional[list] = None) -> pd.DataFrame:
    """Read bars from stable_daily_bars, aliased to the engine's OHLCV column names."""
    base = ("SELECT ticker, date, o AS open, h AS high, l AS low, c AS close, v AS volume "
            "FROM stable_daily_bars")
    if tickers:
        placeholders = ",".join(["%s"] * len(tickers))
        return db.read_df(f"{base} WHERE ticker IN ({placeholders}) ORDER BY ticker, date", tickers)
    return db.read_df(f"{base} ORDER BY ticker, date")


def _to_pyval(v):
    """Coerce numpy/pandas scalars to plain Python (NaN/NA -> None) for psycopg2."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if hasattr(v, "isoformat"):
        return v
    return v


def compute_metrics(tickers: Optional[list] = None) -> dict:
    """Compute metrics for all tickers (or a subset) and write to stable_metrics."""
    db.init_schema()

    cfg = settings_mod.load()
    ma_periods = cfg["metrics"]["ma_periods"]
    logger.info("[stable_metrics] Using MA periods: %s", ma_periods)

    prices = _read_prices(tickers)
    bench_frames = {}
    for b in BENCHMARKS:
        bench_frames[b] = _read_prices([b])

    if prices.empty:
        logger.warning("[stable_metrics] No prices found. Run ingestion first.")
        return {"tickers_processed": 0, "rows_written": 0}

    all_tickers = prices["ticker"].unique().tolist()
    out_frames: list = []
    for t in all_tickers:
        sub = prices[prices["ticker"] == t]
        if len(sub) < 20:
            continue
        try:
            out_frames.append(_compute_for_ticker(sub, bench_frames, ma_periods))
        except Exception as e:
            logger.error("[stable_metrics] error computing metrics for %s: %s", t, e)

    if not out_frames:
        return {"tickers_processed": 0, "rows_written": 0}

    metrics_df = pd.concat(out_frames, ignore_index=True)[_OUT_COLS]

    affected = metrics_df["ticker"].unique().tolist()
    rows = [tuple(_to_pyval(v) for v in rec) for rec in metrics_df.itertuples(index=False, name=None)]
    col_list = ", ".join(_OUT_COLS)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in _OUT_COLS if c not in ("ticker", "date"))
    with db.connect() as conn:
        with conn.cursor() as cur:
            ph = ",".join(["%s"] * len(affected))
            cur.execute(f"DELETE FROM stable_metrics WHERE ticker IN ({ph})", affected)
            execute_values(
                cur,
                f"INSERT INTO stable_metrics ({col_list}) VALUES %s "
                f"ON CONFLICT (ticker, date) DO UPDATE SET {update_set}",
                rows,
                page_size=5000,
            )

    summary = {
        "tickers_processed": len(out_frames),
        "rows_written": len(metrics_df),
        "ma_periods_computed": ma_periods,
    }
    logger.info("[stable_metrics] Done. %d tickers, %d metric rows written.",
                summary["tickers_processed"], summary["rows_written"])
    return summary


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description="Compute per-ticker metrics from stable_daily_bars")
    p.add_argument("--tickers", nargs="*", help="Specific tickers to recompute (default: all).")
    args = p.parse_args()
    compute_metrics([t.upper() for t in args.tickers] if args.tickers else None)
