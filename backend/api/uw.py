"""
API endpoints for receiving UW flow data from Pivot and caching in Redis.
Also broadcasts flow updates via WebSocket for real-time frontend updates.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends

from database.redis_client import get_redis_client

try:
    from utils.pivot_auth import verify_pivot_key
except Exception:  # pragma: no cover
    from backend.utils.pivot_auth import verify_pivot_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uw", tags=["unusual-whales"])

FLOW_TTL = 3600        # 1 hour
TICKER_UPDATE_TTL = 3600  # 1 hour for UW ticker update data
MARKET_FLOW_TTL = 3600    # 1 hour for aggregate market flow
DISCOVERY_TTL = 14400  # 4 hours
RECENT_LIST_MAX = 50   # Max items in the recent alerts list

# UW Flow → Signal thresholds (stored in Redis for tunability, these are defaults)
UW_SIGNAL_DEFAULTS = {
    "min_premium": 500_000,      # $500K total premium
    "min_unusual_count": 3,      # 3+ unusual trades
    "cooldown_seconds": 3600,    # 1 hour per-ticker cooldown
}


async def _maybe_create_uw_signal(ticker_data: dict) -> bool:
    """
    Check if a UW ticker update meets the threshold for independent signal creation.
    Returns True if a signal was created.
    """
    ticker = ticker_data.get("ticker", "").upper()
    if not ticker:
        return False

    total_premium = float(ticker_data.get("total_premium") or 0)
    pc_ratio = float(ticker_data.get("pc_ratio") or 1.0)
    flow_sentiment = ticker_data.get("flow_sentiment")

    # Load thresholds from Redis (with defaults)
    client = await get_redis_client()
    min_premium = UW_SIGNAL_DEFAULTS["min_premium"]
    cooldown = UW_SIGNAL_DEFAULTS["cooldown_seconds"]

    if client:
        try:
            rp = await client.get("config:uw_flow:min_premium")
            if rp:
                min_premium = float(rp)
            rc = await client.get("config:uw_flow:cooldown_seconds")
            if rc:
                cooldown = int(rc)
        except Exception:
            pass  # Use defaults

    # Check thresholds
    if total_premium < min_premium:
        return False
    if not flow_sentiment or flow_sentiment not in ("BULLISH", "BEARISH"):
        return False

    # Check bias alignment
    try:
        from bias_engine.composite import get_cached_composite
        cached = await get_cached_composite()
        if cached:
            comp_score = cached.composite_score
            # BULLISH flow in bearish regime = skip. BEARISH flow in bullish regime = skip.
            if flow_sentiment == "BULLISH" and comp_score < -0.15:
                logger.info(f"UW flow {ticker} BULLISH skipped — bearish bias ({comp_score:+.2f})")
                return False
            if flow_sentiment == "BEARISH" and comp_score > 0.15:
                logger.info(f"UW flow {ticker} BEARISH skipped — bullish bias ({comp_score:+.2f})")
                return False
    except Exception:
        pass  # If bias unavailable, proceed without filter

    # Check per-ticker cooldown
    if client:
        cooldown_key = f"uw_signal_cooldown:{ticker}"
        try:
            if await client.get(cooldown_key):
                logger.debug(f"UW flow {ticker} skipped — cooldown active")
                return False
        except Exception:
            pass

    # All gates passed — create signal
    try:
        from signals.pipeline import process_signal_unified
        import hashlib

        direction = "LONG" if flow_sentiment == "BULLISH" else "SHORT"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_hash = hashlib.md5(f"{ticker}{total_premium}{pc_ratio}".encode()).hexdigest()[:6]
        signal_id = f"UW_{ticker}_{ts}_{short_hash}"

        signal_data = {
            "signal_id": signal_id,
            "ticker": ticker,
            "strategy": "UW_Flow",
            "signal_type": f"UW_FLOW_{direction}",
            "direction": direction,
            "entry_price": float(ticker_data.get("price") or 0),
            "stop_loss": None,
            "target_1": None,
            "target_2": None,
            "timeframe": "D",
            "asset_class": "EQUITY",
            "source": "uw_flow",
            "signal_category": "FLOW_INTEL",
            "metadata": {
                "total_premium": total_premium,
                "flow_sentiment": flow_sentiment,
                "pc_ratio": ticker_data.get("pc_ratio"),
                "put_volume": ticker_data.get("put_volume"),
                "call_volume": ticker_data.get("call_volume"),
                "flow_premium": ticker_data.get("flow_premium"),
                "flow_pct": ticker_data.get("flow_pct"),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await process_signal_unified(signal_data, source="uw_flow")

        # Set cooldown
        if client:
            try:
                await client.set(cooldown_key, "1", ex=cooldown)
            except Exception:
                pass

        logger.info(
            f"UW Flow signal created: {signal_id} "
            f"(premium=${total_premium:,.0f}, {flow_sentiment})"
        )
        return True

    except Exception as e:
        logger.warning(f"UW flow signal creation failed for {ticker}: {e}")
        return False


@router.post("/flow")
async def receive_uw_flow(request: Request, _: str = Depends(verify_pivot_key)):
    """
    Receive per-ticker flow summaries from Pivot.
    Write each to Redis as uw:flow:{SYMBOL}.
    Also push notable trades to uw:flow:recent for the Recent Alerts feed,
    and broadcast via WebSocket for real-time frontend updates.
    """
    try:
        body = await request.json()
        summaries = body.get("summaries", [])

        client = await get_redis_client()
        if not client:
            return {"status": "error", "message": "Redis unavailable"}

        written = 0
        tickers_updated = []

        for summary in summaries:
            ticker = summary.get("ticker")
            if not ticker:
                continue
            key = f"uw:flow:{ticker.upper()}"
            await client.set(key, json.dumps(summary), ex=FLOW_TTL)
            written += 1
            tickers_updated.append(ticker.upper())

            # Push notable trade info to the recent alerts list
            # Build an alert record from the summary for the Recent Alerts feed
            alert_record = {
                "ticker": ticker.upper(),
                "sentiment": summary.get("sentiment", "UNKNOWN"),
                "type": "SWEEP" if summary.get("unusual_count", 0) > 2 else "BLOCK",
                "premium": summary.get("call_premium", 0) + summary.get("put_premium", 0),
                "net_premium": summary.get("net_premium", 0),
                "call_premium": summary.get("call_premium", 0),
                "put_premium": summary.get("put_premium", 0),
                "unusualness_score": summary.get("unusualness_score", 0),
                "unusual_count": summary.get("unusual_count", 0),
                "avg_dte": summary.get("avg_dte"),
                "source": "discord_bot",
                "received_at": datetime.now(timezone.utc).isoformat(),
                "timestamp": body.get("timestamp", datetime.now(timezone.utc).isoformat())
            }

            # Include largest trade details if available
            largest = summary.get("largest_trade")
            if largest:
                alert_record["strike"] = largest.get("strike")
                alert_record["expiry"] = largest.get("expiry")
                alert_record["option_type"] = largest.get("option_type")
                alert_record["largest_premium"] = largest.get("premium")

            await client.lpush("uw:flow:recent", json.dumps(alert_record))

        # Trim the recent list to keep it bounded
        await client.ltrim("uw:flow:recent", 0, RECENT_LIST_MAX - 1)

        # Broadcast via WebSocket for real-time frontend updates
        if written > 0:
            try:
                from websocket.broadcaster import manager
                await manager.broadcast({
                    "type": "FLOW_UPDATE",
                    "tickers_updated": tickers_updated,
                    "count": written
                })
            except Exception as e:
                logger.warning(f"Could not broadcast flow update: {e}")

        logger.info("UW flow: cached %s ticker summaries", written)
        return {"status": "success", "cached": written}

    except Exception as e:
        logger.error(f"Error receiving UW flow: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/discovery")
async def receive_uw_discovery(request: Request, _: str = Depends(verify_pivot_key)):
    """
    Receive discovery list from Pivot.
    Write to Redis as uw:discovery (single key, list of tickers or dicts).
    """
    try:
        body = await request.json()
        tickers = body.get("tickers", [])

        client = await get_redis_client()
        if not client:
            return {"status": "error", "message": "Redis unavailable"}

        await client.set("uw:discovery", json.dumps(tickers), ex=DISCOVERY_TTL)

        logger.info("UW discovery: cached %s tickers", len(tickers))
        return {"status": "success", "cached": len(tickers)}

    except Exception as e:
        logger.error(f"Error receiving UW discovery: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/flow/{ticker}")
async def get_uw_flow(ticker: str):
    """
    Read cached UW flow data for a specific ticker.
    Used by the frontend to display flow context alongside signals.
    """
    client = await get_redis_client()
    if not client:
        return {"status": "error", "available": False}

    data = await client.get(f"uw:flow:{ticker.upper()}")
    if data:
        return {"status": "success", "available": True, "flow": json.loads(data)}
    return {"status": "success", "available": False, "flow": None}


@router.get("/discovery")
async def get_uw_discovery():
    """
    Read the current discovery list.
    Used by the dashboard and the CTA scanner.
    """
    client = await get_redis_client()
    if not client:
        return {"status": "error", "tickers": []}

    data = await client.get("uw:discovery")
    if data:
        return {"status": "success", "tickers": json.loads(data)}
    return {"status": "success", "tickers": []}


# ── UW Ticker Updates (from UW Watcher Bot) ─────────────────


@router.post("/ticker-updates")
async def receive_uw_ticker_updates(request: Request, _: str = Depends(verify_pivot_key)):
    """
    Receive parsed UW Ticker Update data from the VPS watcher bot.
    Stores per-ticker data and aggregate market flow snapshot in Redis.
    """
    try:
        body = await request.json()
        tickers = body.get("tickers", [])
        timestamp = body.get("timestamp", datetime.now(timezone.utc).isoformat())

        client = await get_redis_client()
        if not client:
            return {"status": "error", "message": "Redis unavailable"}

        written = 0
        spy_data = None
        qqq_data = None
        total_premium = 0.0
        bearish_count = 0
        bullish_count = 0

        for td in tickers:
            ticker = td.get("ticker")
            if not ticker:
                continue

            # Store per-ticker data
            ticker_upper = ticker.upper()
            td["received_at"] = datetime.now(timezone.utc).isoformat()
            td["source_timestamp"] = timestamp
            await client.set(f"uw:ticker:{ticker_upper}", json.dumps(td), ex=TICKER_UPDATE_TTL)
            written += 1

            # Track aggregate stats
            total_premium += float(td.get("total_premium") or 0)
            sentiment = td.get("flow_sentiment")
            if sentiment == "BEARISH":
                bearish_count += 1
            elif sentiment == "BULLISH":
                bullish_count += 1

            if ticker_upper == "SPY":
                spy_data = td
            elif ticker_upper == "QQQ":
                qqq_data = td

            # Check if this ticker qualifies for independent signal creation
            try:
                await _maybe_create_uw_signal(td)
            except Exception as e:
                logger.debug(f"UW signal check failed for {ticker_upper}: {e}")

        # Store aggregate market flow snapshot
        if written > 0:
            market_flow = {
                "timestamp": timestamp,
                "spy_pc_ratio": spy_data["pc_ratio"] if spy_data else None,
                "qqq_pc_ratio": qqq_data["pc_ratio"] if qqq_data else None,
                "total_premium_all": total_premium,
                "bearish_flow_count": bearish_count,
                "bullish_flow_count": bullish_count,
                "ticker_count": written,
            }
            await client.set("uw:market_flow:latest", json.dumps(market_flow), ex=MARKET_FLOW_TTL)

        logger.info("UW ticker updates: cached %s tickers", written)
        return {"status": "success", "cached": written}

    except Exception as e:
        logger.error(f"Error receiving UW ticker updates: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/market-flow")
async def get_uw_market_flow():
    """
    Read the aggregate UW market flow snapshot.
    Used by committee context builder for SPY/QQQ P/C ratios and sentiment.
    """
    client = await get_redis_client()
    if not client:
        return {"status": "error", "available": False}

    data = await client.get("uw:market_flow:latest")
    if data:
        return {"status": "success", "available": True, "flow": json.loads(data)}
    return {"status": "success", "available": False, "flow": None}


@router.get("/ticker/{ticker}")
async def get_uw_ticker(ticker: str):
    """
    Read cached UW Ticker Update data for a specific ticker.
    Used by committee context builder for per-ticker flow data.
    """
    client = await get_redis_client()
    if not client:
        return {"status": "error", "available": False}

    data = await client.get(f"uw:ticker:{ticker.upper()}")
    if data:
        return {"status": "success", "available": True, "ticker_data": json.loads(data)}
    return {"status": "success", "available": False, "ticker_data": None}
