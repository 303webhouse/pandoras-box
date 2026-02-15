"""
Shared utilities for composite bias factor scoring.
"""

from __future__ import annotations

from io import StringIO
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
import yfinance as yf

from database.redis_client import get_redis_client
from bias_engine.composite import FactorReading

logger = logging.getLogger(__name__)

PRICE_CACHE_TTL = 900  # 15 minutes

_TUPLE_COLUMN_RE = re.compile(r"^\('([^']+)'\s*,\s*_?'[^']*'\)$")


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

    def _canonical_col_name(raw: Any) -> str:
        text = str(raw).lower().replace(" ", "_")
        # Handle legacy flattened tuple-style names, e.g. "('close',_'spy')".
        match = _TUPLE_COLUMN_RE.match(text)
        if match:
            return match.group(1)
        return text

    # yfinance can return MultiIndex columns even for a single ticker.
    if isinstance(df.columns, pd.MultiIndex):
        # Keep the field name level (open/high/low/close/volume) and drop ticker level.
        df.columns = [_canonical_col_name(col[0]) for col in df.columns]
    else:
        df.columns = [_canonical_col_name(col) for col in df.columns]

    if "close" not in df.columns and "adj_close" in df.columns:
        # Some responses only expose adjusted close; downstream factors expect "close".
        df["close"] = df["adj_close"]

    # Guard against accidental duplicate column names after MultiIndex flattening.
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def _decode_cached_history(cached: Any) -> pd.DataFrame:
    """
    Decode cached payloads written by older and newer cache formats.

    Supports:
    - raw orient=split JSON string
    - double-encoded JSON string (json.dumps(payload))
    - already-decoded dict payload
    """
    payload: Any = cached

    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")

    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise ValueError("empty payload")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text

    if isinstance(payload, dict):
        payload = json.dumps(payload)

    if not isinstance(payload, str):
        raise TypeError(f"unsupported cache payload type: {type(payload).__name__}")

    return pd.read_json(StringIO(payload), orient="split")


async def get_price_history(ticker: str, days: int = 30) -> pd.DataFrame:
    """
    Fetch price history from yfinance with Redis caching.
    Uses a key per ticker+days to avoid mismatched windows.
    """
    symbol = str(ticker).strip().upper()
    cache_key = f"prices:{symbol}:{days}"
    try:
        client = await get_redis_client()
        if client:
            cached = await client.get(cache_key)
            if cached:
                df = _decode_cached_history(cached)
                return _normalize_history(df)
    except Exception as exc:
        logger.warning(f"Price cache read failed for {symbol}: {type(exc).__name__}")
        # Remove poisoned cache entries so they don't spam on every run.
        try:
            client = await get_redis_client()
            if client:
                await client.delete(cache_key)
        except Exception:
            pass

    try:
        data = yf.download(symbol, period=f"{days}d", progress=False, auto_adjust=False, multi_level_index=False)
    except TypeError:
        # Backward compatibility for older yfinance versions without multi_level_index.
        data = yf.download(symbol, period=f"{days}d", progress=False, auto_adjust=False)
    data = _normalize_history(data)

    try:
        client = await get_redis_client()
        if client and data is not None and not data.empty:
            payload = data.to_json(orient="split")
            # Store raw payload (not double-encoded) to avoid decode ambiguity.
            await client.setex(cache_key, PRICE_CACHE_TTL, payload)
    except Exception as exc:
        logger.warning(f"Price cache write failed for {symbol}: {type(exc).__name__}")

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
