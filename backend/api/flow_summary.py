"""
Flow Summary API — aggregated flow dashboard for the Agora UI.
Combines UW flow data (Redis) + recent FLOW_INTEL signals (Postgres)
into a single dashboard-friendly payload.
"""

import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter

from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flow", tags=["flow-summary"])

SUMMARY_CACHE_KEY = "flow:summary"
SUMMARY_CACHE_TTL = 120  # 2 minutes


@router.get("/summary")
async def get_flow_summary():
    """Aggregated flow summary: sentiment gauge, hot tickers, recent signals."""
    redis = await get_redis_client()

    # Check cache
    if redis:
        try:
            cached = await redis.get(SUMMARY_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # --- Aggregate sentiment from UW flow summaries ---
    call_total = 0
    put_total = 0
    hot_tickers = []

    if redis:
        try:
            keys = []
            cursor = b"0"
            while True:
                cursor, batch = await redis.scan(cursor, match="uw:flow:*", count=100)
                keys.extend(
                    k for k in batch
                    if k != b"uw:flow:recent" and k != "uw:flow:recent"
                )
                if cursor == b"0" or cursor == 0:
                    break

            if keys:
                values = await redis.mget(*keys)
                for val in values:
                    if not val:
                        continue
                    try:
                        s = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    cp = s.get("call_premium", 0) or 0
                    pp = s.get("put_premium", 0) or 0
                    call_total += cp
                    put_total += pp
                    ticker = s.get("ticker")
                    if ticker:
                        hot_tickers.append({
                            "ticker": ticker,
                            "total_premium": cp + pp,
                            "direction": s.get("sentiment", "NEUTRAL"),
                            "unusual_count": s.get("unusual_count", 0),
                            "latest_at": s.get("last_updated"),
                        })
        except Exception as e:
            logger.warning("Flow summary Redis scan failed: %s", e)

    # Compute sentiment
    total_premium = call_total + put_total
    if total_premium > 0:
        pc_ratio = round(put_total / max(call_total, 1), 2)
        if pc_ratio < 0.7:
            bias = "BULLISH"
        elif pc_ratio > 1.3:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"
        bias_strength = round(min(1.0, abs(1.0 - pc_ratio)), 2)
    else:
        pc_ratio = 0.0
        bias = "NEUTRAL"
        bias_strength = 0.0

    # Sort hot tickers by total premium descending, top 8
    hot_tickers.sort(key=lambda t: t.get("total_premium", 0), reverse=True)
    hot_tickers = hot_tickers[:8]

    # --- Recent FLOW_INTEL signals from Postgres ---
    recent_signals = []
    try:
        pool = await get_postgres_client()
        if pool:
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT signal_id, ticker, direction, score,
                           signal_category, created_at, metadata
                    FROM signals
                    WHERE signal_category = 'FLOW_INTEL'
                      AND created_at > NOW() - INTERVAL '4 hours'
                    ORDER BY created_at DESC
                    LIMIT 5
                """)
                for row in rows:
                    meta = row.get("metadata") or {}
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except Exception:
                            meta = {}
                    recent_signals.append({
                        "signal_id": row["signal_id"],
                        "ticker": row["ticker"],
                        "direction": row["direction"],
                        "score": row["score"],
                        "total_premium": meta.get("premium") or meta.get("total_premium"),
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    })
    except Exception as e:
        logger.warning("Flow summary Postgres query failed: %s", e)

    result = {
        "sentiment": {
            "call_premium_total": call_total,
            "put_premium_total": put_total,
            "pc_ratio": pc_ratio,
            "bias": bias,
            "bias_strength": bias_strength,
        },
        "hot_tickers": hot_tickers,
        "recent_signals": recent_signals,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Cache
    if redis:
        try:
            await redis.set(SUMMARY_CACHE_KEY, json.dumps(result), ex=SUMMARY_CACHE_TTL)
        except Exception:
            pass

    return result
