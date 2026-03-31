"""
Hermes Flash — Webhook Receiver & Correlation Engine

Receives TradingView velocity breach alerts, evaluates tier (single vs correlated),
stores catalyst events, triggers VPS for Pivot intelligence scrape.

Threshold rationale (set in TradingView per ticker):
  HYG at 0.5%  — high yield bonds barely move; 0.5% in 30 min is a screaming signal
  USO/IBIT at 2.0% — naturally volatile, tighter threshold = noise
  SMH at 1.5% — high beta to QQQ, needs wider band
  Everything else at 1.0% — standard sensitivity for liquid ETFs
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Request, HTTPException, Query

from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client

logger = logging.getLogger("hermes")
router = APIRouter(tags=["hermes"])

# --- Config (editable in code, no DB dependency) ---
HERMES_CONFIG = {
    "tickers": {
        "SPY":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "broad_market"},
        "QQQ":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "tech"},
        "SMH":  {"threshold_pct": 1.5, "timeframe_min": 30, "category": "semis"},
        "XLF":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "financials"},
        "HYG":  {"threshold_pct": 0.5, "timeframe_min": 30, "category": "credit"},
        "IYR":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "real_estate"},
        "TLT":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "bonds"},
        "USO":  {"threshold_pct": 2.0, "timeframe_min": 30, "category": "oil"},
        "GLD":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "safe_haven"},
        "IBIT": {"threshold_pct": 2.0, "timeframe_min": 30, "category": "crypto"},
    },
    "correlation_groups": {
        "credit_event":  ["XLF", "HYG", "IYR"],
        "risk_off":      ["SPY", "QQQ", "SMH"],
        "deescalation":  ["USO", "GLD", "TLT"],
        "full_reversal": ["SPY", "QQQ", "SMH", "XLF", "HYG"],
    },
    "correlation_window_minutes": 5,
    "correlation_min_tickers": 2,
    "vps_trigger_url": "http://188.245.250.2:8000/api/hermes/trigger",
    "cooldown_minutes": 15,
}

VPS_API_KEY = os.getenv("HERMES_VPS_KEY") or ""

# In-memory sliding window for correlation detection
recent_breaches: Dict[str, dict] = {}

# Ticker-specific context terms for Pivot search
CONTEXT_MAP = {
    "SPY": ["S&P 500", "market", "stocks"],
    "QQQ": ["Nasdaq", "tech stocks"],
    "SMH": ["semiconductors", "chips", "NVDA"],
    "XLF": ["banks", "financials", "credit"],
    "HYG": ["high yield", "junk bonds", "credit spread", "default"],
    "IYR": ["real estate", "REIT", "commercial real estate"],
    "TLT": ["Treasury", "bonds", "yields", "10 year"],
    "USO": ["oil", "crude", "Hormuz", "Iran"],
    "GLD": ["gold", "safe haven"],
    "IBIT": ["Bitcoin", "crypto", "BTC"],
}


@router.post("/webhook/hermes")
async def hermes_webhook(request: Request):
    """
    Receives TradingView velocity breach alerts.
    Evaluates tier (single vs correlated), stores event, triggers VPS if needed.
    """
    try:
        payload = await request.json()
    except Exception:
        body = await request.body()
        try:
            payload = json.loads(body.decode())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    ticker = payload.get("ticker")
    velocity_pct = payload.get("velocity_pct")
    direction = payload.get("direction")
    alert_type = payload.get("alert_type")

    if not ticker or velocity_pct is None or alert_type != "hermes_flash":
        raise HTTPException(status_code=400, detail="Missing or invalid hermes_flash fields")

    velocity_pct = float(velocity_pct)
    logger.info("HERMES FLASH: %s %s %.2f%% velocity breach", ticker, direction, velocity_pct)

    config = HERMES_CONFIG
    cooldown_minutes = config.get("cooldown_minutes", 15)
    now = datetime.now(timezone.utc)

    # Cooldown check
    last_breach = recent_breaches.get(ticker)
    if last_breach and (now - last_breach["timestamp"]) < timedelta(minutes=cooldown_minutes):
        logger.info("HERMES: %s in cooldown, skipping", ticker)
        return {"status": "cooldown", "ticker": ticker}

    # Record breach in sliding window
    recent_breaches[ticker] = {
        "timestamp": now,
        "velocity_pct": velocity_pct,
        "direction": direction,
    }

    # Clean old entries
    correlation_window = config.get("correlation_window_minutes", 5)
    cutoff = now - timedelta(minutes=correlation_window)
    stale = [k for k, v in recent_breaches.items() if v["timestamp"] < cutoff]
    for k in stale:
        del recent_breaches[k]

    # Correlation detection
    correlated = []
    tier = 1
    for group_name, group_tickers in config.get("correlation_groups", {}).items():
        if ticker in group_tickers:
            group_breaches = [
                {"ticker": t, "move_pct": round(recent_breaches[t]["velocity_pct"], 2)}
                for t in group_tickers
                if t in recent_breaches and t != ticker
            ]
            if len(group_breaches) >= (config.get("correlation_min_tickers", 2) - 1):
                tier = 2
                correlated = group_breaches
                logger.info("HERMES: Tier 2 CORRELATED — %s: %s + %s",
                            group_name, ticker, [b["ticker"] for b in group_breaches])
                break

    # Sector velocity snapshot
    sector_velocity = await _get_sector_velocity_snapshot()

    # Trip wire status (reuse existing endpoint logic)
    trip_wire_status = await _get_trip_wire_status()

    # Store catalyst event
    event_id = await _store_catalyst_event(
        event_type="velocity_breach",
        tier=tier,
        trigger_ticker=ticker,
        trigger_move_pct=velocity_pct,
        trigger_timeframe=f"{payload.get('timeframe_min', 30)}min",
        correlated_tickers=correlated,
        sector_velocity=sector_velocity,
        trip_wire_status=trip_wire_status,
    )

    # Trigger VPS scrape burst
    vps_url = config.get("vps_trigger_url")
    if vps_url and VPS_API_KEY:
        try:
            search_terms = _build_search_terms(ticker, direction, correlated)
            async with httpx.AsyncClient(timeout=5.0) as client:
                vps_payload = {
                    "event_id": str(event_id),
                    "tier": tier,
                    "trigger_ticker": ticker,
                    "velocity_pct": velocity_pct,
                    "direction": direction,
                    "correlated_tickers": correlated,
                    "search_terms": search_terms,
                    "scrape_interval_seconds": 120,
                    "scrape_duration_minutes": 15,
                    "timestamp": now.isoformat(),
                }
                resp = await client.post(
                    vps_url,
                    json=vps_payload,
                    headers={"X-API-Key": VPS_API_KEY},
                )
                logger.info("HERMES: VPS trigger sent, status %d", resp.status_code)
        except Exception as e:
            logger.error("HERMES: VPS trigger failed: %s", e)

    # Broadcast via WebSocket if available
    try:
        from api.websocket_manager import broadcast_event
        await broadcast_event("hermes_flash", {
            "event_id": str(event_id),
            "tier": tier,
            "trigger_ticker": ticker,
            "trigger_move_pct": velocity_pct,
            "direction": direction,
            "correlated_tickers": correlated,
            "sector_velocity": sector_velocity,
            "trip_wire_status": trip_wire_status,
        })
    except Exception:
        pass

    return {
        "status": "alert_created",
        "event_id": str(event_id),
        "tier": tier,
        "ticker": ticker,
        "correlated": [b["ticker"] for b in correlated],
    }


PIVOT_API_KEY = os.getenv("PIVOT_API_KEY") or ""


@router.post("/hermes/analysis")
async def receive_hermes_analysis(request: Request):
    """
    Receives Pivot's LLM analysis from VPS and updates the catalyst_events row.
    Called by VPS after scrape burst completes — same auth pattern as committee bridge.
    """
    api_key = request.headers.get("X-API-Key")
    if not PIVOT_API_KEY or api_key != PIVOT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    payload = await request.json()
    event_id = payload.get("event_id")
    analysis = payload.get("analysis", {})

    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event_id")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE catalyst_events
               SET headline_summary = $1,
                   catalyst_category = $2,
                   pivot_analysis = $3,
                   updated_at = NOW()
               WHERE id = $4""",
            analysis.get("headline_summary", ""),
            analysis.get("catalyst_category", "unknown"),
            json.dumps(analysis),
            uuid.UUID(event_id),
        )

    logger.info("HERMES ANALYSIS received for event %s: %s",
                event_id, analysis.get("headline_summary", "")[:80])

    # Broadcast update via WebSocket
    try:
        from api.websocket_manager import broadcast_event
        await broadcast_event("hermes_analysis", {
            "event_id": event_id,
            "headline_summary": analysis.get("headline_summary", ""),
            "catalyst_category": analysis.get("catalyst_category", "unknown"),
            "confidence": analysis.get("confidence", 0),
        })
    except Exception:
        pass

    return {"status": "updated", "event_id": event_id}


@router.get("/hermes/alerts")
async def get_hermes_alerts(
    limit: int = Query(20, ge=1, le=100),
    include_dismissed: bool = False,
    tier_min: int = Query(1, ge=1, le=3),
):
    """Returns catalyst events for the Agora frontend."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if include_dismissed:
            rows = await conn.fetch(
                "SELECT * FROM catalyst_events WHERE tier >= $1 ORDER BY created_at DESC LIMIT $2",
                tier_min, limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM catalyst_events WHERE dismissed = false AND tier >= $1 ORDER BY created_at DESC LIMIT $2",
                tier_min, limit,
            )

    alerts = []
    for r in rows:
        alerts.append({
            "id": str(r["id"]),
            "event_type": r["event_type"],
            "tier": r["tier"],
            "trigger_ticker": r["trigger_ticker"],
            "trigger_move_pct": float(r["trigger_move_pct"]) if r["trigger_move_pct"] else None,
            "trigger_timeframe": r["trigger_timeframe"],
            "correlated_tickers": r["correlated_tickers"] if r["correlated_tickers"] else [],
            "headline_summary": r["headline_summary"],
            "catalyst_category": r["catalyst_category"],
            "pivot_analysis": r["pivot_analysis"],
            "sector_velocity": r["sector_velocity"] if r["sector_velocity"] else {},
            "trip_wire_status": r["trip_wire_status"] if r["trip_wire_status"] else {},
            "dismissed": r["dismissed"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })

    return {"alerts": alerts, "count": len(alerts)}


@router.patch("/hermes/alerts/{event_id}/dismiss")
async def dismiss_hermes_alert(event_id: str):
    """Mark a catalyst event as dismissed."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE catalyst_events SET dismissed = true, dismissed_at = NOW() WHERE id = $1",
            uuid.UUID(event_id),
        )
    return {"status": "dismissed", "event_id": event_id}


# --- Helpers ---

def _build_search_terms(ticker: str, direction: str, correlated: list) -> list:
    """Build dynamic search terms for Pivot's Twitter scrape."""
    terms = ["$" + ticker, ticker]
    terms.extend(CONTEXT_MAP.get(ticker, []))

    if correlated:
        correlated_tickers = [b["ticker"] for b in correlated]
        if any(t in correlated_tickers for t in ["XLF", "HYG", "IYR"]):
            terms.extend(["credit crisis", "bank stress", "private credit", "default"])
        if any(t in correlated_tickers for t in ["SPY", "QQQ", "SMH"]):
            terms.extend(["risk off" if direction == "down" else "relief rally",
                          "sell off" if direction == "down" else "buying"])
        if any(t in correlated_tickers for t in ["USO", "GLD", "TLT"]):
            terms.extend(["ceasefire", "Iran deal", "Hormuz", "peace talks"])

    terms.extend(["Iran", "Hormuz", "Trump"])
    return list(set(terms))


async def _get_sector_velocity_snapshot() -> dict:
    """Get current prices for all Hermes tickers from macro strip cache or Polygon."""
    redis = await get_redis_client()
    if not redis:
        return {}

    try:
        cached = await redis.get("macro:strip")
        if cached:
            data = json.loads(cached)
            return {t["ticker"]: t["change_pct"] for t in data.get("tickers", []) if t.get("ticker")}
    except Exception:
        pass
    return {}


async def _get_trip_wire_status() -> dict:
    """Check trip wire status by calling the existing endpoint logic."""
    try:
        from api.trip_wires import get_trip_wires
        result = await get_trip_wires()
        return {w["id"]: w["status"] == "HOT" for w in result.get("wires", [])}
    except Exception as e:
        logger.warning("HERMES: Trip wire check failed: %s", e)
        return {}


async def _store_catalyst_event(**kwargs) -> str:
    """Insert into catalyst_events table, return event UUID."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO catalyst_events
               (event_type, tier, trigger_ticker, trigger_move_pct, trigger_timeframe,
                correlated_tickers, sector_velocity, trip_wire_status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            kwargs.get("event_type", "velocity_breach"),
            kwargs.get("tier", 1),
            kwargs["trigger_ticker"],
            kwargs.get("trigger_move_pct"),
            kwargs.get("trigger_timeframe", "30min"),
            json.dumps(kwargs.get("correlated_tickers", [])),
            json.dumps(kwargs.get("sector_velocity", {})),
            json.dumps(kwargs.get("trip_wire_status", {})),
        )
        return row["id"]
