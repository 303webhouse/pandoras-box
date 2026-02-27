"""
Advance/Decline breadth factor — NYSE A/D ratio via yfinance.
Fallback for TICK breadth when no TradingView webhook data is available.
Only posts if no fresh TICK reading exists from TradingView.
"""

from __future__ import annotations

import logging
from datetime import datetime

import yfinance as yf

from .base_collector import get_json, post_factor, _clamp

logger = logging.getLogger(__name__)


async def collect_and_post():
    # Check if TradingView TICK data already exists and is fresh
    try:
        tick_status = await get_json("/bias/tick")
        if tick_status and tick_status.get("status") in ("ok", "success"):
            tick_high = float(tick_status.get("tick_high", 0) or 0)
            tick_low = float(tick_status.get("tick_low", 0) or 0)
            if tick_high != 0 or tick_low != 0:
                logger.info("AD breadth: fresh TICK data present — skipping A/D proxy")
                return None
    except Exception:
        pass  # If we can't check, proceed with fallback

    # Fetch NYSE advance/decline data
    try:
        advn_df = yf.download("^ADVN", period="5d", interval="1d", progress=False)
        decln_df = yf.download("^DECLN", period="5d", interval="1d", progress=False)
    except Exception as exc:
        logger.warning(f"AD breadth: yfinance download failed: {exc}")
        return None

    if advn_df is None or advn_df.empty or decln_df is None or decln_df.empty:
        logger.warning("AD breadth: ^ADVN or ^DECLN returned empty data")
        return None

    # Get latest close values
    try:
        advn = float(advn_df["Close"].iloc[-1])
        decln = float(decln_df["Close"].iloc[-1])
    except Exception as exc:
        logger.warning(f"AD breadth: failed to extract close values: {exc}")
        return None

    if decln == 0:
        logger.warning("AD breadth: ^DECLN is zero — cannot compute ratio")
        return None

    ad_ratio = advn / decln

    if ad_ratio >= 2.0:
        score = 0.8
    elif ad_ratio >= 1.5:
        score = 0.4
    elif ad_ratio >= 0.5:
        score = 0.0
    elif ad_ratio >= 0.3:
        score = -0.4
    else:
        score = -0.8

    score = _clamp(score)

    detail = f"A/D proxy: ratio {ad_ratio:.2f} ({advn:.0f} adv / {decln:.0f} dec)"
    data = {
        "advancing": float(advn),
        "declining": float(decln),
        "ad_ratio": round(float(ad_ratio), 3),
        "proxy_for": "tick_breadth",
    }

    logger.info(f"AD breadth posting: score={score:+.2f}, {detail}")

    return await post_factor(
        "tick_breadth",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=4,
        source="yfinance_ad_proxy",
    )
