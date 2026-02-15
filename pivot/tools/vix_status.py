"""
Get comprehensive VIX data including term structure and regime classification.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import yfinance as yf

from tools.helpers import _now_iso

logger = logging.getLogger(__name__)


async def get_vix_status() -> dict:
    """
    Get VIX, VIX3M, term structure, regime classification, and DEFCON signal.
    """
    try:
        return await asyncio.to_thread(_get_vix_status_sync)
    except Exception as exc:
        logger.error(f"get_vix_status() failed: {exc}", exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "timestamp": _now_iso(),
        }


def _get_vix_status_sync() -> dict:
    """Synchronous implementation of VIX status fetch."""
    try:
        vix_ticker = yf.Ticker("^VIX")
        vix3m_ticker = yf.Ticker("^VIX3M")

        vix: Optional[float] = None
        vix_prev: Optional[float] = None
        vix3m: Optional[float] = None
        fifty_day_ma: Optional[float] = None

        # Fetch VIX
        try:
            vix_hist = vix_ticker.history(period="60d")
            if vix_hist is not None and not vix_hist.empty and "Close" in vix_hist.columns:
                vix = float(vix_hist["Close"].iloc[-1])
                if len(vix_hist) >= 2:
                    vix_prev = float(vix_hist["Close"].iloc[-2])
                if len(vix_hist) >= 50:
                    fifty_day_ma = float(vix_hist["Close"].tail(50).mean())
        except Exception as exc:
            logger.warning(f"VIX history fetch failed: {exc}")

        # Fetch VIX3M
        try:
            vix3m_hist = vix3m_ticker.history(period="5d")
            if vix3m_hist is not None and not vix3m_hist.empty and "Close" in vix3m_hist.columns:
                vix3m = float(vix3m_hist["Close"].iloc[-1])
        except Exception as exc:
            logger.warning(f"VIX3M history fetch failed: {exc}")

        if vix is None:
            return {
                "status": "error",
                "error": "VIX data unavailable",
                "timestamp": _now_iso(),
            }

        # Compute change fields
        vix_change: Optional[float] = None
        vix_change_pct: Optional[float] = None
        if vix_prev is not None:
            vix_change = round(vix - vix_prev, 3)
            vix_change_pct = round(((vix - vix_prev) / vix_prev) * 100, 2) if vix_prev != 0 else None

        # Term structure
        term_spread: Optional[float] = None
        term_structure: str = "unknown"
        if vix3m is not None:
            term_spread = round(vix - vix3m, 3)
            term_structure = "backwardation" if term_spread > 0 else "contango"

        # Regime classification
        if vix > 35:
            regime = "panic"
        elif vix > 28:
            regime = "fear"
        elif vix > 20:
            regime = "elevated"
        elif vix > 15:
            regime = "normal"
        else:
            regime = "low_vol"

        # DEFCON signal
        if vix > 35:
            defcon_signal = "red"
        elif vix > 28 or term_structure == "backwardation":
            defcon_signal = "orange"
        elif vix > 20:
            defcon_signal = "yellow"
        else:
            defcon_signal = None

        return {
            "status": "ok",
            "vix": round(vix, 2),
            "vix_change": vix_change,
            "vix_change_pct": vix_change_pct,
            "vix3m": round(vix3m, 2) if vix3m is not None else None,
            "term_structure": term_structure,
            "term_spread": term_spread,
            "regime": regime,
            "defcon_signal": defcon_signal,
            "fifty_day_ma": round(fifty_day_ma, 2) if fifty_day_ma is not None else None,
            "timestamp": _now_iso(),
        }
    except Exception as exc:
        logger.error(f"_get_vix_status_sync() error: {exc}", exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "timestamp": _now_iso(),
        }
