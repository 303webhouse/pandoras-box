# Brief 4A — Abacus Backend Fixes & Additions

**Target:** Claude Code (VSCode)
**Phase:** 4 (Knowledge Base Cleanup / Abacus Rebuild)
**Depends on:** Nothing — can start immediately
**Estimated scope:** 7 backend additions/fixes across 4-5 files

---

## Context

The Abacus analytics system (Phase 3) has a functional backend but several critical gaps discovered during a March 15 database audit:

- **Oracle is dead:** `system_health` returns 0 trades/0 P&L despite 111 real trades existing. The outcome tracker job has `last_run: null` — it has never executed.
- **No signal-to-trade linking:** 70 of 111 trades have `signal_source = NULL`. Only 2 are tagged "SIGNAL".
- **No cash flows tracking:** No table, no endpoint, no code. Withdrawals are untracked.
- **No bias history logging:** `bias_history` and `bias_composite_history` tables don't exist. Can't measure bias accuracy without historical record.
- **Price collector stopped:** `price_history` newest entry is Feb 22 — 3 weeks stale. Factor accuracy computations return 0.0 for all factors.
- **Factor performance accuracy is all zeros:** Because price_history is stale, the SPY next-day comparison has no data.

This brief addresses 7 backend items. The frontend rebuild (Brief 4B) depends on items 1, 3, and 4 being complete.

---

## Item 1: Proximity Attribution

**What:** When a trade is opened or closed on ticker X, check if any signal arrived for ticker X in the preceding 6 hours. If yes, create a soft link.

**New file:** `backend/analytics/proximity_attribution.py`

```python
"""
Proximity Attribution — soft-links trades to signals by ticker + time window.

Three attribution types:
- proximity_open: Signal arrived within 6h before trade was opened
- proximity_exit: Signal arrived within 6h before trade was closed (countertrend)
- committee: Trade was opened after committee review (existing path)

Runs:
1. On every trade create/close (called from unified_positions.py)
2. Retroactive backfill of all existing trades (one-time migration)
"""
```

**Core function signatures:**

```python
async def attribute_trade(trade_id: int, ticker: str, action: str, timestamp: datetime, window_hours: int = 6) -> Optional[dict]:
    """
    Check signals table for any signal matching this ticker within window_hours before timestamp.
    
    action: 'open' or 'close'
    
    Returns: {signal_id, strategy, score, attribution_type, time_delta_minutes} or None
    """
    # Query: SELECT id, strategy, score, created_at FROM signals
    #        WHERE UPPER(ticker) = UPPER($1)
    #        AND created_at BETWEEN ($2 - interval '{window_hours} hours') AND $2
    #        ORDER BY created_at DESC LIMIT 1
    #
    # If match found:
    #   attribution_type = 'proximity_open' if action == 'open' else 'proximity_exit'
    #   UPDATE trades SET signal_source = strategy, linked_signal_id = signal_id,
    #                      attribution_type = attribution_type
    #   WHERE id = trade_id


async def backfill_all_attributions(window_hours: int = 6) -> dict:
    """
    One-time retroactive scan of all trades with signal_source IS NULL.
    Returns: {total_scanned, attributed, unmatched}
    """
```

**Database changes — add columns to `trades` table:**

```sql
ALTER TABLE trades ADD COLUMN IF NOT EXISTS linked_signal_id TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS attribution_type TEXT;  -- proximity_open, proximity_exit, committee, manual
```

Add these ALTER statements to `database/postgres_client.py` in the `init_database()` function, following the existing pattern of `ADD COLUMN IF NOT EXISTS`.

**Integration point — call on trade create/close:**

In `backend/api/unified_positions.py`, find the `create_position` endpoint (POST `/v2/positions`). After the position is inserted into `unified_positions`, add:

```python
# Proximity attribution — soft-link to recent signals
try:
    from analytics.proximity_attribution import attribute_trade
    import asyncio
    asyncio.ensure_future(attribute_trade(
        trade_id=new_trade_id,  # from the trades table insert
        ticker=ticker,
        action='open',
        timestamp=datetime.now(timezone.utc)
    ))
except Exception as e:
    logger.warning(f"Proximity attribution failed: {e}")
```

Similar call in the close endpoint (POST `/v2/positions/{position_id}/close`) with `action='close'`.

**Note:** The trades table insert happens inside the position create/close flow via `_log_trade_from_position()` or similar. Find where the trade row is actually INSERTed and wire the attribution call there. Use `asyncio.ensure_future()` so it doesn't block the response.

**API endpoint for backfill:**

```python
# In analytics/api.py or a new route
@router.post("/analytics/backfill-attribution")
async def run_backfill_attribution():
    from analytics.proximity_attribution import backfill_all_attributions
    result = await backfill_all_attributions()
    return result
```

This is a one-time endpoint. After running it, the 70 null-source trades will be scanned against 2,069 signals.

---

## Item 2: Cash Flows Table & Endpoint

**What:** Track withdrawals (and deposits) so the P&L chart doesn't show payouts as trading losses.

**Database — add to `init_database()` in `database/postgres_client.py`:**

```sql
CREATE TABLE IF NOT EXISTS cash_flows (
    id SERIAL PRIMARY KEY,
    account TEXT NOT NULL DEFAULT 'robinhood',
    flow_type TEXT NOT NULL,  -- 'withdrawal', 'deposit', 'transfer_in', 'transfer_out'
    amount NUMERIC(12,2) NOT NULL,  -- positive for deposits, negative for withdrawals
    description TEXT,
    flow_date TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**API endpoints — add to `analytics/api.py`:**

```python
@analytics_router.get("/cash-flows")
async def list_cash_flows(account: Optional[str] = None, days: int = 365):
    """List all cash flows."""
    # SELECT * FROM cash_flows WHERE ... ORDER BY flow_date DESC

@analytics_router.post("/cash-flows")
async def log_cash_flow(body: dict):
    """Log a withdrawal or deposit.
    Body: {account, flow_type, amount, description, flow_date}
    """
    # INSERT INTO cash_flows ...
    # Require auth (PIVOT_API_KEY)
```

**Integration with equity curve:**

In the existing `trade-stats` endpoint (in `analytics/api.py` or `analytics/queries.py`), find where `equity_curve` is computed. The current logic sums `pnl_dollars` from trades. Modify to:

1. After building the equity curve from trades, query `cash_flows` for the same date range
2. For each withdrawal, add an annotation point: `{date, cumulative_pnl, withdrawal: true, withdrawal_amount: -2000}`
3. Do NOT subtract withdrawals from cumulative_pnl — the curve shows trading performance only
4. The frontend will render withdrawal annotations as vertical markers

**Auth:** The POST endpoint must be protected by `PIVOT_API_KEY` (same pattern as other mutation routes). Add to the auth middleware check.

---

## Item 3: Score-Band Accuracy

**What:** Answer "for signals scored 70-80, what's the actual win rate?"

**Where to add:** In the existing `/api/analytics/signal-stats` endpoint response.

Find the signal-stats computation (likely in `analytics/queries.py` or `analytics/api.py`). Add a new field `accuracy_by_score_band` to the response.

**Computation:**

```python
async def compute_score_band_accuracy(source: str = None, days: int = 30) -> dict:
    """
    Bucket signals by score into bands, compute win rate per band.
    
    Returns: {
        "0-50": {"signals": 120, "resolved": 80, "wins": 28, "win_rate": 0.35},
        "50-60": {"signals": 45, "resolved": 30, "wins": 16, "win_rate": 0.533},
        "60-70": {"signals": 38, "resolved": 25, "wins": 15, "win_rate": 0.60},
        "70-80": {"signals": 22, "resolved": 18, "wins": 12, "win_rate": 0.667},
        "80-90": {"signals": 10, "resolved": 8, "wins": 6, "win_rate": 0.75},
        "90-100": {"signals": 3, "resolved": 3, "wins": 3, "win_rate": 1.0}
    }
    """
    # Query signals table:
    # SELECT 
    #   CASE 
    #     WHEN score < 50 THEN '0-50'
    #     WHEN score < 60 THEN '50-60'
    #     WHEN score < 70 THEN '60-70'
    #     WHEN score < 80 THEN '70-80'
    #     WHEN score < 90 THEN '80-90'
    #     ELSE '90-100'
    #   END as band,
    #   COUNT(*) as signals,
    #   COUNT(*) FILTER (WHERE outcome IS NOT NULL) as resolved,
    #   COUNT(*) FILTER (WHERE outcome = 'win') as wins
    # FROM signals
    # WHERE created_at > NOW() - interval '{days} days'
    #   AND (source = $1 OR $1 IS NULL)
    # GROUP BY band ORDER BY band
```

**Note:** The `signals` table uses `outcome` column for win/loss tracking. Check actual column names — it might be `signal_accuracy` (boolean) instead of `outcome` (text). Adapt the query to match the actual schema. If outcomes aren't being resolved (the outcome tracker is broken), this will return all zeros for `resolved` — that's expected and will populate once the outcome tracker is fixed.

---

## Item 4: Realized vs Unrealized P&L Split

**What:** Separate "money actually made" from "money theoretically up on open positions."

**Where to modify:** The existing `/api/analytics/trade-stats` endpoint response.

Find the `pnl` object in the trade-stats computation. Currently it has `total_dollars`. Add:

```python
# In the pnl computation section:
realized_pnl = sum(t.pnl_dollars for t in trades if t.status == 'closed' and t.pnl_dollars is not None)
unrealized_pnl = sum(t.pnl_dollars for t in trades if t.status == 'open' and t.pnl_dollars is not None)

# Add to the response pnl object:
"realized_dollars": realized_pnl,
"unrealized_dollars": unrealized_pnl,
```

The existing `total_dollars` stays as-is (sum of both). Frontend will display realized prominently and unrealized separately.

---

## Item 5: Bias Composite History Logging

**What:** Every time `score_all_factors()` runs (every 15 min), save the composite score and bias level.

**Database — add to `init_database()`:**

```sql
CREATE TABLE IF NOT EXISTS bias_composite_history (
    id SERIAL PRIMARY KEY,
    composite_score NUMERIC(6,4),
    bias_level TEXT NOT NULL,  -- URSA_MAJOR, URSA_MINOR, NEUTRAL, TORO_MINOR, TORO_MAJOR
    bias_numeric INTEGER,
    factor_count INTEGER,
    null_count INTEGER,
    circuit_breaker_active BOOLEAN DEFAULT FALSE,
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bias_composite_history_recorded_at ON bias_composite_history(recorded_at);
```

**Integration — wire into the scoring pipeline:**

Find `score_all_factors()` in `backend/bias_engine/factor_scorer.py` or `backend/scheduler/bias_scheduler.py`. At the END of the function, after the composite is computed, add:

```python
# Log composite to history
try:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO bias_composite_history 
               (composite_score, bias_level, bias_numeric, factor_count, null_count, circuit_breaker_active)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            composite_score, bias_level, bias_numeric, factor_count, null_count, cb_active
        )
except Exception as e:
    logger.warning(f"Bias history log failed: {e}")
```

The variable names above are placeholders — use whatever the actual computed values are called in the scoring function. The key is: capture the final composite_score, the derived bias_level string, and whether a circuit breaker was active.

---

## Item 6: Bias Accuracy Report Endpoint

**What:** Answer "when the bias said URSA, did SPY actually go down?" and "how good is the bias at filtering signals?"

**New endpoint in `analytics/api.py`:**

```python
@analytics_router.get("/bias-accuracy")
async def bias_accuracy_report(days: int = 30):
    """
    Computes two things:
    1. Directional accuracy: When bias was bullish/bearish, was SPY's next-day return in that direction?
    2. Gatekeeper effectiveness: Of signals rejected by bias alignment, how many would have lost?
    
    Returns: {
        "directional_accuracy": {
            "URSA_MAJOR": {"readings": 15, "correct": 11, "accuracy": 0.733},
            "URSA_MINOR": {"readings": 42, "correct": 24, "accuracy": 0.571},
            "NEUTRAL": {"readings": 20, "correct": null, "accuracy": null},
            "TORO_MINOR": {"readings": 30, "correct": 18, "accuracy": 0.60},
            "TORO_MAJOR": {"readings": 8, "correct": 6, "accuracy": 0.75},
            "overall": {"readings": 115, "correct": 59, "accuracy": 0.621}
        },
        "gatekeeper": {
            "signals_passed": 180,
            "signals_rejected": 45,
            "rejected_would_have_won": 12,
            "rejected_would_have_lost": 28,
            "rejected_unknown": 5,
            "filter_accuracy": 0.70
        },
        "data_available_since": "2026-03-15T12:00:00",
        "note": "Bias history logging started Mar 15. Accuracy improves with more data."
    }
    """
```

**Directional accuracy computation:**

```sql
-- Get daily bias readings (take the last reading each day)
WITH daily_bias AS (
    SELECT DISTINCT ON (DATE(recorded_at))
        DATE(recorded_at) as bias_date,
        bias_level,
        composite_score
    FROM bias_composite_history
    WHERE recorded_at > NOW() - interval '{days} days'
    ORDER BY DATE(recorded_at), recorded_at DESC
),
-- Get SPY daily close prices
daily_spy AS (
    SELECT DATE(timestamp) as price_date, close
    FROM price_history
    WHERE ticker = 'SPY' AND timeframe = 'D'
    AND timestamp > NOW() - interval '{days + 5} days'
    ORDER BY timestamp
)
-- Join: for each bias day, check if next day's SPY move matched the bias direction
SELECT
    db.bias_level,
    db.bias_date,
    (LEAD(ds.close) OVER (ORDER BY ds.price_date) - ds.close) as next_day_change
FROM daily_bias db
JOIN daily_spy ds ON db.bias_date = ds.price_date
```

Then in Python: if bias is URSA and next_day_change < 0 → correct. If TORO and next_day_change > 0 → correct. NEUTRAL is not scored.

**Gatekeeper effectiveness computation:**

```sql
-- Signals that were rejected (bias_alignment = false or status contains 'rejected')
SELECT id, ticker, direction, score, outcome, signal_accuracy
FROM signals
WHERE created_at > NOW() - interval '{days} days'
AND bias_alignment = false
```

Then count how many of those rejected signals had `signal_accuracy = true` (would have won) vs `false` (would have lost).

**Important:** This endpoint will return sparse data initially since bias_composite_history starts empty. Include a `data_available_since` field and a `note` field explaining this. The UI should show "Collecting data — X days of history accumulated" until there's at least 14 days of data.

---

## Item 7: Fix Price Collector

**What:** The price collector background job stopped running. Newest `price_history` entry is Feb 22.

**Diagnosis needed:** Look at `backend/analytics/price_collector.py` and the background loop in `main.py`. The `price_collector` job shows `last_run: null` in the schema-status endpoint.

In `main.py`, search for the price collector background task. It may:
- Not be started at all (task creation missing or commented out)
- Be crashing silently on startup
- Have a dependency that fails (Polygon API key, rate limit, etc.)

**Expected fix pattern:**

1. Find the price collector loop in `main.py` (search for `price_collect` or similar)
2. If it doesn't exist, add a background loop similar to the others:

```python
async def price_collector_loop():
    """Collect SPY + watchlist prices daily."""
    await asyncio.sleep(180)  # 3 min startup delay
    while True:
        try:
            from analytics.price_collector import collect_daily_prices
            await collect_daily_prices()
            logger.info("📈 Price collector: daily prices updated")
        except Exception as e:
            logger.warning(f"Price collector error: {e}")
        await asyncio.sleep(86400)  # 24 hours

price_collector_task = asyncio.create_task(price_collector_loop())
```

3. Also check that `collect_daily_prices()` in `price_collector.py` actually works — it may need the Polygon API key or may be hitting rate limits.
4. After fixing, verify by checking the `price_history` table for new entries after deploy.

**Add to shutdown block:** `price_collector_task.cancel()`

---

## Testing Requirements

- **Proximity attribution:** Run backfill endpoint, verify at least some of the 70 null-source trades get attributed
- **Cash flows:** POST a test withdrawal, GET cash-flows, verify it appears
- **Score-band accuracy:** Call signal-stats, verify `accuracy_by_score_band` field exists (values may be zero if outcomes not resolved)
- **Realized vs unrealized:** Call trade-stats, verify `realized_dollars` and `unrealized_dollars` fields exist
- **Bias history:** After deploy, wait 15 min, query `bias_composite_history` table — should have at least 1 row
- **Bias accuracy:** Call `/api/analytics/bias-accuracy` — should return structure with note about sparse data
- **Price collector:** After deploy, check `price_history` for entries newer than Feb 22

## Deploy

```bash
git push origin main
curl https://pandoras-box-production.up.railway.app/health
# Wait 15 min, then:
curl https://pandoras-box-production.up.railway.app/api/analytics/bias-accuracy
# Run retroactive backfill:
curl -X POST https://pandoras-box-production.up.railway.app/api/analytics/backfill-attribution -H 'X-API-Key: <key>'
```
