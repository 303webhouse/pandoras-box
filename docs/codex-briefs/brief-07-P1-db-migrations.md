# Brief 07-P1 — Database Migrations

**Phase:** 1 (SERIAL — must complete before all other sub-briefs)
**Touches:** `backend/database/postgres_client.py`
**Estimated time:** 15 minutes

---

## Task

Add 4 new tables to Railway PostgreSQL by appending CREATE TABLE IF NOT EXISTS statements to the `init_database()` function in `backend/database/postgres_client.py`.

## Find the anchor

In `backend/database/postgres_client.py`, locate the `init_database()` async function. It contains multiple `CREATE TABLE IF NOT EXISTS` blocks. Append the following **after** the last existing CREATE TABLE block but **before** the function's closing/return.

## SQL to add

```sql
-- Brief 07: Account balances across all brokerages
CREATE TABLE IF NOT EXISTS account_balances (
    id SERIAL PRIMARY KEY,
    account_name TEXT NOT NULL UNIQUE,
    broker TEXT NOT NULL,
    balance NUMERIC(12,2) NOT NULL,
    cash NUMERIC(12,2),
    buying_power NUMERIC(12,2),
    margin_total NUMERIC(12,2),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'manual'
);

-- Brief 07: Open positions (RH active trading account only)
CREATE TABLE IF NOT EXISTS open_positions (
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

-- Brief 07: Cash flow events for accurate P&L calculation
CREATE TABLE IF NOT EXISTS cash_flows (
    id SERIAL PRIMARY KEY,
    account_name TEXT NOT NULL DEFAULT 'Robinhood',
    flow_type TEXT NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    description TEXT,
    activity_date DATE NOT NULL,
    imported_from TEXT DEFAULT 'csv'
);

-- Brief 07: RH trade history imported from CSV exports
CREATE TABLE IF NOT EXISTS rh_trade_history (
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

## Seed data

After the CREATE TABLE statements, add a seed block for initial account balances:

```sql
-- Seed account balances (only if table is empty)
INSERT INTO account_balances (account_name, broker, balance, cash, buying_power, margin_total, updated_by)
SELECT 'Robinhood', 'robinhood', 4469.37, 2868.92, 6227.38, 3603.94, 'manual'
WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_name = 'Robinhood');

INSERT INTO account_balances (account_name, broker, balance, updated_by)
SELECT 'Fidelity 401A', 'fidelity', 10109.63, 'manual'
WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_name = 'Fidelity 401A');

INSERT INTO account_balances (account_name, broker, balance, updated_by)
SELECT 'Fidelity 403B', 'fidelity', 158.98, 'manual'
WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_name = 'Fidelity 403B');

INSERT INTO account_balances (account_name, broker, balance, updated_by)
SELECT 'Fidelity Roth', 'fidelity', 8233.52, 'manual'
WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_name = 'Fidelity Roth');
```

## Implementation pattern

Follow the existing pattern in `init_database()`. Each CREATE TABLE is executed via `await pool.execute(sql)`. The seed inserts use the same pattern.

## Verification

After push to main (Railway auto-deploys), verify:
```bash
curl https://pandoras-box-production.up.railway.app/health
# Should return healthy

# Tables will be created on next Railway restart
```

## Commit

```
feat: add portfolio tracker database tables (brief 07-P1)
```

## Definition of Done

- [ ] 4 CREATE TABLE IF NOT EXISTS statements added to `init_database()`
- [ ] Seed data for 4 account balances added (idempotent — won't duplicate on restart)
- [ ] Pushed to main, Railway auto-deploys without errors
