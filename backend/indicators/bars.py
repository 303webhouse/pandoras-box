"""Daily OHLC fetch for indicators (sub-brief 3 Chunk 3) — reusable.

Wraps UW `get_ohlc` and normalizes to chronological highs/lows/closes arrays
(oldest→newest). UW-primary; no yfinance. The PYTHAGORAS feed Phase 0 reuses
this for its own bar math, so it is ticker-agnostic and indicator-agnostic.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


async def fetch_daily_ohlc(
    ticker: str, lookback_sessions: int = 60
) -> Optional[Dict[str, List[float]]]:
    """Return {"highs": [...], "lows": [...], "closes": [...]} chronological.

    Requests extra calendar days to cover weekends/holidays. Returns None on
    fetch failure or fewer than 2 usable bars (never fabricates).
    """
    try:
        from integrations.uw_api import get_ohlc

        # ~1.6x calendar days per session + slack to clear weekends/holidays
        lookback_days = int(lookback_sessions * 1.6) + 10
        bars = await get_ohlc(ticker, candle_size="1d", lookback_days=lookback_days, caller="ohlc_bars")
    except Exception as exc:
        logger.warning("fetch_daily_ohlc(%s) failed: %s", ticker, exc)
        return None

    if not bars or not isinstance(bars, list):
        return None

    # Ensure chronological order (UW carries start_time per bar)
    try:
        bars = sorted(bars, key=lambda b: b.get("start_time") or "")
    except Exception:
        pass

    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    for b in bars:
        # UW /ohlc/1d returns SESSION-SPLIT rows per date (market_time pr/r/po).
        # Keep only the REGULAR-session ('r') bar per date — otherwise ADX(14)
        # is computed on premarket/postmarket partials. Mirrors the existing
        # filter in chart_indicators.py and uw_api._get_bars_via_uw.
        if (b.get("market_time") or "").lower() != "r":
            continue
        try:
            h = float(b["high"])
            l = float(b["low"])
            c = float(b["close"])
        except (KeyError, TypeError, ValueError):
            continue
        highs.append(h)
        lows.append(l)
        closes.append(c)

    if len(closes) < 2:
        return None
    return {"highs": highs, "lows": lows, "closes": closes}
