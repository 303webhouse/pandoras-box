"""
Pythia Market Profile Events — stores VAL/VAH cross alerts from TradingView.

Receives alerts when price crosses value area boundaries, stores in
pythia_events table for scoring cross-reference (P4B) and committee context.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client

logger = logging.getLogger("pythia_events")
router = APIRouter(tags=["pythia"])


@router.post("/webhook/pythia")
async def pythia_webhook(request: Request = None, payload: dict = None):
    """
    Receive Pythia market profile alerts from TradingView.
    Expected payload fields: ticker, alert_type (pythia_val_cross_below,
    pythia_vah_cross_above, 80pct_rule), price, vah, val, poc, direction.
    Can be called directly with a payload dict (from TV webhook router).
    """
    if payload is None:
        payload = await request.json()
    ticker = (payload.get("ticker") or "").upper()
    alert_type = payload.get("alert_type") or payload.get("event") or payload.get("signal_type") or "unknown"
    price = payload.get("price") or payload.get("close")
    direction = payload.get("direction") or ""
    vah = payload.get("vah")
    val = payload.get("val")
    poc = payload.get("poc")

    if not ticker:
        return {"error": "missing ticker"}

    logger.info("PYTHIA event: %s %s @ %s (VAH=%s POC=%s VAL=%s)",
                ticker, alert_type, price, vah, poc, val)

    # Store in database
    event_id = None
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO pythia_events
                    (ticker, alert_type, price, direction, vah, val, poc, raw_payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
                ticker, alert_type,
                float(price) if price else None,
                direction,
                float(vah) if vah else None,
                float(val) if val else None,
                float(poc) if poc else None,
                json.dumps(payload),
            )
            event_id = row["id"] if row else None
    except Exception as e:
        logger.error("Failed to store Pythia event: %s", e)

    # Also cache latest levels in Redis for quick scoring lookups
    redis = await get_redis_client()
    if redis and vah and val and poc:
        try:
            level_data = {
                "vah": float(vah), "val": float(val), "poc": float(poc),
                "price": float(price) if price else None,
                "alert_type": alert_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.set(f"pythia:{ticker}", json.dumps(level_data), ex=86400)
        except Exception:
            pass

    return {
        "status": "ok",
        "event_id": event_id,
        "ticker": ticker,
        "alert_type": alert_type,
    }


async def get_pythia_profile_position(ticker: str, entry_price: float, direction: str) -> dict:
    """
    Check where entry_price sits relative to the latest Pythia value area.
    Returns profile_position scoring data for the scoring engine (P4B).
    """
    redis = await get_redis_client()
    if not redis:
        return {"profile_bonus": 0}

    try:
        raw = await redis.get(f"pythia:{ticker}")
        if not raw:
            # Fallback: check mp_levels key
            raw = await redis.get(f"mp_levels:{ticker}")
        if not raw:
            return {"profile_bonus": 0}

        data = json.loads(raw)
        vah = data.get("vah")
        val = data.get("val")
        poc = data.get("poc")
        if not vah or not val or not poc:
            return {"profile_bonus": 0}

        vah, val, poc = float(vah), float(val), float(poc)
        is_long = direction.upper() in ("LONG", "BUY", "BULLISH")

        if is_long:
            if entry_price <= val:
                return {"profile_bonus": 8, "zone": "below_VAL", "vah": vah, "val": val, "poc": poc}
            elif entry_price <= poc:
                return {"profile_bonus": 3, "zone": "VAL_to_POC", "vah": vah, "val": val, "poc": poc}
            elif entry_price <= vah:
                return {"profile_bonus": 0, "zone": "POC_to_VAH", "vah": vah, "val": val, "poc": poc}
            else:
                return {"profile_bonus": -10, "zone": "above_VAH", "vah": vah, "val": val, "poc": poc}
        else:
            if entry_price >= vah:
                return {"profile_bonus": 8, "zone": "above_VAH", "vah": vah, "val": val, "poc": poc}
            elif entry_price >= poc:
                return {"profile_bonus": 3, "zone": "POC_to_VAH", "vah": vah, "val": val, "poc": poc}
            elif entry_price >= val:
                return {"profile_bonus": 0, "zone": "VAL_to_POC", "vah": vah, "val": val, "poc": poc}
            else:
                return {"profile_bonus": -10, "zone": "below_VAL", "vah": vah, "val": val, "poc": poc}

    except Exception as e:
        logger.debug("Pythia profile lookup failed for %s: %s", ticker, e)
        return {"profile_bonus": 0}
