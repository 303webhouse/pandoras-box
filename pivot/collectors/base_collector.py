"""
Shared collector utilities for Pivot.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
import yfinance as yf

from .config import (
    PANDORA_API_URL,
    PIVOT_API_KEY,
    HTTP_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
)

logger = logging.getLogger(__name__)


def score_to_bias(score: float) -> str:
    if score >= 0.60:
        return "TORO_MAJOR"
    if score >= 0.20:
        return "TORO_MINOR"
    if score >= -0.19:
        return "NEUTRAL"
    if score >= -0.59:
        return "URSA_MINOR"
    return "URSA_MAJOR"


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if PIVOT_API_KEY:
        headers["Authorization"] = f"Bearer {PIVOT_API_KEY}"
    return headers


def _api_url(path: str) -> str:
    if not PANDORA_API_URL:
        raise RuntimeError("PANDORA_API_URL is not configured")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{PANDORA_API_URL}{path}"


async def post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(_api_url(path), json=payload, headers=_headers())
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
                return response.json()
        except Exception as exc:
            last_error = exc
            logger.warning(f"POST {path} failed (attempt {attempt}/{RETRY_ATTEMPTS}): {exc}")
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError(f"POST {path} failed after retries: {last_error}")


async def get_json(path: str) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.get(_api_url(path), headers=_headers())
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
                return response.json()
        except Exception as exc:
            last_error = exc
            logger.warning(f"GET {path} failed (attempt {attempt}/{RETRY_ATTEMPTS}): {exc}")
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError(f"GET {path} failed after retries: {last_error}")


async def post_factor(
    factor_name: str,
    score: float,
    bias: Optional[str] = None,
    detail: str = "",
    data: Optional[Dict[str, Any]] = None,
    scoring_details: Optional[Dict[str, Any]] = None,
    collected_at: Optional[datetime] = None,
    stale_after_hours: Optional[int] = None,
    source: str = "pivot",
) -> Dict[str, Any]:
    payload = {
        "score": float(score),
        "bias": bias or score_to_bias(score),
        "detail": detail,
        "data": data or {},
        "scoring_details": scoring_details or {},
        "collected_at": (collected_at or datetime.utcnow()).isoformat(),
        "stale_after_hours": stale_after_hours,
        "source": source,
    }
    return await post_json(f"/bias/factors/{factor_name}", payload)


async def post_health(status: str = "ok", factors_collected: Optional[int] = None) -> Dict[str, Any]:
    payload = {
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "factors_collected": factors_collected,
    }
    return await post_json("/bias/health", payload)


async def post_sector_strength(sector_strength: Dict[str, Any]) -> Dict[str, Any]:
    return await post_json("/watchlist/sector-strength", {"sector_strength": sector_strength})


async def post_pivot_alert(payload: Dict[str, Any]) -> Dict[str, Any]:
    return await post_json("/alerts/pivot", payload)


async def get_price_history(ticker: str, days: int = 30):
    def _download():
        data = yf.download(ticker, period=f"{days}d", progress=False)
        if data is not None and not data.empty:
            data.columns = [str(c).lower().replace(" ", "_") for c in data.columns]
        return data

    return await asyncio.to_thread(_download)


async def get_latest_price(ticker: str) -> Optional[float]:
    data = await get_price_history(ticker, days=5)
    if data is None or data.empty or "close" not in data.columns:
        return None
    return float(data["close"].iloc[-1])
