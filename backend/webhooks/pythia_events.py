"""
Pythia Market Profile Events — stores VAL/VAH cross alerts from TradingView.

Receives alerts when price crosses value area boundaries, stores in
pythia_events table for scoring cross-reference (P4B) and committee context.
"""

import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client

logger = logging.getLogger("pythia_events")
router = APIRouter(tags=["pythia"])

# B4 Chunk B — AEGIS hardening.
# This handler is the chokepoint for the live PYTHIA feed: the /webhook/tradingview
# router forwards source=="pythia" payloads here (early-return BEFORE its own secret
# check), AND it is directly POST-able at /api/webhook/pythia. Enforcing here covers
# both paths.
PYTHIA_WEBHOOK_SECRET = os.getenv("PYTHIA_WEBHOOK_SECRET") or ""
MAX_PAYLOAD_BYTES = 8192  # reject oversized bodies

# B4 Chunk C — replay protection + idempotency.
REPLAY_WINDOW_MS = 10 * 60 * 1000   # ±10 min tolerance on bar_time (TV fire time)
IDEMPOTENCY_TTL_S = 30 * 60          # pythia_seen:{ticker}:{event}:{bar_time} key TTL


def _pos_num(v):
    """True only if v parses to a strictly positive float (rejects nz()-zeros)."""
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


def _num_or_none(v):
    """Float, but treat 0/0.0 and non-numeric as None.

    Pine v2.4 serializes missing levels as nz(x,0) -> literal 0. A confident
    zero is NOT data — store NULL, not a fake level.
    """
    try:
        f = float(v)
        return f if f != 0 else None
    except (TypeError, ValueError):
        return None


@router.post("/webhook/pythia")
async def pythia_webhook(request: Request = None, payload: dict = None):
    """
    Receive Pythia market profile alerts from TradingView.
    Expected payload fields: ticker, alert_type/event, price, vah, val, poc,
    direction, secret, bar_time, and rich v2.4 fields.
    Called directly (POST /api/webhook/pythia) or with a payload dict from the
    /webhook/tradingview router. Both paths are authenticated here.
    """
    if payload is None:
        # R-4: reject oversized bodies before reading them into memory (direct hits)
        cl = request.headers.get("content-length") if request else None
        if cl and cl.isdigit() and int(cl) > MAX_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="payload too large")
        payload = await request.json()

    # ── AEGIS: payload size cap (router-forward path / chunked bodies) ──
    if len(json.dumps(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        logger.warning("Rejected PYTHIA webhook — payload over size cap")
        raise HTTPException(status_code=413, detail="payload too large")

    # ── AEGIS: shared secret — constant-time, FAIL-CLOSED ──
    if not PYTHIA_WEBHOOK_SECRET:
        logger.error("PYTHIA_WEBHOOK_SECRET not configured — rejecting (fail-closed)")
        raise HTTPException(status_code=503, detail="webhook auth not configured")
    supplied = str(payload.get("secret") or "")
    if not hmac.compare_digest(supplied, PYTHIA_WEBHOOK_SECRET):
        logger.warning("Rejected PYTHIA webhook — invalid secret (ticker=%s)",
                       payload.get("ticker"))
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    # ── AEGIS: strip secret before ANY logging or persistence ──
    payload = {k: v for k, v in payload.items() if k != "secret"}

    ticker = (payload.get("ticker") or "").upper()
    alert_type = payload.get("alert_type") or payload.get("event") or payload.get("signal_type") or "unknown"
    price = payload.get("price") or payload.get("close")
    direction = payload.get("direction") or ""
    vah = payload.get("vah")
    val = payload.get("val")
    poc = payload.get("poc")

    # ── AEGIS: required fields present + numeric + > 0 (reject confident-zeros) ──
    if not ticker:
        raise HTTPException(status_code=400, detail="missing ticker")
    if not (_pos_num(vah) and _pos_num(val) and _pos_num(poc)):
        logger.warning(
            "Rejected PYTHIA webhook — vah/val/poc missing or <= 0 (ticker=%s vah=%s val=%s poc=%s)",
            ticker, vah, val, poc,
        )
        raise HTTPException(status_code=400, detail="vah/val/poc required and must be > 0")

    # ── Chunk C: replay protection — bar_time required + within ±10 min ──
    # Q-C1 ruling: missing/malformed bar_time → reject 400 (no confident default).
    try:
        bar_time_ms = int(float(payload.get("bar_time")))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="bar_time required and must be numeric epoch ms")
    now_ms = int(time.time() * 1000)
    if abs(now_ms - bar_time_ms) > REPLAY_WINDOW_MS:
        logger.warning("Rejected PYTHIA webhook — bar_time outside replay window (ticker=%s skew_ms=%s)",
                       ticker, now_ms - bar_time_ms)
        raise HTTPException(status_code=400, detail="bar_time outside replay window (+/-10 min)")

    # Rich fields — treat 0.0 as null (nz()-zero scrub), not data
    va_migration = payload.get("va_migration")
    poor_high = payload.get("poor_high", False)
    poor_low = payload.get("poor_low", False)
    volume_quality = payload.get("volume_quality")
    ib_high = _num_or_none(payload.get("ib_high"))
    ib_low = _num_or_none(payload.get("ib_low"))
    interpretation = payload.get("interpretation")

    logger.info("PYTHIA event: %s %s @ %s (VAH=%s POC=%s VAL=%s mig=%s vol=%s)",
                ticker, alert_type, price, vah, poc, val, va_migration, volume_quality)

    # ── Chunk C: idempotency — first writer wins per (ticker, event, bar_time) ──
    # TV retries on non-2xx; SETNX is the atomic claim. Duplicate → 200, no row.
    # Redis-down degrades open (allow the write) — never drop a real event for a
    # cache outage.
    _redis = await get_redis_client()
    if _redis:
        seen_key = f"pythia_seen:{ticker}:{alert_type}:{bar_time_ms}"
        try:
            is_new = await _redis.set(seen_key, "1", nx=True, ex=IDEMPOTENCY_TTL_S)
        except Exception as exc:
            logger.debug("PYTHIA idempotency SETNX failed (%s) — proceeding without dedup", exc)
            is_new = True
        if not is_new:
            logger.info("PYTHIA duplicate suppressed: %s %s bar_time=%s", ticker, alert_type, bar_time_ms)
            return {"status": "duplicate", "ticker": ticker, "alert_type": alert_type}

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
                _num_or_none(price),
                direction,
                float(vah),  # validated > 0 above
                float(val),
                float(poc),
                va_migration,
                bool(poor_high) if poor_high is not None else False,
                bool(poor_low) if poor_low is not None else False,
                volume_quality,
                ib_high,     # already None-or-float (nz-zero scrubbed)
                ib_low,
                interpretation,
                json.dumps(payload),  # secret already stripped above
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
