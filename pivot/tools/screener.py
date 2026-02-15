"""
Quick multi-ticker scan for watchlist snapshots.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import yfinance as yf

from tools.helpers import _now_iso
from tools import YF_LOCK

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST = ["SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "USO", "^VIX"]


async def scan_watchlist(tickers: Optional[list[str]] = None) -> dict:
    """
    Quick multi-ticker scan returning price, change, and volume for each ticker.

    Args:
        tickers: List of ticker symbols to scan. Defaults to DEFAULT_WATCHLIST.

    Returns:
        Dict with results list and market_breadth summary.
    """
    if not tickers:
        tickers = DEFAULT_WATCHLIST

    try:
        return await asyncio.to_thread(_scan_watchlist_sync, tickers)
    except Exception as exc:
        logger.error(f"scan_watchlist() failed: {exc}", exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "timestamp": _now_iso(),
        }


def _scan_watchlist_sync(tickers: list[str]) -> dict:
    """Synchronous implementation of watchlist scan."""
    try:
        # Batch download is faster than individual Ticker calls
        tickers_str = " ".join(tickers)
        raw = yf.download(
            tickers_str,
            period="5d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        if raw is None or raw.empty:
            return {
                "status": "error",
                "error": "No data returned from yfinance batch download",
                "timestamp": _now_iso(),
            }

        results = []
        for ticker in tickers:
            try:
                result = _extract_ticker_data(raw, ticker, tickers)
                if result:
                    results.append(result)
            except Exception as exc:
                logger.warning(f"scan_watchlist: failed to process {ticker}: {exc}")
                results.append({
                    "ticker": ticker.upper(),
                    "price": None,
                    "change_pct": None,
                    "volume_ratio": None,
                    "error": str(exc),
                })

        # Market breadth
        advancers = sum(1 for r in results if r.get("change_pct") is not None and r["change_pct"] > 0)
        decliners = sum(1 for r in results if r.get("change_pct") is not None and r["change_pct"] < 0)
        unchanged = sum(1 for r in results if r.get("change_pct") is not None and r["change_pct"] == 0)

        return {
            "status": "ok",
            "results": results,
            "market_breadth": {
                "advancers": advancers,
                "decliners": decliners,
                "unchanged": unchanged,
            },
            "timestamp": _now_iso(),
        }
    except Exception as exc:
        logger.error(f"_scan_watchlist_sync() error: {exc}", exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "timestamp": _now_iso(),
        }


def _extract_ticker_data(raw, ticker: str, all_tickers: list[str]) -> Optional[dict]:
    """Extract data for a single ticker from the batch download result."""
    import pandas as pd

    ticker_upper = ticker.upper()

    # Handle single vs multi ticker column structure
    if len(all_tickers) == 1:
        # Single ticker: columns are just field names
        df = raw
    else:
        # Multi ticker: try to slice by ticker
        try:
            if hasattr(raw.columns, "levels"):
                # MultiIndex columns: (field, ticker)
                # Try both orderings
                try:
                    df = raw.xs(ticker_upper, axis=1, level=1)
                except KeyError:
                    try:
                        df = raw.xs(ticker_upper, axis=1, level=0)
                    except KeyError:
                        logger.debug(f"Ticker {ticker_upper} not found in multiindex columns")
                        return None
            elif ticker_upper in raw.columns:
                df = raw[ticker_upper]
            else:
                return None
        except Exception as exc:
            logger.debug(f"Column extraction failed for {ticker_upper}: {exc}")
            return None

    if df is None or (hasattr(df, "empty") and df.empty):
        return None

    # Normalize column names to lowercase
    if hasattr(df, "columns"):
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    else:
        return None

    # Need at least 2 rows for change calculation
    if len(df) < 2:
        price = _safe_float(df["close"].iloc[-1]) if "close" in df.columns else None
        return {
            "ticker": ticker_upper,
            "price": price,
            "change_pct": None,
            "volume_ratio": None,
        }

    # Latest and previous day
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    close_col = "close" if "close" in df.columns else None
    if close_col is None:
        return None

    price = _safe_float(latest[close_col])
    prev_price = _safe_float(prev[close_col])

    change_pct: Optional[float] = None
    if price is not None and prev_price is not None and prev_price != 0:
        change_pct = round(((price - prev_price) / prev_price) * 100, 2)

    # Volume ratio: today / rolling avg
    volume_ratio: Optional[float] = None
    if "volume" in df.columns:
        today_vol = _safe_float(latest["volume"])
        avg_vol_vals = df["volume"].dropna()
        if len(avg_vol_vals) > 1 and today_vol is not None:
            avg_vol = float(avg_vol_vals[:-1].mean())
            if avg_vol > 0:
                volume_ratio = round(today_vol / avg_vol, 2)

    return {
        "ticker": ticker_upper,
        "price": price,
        "change_pct": change_pct,
        "volume_ratio": volume_ratio,
    }


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        import math
        f = float(value)
        return None if not math.isfinite(f) else f
    except (TypeError, ValueError):
        return None
