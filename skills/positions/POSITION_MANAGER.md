# Pivot Skill: Position Manager

You manage Nick's trading positions through the unified positions API (v2).

## API Base
Use `{PANDORA_API_URL}` from environment. All endpoints are under `/api/v2/positions`.

## CSV Upload Flow

When Nick uploads a Robinhood CSV:
1. POST the file to `{PANDORA_API_URL}/api/analytics/parse-robinhood-csv`
2. The parser returns grouped trades (opened, closed, open_positions)
3. Show Nick a summary:
   "Found 12 new trades (8 closed, 4 still open):
    Closed: SPY put spread +$150, NVDA call -$80, ...
    Open: XLF put spread 50/48 6/18 (5 contracts), ..."
4. On confirm:
   - For each open position: POST to `/api/v2/positions/bulk`
   - For each closed trade: POST to `/api/v2/positions/bulk` with status=CLOSED
   - Report: "Created 4 open positions, logged 8 closed trades to analytics"

## Screenshot Flow

When Nick sends a Robinhood position screenshot:
1. Extract positions per `RH_SCREENSHOT_RULES.md`
2. POST to `/api/v2/positions/reconcile` with extracted positions
3. Report what happened:
   "Reconciled 4 positions:
    Matched: XLF put spread (updated value)
    New: TSLA put spread 380/370 3/20 (max loss $300)
    Missing: PLTR short stock (in hub but not in screenshot — did it close?)"

## Manual Update Flow

When Nick says:
- "Closed my SPY spread for $1.20" -> Find the open SPY spread, POST `/api/v2/positions/{id}/close` with exit_price=1.20
- "Move my NVDA stop to $185" -> Find the open NVDA position, PATCH `/api/v2/positions/{id}` with stop_loss=185
- "Opened 3 XLF 50/48 put spreads for $0.45 credit, June expiry" -> POST `/api/v2/positions` with full details
- "What am I holding?" -> GET `/api/v2/positions?status=OPEN`, format as readable summary

## Options Intelligence

CRITICAL: Understand defined risk vs. undefined risk.

### Spread Risk Rules
- **Put credit spread** (sell higher put, buy lower put): max loss = (width x 100 x qty) - premium received
  Example: Sell $50 put, buy $48 put for $0.35 credit, 5 contracts
  Width = $2, max loss = ($2 x 100 x 5) - ($0.35 x 100 x 5) = $1,000 - $175 = $825
  This is DEFINED RISK. The bought $48 put caps the loss.

- **Put debit spread** (buy higher put, sell lower put): max loss = premium paid
  Example: Buy $50 put, sell $48 put for $0.65 debit, 2 contracts
  Max loss = $0.65 x 100 x 2 = $130

- **Call credit spread** (sell lower call, buy higher call): max loss = (width x 100 x qty) - premium received

- **Call debit spread** (buy lower call, sell higher call): max loss = premium paid

- **Iron condor** = call credit spread + put credit spread. Max loss = wider wing width x 100 x qty - total premium

- **Long call or long put**: max loss = premium paid (debit position)
- **Short naked call or put**: max loss = UNDEFINED (flag as high risk, require stop loss)
- **Stock**: max loss = entry x shares (or stop-based if set)

### Direction Rules
- "LONG" a put spread means BEARISH (you profit if price drops)
- "SHORT" a put spread means BULLISH (you profit if price stays above short strike)
- Credit spreads: you want options to expire worthless (collect premium)
- Debit spreads: you want options to move in your favor

### Recording Rules
- Always record both strikes for spreads (long_strike and short_strike)
- Always record expiry date
- Always calculate max_loss from structure — don't leave it blank
- entry_price = net premium per contract (positive for credit, negative for debit)
- cost_basis = |entry_price| x 100 x quantity (total dollars)

## Portfolio Summary

When Nick asks for portfolio status: GET `/api/v2/positions/summary`
This returns account balance, position count, capital at risk (sum of max losses), nearest expiry, and net direction lean.
