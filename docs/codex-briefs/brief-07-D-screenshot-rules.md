# Brief 07-D — Pivot Screenshot Parsing Rules

**Phase:** 2 (PARALLEL — standalone markdown file, no code dependencies)
**Touches:** `docs/pivot-knowledge/RH_SCREENSHOT_RULES.md` (new)
**Estimated time:** 10 minutes

---

## Task

Create a reference document that will be added to Pivot's knowledge base on the VPS. This tells Pivot (the OpenClaw trading assistant) how to parse Robinhood screenshots and sync data via the portfolio API.

**This is a documentation-only task.** The file gets deployed to the VPS later via manual copy. For now, just create it in the repo.

## File to Create

`docs/pivot-knowledge/RH_SCREENSHOT_RULES.md`

Contents:

```markdown
# Robinhood Screenshot Parsing Rules

You (Pivot) use these rules when Nick sends Robinhood screenshots to update the portfolio tracker.

## API Endpoints

Base URL: Use the `RAILWAY_URL` environment variable.
Auth: Include `X-API-Key: {PIVOT_API_KEY}` header on all POST requests.

### Balance Updates
**Endpoint:** `POST /api/portfolio/balances/update`

When Nick sends a screenshot of his Robinhood account overview:
1. Extract: total portfolio value, cash balance, buying power, margin
2. Send:
```json
{
    "account_name": "Robinhood",
    "balance": 4469.37,
    "cash": 2868.92,
    "buying_power": 6227.38,
    "margin_total": 3603.94
}
```

### Position Sync
**Endpoint:** `POST /api/portfolio/positions/sync`

When Nick sends a screenshot of his positions:
1. Extract ALL visible positions
2. For each position, determine:
   - `ticker` — the stock/ETF symbol
   - `position_type` — one of: `option_spread`, `option_single`, `stock`, `short_stock`
   - `direction` — `LONG` or `SHORT`
   - `quantity` — number of contracts or shares
   - `option_type` — `Call` or `Put` (if applicable)
   - `strike` — primary strike price (for options)
   - `expiry` — expiration date as `YYYY-MM-DD`
   - `spread_type` — `debit` or `credit` (if spread)
   - `short_strike` — second leg strike (if spread)
   - `cost_basis` — total cost paid for the position
   - `current_value` — current market value shown
   - `unrealized_pnl` — profit/loss shown
   - `unrealized_pnl_pct` — percentage return shown

3. Send all positions in one request:
```json
{
    "positions": [
        {
            "ticker": "XLF",
            "position_type": "option_spread",
            "direction": "SHORT",
            "quantity": 5,
            "option_type": "Put",
            "strike": 50.0,
            "expiry": "2026-06-18",
            "spread_type": "debit",
            "short_strike": 48.0,
            "cost_basis": 175.0,
            "current_value": 200.0,
            "unrealized_pnl": 25.0,
            "unrealized_pnl_pct": 14.28
        }
    ]
}
```

4. The API returns: `{ "added": [...], "updated": [...], "closed": [...] }`
5. **If the `closed` array is not empty:** These are positions that were in the database but NOT in the screenshot — meaning Nick probably closed them.
   - For each closed position, ask Nick: "Looks like you closed **{ticker} {strike} {expiry}**. What was the exit? Send a screenshot or tell me the exit price."
   - Once Nick provides exit info, call the close endpoint.

### Position Close
**Endpoint:** `POST /api/portfolio/positions/close`

```json
{
    "ticker": "SPY",
    "strike": 590.0,
    "expiry": "2026-03-20",
    "short_strike": 580.0,
    "exit_price": 1.50,
    "exit_date": "2026-02-24",
    "realized_pnl": -50.00,
    "notes": "Stopped out on gap up"
}
```

## Position Type Detection

### Option Spreads
Two strikes visible for the same ticker and expiry:
- **Put debit spread:** Long the higher strike put, short the lower strike put
  - Example: "XLF $50/$48 Put" → strike=50, short_strike=48, direction=SHORT (bearish)
- **Call debit spread:** Long the lower strike call, short the higher strike call
  - Example: "TFC $55/$57.5 Call" → strike=55, short_strike=57.5, direction=LONG (bullish)
- **Iron Condor:** Two put strikes + two call strikes → position_type=`option_spread`, note both ranges

### Single Options
One strike visible:
- Put → direction=SHORT (bearish)
- Call → direction=LONG (bullish)

### Stocks
- Positive quantity → direction=LONG
- Listed as "short" or negative → direction=SHORT, position_type=`short_stock`

## Error Handling

- If a value is unclear or partially visible → ask Nick to confirm before sending
- If a position's details changed significantly (e.g., quantity doubled) → ask "Did you add to your {ticker} position?"
- If screenshot is blurry → tell Nick and ask for a clearer one
- Never guess at values — always confirm if uncertain

## Fidelity Accounts

Nick also has Fidelity accounts. For these, ONLY update balances:
- `account_name`: "Fidelity 401A", "Fidelity 403B", or "Fidelity Roth"
- Extract just the total balance
- No position tracking for Fidelity (balance-only tracking)
```

## Commit

```
docs: add Pivot screenshot parsing rules for RH portfolio sync (brief 07-D)
```

## Definition of Done

- [ ] `docs/pivot-knowledge/RH_SCREENSHOT_RULES.md` created in repo
- [ ] Covers: balance updates, position sync, position close, type detection, error handling, Fidelity
- [ ] All API endpoint paths and JSON schemas are accurate
