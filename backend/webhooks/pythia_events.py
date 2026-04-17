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
    # Rich fields from Pythia v2 PineScript
    va_migration = payload.get("va_migration")
    poor_high = payload.get("poor_high", False)
    poor_low = payload.get("poor_low", False)
    volume_quality = payload.get("volume_quality")
    ib_high = payload.get("ib_high")
    ib_low = payload.get("ib_low")
    interpretation = payload.get("interpretation")

    if not ticker:
        return {"error": "missing ticker"}

    logger.info("PYTHIA event: %s %s @ %s (VAH=%s POC=%s VAL=%s mig=%s vol=%s)",
                ticker, alert_type, price, vah, poc, val, va_migration, volume_quality)

    # Store in database
    event_id = None
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO pythia_events
                    (ticker, alert_type, price, direction, vah, val, poc,
                     va_migration, poor_high, poor_low, volume_quality,
                     ib_high, ib_low, interpretation, raw_payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING id
            """,
                ticker, alert_type,
                float(price) if price else None,
                direction,
                float(vah) if vah else None,
                float(val) if val else None,
                float(poc) if poc else None,
                va_migration,
                bool(poor_high) if poor_high is not None else False,
                bool(poor_low) if poor_low is not None else False,
                volume_quality,
                float(ib_high) if ib_high else None,
                float(ib_low) if ib_low else None,
                interpretation,
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
    Three-tier Pythia scoring:
    Tier 1 — Static position (entry vs VAH/VAL/POC)
    Tier 2 — Dynamic session data (VA migration, poor extremes, volume quality)
    Tier 3 — IB context (initial balance breakout/failure)
    """
    _no_coverage = {
        "profile_bonus": 0,
        "total_pythia_adjustment": 0,
        "pythia_coverage": False,
        "needs_structural_review": True,
    }

    redis = await get_redis_client()
    if not redis:
        return _no_coverage

    try:
        raw = await redis.get(f"pythia:{ticker}")
        if not raw:
            raw = await redis.get(f"mp_levels:{ticker}")
        if not raw:
            # Telemetry: count coverage misses per ticker for weekly watchlist review
            try:
                await redis.incr(f"pythia_coverage_miss:{ticker}")
                await redis.expire(f"pythia_coverage_miss:{ticker}", 604800)  # 7 days
            except Exception:
                pass
            return _no_coverage

        data = json.loads(raw)
        vah = data.get("vah")
        val = data.get("val")
        poc = data.get("poc")
        if not vah or not val or not poc:
            return _no_coverage

        vah, val, poc = float(vah), float(val), float(poc)
        is_long = direction.upper() in ("LONG", "BUY", "BULLISH")

        # ── Tier 1: Static position ──
        if is_long:
            if entry_price <= val:
                tier1 = 8; zone = "below_VAL"
            elif entry_price <= poc:
                tier1 = 3; zone = "VAL_to_POC"
            elif entry_price <= vah:
                tier1 = 0; zone = "POC_to_VAH"
            else:
                tier1 = -10; zone = "above_VAH"
        else:
            if entry_price >= vah:
                tier1 = 8; zone = "above_VAH"
            elif entry_price >= poc:
                tier1 = 3; zone = "POC_to_VAH"
            elif entry_price >= val:
                tier1 = 0; zone = "VAL_to_POC"
            else:
                tier1 = -10; zone = "below_VAL"

        # ── Tier 2: Dynamic session data ──
        migration_adj = 0
        poor_adj = 0
        vol_quality = data.get("volume_quality", "normal")
        va_migration = data.get("va_migration", "")
        poor_high = data.get("poor_high", False)
        poor_low = data.get("poor_low", False)
        data_age = "current"

        # Also check recent pythia_events for richer data
        try:
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                evt = await conn.fetchrow(
                    "SELECT va_migration, poor_high, poor_low, volume_quality, "
                    "ib_high, ib_low FROM pythia_events "
                    "WHERE ticker = $1 AND timestamp > NOW() - INTERVAL '4 hours' "
                    "ORDER BY timestamp DESC LIMIT 1", ticker
                )
                if evt:
                    va_migration = evt["va_migration"] or va_migration
                    poor_high = evt["poor_high"] if evt["poor_high"] is not None else poor_high
                    poor_low = evt["poor_low"] if evt["poor_low"] is not None else poor_low
                    vol_quality = evt["volume_quality"] or vol_quality
                    data.update({
                        "ib_high": float(evt["ib_high"]) if evt["ib_high"] else data.get("ib_high"),
                        "ib_low": float(evt["ib_low"]) if evt["ib_low"] else data.get("ib_low"),
                    })
                else:
                    data_age = "stale"
        except Exception:
            data_age = "stale"

        # VA migration scoring — PineScript writes "higher"/"lower"/"overlapping"/"unknown"
        if va_migration:
            mig = va_migration.lower().strip()
            if (is_long and mig == "higher") or (not is_long and mig == "lower"):
                migration_adj = 3
            elif (is_long and mig == "lower") or (not is_long and mig == "higher"):
                migration_adj = -8
            # "overlapping" and "unknown" stay 0 (no directional edge)
        logger.debug("Pythia %s migration=%r adj=%+d", ticker, va_migration, migration_adj)

        # Poor extreme scoring
        if poor_low and is_long:
            poor_adj = -10
        elif poor_high and not is_long:
            poor_adj = -10
        elif poor_low and not is_long:
            poor_adj = 5
        elif poor_high and is_long:
            poor_adj = 5

        # Volume quality multiplier on Tier 1
        if vol_quality == "high":
            tier1 = round(tier1 * 1.5)
        elif vol_quality == "thin":
            tier1 = round(tier1 * 0.5)

        # ── Tier 3: IB context ──
        ib_adj = 0
        ib_high = data.get("ib_high")
        ib_low = data.get("ib_low")
        if ib_high and ib_low:
            ib_h, ib_l = float(ib_high), float(ib_low)
            if entry_price > ib_h and is_long and vol_quality == "high":
                ib_adj = 5
            elif entry_price < ib_l and is_long:
                ib_adj = -5
            elif entry_price < ib_l and not is_long and vol_quality == "high":
                ib_adj = 5
            elif entry_price > ib_h and not is_long:
                ib_adj = -5

        total = tier1 + migration_adj + poor_adj + ib_adj

        return {
            "profile_bonus": tier1,
            "migration_bonus": migration_adj,
            "poor_extreme_bonus": poor_adj,
            "ib_bonus": ib_adj,
            "volume_quality": vol_quality,
            "total_pythia_adjustment": total,
            "zone": zone,
            "vah": vah, "val": val, "poc": poc,
            "data_age": data_age,
            "pythia_coverage": True,
            "needs_structural_review": False,
        }

    except Exception as e:
        logger.debug("Pythia profile lookup failed for %s: %s", ticker, e)
        return {"profile_bonus": 0, "total_pythia_adjustment": 0,
                "pythia_coverage": False, "needs_structural_review": True}
