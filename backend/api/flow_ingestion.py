"""
UW Flow Ingestion — receives parsed Unusual Whales data from the VPS bot
and writes to Redis (live dashboard) + Postgres (historical analysis).
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client
from utils.pivot_auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/uw", tags=["uw-flow"])

REDIS_FLOW_TTL = 21600  # 6 hours — keys expire after market close


class TickerFlowData(BaseModel):
    ticker: str
    price: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    pc_ratio: Optional[float] = None
    put_volume: Optional[int] = None
    call_volume: Optional[int] = None
    total_premium: Optional[int] = None
    flow_sentiment: Optional[str] = None    # BULLISH / BEARISH / None
    flow_premium: Optional[int] = None
    flow_pct: Optional[float] = None


class UWTickerUpdateRequest(BaseModel):
    timestamp: Optional[str] = None
    source: Optional[str] = "uw_ticker_updates"
    tickers: List[TickerFlowData]


@router.post("/ticker-updates")
async def ingest_uw_ticker_updates(req: UWTickerUpdateRequest, _=Depends(require_api_key)):
    """
    Receive parsed UW ticker updates from the VPS watcher bot.
    Writes to:
      1. Redis uw:flow:{ticker} — consumed by GET /api/flow/summary for live dashboard
      2. Postgres flow_events — persistent history for flow velocity analysis
    """
    redis = await get_redis_client()
    pool = await get_postgres_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    redis_written = 0
    pg_written = 0
    errors = []

    for t in req.tickers:
        ticker = t.ticker.upper()

        # --- Derive sentiment if not explicitly provided ---
        sentiment = t.flow_sentiment
        if not sentiment and t.pc_ratio is not None:
            if t.pc_ratio < 0.7:
                sentiment = "BULLISH"
            elif t.pc_ratio > 1.3:
                sentiment = "BEARISH"
            else:
                sentiment = "NEUTRAL"

        # --- Estimate call/put premium split from total ---
        # UW gives total_premium and pc_ratio. We can estimate the split.
        call_premium = 0
        put_premium = 0
        if t.total_premium and t.pc_ratio is not None and t.pc_ratio > 0:
            # pc_ratio = put_vol / call_vol, use as proxy for premium split
            # put_share = pc_ratio / (1 + pc_ratio)
            put_share = t.pc_ratio / (1 + t.pc_ratio)
            put_premium = int(t.total_premium * put_share)
            call_premium = t.total_premium - put_premium
        elif t.total_premium:
            # No pc_ratio — split 50/50
            call_premium = t.total_premium // 2
            put_premium = t.total_premium - call_premium

        # If flow_premium is available with sentiment, use it for more accuracy
        if t.flow_premium and t.flow_sentiment:
            if t.flow_sentiment == "BULLISH":
                call_premium = max(call_premium, t.flow_premium)
            elif t.flow_sentiment == "BEARISH":
                put_premium = max(put_premium, t.flow_premium)

        # --- 1. Write to Redis (format flow_summary.py expects) ---
        if redis:
            try:
                redis_key = f"uw:flow:{ticker}"

                # Read existing to increment unusual_count
                existing_count = 0
                try:
                    existing_raw = await redis.get(redis_key)
                    if existing_raw:
                        existing = json.loads(existing_raw)
                        existing_count = existing.get("unusual_count", 0)
                except Exception:
                    pass

                redis_val = {
                    "ticker": ticker,
                    "call_premium": call_premium,
                    "put_premium": put_premium,
                    "sentiment": sentiment or "NEUTRAL",
                    "unusual_count": existing_count + 1,
                    "last_updated": now_iso,
                    # Extra fields for future use (flow badges, position radar)
                    "pc_ratio": t.pc_ratio,
                    "total_premium": t.total_premium,
                    "price": t.price,
                    "change_pct": t.change_pct,
                    "volume": t.volume,
                    "put_volume": t.put_volume,
                    "call_volume": t.call_volume,
                    "flow_pct": t.flow_pct,
                }
                await redis.set(redis_key, json.dumps(redis_val), ex=REDIS_FLOW_TTL)
                redis_written += 1
            except Exception as e:
                errors.append({"ticker": ticker, "target": "redis", "error": str(e)})
                logger.warning("Redis write failed for %s: %s", ticker, e)

        # --- 2. Write to Postgres flow_events (persistent history) ---
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO flow_events
                            (ticker, pc_ratio, call_volume, put_volume, total_premium,
                             call_premium, put_premium, flow_sentiment, price, change_pct,
                             volume, source, captured_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                    """,
                        ticker,
                        t.pc_ratio,
                        t.call_volume,
                        t.put_volume,
                        t.total_premium,
                        call_premium,
                        put_premium,
                        sentiment,
                        t.price,
                        t.change_pct,
                        t.volume,
                        "uw_watcher",
                    )
                pg_written += 1
            except Exception as e:
                errors.append({"ticker": ticker, "target": "postgres", "error": str(e)})
                logger.warning("Postgres write failed for %s: %s", ticker, e)

    logger.info(
        "UW ingestion: %d tickers received, %d Redis, %d Postgres, %d errors",
        len(req.tickers), redis_written, pg_written, len(errors),
    )

    # === Flow-to-Signal Promotion (Whale Hunter Replacement) ===
    # When a UW flow event exceeds the premium threshold, create a DARK_POOL
    # signal in the signals table so it appears as a trade idea card.
    promoted = 0
    for t in req.tickers:
        if not t.ticker or not t.flow_sentiment:
            continue

        premium = t.total_premium or 0
        # Configurable threshold — check Redis first, fall back to default
        try:
            threshold_raw = redis and await redis.get("config:uw_flow:signal_threshold")
            threshold = int(threshold_raw) if threshold_raw else 1_000_000
        except Exception:
            threshold = 1_000_000  # $1M default

        if premium < threshold:
            continue

        # Check cooldown — don't re-promote same ticker+direction within 4 hours
        direction = "LONG" if t.flow_sentiment == "BULLISH" else "SHORT"
        cooldown_key = f"signal:cooldown:{t.ticker.upper()}:UW_FLOW:{direction}"
        try:
            if redis and await redis.get(cooldown_key):
                continue
            if redis:
                await redis.set(cooldown_key, "1", ex=14400)  # 4 hour cooldown
        except Exception:
            pass

        # Build signal data for the unified pipeline
        premium_display = f"${premium/1_000_000:.1f}M" if premium >= 1_000_000 else f"${premium/1_000:.0f}K"
        signal_data = {
            "ticker": t.ticker.upper(),
            "strategy": "UW_FLOW",
            "direction": direction,
            "signal_type": "DARK_POOL",
            "signal_category": "DARK_POOL",
            "entry_price": t.price or 0,
            "timeframe": "flow",
            "source": "uw_watcher",
            "asset_class": "EQUITY",
            "metadata": {
                "total_premium": premium,
                "premium_display": premium_display,
                "flow_sentiment": t.flow_sentiment,
                "pc_ratio": t.pc_ratio,
                "put_volume": t.put_volume,
                "call_volume": t.call_volume,
                "volume": t.volume,
            },
        }

        try:
            from signals.pipeline import process_signal_unified
            import asyncio
            asyncio.ensure_future(process_signal_unified(signal_data, source="uw_flow"))
            promoted += 1
            logger.info(
                "UW flow promoted to DARK_POOL signal: %s %s (%s premium)",
                t.ticker.upper(), direction, premium_display,
            )
        except Exception as e:
            logger.warning("Failed to promote UW flow to signal: %s", e)

    return {
        "status": "ok",
        "received": len(req.tickers),
        "redis_written": redis_written,
        "pg_written": pg_written,
        "signals_promoted": promoted,
        "errors": errors[:5] if errors else [],
    }
