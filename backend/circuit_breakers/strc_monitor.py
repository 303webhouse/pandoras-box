"""
STRC Circuit Breaker Monitor

Polygon-first price fetcher for STRC (Sarcos Technology and Robotics Corp).
Tracks price relative to $1.00 par value. Fires a one-time Discord alert
when price crosses below par. Caches in Redis with 5-min TTL, detects
staleness at 15 min.

Used by GET /api/crypto/circuit-breakers.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

PAR_VALUE = 1.00
CACHE_KEY = "circuit_breaker:strc"
CACHE_TTL = 300  # 5 minutes
STALE_THRESHOLD = 900  # 15 minutes
ALERT_SENT_KEY = "circuit_breaker:strc:alert_sent"

DISCORD_WEBHOOK_CB = os.getenv("DISCORD_WEBHOOK_CB") or ""

# In-memory cache to avoid Redis on every call
_mem_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}
_MEM_TTL = 60  # 1 minute in-memory


async def get_strc_price() -> Optional[Dict[str, Any]]:
    """
    Fetch STRC price. Priority: Polygon snapshot > Polygon prev close > yfinance.
    Returns dict with: price, source, fetched_at  or None on total failure.
    """
    # Try Polygon snapshot first
    try:
        from integrations.polygon_equities import get_snapshot
        snap = await get_snapshot("STRC")
        if snap:
            # Snapshot has day.c (today's close so far) or lastTrade.p
            price = None
            last_trade = snap.get("lastTrade") or {}
            day_data = snap.get("day") or {}
            price = last_trade.get("p") or day_data.get("c")
            if price is not None:
                return {
                    "price": round(float(price), 4),
                    "source": "polygon_snapshot",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
    except Exception as e:
        logger.warning("STRC Polygon snapshot failed: %s", e)

    # Try Polygon previous close
    try:
        from integrations.polygon_equities import get_previous_close
        prev = await get_previous_close("STRC")
        if prev and prev.get("c"):
            return {
                "price": round(float(prev["c"]), 4),
                "source": "polygon_prev_close",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        logger.warning("STRC Polygon prev close failed: %s", e)

    # yfinance fallback
    try:
        import asyncio
        import yfinance as yf

        def _fetch():
            data = yf.download("STRC", period="1d", interval="1d", progress=False)
            if data is not None and len(data) > 0 and "Close" in data.columns:
                closes = data["Close"].dropna().tolist()
                if closes:
                    return float(closes[-1])
            return None

        price = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        if price is not None:
            return {
                "price": round(price, 4),
                "source": "yfinance",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        logger.warning("STRC yfinance fallback failed: %s", e)

    return None


async def _send_par_alert(price: float) -> None:
    """Send one-time Discord alert when STRC crosses below par."""
    if not DISCORD_WEBHOOK_CB:
        logger.debug("DISCORD_WEBHOOK_CB not set -- skipping STRC alert")
        return

    payload = {
        "embeds": [{
            "title": "STRC Circuit Breaker -- Below Par",
            "description": (
                f"**STRC** is trading at **${price:.4f}**, below the "
                f"**${PAR_VALUE:.2f} par value**.\n\n"
                "Review Stater Swap crypto positions for potential forced liquidation risk."
            ),
            "color": 0xFF4444,  # Red
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Pandora's Box -- STRC Monitor"},
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(DISCORD_WEBHOOK_CB, json=payload)
            if resp.status_code in (200, 204):
                logger.info("STRC par alert sent (price=%.4f)", price)
            else:
                logger.warning("STRC Discord alert failed: HTTP %s", resp.status_code)
    except Exception as e:
        logger.error("STRC Discord alert error: %s", e)


async def check_strc_status() -> Dict[str, Any]:
    """
    Main entry point. Returns STRC circuit breaker status.

    Response shape:
    {
        "ticker": "STRC",
        "price": 0.85,
        "par_value": 1.00,
        "status": "BELOW_PAR" | "ABOVE_PAR" | "STALE" | "UNAVAILABLE",
        "severity": "red" | "amber" | "green" | "gray",
        "message": "...",
        "source": "polygon_snapshot",
        "fetched_at": "2026-03-17T...",
        "cached": true/false,
        "stale": true/false,
    }
    """
    now = time.time()

    # 1. Check in-memory cache
    if _mem_cache["data"] and (now - _mem_cache["timestamp"]) < _MEM_TTL:
        result = _mem_cache["data"].copy()
        result["cached"] = True
        return result

    # 2. Check Redis cache
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            cached = await redis.get(CACHE_KEY)
            if cached:
                data = json.loads(cached)
                fetched_at = data.get("fetched_at", "")
                # Check staleness
                try:
                    fetch_time = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
                    age_seconds = (datetime.now(timezone.utc) - fetch_time).total_seconds()
                    if age_seconds < STALE_THRESHOLD:
                        _mem_cache["data"] = data
                        _mem_cache["timestamp"] = now
                        data["cached"] = True
                        return data
                    else:
                        # Stale but usable as fallback
                        pass
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Redis cache check failed: %s", e)
        redis = None

    # 3. Fetch fresh price
    price_data = await get_strc_price()

    if price_data is None:
        result = {
            "ticker": "STRC",
            "price": None,
            "par_value": PAR_VALUE,
            "status": "UNAVAILABLE",
            "severity": "gray",
            "message": "STRC price unavailable -- all sources failed",
            "source": None,
            "fetched_at": None,
            "cached": False,
            "stale": True,
        }
        _mem_cache["data"] = result
        _mem_cache["timestamp"] = now
        return result

    price = price_data["price"]
    below_par = price < PAR_VALUE
    pct_from_par = round((price / PAR_VALUE - 1) * 100, 2)

    if below_par:
        if price < PAR_VALUE * 0.90:
            severity = "red"
            status = "BELOW_PAR"
            message = f"STRC ${price:.4f} -- {abs(pct_from_par):.1f}% below par (CRITICAL)"
        else:
            severity = "amber"
            status = "BELOW_PAR"
            message = f"STRC ${price:.4f} -- {abs(pct_from_par):.1f}% below par"
    else:
        severity = "green"
        status = "ABOVE_PAR"
        message = f"STRC ${price:.4f} -- {pct_from_par:+.1f}% from par"

    result = {
        "ticker": "STRC",
        "price": price,
        "par_value": PAR_VALUE,
        "status": status,
        "severity": severity,
        "message": message,
        "source": price_data["source"],
        "fetched_at": price_data["fetched_at"],
        "cached": False,
        "stale": False,
    }

    # 4. Cache in Redis
    try:
        if redis:
            await redis.set(CACHE_KEY, json.dumps(result), ex=CACHE_TTL)
    except Exception as e:
        logger.debug("Redis cache write failed: %s", e)

    # 5. One-time Discord alert on par crossing
    if below_par:
        try:
            if redis:
                already_sent = await redis.get(ALERT_SENT_KEY)
                if not already_sent:
                    await _send_par_alert(price)
                    await redis.set(ALERT_SENT_KEY, "1", ex=86400)  # 24h cooldown
            else:
                # No Redis -- skip dedup, just send
                await _send_par_alert(price)
        except Exception as e:
            logger.warning("STRC alert check failed: %s", e)
    else:
        # Price recovered above par -- clear the alert flag
        try:
            if redis:
                await redis.delete(ALERT_SENT_KEY)
        except Exception:
            pass

    _mem_cache["data"] = result
    _mem_cache["timestamp"] = now
    return result
