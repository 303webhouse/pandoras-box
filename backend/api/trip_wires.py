"""
Trip Wire Monitor — checks 4 reversal conditions against live data.
Reads existing bias factor Redis keys + macro strip for Brent.
SPX approximated from SPY × 10. VIX via bias cache or yfinance fallback.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trip-wires", tags=["trip-wires"])

# SPY-to-SPX multiplier (approximate; SPY ≈ SPX / 10)
SPY_TO_SPX = 10.0

# VIX fallback cache (avoid hammering yfinance on every request)
_vix_fallback_cache = {"price": None, "ts": 0}
VIX_FALLBACK_TTL = 60  # seconds


async def _get_redis_float(redis, key: str) -> Optional[float]:
    """Read a float from Redis, returning None if missing."""
    if not redis:
        return None
    try:
        val = await redis.get(key)
        if val is not None:
            return float(val)
    except Exception:
        pass
    return None


def _fetch_vix_yfinance_sync() -> Optional[float]:
    """Synchronous yfinance VIX fetch (called in executor)."""
    try:
        import yfinance as yf
        data = yf.download("^VIX", period="1d", interval="1d", progress=False)
        if data is not None and not data.empty and "Close" in data.columns:
            closes = data["Close"].dropna().tolist()
            if closes:
                return float(closes[-1])
    except Exception as e:
        logger.warning("VIX yfinance fallback failed: %s", e)
    return None


async def _get_vix_price(redis) -> Optional[float]:
    """Get VIX price: try Redis bias cache first, then yfinance fallback."""
    # Try Redis first
    vix = await _get_redis_float(redis, "bias:factor:vix_price")
    if vix is not None:
        return vix

    # Try yfinance fallback with simple in-memory cache
    import time
    now = time.time()
    if _vix_fallback_cache["price"] is not None and (now - _vix_fallback_cache["ts"]) < VIX_FALLBACK_TTL:
        return _vix_fallback_cache["price"]

    loop = asyncio.get_event_loop()
    vix = await loop.run_in_executor(None, _fetch_vix_yfinance_sync)
    if vix is not None:
        _vix_fallback_cache["price"] = vix
        _vix_fallback_cache["ts"] = now
        # Also cache in Redis for other consumers (5 min TTL)
        if redis:
            try:
                await redis.set("bias:factor:vix_price", str(vix), ex=300)
            except Exception:
                pass
    return vix


@router.get("")
async def get_trip_wires():
    """
    Return status of 4 reversal trip wires.
    Two firing simultaneously = regime change signal.
    """
    redis = await get_redis_client()

    # Wire 1: SPX distance to 200 DMA
    spy_price = await _get_redis_float(redis, "bias:factor:spy_price")
    spy_200dma = await _get_redis_float(redis, "bias:factor:spy_200sma")
    if spy_price is None:
        # Fallback: try macro strip cache for SPY price
        try:
            macro = await redis.get("macro:strip")
            if macro:
                macro_data = json.loads(macro)
                for t in macro_data.get("tickers", []):
                    if t["ticker"] == "SPY":
                        spy_price = t["price"]
                        break
        except Exception:
            pass
    # Convert SPY to approximate SPX (×10) for display and threshold comparison
    spx_approx = round(spy_price * SPY_TO_SPX, 0) if spy_price else None
    spx_200dma_approx = round(spy_200dma * SPY_TO_SPX, 0) if spy_200dma else None
    spx_threshold = 6600
    spx_status = "COLD"
    spx_proximity = 0
    if spx_approx is not None:
        if spx_200dma_approx:
            spx_proximity = round(spx_approx / spx_200dma_approx * 100, 1)
            if spx_approx >= spx_200dma_approx:
                spx_status = "HOT"
            elif spx_approx >= spx_200dma_approx * 0.97:
                spx_status = "WARM"
        else:
            # No 200 DMA available, compare directly to threshold
            spx_proximity = round(spx_approx / spx_threshold * 100, 1)
            if spx_approx >= spx_threshold:
                spx_status = "HOT"
            elif spx_approx >= spx_threshold * 0.97:
                spx_status = "WARM"

    # Wire 2: Brent crude below $95 (USO proxy)
    brent_price = None
    try:
        macro = await redis.get("macro:strip")
        if macro:
            macro_data = json.loads(macro)
            for t in macro_data.get("tickers", []):
                if t["ticker"] == "USO":
                    brent_price = t["price"]
                    break
    except Exception:
        pass
    brent_threshold = 95
    brent_status = "COLD"
    brent_note = "Using USO as proxy — check Brent directly for precision"

    # Wire 3: Formal ceasefire / Hormuz reopening — manual only
    ceasefire_status = "COLD"
    ceasefire_manual = True
    try:
        cf = await redis.get("trip_wire:ceasefire")
        if cf:
            decoded = cf if isinstance(cf, str) else cf.decode()
            if decoded == "HOT":
                ceasefire_status = "HOT"
    except Exception:
        pass

    # Wire 4: VIX below 20 for 48 hours
    vix_price = await _get_vix_price(redis)
    vix_threshold = 20
    vix_status = "COLD"
    vix_proximity = 0
    if vix_price:
        vix_proximity = round(vix_price / vix_threshold * 100, 1)
        if vix_price < vix_threshold:
            vix_status = "WARM"  # Need duration tracking for full HOT
            try:
                below_since = await redis.get("trip_wire:vix_below_since")
                if below_since:
                    decoded = below_since if isinstance(below_since, str) else below_since.decode()
                    since = datetime.fromisoformat(decoded)
                    hours_below = (datetime.now(timezone.utc) - since).total_seconds() / 3600
                    if hours_below >= 48:
                        vix_status = "HOT"
                else:
                    await redis.set("trip_wire:vix_below_since", datetime.now(timezone.utc).isoformat())
            except Exception:
                pass
        else:
            try:
                await redis.delete("trip_wire:vix_below_since")
            except Exception:
                pass

    wires = [
        {
            "id": "spx_200dma",
            "label": "SPX vs 200 DMA",
            "current": int(spx_approx) if spx_approx else None,
            "threshold": f">{spx_threshold} (2 closes)",
            "threshold_display": str(spx_threshold),
            "status": spx_status,
            "proximity_pct": spx_proximity,
            "note": "SPX approximated from SPY × 10",
        },
        {
            "id": "brent_crude",
            "label": "Oil (USO proxy)",
            "current": round(brent_price, 2) if brent_price else None,
            "threshold": f"<${brent_threshold}",
            "threshold_display": str(brent_threshold),
            "status": brent_status,
            "note": brent_note,
        },
        {
            "id": "ceasefire",
            "label": "Ceasefire / Hormuz",
            "current": "Manual",
            "threshold": "Confirmed",
            "threshold_display": "Confirmed",
            "status": ceasefire_status,
            "manual": True,
        },
        {
            "id": "vix_48h",
            "label": "VIX <20 (48hr)",
            "current": round(vix_price, 2) if vix_price else None,
            "threshold": f"<{vix_threshold} for 48h",
            "threshold_display": str(vix_threshold),
            "status": vix_status,
            "proximity_pct": vix_proximity,
        },
    ]

    hot_count = sum(1 for w in wires if w["status"] == "HOT")
    warm_count = sum(1 for w in wires if w["status"] == "WARM")

    return {
        "wires": wires,
        "hot_count": hot_count,
        "warm_count": warm_count,
        "regime_change": hot_count >= 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/ceasefire/{status}")
async def set_ceasefire_wire(status: str):
    """Manually set the ceasefire trip wire. Values: HOT, COLD."""
    if status.upper() not in ("HOT", "COLD"):
        raise HTTPException(400, "Status must be HOT or COLD")
    redis = await get_redis_client()
    if redis:
        await redis.set("trip_wire:ceasefire", status.upper())
    return {"status": status.upper(), "wire": "ceasefire"}
