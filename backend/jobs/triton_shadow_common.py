"""Triton Step-0 shadow — shared helpers (poller B2 + grader B3).

ALL Triton bar-fetches go through get_ohlc(caller="triton_flow_shadow") + the 'r'
regular-session filter, tagged to the Triton BACKGROUND governor budget (clean
attribution; never rides ohlc_bars — so Triton can't die as collateral when the
over-quota ohlc_bars caller throttles). SHADOW-ONLY: no scoring/pipeline coupling.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger("triton_shadow")

TRITON_CALLER = "triton_flow_shadow"

# Mega/index premium bucket (flow_scanner INDEX_TICKERS — the $2M tier).
INDEX_TICKERS = {"SPY", "QQQ", "SMH", "NVDA", "AVGO", "MSFT", "GOOGL", "AMZN", "META"}
LARGE_MIN = 750_000  # flow_scanner LARGE_MIN_PREMIUM (TSLA-class)


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def classify_bucket(ticker: str, premium_usd: Optional[int]) -> str:
    """flow_scanner liquidity buckets: index (mega/ETF) / large / small_mid."""
    if (ticker or "").upper() in INDEX_TICKERS:
        return "index"
    if premium_usd is not None and premium_usd >= LARGE_MIN:
        return "large"
    return "small_mid"


def classify_direction(opt_type: Optional[str]) -> Optional[str]:
    """Ask-side is enforced by the request filter, so direction is the option
    side: call -> BULL, put -> BEAR."""
    if not opt_type:
        return None
    t = str(opt_type).lower()
    return "BULL" if t == "call" else "BEAR" if t == "put" else None


async def fetch_r_close_index(ticker: str, lookback_days: int) -> Dict[date, float]:
    """{date: regular-session close} via get_ohlc('1d', caller=TRITON_CALLER),
    filtered to market_time=='r' (the ONLY acceptable bar source — mirrors the
    bars.py facf023 fix, but keeps the dates grading/prior-return needs).
    Empty dict on any failure (never raises)."""
    from integrations.uw_api import get_ohlc
    try:
        bars = await get_ohlc(ticker.upper(), candle_size="1d",
                              lookback_days=lookback_days, caller=TRITON_CALLER)
    except Exception as exc:
        logger.warning("triton bars fetch failed %s: %s", ticker, type(exc).__name__)
        return {}
    out: Dict[date, float] = {}
    if not bars or not isinstance(bars, list):
        return out
    for b in bars:
        if (b.get("market_time") or "").lower() != "r":  # regular session only
            continue
        d = b.get("start_time") or b.get("date")
        c = _f(b.get("close"))
        if not d or c is None:
            continue
        try:
            dd = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        out[dd] = c
    return out


def nth_trading_day(anchor: date, n: int) -> date:
    """nth Mon-Fri strictly after anchor (mirrors a3; no holiday calendar in v0)."""
    day = anchor
    count = 0
    while count < n:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return day


def close_on_or_near(idx: Dict[date, float], target: date) -> Optional[float]:
    """Close at target, else ±1/±2 calendar-day tolerance (holiday/missing bar)."""
    if target in idx:
        return idx[target]
    for delta in (1, -1, 2, -2):
        v = idx.get(target + timedelta(days=delta))
        if v is not None:
            return v
    return None
