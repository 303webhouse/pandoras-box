# Brief — Portfolio PnL Display + Fidelity Cash Editing + Balance Snapshots

**Priority:** HIGH — daily use, no workaround
**Touches:** `backend/api/unified_positions.py`, `backend/database/postgres_client.py`, `backend/main.py`, `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
**Estimated time:** 3–4 hours

---

## Context

The portfolio summary widget at the top of the Trading Hub currently:
1. **Hardcodes Fidelity Retirement** as a JS constant (`FIDELITY_RETIREMENT = 10341` at ~line 8014 of `app.js`) — never fetches from DB
2. Has **no click-to-edit cash** on Fidelity Active Trading or Fidelity Retirement rows — only RH has this
3. Has **no withdraw/deposit logging** for Fidelity accounts — the W/D button only exists on the RH row and hardcodes `account_name: 'Robinhood'`
4. Shows **no daily, weekly, or monthly PnL** — the combined balance is a static number with no comparison to prior snapshots
5. Has **no balance snapshot infrastructure** — there's no table to store historical end-of-day balances

The backend `POST /api/portfolio/cash-flows` endpoint already accepts any `account_name`, so W/D logging for Fidelity is purely a frontend wiring task. The `PATCH /api/v2/positions/reconcile-cash` endpoint also works for any account.

---

## DB Account Names (exact strings)

These are the `account_name` values in the `account_balances` table. All API calls must use these exact strings:

| account_name | broker | What it is |
|---|---|---|
| `Robinhood` | robinhood | RH High-Risk (active trading) |
| `Fidelity Roth` | fidelity | Fidelity Active Trading (Roth Brokerage) |
| `Fidelity 401A` | fidelity | Fidelity Retirement (401A) |
| `Fidelity 403B` | fidelity | Fidelity Retirement (403B) |
| `Interactive Brokers` | ibkr | IBKR (unfunded, ignore for now) |

---

## Part 1 — Backend: Balance Snapshots Table

### File: `backend/database/postgres_client.py`

Add after the `cash_flows` table creation (~line 923):

```sql
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id SERIAL PRIMARY KEY,
    account_name TEXT NOT NULL,
    total_balance NUMERIC(12,2) NOT NULL,
    cash NUMERIC(12,2),
    position_value NUMERIC(12,2) DEFAULT 0,
    snapshot_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_name, snapshot_date)
)
```

Add index:
```sql
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_date ON balance_snapshots(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_account_date ON balance_snapshots(account_name, snapshot_date DESC);
```

---

## Part 2 — Backend: Snapshot After Mark-to-Market

### File: `backend/api/unified_positions.py` — end of `run_mark_to_market()`

After the existing MTM loop completes (after the `return` dict is built but before it's returned), add a call to snapshot balances. Only snapshot during market hours or at close. One upsert per account per day.

```python
# At end of run_mark_to_market(), before return:
try:
    await _snapshot_balances(pool)
except Exception as e:
    logger.warning("Balance snapshot failed: %s", e)
```

New helper function in `unified_positions.py`:

```python
async def _snapshot_balances(pool):
    """Upsert today's balance snapshot for all accounts. Called after MTM."""
    import pytz
    now_et = datetime.now(timezone.utc).astimezone(pytz.timezone("America/New_York"))
    
    # Only snapshot on weekdays during/after market hours (9:30 AM - 5:00 PM ET)
    if now_et.weekday() >= 5:
        return
    if now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 30):
        return
    
    today = now_et.date()
    
    # Get all account balances
    async with pool.acquire() as conn:
        bal_rows = await conn.fetch("SELECT account_name, cash, balance FROM account_balances")
    
    # Get open position values per account
    async with pool.acquire() as conn:
        pos_rows = await conn.fetch(
            "SELECT account, cost_basis, unrealized_pnl FROM unified_positions WHERE status = 'OPEN'"
        )
    
    # Sum position values by account
    pos_value_by_account = {}
    for pr in pos_rows:
        acct = (pr["account"] or "ROBINHOOD").upper()
        cost = float(pr["cost_basis"] or 0)
        pnl = float(pr["unrealized_pnl"] or 0)
        pos_value_by_account[acct] = pos_value_by_account.get(acct, 0) + cost + pnl
    
    # Upsert snapshot for each account
    async with pool.acquire() as conn:
        for br in bal_rows:
            acct_name = br["account_name"]
            cash = float(br["cash"] or 0)
            # Match position value to this account
            acct_upper = acct_name.upper().replace(" ", "_")
            pos_val = pos_value_by_account.get(acct_upper, 0)
            # Also try plain uppercase match
            if pos_val == 0:
                for k, v in pos_value_by_account.items():
                    if k.startswith(acct_name.upper().split()[0]):
                        pos_val += v
            
            total = round(cash + pos_val, 2)
            
            await conn.execute("""
                INSERT INTO balance_snapshots (account_name, total_balance, cash, position_value, snapshot_date)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (account_name, snapshot_date)
                DO UPDATE SET total_balance = $2, cash = $3, position_value = $4, created_at = NOW()
            """, acct_name, total, cash, round(pos_val, 2), today)
    
    logger.info("Balance snapshots upserted for %d accounts on %s", len(bal_rows), today)
```

**IMPORTANT:** The position value matching must handle the mismatch between `account_balances.account_name` (e.g., `"Fidelity Roth"`) and `unified_positions.account` (e.g., `"FIDELITY_ROTH"`). Use the existing `_match_account_balance()` function or the uppercase+underscore normalization shown above.

---

## Part 3 — Backend: PnL Endpoint

### File: `backend/api/unified_positions.py`

Add new endpoint **before** the `/{position_id}` route (to avoid path capture):

```python
@router.get("/v2/positions/pnl")
async def portfolio_pnl(account: Optional[str] = Query(None)):
    """
    Returns daily, weekly, and monthly PnL by comparing current balance to snapshots.
    - daily: today vs yesterday (most recent prior snapshot)
    - weekly: today vs last Friday close (or most recent snapshot before this week)
    - monthly: today vs first snapshot of current month
    """
    pool = await get_postgres_client()
    
    import pytz
    now_et = datetime.now(timezone.utc).astimezone(pytz.timezone("America/New_York"))
    today = now_et.date()
    
    # Get current balance (same logic as portfolio_summary)
    async with pool.acquire() as conn:
        bal_rows = await conn.fetch("SELECT account_name, cash FROM account_balances")
        pos_rows = await conn.fetch(
            "SELECT account, cost_basis, unrealized_pnl FROM unified_positions WHERE status = 'OPEN'"
        )
    
    # Calculate current total balance (mirrors portfolio_summary logic)
    if account:
        account_upper = account.upper()
        if account_upper == "FIDELITY":
            cash = sum(float(br["cash"] or 0) for br in bal_rows if (br["account_name"] or "").lower().startswith("fidelity"))
        else:
            cash = 0
            for br in bal_rows:
                if _match_account_balance(account, br["account_name"]):
                    cash = float(br["cash"] or 0)
                    break
        pos_val = 0
        for pr in pos_rows:
            acct = (pr["account"] or "ROBINHOOD").upper()
            if account_upper == "FIDELITY" and acct.startswith("FIDELITY"):
                pos_val += float(pr["cost_basis"] or 0) + float(pr["unrealized_pnl"] or 0)
            elif acct == account_upper:
                pos_val += float(pr["cost_basis"] or 0) + float(pr["unrealized_pnl"] or 0)
    else:
        cash = sum(float(br["cash"] or 0) for br in bal_rows)
        pos_val = sum(float(pr["cost_basis"] or 0) + float(pr["unrealized_pnl"] or 0) for pr in pos_rows)
    
    current_balance = round(cash + pos_val, 2)
    
    # Helper to get a snapshot balance for a given date range
    async def _get_snapshot(before_date, after_date=None):
        async with pool.acquire() as conn:
            if account:
                if account.upper() == "FIDELITY":
                    if after_date:
                        rows = await conn.fetch("""
                            SELECT snapshot_date, SUM(total_balance) as total
                            FROM balance_snapshots
                            WHERE account_name LIKE 'Fidelity%'
                              AND snapshot_date <= $1 AND snapshot_date >= $2
                            GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1
                        """, before_date, after_date)
                    else:
                        rows = await conn.fetch("""
                            SELECT snapshot_date, SUM(total_balance) as total
                            FROM balance_snapshots
                            WHERE account_name LIKE 'Fidelity%' AND snapshot_date <= $1
                            GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1
                        """, before_date)
                else:
                    acct_names = [br["account_name"] for br in bal_rows if _match_account_balance(account, br["account_name"])]
                    if not acct_names:
                        return None
                    acct_name = acct_names[0]
                    if after_date:
                        rows = await conn.fetch("""
                            SELECT snapshot_date, total_balance as total
                            FROM balance_snapshots
                            WHERE account_name = $1 AND snapshot_date <= $2 AND snapshot_date >= $3
                            ORDER BY snapshot_date DESC LIMIT 1
                        """, acct_name, before_date, after_date)
                    else:
                        rows = await conn.fetch("""
                            SELECT snapshot_date, total_balance as total
                            FROM balance_snapshots
                            WHERE account_name = $1 AND snapshot_date <= $2
                            ORDER BY snapshot_date DESC LIMIT 1
                        """, acct_name, before_date)
            else:
                if after_date:
                    rows = await conn.fetch("""
                        SELECT snapshot_date, SUM(total_balance) as total
                        FROM balance_snapshots
                        WHERE snapshot_date <= $1 AND snapshot_date >= $2
                        GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1
                    """, before_date, after_date)
                else:
                    rows = await conn.fetch("""
                        SELECT snapshot_date, SUM(total_balance) as total
                        FROM balance_snapshots
                        WHERE snapshot_date <= $1
                        GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1
                    """, before_date)
            if rows:
                return float(rows[0]["total"])
            return None
    
    # Daily PnL
    yesterday = today - timedelta(days=1)
    prev_balance = await _get_snapshot(yesterday, today - timedelta(days=5))
    daily_pnl = round(current_balance - prev_balance, 2) if prev_balance is not None else None
    daily_pnl_pct = round((daily_pnl / prev_balance) * 100, 2) if prev_balance and daily_pnl is not None else None
    
    # Weekly PnL
    days_since_monday = today.weekday()
    last_friday = today - timedelta(days=days_since_monday + 3) if days_since_monday > 0 else today - timedelta(days=3)
    week_start_balance = await _get_snapshot(last_friday, last_friday - timedelta(days=3))
    weekly_pnl = round(current_balance - week_start_balance, 2) if week_start_balance is not None else None
    weekly_pnl_pct = round((weekly_pnl / week_start_balance) * 100, 2) if week_start_balance and weekly_pnl is not None else None
    
    # Monthly PnL
    first_of_month = today.replace(day=1)
    month_start_balance = await _get_snapshot(first_of_month + timedelta(days=4), first_of_month)
    monthly_pnl = round(current_balance - month_start_balance, 2) if month_start_balance is not None else None
    monthly_pnl_pct = round((monthly_pnl / month_start_balance) * 100, 2) if month_start_balance and monthly_pnl is not None else None
    
    return {
        "current_balance": current_balance,
        "daily": {"pnl": daily_pnl, "pnl_pct": daily_pnl_pct, "prior_balance": prev_balance},
        "weekly": {"pnl": weekly_pnl, "pnl_pct": weekly_pnl_pct, "prior_balance": week_start_balance},
        "monthly": {"pnl": monthly_pnl, "pnl_pct": monthly_pnl_pct, "prior_balance": month_start_balance},
    }
```

**CRITICAL PLACEMENT:** This route MUST be registered before `@router.get("/v2/positions/{position_id}")` or FastAPI will interpret `"pnl"` as a `position_id`. Place it immediately after the existing `/v2/positions/summary` endpoint.

---

## Part 4 — No Backend Change Needed

The existing `GET /api/portfolio/balances` endpoint already returns all accounts including 401A and 403B. The frontend will call it directly.

---

## Part 5 — Frontend: Remove Hardcoded Fidelity Retirement

### File: `frontend/app.js`

**DELETE** the hardcoded constant (~line 8014):
```javascript
// DELETE THIS LINE:
const FIDELITY_RETIREMENT = 10341;     // 401A ($10,108) + 403B ($233)
```

---

## Part 6 — Frontend: Rewrite `loadPortfolioSummary()` and `renderPortfolioSummaryWidget()`

### File: `frontend/app.js` — `loadPortfolioSummary()` (~line 7908)

Replace the existing function to fetch all four data sources:

```javascript
async function loadPortfolioSummary() {
    try {
        const [rhRes, fidRothRes, balancesRes, pnlRes] = await Promise.all([
            fetch(`${API_URL}/v2/positions/summary?account=ROBINHOOD`),
            fetch(`${API_URL}/v2/positions/summary?account=FIDELITY_ROTH`),
            fetch(`${API_URL}/portfolio/balances`),
            fetch(`${API_URL}/v2/positions/pnl`),
        ]);
        const rhData = await rhRes.json();
        const fidRothData = await fidRothRes.json();
        const balances = await balancesRes.json();
        const pnlData = pnlRes.ok ? await pnlRes.json() : null;
        
        const bal401A = balances.find(b => b.account_name === 'Fidelity 401A');
        const bal403B = balances.find(b => b.account_name === 'Fidelity 403B');
        const retirementTotal = (bal401A?.cash || bal401A?.balance || 0) + (bal403B?.cash || bal403B?.balance || 0);
        
        renderPortfolioSummaryWidget(rhData, fidRothData, {
            total: retirementTotal,
            bal401A: bal401A?.cash || bal401A?.balance || 0,
            bal403B: bal403B?.cash || bal403B?.balance || 0,
        }, pnlData);
    } catch (error) {
        console.error('Error loading portfolio summary:', error);
    }
}
```

### File: `frontend/app.js` — `renderPortfolioSummaryWidget()` (~line 8016)

Replace entire function. New signature: `renderPortfolioSummaryWidget(rhSummary, fidRothSummary, retirement, pnlData)`.

The new function must:
- Color the combined balance green/red based on `pnlData.monthly.pnl`
- Show monthly PnL % in `#portfolioMonthlyPnl`
- Show daily PnL in `#portfolioDailyPnl` (left)
- Show weekly PnL in `#portfolioWeeklyPnl` (right)
- Use live `retirement.total` instead of `FIDELITY_RETIREMENT`
- Add click-to-edit cash links + W/D buttons on Fidelity Active Trading and Retirement rows
- Pass `accountName` to `showCashUpdateModal()` and `showWithdrawModal()`

See full implementation in the local brief file at `docs/codex-briefs/brief-portfolio-pnl-and-fidelity-cash.md`.

---

## Part 7 — Frontend: Parameterize `showCashUpdateModal()`

### File: `frontend/app.js` — `showCashUpdateModal()` (~line 8058)

**Find:** `function showCashUpdateModal(currentCash) {`
**Replace:** `function showCashUpdateModal(currentCash, accountName) {` with `accountName = accountName || 'Robinhood';`

Update modal title to `Update ${accountName} Cash` and pass `accountName` (not hardcoded `'ROBINHOOD'`) to the reconcile-cash API.

---

## Part 8 — Frontend: Parameterize `showWithdrawModal()`

### File: `frontend/app.js` — `showWithdrawModal()` (~line 8110)

**Find:** `function showWithdrawModal() {`
**Replace:** `function showWithdrawModal(accountName) {` with `accountName = accountName || 'Robinhood';`

Update modal title to `${accountName}: Withdrawal / Deposit`. Pass `accountName` to the API body instead of hardcoded `'Robinhood'`.

For retirement accounts, default toggle to Deposit:
```javascript
if (accountName.startsWith('Fidelity 4')) {
    flowType = 'deposit';
    toggles[0].classList.remove('active');
    toggles[1].classList.add('active');
}
```

---

## Part 9 — Frontend: Update HTML Layout

### File: `frontend/index.html` (~lines 175-208)

Replace the portfolio summary card HTML with new structure that includes:
- `portfolio-combined-row` flex wrapper: Daily PnL | Total + Monthly | Weekly PnL
- `fidelityActiveBreakdown` div (was static text)
- `fidelityRetirementBreakdown` div (was hardcoded values)
- All static dollar amounts removed

---

## Part 10 — Frontend: CSS for PnL Row

### File: `frontend/styles.css`

Add `.portfolio-combined-row`, `.portfolio-combined-center`, `.portfolio-pnl-indicator`, `.portfolio-monthly-pnl` styles. PnL indicators at 13px font, 600 weight. Add `--pnl-green: #4ade80` and `--pnl-red: #f87171` CSS vars if not already present.

---

## Part 11 — Frontend: 15-Minute Market Hours Refresh

Add `setInterval` that calls `loadPortfolioSummary()` every 15 minutes, but only Mon-Fri 9:30 AM - 4:15 PM ET.

---

## Part 12 — Cache Bust

Bump CSS and JS version numbers in `index.html`.

---

## Build Order

| Step | File(s) | What |
|------|---------|------|
| 1 | `postgres_client.py` | Create `balance_snapshots` table |
| 2 | `unified_positions.py` | Add `_snapshot_balances()` + call from MTM |
| 3 | `unified_positions.py` | Add `GET /v2/positions/pnl` (BEFORE `/{position_id}`) |
| 4 | `app.js` | Delete `FIDELITY_RETIREMENT` constant |
| 5 | `app.js` | Rewrite `loadPortfolioSummary()` |
| 6 | `app.js` | Rewrite `renderPortfolioSummaryWidget()` |
| 7 | `app.js` | Parameterize `showCashUpdateModal(currentCash, accountName)` |
| 8 | `app.js` | Parameterize `showWithdrawModal(accountName)` |
| 9 | `index.html` | Replace portfolio summary HTML block |
| 10 | `styles.css` | Add PnL row styles |
| 11 | `app.js` | Add 15-min market-hours refresh |
| 12 | `index.html` | Cache bust |

---

## Verification Checklist

- [ ] `balance_snapshots` table created on deploy
- [ ] MTM trigger creates snapshot rows for today
- [ ] `GET /v2/positions/pnl` returns daily/weekly/monthly objects
- [ ] Portfolio widget loads with correct combined total
- [ ] Fidelity Retirement shows live DB values (not $10,341)
- [ ] Click Fidelity Active Trading cash → update modal opens → save works
- [ ] Click 401A/403B amounts → update modal opens → save works
- [ ] W/D on Fidelity Active Trading → logs to cash_flows with `Fidelity Roth`
- [ ] W/D on Retirement → defaults to Deposit toggle → logs with `Fidelity 401A`
- [ ] PnL shows "—" initially → populates after 2 trading days of snapshots
- [ ] Combined balance color changes green/red based on monthly PnL
- [ ] 15-min refresh fires during market hours only

---

## Known Limitations

1. PnL shows "—" until snapshots accumulate (2+ trading days needed)
2. W/D on Retirement defaults to 401A — click 403B amount directly to update that sub-account
3. Snapshots only fire during MTM runs (market hours). Standalone cron snapshot is a future enhancement.
