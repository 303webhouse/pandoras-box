# CC-POSITIONS Phase 0b — Items 1, 8, 9

**Status:** READ-ONLY assessment. No writes, no migrations, no code changes, no allowlist edits.
**Vintage:** read 2026-08-25 05:12 UTC (2026-08-24 23:12 MDT) · repo `2de26c6` · branch `main`
**Read path:** direct SQL via read-only Postgres MCP with `::text` casts; source read from
the working tree. `hub_get_positions` / `hub_get_portfolio_balances` **not** used as a read
path for state (per standing instruction).

> ### Code vintage pin — `2de26c6`
>
> Every source citation in this file was read at **`2de26c6`**, the session-open local HEAD.
> That is the pin; it is not `origin/main`.
>
> **As of 2026-08-25 05:45 UTC (2026-08-24 23:45 MDT), `origin/main` = `8b2d767`** — the
> working tree was **7 behind, 0 ahead** and has **subsequently been rebased to `8b2d767`** at 06:12 UTC under R-IV.80(c) fetch-before-write hygiene. The pin is unaffected: it records where the reads were taken, not the current tree. Remote state confirmed first-hand by
> `git ls-remote origin refs/heads/main`, not by the local remote-tracking ref alone.
> `origin/main` moved twice during this session (`cb77712` → `8b2d767`); concurrent sessions
> push `main`, so treat any pinned remote SHA here as a timestamped observation.
>
> **Do the findings survive the 7-commit delta? Yes — verified, not assumed.**
> Of the 6 files inventoried in Item 9.1, exactly two were touched —
> `backend/api/unified_positions.py` and `backend/database/postgres_client.py` — both solely
> by `073395f fix(p0): NaN-poison — close the JSONB bind class` (`json.dumps` →
> `dumps_jsonb` at bind sites). Confirmed unchanged at `origin/main`:
> `ACCOUNT_DISPLAY_MAP` (:60, still carrying `FIDELITY_401A`), `_match_account_balance`
> (:68), and the seed block. **Untouched entirely:** `backend/api/portfolio.py`,
> `backend/hub_mcp/tools/portfolio_balances.py`, `backend/hub_mcp/tools/positions.py`,
> `backend/services/read_only/balances.py`, `backend/services/read_only/positions.py`,
> `frontend/app.js`, `frontend/index.html`.
>
> That means every Item 1 / 8 / 9 defect is live at `origin/main` as written — the
> uppercase-filter zero-match, the `balance ≤ cash` semantics, the
> `position_value = balance − cash` arithmetic, the five disagreeing account lists, and the
> `401a`/`403b` substring rollup that drops `BROKERAGE_LINK_401K`.
>
> **Line-number offset:** an added import at line 23 shifts everything below it by **+1** in
> `unified_positions.py` (`:59-64` → `:60-65`, `:67-74` → `:68-75`, `:80-86` → `:81-87`,
> `:815-855` → `:816-856`, `:1066` → `:1067`, `:2062-2072` → `:2063-2073`). Line numbers in
> every other file cited here are unaffected.

## Manifest (law v2)

| Scope | Rows | Fingerprint |
|---|---|---|
| `account_balances` (`account_name\|balance\|cash\|updated_at`) | **3** | `26db698969b711c2859c957f39335852` |
| `balance_snapshots` (`snapshot_date\|account_name\|balance\|position_value`) | **516** | `fea8d69a7ee7ef9718fc1c4b40c13165` |
| `unified_positions` marks (`position_id\|current_price\|price_updated_at\|status`) | **329** | `f5cb12f1b32a825960cca30ef63684e1` |

---

# ITEM 1 (PRIORITY) — Does any sizing path read the aggregate?

**Answer: YES — but the consumer is an LLM committee agent, not a code path. There is no
automated sizing function that reads `total_balance`.**

## The complete consumer inventory for `total_balance` / `total_cash`

```
backend/hub_mcp/tools/portfolio_balances.py:119   total_balance = sum(a["balance"] for a in accounts)
backend/hub_mcp/tools/portfolio_balances.py:120   total_cash    = sum(a["cash"] or 0 for a in accounts)
backend/hub_mcp/tools/portfolio_balances.py:131   "total_balance": round(total_balance, 2)
backend/hub_mcp/tools/portfolio_balances.py:132   "total_cash":    round(total_cash, 2)
backend/hub_mcp/tools/portfolio_balances.py:145   summary string f"Total ${total_balance:,.0f} across {len(accounts)} accounts."
backend/hub_mcp/tests/test_tools_smoke.py:504     assert r["data"]["total_balance"] == 4500.0   (test only)
```

That is the **entire** set. `total_balance` is produced in exactly one file and consumed by
**no other Python code anywhere** in `backend/`, `scripts/`, `pivot/`, or `frontend/`. No
risk calculator, no position sizer, no committee script reads the field programmatically.

## Why that is not reassuring

The consumer is the model reading the MCP envelope. The tool's own description
([portfolio_balances.py:13-27](../../backend/hub_mcp/tools/portfolio_balances.py#L13-L27))
directs it into sizing in six explicit places:

> "Use this whenever **sizing recommendations** need real account values (**replaces the
> prior practice of hardcoding dollar amounts in skill files**), when TORO/URSA/DAEDALUS/
> PIVOT is producing a **sizing recommendation**, when PYTHAGORAS is computing **per-position
> risk parameters against account size**, when PYTHIA is **sizing a B3 scalp trigger**, when
> THALES is flagging **sector concentration as a % of account**, when evaluating whether a
> proposed trade fits within **three-bucket sizing rules**."

So the sizing path is: committee agent → `hub_get_portfolio_balances` → reads
`total_balance` and the `summary` string → sizes against it. The summary line
(`"Total $21,320 across 3 accounts"`) is the most-read surface and carries the inflated
figure in prose, where it is least likely to be questioned.

**Quantification, as the work order requests.** Per the principal's broker artifact, both
Fidelity rows describe the same real account ACCT-ROTH. Present state:

| account_name | balance | true tradeable |
|---|---|---|
| Robinhood | $835.69 | $835.69 |
| BROKERAGE_LINK_401K | $11,642.35 | *(duplicate of Roth — same account)* |
| Fidelity Roth | $8,842.09 | $11,382.17 (broker actual) |
| **`total_balance` rendered** | **$21,320.13** | **$12,217.86 true** |

**Overstatement: $9,102.27 — 74.5% high.** `total_balance` has read $21,320.13 since the
2026-07-23 consolidation; the `BROKERAGE_LINK_401K` row has not been touched since
**2026-06-09 23:46:03+00** (77 days stale as of this read).

**Verdict:** no code-level sizing gate reads the aggregate, so no automated order was sized
off it. Every *advisory* sizing recommendation produced by a committee agent since at least
2026-06-09 was anchored to a number 74.5% too large. Spine's hold on EDGE and 3DTE
sizing-dependent gates is, on this evidence, warranted.

## Additional live defect found while inventorying — account filter returns zero

`get_account_balances()` ([services/read_only/balances.py:33-38](../../backend/services/read_only/balances.py#L33-L38))
filters with `WHERE account_name = $1` on `account.upper()`. The DB stores mixed case:

```
 filter_value           rows_matched
 ROBINHOOD                        0
 FIDELITY_ROTH                    0
 BROKERAGE_LINK_401K              1
 BREAKOUT_PROP                    0
```

Actual `account_name` values are `'Robinhood'` and `'Fidelity Roth'`. Only
`BROKERAGE_LINK_401K` is stored uppercase, so it is the **only** filter that can ever match.

`hub_get_portfolio_balances(account="robinhood")` therefore returns `accounts: []`,
`total_balance: 0.0`, and — because `funded` is empty, so `any_stale` is `False`
([portfolio_balances.py:127-128](../../backend/hub_mcp/tools/portfolio_balances.py#L127-L128))
— **`status: "ok"`**. A filtered balance query for the primary trading account reports **$0
as healthy**. Fake-healthy, same class as the breakout_prop defect closed on 2026-07-23.
Cause confirmed; **no fix proposed** (CC-BUILD's lane).

---

# ITEM 8 — Does `balance` hold total value, or cash?

**Answer: NEITHER, reliably. `balance` is a manually-typed screenshot figure that then
drifts by cash deltas only. It has no positions-value component, and the suspicion in the
work order is confirmed with a hard artifact.**

## 8.1 — Which job writes the balances table, and which broker field it reads

**There is no broker integration for balances.** No job reads any broker field, because no
balance feed exists. Every write is human-originated or a local delta:

| # | Writer | File:line | Writes | `updated_by` |
|---|---|---|---|---|
| 1 | `update_balance()` — `POST /balances/update` | [portfolio.py:59-83](../../backend/api/portfolio.py#L59-L83) | `balance` (+ optional cash/BP/margin, COALESCEd) | `pivot_screenshot` |
| 2 | `create_cash_flow()` — `POST /api/portfolio/cash-flows` | [portfolio.py:350-356](../../backend/api/portfolio.py#L350-L356) | `cash = cash + $1`, **`balance = balance + $1`** | `cash_flow` |
| 3 | `_adjust_account_cash_with_conn()` | [unified_positions.py:80-86](../../backend/api/unified_positions.py#L80-L86) | `cash = cash + $1` **only** | `auto` |
| 4 | dashboard cash set | [unified_positions.py:1066](../../backend/api/unified_positions.py#L1066) | `cash = $1` **only** | `dashboard` |
| 5 | `reconcile_cash()` — `POST /v2/positions/reconcile-cash` | [unified_positions.py:2064-2072](../../backend/api/unified_positions.py#L2064-L2072) | `cash = $1` **only** | `cash_reconcile` |
| 6 | `init_database()` seed (empty-table guarded) | [postgres_client.py:969-995](../../backend/database/postgres_client.py#L969-L995) | initial rows | seed |

**`balance` is written by writers 1 and 2 only.** Writer 1 is a human typing a number off a
Fidelity/RH screenshot. Writer 2 adds a cash-flow delta. **Nothing ever adds position value
to `balance`, and writers 3/4/5 move `cash` without touching `balance`** — so the two fields
decouple with every position open/close.

The source field is therefore "whatever the human typed", and its semantic (account value vs
cash) depends entirely on which figure they read off the screenshot that day.

## 8.2 — `balance` vs `cash` vs positions-value, per account

There is **no positions-value column**. `account_balances` is
`(id, account_name, broker, balance, cash, buying_power, margin_total, updated_at, updated_by)`.

```
 account_name          broker      balance    cash      buying_power  balance−cash  updated_at                       updated_by
 Robinhood             robinhood    835.69   1070.00        1482.09      −234.31    2026-08-24 17:01:35.462841+00    auto
 BROKERAGE_LINK_401K   fidelity   11642.35  11642.35           NULL         0.00    2026-06-09 23:46:03.19288+00     pivot_screenshot; consolidated 401A+403B 2026-07-23
 Fidelity Roth         fidelity    8842.09   8935.49           NULL       −93.40    2026-08-01 19:35:26.257141+00    cash_reconcile
```

**Does `balance` ever exceed `cash` by the value of open positions? No — it never exceeds
`cash` at all.** In all three rows `balance ≤ cash`. Two are strictly negative on
`balance − cash`, which is impossible for an account holding long positions.

This confirms the work order's suspicion directly. Robinhood currently holds 19 open
positions yet reports `balance` **$234.31 below** its own cash.

## 8.3 — Are `total_balance` and `total_cash` computed from the same column?

**Different columns**, both in [portfolio_balances.py:119-120](../../backend/hub_mcp/tools/portfolio_balances.py#L119-L120):

```python
total_balance = sum(a["balance"] for a in accounts)   # <- balance column
total_cash    = sum(a["cash"] or 0 for a in accounts) # <- cash column
```

Given 8.2, `total_cash` ($21,647.84) currently **exceeds** `total_balance` ($21,320.13).

## 8.4 — The contamination artifact: `balance_snapshots.position_value`

`snapshot_account_balances()` ([portfolio.py:457-460](../../backend/api/portfolio.py#L457-L460))
runs after every mark-to-market during market hours and computes:

```python
position_value = round(balance - cash, 2)
```

It **assumes the invariant `balance = cash + position_value`** — exactly the invariant 8.1
and 8.2 show does not hold. The result is a corrupted historical series:

```
 total_snapshots  negative_position_value  accounts  first_snap   last_snap
             516                       52         6  2026-03-20   2026-08-24
```

```
 account_name          snaps  neg_pv  min_pv     max_pv     last_snap
 Fidelity Roth           112      29  −188.39    4979.65    2026-08-24
 Robinhood               112      23  −1168.82   1938.31    2026-08-24
 Interactive Brokers      90       0     0.00       0.00    2026-07-23
 Fidelity 401A            90       0     0.00   10107.90    2026-07-23
 Fidelity 403B            90       0     0.00     233.15    2026-07-23
 BROKERAGE_LINK_401K      22       0     0.00       0.00    2026-08-24
```

**52 of 516 snapshots (10.1%) carry a negative `position_value`** — down to −$1,168.82 on
Robinhood. A negative long-position value is not a plausible state; it is the arithmetic
artifact of subtracting a drifting `cash` from a stale hand-typed `balance`.

## 8.5 — Does Phase 1 need to write a value or compute one?

The question the item was posed to settle. Stating the evidence, not the remedy:

- `balance` cannot be *read* as account value — it is neither value nor cash consistently,
  and is up to 77 days stale on the Fidelity row.
- It cannot be *computed* from existing DB state either: `position_value` would have to come
  from `unified_positions` marks, and Item 6 establishes 6 of 25 open positions carry stale
  or absent marks, plus at least one fresh-but-wrong mark.
- Independent corroboration that a bottom-up computation is tractable: the work order reports
  a cash-ledger + live-quote reconstruction landing at $11,381.27 against a broker actual of
  $11,382.17 — a **$0.90** delta. That path works *when quotes are good*.

So the honest framing for spine: **computing is feasible but inherits the mark-integrity
seam** (DEF-MARK-INTEGRITY); **writing is simpler but re-creates the staleness** that
produced the $9,102.27 overstatement. Not resolvable from within this read-only lane.
Recommendation deferred to CC-BUILD's remedy brief.

---

# ITEM 9 — Scope reduction impact (read-only assessment)

## 9.1 — Full inventory: every site that enumerates accounts or reads balances

**Blast radius: 6 files, 34 sites.** No removal, no edit performed.

### Backend — account allowlists / identity maps (hardcoded)

| File:line | What |
|---|---|
| [hub_mcp/tools/portfolio_balances.py:31](../../backend/hub_mcp/tools/portfolio_balances.py#L31) | `Account` Literal type — 4 values |
| [hub_mcp/tools/portfolio_balances.py:33](../../backend/hub_mcp/tools/portfolio_balances.py#L33) | `_VALID_ACCOUNTS` set — 4 values |
| [hub_mcp/tools/portfolio_balances.py:35-40](../../backend/hub_mcp/tools/portfolio_balances.py#L35-L40) | `_DB_TO_NORMAL` map — 4 entries |
| [hub_mcp/tools/portfolio_balances.py:47-64](../../backend/hub_mcp/tools/portfolio_balances.py#L47-L64) | `_BREAKOUT_PROP_UNTRACKED` honest-absence block |
| [hub_mcp/tools/positions.py:36](../../backend/hub_mcp/tools/positions.py#L36) | `Account` Literal type — 4 values |
| [hub_mcp/tools/positions.py:40](../../backend/hub_mcp/tools/positions.py#L40) | `_VALID_ACCOUNTS` set — 4 values |
| [hub_mcp/tools/positions.py:49](../../backend/hub_mcp/tools/positions.py#L49) | normalize map `brokerage_link_401k` → `BROKERAGE_LINK_401K` |
| [api/unified_positions.py:59-64](../../backend/api/unified_positions.py#L59-L64) | **`ACCOUNT_DISPLAY_MAP`** — a *fifth* list, with `FIDELITY_401A` still live |
| [services/read_only/positions.py:57-69](../../backend/services/read_only/positions.py#L57-L69) | if/elif ladder over 4 account literals |

### Backend — balance readers / writers

| File:line | What |
|---|---|
| [services/read_only/balances.py:29-52](../../backend/services/read_only/balances.py#L29-L52) | `get_account_balances()` — the single read entry point (see the case defect, Item 1) |
| [api/portfolio.py:41-46](../../backend/api/portfolio.py#L41-L46) | `GET /balances` |
| [api/portfolio.py:59-83](../../backend/api/portfolio.py#L59-L83) | `POST /balances/update` — **writes `balance`** |
| [api/portfolio.py:350-356](../../backend/api/portfolio.py#L350-L356) | cash-flow — **writes `balance`** |
| [api/portfolio.py:387](../../backend/api/portfolio.py#L387) / [:414](../../backend/api/portfolio.py#L414) | reconcile reads / snapshot subquery |
| [api/portfolio.py:444-467](../../backend/api/portfolio.py#L444-L467) | `snapshot_account_balances()` — **writes `balance_snapshots`, incl. the bad `position_value`** |
| [api/unified_positions.py:67-74](../../backend/api/unified_positions.py#L67-L74) | `_match_account_balance()` — prefix/alias matcher |
| [api/unified_positions.py:80-86](../../backend/api/unified_positions.py#L80-L86) | cash adjust (writer) |
| [api/unified_positions.py:815-855](../../backend/api/unified_positions.py#L815-L855) | `/v2/positions/summary` rollup — **`FIDELITY` prefix sums all Fidelity rows** |
| [api/unified_positions.py:1066](../../backend/api/unified_positions.py#L1066) | dashboard cash writer |
| [api/unified_positions.py:2062-2072](../../backend/api/unified_positions.py#L2062-L2072) | `reconcile_cash()` writer |
| [database/postgres_client.py:759](../../backend/database/postgres_client.py#L759) | `account_balances` DDL |
| [database/postgres_client.py:969-995](../../backend/database/postgres_client.py#L969-L995) | seed block (empty-table guarded — see `def-seed-resurrection`) |

### Frontend

| File:line | What |
|---|---|
| [app.js:2454](../../frontend/app.js#L2454) | `fetch /api/portfolio/balances` |
| [app.js:8882](../../frontend/app.js#L8882) | `activePositionsAccount` — comment still names `FIDELITY_401A` |
| [app.js:8884-8889](../../frontend/app.js#L8884-L8889) | `matchesAccountFilter()` — `FIDELITY` = `startsWith('FIDELITY')` |
| [app.js:9441-9451](../../frontend/app.js#L9441-L9451) | summary widget fetch (hardcodes `account=FIDELITY_ROTH`) |
| [app.js:9540-9554](../../frontend/app.js#L9540-L9554) | `renderPortfolioSummaryWidget()` — **401A/403B rollup, see 9.3** |
| [app.js:9800](../../frontend/app.js#L9800), [:9842](../../frontend/app.js#L9842) | `POST /portfolio/balances/update` |
| [app.js:10701](../../frontend/app.js#L10701), [:10786-10787](../../frontend/app.js#L10786-L10787) | account `<option>` / default account |
| [index.html:496-498](../../frontend/index.html#L496-L498) | positions tabs: ALL / ROBINHOOD / FIDELITY |
| [index.html:595-597](../../frontend/index.html#L595-L597) | entry buttons: ROBINHOOD / FIDELITY_ROTH / **FIDELITY_401A** |
| [index.html:855](../../frontend/index.html#L855) | `<option value="ROBINHOOD">` |

### Data-side

`account_balances` (3 rows), `balance_snapshots` (516 rows, 6 distinct `account_name`),
`cash_flows.account_name`, `unified_positions.account`, `closed_positions.account`,
`portfolio_snapshots.account`, `trades.account`.

## 9.2 — Hardcoded or data-derived? **Both, in five separate places, and they disagree.**

The account list is hardcoded in **five** independent locations, not one:

1. `portfolio_balances.py:31/33` — `{robinhood, fidelity_roth, brokerage_link_401k, breakout_prop}`
2. `positions.py:36/40` — same four
3. `unified_positions.py:59-64` — **`ACCOUNT_DISPLAY_MAP`: `{ROBINHOOD, FIDELITY_ROTH, FIDELITY_401A, FIDELITY}`** — a different set. Still carries `FIDELITY_401A` (a row deleted 2026-07-23) and lacks `BROKERAGE_LINK_401K` entirely
4. `read_only/positions.py:57-69` — if/elif ladder, four literals
5. `frontend/index.html:595-597` + `app.js:8882` — UI buttons still offering **`FIDELITY_401A`**

And it is **also data-derived** in three places that enumerate whatever rows exist, with no
allowlist at all: `get_account_balances()` (no filter), `portfolio.py:41-46`, and
`unified_positions.py:832` — plus the frontend's `startsWith('FIDELITY')` prefix match.

**Consequence for a scope change:** editing `_VALID_ACCOUNTS` alone changes nothing about
what the summary endpoint, the snapshot job, or the frontend enumerate. A scope reduction
touches all five hardcoded sites **and** must decide what the three data-derived paths do
with rows that still exist in the table.

`ACCOUNT_DISPLAY_MAP` referencing `FIDELITY_401A`, and `index.html:597` still offering it as
an entry button, are **pre-existing drift** from the 2026-07-23 consolidation — not caused by
the proposed scope change, but they sit inside its blast radius.

## 9.3 — Does descoping break any historical series, attribution, or P&L baseline?

**Three findings; only one is a genuine break, and it is already broken.**

**(a) `balance_snapshots` — already frozen, nothing further to lose.** The AHRP rows
(`Fidelity 401A` 90 snaps, `Fidelity 403B` 90 snaps, `Interactive Brokers` 90 snaps) all stop
at **2026-07-23**, the consolidation date. They are already historical. Descoping AHRP
removes nothing that is still being written. The series is however **independently corrupted**
by the `position_value = balance − cash` defect (Item 8.4) — that is the real integrity
problem in this table, and it is unrelated to the scope change.

**(b) The frontend summary widget is already dropping the 401k row — silently.**
[app.js:9544-9554](../../frontend/app.js#L9544-L9554):

```javascript
let fid401a = 0, fid403b = 0;
for (const b of balances) {
    const name = (b.account_name || '').toLowerCase();
    if (name.includes('401a')) fid401a = b.balance || 0;
    if (name.includes('403b')) fid403b = b.balance || 0;
}
const fidRetirement = fid401a + fid403b;
const combinedBalance = rhBalance + fidRothBalance + fidRetirement;
```

It matches on the substrings `401a` / `403b`. Those rows were deleted 2026-07-23; the
surviving row is named `BROKERAGE_LINK_401K`, which contains **neither** substring. So
`fidRetirement` has been **0** since 2026-07-23, and the dashboard's headline
`combinedBalance` shows **$9,677.78** (RH + Roth) — while the MCP shows **$21,320.13**.

**The two surfaces disagree by $11,642.35 today**, and neither equals the true tradeable
$12,217.86. Descoping AHRP would not break this; it is already broken, in the opposite
direction from the MCP.

**(c) Attribution / P&L baseline — no dependency found.** `trades.account`,
`closed_positions.account`, and `unified_positions.account` hold `ROBINHOOD` /
`FIDELITY_ROTH` only. **Zero rows carry `BROKERAGE_LINK_401K`, `FIDELITY_401A`, or
`FIDELITY_403B` in any position or trade table.** `analytics/oracle_engine.py:274` and
`analytics/confluence_validation.py:18` aggregate on outcome fields, not account. No P&L
baseline includes AHRP balances, because AHRP never held a tracked position.

**Net:** descoping AHRP 401A/403B breaks **no live series**. The pre-existing breaks in this
area (the widget rollup, the snapshot arithmetic) are independent of it.

## 9.4 — Standing invariant check: ACCT-ROTH trades ETFs only

**INVARIANT HOLDS on asset class. One ticker flagged for the principal's eye.**

All Fidelity-side rows in `unified_positions`:

```
 account         asset_type  rows  tickers
 FIDELITY_ROTH   EQUITY        46  BITI, BITX, BTCZ, GDX, GDXJ, GDXY, GUSH, JNUG, MOO,
                                   MSTZ, NLR, NUGT, QQQI, SBU, SMST, SOXL, SOXS, SQQQ,
                                   SRTY, TLT, TSLQ, URA, XLE
```

- **Zero `OPTION` rows. Zero `SPREAD` rows.** The no-options half of the invariant holds
  cleanly across all 46 rows, open and closed.
- **Zero rows on `BROKERAGE_LINK_401K`** — consistent with the work order's statement that
  the row has no positions, and with the two-rows-one-account finding.
- 22 of the 23 tickers are recognisable ETFs/ETNs (leveraged, sector, and thematic).

**One flag — `SBU`.** It is the only ticker I cannot confirm as an ETF from repo or DB state.
It is absent from `stable_universe` (which does classify e.g. `SOXL` as `sector='ETF'`), so
there is no in-DB classification to appeal to. The row:

```
 position_id                 POS_SBU_20260429_031106
 status  CLOSED   qty 25   entry_price 18.24   source MANUAL
 entry_date  2026-04-29 03:11:06.732043+00
 exit_date   2026-04-29 03:11:46.720508+00     <-- 39.99 s later
```

Opened and closed **40 seconds apart** by manual entry, which reads more like a data-entry
artifact than a held trade. I am **not** asserting it is a violation — classifying `SBU`
requires a security master this repo does not have. **UNKNOWN; flagged for Nick.** If it is a
single-name, it is one closed row and a mis-attribution, not a live invariant breach.

**No violations found requiring action. No rows removed, no allowlist edited.**

---

# Summary across Items 1, 8, 9

| # | Item | Finding | Confidence |
|---|---|---|---|
| 1 | 1 | `total_balance` has **no programmatic consumer** — produced in one file, read by no other code. | Confirmed |
| 2 | 1 | The consumer is the **committee agent reading the MCP envelope**; the tool description directs it into sizing in six places. Advisory sizing since ≥2026-06-09 anchored to a figure **74.5% high** ($21,320.13 vs $12,217.86). | Confirmed |
| 3 | 1 | `hub_get_portfolio_balances(account="robinhood"\|"fidelity_roth")` returns **0 accounts, $0, status "ok"** — uppercase filter vs mixed-case rows. Fake-healthy. | Confirmed |
| 4 | 8 | **No broker balance feed exists.** `balance` is written only by a manual screenshot POST and cash-flow deltas. | Confirmed |
| 5 | 8 | `balance ≤ cash` in **all three rows** (two negative). `balance` carries **no positions-value component**. Suspicion confirmed. | Confirmed |
| 6 | 8 | `total_balance` sums `balance`; `total_cash` sums `cash` — **different columns**. `total_cash` currently exceeds `total_balance`. | Confirmed |
| 7 | 8 | `balance_snapshots.position_value = balance − cash` assumes an invariant that does not hold → **52/516 snapshots negative**, min −$1,168.82. Historical series contaminated. | Confirmed |
| 8 | 8 | Write-vs-compute: computing inherits the mark seam; writing re-creates staleness. Not resolvable read-only. | Deferred |
| 9 | 9 | Blast radius **6 files / 34 sites**; account list hardcoded in **five** places that **disagree**, plus 3 data-derived paths with no allowlist. | Confirmed |
| 10 | 9 | `ACCOUNT_DISPLAY_MAP` and `index.html:597` still reference **`FIDELITY_401A`**, deleted 2026-07-23. Pre-existing drift. | Confirmed |
| 11 | 9 | Frontend widget matches `401a`/`403b` substrings → **silently drops `BROKERAGE_LINK_401K` since 2026-07-23**. Dashboard shows $9,677.78 vs MCP $21,320.13 — a **$11,642.35** disagreement between two live surfaces. | Confirmed |
| 12 | 9 | Descoping AHRP breaks **no live series** — snapshots already frozen 2026-07-23; zero position/trade rows on any AHRP account. | Confirmed |
| 13 | 9 | ETF-only invariant **holds**: 46/46 Fidelity rows are EQUITY, zero options, zero spreads. | Confirmed |
| 14 | 9 | `SBU` is the one ticker not confirmable as an ETF (absent from `stable_universe`); closed row, open 40 seconds, likely a data-entry artifact. | **UNKNOWN** — flagged |

No fixes proposed. No writes, no migrations, no allowlist edits, no removals performed.
Remedy briefs route to CC-BUILD after spine rules.

---

# ITEM 10 — Normalizer: unaffected, and still the oldest open item

**Status: OPEN. Not started in this lane. Not blocked by anything in Items 1/6/7/8/9.**

Recorded per direction. This lane holds no Item 10 work order — what follows is a **status
and dependency note**, not findings.

## Why none of the preceding churn touches it

The pin dispute, the 7-commit `origin/main` delta, and the `+1` line offset are all
repo-state concerns. **The normalizer consumes no repo state**, verified by reading
`data/imports/normalize_fidelity_history.py` (138 lines) rather than assuming:

```
17: import argparse, hashlib, json, os
18: import pandas as pd
```

That is the complete import set. There is **no** `sys.path` manipulation, no
`get_postgres_client`, no `psycopg2`/`asyncpg`, no `.mcp.json` read, no `os.getenv`, and no
network call. It is a pure CSV→CSV transform driven by `argparse`, writing three files to an
`--outdir`:

```
130: fills.to_csv(... f"{stem}_fills_normalized.csv")
131: cash.to_csv (... f"{stem}_cash_events.csv")
132: open(       ... "import_reconciliation.json", "w")
```

It therefore produces **exactly the three artifacts Phase 0 reported as missing**, and its
behaviour is identical at `2de26c6` and at `origin/main` — the file is untracked and appears
in neither commit. Pinning, pulling, or rebasing changes nothing about it.

## Why it is the oldest open item in the thread

It is the residue of the original Phase 0 blocker. That blocker has been narrowed once but
never cleared:

| Artifact | Phase 0 (2026-08-25 00:13 UTC) | Now |
|---|---|---|
| `History_for_Account_ACCT-ROTH.csv` | absent | **present** (18,306 B, mtime 2026-08-24 12:23) |
| `normalize_fidelity_history.py` | absent | **present** (6,328 B, 138 lines) |
| `fidelity_ACCT-ROTH_fills_normalized.csv` | absent | **PRESENT — generated below** (8,733 B) |
| `fidelity_ACCT-ROTH_cash_events.csv` | absent | **PRESENT — generated below** (884 B) |
| `import_reconciliation.json` | absent | **PRESENT — generated below** (843 B) |

## EXECUTED — R-IV.80(h) ordered Item 10 first

Run 2026-08-25 06:12 UTC (2026-08-25 00:12 MDT), after `git pull --rebase` to `8b2d767`
per R-IV.80(c)'s fetch-before-write hygiene. No JSONB column is bound by this tool, so the
named hazard does not reach it; the rebase was taken for the broker-export ignore rules,
which it activated (all three outputs verified `git check-ignore` → IGNORED).

```
python data/imports/normalize_fidelity_history.py \
  --src data/imports/History_for_Account_ACCT-ROTH.csv \
  --account-number ACCT-ROTH --outdir data/imports
```

### Phase 0's on-faith figures — now VERIFIED first-hand

Every CSV-derived claim the parent brief carried unverified reproduces **exactly**:

| Claim (taken on faith in Phase 0) | Normalizer output | Verdict |
|---|---|---|
| 83 trade fills | `trade_fills: 83` | ✅ |
| 11 cash events | `cash_events: 11` | ✅ |
| Last pre-split fill `2026-07-14` | `split_boundary_last_pre: "2026-07-14"` | ✅ |
| First post-split fill `2026-07-15` | `split_boundary_first_post: "2026-07-15"` | ✅ |
| Window 2026-06-25 → 2026-08-24 | `date_range: ["2026-06-25","2026-08-24"]` | ✅ |

**Phase 0's blocker is CLEARED.** Nothing in the parent brief now rests on recall.

### Full reconciliation payload

```json
{ "account_number": "ACCT-ROTH", "source_rows_total": 94,
  "trade_fills": 83, "cash_events": 11,
  "date_range": ["2026-06-25", "2026-08-24"],
  "symbols": ["BITX","GDXJ","GUSH","RAMZ","SOXS","SQQQ","SSPC","WRTH","XLE"],
  "buys": 50, "sells": 33, "pre_split_rows": 16, "unsettled_rows": 7,
  "duplicate_same_day_fills": 0, "hash_collisions": 0,
  "gross_buy_notional": -32308.61, "gross_sell_notional": 33510.14,
  "total_fees": 0.85,
  "split_boundary_last_pre": "2026-07-14", "split_boundary_first_post": "2026-07-15",
  "net_share_flow_split_adjusted": {
    "BITX": 0.0, "GDXJ": 0.0, "GUSH": 30.0, "RAMZ": 0.0, "SOXS": -45.0,
    "SQQQ": 0.0, "SSPC": 0.0, "WRTH": 20.0, "XLE": -0.071 } }
```

**Import-safety signals:** `duplicate_same_day_fills: 0` and `hash_collisions: 0` — the
`fill_hash` column is unique across all 83 rows, so a fill-level import keyed on it would be
idempotent. `unsettled_rows: 7` (settle dates 2026-08-25) must not be treated as final.

### New findings the run surfaced — three reconciliation breaks

**(1) `POS_SOXS_20260610_154556` is OPEN in the DB but FLAT at the broker.**
Split-adjusted flows over the window net to **−45**, which exactly offsets the 45 shares the
DB still carries. Reconstructing the running balance backward from zero closes cleanly and
shows the book hitting flat on **2026-07-14** — the split boundary itself — then trading
round-trips post-split back to zero (pending one unsettled 10-share sell dated 2026-08-24).
The DB row still shows `status='OPEN'`, `quantity=45`, `unrealized_pnl=+465.97`, freshly
marked 2026-08-24. **A live fake-healthy position row carrying $465.97 of P&L on a flat
book.** Confirmation deferred to the mid-morning broker read.

**(2) GUSH quantity cannot be reconciled from this window.** Net flow is **+30**; the DB
carries 60 open. The first in-window GUSH fill is a BUY on 2026-07-24, and the position
opened 2026-06-09 — before the export starts — so the pre-window balance is not derivable
from this artifact. Ending quantity is **30 or 90** depending on it. **UNKNOWN; not
asserted.**

**(3) Three traded symbols have no representation in `unified_positions` at all.**
`RAMZ`, `SSPC`, `WRTH` return **zero rows** on any status. `RAMZ` and `SSPC` net to 0.0 —
round-tripped, so absence costs nothing. **`WRTH` nets +20 and is an untracked live
position.** This is coverage absence, not a stale row.

⚠️ The safety note below still applies to `docs/incidents/` — see (b) there, which the
rebase did **not** resolve.

---

# ⚠️ SAFETY — public repo, unignored broker data in this working tree

**Raised 2026-08-25 05:45 UTC (2026-08-24 23:45 MDT). Nothing is committed; this is a
pre-emptive flag, not a live exposure.**

> **UPDATE 2026-08-25 06:12 UTC — (a) RESOLVED, (b) STANDS.**
> The tree was rebased to `8b2d767` under R-IV.80(c) hygiene. Re-checked after:
> `data/imports/History_for_Account_ACCT-ROTH.csv` → **IGNORED**, as are all three
> normalizer outputs. Exposure (a) is closed.
> **Exposure (b) is unchanged and now the only one left:** the three `docs/incidents/`
> reports match no ignore rule at `8b2d767` either. Re-verified post-rebase — still
> `NOT IGNORED`. With R-IV.80(h) confirming BUILD's next batch sweeps untracked files,
> this needs a disposition before that batch runs.

`origin` is **`https://github.com/303webhouse/pandoras-box.git` — a PUBLIC repository.**

Commit `8b2d767` (pushed by a concurrent session at 23:40 MDT) added `.gitignore` rules for
exactly this risk:

```
37: # Broker/account exports are NEVER committed — this repo is PUBLIC.
38: # data/imports/ held an untracked Fidelity account-history CSV on 2026-08-25;
40: data/imports/
41: *_Trade_Updates.csv
42: RH_Report_*.csv
43: History_for_Account_*.csv
```

**Those rules are not in this working tree.** It sits at `2de26c6`, 7 commits behind, and its
local `.gitignore` stops at line 79. Confirmed by `git check-ignore`:

```
data/imports/History_for_Account_ACCT-ROTH.csv          NOT IGNORED
docs/incidents/FIDELITY_IMPORT_PHASE0.md                NOT IGNORED
docs/incidents/DEF-MARK-INTEGRITY.md                    NOT IGNORED
docs/incidents/FIDELITY_IMPORT_PHASE0B_ITEMS_1_8_9.md   NOT IGNORED
```

Two distinct exposures, one of which the new rules do **not** cover:

**(a) The broker CSV — covered on `origin`, uncovered here.** Pulling to `8b2d767` resolves
it. Until then a blanket `git add` in this tree would stage a real Fidelity account history.

**(b) These incident reports — covered by nothing, anywhere.** No `.gitignore` rule at
`origin/main` matches `docs/incidents/`. All three files carry material that does not belong
in a public repo: the account number **ACCT-ROTH** (in prose *and* in a filename), broker
balances ($11,382.17 / $11,642.35 / $8,842.09 / $835.69), per-position entry prices,
quantities, and realized P&L.

**Why this is urgent rather than theoretical:** `8b2d767`'s commit body records that
**"R-IV.76(h) ordered the next BUILD batch to sweep untracked files into the repo."** A sweep
executed against this tree would publish both (a) and (b) to a public GitHub repository.

**Recommended before any commit, sweep, or normalizer run — Nick's call, not taken here:**

1. `git pull --rebase` to `8b2d767` so the broker-export ignore rules are active locally.
2. Decide the disposition of `docs/incidents/`: redact the account number and balances, add
   an ignore rule, or relocate the reports outside the repo. **They are currently untracked
   and unignored — the worst of both states for a sweep.**
3. Only then run the normalizer, and confirm its outputs land under an ignored path.

No files were deleted, moved, redacted, or committed. No `.gitignore` was edited.
