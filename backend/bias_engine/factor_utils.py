"""
Shared utilities for composite bias factor scoring.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
import yfinance as yf

from database.redis_client import get_redis_client
from bias_engine.composite import FactorReading

logger = logging.getLogger(__name__)

PRICE_CACHE_TTL = 900  # 15 minutes


def score_to_signal(score: float) -> str:
    """Convert numeric score to human-readable signal name."""
    if score >= 0.6:
        return "TORO_MAJOR"
    if score >= 0.2:
        return "TORO_MINOR"
    if score >= -0.19:
        return "NEUTRAL"
    if score >= -0.59:
        return "URSA_MINOR"
    return "URSA_MAJOR"


def _normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]
    return df


async def get_price_history(ticker: str, days: int = 30) -> pd.DataFrame:
    """
    Fetch price history from yfinance with Redis caching.
    Uses a key per ticker+days to avoid mismatched windows.
    """
    cache_key = f"prices:{ticker}:{days}"
    try:
        client = await get_redis_client()
        if client:
            cached = await client.get(cache_key)
            if cached:
                payload = json.loads(cached)
                df = pd.read_json(payload, orient="split")
                return _normalize_history(df)
    except Exception as exc:
        logger.warning(f"Price cache read failed for {ticker}: {exc}")

    data = yf.download(ticker, period=f"{days}d", progress=False)
    data = _normalize_history(data)

    try:
        client = await get_redis_client()
        if client and data is not None and not data.empty:
            payload = data.to_json(orient="split")
            await client.setex(cache_key, PRICE_CACHE_TTL, json.dumps(payload))
    except Exception as exc:
        logger.warning(f"Price cache write failed for {ticker}: {exc}")

    return data


async def get_latest_price(ticker: str) -> Optional[float]:
    """Fetch latest close price for a ticker."""
    data = await get_price_history(ticker, days=5)
    if data is None or data.empty or "close" not in data.columns:
        return None
    return float(data["close"].iloc[-1])


def neutral_reading(
    factor_id: str,
    detail: str,
    source: str = "system",
    raw_data: Optional[Dict[str, Any]] = None,
) -> FactorReading:
    return FactorReading(
        factor_id=factor_id,
        score=0.0,
        signal=score_to_signal(0.0),
        detail=detail,
        timestamp=datetime.utcnow(),
        source=source,
        raw_data=raw_data or {},
    )
