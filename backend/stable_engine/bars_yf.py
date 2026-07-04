"""Batched yfinance daily OHLCV downloader for the Stable Engine.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
Data layer swapped Polygon->yfinance (sanctioned fallback: EOD/context data, not
execution-path data). Zero UW calls.

Coverage contract (house rule): every batch logs fetched/missing counts; callers
mark a run degraded when coverage < 90% and log which tickers failed. We NEVER fill
gaps with fabricated or stale-as-fresh values — a missing ticker is simply absent.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import pandas as pd

from . import config, db

logger = logging.getLogger(__name__)

# Prices use auto-adjusted OHLC (splits + dividends) so MAs/returns/ATR have no
# artificial gaps — standard for technical metrics.
_AUTO_ADJUST = True


def _extract_ticker_frame(data: pd.DataFrame, ticker: str, single: bool) -> pd.DataFrame | None:
    """Pull a single ticker's OHLCV frame out of a yfinance download result."""
    try:
        if single:
            sub = data
        elif isinstance(data.columns, pd.MultiIndex):
            if ticker not in data.columns.get_level_values(0):
                return None
            sub = data[ticker]
        else:
            sub = data
    except Exception:
        return None

    if sub is None or sub.empty:
        return None
    sub = sub.dropna(how="all")
    if sub.empty or "Close" not in sub.columns:
        return None

    out = pd.DataFrame({
        "date": pd.to_datetime(sub.index).date,
        "o": sub["Open"].astype(float) if "Open" in sub else None,
        "h": sub["High"].astype(float) if "High" in sub else None,
        "l": sub["Low"].astype(float) if "Low" in sub else None,
        "c": sub["Close"].astype(float),
        "v": sub["Volume"].fillna(0).astype("int64") if "Volume" in sub else 0,
    })
    out = out.dropna(subset=["c"])
    return out if not out.empty else None


def fetch_batch(tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    """Download one batch of tickers. Retry once with backoff. Returns {ticker: frame}."""
    import yfinance as yf

    tickers = [t for t in tickers if t]
    if not tickers:
        return {}

    last_err = None
    for attempt in (1, 2):
        try:
            data = yf.download(
                tickers, start=start.isoformat(), end=end.isoformat(),
                auto_adjust=_AUTO_ADJUST, group_by="ticker",
                progress=False, threads=True, actions=False,
            )
            single = len(tickers) == 1
            out: dict[str, pd.DataFrame] = {}
            if data is not None and not data.empty:
                for t in tickers:
                    frame = _extract_ticker_frame(data, t, single)
                    if frame is not None:
                        out[t] = frame
            return out
        except Exception as e:  # transient network/yfinance error
            last_err = e
            logger.warning("[stable_bars] batch attempt %d failed (%d tickers): %s",
                           attempt, len(tickers), e)
            if attempt == 1:
                time.sleep(1.5)
    logger.error("[stable_bars] batch permanently failed after retry: %s", last_err)
    return {}


def download_and_store(
    tickers: list[str],
    years: int | None = None,
    end: date | None = None,
    batch_size: int = 100,
    block_tickers: set[str] | None = None,
) -> dict:
    """Download `years` of daily bars for `tickers`, upsert to stable_daily_bars.

    Args:
        block_tickers: simulate a partial outage — these tickers are skipped from the
            request entirely (degraded-run test), never fabricated.

    Returns a coverage summary. degraded=True when coverage < 90% of the request.
    """
    years = years or config.HISTORY_YEARS
    end = end or (date.today() + timedelta(days=1))  # yfinance end is exclusive
    start = date(end.year - years, end.month, end.day)
    block_tickers = block_tickers or set()

    requested = [t for t in dict.fromkeys(tickers) if t and t not in block_tickers]  # dedupe, drop blocked
    skipped_blocked = [t for t in tickers if t in block_tickers]

    db.init_schema()

    fetched: list[str] = []
    missing: list[str] = []
    rows_written = 0

    for i in range(0, len(requested), batch_size):
        batch = requested[i:i + batch_size]
        result = fetch_batch(batch, start, end)
        batch_rows = []
        for t in batch:
            frame = result.get(t)
            if frame is None or frame.empty:
                missing.append(t)
                continue
            fetched.append(t)
            for r in frame.itertuples(index=False, name=None):
                # r = (date, o, h, l, c, v)
                d, o, h, l, c, v = r
                batch_rows.append((t, d,
                                   None if pd.isna(o) else float(o),
                                   None if pd.isna(h) else float(h),
                                   None if pd.isna(l) else float(l),
                                   None if pd.isna(c) else float(c),
                                   int(v) if not pd.isna(v) else 0))
        rows_written += db.upsert_bars(batch_rows)
        logger.info("[stable_bars] batch %d-%d: %d/%d fetched, %d rows",
                    i, i + len(batch), len(batch) - sum(1 for t in batch if t in missing),
                    len(batch), len(batch_rows))

    total_target = len(requested) + len(skipped_blocked)
    coverage_pct = round(100.0 * len(fetched) / total_target, 2) if total_target else 0.0
    # Blocked tickers count against coverage (they are genuinely absent this run).
    degraded = coverage_pct < 90.0 or bool(skipped_blocked)

    summary = {
        "requested": len(requested),
        "blocked": len(skipped_blocked),
        "target": total_target,
        "fetched": len(fetched),
        "missing": len(missing) + len(skipped_blocked),
        "rows_written": rows_written,
        "coverage_pct": coverage_pct,
        "degraded": degraded,
        "missing_tickers": sorted(missing),
        "blocked_tickers": sorted(skipped_blocked),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    logger.info("[stable_bars] coverage %.1f%% (%d/%d) degraded=%s missing=%d blocked=%d",
                coverage_pct, len(fetched), total_target, degraded,
                len(missing), len(skipped_blocked))
    return summary
