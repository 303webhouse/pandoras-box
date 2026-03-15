# Brief 4C — Robinhood CSV Reconciliation

**Target:** Claude Code (VSCode)
**Depends on:** Brief 4A deployed (proximity attribution columns exist)
**Estimated scope:** Small — run existing parser, compare, reconcile

---

## Context

Nick's RH account shows YTD P&L of **$2,486.57**. The database has **$2,129.55** across 111 trades. A CSV-to-DB reconciliation found:

- **29 tickers completely missing from DB** (total impact: -$574.50). These are mostly stock round-trips (SOXS, SQQQ, TSLQ partial fills, BTCZ, IGV, JPM, UNG, etc.) that the original CSV import missed.
- **12 tickers with P&L mismatches** (net impact: -$95.10). Largest: AAPL (CSV -$237 vs DB +$59), TSLA (CSV $206 vs DB $20), IWM (CSV $61 vs DB -$6).
- **1 phantom "TEST" trade** in DB with -$20 P&L that doesn't exist in RH.
- **1 missing withdrawal** — DB has 7 ACH entries, CSV shows 8 (Jan 20 $250 is missing).

The CSV file is at `C:\trading-hub\rh_export.csv` (copied from user upload). It covers Jan 2 – Mar 13, 2026, with 864 rows and 749 data rows.

## Task

### Step 1: Parse the CSV through the existing parser

The RH parser at `backend/analytics/robinhood_parser.py` handles spread grouping, OEXP, multi-leg matching, etc. Use it:

```python
# In a test script or via the API endpoint:
# POST /api/analytics/parse-robinhood-csv with the CSV file
# This returns grouped trades with proper P&L calculation
```

Alternatively, import the parser directly:
```python
from analytics.robinhood_parser import parse_robinhood_csv
with open('rh_export.csv', 'rb') as f:
    result = parse_robinhood_csv(f)
# result has: trades, open_positions, warnings, format_detected, etc.
```

### Step 2: Compare parsed trades against DB

For each parsed trade from the CSV:
1. Match against DB by ticker + approximate open date (±1 day) + structure
2. If no match → trade is MISSING from DB
3. If match but P&L differs by >$2 → P&L MISMATCH
4. If match and P&L matches → OK, skip

### Step 3: Import missing trades

Use the existing import endpoint:
```
POST /api/analytics/import-trades
Body: { account: "robinhood", trades: [...] }
```

Or insert directly into the `trades` table if the endpoint has issues with the format.

**Important:** Set `origin = 'csv_reconciliation'` on imported trades so they're distinguishable from the original import.

### Step 4: Fix P&L mismatches

For the 12 mismatched tickers, the CSV P&L is more accurate (RH is source of truth). Update the `pnl_dollars` and `pnl_percent` fields on the matching DB trades.

### Step 5: Delete phantom TEST trade

```sql
DELETE FROM trades WHERE ticker = 'TEST';
```

### Step 6: Add missing withdrawal

The Jan 20, 2026 $250 ACH withdrawal is missing from `cash_flows`:
```
POST /api/analytics/cash-flows
Body: { account: "robinhood", flow_type: "ACH", amount: -250, description: "ACH Withdrawal", flow_date: "2026-01-20" }
```

### Step 7: Re-run proximity attribution backfill

After importing new trades, re-run the backfill so newly imported trades get linked to signals:
```
POST /api/analytics/backfill-attribution
```

## Verification

After reconciliation:
1. `GET /api/analytics/trade-stats?days=3650` should show total P&L closer to $2,486.57
2. The 29 missing tickers should now have trades in the DB
3. No TEST trade should exist
4. Cash flows should show 8 ACH entries totaling -$3,451
5. The Cockpit UI should update automatically on next load

## Files

- CSV: `C:\trading-hub\rh_export.csv` (also available as upload in Claude.ai conversation)
- Parser: `backend/analytics/robinhood_parser.py`
- Import endpoint: `POST /api/analytics/import-trades`
- Cash flows endpoint: `POST /api/analytics/cash-flows`
- Attribution backfill: `POST /api/analytics/backfill-attribution`
