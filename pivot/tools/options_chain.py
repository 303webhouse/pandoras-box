"""
Get options chain data (expirations, calls, puts, Greeks) for any ticker.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

import yfinance as yf

from tools.helpers import _now_iso, _error_response
from tools import YF_LOCK

logger = logging.getLogger(__name__)


async def get_expirations(ticker: str) -> dict:
    """Get available options expiration dates for a ticker."""
    try:
        return await asyncio.to_thread(_get_expirations_sync, ticker)
    except Exception as exc:
        logger.error(f"get_expirations({ticker}) failed: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


def _get_expirations_sync(ticker: str) -> dict:
    """Synchronous implementation of expirations fetch."""
    try:
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            return _error_response(ticker, "No options data available for this ticker")

        expirations_list = list(expirations)
        nearest = expirations_list[0] if expirations_list else None

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "expirations": expirations_list,
            "nearest": nearest,
            "timestamp": _now_iso(),
        }
    except Exception as exc:
        logger.error(f"_get_expirations_sync({ticker}) error: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


async def get_options_chain(
    ticker: str,
    expiry: str,
    strike_range: Optional[float] = 0.15,
) -> dict:
    """
    Get the full options chain for a ticker at a specific expiration.

    Args:
        ticker: Stock/ETF ticker symbol.
        expiry: Expiration date string in 'YYYY-MM-DD' format.
        strike_range: Filter strikes to ±N% of current price. Pass None for all strikes.
    """
    try:
        return await asyncio.to_thread(_get_options_chain_sync, ticker, expiry, strike_range)
    except Exception as exc:
        logger.error(f"get_options_chain({ticker}, {expiry}) failed: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


def _get_options_chain_sync(
    ticker: str,
    expiry: str,
    strike_range: Optional[float],
) -> dict:
    """Synchronous implementation of options chain fetch."""
    try:
        t = yf.Ticker(ticker)

        # Get current underlying price
        underlying_price: Optional[float] = None
        try:
            fi = t.fast_info
            underlying_price = getattr(fi, "last_price", None)
        except Exception:
            pass
        if underlying_price is None:
            try:
                info = t.info
                underlying_price = (
                    info.get("currentPrice")
                    or info.get("regularMarketPrice")
                    or info.get("previousClose")
                )
            except Exception:
                pass

        # Fetch option chain
        chain = t.option_chain(expiry)

        # Calculate DTE
        try:
            expiry_dt = datetime.strptime(expiry, "%Y-%m-%d").date()
            today = date.today()
            dte = (expiry_dt - today).days
        except Exception:
            dte = None

        # Process calls and puts
        calls = _process_chain_df(chain.calls, underlying_price, strike_range)
        puts = _process_chain_df(chain.puts, underlying_price, strike_range)

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "expiry": expiry,
            "dte": dte,
            "underlying_price": _safe_float(underlying_price),
            "calls": calls,
            "puts": puts,
            "timestamp": _now_iso(),
        }
    except Exception as exc:
        logger.error(f"_get_options_chain_sync({ticker}, {expiry}) error: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


def _process_chain_df(df, underlying_price: Optional[float], strike_range: Optional[float]) -> list:
    """Convert a chain DataFrame to a list of dicts, optionally filtering by strike range."""
    if df is None or df.empty:
        return []

    # Filter by strike range if specified
    if strike_range is not None and underlying_price is not None and underlying_price > 0:
        low = underlying_price * (1 - strike_range)
        high = underlying_price * (1 + strike_range)
        if "strike" in df.columns:
            df = df[(df["strike"] >= low) & (df["strike"] <= high)]

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "strike": _safe_float(row.get("strike")),
            "bid": _safe_float(row.get("bid")),
            "ask": _safe_float(row.get("ask")),
            "last": _safe_float(row.get("lastPrice")),
            "volume": _safe_int(row.get("volume")),
            "open_interest": _safe_int(row.get("openInterest")),
            "implied_vol": _safe_float(row.get("impliedVolatility")),
            "delta": _safe_float(row.get("delta")),
            "gamma": _safe_float(row.get("gamma")),
            "theta": _safe_float(row.get("theta")),
            "vega": _safe_float(row.get("vega")),
            "in_the_money": bool(row.get("inTheMoney", False)),
        })
    return rows


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        import math
        f = float(value)
        return None if not math.isfinite(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
