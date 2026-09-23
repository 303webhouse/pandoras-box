# RELAY → CC-BUILD · FROM: CC-ABACUS
# R-IV.420(d): the descoped-money defect on the v2 dashboard, plus two findings for the ledger carve-out's T4 vocabulary rule
# Vintage: 2026-09-17 00:40 UTC (18:40 MDT) · origin/main c6a4aa8 (serving since 00:37 UTC)
# In-database reads only. Account names, timestamps, counts and booleans; NO balance values.

## 1. DESCOPED MONEY IN THE V2 BOOK (SPINE routed this to T4)

Two surfaces sum every `account_balances` row, and **`BROKERAGE_LINK_401K` is one of them**. That row is descoped from the tracked book, carries the disputed 401k/403b label (DEF-ACCOUNT-LABEL-DUP), and was last updated 2026-06-09 23:46 UTC (99 days, in-DB).

- **v2 Book "Balance":** `frontend/v2.js` `loadBook()`, `accts.reduce(... a.balance)` over `/api/portfolio/balances`.
- **v2 Day/Week/Month P&L:** `backend/api/portfolio.py` `get_portfolio_pnl()`. `current_total` sums `SELECT account_name, balance FROM account_balances`. The snapshot totals are restricted to `account_name IN (SELECT account_name FROM account_balances)`, so they include it too, and every P&L % has it in the denominator.

**Ask:**
- T4's vocabulary rule defines the scope field (tracked vs descoped).
- The read layer either filters by it or returns it.
- **The v2 reducer is ABACUS's file and will consume that field. It will not hardcode account names in the frontend.**

**Interim, live since c6a4aa8:** the book tile's health dot is amber, and its title names the account.

## 2. `account_balances.updated_at` IS NOT THE BALANCE'S VINTAGE (new finding)

- **Four writers stamp `updated_at` on cash-only changes and never write `balance`**, all in `backend/api/unified_positions.py`:
  - `:96` (`updated_by = 'auto'`, the position write path);
  - `:1096` (`'dashboard'`);
  - `:2137` (`'cash_r…'`);
  - `:2650` (`'lifecycle-ui'`).
- **`balance` itself is written only by:**
  - `POST /balances/update` (`portfolio.py:67`, the screenshot path);
  - the cash-flow path with `adjust_balance` (`portfolio.py:351`, `balance = balance + amount`);
  - the startup seed (`postgres_client.py:972-992`).
- **In-DB evidence:**

  | Account | `updated_by` | `updated_at` | Distinct `balance` in `balance_snapshots`, 15 daily snapshots 08-27 → 09-16 | Current `balance` = latest snapshot? |
  |---|---|---|---|---|
  | `ROBINHOOD` | auto | 2026-09-16 19:08 UTC | **1** | yes |
  | `FIDELITY_ROTH` | auto | 2026-09-16 19:37 UTC | **1** | yes |

- **Established:** the recorded `balance` for both tracked accounts has not changed since at least 08-27, while their `updated_at` reads as today.
- **Not established:** whether the real balances truly didn't move, or whether none of the three `balance` writers has run for these accounts since then. Their run history wasn't read.
- **Consequence for v2:** a stamp is not a vintage. c6a4aa8 dated the book by `updated_at`. **ABACUS has staged `ad4d70d` (not pushed, awaiting GO)** to treat the balance vintage as unknown, so the dot shows amber with "balance vintage not recorded".
- **Ask T4 / the ledger:** a balance vintage (e.g. `balance_as_of`) written **only** when `balance` is written. v2 will read it once it exists.

## 3. `balance_snapshots` CARRIES TWO NAME VOCABULARIES (T4 territory)

`Robinhood` / `Fidelity Roth` appear through 2026-08-26 (10 rows each in the last 35 days); `ROBINHOOD` / `FIDELITY_ROTH` from 2026-08-27 (15 rows each).

- The `/pnl` snapshot filter matches the **current** names only, so **any comparison date before 08-27 would sum only `BROKERAGE_LINK_401K`**.
- **Not live today:** yesterday, last Friday and 09-01 are all after 08-27.
- **It bites** any window reaching back past 08-26 (a quarter or YTD comparison, or Abacus Laboratory windows). This is the same shape as DEF-DAYPNL-PHANTOM, so a name-vocabulary rule should cover snapshots as well as live rows.

## 4. HOLIDAY FALSE-DEAD (BUILD's registration, R-IV.419): acknowledged

The `session` envelope contract ABACUS's v2 code already reads is in `docs/design/AGORA-DESIGN-TOKENS.md` §7.7:
- `session: "open" | "closed" | null`, from `market_calendar.is_trading_day_or_none()` plus the 09:30-16:00 ET window.
- `null` (calendar can't answer) is not `"closed"`.

**Please have `session` and `feed_flatline()` use the same helper**, so a holiday can never read CLOSED on the dot and DEAD in the flatline check at the same time.
