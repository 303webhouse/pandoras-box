"""
PYTHIA Market Profile Levels — Webhook Handler

Receives MP level data from TradingView Pine Script indicator,
stores in Redis with 24h TTL, forwards 80% rule alerts to Discord.
"""
import hmac
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request

from database.redis_client import get_redis_client

logger = logging.getLogger("mp_levels")
router = APIRouter()

MP_LEVELS_TTL = 86400  # 24 hours
DISCORD_WEBHOOK_SIGNALS = os.getenv("DISCORD_WEBHOOK_SIGNALS") or ""

# B4 Chunk B — AEGIS hardening. This endpoint has no live writer today (census
# 2026-06-09) but is externally POST-able; same shared-secret gate as
# pythia_events. Reuses PYTHIA_WEBHOOK_SECRET.
PYTHIA_WEBHOOK_SECRET = os.getenv("PYTHIA_WEBHOOK_SECRET") or ""
MAX_PAYLOAD_BYTES = 8192


async def _notify_discord_mp_alert(payload: dict):
    """Post 80% rule alert to Discord signals channel."""
    if not DISCORD_WEBHOOK_SIGNALS:
        logger.debug("No Discord webhook configured for MP alerts")
        return

    ticker = payload.get("ticker", "???")
    direction = payload.get("direction", "???")
    vah = payload.get("vah", "?")
    val = payload.get("val", "?")
    poc = payload.get("poc", "?")
    detail = payload.get("detail", "80% rule triggered")

    content = (
        f"\U0001f52e **PYTHIA: 80% Rule — {ticker}**\n"
        f"{detail}\n"
        f"Expect travel to {'VAL' if direction == 'BEARISH' else 'VAH'} "
        f"(${val if direction == 'BEARISH' else vah}) | POC at ${poc}"
    )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(DISCORD_WEBHOOK_SIGNALS, json={"content": content})
    except Exception as e:
        logger.warning("Discord MP alert failed: %s", e)


@router.post("/mp_levels")
async def mp_levels_webhook(request: Request):
    """Receive Market Profile levels from TradingView webhook."""
    # R-4: reject oversized bodies before reading them into memory
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    payload = await request.json()

    # ── AEGIS: size cap (chunked bodies without Content-Length) ──
    if len(json.dumps(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        logger.warning("Rejected mp_levels webhook — payload over size cap")
        raise HTTPException(status_code=413, detail="payload too large")

    # ── AEGIS: shared secret — constant-time, FAIL-CLOSED ──
    if not PYTHIA_WEBHOOK_SECRET:
        logger.error("PYTHIA_WEBHOOK_SECRET not configured — rejecting (fail-closed)")
        raise HTTPException(status_code=503, detail="webhook auth not configured")
    if not hmac.compare_digest(str(payload.get("secret") or ""), PYTHIA_WEBHOOK_SECRET):
        logger.warning("Rejected mp_levels webhook — invalid secret (ticker=%s)",
                       payload.get("ticker"))
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    # ── AEGIS: strip secret before persistence ──
    payload = {k: v for k, v in payload.items() if k != "secret"}

    ticker = (payload.get("ticker") or "").upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="missing ticker")

    redis = await get_redis_client()
    if not redis:
        logger.warning("Redis unavailable — cannot store MP levels")
        return {"error": "redis unavailable"}

    key = f"mp_levels:{ticker}"
    await redis.set(key, json.dumps(payload), ex=MP_LEVELS_TTL)
    logger.info("MP levels stored for %s: POC=%s VAH=%s VAL=%s",
                ticker, payload.get("poc"), payload.get("vah"), payload.get("val"))

    # Forward 80% rule alerts to Discord
    if payload.get("alert_type") == "80pct_rule":
        await _notify_discord_mp_alert(payload)

    return {"status": "ok", "ticker": ticker}
