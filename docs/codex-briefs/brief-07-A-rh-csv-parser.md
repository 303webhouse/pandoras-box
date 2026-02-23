# Brief 07-A — RH CSV Trade History Parser

**Phase:** 2 (PARALLEL — can run after 07-P1 completes)
**Touches:** `backend/importers/` (new directory — no conflicts)
**Depends on:** 07-P1 (tables must exist)
**Estimated time:** 1-2 hours

---

## Task

Create a Robinhood CSV parser that imports trade history into `rh_trade_history` and `cash_flows` tables.

## Files to Create

```
backend/
  importers/
    __init__.py
    rh_csv_parser.py      — Core parsing logic (functions only, no DB)
    import_rh_csv_cli.py   — CLI script that parses + inserts into DB
```

## RH CSV Format — Critical Quirks

The CSV has these columns:
```
Activity Date, Process Date, Settle Date, Instrument, Description, Trans Code, Quantity, Price, Amount
```

### Transaction Code Map

| Code | Meaning | Action |
|------|---------|--------|
| `BTO` | Buy to Open option | → `rh_trade_history` (is_option=TRUE) |
| `STC` | Sell to Close option | → `rh_trade_history` (is_option=TRUE) |
| `STO` | Sell to Open option | → `rh_trade_history` (is_option=TRUE) |
| `BTC` | Buy to Close option | → `rh_trade_history` (is_option=TRUE) |
| `Buy` | Stock purchase | → `rh_trade_history` (is_option=FALSE) |
| `Sell` | Stock sale | → `rh_trade_history` (is_option=FALSE) |
| `OEXP` | Option expiration | → `rh_trade_history` (special handling) |
| `ACH` | Deposit/withdrawal | → `cash_flows` table |
| `SLIP` | Stock lending | **SKIP** |
| `GOLD` | Gold subscription | **SKIP** |
| `MTM` | Futures mark-to-market | **SKIP** |
| `INT` | Interest payment | **SKIP** |
| `FUTSWP` | Futures sweep | **SKIP** |

### Parsing Rules

1. **Option descriptions** follow exact format: `TICKER MM/DD/YYYY Call $XX.XX` or `Put`
   - Regex: `^(\w+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$(\d+\.?\d*)$`

2. **Stock descriptions** contain CUSIP newlines: `Snowflake\nCUSIP: 833445109`
   - **Use the `Instrument` column for ticker**, NOT Description

3. **Amounts use parentheses for negatives:** `($160.04)` → -160.04, `$479.95` → +479.95

4. **Prices have `$` prefix:** Strip it

5. **OEXP quantity suffix:** `2S` = 2 short contracts, `2L` or `2` = long

6. **Empty rows at end of file:** Skip rows where Activity Date is empty

7. **Amounts include per-contract fees** (~$0.04/contract): Amount is the actual cash impact, Price is clean

8. **Spread legs are NOT grouped in the CSV.** A debit spread = two rows on same date (one BTO + one STO with same ticker+expiry). Parser must group these.

### Spread Grouping Logic

After parsing all trades, group spread legs:
- Same `activity_date` + same `ticker` + same `expiry`
- One row is a buy (BTO/BTC), one is a sell (STO/STC)
- Same `quantity` on both legs
- Assign a shared `trade_group_id` to paired legs (e.g., `grp_` + hash of date+ticker+expiry+strikes)

## Core Parser: `rh_csv_parser.py`

This file contains pure parsing functions with NO database access:

### Functions to implement:

```python
from decimal import Decimal
from datetime import date, datetime
import csv
import re
import hashlib

OPTION_CODES = {'BTO', 'STC', 'STO', 'BTC'}
STOCK_CODES = {'Buy', 'Sell'}
SKIP_CODES = {'SLIP', 'GOLD', 'MTM', 'INT', 'FUTSWP'}
OPTION_DESC_RE = re.compile(r'^(\w+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$(\d+\.?\d*)$')

def parse_amount(raw: str) -> Decimal:
    """Parse RH amount: '($160.04)' → Decimal('-160.04'), '$479.95' → Decimal('479.95')"""
    raw = raw.strip()
    if raw.startswith('(') and raw.endswith(')'):
        return -Decimal(raw[1:-1].replace('$', '').replace(',', ''))
    return Decimal(raw.replace('$', '').replace(',', ''))

def parse_price(raw: str) -> Decimal | None:
    """Parse price field, stripping $ prefix. Returns None if empty."""
    raw = raw.strip()
    if not raw:
        return None
    return Decimal(raw.replace('$', '').replace(',', ''))

def parse_option_description(desc: str) -> dict | None:
    """Parse 'AAPL 03/21/2026 Put $220.00' → {ticker, expiry, option_type, strike}"""
    m = OPTION_DESC_RE.match(desc.strip())
    if not m:
        return None
    return {
        'ticker': m.group(1),
        'expiry': datetime.strptime(m.group(2), '%m/%d/%Y').date(),
        'option_type': m.group(3),
        'strike': Decimal(m.group(4))
    }

def parse_oexp_quantity(raw: str) -> tuple[int, str]:
    """Parse OEXP quantity: '2S' → (2, 'short'), '2L' or '2' → (2, 'long')"""
    raw = raw.strip()
    if raw.endswith('S'):
        return int(raw[:-1]), 'short'
    elif raw.endswith('L'):
        return int(raw[:-1]), 'long'
    return int(raw), 'long'

def parse_rh_csv(filepath: str) -> dict:
    """Parse entire RH CSV. Returns {trades: [], cash_flows: [], expirations: [], skipped: int}"""
    # Implementation: read CSV, route each row by trans_code, parse fields
    pass

def group_spread_legs(trades: list) -> list:
    """Group option trades into spreads by matching legs."""
    # Implementation: group by (date, ticker, expiry), match buy+sell legs, assign trade_group_id
    pass
```

## CLI Script: `import_rh_csv_cli.py`

```python
"""
CLI tool to import Robinhood CSV trade history.
Usage: python backend/importers/import_rh_csv_cli.py /path/to/robinhood.csv
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.importers.rh_csv_parser import parse_rh_csv, group_spread_legs
from backend.database.postgres_client import get_postgres_client

async def main(csv_path: str):
    print(f"Parsing {csv_path}...")
    result = parse_rh_csv(csv_path)
    trades = group_spread_legs(result['trades'])

    print(f"Parsed: {len(trades)} trades, {len(result['cash_flows'])} cash flows, "
          f"{len(result['expirations'])} expirations, {result['skipped']} skipped")

    pool = await get_postgres_client()

    # Insert trades (ON CONFLICT DO NOTHING for idempotency)
    inserted = 0
    dupes = 0
    for t in trades:
        try:
            result_row = await pool.execute("""
                INSERT INTO rh_trade_history
                    (activity_date, settle_date, ticker, description, trans_code,
                     quantity, price, amount, is_option, option_type, strike, expiry, trade_group_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (activity_date, ticker, description, trans_code, quantity, price)
                DO NOTHING
            """, t['activity_date'], t.get('settle_date'), t['ticker'], t['description'],
                t['trans_code'], float(t['quantity']) if t['quantity'] else None,
                float(t['price']) if t['price'] else None, float(t['amount']),
                t['is_option'], t.get('option_type'),
                float(t['strike']) if t.get('strike') else None,
                t.get('expiry'), t.get('trade_group_id'))
            if 'INSERT 0 1' in str(result_row):
                inserted += 1
            else:
                dupes += 1
        except Exception as e:
            print(f"  Error inserting trade: {e}")

    # Insert cash flows
    cf_inserted = 0
    for cf in result['cash_flows']:
        try:
            await pool.execute("""
                INSERT INTO cash_flows (account_name, flow_type, amount, description, activity_date, imported_from)
                VALUES ('Robinhood', $1, $2, $3, $4, 'csv')
            """, cf['flow_type'], float(cf['amount']), cf['description'], cf['activity_date'])
            cf_inserted += 1
        except Exception as e:
            print(f"  Error inserting cash flow: {e}")

    print(f"\nDone!")
    print(f"  Trades: {inserted} inserted, {dupes} duplicates skipped")
    print(f"  Cash flows: {cf_inserted} inserted")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python import_rh_csv_cli.py <path_to_csv>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
```

## Verification

```bash
# From project root
python backend/importers/import_rh_csv_cli.py path/to/robinhood_history.csv

# Expected: ~370 trades, 5 cash flows, 1 expiration, ~15 skipped
# Run again: 0 inserted, all duplicates skipped (idempotent)
```

## Commit

```
feat: add RH CSV trade history parser and CLI importer (brief 07-A)
```

## Definition of Done

- [ ] `backend/importers/__init__.py` created
- [ ] `backend/importers/rh_csv_parser.py` with all parsing functions
- [ ] `backend/importers/import_rh_csv_cli.py` with DB insertion
- [ ] Can parse actual RH CSV (506 rows) without errors
- [ ] Spread legs grouped with `trade_group_id`
- [ ] Re-running import skips duplicates (idempotent)
