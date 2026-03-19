# Codex Brief: Conflicting Signal Auto-Clear (Option B)

**Priority:** High — contradictory signals are cluttering the Insights feed  
**Scope:** Backend pipeline only (`signals/pipeline.py`)  
**Risk:** Low — additive check, signals are still logged to DB for backtesting  

---

## Problem

When two strategies disagree on direction for the same ticker (e.g., Artemis says LONG XLE, then Sell the Rip says SHORT XLE), both appear as separate Insight cards. This creates confusion — neither is a clean, high-conviction setup.

## Desired Behavior

When a new signal arrives for a ticker that already has an ACTIVE signal in the **opposite direction**:
1. The new signal is still **logged to PostgreSQL** (for backtesting / audit trail)
2. Both the existing signal(s) AND the new signal are **auto-dismissed**
3. Both get `notes` explaining the conflict
4. The new signal is **NOT broadcast** via WebSocket and **NOT flagged** for committee
5. Neither signal appears in the Insights tab

Same-direction signals (confirming) should pass through normally — no change to that behavior.

---

## File Changes

### `backend/signals/pipeline.py`

**What:** Add a conflict-detection step after the signal is persisted but before broadcast/committee.

#### Step 1: Add the conflict-check function

Insert this function near the other helper functions (after `_maybe_tag_position_signal`, around line 340):

```python
async def _check_and_clear_conflicting_signals(signal_data: Dict[str, Any]) -> bool:
    """
    Check if an ACTIVE signal exists for this ticker in the OPPOSITE direction.
    If so, dismiss BOTH the existing signal(s) and the new signal.
    
    Returns True if conflict was found and signals were cleared (caller should
    skip broadcast/committee). Returns False if no conflict.
    """
    ticker = (signal_data.get("ticker") or "").upper()
    sig_direction = (signal_data.get("direction") or "").upper()
    new_signal_id = signal_data.get("signal_id")
    
    if not ticker or not sig_direction or not new_signal_id:
        return False
    
    bullish = {"LONG", "BULLISH", "BUY"}
    bearish = {"SHORT", "BEARISH", "SELL"}
    
    if sig_direction in bullish:
        opposite_dirs = list(bearish)
    elif sig_direction in bearish:
        opposite_dirs = list(bullish)
    else:
        return False
    
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # Find active signals for same ticker, opposite direction
            rows = await conn.fetch(
                """
                SELECT signal_id, direction, strategy
                FROM signals
                WHERE UPPER(ticker) = $1
                AND UPPER(direction) = ANY($2)
                AND status = 'ACTIVE'
                AND user_action IS NULL
                AND created_at > NOW() - INTERVAL '24 hours'
                AND signal_id != $3
                """,
                ticker,
                opposite_dirs,
                new_signal_id,
            )
            
            if not rows:
                return False
            
            # Conflict found — dismiss all existing opposite-direction signals
            existing_ids = [row["signal_id"] for row in rows]
            existing_strategies = [row["strategy"] for row in rows]
            all_ids = existing_ids + [new_signal_id]
            
            conflict_note = (
                f"Auto-cleared: conflicting signals on {ticker}. "
                f"Existing {rows[0]['direction']} ({', '.join(existing_strategies)}) "
                f"vs incoming {sig_direction} ({signal_data.get('strategy', '?')}). "
                f"Neither thesis is clean — both dismissed."
            )
            
            await conn.execute(
                """
                UPDATE signals
                SET status = 'DISMISSED',
                    user_action = 'DISMISSED',
                    dismissed_at = NOW(),
                    notes = CASE
                        WHEN notes IS NULL OR notes = '' THEN $2
                        ELSE notes || ' | ' || $2
                    END
                WHERE signal_id = ANY($1)
                AND status = 'ACTIVE'
                """,
                all_ids,
                conflict_note,
            )
            
            logger.info(
                f"\u2694\ufe0f Conflicting signals cleared for {ticker}: "
                f"{len(existing_ids)} existing {rows[0]['direction']} + "
                f"1 incoming {sig_direction} — all dismissed"
            )
            return True
            
    except Exception as e:
        logger.warning(f"Conflict check failed for {ticker} (non-blocking): {e}")
        return False
```

#### Step 2: Call the conflict check in the pipeline

Find this anchor (around line 456, after score_v2 computation):

```python
    # 5. Cache in Redis
    try:
        await cache_signal(signal_data["signal_id"], signal_data, ttl=cache_ttl)
```

Insert BEFORE that block:

```python
    # 4f. Check for conflicting signals (opposite direction, same ticker)
    # If conflict found, both signals are auto-dismissed — skip broadcast/committee
    try:
        conflict_cleared = await _check_and_clear_conflicting_signals(signal_data)
        if conflict_cleared:
            signal_data["status"] = "DISMISSED"
            signal_data["conflict_cleared"] = True
            elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000
            logger.info(
                f"\u2694\ufe0f Pipeline short-circuit: {signal_data.get('ticker')} "
                f"conflicting signal cleared in {elapsed_ms:.1f}ms"
            )
            return signal_data
    except Exception as e:
        logger.warning(f"Conflict check failed (non-blocking): {e}")
```

**Important:** This goes AFTER `log_signal()` (step 4) and AFTER score_v2 (step 4d), but BEFORE cache/broadcast/committee (steps 5-7). The signal is already in the database for backtesting — we're just preventing it from appearing in the Insights feed and skipping downstream processing.

---

## Testing

1. Send a LONG signal for a test ticker:
```bash
curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"ticker":"TEST123","strategy":"Artemis","direction":"LONG","timeframe":"1H"}'
```

2. Verify it appears in Insights (give it a few seconds)

3. Send a SHORT signal for the same ticker:
```bash
curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"ticker":"TEST123","strategy":"sell_the_rip","direction":"SHORT","timeframe":"daily"}'
```

4. Verify BOTH signals disappear from Insights
5. Check DB: both should have `status='DISMISSED'`, `user_action='DISMISSED'`, and conflict note in `notes`

---

## Notes

- Only checks ACTIVE signals with `user_action IS NULL` (won't conflict with already-accepted positions)
- Only looks at signals from the last 24 hours (matches the Insights window)
- The new signal IS persisted first via `log_signal()` — both sides of the conflict exist in the DB for backtesting
- Same-direction signals are unaffected — they still stack as confirming
- The `conflict_cleared` flag on signal_data lets downstream code know this signal was auto-cleared if needed
