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

    result = {
        "status": "ok",
        "received": len(req.tickers),
        "redis_written": redis_written,
        "pg_written": pg_written,
    }
    if errors:
        result["errors"] = errors
    return result
