"""
Calculate IV rank and IV percentile for a ticker using realized volatility as proxy.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import yfinance as yf

from tools.helpers import _now_iso, _error_response
from tools import YF_LOCK

logger = logging.getLogger(__name__)


async def get_iv_rank(ticker: str, period_days: int = 252) -> dict:
    """
    Calculate IV rank and percentile for a ticker.

    Uses realized volatility as a proxy for IV (MVP approach).
    Period defaults to 252 trading days (~1 year).
    """
    try:
        return await asyncio.to_thread(_get_iv_rank_sync, ticker, period_days)
    except Exception as exc:
        logger.error(f"get_iv_rank({ticker}) failed: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


def _get_iv_rank_sync(ticker: str, period_days: int) -> dict:
    """Synchronous implementation of IV rank calculation."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")

        if hist is None or hist.empty or "Close" not in hist.columns:
            return _error_response(ticker, "No historical price data available")

        returns = hist["Close"].pct_change().dropna()
        if len(returns) < 31:
            return _error_response(ticker, "Insufficient historical data for IV rank calculation")

        # Rolling 30-day realized vol, annualized
        rolling_vol = returns.rolling(30).std() * (252 ** 0.5)
        rolling_vol = rolling_vol.dropna()

        if rolling_vol.empty:
            return _error_response(ticker, "Could not compute rolling volatility")

        current_rv = float(rolling_vol.iloc[-1])
        iv_high = float(rolling_vol.max())
        iv_low = float(rolling_vol.min())

        # IV Rank: where current IV sits in the 52-week range
        if iv_high == iv_low:
            iv_rank = 50.0
        else:
            iv_rank = (current_rv - iv_low) / (iv_high - iv_low) * 100

        # IV Percentile: % of days IV was lower than current
        iv_percentile = float((rolling_vol < current_rv).sum() / len(rolling_vol) * 100)

        # Regime classification
        if iv_rank > 70:
            regime = "high"
            guidance = (
                f"IV rank {iv_rank:.0f} — elevated. "
                "Lean toward selling premium (credit spreads, iron condors)."
            )
        elif iv_rank > 50:
            regime = "elevated"
            guidance = (
                f"IV rank {iv_rank:.0f} — above average. Selling premium has edge."
            )
        elif iv_rank > 30:
            regime = "normal"
            guidance = (
                f"IV rank {iv_rank:.0f} — neutral zone. "
                "Bias can dictate strategy (buy or sell premium)."
            )
        else:
            regime = "low"
            guidance = (
                f"IV rank {iv_rank:.0f} — depressed. "
                "Lean toward buying premium (debit spreads, long options)."
            )

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "current_iv": round(current_rv, 4),
            "iv_rank": round(iv_rank, 1),
            "iv_percentile": round(iv_percentile, 1),
            "iv_high_52w": round(iv_high, 4),
            "iv_low_52w": round(iv_low, 4),
            "regime": regime,
            "playbook_guidance": guidance,
            "note": "Using realized volatility as IV proxy",
            "timestamp": _now_iso(),
        }
    except Exception as exc:
        logger.error(f"_get_iv_rank_sync({ticker}) error: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))
