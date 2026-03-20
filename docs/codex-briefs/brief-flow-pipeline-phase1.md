# Brief — Phase 1: UW Flow Data Pipeline (Fix the Missing Endpoint)

**Priority:** HIGH — unblocks all future flow work
**Touches:** `backend/api/flow_ingestion.py` (NEW), `backend/main.py`, `backend/database/postgres_client.py`
**Estimated time:** 1.5–2 hours

---

## Context

The UW Watcher bot has been running on the VPS for weeks, successfully parsing Unusual Whales data from Discord. It POSTs parsed ticker data to `POST /api/uw/ticker-updates` — **an endpoint that was never built.** Every request returns 404:

```
2026-03-19 19:45:29 [WARNING] uw_watcher: Unexpected status: {"detail":"Not Found"}
```

Meanwhile, `flow_summary.py` (the endpoint the Flow tab calls) is already built and working — it reads from Redis keys `uw:flow:*` and aggregates them. But those keys are empty because nothing is writing to them.

This brief builds the missing link: the ingestion endpoint that receives UW Watcher data and writes it to Redis + Postgres.

---

## UW Watcher Payload Format

The bot posts to `POST /api/uw/ticker-updates` with `Authorization: Bearer {PIVOT_API_KEY}`:

```json
{
    "timestamp": "2026-03-20T12:00:00.000000Z",
    "source": "uw_ticker_updates",
    "tickers": [
        {
            "ticker": "AAPL",
            "price": 175.50,
            "change_pct": 0.23,
            "volume": 7360000,
            "pc_ratio": 1.07,
            "put_volume": 743000,
            "call_volume": 698000,
            "total_premium": 320000000,
            "flow_sentiment": "BULLISH",
            "flow_premium": 217000000,
            "flow_pct": 67.8
        }
    ]
}
```

Fields that may be null: `flow_sentiment`, `flow_premium`, `flow_pct` (only present when UW includes the optional emoji flow suffix).

---

## What `flow_summary.py` Expects in Redis

The existing `GET /api/flow/summary` endpoint (already deployed, already called by the Flow tab) scans Redis keys `uw:flow:*` and expects each value to be JSON with:

```json
{
    "ticker": "AAPL",
    "call_premium": 217000000,
    "put_premium": 103000000,
    "sentiment": "BULLISH",
    "unusual_count": 3,
    "last_updated": "2026-03-20T12:00:00Z"
}
```

The ingestion endpoint must transform UW Watcher fields into this format.

---

## Part 1 — New File: `backend/api/flow_ingestion.py`

Create this file:

```python
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
```

---

## Part 2 — Database: Create `flow_events` Table

### File: `backend/database/postgres_client.py`

Add after the `balance_snapshots` table (or after `cash_flows` if the snapshots brief hasn't been built yet). Find the section with other CREATE TABLE statements and add:

```sql
CREATE TABLE IF NOT EXISTS flow_events (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    pc_ratio NUMERIC(5,2),
    call_volume BIGINT,
    put_volume BIGINT,
    total_premium BIGINT,
    call_premium BIGINT,
    put_premium BIGINT,
    flow_sentiment TEXT,
    price NUMERIC(10,2),
    change_pct NUMERIC(6,2),
    volume BIGINT,
    source TEXT DEFAULT 'uw_watcher',
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flow_events_ticker_time ON flow_events(ticker, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_flow_events_time ON flow_events(captured_at DESC);
```

**Also add a cleanup migration** to prevent unbounded table growth. Add after the CREATE:

```sql
DELETE FROM flow_events WHERE captured_at < NOW() - INTERVAL '90 days';
```

This runs on every deploy. For ongoing maintenance, the weekly audit cron can also purge old rows (future enhancement).

---

## Part 3 — Register Router in `main.py`

### File: `backend/main.py`

**Find** the existing flow_summary import (~line 629):
```python
from api.flow_summary import router as flow_summary_router
```

**Add immediately after it:**
```python
from api.flow_ingestion import router as flow_ingestion_router
```

**Find** the existing flow_summary router registration (~line 667):
```python
app.include_router(flow_summary_router, prefix="/api", tags=["flow-summary"])
```

**Add immediately after it:**
```python
app.include_router(flow_ingestion_router, prefix="/api", tags=["uw-flow"])
```

This mounts the new endpoint at `POST /api/uw/ticker-updates` — exactly where the VPS bot already POSTs.

---

## Part 4 — Verification

After deploy, verify end-to-end:

### Step 1: Verify endpoint exists
```bash
curl -s -X POST "https://pandoras-box-production.up.railway.app/api/uw/ticker-updates" \
  -H "Authorization: Bearer $PIVOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tickers":[{"ticker":"TEST","price":100,"pc_ratio":0.8,"total_premium":1000000}]}' | python3 -m json.tool
```

Expected: `{"status":"ok","received":1,"redis_written":1,"pg_written":1}`

### Step 2: Verify Redis populated
```bash
curl -s "https://pandoras-box-production.up.railway.app/api/flow/summary" | python3 -m json.tool
```

Expected: `hot_tickers` should now contain TEST with premium data. Sentiment should populate.

### Step 3: Wait for next UW Watcher post
Check VPS logs after the next UW message arrives (~every 15-30 min during market hours):
```bash
journalctl -u uw-watcher -n 20 --no-pager
```

Expected: `Posted X tickers to Pandora API (status=200)` instead of the current 404.

### Step 4: Verify Flow tab shows data
Open Trading Hub, click the Flow tab. Should now show sentiment gauge with actual P/C data, hot tickers with premium amounts, etc.

### Step 5: Verify Postgres persistence
```sql
SELECT ticker, pc_ratio, total_premium, flow_sentiment, captured_at
FROM flow_events ORDER BY captured_at DESC LIMIT 10;
```

---

## Build Order

| Step | File | What |
|------|------|------|
| 1 | `backend/database/postgres_client.py` | Create `flow_events` table + indexes + cleanup |
| 2 | `backend/api/flow_ingestion.py` | New file — UW ingestion endpoint |
| 3 | `backend/main.py` | Import and register flow_ingestion_router |
| 4 | Deploy + verify | Push, wait for deploy, run verification steps |

---

## What This Unlocks (Not Part of This Brief)

Once data is flowing:
- **Flow tab comes alive immediately** — `flow_summary.py` already aggregates and the frontend already renders it. No frontend changes needed.
- **Phase 2 (future brief):** Flow badges on position cards — read from Redis `uw:flow:{ticker}` for each open position, compare sentiment to position direction, render confirming/counter badge.
- **Phase 3 (future brief):** Radar tab — filter flow data to positions + watchlist only, add flow velocity (is premium accelerating?) using `flow_events` history.

---

## Known Limitations

1. **Premium split is estimated.** UW gives total premium + P/C ratio, not separate call/put premium. We use the P/C ratio as a proxy. When UW includes the explicit flow sentiment + premium suffix (the emoji line), we use that for better accuracy.
2. **UW posts every 15-30 minutes.** Flow data is not real-time — it's a periodic snapshot from Unusual Whales. Sufficient for position monitoring, not for scalping.
3. **Embed messages still skipped.** The UW Watcher currently skips embed-only messages which contain individual large sweeps. Parsing those is a future enhancement that would significantly improve flow signal quality.
4. **No backfill.** Flow data starts accumulating from the moment this deploys. No historical data recovery.

---

## Commit

```
feat: UW flow ingestion endpoint + flow_events table (Phase 1)
```
