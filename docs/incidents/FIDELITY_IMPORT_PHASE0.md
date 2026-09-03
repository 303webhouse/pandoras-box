# FIDELITY-IMPORT-ACCT-ROTH — Phase 0 (READ-ONLY)

**Status:** Investigation complete. **No writes, no migrations, no code changes were made.**
**Run:** 2026-08-25 00:13 UTC (2026-08-24 18:13 MDT) · repo `2de26c6` · branch `main`
**DB:** Railway Postgres via read-only MCP (`mcp__postgres__query`)

> ### Code vintage pin — `2de26c6`
>
> Every source citation in this file was read at **`2de26c6`**, the session-open local HEAD.
> That is the pin; it is not `origin/main`.
>
> **As of 2026-08-25 05:45 UTC (2026-08-24 23:45 MDT), `origin/main` = `8b2d767`** — the
> working tree was **7 behind, 0 ahead** and has **subsequently been rebased to `8b2d767`** at 06:12 UTC under R-IV.80(c) fetch-before-write hygiene. The pin is unaffected: it records where the reads were taken, not the current tree. Remote state confirmed first-hand by
> `git ls-remote origin refs/heads/main`, not by the local remote-tracking ref alone.
> `origin/main` moved twice during this session (`cb77712` → `8b2d767`); concurrent sessions
> push `main`, so treat any pinned remote SHA here as a timestamped observation, not a
> current value.
>
> **Do the findings survive the 7-commit delta? Yes — verified, not assumed.**
> Two files these findings rest on were touched — `backend/api/unified_positions.py` and
> `backend/database/postgres_client.py` — both solely by `073395f fix(p0): NaN-poison —
> close the JSONB bind class`, which swaps `json.dumps` → `dumps_jsonb` at bind sites. None
> of the cited logic changed: the mark job still selects `WHERE status = 'OPEN'`, the mark
> UPDATE still stamps `price_updated_at = NOW()`, both grading branches still compute from
> the supplied exit price, and `ACCOUNT_DISPLAY_MAP` / `_match_account_balance` are
> unchanged. `backend/hub_mcp/tools/positions.py` was **not touched at all** — the
> `"closed_at": row.get("closed_at")` defect is live at `origin/main` verbatim.
>
> **Line-number offset:** an added import at line 23 shifts everything below it by **+1** in
> `unified_positions.py`. Citations here read one line low against `origin/main`
> (e.g. `:2201` → `:2203`, `:2222` → `:2225`, `:2377` → `:2380`, `:59` → `:60`, `:67` → `:68`).
> Line numbers in all other files are unaffected.

---

## Manifest (law v2)

| Artifact | Rows | Fingerprint / note |
|---|---|---|
| `unified_positions` | **329** | payload md5 `de6f00334b127fa2aae7b1a92d20dddb` over `position_id\|entry_price\|current_price\|exit_date\|trade_outcome` ordered by `position_id` |
| `rh_trade_history` | 1295 | fill-level, Robinhood-scoped |
| `trades` | 350 | position/ledger-level |
| `trade_legs` | 36 | fill-level, FK to `trades` |
| `cash_flows` | 23 | has dedup UNIQUE |
| `account_balances` | 3 | Robinhood / BROKERAGE_LINK_401K / Fidelity Roth |
| `fidelity_ACCT-ROTH_fills_normalized.csv` | — | **NOT PRESENT on this machine** (see Blocker) |
| `fidelity_ACCT-ROTH_cash_events.csv` | — | **NOT PRESENT** |
| `import_reconciliation.json` | — | **NOT PRESENT** |

### Blocker — import artifacts are absent

None of the three named artifacts exist in the repo or on this machine. Searched
`c:\trading-hub` (all files), `~/Downloads`, `~/Desktop`, `~/Documents`, and the session
scratchpad for `*ACCT-ROTH*`, `*fidelity*`, `*import_reconciliation*` — **zero hits**. The
string `ACCT-ROTH` also appears nowhere in the repo.

Every count in this brief that describes the CSVs (83 fills, 11 cash events, the
2026-07-14/2026-07-15 split boundary) is therefore **taken on faith from the brief and was
not independently verified**. Phase 1 cannot begin until the artifacts are supplied.

> **BLOCKER CLEARED 2026-08-25 06:12 UTC.** The normalizer was run under R-IV.80(h)
> (Item 10 ordered first). All three artifacts now exist, and every figure above
> reproduced exactly — 83 fills, 11 cash events, split boundary 07-14/07-15.
> Nothing in this brief still rests on recall. See ITEM 10 in
> [`FIDELITY_IMPORT_PHASE0B_ITEMS_1_8_9.md`](FIDELITY_IMPORT_PHASE0B_ITEMS_1_8_9.md).

---

## Q1 — Is there a fill-level table?

**Answer: YES — two, but neither is a general-purpose fill ledger, and neither is safe to
import into as-is.**

### `unified_positions` — position-level, 39 columns

**Correction to the brief:** the columns are **`entry_date`** and **`exit_date`**, not
`opened_at` / `closed_at`. Those two names exist only in the MCP response envelope. This
matters — it is the direct cause of the Q3 `closed_at: null` symptom (see Q3.2).

```
                            Table "public.unified_positions"
 id                integer      NOT NULL  nextval('unified_positions_id_seq')
 position_id       text         NOT NULL                    <-- UNIQUE
 ticker            text         NOT NULL
 asset_type        text         NOT NULL  'OPTION'
 structure         text
 direction         text         NOT NULL
 legs              jsonb
 entry_price       numeric
 entry_date        timestamptz  NOT NULL  now()
 quantity          integer      NOT NULL  1
 cost_basis        numeric
 max_loss          numeric
 max_profit        numeric
 stop_loss         numeric
 target_1          numeric
 target_2          numeric
 breakeven         numeric[]
 current_price     numeric
 unrealized_pnl    numeric
 price_updated_at  timestamptz
 expiry            date
 dte               integer
 long_strike       numeric
 short_strike      numeric
 source            text         NOT NULL  'MANUAL'
 signal_id         text
 account           text                   'ROBINHOOD'
 notes             text
 tags              text[]
 status            text         NOT NULL  'OPEN'
 exit_price        numeric
 exit_date         timestamptz
 realized_pnl      numeric
 trade_outcome     text
 trade_id          integer
 created_at        timestamptz            now()
 updated_at        timestamptz            now()
 long_leg_price    numeric
 short_leg_price   numeric

Constraints:
  "unified_positions_pkey"            PRIMARY KEY (id)
  "unified_positions_position_id_key" UNIQUE (position_id)
```

There are **no CHECK constraints, no foreign keys, and no triggers** on this table.
`account` is plain `text` with default `'ROBINHOOD'` — see Q2.

### Tables matching `%fill%` / `%execution%` / `%transaction%` / `%trade%` / `%ledger%`

```
account_balances     closed_positions     options_positions    pending_trades
cash_flows           position_sync_audit  positions            rh_trade_history
trade_legs           trade_watchlist      trades               unified_positions
```

Nothing matches `%fill%` or `%execution%`. The two genuine fill-level tables are:

**`rh_trade_history` (1295 rows)** — the closest structural match to the CSV. One row per
execution, with `activity_date`, `settle_date`, `ticker`, `description`, `trans_code`,
`quantity`, `price`, `amount`, `is_option`, `option_type`, `strike`, `expiry`,
`trade_group_id`, `signal_id`, `occurrence`. **It has no account column** — the name and
schema scope it to Robinhood. Importing Fidelity fills here would silently commingle two
brokers in a table whose consumers assume one.

**`trade_legs` (36 rows)** — `trade_id` (FK → `trades.id`), `timestamp`, `action`,
`direction`, `quantity`, `price`, `strike`, `expiry`, `leg_type`, `commission`, `notes`.
Fill-shaped, but every row must hang off a parent `trades` row, and it carries **no unique
constraint at all**.

**`signal_outcomes` (18283 rows)** — carries **no fills**. It is strictly signal → outcome
pairs: `signal_id` (UNIQUE), `symbol`, `signal_type`, `direction`, `cta_zone`, `entry`,
`stop`, `t1`, `t2`, `invalidation_level`, `outcome`, `outcome_at`, `outcome_price`,
`max_favorable`, `max_adverse`, `days_to_outcome`. Not an import target.

### Idempotency — which UNIQUE constraints would make a re-import safe?

| Table | Constraint | Re-import idempotent? |
|---|---|---|
| `rh_trade_history` | `UNIQUE NULLS NOT DISTINCT (activity_date, ticker, description, trans_code, quantity, price, occurrence)` | **Yes** — but the key has no account column, so two brokers' identical fills would collide |
| `cash_flows` | `UNIQUE NULLS NOT DISTINCT (account_name, flow_type, amount, description, activity_date, imported_from)` | **Yes** — and it *does* include the account. Best-shaped target found for the 11 cash events |
| `unified_positions` | `UNIQUE (position_id)` | Only if the importer mints deterministic `position_id`s |
| `trades` | PK on `id` only | **No** |
| `trade_legs` | PK on `id` only | **No** |

**No table was created. Nothing was altered.**

---

## Q2 — Which account is `ACCT-ROTH`?

**Answer: UNKNOWN. The mapping does not exist in the database. Nick must supply it.**

Scanned all 16 tables that contain an account-ish column or any position/trade/cash data,
casting each full row to text:

```
       tbl            hits   total
 account_balances       0       3
 balance_snapshots      0     516
 cash_flows             0      23
 close_attempts         0      94
 closed_positions       0     150
 options_positions      0       0
 pending_trades         0       0
 portfolio_snapshots    0      31
 positions              0       0
 position_sync_audit    0      20
 rh_trade_history       0    1295
 system_config          0       1
 trade_legs             0      36
 trades                 0     350
 unified_positions      0     329
 weekly_reports         0       0
```

**Zero hits.** There is no account-number mapping table anywhere in the schema — the only
account-identifying columns in the entire DB are `account_balances.account_name` /
`.broker`, and `account`/`account_name` free-text columns on six other tables. None holds a
number.

`account_balances` in full:

```
 id  account_name          broker      balance    cash       updated_by
  1  Robinhood             robinhood     835.69   1070.00    auto
  2  BROKERAGE_LINK_401K   fidelity    11642.35  11642.35    pivot_screenshot; consolidated 401A+403B 2026-07-23
  4  Fidelity Roth         fidelity     8842.09   8935.49    cash_reconcile
```

### Correction: there is no schema enum

The brief states "the schema enum has four values." **No enum type exists in this database**
— `SELECT ... FROM pg_enum` returns zero rows, and `unified_positions.account` is plain
`text` with no CHECK constraint. The four values are a **Python-level allowlist**:

```
backend/hub_mcp/tools/positions.py:36           _VALID_ACCOUNTS = {"robinhood",
backend/hub_mcp/tools/portfolio_balances.py:33   "fidelity_roth", "brokerage_link_401k", "breakout_prop"}
```

Nothing in the DB enforces it. `unified_positions` today holds only two distinct values:

```
 account         rows   first_entry   last_entry
 ROBINHOOD        283    2026-01-05    2026-08-18
 FIDELITY_ROTH     46    2026-03-11    2026-06-18
```

**Note for Phase 1:** there are **zero** `BROKERAGE_LINK_401K` rows in `unified_positions`,
and the existing `FIDELITY_ROTH` rows stop at **2026-06-18** — a week before the import
window opens (2026-06-25). Whichever account `ACCT-ROTH` turns out to be, the import window
barely overlaps existing position data. Do not guess; ask.

---

## Q3 — Split contamination audit

The brief's three premises each turned out to be **partly or wholly incorrect**. Correcting
them changes the scope of Phase 1 substantially, so each is walked through below.

### Q3.1 — Rows where `entry_price` is inconsistent with price history by >5x

**Answer: NOT ANSWERABLE AS ASKED — there is no in-DB price history for these tickers.**

- `price_history` — **0 rows** (empty table).
- `stable_daily_bars` — 855,433 rows, but covers **none** of the tickers in question.

```
 ticker  unified_positions rows  rows with any bar coverage
 SOXS              15                      0
 SQQQ               4                      0
 GUSH               3                      0
 BITX               2                      0
 RAMZ               0  (ticker not present in unified_positions)
```

Across the whole table: **130 distinct tickers, 75 have bar coverage; 221 of 329 rows are
covered, 108 are not.** Every leveraged ETF named in the brief falls in the uncovered set.
The requested comparison cannot be performed against DB state. Flagging as **UNKNOWN**
rather than substituting a vendor call.

**What can be measured instead** — a self-contained internal-consistency test comparing each
row's own `entry_price` against its own `current_price`. Run across all 329 rows, the
unrestricted test returns 40 rows, but it is **dominated by ordinary option decay** (a
`0.63 → 0.01` option is normal expiry, not a split). Restricting to `asset_type='EQUITY'`,
where a share-count split actually shows:

```
 equity rows with >5x entry/current divergence:  1
```

**Exactly one row**, and it is the one from the brief:

```
 position_id                  ticker status  qty  entry  current  ratio  exit_px  realized
 POS_SOXS_20260707_06000003   SOXS   CLOSED   87   4.67    54.85  11.75     4.00    -58.30
```

### Q3.2 — Rows with `trade_outcome IN ('WIN','LOSS')` AND no close timestamp

**Answer: ZERO. The brief's premise is incorrect — and the reason it looked true is a real,
separate, confirmed bug.**

```
 check_name                          n
 WIN_LOSS_with_null_exit_date        0
 WIN_LOSS_total                    259
 status_CLOSED_with_null_exit_date  11   (all have trade_outcome NULL, not WIN/LOSS)
```

All 259 WIN/LOSS rows carry a populated `exit_date`. The data is sound.

**The bug is in the MCP serializer.** [`backend/hub_mcp/tools/positions.py:95`](../../backend/hub_mcp/tools/positions.py#L95):

```python
"opened_at": row.get("entry_date") or row.get("created_at"),   # line 94 — correct
"closed_at": row.get("closed_at"),                             # line 95 — always None
```

Line 94 correctly maps `entry_date` → `opened_at`. Line 95 reads a key named `closed_at`,
which **does not exist on this table** — the column is `exit_date`. `row.get()` returns
`None` every time. So `hub_get_positions` reports **every position that has ever existed as
never-closed**, including all 259 with a real close timestamp.

This is an honest-seam violation of the same class the brief cites, but it is a **read-lens
bug, not a data bug** — and it is not confined to SOXS/GUSH. It affects 100% of rows.
Filed here as an observation; no fix proposed per Phase 0 scope.

### Q3.3 — The `$4,365.66`: real, but not what the brief describes

The brief reads `POS_SOXS_20260707_06000003` as a pre-split entry marked against a
post-split price, producing fabricated P&L. **The number is fabricated, and the mechanism is
adjacent to but distinct from the one described.**

Full row:

```
 position_id     POS_SOXS_20260707_06000003    status           CLOSED
 entry_price     4.67                          entry_date       2026-07-07
 exit_price      4.00                          exit_date        2026-07-14   <-- last pre-split day
 quantity        87                            realized_pnl     -58.30
 current_price   54.85                         price_updated_at 2026-07-17   <-- 3 days AFTER close
 unrealized_pnl  4365.66
```

- **`realized_pnl` is correct.** `(4.00 − 4.67) × 87 = −58.29 ≈ −58.30`. Entry, exit, and
  quantity are all coherent pre-split units. For a closed trade, this is the number that
  matters, and it is right.
- **`unrealized_pnl` is the fabricated field.** `(54.85 − 4.67) × 87 = 4365.66` — exact. The
  price updater kept marking a **closed** row for 3 days past its close, and in doing so
  walked it across the 07-14/07-15 split boundary, stamping a post-split `current_price`
  onto a pre-split cost basis.

So the defect is **"the price updater marks closed positions"**, and the split boundary is
what turned a harmless stale mark into a $4,365.66 one. Systematically:

```
 closed rows still marked after their close date:  15
   ...of those, |unrealized_pnl| > $100:            2
 sum of |phantom unrealized_pnl| across all 15:  $4,888.16
```

`POS_SOXS_20260707_06000003` alone accounts for **$4,365.66 of that $4,888.16 (89%)**. The
other 14 are small ($166 down to $0). The split is what made this row the outlier; the
underlying marking defect is general.

Because `_build_position` emits `unrealized_pnl` verbatim, **the $4,365.66 is exposed
through `hub_get_positions`.** The fake-healthy exposure is real.

### Q3.4 — The "internal inconsistency" is backwards

The brief flags rows 2 and 3 as one-adjusted / one-not, in the same table. Checked against
[`scripts/def_position_integrity.py`](../../scripts/def_position_integrity.py), which already
performed a SOXS 1-for-10 correction under DEF-POSITION-INTEGRITY:

| Row | Units | Verdict |
|---|---|---|
| `POS_SOXS_20260610_154556` — qty 45, entry **40.395**, OPEN | POST | **Already correctly adjusted.** This is the one STRADDLING row the prior script fixed: pre-split `4.0395 × 10 = 40.395`, qty `450 / 10 = 45`. Unrealized `(50.75 − 40.395) × 45 = 465.98` ✓ |
| `POS_SOXS_20260609_230655` — qty 150, entry **5.41**, CLOSED 06-10 | PRE | **Correct as-is.** Opened and closed entirely pre-split. Realized `(6.11 − 5.41) × 150 = 105.00` ✓ |

These two rows are not inconsistent with each other — one is a live position correctly
carried in post-split units, the other a closed pre-split trade correctly left in pre-split
units. **A blanket re-adjustment of SOXS rows in Phase 1 would corrupt both**, and would
double-apply the ×10 to `POS_SOXS_20260610_154556` (the prior script guards this with
`WHERE entry_price < 20`; a new importer would not inherit that guard).

The one genuinely mixed-unit row is `POS_SOXS_20260707_06000003` — pre-split
entry/exit/quantity, post-split `current_price`.

### Q3.5 — Split-adjustment / corporate-actions infrastructure

**Answer: NONE EXISTS.**

- No table matching `%split%`, `%corporate%`, or `%adjust%` — the schema has 66 tables, none qualify.
- No column matching `%split%`, `%adjust%`, `%corp%`, `%cusip%`. The only `%ratio%` hits are
  unrelated (`flow_events.pc_ratio`, `stable_metrics.vol_ratio`, `ticker_profiles.pe_ratio`,
  `strategy_health.mfe_mae_ratio`, `squeeze_scores.uw_put_call_ratio`).
- No adjustment log. The closest thing is `position_sync_audit` (20 rows) — a generic
  before/after JSONB audit trail, not corporate-action-aware.
- The only split handling that exists anywhere is **two one-off scripts**:
  `scripts/def_position_integrity.py` (the SOXS ×10 correction, keyed to a single hardcoded
  `position_id`) and `scripts/reconcile_soxs_xlf_dry_run.py` (groups by CUSIP so a
  corporate-action CUSIP change is visible).

There is no standing mechanism. Every split is handled by hand, per incident.

---

## Summary of findings

| # | Finding | Confidence |
|---|---|---|
| 1 | **Import artifacts are absent from this machine.** All CSV-derived figures unverified. Phase 1 blocked. | Confirmed |
| 2 | No general fill-level table. `rh_trade_history` is closest but has **no account column**; `trade_legs` requires a parent `trades` row and has **no unique constraint**. | Confirmed |
| 3 | `cash_flows` has the only account-aware dedup key — best-shaped target for the 11 cash events. | Confirmed |
| 4 | **`ACCT-ROTH` appears nowhere in the DB.** No mapping table exists. Needs Nick. | Confirmed |
| 5 | **No account enum exists in the DB** — it is a Python allowlist; `account` is unconstrained `text`. | Confirmed |
| 6 | **`hub_get_positions` reports every position as never-closed** — `positions.py:95` reads `closed_at` on a table whose column is `exit_date`. Affects 100% of rows, not just SOXS/GUSH. | Confirmed |
| 7 | Zero rows have WIN/LOSS with a null close timestamp. The brief's premise came from finding 6. | Confirmed |
| 8 | The `$4,365.66` is real and exposed, but is **stale-marking of a closed row across the split boundary** — `realized_pnl` (−58.30) is correct. | Confirmed |
| 9 | **15 closed rows are still being price-marked after close**, $4,888.16 total phantom P&L; the SOXS row is 89% of it. General defect, not SOXS-specific. | Confirmed |
| 10 | `POS_SOXS_20260610_154556` is **already correctly adjusted** by prior DEF-POSITION-INTEGRITY work. A blanket Phase-1 re-adjustment would double-apply ×10. | Confirmed |
| 11 | Split-contamination count across all tickers is **UNKNOWN** — no in-DB price history for any leveraged ETF (`price_history` empty; `stable_daily_bars` covers 0 of them). | Unknown — unresolvable from DB |
| 12 | **No corporate-actions table, column, or adjustment log exists.** Splits are handled by one-off scripts. | Confirmed |

No fix is proposed — Phase 0 is investigation only.

## Open questions for Nick

1. **Which account is `ACCT-ROTH`** — `fidelity_roth` or `brokerage_link_401k`? Not
   derivable from any repo or DB state.
2. **Where are the three artifacts?** Nothing can be verified or imported without them.
3. Findings **6** and **9** are live P0-class honest-seam bugs that exist independently of
   this import. Do they get their own DEF filings, or ride along with Phase 1?

---

# ADDENDUM — ITEM 7: XLF 10/16 grouping check

**Appended 2026-08-25 05:12 UTC (2026-08-24 23:12 MDT) · repo `2de26c6`**
**READ-ONLY.** No correction, no write, no representation change. Scope per the Phase 0b
addendum: the missing-leg hunt is CANCELLED; the three-leg structure is confirmed by design.
The only live question is **one broker order or two**.

**Read path:** direct SQL, `::text` on all timestamps. `hub_get_positions` not used.

## Manifest

| Scope | Rows | Fingerprint |
|---|---|---|
| `unified_positions` WHERE ticker='XLF' AND expiry='2026-10-16' (`position_id\|entry_date\|long_strike\|short_strike`) | **2** | `3fa5b6e0fcaccf4056bf036e0eb4baa7` |
| `trades` WHERE ticker='XLF' | 13 | — |
| `trade_legs` (entire table, all tickers) | 36 | — |

## Artifact status update (supersedes the Phase 0 blocker)

`data/imports/` now exists (untracked) and contains
`History_for_Account_ACCT-ROTH.csv` (18,306 bytes, mtime 2026-08-24 12:23) and
`normalize_fidelity_history.py` (6,328 bytes). The **raw** export has arrived. The three
artifacts named in the original Phase 0 brief — `fidelity_ACCT-ROTH_fills_normalized.csv`,
`fidelity_ACCT-ROTH_cash_events.csv`, `import_reconciliation.json` — are **still absent**;
only the raw history plus a normalizer script are present. Phase 0's blocker is narrowed,
not cleared.

## 7.1 — Every XLF 10/16 row in the DB

### `unified_positions` — exactly TWO rows (three legs). No phantom fourth leg.

| position_id | structure | qty | long_strike | short_strike | entry_price | current_price | unrealized_pnl | entry_date | exit_date | source | account |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `POS_XLF_20260609_233055` | `put_debit_spread` | 4 | 45 | 40 | 0.1455 | 0.01 | −54.20 | `2026-06-09 23:30:55.068149+00` | NULL | MANUAL | ROBINHOOD |
| `POS_XLF_20260609_233128` | `long_put` | 4 | 30.0 | NULL | 0.0826 | 0.10 | +6.96 | `2026-06-09 23:31:28.457455+00` | NULL | MANUAL | ROBINHOOD |

Both `status='OPEN'`, both `exit_date IS NULL`, both `legs` JSONB = NULL.

The count is **2 rows / 3 legs**, not 3 rows — the 45/40 put debit spread is modelled as one
row carrying `long_strike`+`short_strike`. That is the table's normal spread representation,
not a missing row. **Confirmed: no short 35, no fourth leg, in any table.** A full scan of
all 10 XLF rows in `unified_positions` (every expiry, closed rows included) shows no 35
strike anywhere.

### `trades` — ONE row, explicitly modelled as a 3-leg structure

```
 id      581
 ticker  XLF                      structure  put_3leg_45_40_30
 status  open                     origin     imported
 entry_price 0.36                 quantity   2.00000000
 long_strike 45.00   short_strike 40.00   strike 30.00
 expiry  2026-10-16
 opened_at   2026-06-08 06:00:00+00        closed_at  NULL
 notes   "XLF 10/16 3-leg: long 45 put x2 / short 40 put x2 / long 30 put x2
          (RH screenshot 2026-07-12). ~$0.36 debit/unit."
```

### `trade_legs` — ZERO XLF rows

The table holds 36 rows total, covering NVDA, SPCH, TQQQ, META, IWM, DRAM, SLV, USO, XLE,
AAPL, HYG. **No XLF row of any expiry exists.** There is no leg-level record of this
position anywhere in the database.

## 7.2 — The 06-09 order records

**There are no broker order records in the database.** This is the finding, and it is what
decides the item.

- No table in the schema has an order-id column. `trades` has no `order_id`; `trade_legs`
  has none; neither does `unified_positions`.
- Both surviving records are **human-origin reconstructions**, not order-feed captures:
  `unified_positions` rows are `source='MANUAL'`; `trades` id 581 is `origin='imported'` with
  notes citing an **RH screenshot dated 2026-07-12** — a month after the fact.
- The two record sets **disagree on the trade date itself**: `trades` says `opened_at
  2026-06-08 06:00:00+00` (a date-only midnight stamp), `unified_positions` says
  `2026-06-09 23:30:55`. They cannot both be the fill time.

### On the 33-second gap

```
POS_XLF_20260609_233128.entry_date   2026-06-09 23:31:28.457455+00
POS_XLF_20260609_233055.entry_date   2026-06-09 23:30:55.068149+00
                          delta =              33.389306 s
```

The gap reproduces exactly as described. **But it is not evidence about the broker.**
`unified_positions.entry_date` carries a schema default of `now()`, and both rows are
`source='MANUAL'` — so 23:30:55 and 23:31:28 UTC are the timestamps at which the two rows
were **typed into the dashboard**, ~17:31 MDT on 2026-06-09. Two manual entries 33 seconds
apart is exactly what one person entering a spread and then a single leg looks like.

The 33-second delta therefore measures data-entry cadence, not order routing, and **cannot
distinguish one broker order from two.**

## 7.3 — Which account

**ROBINHOOD**, on both `unified_positions` rows and on `trades` id 581 (`account='robinhood'`).

This confirms the work order's expectation: it is not the Fidelity account under review. The
Fidelity export contains zero options rows, and `unified_positions` independently agrees —
all 46 `FIDELITY_ROTH` rows are `asset_type='EQUITY'`, zero options (see Item 9.4).

## Ruling against the stated interpretation rubric

The work order offers two outcomes. **Neither is reachable**, and saying so is the honest
result:

> **One order in the broker, two records in the DB** -> grouping defect (cosmetic).
> **Two orders in the broker** -> DB faithful, no defect, close the thread.

Both branches condition on *what the broker did*. The database holds **no broker record** —
no order ids, no leg-level fills, no order-feed capture, and two mutually inconsistent
human reconstructions. **The broker-side question is UNKNOWN and is not answerable from DB
state.** Resolving it requires the Robinhood order history for 2026-06-08/09, which is not
in this repo or this database.

What *is* established, and is a finding in its own right:

**The two tables represent the same position incompatibly.** `trades` models it as **one**
3-leg order (`structure='put_3leg_45_40_30'`); `unified_positions` models it as **two**
independent positions. That is an internal representation inconsistency — the outcome-A
*shape* — but it is a disagreement between two DB tables, not evidence about the broker.
Cosmetic for risk (defined-risk throughout, as the work order states). Relevant to
FEAT-POSITION-LIFECYCLE.

### Quantity disagreement — three sources, three numbers

Flagged as a read observation, not chased:

| source | contracts per leg | implied net basis |
|---|---|---|
| Broker (principal screenshot, 2026-08-25) | **8** | $111.04 |
| `unified_positions` | **4** | 0.1455x100x4 + 0.0826x100x4 = **$91.24** |
| `trades` id 581 | **2** ("x2" in notes) | 0.36x100x2 = **$72.00** |

No two agree. The DB's net open loss (−54.20 + 6.96 = **−$47.24**) does not reconcile with
the broker's **−$103.04**. Per the work order this item authorises **no correction**, so
this is recorded and left.

The 30-put leg additionally carries a fresh-but-wrong mark (DB 0.10 vs broker 0.01) — filed
separately as Finding 8 of [`DEF-MARK-INTEGRITY.md`](DEF-MARK-INTEGRITY.md).

## Item 7 summary

| # | Finding | Confidence |
|---|---|---|
| 1 | `unified_positions`: exactly 2 rows / 3 legs. **No phantom fourth leg** in any table. | Confirmed |
| 2 | `trades` id 581 models it as ONE 3-leg order (`put_3leg_45_40_30`). | Confirmed |
| 3 | `trade_legs` holds **zero** XLF rows — no leg-level record exists. | Confirmed |
| 4 | **No broker order record exists anywhere in the DB** — no order-id column in any table. | Confirmed |
| 5 | The 33-second gap is manual data-entry cadence (`entry_date` defaults to `now()`, `source='MANUAL'`), **not** order timing. | Confirmed |
| 6 | **One broker order or two — UNKNOWN.** Not answerable from DB state; needs RH order history. | Unknown |
| 7 | `trades` and `unified_positions` represent the same position incompatibly (1 row vs 2). Representation defect; cosmetic for risk. | Confirmed |
| 8 | Quantity disagrees three ways: broker 8, `unified_positions` 4, `trades` 2. | Confirmed |
| 9 | Account is **ROBINHOOD** — confirmed distinct from the Fidelity import. | Confirmed |
