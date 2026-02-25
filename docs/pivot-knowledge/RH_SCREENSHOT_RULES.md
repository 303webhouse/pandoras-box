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

## API Call Formats

### Screenshot sync (portfolio list view — multiple positions)
ALWAYS send `partial: true`. Screenshots may not show all positions.

**Endpoint:** `POST /api/portfolio/positions/sync`

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
    ],
    "partial": true,
    "account": "robinhood"
}
```

The API returns:
```json
{
    "added": [...],
    "updated": [...],
    "closed": [...],
    "possibly_closed": [
        {"id": 12, "ticker": "SPY", "strike": 580.0, "expiry": "2026-03-20", "direction": "SHORT"}
    ]
}
```

**If `possibly_closed` is not empty:** Ask Nick for each entry:
> "I noticed **{ticker} {strike} {expiry}** wasn't in this screenshot. Did you close it?"
- **Yes** → call `POST /api/portfolio/positions/close` with whatever exit details Nick provides
- **No** → do nothing (it'll reappear on the next sync)

### Single fill screenshot (one new position, especially after TAKE)
Use `POST /api/portfolio/positions` to create a single position.

**Before calling this endpoint**, check `/opt/openclaw/workspace/data/last_take.json`.
If the file exists and:
1. Was written within the last 15 minutes
2. The ticker matches the screenshot

Then include its `signal_id` in your POST call to link the position to the committee recommendation.

```json
{
    "ticker": "TSLA",
    "position_type": "option_spread",
    "direction": "BEARISH",
    "quantity": 2,
    "option_type": "Put",
    "strike": 250.0,
    "expiry": "2026-03-21",
    "spread_type": "debit",
    "short_strike": 240.0,
    "cost_basis": 340.0,
    "cost_per_unit": 1.70,
    "signal_id": "sig_xxx",
    "account": "robinhood"
}
```

Returns the created position row. If a 409 Conflict is returned, the position already exists —
use `POST /api/portfolio/positions/sync` with `partial: true` to update it instead.

### Position Close
**Endpoint:** `POST /api/portfolio/positions/close`

```json
{
    "ticker": "SPY",
    "strike": 590.0,
    "expiry": "2026-03-20",
    "short_strike": 580.0,
    "direction": "SHORT",
    "exit_value": 150.0,
    "exit_price": 1.50,
    "close_reason": "stopped out",
    "closed_at": "2026-02-24T14:30:00",
    "account": "robinhood",
    "notes": "Stopped out on gap up"
}
```

Returns the `closed_positions` row with computed `pnl_dollars`, `pnl_percent`, and `hold_days`.
The position is removed from `open_positions`.

## Linking positions to committee recommendations

Before calling `POST /api/portfolio/positions` for a fill screenshot, check
`/opt/openclaw/workspace/data/last_take.json`. If it exists and:
1. Was written within the last 15 minutes
2. The ticker matches the screenshot

Then include its `signal_id` in your POST call. This links the position back to the committee
recommendation for analytics.

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
