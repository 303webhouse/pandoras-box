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

    # Hydra convergence check — are any involved tickers in squeeze territory?
    # If so, generate a Lightning Card
    convergence_alert = None
    try:
        from scanners.hydra_squeeze import calculate_squeeze_score
        involved_tickers = [ticker] + [b["ticker"] for b in correlated]
        for t in involved_tickers:
            sv = sector_velocity.get(t, 0) if isinstance(sector_velocity, dict) else 0
            score = await calculate_squeeze_score(t, sector_velocity=sv)
            if score and score["composite_score"] >= 50:
                logger.info("HERMES+HYDRA CONVERGENCE: %s catalyst + squeeze score %.1f",
                            t, score["composite_score"])
                convergence_alert = {
                    "ticker": t,
                    "squeeze_score": score["composite_score"],
                    "squeeze_tier": score["squeeze_tier"],
                }

                # === LIGHTNING CARD GENERATION ===
                card_direction = "bullish" if direction == "up" else "bearish"
                try:
                    # Position classification: CONFIRMING / OPPOSING / UNRELATED
                    relationship = await _classify_position_relationship(
                        pool, t, card_direction
                    )

                    # Get current price for post-mortem tracking
                    current_price = None
                    try:
                        import httpx
                        poly_key = os.getenv("POLYGON_API_KEY", "")
                        if poly_key:
                            async with httpx.AsyncClient(timeout=5.0) as hc:
                                snap = await hc.get(
                                    f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{t}",
                                    params={"apiKey": poly_key},
                                )
                                if snap.status_code == 200:
                                    sd = snap.json().get("ticker", {})
                                    current_price = (
                                        sd.get("day", {}).get("c")
                                        or sd.get("prevDay", {}).get("c")
                                    )
                    except Exception:
                        pass

                    async with pool.acquire() as conn:
                        await conn.execute("""
                            INSERT INTO lightning_cards (
                                catalyst_event_id, ticker, direction,
                                squeeze_composite_score, squeeze_tier,
                                position_relationship, related_position_id,
                                related_position_details, action_hint,
                                catalyst_headline, catalyst_category,
                                price_at_generation, status
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'active'
                            )
                        """,
                            event_id, t, card_direction,
                            score["composite_score"], score["squeeze_tier"],
                            relationship.get("relationship", "UNRELATED"),
                            relationship.get("position_id"),
                            relationship.get("details"),
                            relationship.get("action_hint"),
                            None,  # headline filled later by Pivot
                            None,  # category filled later by Pivot
                            current_price,
                        )
                    logger.info(
                        "LIGHTNING CARD created: %s %s (score %.1f, %s)",
                        t, card_direction, score["composite_score"],
                        relationship.get("relationship", "UNRELATED"),
                    )
                except Exception as lc_err:
                    logger.error("Lightning Card creation failed: %s", lc_err)

                break
    except Exception as e:
        logger.debug("Hydra convergence check in Hermes failed: %s", e)

    # Broadcast via WebSocket if available
    try:
        from api.websocket_manager import broadcast_event
        ws_payload = {
            "event_id": str(event_id),
            "tier": tier,
            "trigger_ticker": ticker,
            "trigger_move_pct": velocity_pct,
            "direction": direction,
            "correlated_tickers": correlated,
            "sector_velocity": sector_velocity,
            "trip_wire_status": trip_wire_status,
        }
        if convergence_alert:
            ws_payload["hydra_convergence"] = convergence_alert
        await broadcast_event("hermes_flash", ws_payload)
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

    # Validate UUID format
    try:
        event_uuid = uuid.UUID(event_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid event_id format: {event_id}")

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
            event_uuid,
        )
        # Check if a row was actually updated
        rows_affected = int(result.split()[-1]) if result else 0
        if rows_affected == 0:
            logger.warning("HERMES ANALYSIS: No catalyst_event found for id %s", event_id)
            return {"status": "not_found", "event_id": event_id, "detail": "No matching catalyst event"}

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

    # Update any Lightning Cards linked to this event with Pivot's analysis
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE lightning_cards
                SET catalyst_headline = $1,
                    catalyst_category = $2,
                    thesis_impact = $3,
                    updated_at = NOW()
                WHERE catalyst_event_id = $4
                AND status = 'active'
            """,
                analysis.get("headline_summary", ""),
                analysis.get("catalyst_category", "unknown"),
                analysis.get("thesis_impact", ""),
                event_uuid,
            )
    except Exception as e:
        logger.debug("Lightning Card update with Pivot analysis failed: %s", e)

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


# Correlated ticker map: individual stock → ETF it belongs to
_CORRELATION_MAP = {
    "NVDA": "SMH", "AMD": "SMH", "MRVL": "SMH", "AVGO": "SMH",
    "INTC": "SMH", "QCOM": "SMH", "MU": "SMH", "SMCI": "SMH",
    "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "GS": "XLF",
    "MS": "XLF", "C": "XLF", "SCHW": "XLF", "BLK": "XLF",
    "AMT": "IYR", "PLD": "IYR", "SPG": "IYR", "O": "IYR",
    "COIN": "IBIT", "MSTR": "IBIT", "MARA": "IBIT", "RIOT": "IBIT",
}


async def _classify_position_relationship(pool, ticker: str, direction: str) -> dict:
    """
    Three-way classification:
      CONFIRMING  — squeeze aligns with position (thesis accelerating)
      OPPOSING    — squeeze works against position (position at risk)
      UNRELATED   — no position on this ticker
    Also checks correlated ETFs (e.g. MRVL squeeze vs SMH puts).
    """
    try:
        async with pool.acquire() as conn:
            positions = await conn.fetch(
                "SELECT position_id, ticker, direction, option_type, "
                "strike_price, expiry_date FROM unified_positions "
                "WHERE status = 'OPEN' AND ticker = $1",
                ticker,
            )
            corr_etf = _CORRELATION_MAP.get(ticker)
            if not positions and corr_etf:
                positions = await conn.fetch(
                    "SELECT position_id, ticker, direction, option_type, "
                    "strike_price, expiry_date FROM unified_positions "
                    "WHERE status = 'OPEN' AND ticker = $1",
                    corr_etf,
                )

        if not positions:
            return {"relationship": "UNRELATED"}

        for pos in positions:
            pos_dir = pos.get("direction", "")
            opt_type = pos.get("option_type", "")
            pos_bearish = pos_dir in ("SHORT", "BEARISH") or opt_type == "PUT"
            pos_bullish = pos_dir in ("LONG", "BULLISH") or opt_type == "CALL"
            pt = pos.get("ticker", "")
            strike = pos.get("strike_price", "")
            expiry = pos.get("expiry_date", "")
            details = f"{pt} {opt_type or pos_dir} {'$' + str(strike) if strike else ''} {expiry or ''}".strip()
            is_corr = pt != ticker
            if is_corr:
                details += f" (correlated: {ticker} → {pt})"

            if (direction == "bullish" and pos_bullish) or (direction == "bearish" and pos_bearish):
                return {
                    "relationship": "CONFIRMING",
                    "position_id": pos["position_id"],
                    "details": details,
                    "action_hint": "Thesis accelerating — tighten stops, take partials, or add to winner",
                }
            if (direction == "bullish" and pos_bearish) or (direction == "bearish" and pos_bullish):
                return {
                    "relationship": "OPPOSING",
                    "position_id": pos["position_id"],
                    "details": details,
                    "action_hint": "Position at risk — consider hedging, reducing size, or closing",
                }
    except Exception as e:
        logger.debug("Position classification error: %s", e)

    return {"relationship": "UNRELATED"}
