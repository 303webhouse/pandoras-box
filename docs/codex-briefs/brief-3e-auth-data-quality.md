# Brief 3E: Auth Audit + Data Quality + Structural Cleanup

## Summary

Finish auth on analytics mutation routes, clean up structural clutter (duplicate routers, orphaned code), back-fill missing signal attribution on historical trades, and add focused analytics tests.

## 1. Auth on Analytics Mutations

Check these analytics mutation routes in `backend/analytics/api.py` for `require_api_key`:

```
POST  /analytics/trades              (log_trade)
POST  /analytics/trades/close        (close_trade_endpoint)
POST  /analytics/trades/legs         (log_trade_leg)
POST  /analytics/outcomes            (create_manual_outcome)
POST  /analytics/signals             (log_signal_endpoint)
POST  /analytics/uw-snapshots        (log_uw_snapshot)
POST  /analytics/import-trades       (import_trades)
DELETE /analytics/import-trades      (delete_all_imported_trades)
DELETE /analytics/trades/{trade_id}  (delete_trade_by_id)
POST  /analytics/health-alerts/{id}/dismiss  (dismiss_health_alert)
```

For each: if no `Depends(require_api_key)`, add it. Same pattern as Phase 0H.

## 2. CSV Import Sanitization

The `parse_robinhood_csv` endpoint accepts file uploads. Verify:
- File size limit enforced
- No path traversal in uploaded filename
- CSV content sanitized (no formula injection: cells starting with `=`, `+`, `-`, `@` that could trigger spreadsheet formula execution if data is exported later)
- Input validation on parsed fields (amounts, dates, ticker symbols)

## 3. Export Endpoint Auth

Verify auth on export endpoints:
```
GET /analytics/export/signals
GET /analytics/export/trades
GET /analytics/export/factors
GET /analytics/export/price-history
```

These return sensitive trading data. If unauthenticated, add `Depends(require_api_key)`.

## 4. Duplicate Router Cleanup

GPT flagged a dormant duplicate router. Check:
- `backend/api/analytics.py` — is this file different from `backend/analytics/api.py`?
- If `backend/api/analytics.py` exists and is a stub/duplicate, remove it
- Verify `main.py` only mounts one analytics router

```python
# In main.py, should be ONE of:
from analytics.api import router as analytics_router
# NOT also:
from api.analytics import router as analytics_router_v2  # duplicate?
```

## 5. Back-Fill Signal Attribution

Many historical trades in the `trades` table (Robinhood imports, manual entries) have no `signal_id`. For imported trades, attempt to match:

```python
async def backfill_signal_attribution():
    """
    One-time job: match historical trades to signals by ticker + direction + time proximity.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Get trades without signal_id
        trades = await conn.fetch("""
            SELECT id, ticker, direction, opened_at
            FROM trades
            WHERE signal_id IS NULL
            AND opened_at IS NOT NULL
        """)

        for trade in trades:
            # Find closest signal within 24h window
            signal = await conn.fetchrow("""
                SELECT signal_id FROM signals
                WHERE ticker = $1
                AND direction = $2
                AND created_at BETWEEN $3 - INTERVAL '24 hours' AND $3 + INTERVAL '2 hours'
                ORDER BY ABS(EXTRACT(EPOCH FROM (created_at - $3)))
                LIMIT 1
            """, trade["ticker"], trade["direction"], trade["opened_at"])

            if signal:
                await conn.execute(
                    "UPDATE trades SET signal_id = $1 WHERE id = $2",
                    signal["signal_id"], trade["id"]
                )
```

Run this once as a migration script. Won't be perfect but captures obvious matches.

## 6. Analytics Endpoint Tests

Add to `backend/tests/` — beyond route smoke tests, test that endpoints return valid data shapes:

```python
class TestAnalyticsEndpoints:
    def test_oracle_returns_expected_shape(self, client):
        resp = client.get("/api/analytics/oracle?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "narrative" in data
        assert "system_health" in data
        assert "strategy_scorecards" in data

    def test_risk_budget_returns_equity_and_crypto(self, client):
        resp = client.get("/api/analytics/risk-budget")
        assert resp.status_code == 200
        data = resp.json()
        assert "equity" in data
        assert "crypto" in data
        assert "combined" in data

    def test_signal_stats_filters_by_source(self, client):
        resp = client.get("/api/analytics/signal-stats?source=Holy_Grail&days=30")
        assert resp.status_code == 200
```

## Definition of Done

- [ ] All 10 analytics mutation routes have `require_api_key`
- [ ] CSV import validates file size, sanitizes content
- [ ] Export endpoints require auth
- [ ] No duplicate analytics router mounted
- [ ] Historical trades back-filled with signal_id where matchable
- [ ] Analytics endpoint shape tests added
- [ ] Auto-discovery auth test updated if needed
- [ ] All existing tests pass
