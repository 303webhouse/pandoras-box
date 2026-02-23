# Brief 07 — Portfolio Tracker, Open Positions, RH Import & Pivot Rename

**Priority:** HIGH
**Scope:** Database schema, API endpoints, frontend UI, Pivot screenshot parsing rules, RH CSV import, doc rename
**Estimated effort:** 6-8 hours across backend + frontend + VPS

---

## Overview

This brief adds four capabilities to Pivot:

1. **Account Balance Dashboard** — Shows all account balances on the main UI
2. **Open Positions Tracker** — Real-time view of active RH positions, updated via Pivot screenshot parsing
3. **RH Trade History Import** — Parse Robinhood CSV exports into the trade journal/backtest database
4. **"Pivot II" → "Pivot" Rename** — Remove all "Pivot II" references now that old bot is disabled

---

## Part 1: Database Schema

### New Tables (Railway PostgreSQL)

```sql
-- Account balances across all brokerages
CREATE TABLE account_balances (
    id SERIAL PRIMARY KEY,
    account_name TEXT NOT NULL,
    broker TEXT NOT NULL,
    balance NUMERIC(12,2) NOT NULL,
    cash NUMERIC(12,2),
    buying_power NUMERIC(12,2),
    margin_total NUMERIC(12,2),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'manual'
);

INSERT INTO account_balances (account_name, broker, balance, cash, buying_power, margin_total, updated_by) VALUES
    ('Robinhood', 'robinhood', 4469.37, 2868.92, 6227.38, 3603.94, 'manual'),
    ('Fidelity 401A', 'fidelity', 10109.63, NULL, NULL, NULL, 'manual'),
    ('Fidelity 403B', 'fidelity', 158.98, NULL, NULL, NULL, 'manual'),
    ('Fidelity Roth', 'fidelity', 8233.52, NULL, NULL, NULL, 'manual');

-- Open positions (RH only)
CREATE TABLE open_positions (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    position_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    option_type TEXT,
    strike NUMERIC(10,2),
    expiry DATE,
    spread_type TEXT,
    short_strike NUMERIC(10,2),
    cost_basis NUMERIC(10,2) NOT NULL,
    cost_per_unit NUMERIC(10,2),
    current_value NUMERIC(10,2),
    current_price NUMERIC(10,2),
    unrealized_pnl NUMERIC(10,2),
    unrealized_pnl_pct NUMERIC(6,2),
    opened_at TIMESTAMPTZ,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'manual',
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Cash flow events
CREATE TABLE cash_flows (
    id SERIAL PRIMARY KEY,
    account_name TEXT NOT NULL DEFAULT 'Robinhood',
    flow_type TEXT NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    description TEXT,
    activity_date DATE NOT NULL,
    imported_from TEXT DEFAULT 'csv'
);

-- RH trade history
CREATE TABLE rh_trade_history (
    id SERIAL PRIMARY KEY,
    activity_date DATE NOT NULL,
    settle_date DATE,
    ticker TEXT NOT NULL,
    description TEXT NOT NULL,
    trans_code TEXT NOT NULL,
    quantity NUMERIC(10,4),
    price NUMERIC(10,4),
    amount NUMERIC(12,2) NOT NULL,
    is_option BOOLEAN NOT NULL DEFAULT FALSE,
    option_type TEXT,
    strike NUMERIC(10,2),
    expiry DATE,
    trade_group_id TEXT,
    signal_id TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(activity_date, ticker, description, trans_code, quantity, price)
);
```

---

## Part 2: RH CSV Parser

### File: `backend/importers/rh_csv_parser.py`

### RH CSV Format Rules

**CRITICAL — Agents must understand these RH-specific quirks:**

1. **Column headers:** Activity Date, Process Date, Settle Date, Instrument, Description, Trans Code, Quantity, Price, Amount

2. **Transaction codes:**

| Code | Meaning | Import As |
|------|---------|-----------|
| `BTO` | Buy to Open (long option) | Trade |
| `STC` | Sell to Close (close long option) | Trade |
| `STO` | Sell to Open (short option) | Trade |
| `BTC` | Buy to Close (close short option) | Trade |
| `Buy` | Stock purchase | Trade |
| `Sell` | Stock sale | Trade |
| `OEXP` | Option expiration | Trade event |
| `ACH` | Deposit/withdrawal | Cash flow |
| `SLIP` | Stock lending income | **SKIP** |
| `GOLD` | Gold subscription fee | **SKIP** |
| `MTM` | Futures mark-to-market | **SKIP** |
| `INT` | Interest payment | **SKIP** |
| `FUTSWP` | Futures sweep | **SKIP** |

3. **Option descriptions:** `TICKER MM/DD/YYYY Call $XX.XX` or `Put`. Regex: `^(\w+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$(\d+\.?\d*)$`

4. **Stock descriptions contain newlines with CUSIP:** `Snowflake\nCUSIP: 833445109`. Use the **Instrument column** for ticker, NOT Description.

5. **Amounts use parentheses for negatives:** `($160.04)` → -160.04

6. **Prices have `$` prefix:** `$4.80` → 4.80

7. **OEXP quantity suffix:** `2S` = 2 short contracts expired. `2L` or `2` = long.

8. **Empty rows/disclaimer at end:** Skip rows where Activity Date is empty.

9. **Amounts include commissions:** Amount is net of ~$0.04/contract fee.

10. **Spread legs NOT grouped:** Same-date BTO+STO with same ticker+expiry = a spread. Parser groups by: same date + ticker + expiry + one buy/one sell.

### Parser Implementation

```python
import csv
import re
from datetime import datetime
from decimal import Decimal

SKIP_CODES = {'SLIP', 'GOLD', 'MTM', 'INT', 'FUTSWP'}
OPTION_CODES = {'BTO', 'STC', 'STO', 'BTC'}
STOCK_CODES = {'Buy', 'Sell'}
CASH_FLOW_CODES = {'ACH'}
EXPIRY_CODES = {'OEXP'}

OPTION_DESC_REGEX = re.compile(
    r'^(\w+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$(\d+\.?\d*)$'
)

def parse_amount(raw: str) -> Decimal:
    raw = raw.strip()
    if not raw:
        return Decimal('0')
    negative = raw.startswith('(') and raw.endswith(')')
    cleaned = raw.replace('$', '').replace('(', '').replace(')', '').replace(',', '')
    val = Decimal(cleaned)
    return -val if negative else val

def parse_price(raw: str) -> Decimal | None:
    raw = raw.strip()
    if not raw:
        return None
    return Decimal(raw.replace('$', '').replace(',', ''))

def parse_option_description(desc: str) -> dict | None:
    match = OPTION_DESC_REGEX.match(desc.strip())
    if not match:
        return None
    return {
        'ticker': match.group(1),
        'expiry': datetime.strptime(match.group(2), '%m/%d/%Y').date(),
        'option_type': match.group(3).upper(),
        'strike': Decimal(match.group(4))
    }

def parse_oexp_quantity(raw: str) -> tuple[int, str]:
    raw = raw.strip()
    if raw.endswith('S'):
        return int(raw[:-1]), 'SHORT'
    elif raw.endswith('L'):
        return int(raw[:-1]), 'LONG'
    else:
        return int(raw), 'LONG'

def parse_rh_csv(filepath: str) -> dict:
    trades = []
    cash_flows = []
    expirations = []
    skipped = 0

    with open(filepath, 'r', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)

        for row in reader:
            if len(row) < 6 or not row[0].strip():
                continue

            activity_date_str = row[0].strip()
            settle_date_str = row[2].strip()
            instrument = row[3].strip()
            description = row[4].strip()
            trans_code = row[5].strip()
            quantity_raw = row[6].strip()
            price_raw = row[7].strip() if len(row) > 7 else ''
            amount_raw = row[8].strip() if len(row) > 8 else ''

            if trans_code in SKIP_CODES:
                skipped += 1
                continue

            try:
                activity_date = datetime.strptime(activity_date_str, '%m/%d/%Y').date()
            except ValueError:
                skipped += 1
                continue

            settle_date = None
            if settle_date_str:
                try:
                    settle_date = datetime.strptime(settle_date_str, '%m/%d/%Y').date()
                except ValueError:
                    pass

            amount = parse_amount(amount_raw)

            if trans_code in CASH_FLOW_CODES:
                flow_type = 'withdrawal' if amount < 0 else 'deposit'
                cash_flows.append({
                    'activity_date': activity_date,
                    'flow_type': flow_type,
                    'amount': amount,
                    'description': description
                })
                continue

            if trans_code in EXPIRY_CODES:
                oexp_parsed = parse_option_description(
                    description.replace('Option Expiration for ', '')
                )
                qty, side = parse_oexp_quantity(quantity_raw)
                expirations.append({
                    'activity_date': activity_date,
                    'ticker': instrument,
                    'description': description,
                    'trans_code': trans_code,
                    'quantity': qty,
                    'side': side,
                    'parsed': oexp_parsed
                })
                continue

            if trans_code in OPTION_CODES:
                parsed = parse_option_description(description)
                price = parse_price(price_raw)
                quantity = Decimal(quantity_raw) if quantity_raw else Decimal('0')
                trades.append({
                    'activity_date': activity_date,
                    'settle_date': settle_date,
                    'ticker': instrument,
                    'description': description,
                    'trans_code': trans_code,
                    'quantity': quantity,
                    'price': price,
                    'amount': amount,
                    'is_option': True,
                    'option_type': parsed['option_type'] if parsed else None,
                    'strike': parsed['strike'] if parsed else None,
                    'expiry': parsed['expiry'] if parsed else None,
                })
                continue

            if trans_code in STOCK_CODES:
                price = parse_price(price_raw)
                quantity = Decimal(quantity_raw) if quantity_raw else Decimal('0')
                trades.append({
                    'activity_date': activity_date,
                    'settle_date': settle_date,
                    'ticker': instrument,
                    'description': description.split('\n')[0],
                    'trans_code': trans_code,
                    'quantity': quantity,
                    'price': price,
                    'amount': amount,
                    'is_option': False,
                    'option_type': None,
                    'strike': None,
                    'expiry': None,
                })
                continue

            skipped += 1

    return {
        'trades': trades,
        'cash_flows': cash_flows,
        'expirations': expirations,
        'skipped': skipped
    }


def group_spread_legs(trades: list) -> list:
    import hashlib
    from collections import defaultdict

    options = [t for t in trades if t['is_option']]
    stocks = [t for t in trades if not t['is_option']]

    groups = defaultdict(list)
    for t in options:
        key = (t['activity_date'], t['ticker'], t['expiry'])
        groups[key].append(t)

    for key, legs in groups.items():
        if len(legs) < 2:
            continue
        buys = [l for l in legs if l['trans_code'] in ('BTO', 'BTC')]
        sells = [l for l in legs if l['trans_code'] in ('STO', 'STC')]

        for buy in buys:
            for sell in sells:
                if buy.get('trade_group_id') or sell.get('trade_group_id'):
                    continue
                if buy['quantity'] == sell['quantity']:
                    group_id = hashlib.md5(
                        f"{key[0]}-{key[1]}-{key[2]}-{buy['strike']}-{sell['strike']}".encode()
                    ).hexdigest()[:12]
                    buy['trade_group_id'] = f"grp_{group_id}"
                    sell['trade_group_id'] = f"grp_{group_id}"
                    break

    return options + stocks
```

Also create CLI script `backend/importers/import_rh_csv_cli.py` and API endpoint `POST /api/trades/import/robinhood`.

---

## Part 3: API Endpoints

### File: `backend/api/portfolio.py`

```python
# GET  /api/portfolio/balances          — all account balances
# POST /api/portfolio/balances/update   — upsert balance (from Pivot screenshot)
# GET  /api/portfolio/positions         — all active positions
# POST /api/portfolio/positions/sync    — full sync from screenshot (returns added/updated/closed)
# POST /api/portfolio/positions/close   — close position with exit details
# GET  /api/portfolio/trade-history     — query with filters
# GET  /api/portfolio/trade-history/stats — aggregate stats
```

Auth: `PIVOT_API_KEY` in `X-API-Key` header.

Position sync flow:
1. Pivot sends all current positions from screenshot
2. API compares against DB
3. New → INSERT, Existing → UPDATE values, Missing → mark inactive + return in `closed` array
4. Pivot asks Nick about closed positions

---

## Part 4: Frontend — Account Balance Box

**Location:** Main dashboard (`index.html`), between bias cards row and chart area. Far-right, 1/4 width.

- RH row highlighted (active account), shows Cash + Buying Power sub-line
- Fidelity accounts dimmed, balance only
- Total row bold at bottom
- "Updated X ago" timestamp
- Polls every 60s
- Green/red accent on balance change

### Open Positions table wired to `/api/portfolio/positions`

Columns: Ticker | Position | Qty | Cost | Value | P&L
- Sorted by expiry (soonest first)
- P&L green/red colored
- Polls every 60s

---

## Part 5: Pivot Screenshot Parsing Rules

### File: `pivot/docs/RH_SCREENSHOT_RULES.md`

Add to Pivot's knowledge base. Haiku handles all parsing.

**Position screenshots:** Extract ticker, description, qty, avg cost, current value, return. Identify type (spread/single/stock). Call POST /api/portfolio/positions/sync. If API returns closed positions, ask Nick for exit details.

**Balance screenshots:** Extract total value, cash, buying power, margin. Call POST /api/portfolio/balances/update.

**Error handling:** If value unclear, ask Nick to confirm. If position details changed, ask if he added to the position.

---

## Part 6: "Pivot II" → "Pivot" Rename

Update all `.md`, `.py`, `.html`, `.js` files. Do NOT rename `pivot2_*.py` filenames (would break cron). Only change human-readable strings.

---

## Part 7: Deployment Order

1. Railway: Create tables → add endpoints → push → auto-deploy
2. Run CSV import CLI
3. Frontend: Update UI → push → deploy to VPS
4. VPS: Add screenshot rules to knowledge base → restart
5. Rename pass across all files

---

## Data Summary

RH CSV: 506 rows, Jan 2 – Feb 18, 2026. 259 option trades (32 tickers), 111 stock trades (31 tickers), 1 OEXP, 5 ACH withdrawals ($2,301 total).

### Current Balances (Feb 22, 2026)

| Account | Balance | Cash | BP | Margin |
|---------|---------|------|----|--------|
| Robinhood | $4,469.37 | $2,868.92 | $6,227.38 | $3,603.94 |
| Fidelity 401A | $10,109.63 | — | — | — |
| Fidelity 403B | $158.98 | — | — | — |
| Fidelity Roth | $8,233.52 | — | — | — |

### Current Open Positions (seed)

| Ticker | Type | Dir | Qty | Strikes | Expiry | Cost | Status |
|--------|------|-----|-----|---------|--------|------|--------|
| XLF | Put Spread | LONG | 5 | $50/$48 | 06/18 | $175 | Queued |
| XLF | Put Single | LONG | 2 | $43 | 06/18 | $70 | Queued |
| GS | Put Spread | LONG | 2 | $740/$730 | 05/15 | $230 | Open |
| TSLA | Put Spread | LONG | 2 | $380/$370 | 03/20 | ~$370 | Open |
| ELV | Put Spread | LONG | 2 | $310/$290 | 03/20 | ~$350 | Open |
| TFC | Call Spread | LONG | 2 | $55/$57.5 | 03/20 | ~$100 | Open |
| PFE | Call Spread | LONG | 3 | $29/$31 | 03/20 | ~$57 | Open |
| WM | Call Spread | LONG | 2 | $240/$250 | 03/20 | ~$200 | Open |
| SPB | Call Spread | LONG | 2 | $95/$105 | 07/17 | ~$324 | Open |
| IBIT | Iron Condor | MIXED | 2 | ~$38.48 | 02/27 | ~$100 | Open |
| PLTR | Short Stock | SHORT | 5 | — | — | ~$500 | Open |
