# Brief: Phase B — Build Confluence Engine

**Priority:** HIGH — Week 1 of the approved build plan. Start immediately.
**Target:** Railway backend (`backend/`)
**Estimated time:** 3-5 days
**Depends on:** Nothing (uses existing 332 signals already in pipeline)

---

## What It Does

A background task that runs every 15 minutes during market hours. It groups active trade ideas by `ticker + direction`, checks if multiple INDEPENDENT analytical lenses agree, and assigns confluence tiers:

- **STANDALONE:** 1 lens (default, no change)
- **CONFIRMED:** 2+ different lenses agree on same ticker + direction within 4-hour window
- **CONVICTION:** 3+ lenses converge, OR 2 lenses + quality gate (Scout score ≥5, or Holy Grail ADX ≥30)

## Lens Categories

This is the critical business logic. Strategies are grouped by what they measure — two signals from the SAME lens are redundant, not confirming.

```python
LENS_MAP = {
    # Strategy name → lens category
    "CTA Scanner": "TREND_STRUCTURE",
    "Holy_Grail": "MOMENTUM_CONTINUATION",  # Adjacent to TREND — counts as CONFIRMED but reduced weight for CONVICTION
    "Sniper": "MEAN_REVERSION",             # Hub Sniper (VWAP bands)
    "ScoutSniper": "REVERSAL_DETECTION",
    "Scout": "REVERSAL_DETECTION",           # Alternate name in pipeline
    "Exhaustion": "REVERSAL_DETECTION",      # Same lens as Scout — complementary, not redundant
    "Whale": "INSTITUTIONAL_FOOTPRINT",
    "absorption_wall": "ORDER_FLOW_BALANCE",
    "UW": "OPTIONS_FLOW",
}

# Sub-types within CTA Scanner are all ONE lens
# PULLBACK_ENTRY, RESISTANCE_REJECTION, TWO_CLOSE_VOLUME, GOLDEN_TOUCH,
# TRAPPED_SHORTS, TRAPPED_LONGS, BEARISH_BREAKDOWN = all TREND_STRUCTURE

# Adjacent lenses: CTA (TREND_STRUCTURE) + Holy Grail (MOMENTUM_CONTINUATION)
# count as CONFIRMED but NOT as 2 independent lenses toward CONVICTION.
ADJACENT_LENSES = {
    frozenset({"TREND_STRUCTURE", "MOMENTUM_CONTINUATION"}),
    frozenset({"MEAN_REVERSION", "TREND_STRUCTURE"}),  # CTA TWO_CLOSE_VOLUME overlap
}
```

## Database Schema Changes

Add columns to the `trade_ideas` table (or whatever table stores active signals in Postgres):

```sql
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS confluence_tier VARCHAR(20) DEFAULT 'STANDALONE';
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS confluence_signals TEXT[];  -- array of signal_ids
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS confluence_lenses TEXT[];  -- array of lens names
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS confluence_count INTEGER DEFAULT 0;
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS confluence_updated_at TIMESTAMP;
```

## Background Task

Add to `backend/main.py` lifespan, similar to existing `signal_expiry_loop()`:

```python
async def confluence_engine_loop():
    """Group active signals by ticker+direction, assign confluence tiers every 15 min."""
    import pytz
    from datetime import datetime as dt_cls
    
    while True:
        try:
            et = dt_cls.now(pytz.timezone("America/New_York"))
            # Only run during market hours (9:30 AM - 4:30 PM ET, weekdays)
            if et.weekday() < 5 and 9 <= et.hour < 17:
                from confluence.engine import run_confluence_scan
                result = await run_confluence_scan()
                if result.get("updated", 0) > 0:
                    logger.info("🔗 Confluence: %d signals updated (%d CONFIRMED, %d CONVICTION)",
                               result["updated"], result.get("confirmed", 0), result.get("conviction", 0))
            else:
                logger.debug("Confluence engine: outside market hours, skipping")
        except Exception as e:
            logger.warning("Confluence engine error: %s", e)
        await asyncio.sleep(900)  # 15 minutes

confluence_task = asyncio.create_task(confluence_engine_loop())
```

## Core Engine Logic

Create `backend/confluence/engine.py`:

```python
async def run_confluence_scan() -> dict:
    """
    1. Query all active signals from last 4 hours
    2. Group by (ticker, direction)
    3. For each group, determine unique lenses
    4. Assign tier: STANDALONE / CONFIRMED / CONVICTION
    5. Update signals with confluence metadata
    6. Broadcast via WebSocket
    7. Post Discord alerts for CONFIRMED/CONVICTION
    """
    from database.postgres_client import get_postgres_client
    from datetime import datetime, timedelta
    import pytz
    
    et_now = datetime.now(pytz.timezone("America/New_York"))
    cutoff = et_now - timedelta(hours=4)
    
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Fetch active signals from last 4 hours
        rows = await conn.fetch("""
            SELECT id, signal_id, ticker, direction, strategy, signal_type,
                   score, timestamp, confidence
            FROM trade_ideas
            WHERE timestamp >= $1
              AND status = 'ACTIVE'
            ORDER BY ticker, direction, timestamp
        """, cutoff)
    
    if not rows:
        return {"updated": 0}
    
    # Group by (ticker, direction)
    groups = {}
    for row in rows:
        key = (row["ticker"], row["direction"])
        if key not in groups:
            groups[key] = []
        groups[key].append(dict(row))
    
    updated = 0
    confirmed_count = 0
    conviction_count = 0
    
    for (ticker, direction), signals in groups.items():
        if len(signals) < 2:
            continue
        
        # Determine unique lenses
        lenses = set()
        for sig in signals:
            strategy = sig.get("strategy", "")
            lens = LENS_MAP.get(strategy, "UNKNOWN")
            if lens != "UNKNOWN":
                lenses.add(lens)
        
        if len(lenses) < 2:
            continue  # Same lens = redundant, not confirming
        
        # Check for adjacent lens pairs
        independent_count = count_independent_lenses(lenses)
        
        # Determine tier
        if independent_count >= 3:
            tier = "CONVICTION"
            conviction_count += 1
        elif independent_count >= 2:
            # Check quality gates for CONVICTION upgrade
            has_quality_gate = any(
                (sig.get("score", 0) >= 5 and LENS_MAP.get(sig.get("strategy"), "") == "REVERSAL_DETECTION") or
                (sig.get("adx", 0) >= 30 and LENS_MAP.get(sig.get("strategy"), "") == "MOMENTUM_CONTINUATION")
                for sig in signals
            )
            if has_quality_gate:
                tier = "CONVICTION"
                conviction_count += 1
            else:
                tier = "CONFIRMED"
                confirmed_count += 1
        else:
            continue  # Adjacent lenses only = weak confirmation
        
        # Update all signals in this group
        signal_ids = [sig["signal_id"] for sig in signals]
        lens_list = sorted(lenses)
        
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE trade_ideas
                SET confluence_tier = $1,
                    confluence_signals = $2,
                    confluence_lenses = $3,
                    confluence_count = $4,
                    confluence_updated_at = NOW()
                WHERE signal_id = ANY($5)
            """, tier, signal_ids, lens_list, len(lenses), signal_ids)
        
        updated += len(signals)
        
        # Discord notification
        if tier in ("CONFIRMED", "CONVICTION"):
            await post_confluence_discord(ticker, direction, tier, signals, lens_list)
    
    # Broadcast via WebSocket
    if updated > 0:
        from websocket.broadcaster import manager
        await manager.broadcast({
            "type": "confluence_update",
            "updated": updated,
            "confirmed": confirmed_count,
            "conviction": conviction_count,
        })
    
    return {
        "updated": updated,
        "confirmed": confirmed_count,
        "conviction": conviction_count,
    }


def count_independent_lenses(lenses: set) -> int:
    """Count truly independent lenses, treating adjacent pairs as 1."""
    lens_list = sorted(lenses)
    independent = len(lens_list)
    
    for adj_pair in ADJACENT_LENSES:
        if adj_pair.issubset(lenses):
            independent -= 1  # Adjacent pair counts as 1, not 2
    
    return independent
```

## Discord Notification

Create `backend/confluence/discord.py`:

```python
async def post_confluence_discord(ticker, direction, tier, signals, lenses):
    """Post a confluence alert to #📊-signals Discord channel."""
    import aiohttp
    import os
    
    webhook_url = os.environ.get("DISCORD_SIGNALS_WEBHOOK")
    if not webhook_url:
        return
    
    emoji = "🔗" if tier == "CONFIRMED" else "🔥"
    color = 0x3b82f6 if tier == "CONFIRMED" else 0xef4444
    
    strategies = [sig.get("strategy", "?") for sig in signals]
    scores = [sig.get("score", 0) for sig in signals]
    
    embed = {
        "title": f"{emoji} {tier}: {ticker} {direction}",
        "color": color,
        "fields": [
            {"name": "Lenses", "value": " + ".join(lenses), "inline": False},
            {"name": "Strategies", "value": ", ".join(strategies), "inline": True},
            {"name": "Scores", "value": ", ".join(str(s) for s in scores), "inline": True},
            {"name": "Signals", "value": str(len(signals)), "inline": True},
        ],
        "footer": {"text": f"Confluence Engine • 4-hour window"}
    }
    
    async with aiohttp.ClientSession() as session:
        await session.post(webhook_url, json={"embeds": [embed]})
```

## API Endpoint

Add to an existing router or create `backend/api/confluence.py`:

```python
@router.get("/confluence/active")
async def get_active_confluence():
    """Return currently active CONFIRMED/CONVICTION signals."""
    from database.postgres_client import get_postgres_client
    from datetime import datetime, timedelta
    import pytz
    
    et_now = datetime.now(pytz.timezone("America/New_York"))
    cutoff = et_now - timedelta(hours=4)
    
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT signal_id, ticker, direction, strategy, signal_type,
                   score, confluence_tier, confluence_lenses, confluence_count,
                   timestamp
            FROM trade_ideas
            WHERE confluence_tier IN ('CONFIRMED', 'CONVICTION')
              AND timestamp >= $1
            ORDER BY 
                CASE confluence_tier WHEN 'CONVICTION' THEN 1 WHEN 'CONFIRMED' THEN 2 END,
                confluence_count DESC
        """, cutoff)
    
    return {
        "confluence_signals": [dict(r) for r in rows],
        "count": len(rows),
    }
```

## File Structure

```
backend/
├── confluence/
│   ├── __init__.py
│   ├── engine.py          ← Core confluence logic
│   ├── discord.py         ← Discord notifications
│   └── lenses.py          ← LENS_MAP + ADJACENT_LENSES constants
├── api/
│   └── confluence.py      ← API endpoint (optional, for frontend)
└── main.py                ← Add confluence_engine_loop() to lifespan
```

## Validation

After deploying to Railway (auto-deploy on push to main):

1. Check Railway logs for: `🔗 Confluence:` messages every 15 min during market hours
2. Query the API: `curl https://pandoras-box-production.up.railway.app/api/confluence/active`
3. Check Postgres: `SELECT confluence_tier, count(*) FROM trade_ideas WHERE confluence_tier != 'STANDALONE' GROUP BY confluence_tier`

With 332 existing signals, there SHOULD be some natural confluence events already in the data. If zero confluence is found, check:
- Are signals from different strategies hitting the same tickers?
- Is the 4-hour window too tight? (Try expanding to 8 hours for initial testing)
- Are the strategy names in the data matching the LENS_MAP keys?

## Important Notes

- The `trade_ideas` table name and column names may differ from what's shown here. Check `backend/api/trade_ideas.py` and `backend/database/postgres_client.py` for the actual schema.
- The Discord webhook URL env var (`DISCORD_SIGNALS_WEBHOOK`) needs to be set on Railway. Check if a similar var already exists.
- Don't modify any existing signal generation logic. The confluence engine is READ-ONLY on signal data — it only ADDS metadata (tier, lenses, count).
- The WebSocket broadcast type `confluence_update` is new — the frontend won't use it yet, but it's ready for when we add confluence badges.
