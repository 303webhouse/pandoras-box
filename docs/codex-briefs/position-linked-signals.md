# Codex Brief: Position-Linked Signal Tagging

**Priority:** High — Signals for tickers with open positions are being silently suppressed  
**Scope:** Backend pipeline + positions API + frontend position cards  
**Risk:** Low — additive feature, no existing behavior changes except suppression logic  

---

## Problem

When a signal fires for a ticker that already has an open position, it is completely suppressed — the user never sees it. Both confirming signals (same direction as position) and counter signals (opposite direction) are dropped silently.

Counter-signal storage already half-exists (Redis key + position card banner) but is only set from the OLD `positions.py`, not the main signal pipeline. Confirming signals have zero support anywhere.

## Desired Behavior

When a signal fires for a ticker with an open position:
1. The signal should NOT appear in the Insights tab (current suppression is fine)
2. Instead, it should be tagged onto the open position card as either:
   - **CONFIRMING SIGNAL** (signal direction aligns with position direction)
   - **COUNTER SIGNAL** (signal direction opposes position direction)
3. The position card should display the signal with strategy name, score, and timestamp
4. Multiple signals can accumulate — show the most recent of each type

---

## Architecture

### Data Flow

```
Signal arrives → pipeline scores it → check unified_positions for open ticker
  → Match found?
    → Same direction: store as confirming_signal:{TICKER} in Redis (4h TTL)
    → Opposite direction: store as counter_signal:{TICKER} in Redis (4h TTL)
    → No match: proceed normally to Insights
```

---

## File Changes

### 1. Backend: `backend/signals/pipeline.py`

**What:** Add step 4e after score_v2 computation — check for open positions and store signal on position.

**Find this anchor (around line 395):**
```python
    # 5. Cache in Redis
    try:
        await cache_signal(signal_data["signal_id"], signal_data, ttl=cache_ttl)
```

**Insert BEFORE that block:**
```python
    # 4e. Tag signal to open position if ticker has one
    try:
        await _maybe_tag_position_signal(signal_data)
    except Exception as e:
        logger.warning(f"Position signal tagging failed (non-blocking): {e}")
```

**Add this function near the top of the file (after the existing helper functions, around line 130):**
```python
async def _maybe_tag_position_signal(signal_data: Dict[str, Any]) -> None:
    """
    Check if signal ticker has an open position. If so, store the signal
    in Redis as either a confirming or counter signal on that position.
    The signal is NOT suppressed from the DB — it still gets logged — but
    the grouped Insights endpoint naturally excludes it via the existing
    WebSocket suppression in the frontend.
    """
    ticker = (signal_data.get("ticker") or "").upper()
    if not ticker:
        return

    sig_direction = (signal_data.get("direction") or "").upper()
    if not sig_direction:
        return

    # Check unified_positions for an open position with this ticker
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT position_id, direction FROM unified_positions WHERE ticker = $1 AND status = 'OPEN' LIMIT 1",
                ticker,
            )
    except Exception as e:
        logger.debug(f"Position lookup failed for {ticker}: {e}")
        return

    if not row:
        return

    pos_direction = (row["direction"] or "").upper()
    bullish = {"LONG", "BULLISH", "BUY"}
    bearish = {"SHORT", "BEARISH", "SELL"}
    same_direction = (
        (pos_direction in bullish and sig_direction in bullish)
        or (pos_direction in bearish and sig_direction in bearish)
    )

    signal_summary = {
        "signal_id": signal_data.get("signal_id"),
        "ticker": ticker,
        "direction": signal_data.get("direction"),
        "strategy": signal_data.get("strategy"),
        "score": signal_data.get("score_v2") or signal_data.get("score"),
        "signal_type": signal_data.get("signal_type"),
        "timeframe": signal_data.get("timeframe"),
        "timestamp": signal_data.get("timestamp") or datetime.utcnow().isoformat(),
        "position_id": row["position_id"],
    }

    import json
    from database.redis_client import get_redis_client
    redis = await get_redis_client()
    if not redis:
        return

    ttl = 14400  # 4 hours

    if same_direction:
        key = f"confirming_signal:{ticker}"
        label = "confirming"
    else:
        key = f"counter_signal:{ticker}"
        label = "counter"

    await redis.set(key, json.dumps(signal_summary), ex=ttl)
    logger.info(f"{'✅' if same_direction else '⚠️'} {label.title()} signal tagged to position: {ticker} {sig_direction} vs open {pos_direction}")
```

---

### 2. Backend: `backend/api/unified_positions.py`

**What:** In the `list_positions` endpoint, also read `confirming_signal:{ticker}` from Redis (counter_signal is already read).

**Find this anchor (around line 593):**
```python
    # Attach counter-signal warnings from Redis for open positions
    if status.upper() == "OPEN":
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis:
                for p in positions:
                    ticker = (p.get("ticker") or "").upper()
                    if ticker:
                        raw = await redis.get(f"counter_signal:{ticker}")
                        if raw:
                            p["counter_signal"] = json.loads(raw)
        except Exception as e:
            logger.warning(f"Failed to attach counter-signals: {e}")
```

**Replace with:**
```python
    # Attach confirming-signal and counter-signal data from Redis for open positions
    if status.upper() == "OPEN":
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis:
                for p in positions:
                    ticker = (p.get("ticker") or "").upper()
                    if ticker:
                        raw_counter = await redis.get(f"counter_signal:{ticker}")
                        if raw_counter:
                            p["counter_signal"] = json.loads(raw_counter)
                        raw_confirming = await redis.get(f"confirming_signal:{ticker}")
                        if raw_confirming:
                            p["confirming_signal"] = json.loads(raw_confirming)
        except Exception as e:
            logger.warning(f"Failed to attach position signals: {e}")
```

---

### 3. Frontend: `frontend/app.js`

**What:** Add confirming signal banner to position cards (counter banner already exists).

**Find this anchor (around line 8327 — inside the position card render function):**
```javascript
    // Counter-signal warning
    let counterBanner = '';
    if (pos.counter_signal) {
```

**Insert BEFORE that block:**
```javascript
    // Confirming signal indicator
    let confirmingBanner = '';
    if (pos.confirming_signal) {
        const cs = pos.confirming_signal;
        let csTime = '';
        if (cs.timestamp) {
            try {
                const csDate = new Date(cs.timestamp);
                const csMin = Math.round((Date.now() - csDate.getTime()) / 60000);
                csTime = csMin < 1 ? 'just now' : csMin < 60 ? `${csMin}m ago` : `${Math.round(csMin / 60)}h ago`;
            } catch(e) {}
        }
        confirmingBanner = `
            <div class="confirming-signal-banner">
                Confirming: ${cs.direction || '?'} ${formatStrategyName(cs.strategy)} (score: ${cs.score || 'N/A'})${csTime ? ` <span class="confirming-signal-time">${csTime}</span>` : ''}
            </div>`;
    }
```

**Then find the position card HTML template (a few lines below, around line 8345):**
```javascript
            ${counterBanner}
            ${strikeLine}
```

**Replace with:**
```javascript
            ${confirmingBanner}
            ${counterBanner}
            ${strikeLine}
```

---

### 4. Frontend: `frontend/styles.css`

**What:** Add CSS for the confirming signal banner (counter-signal styles already exist).

**Find this anchor (search for `.counter-signal-warning`):**
```css
.counter-signal-warning {
```

**Add AFTER the entire `.counter-signal-warning` block and its children:**
```css
.confirming-signal-banner {
    background: rgba(76, 175, 80, 0.12);
    border-left: 3px solid #4CAF50;
    color: #7CFF6B;
    padding: 4px 8px;
    font-size: 11px;
    margin: 4px 0;
    border-radius: 0 4px 4px 0;
}
.confirming-signal-banner .confirming-signal-time {
    color: var(--text-secondary);
    font-size: 10px;
    margin-left: 6px;
}
```

---

### 5. Frontend: `frontend/app.js` — WebSocket handler

**What:** Both `handleNewSignal()` and `handlePrioritySignal()` already suppress signals for open position tickers and call `loadOpenPositionsEnhanced()` for counter signals. Extend them to ALSO refresh positions for confirming signals.

**Find this anchor (around line 1091):**
```javascript
    const matchingPos = openPositions.find(p => (p.ticker || '').toUpperCase() === sigTicker);
    if (matchingPos) {
        if (!isDirectionAligned(matchingPos.direction, signalData.direction)) {
            // Counter-signal — refresh positions to show warning banner
            loadOpenPositionsEnhanced();
        }
        return;
    }
```

**Replace with:**
```javascript
    const matchingPos = openPositions.find(p => (p.ticker || '').toUpperCase() === sigTicker);
    if (matchingPos) {
        // Signal matches an open position — refresh cards to show confirming/counter banner
        loadOpenPositionsEnhanced();
        return;
    }
```

**Do the same replacement for `handlePrioritySignal()` (around line 1135) — it has identical logic.**

---

## Testing

1. Open a position for any ticker (e.g., XLE LONG)
2. Send a test webhook for XLE LONG — should appear as confirming banner on position card
3. Send a test webhook for XLE SHORT — should appear as counter banner on position card
4. Neither signal should appear in the Insights tab
5. Verify signals still appear in Insights for tickers WITHOUT open positions

**Test webhook command:**
```bash
curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"ticker":"XLE","strategy":"Artemis","direction":"LONG","timeframe":"1H"}'
```

---

## Notes

- The pipeline position check is a single SELECT query — negligible latency impact
- Redis TTL of 4 hours means signals naturally expire from position cards
- Both confirming and counter signals can coexist on the same position card
- The old `positions.py` counter-signal setter can remain — it's redundant but harmless since the pipeline now handles it
- This does NOT change how signals are persisted to PostgreSQL — they still get full lifecycle tracking
