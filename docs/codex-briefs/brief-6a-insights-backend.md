# Brief 6A: Insights Quality Overhaul — Backend

**Target Agent:** Claude Code (VSCode)
**Phase:** 6 — Insights Quality
**Depends On:** Nothing (standalone)
**Titans Approved:** March 17, 2026

---

## What This Does

Four backend changes to fix signal noise, duplicate stacking, and add accept/reject lifecycle:
1. Webhook-level dedup via Redis (stops duplicate signals at the source)
2. Grouped Insights query filters out acted-on signals and enforces score threshold
3. Distinct-strategy confluence count replaces raw signal count
4. Accept/reject lifecycle propagates to all signals for that ticker+direction

---

## Step 1: Webhook Dedup via Redis

TradingView webhooks fire every time price crosses a level. Holy Grail, Artemis, and Phalanx can produce 5-10 identical signals per day for the same ticker. The CTA scanner has a `has_recent_active_signal` cooldown but webhooks don't.

### 1A. Create dedup helper

**File:** `backend/utils/signal_dedup.py` (NEW FILE)

```python
"""
Signal Dedup — Redis-based atomic deduplication for webhook signals.

Prevents the same strategy from firing duplicate signals for the same
ticker+direction within a cooldown window. Uses Redis SET NX for
atomicity (no race conditions on rapid-fire webhooks).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cooldown periods by timeframe
DEDUP_COOLDOWN_INTRADAY = 7200    # 2 hours for 1M-1H signals
DEDUP_COOLDOWN_DAILY = 28800      # 8 hours for daily signals
DEDUP_COOLDOWN_DEFAULT = 7200     # 2 hours fallback


def _get_cooldown_seconds(timeframe: str) -> int:
    """Get dedup cooldown based on signal timeframe."""
    tf = (timeframe or "1H").upper()
    if tf in ("D", "1D", "DAILY", "W", "1W", "WEEKLY"):
        return DEDUP_COOLDOWN_DAILY
    return DEDUP_COOLDOWN_INTRADAY


async def is_duplicate_signal(
    ticker: str,
    strategy: str,
    direction: str,
    timeframe: str = "1H",
) -> bool:
    """
    Check if a signal is a duplicate using Redis SET NX.
    Returns True if this is a duplicate (should be skipped).
    Returns False if this is the first signal (proceed to process).

    Atomic: SET NX ensures only one signal wins even under concurrent webhooks.
    """
    try:
        from database.redis_client import get_redis
        redis = await get_redis()

        key = f"dedup:{ticker.upper()}:{strategy.upper()}:{direction.upper()}"
        ttl = _get_cooldown_seconds(timeframe)

        # SET NX: returns True if key was SET (first signal), False if already exists (duplicate)
        was_set = await redis.set(key, "1", ex=ttl, nx=True)

        if was_set:
            logger.debug(f"Dedup: {key} — first signal, proceeding (TTL={ttl}s)")
            return False  # Not a duplicate
        else:
            logger.info(f"Dedup: {key} — duplicate within {ttl}s cooldown, skipping")
            return True  # Is a duplicate

    except Exception as e:
        logger.warning(f"Dedup check failed (allowing signal through): {e}")
        return False  # Fail open — don't block signals if Redis is down
```

### 1B. Wire dedup into TradingView webhook handlers

**File:** `backend/webhooks/tradingview.py`

This is a large file with multiple handler functions. The dedup check needs to be added to EACH handler that processes TradingView webhook signals. Search for all functions that call `process_signal_unified()`:

```
grep -n "process_signal_unified\|async def process_" backend/webhooks/tradingview.py
```

For each handler (e.g., `process_artemis_signal`, `process_holy_grail_signal`, `process_phalanx_signal`, `process_whale_signal`, `process_sell_rip_signal`, `process_generic_signal`, etc.), add the dedup check **after** the signal_data dict is built but **before** calling `process_signal_unified()`.

The pattern to insert in each handler:

```python
    # Dedup check — skip if same ticker+strategy+direction fired recently
    from utils.signal_dedup import is_duplicate_signal
    if await is_duplicate_signal(
        ticker=signal_data.get("ticker", ""),
        strategy=signal_data.get("strategy", ""),
        direction=signal_data.get("direction", ""),
        timeframe=signal_data.get("timeframe", "1H"),
    ):
        logger.info(f"Dedup skip: {signal_data.get('ticker')} {signal_data.get('strategy')}")
        return {"status": "skipped", "reason": "duplicate_within_cooldown"}
```

**Important:**
- Add this to EVERY `process_*_signal()` function in `tradingview.py`
- Do NOT add it to `process_signal_unified()` in `pipeline.py` (other sources like CTA scanner have their own dedup)
- The import can be at the top of the file or inline (inline is safer if the file is large)

---

## Step 2: Improve Grouped Insights Query

**File:** `backend/api/trade_ideas.py`

The existing `/trade-ideas/grouped` endpoint needs three changes:

### 2A. Filter out acted-on signals

**Find this block** in `get_trade_ideas_grouped()`:

```python
    conditions = [
        "status = 'ACTIVE'",
        "(expires_at IS NULL OR expires_at > NOW())",
        "created_at > NOW() - INTERVAL '24 hours'",
    ]
```

**Replace with:**

```python
    conditions = [
        "status = 'ACTIVE'",
        "(expires_at IS NULL OR expires_at > NOW())",
        "created_at > NOW() - INTERVAL '24 hours'",
        "user_action IS NULL",  # Exclude accepted/rejected/dismissed signals
    ]
```

### 2B. Apply default score threshold

The `min_score` parameter already exists but defaults to `None`. Change the default:

**Find:**
```python
async def get_trade_ideas_grouped(
    limit: int = Query(default=20, le=50),
    min_score: Optional[float] = Query(default=None),
):
```

**Replace with:**
```python
async def get_trade_ideas_grouped(
    limit: int = Query(default=20, le=50),
    min_score: Optional[float] = Query(default=70.0),
    show_all: bool = Query(default=False),
):
```

Then **find** the block that applies `min_score`:

```python
    if min_score is not None:
        conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
        params.append(min_score)
        idx += 1
```

**Replace with:**

```python
    effective_min_score = None if show_all else min_score
    if effective_min_score is not None:
        conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
        params.append(effective_min_score)
        idx += 1
```

### 2C. Add `last_signal_at` and `distinct_strategy_count` to group output

The grouped endpoint already tracks `newest_at` and `strategies` list. Make these explicitly available in the output.

**Find** the block where each group is finalized (inside the loop or after dedup). After the line:
```python
        g["strategies"] = strats
```

**Add:**
```python
        g["distinct_strategy_count"] = len(set(s.lower() for s in strats))
        g["last_signal_at"] = g["newest_at"]
```

---

## Step 3: Accept/Reject Lifecycle — Propagate to Group

When Nick accepts or rejects an Insight card, ALL signals for that ticker+direction should be marked accordingly. This prevents new signals from the same setup resurfacing after a decision.

### 3A. Add group action endpoint

**File:** `backend/api/trade_ideas.py`

**Add this new endpoint** after the existing `update_trade_idea_status` function:

```python
class GroupAction(BaseModel):
    action: str  # ACCEPTED or REJECTED
    ticker: str
    direction: str
    reason: Optional[str] = None


@router.post("/trade-ideas/group-action")
async def act_on_trade_idea_group(body: GroupAction, _=Depends(require_api_key)):
    """
    Accept or reject all signals for a ticker+direction group.

    When ACCEPTED: all active signals for this ticker+direction get user_action='SELECTED'.
    When REJECTED: all active signals for this ticker+direction get user_action='DISMISSED'.

    Future signals for this ticker+direction within the dedup window will still persist
    in the DB but won't appear in the Insights feed (filtered by user_action IS NULL).

    A Redis key is set to suppress new Insights for this ticker+direction for 8 hours.
    After 8 hours, if genuinely new signals arrive, the card can reappear.
    """
    pool = await get_postgres_client()
    action = body.action.upper()
    ticker = body.ticker.upper()
    direction = body.direction.upper()

    if action not in ("ACCEPTED", "REJECTED"):
        raise HTTPException(status_code=400, detail="action must be ACCEPTED or REJECTED")

    user_action = "SELECTED" if action == "ACCEPTED" else "DISMISSED"
    timestamp_field = "selected_at" if action == "ACCEPTED" else "dismissed_at"

    async with pool.acquire() as conn:
        result = await conn.execute(
            f"""
            UPDATE signals
            SET user_action = $1,
                {timestamp_field} = NOW(),
                status = CASE WHEN $1 = 'DISMISSED' THEN 'DISMISSED' ELSE status END,
                notes = COALESCE(notes || ' | ', '') || $4
            WHERE UPPER(ticker) = $2
            AND UPPER(direction) = $3
            AND status = 'ACTIVE'
            AND user_action IS NULL
            """,
            user_action,
            ticker,
            direction,
            f"Group {action.lower()} via dashboard",
        )

    # Parse count
    count = 0
    if result:
        parts = result.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            count = int(parts[-1])

    # Set Redis suppression key — prevents this ticker+direction from reappearing for 8 hours
    try:
        from database.redis_client import get_redis
        redis = await get_redis()
        suppress_key = f"insight_acted:{ticker}:{direction}"
        await redis.set(suppress_key, action, ex=28800)  # 8 hours
    except Exception as e:
        logger.warning(f"Failed to set suppression key: {e}")

    logger.info(f"Group {action}: {ticker} {direction} — {count} signals updated")
    return {
        "action": action,
        "ticker": ticker,
        "direction": direction,
        "signals_updated": count,
    }
```

### 3B. Check suppression in grouped query

New signals that arrive after an accept/reject should not create new Insight cards (for 8 hours). Add a post-query filter.

**In `get_trade_ideas_grouped()`**, after the groups are built but before sorting, add:

```python
    # Filter out groups that have been recently acted on (Redis suppression)
    try:
        from database.redis_client import get_redis
        redis = await get_redis()
        suppressed_keys = []
        for key in list(groups_map.keys()):
            ticker, direction = key.split(":")
            suppress_key = f"insight_acted:{ticker}:{direction}"
            if await redis.exists(suppress_key):
                suppressed_keys.append(key)
        for key in suppressed_keys:
            del groups_map[key]
    except Exception as e:
        logger.warning(f"Suppression check failed (showing all groups): {e}")
```

Insert this **after** the dedup loop (`for g in groups_map.values(): g["related_signals"] = ...`) and **before** the composite rank computation (`now = datetime.utcnow()`).

---

## Step 4: Expose Score Factors in Grouped Response

The `triggering_factors` JSON is already stored on each signal. Expose the top factors on the primary signal in each group.

**In `get_trade_ideas_grouped()`**, in the group creation block where `primary_signal` is set, the signal already contains `triggering_factors`. No backend change needed — the frontend just needs to read `primary_signal.triggering_factors`.

However, verify the field is included in `serialize_db_row()`. Search:
```
grep -n "triggering_factors\|serialize_db_row" backend/database/postgres_client.py
```

If `triggering_factors` is a JSONB column, `serialize_db_row` should handle it. If it's being excluded, add it.

---

## Testing Checklist

1. **Webhook dedup:** Send two identical TradingView webhooks within 10 seconds. First should process, second should return `{"status": "skipped", "reason": "duplicate_within_cooldown"}`
2. **Grouped query filter:** After dismissing a signal, `GET /api/trade-ideas/grouped` should NOT show that ticker+direction group
3. **Score threshold:** `GET /api/trade-ideas/grouped` should only return signals scoring >= 70 by default. `GET /api/trade-ideas/grouped?show_all=true` returns all.
4. **Group action:** `POST /api/trade-ideas/group-action` with `{"action": "REJECTED", "ticker": "AAPL", "direction": "LONG"}` should mark all AAPL LONG signals as DISMISSED
5. **Suppression:** After rejecting AAPL LONG, new AAPL LONG signals should not appear in grouped view for 8 hours
6. **Distinct strategies:** A group with 5 Holy Grail signals and 1 Artemis signal should show `distinct_strategy_count: 2`, not `signal_count: 6`
7. **last_signal_at:** Each group should include the timestamp of the most recent signal
8. **Existing tests pass**

## Definition of Done
- [ ] `backend/utils/signal_dedup.py` created with Redis SET NX dedup
- [ ] All TradingView webhook handlers call `is_duplicate_signal()` before `process_signal_unified()`
- [ ] `/trade-ideas/grouped` filters out `user_action IS NOT NULL` signals
- [ ] `/trade-ideas/grouped` defaults to `min_score=70` with `show_all` toggle
- [ ] `/trade-ideas/group-action` endpoint accepts/rejects all signals for a ticker+direction
- [ ] Redis suppression prevents re-surfacing for 8 hours after action
- [ ] `distinct_strategy_count` and `last_signal_at` exposed in group response
- [ ] All existing tests pass
