# Brief: Audit — Trojan Horse + Whale Hunter Signal Delivery

**Date:** March 25, 2026
**Type:** Diagnostic audit (no code changes unless bugs found)
**Priority:** HIGH — these two signal sources may be silently broken

## Context

Trojan Horse (footprint/volume imbalance) and Whale Hunter (dark pool detection) are TradingView PineScript strategies that fire webhooks to Railway. Both have been built and deployed, but neither has been verified end-to-end recently. Trojan Horse alerts were reported as erroring ~March 18. Whale Hunter was expanded to 32 tickers ~March 11 but signal flow hasn't been confirmed since.

**Goal:** Determine if signals are flowing, where they're breaking if not, and what needs fixing.

---

## Audit Step 1: Check Recent Signal Flow in Database

Query the `signals` table for recent Whale Hunter and Trojan Horse signals:

```sql
-- Whale Hunter signals (last 7 days)
SELECT id, ticker, strategy, direction, score, created_at, signal_category
FROM signals
WHERE signal_category = 'DARK_POOL' OR strategy ILIKE '%whale%'
ORDER BY created_at DESC
LIMIT 20;

-- Trojan Horse / Footprint signals (last 7 days)
SELECT id, ticker, strategy, direction, score, created_at, metadata
FROM signals
WHERE strategy ILIKE '%footprint%' OR strategy ILIKE '%trojan%'
ORDER BY created_at DESC
LIMIT 20;
```

Run these via the Supabase MCP `execute_sql` tool.

**Expected:** Recent rows for both. If either returns zero rows, signals aren't making it to the database.

---

## Audit Step 2: Check Railway Logs for Webhook Hits

Search Railway logs for recent whale and footprint webhook activity:

```bash
# Check the /health endpoint first to confirm Railway is up
curl -s -H "X-API-Key: rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk" \
  https://pandoras-box-production.up.railway.app/api/health
```

If you can't access Railway logs directly, check for errors by hitting both endpoints with diagnostic payloads (Step 3).

---

## Audit Step 3: Test Both Webhook Endpoints

### 3A: Test Whale Hunter endpoint

```bash
curl -s -X POST \
  https://pandoras-box-production.up.railway.app/webhook/whale \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "TEST_AUDIT",
    "signal": "WHALE",
    "direction": "BULLISH",
    "price": 100.00,
    "volume": 5000000,
    "avg_volume": 1000000,
    "rvol": 5.0,
    "poc": 99.50,
    "lean": "BULLISH",
    "match_type": "block_sweep",
    "timeframe": "5"
  }'
```

**Expected:** 200 response with signal confirmation. If 500, capture the error message.

### 3B: Test Trojan Horse (Footprint) endpoint

```bash
curl -s -X POST \
  https://pandoras-box-production.up.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "signal": "FOOTPRINT",
    "ticker": "TEST_AUDIT",
    "direction": "BULLISH",
    "sub_type": "stacked_buy",
    "price": 100.00,
    "stacked_layers": 5,
    "buy_imb_count": 8,
    "sell_imb_count": 2,
    "density_pct": 75.0,
    "zone_coverage_pct": 60.0,
    "vol_ratio": 2.5,
    "timeframe": "15"
  }'
```

**Expected:** 200 response. If 422 (validation error), the Pydantic model is rejecting v2 fields. If 500, capture the full error.

### 3C: Cleanup test signals

After testing, delete any TEST_AUDIT rows:

```sql
DELETE FROM signals WHERE ticker = 'TEST_AUDIT';
```

---

## Audit Step 4: Check Trojan Horse v2 Handler Brief Status

Read `docs/codex-briefs/brief-trojan-horse-v2-handler.md` and then check if its changes were ever implemented:

1. Open `backend/webhooks/footprint.py`
2. Check the `FootprintSignal` Pydantic model — does it have `density_pct`, `zone_coverage_pct`, `vol_ratio` as explicit fields (not just `extra="allow"`)?
3. Check the Redis cache block (~line 140) — are those 3 fields included in the cached JSON?
4. Check the pipeline metadata block (~line 170) — same 3 fields?
5. Check `_sub_type_display()` — are dead `buy_absorption` / `sell_absorption` entries removed?

**If the brief was NOT implemented:** Implement it now. The signals will still flow (because `extra="allow"` accepts them), but the v2 enrichment data won't be stored or surfaced. The brief has exact find/replace anchors.

---

## Audit Step 5: Verify Olympus Committee Whale Context

Check that the committee can access whale data when reviewing a signal:

1. Open `/opt/openclaw/workspace/scripts/pivot2_committee.py` on VPS via SSH
2. Find the `build_market_context` function
3. Confirm it fetches from the whale Redis cache or whale API endpoint
4. Check `committee_context.py` — confirm it renders "WHALE VOLUME DETECTED" section

Also check the Railway API endpoint the committee calls:

```bash
curl -s -H "X-API-Key: rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk" \
  "https://pandoras-box-production.up.railway.app/api/whale/recent?ticker=SPY"
```

**Expected:** JSON response with recent whale signals for SPY (or empty array if none recently). If 404, the endpoint doesn't exist or is at a different path.

---

## Audit Step 6: Check TradingView Alert Status

This step is for Nick (manual), not CC:
- Open TradingView
- Check Alerts panel — are Trojan Horse and Whale Hunter alerts active or errored?
- If any show red/error state, note which tickers and what error message

---

## Deliverable

Write a summary report with:

1. **Whale Hunter status:** Flowing / Broken / Partially working
   - Last signal date
   - Any errors from test payload
   - Committee access confirmed Y/N
2. **Trojan Horse status:** Flowing / Broken / Partially working
   - Last signal date
   - Any errors from test payload
   - v2 handler brief implemented Y/N
3. **Action items:** Numbered list of anything that needs fixing, ordered by priority

Save the report to `docs/audit-reports/audit-trojan-whale-2026-03-25.md` and push to GitHub.
