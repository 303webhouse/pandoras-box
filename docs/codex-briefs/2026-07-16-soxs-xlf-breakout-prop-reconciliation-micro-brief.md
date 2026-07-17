# CC MICRO-BRIEF — SOXS / XLF / breakout_prop Reconciliation

**Drafted 2026-07-16 evening. Dry-run completed same night** (`scripts/reconcile_soxs_xlf_dry_run.py`, read-only, writes nothing). **No write action taken — this brief proposes, it does not execute.** Any actual `account_balances` write needs Nick's explicit confirmation of current numbers (see below) before it happens.

## Scope, as given

Three items bundled: SOXS position accuracy, XLF position accuracy, and `breakout_prop`'s fake-healthy balance defect (S-1 backlog Tier 1 #3: `hub_get_portfolio_balances(account="breakout_prop")` returns an empty list tagged fresh instead of unavailable).

## Finding 1 — `breakout_prop`: root cause confirmed, fix is well-scoped

`account_balances` has zero rows for `breakout_prop` — confirmed via direct query and the dry-run script. This fully explains the S-1 defect: `hub_get_portfolio_balances`'s code (`backend/hub_mcp/tools/portfolio_balances.py`) is correct; the underlying table simply has never had a row for this account.

**The real data exists — it's just not synced.** `pivot/llm/playbook_v2.1.md` tracks it manually under "Tier C: Breakout Prop Account":
- Platform: Breakout Terminal (backed by Kraken), $25,000 evaluation capital, Step 1 of a 2-Step eval.
- Snapshot in the playbook: Balance $24,802, High Water Mark $25,158.42, trailing drawdown floor $23,158.42.
- The playbook file has no visible "as of" timestamp on this snapshot — **do not treat these numbers as current without Nick confirming them tonight or pulling a fresh screenshot.** The existing Fidelity 401A/403B rows in `account_balances` were populated the same way (`updated_by='pivot_screenshot'`, manually entered) — this is the established, precedented pattern for accounts with no API sync, not a one-off hack.

**Proposed fix (not executed):** one `INSERT` into `account_balances` for `account_name='BREAKOUT_PROP'` (or whatever exact casing keeps `_DB_TO_NORMAL`'s mapping in `portfolio_balances.py:35-40` correct — that map already expects `'BREAKOUT_PROP'` uppercase), `broker='breakout'`, `balance`/`updated_by='pivot_screenshot'` sourced from a **current** number, not the playbook's undated snapshot. Also: `portfolio_balances.py`'s `_build_account()` (lines 70-71) hardcodes `trailing_drawdown_floor`/`high_water_mark` to `None` for every account — for `breakout_prop` specifically, real values exist and matter a lot (this is the account DAEDALUS issues sizing vetoes against). Wiring these two fields for `breakout_prop` is a small, separate, worthwhile follow-up once the balance row itself lands — not bundled into this same write to keep the diff reviewable.

## Finding 2 — two more account_balances rows need a decision, not just breakout_prop

The dry-run's full-table dump surfaces two more items the original S-1 finding only summarized:
- **`Interactive Brokers`** — $0.00, last updated 2026-02-25 (`updated_by='manual'`), 4+ months stale. Reads as a dead/legacy account. Recommend archiving or deleting rather than leaving it in the unfiltered `hub_get_portfolio_balances()` response looking like a live $0 account — **Nick's call**, not assumed here (might still be intentionally open).
- **`Fidelity 401A`** / **`Fidelity 403B`** — two distinct, real sub-accounts (a 401(a) and a 403(b) are different retirement-account types) that don't match the documented single `brokerage_link_401k` account in `portfolio_balances.py`'s `_VALID_ACCOUNTS`/`_DB_TO_NORMAL`. Either the documented 4-account structure is stale (it should be 5+ real accounts: Robinhood, Fidelity Roth, Fidelity 401A, Fidelity 403B, Breakout Prop — Interactive Brokers pending the archive decision above), or these two rows should be consolidated under one `brokerage_link_401k` identity. **This is a real structural question, not a data-entry bug — flagging for Nick's decision, not guessing.**

## Finding 3 — SOXS: clean within the checkable window; current open positions can't be verified yet

Dry-run script output (`scripts/reconcile_soxs_xlf_dry_run.py`, both local Robinhood CSV exports):
- Two distinct CUSIPs found for SOXS: `25460G112` (Feb 2026 activity) and `25461H572` (May 2026 activity) — **a real corporate-action event** (Direxion leveraged ETFs periodically reverse-split; this is expected behavior, not a data error, but any reconciliation MUST treat the two CUSIP eras separately, never net raw share counts across the boundary without confirming the split ratio).
- Both CUSIP eras net to **exactly zero** within the CSV's coverage (Feb era: bought 900, sold 900; May era: bought 50, sold 50) — every historical SOXS round-trip captured in these files closed cleanly. No discrepancy found in the checkable window.
- **The CSV exports end 2026-05-13 (SOXS's last activity in them) / 2026-06-08 (file-wide).** The two currently-OPEN SOXS positions (87 shares Robinhood, opened 2026-07-07; 450 shares Fidelity Roth, opened 2026-06-10) both postdate this coverage — **neither is reconcilable against what's in this repo today.** This is a coverage gap, not a discrepancy.
- **Fidelity has no CSV reconciliation source at all in this codebase.** Unlike Robinhood (two exports, `scripts/reconcile_rh.py` precedent — see security note below), there is no equivalent Fidelity export or import path anywhere. The 450-share Fidelity Roth SOXS position has never been reconcilable against a broker record in this system, not just today.

**To close this properly:** a fresh Robinhood CSV export (covering through today) would reconcile the 87-share open position. Fidelity would need either a fresh export + a new import script (following `reconcile_rh.py`'s pattern, minus its security issue — see below) or manual confirmation, since no automated path exists.

## Finding 4 — XLF: not reconciled tonight, options contract-matching not attempted

XLF's three open Robinhood positions (per `unified_positions`) are all **options** (tiny quantities/prices consistent with options premiums, e.g. entry_price $0.07/$0.29/$0.0671), not equity shares. The dry-run script only nets equity Buy/Sell trans codes — it explicitly skips BTO/STO/BTC/STC option legs, since matching them correctly requires strike/expiry-aware pairing (the CSV shows a recurring short-put-spread pattern on XLF, e.g. simultaneous "Put $45.00 STO" + "Put $48.00 BTO" pairs on the same dates), not a simple net-shares reduction. **This needs its own, more careful reconciliation pass** — not attempted here to avoid a rushed, wrong answer on options data.

## Security note (found incidentally, not part of this brief's scope, flagging regardless)

`scripts/reconcile_rh.py` (untracked, never committed — confirmed via `git status`/`git log`) has a **hardcoded plaintext Postgres password** in its `DB_URL` constant. It has never leaked via git history since it's never been committed, but it's sitting live in the working directory. Recommend: before this file is ever committed or reused, replace the hardcoded URL with the same `.mcp.json`-reading pattern this session's other scripts use (`scripts/crypto_dual_write_diff_report.py`, and this brief's own `reconcile_soxs_xlf_dry_run.py`) — never construct or print a raw DB URL. Not fixed in this pass (out of scope for tonight's reconciliation ask); noting so it doesn't get committed as-is later.

## What this brief does NOT propose

No write to `account_balances`, `unified_positions`, or any other table happens as part of this brief. The `breakout_prop` fix (Finding 1) is ready to execute as a single `INSERT` **once Nick confirms a current balance number** — the playbook snapshot has no timestamp and may be stale. The Interactive Brokers / Fidelity-401A-403B structural questions (Finding 2) need a decision, not an assumption. SOXS/XLF need fresher broker data before any further reconciliation is meaningful.

## Next steps (ordered, none executed tonight)

1. Nick confirms current Breakout Prop balance + HWM + drawdown floor (or provides a fresh screenshot/number).
2. Nick decides: archive Interactive Brokers, and clarify the Fidelity 401A/403B vs. documented `brokerage_link_401k` structure.
3. Insert the `breakout_prop` row (small, single-statement, low-risk once #1 is confirmed) — wire `trailing_drawdown_floor`/`high_water_mark` for that account as a bundled follow-up, not the same commit.
4. Fresh Robinhood CSV export (covering 6/8/2026 to present) to close the SOXS reconciliation gap.
5. Options-aware XLF reconciliation pass, separately scoped.
6. `reconcile_rh.py`'s hardcoded credential fixed before that script is ever reused or committed.
