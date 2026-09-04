# DEF-MARK-INTEGRITY — Item 6 (DEF-OPTIONS-MARK-STALE diagnosis)

**Status:** READ-ONLY diagnosis. No writes, no migrations, no code changes.
**Vintage:** read 2026-08-25 05:12 UTC (2026-08-24 23:12 MDT) · repo `2de26c6` · branch `main`
**Read path:** direct SQL via read-only Postgres MCP, `::text` casts on all timestamps.
`hub_get_positions` was NOT used for any position state (per standing instruction —
`positions.py:95` returns `None` for `closed_at` on all rows).

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
> `backend/api/unified_positions.py` was touched, solely by `073395f fix(p0): NaN-poison —
> close the JSONB bind class` (`json.dumps` → `dumps_jsonb` at bind sites). Every load-bearing
> element of this diagnosis is intact at `origin/main`: `run_mark_to_market` still selects
> `WHERE status = 'OPEN'` (:2225), the single mark UPDATE still stamps
> `price_updated_at = NOW(), updated_at = NOW()` (:2380), and both grading branches still
> derive `trade_outcome` from the supplied exit price (:1683 interactive, :1992 CSV) with no
> read of `current_price`. The Q4 conclusion — grading never consumes the mark — therefore
> holds at `origin/main`, not only at the pin.
>
> `backend/hub_mcp/tools/positions.py` was **not touched at all**; the `closed_at` defect
> cited in the read-path note is live at `origin/main` verbatim.
>
> **Line-number offset:** an added import at line 23 shifts everything below it by **+1** in
> `unified_positions.py`. Citations here read one line low against `origin/main`
> (`:2201` → `:2203`, `:2222` → `:2225`, `:2376-2383` → `:2379-2386`, `:1670-1681` →
> `:1671-1682`, `:1735-1748` → `:1736-1749`, `:1985-1991` → `:1986-1992`).

## Manifest (law v2)

| Scope | Rows | Fingerprint |
|---|---|---|
| `unified_positions` marks (`position_id\|current_price\|price_updated_at\|status`) | **329** | `f5cb12f1b32a825960cca30ef63684e1` |

---

## MERGE RULING — answer to the merge question

**ONE JOB WRITES BOTH. These are one defect on two asset classes. Merge.**

`run_mark_to_market()` in [`backend/api/unified_positions.py:2201`](../../backend/api/unified_positions.py#L2201)
is the sole writer of `current_price`, `unrealized_pnl`, and `price_updated_at`. Options and
equities are two *branches inside that one function*, terminating in a single UPDATE at
[unified_positions.py:2376-2383](../../backend/api/unified_positions.py#L2376-L2383):

```sql
UPDATE unified_positions SET
    current_price = $1, unrealized_pnl = $2,
    long_leg_price = $3, short_leg_price = $4,
    price_updated_at = NOW(), updated_at = NOW()
WHERE position_id = $5
```

- **Options / spreads** → Unusual Whales (`get_multi_leg_value` / `get_spread_value` /
  `get_single_option_value`), lines 2277–2350.
- **Equities** → yfinance `fast_info.last_price` fallback, lines 2355–2367, gated by
  `is_equity_position`.

DEF-OPTIONS-MARK-STALE and the POSITIONS-filed DEF-POSITIONS-MARK-PAST-CLOSE are therefore
**the same seam**. Recommend a single DEF. Spine holds the call.

**Filing-state note:** DEF-POSITIONS-MARK-PAST-CLOSE does not exist as a file in this repo.
The finding was recorded as Finding 9 of `FIDELITY_IMPORT_PHASE0.md`; no separate DEF was
ever written. There is nothing to merge *into* — this file is the merged filing.

---

## Q1 — Which column, which job, which file/function

| | |
|---|---|
| **Columns written** | `current_price`, `unrealized_pnl`, `long_leg_price`, `short_leg_price`, `price_updated_at`, `updated_at` |
| **Function** | `run_mark_to_market()` |
| **File** | `backend/api/unified_positions.py:2201` (UPDATE at :2376) |
| **HTTP wrapper** | `POST /v2/positions/mark-to-market` → `mark_to_market()` at :2392 |
| **Row selection** | `SELECT * FROM unified_positions WHERE status = 'OPEN'` (:2222) |
| **Options source** | Unusual Whales (`integrations.uw_api`) |
| **Equity source** | yfinance `fast_info.last_price` |

### Correction to the standing defect statement

**The mark job does not mark closed positions.** Its row selection is `WHERE status = 'OPEN'`
— closed rows are never fetched, so it cannot write to them.

This falsifies the Phase 0 Finding 9 wording ("the price updater continues marking rows past
close"). The real mechanism is the opposite:

> **Closing a position does not clear the live-mark fields.**

The close UPDATE at [unified_positions.py:1735-1748](../../backend/api/unified_positions.py#L1735-L1748)
sets `status`, `exit_price`, `exit_date`, `realized_pnl`, `trade_outcome`, `trade_id`,
`notes`, `updated_at` — and **leaves `current_price`, `unrealized_pnl`, and
`price_updated_at` untouched**, frozen at whatever the last live mark was.

A closed row can then show `price_updated_at > exit_date` whenever `exit_date` is
**backdated** — which the CSV-import close path does explicitly
([:1991-1996](../../backend/api/unified_positions.py#L1991-L1996), `exit_date_val` taken from
`item.exit_date`). The interactive `/close` path stamps `exit_date = now()`, so it cannot
produce the inversion on its own.

That is the correct causal chain for the $4,365.66 SOXS row: marked live while OPEN through
2026-07-17, then closed with a backdated `exit_date` of 2026-07-14 — the pre-split side of
the boundary — with the post-split mark left frozen on the row.

**Consequence for the fix brief (CC-BUILD's lane, not this one):** the remedy is at the
*close* path, not the mark path. Changing the mark job's row selection would fix nothing.

---

## Q2 — Mark-age distribution

### By status

```
 status    rows  has_mark  null_mark  oldest_mark                      newest_mark
 CLOSED     278       157        121  2026-03-02 21:49:47.271475+00    2026-08-24 16:47:03.70357+00
 EXPIRED     26        23          3  2026-04-10 22:12:34.862089+00    2026-08-04 13:17:09.613913+00
 OPEN        25        23          2  2026-07-24 13:17:09.792161+00    2026-08-24 20:47:11.741646+00
```

### OPEN positions — the set that matters (25 rows)

| Mark age | Rows | Positions |
|---|---|---|
| **Fresh (2026-08-24, ≤16h)** | **19** | SLV, SOXS, ORCL, QQQ×2, GUSH, XLE×2, GDXJ, TSLA, XLF×2, UBER, UVXY, USO, PLTR×2, WEAT, SPCX |
| 6 days (2026-08-18) | 2 | `POS_ABNB_20260811_130007`, `POS_TGT_20260817_130009` |
| 13 days (2026-08-11) | 1 | `POS_HYG_20260603_193356` |
| 31 days (2026-07-24) | 1 | `POS_BX_20260609_233603` |
| **Never marked (NULL)** | **2** | `POS_TRIN_20260727_120003`, `POS_BX_20260724_182213` |

**19 of 25 open positions (76%) carry a mark under 16 hours old.** The job is running and
succeeding for the large majority. Staleness is concentrated in **6 rows**, and every one of
them is an OPTION — the two equities in the stale/null set: none. All 6 stale/null rows are
`asset_type='OPTION'`; all 4 open EQUITY rows (SOXS, GUSH, XLE, GDXJ) marked fresh 08-24.

### How many closed rows carry a mark older than their own close

**15 rows** where `status <> 'OPEN' AND price_updated_at::date > exit_date::date`
(as reported in Phase 0; re-confirmed this run). Total |phantom `unrealized_pnl`| =
**$4,888.16**, of which `POS_SOXS_20260707_06000003` is **$4,365.66 (89%)**.

Separately, **121 CLOSED rows carry no mark at all** (`price_updated_at IS NULL`) — these are
import-origin rows that were never live in the mark loop. Honest absence, not staleness.

---

## Q3 — Correlation with the 2026-08-18 UW chain death

**The data does not support the hypothesis. Reporting as NOT-SUPPORTED; not promoting
anything to cause, and not proposing an alternative cause.**

Marks per calendar date (all rows carrying a mark):

```
 mark_date    rows  open_rows  option_rows  equity_rows
 2026-08-24     21         19           17            4
 2026-08-18      3          2            2            1
 2026-08-17      3          0            3            0
 2026-08-11      1          1            1            0
 2026-08-05      1          0            1            0
 2026-08-04      1          0            1            0
```

Three observations, each stated as measurement only:

1. **No clustering at 08-18.** Only **2 of 25** open rows carry a last-mark of 2026-08-18. If
   a chain outage on that date had stuck the book, the expected signature is most or all
   open option rows frozen at 08-18. Instead **17 open OPTION rows re-marked successfully on
   2026-08-24**, six days later.
2. **Two stale rows predate 08-18.** `POS_HYG_20260603_193356` last marked 2026-08-11 and
   `POS_BX_20260609_233603` last marked 2026-07-24 — both *before* the hypothesised event.
   A 08-18 outage cannot explain a mark that stopped on 07-24.
3. **Two rows have never been marked at all**, including one opened 2026-07-27 — again
   predating 08-18.

The staleness is **per-contract, not per-date**. What the 6 affected rows share is that they
are all options; what they do not share is a common last-mark date.

**Mechanism note (design, not cause-attribution):** the mark loop retains the prior price
when a pricing call fails, by deliberate change on 2026-05-14
([comment at :2384-2390](../../backend/api/unified_positions.py#L2384-L2390)) — a prior
version wiped the field to NULL on every UW 429. Under this design a contract UW cannot
price simply keeps its old `price_updated_at` forever and reads as "stale". So *staleness
here is the designed signature of repeated per-contract pricing failure*, and the honest
next question is which contracts UW declines to quote and why — **not answerable from DB
state, and not attempted here.** UNKNOWN.

### A finding that staleness does not explain — a *fresh* mark that is wrong

`POS_XLF_20260609_233128` (long put, XLF $30, exp 2026-10-16) carries
`current_price = 0.10`, `price_updated_at = 2026-08-24 20:47:08+00` — **freshly marked, 8
hours old**, showing `unrealized_pnl = +6.96`.

The principal's broker artifact (2026-08-25 00:59 ET, supplied in the work order) shows that
same leg at **last 0.01**, total G/L **−$65.04**.

The DB reports a small gain on a leg the broker reports as an 89% loss, from a mark taken
today. That is a **wrong value, not a stale one** — it does not fit the staleness frame at
all. Flagging it as a distinct observation for spine; cause unattributed, and I have not
determined whether the discrepancy originates in the UW quote, the `long_put` pricing
branch, or the quantity mismatch recorded in Item 7. **UNKNOWN.**

---

## Q4 — Does expiry/outcome grading consume the mark? (load-bearing)

**NO. Grading never reads `current_price`. The realized ledger is not corrupted by mark
staleness. Blast radius is display-only.**

Both grading paths compute P&L from an **explicitly supplied exit price**, never from the
mark:

**Path 1 — interactive close** ([unified_positions.py:1670-1681](../../backend/api/unified_positions.py#L1670-L1681)):
```python
if is_stock:
    realized_pnl = round((req.exit_price - entry_price) * close_qty, 2)      # req.exit_price
elif s in CREDIT_STRUCTURES:
    realized_pnl = round((entry_price - req.exit_price) * 100 * close_qty, 2)
else:
    realized_pnl = round((req.exit_price - entry_price) * 100 * close_qty, 2)

trade_outcome = "WIN" if realized_pnl > 0 else "LOSS" if realized_pnl < 0 else "BREAKEVEN"
```

**Path 2 — CSV import close** ([unified_positions.py:1985-1991](../../backend/api/unified_positions.py#L1985-L1991)):
```python
exit_price = item.exit_price                                                  # CSV field
realized_pnl = round((exit_price - item.entry_price) * 100 * item.quantity, 2)
trade_outcome = "WIN" if realized_pnl > 0 else ("LOSS" if realized_pnl < 0 else "BREAKEVEN")
```

`req.exit_price` is a request parameter; `item.exit_price` is a CSV column. Neither reads
`current_price`, `unrealized_pnl`, or `price_updated_at`. The grep for `trade_outcome =` and
`realized_pnl =` across `backend/`, `scripts/`, `pivot/` returns no other write site that
touches the mark.

### Settlement audit — 3 historical stamps

Verified by internal arithmetic (`realized_pnl` vs `(exit − entry) × qty × multiplier`),
which is the check that detects a mark leaking into grading:

| position_id | outcome | entry | exit | qty | stated `realized_pnl` | recomputed from exit | mark at the time (`current_price`) | verdict |
|---|---|---|---|---|---|---|---|---|
| `POS_SOXS_20260707_06000003` | LOSS | 4.67 | 4.00 | 87 (EQUITY) | **−58.30** | (4.00−4.67)×87 = **−58.29** | 54.85 → would imply **+4365.66** | ✅ graded from exit, **not** the mark |
| `POS_SOXS_20260609_230655` | WIN | 5.41 | 6.11 | 150 (EQUITY) | **105.00** | (6.11−5.41)×150 = **105.00** | 6.345 → would imply +140.25 | ✅ graded from exit |
| `POS_XLF_20260717_060000` | LOSS | 0.08086 | 0.00 | 5 (OPTION) | **−40.43** | (0−0.08086)×100×5 = **−40.43** | 0.065 → would imply −7.93 | ✅ graded from exit |

In all three the stated `realized_pnl` reproduces exactly from the exit price, and in all
three the mark would have produced a materially different — in the SOXS case a
**sign-flipped** — number. Grading demonstrably ignores the mark.

**Conclusion:** the realized ledger is sound. The seam is confined to `current_price` /
`unrealized_pnl` as *displayed* values. This does **not** downgrade the display defect —
$4,365.66 of phantom P&L is exposed through `hub_get_positions`, which emits
`unrealized_pnl` verbatim at [`positions.py:85`](../../backend/hub_mcp/tools/positions.py#L85)
— but it does bound the blast radius to every *displayed* outcome rather than every *graded*
one.

---

## TWO FACETS ADDED, BOTH HELD (R-IV.252(d))

Registered 2026-09-04. **HELD** — recorded, not fixed, and not scheduled here.

### Facet A — the 381-alarming / 407-flattering pair

Two positions whose P&L was **zeroed rather than computed against entry**. The pair is
the diagnostic: one reads alarming and one reads flattering, from the *same* defect. A
single-direction error would have been caught by whoever it hurt; a symmetric one hides,
because the flattering half suppresses the complaint the alarming half would have
generated.

**Zeroed is not computed.** A P&L of 0.00 against an entry the position actually has is
not a small error — it is the absence of the calculation, rendered in the same field and
format as a real result.

### Facet B — `update_position` (`backend/api/unified_positions.py:1486`) rewrites unrealized P&L with no status check

`update_position` (`backend/api/unified_positions.py:1486`) overwrites `unrealized_pnl` with **no guard on position status**, so a closed or
expired position is as writable as an open one.

**INERT ONLY WHILE `current_price` IS NULL.** That is the whole containment, and it is an
accident of the current data rather than a property of the code. **The moment
`current_price` is populated — which is exactly what the mark job exists to do — this
becomes live**, and it will rewrite P&L on positions that are no longer open.

**So the ordering matters:** anything that fixes or restarts the mark path arms this
facet. It is not safe to treat "no observed damage" as evidence the guard exists.

## Summary

| # | Finding | Confidence |
|---|---|---|
| 1 | One job (`run_mark_to_market`, unified_positions.py:2201) writes marks for both options and equities → **merge the two DEFs**. | Confirmed |
| 2 | The mark job selects `WHERE status = 'OPEN'` and **cannot** write to closed rows. The "marks past close" wording is wrong. | Confirmed |
| 3 | Real mechanism: **close does not clear `current_price`/`unrealized_pnl`/`price_updated_at`**; backdated `exit_date` on the CSV path then inverts the ordering. Remedy belongs at the close path. | Confirmed |
| 4 | 19/25 open positions marked within 16h. Staleness confined to **6 rows, all options**; 2 never marked. | Confirmed |
| 5 | 15 closed rows carry a mark newer than their close; $4,888.16 phantom, SOXS = 89%. | Confirmed |
| 6 | **Staleness does not cluster at 2026-08-18.** Two stale rows predate it; 17 open option rows re-marked on 08-24. Hypothesis NOT SUPPORTED. | Confirmed (measurement) |
| 7 | Why UW declines to quote the 6 affected contracts. | **UNKNOWN** — not answerable from DB |
| 8 | `POS_XLF_20260609_233128` carries a **fresh but wrong** mark (DB 0.10 / +6.96 vs broker 0.01 / −65.04). Not a staleness case. | Confirmed vs supplied artifact; cause **UNKNOWN** |
| 9 | **Grading never reads the mark.** Both paths grade from a supplied exit price; 3/3 settlement audits reproduce exactly. Realized ledger intact. | Confirmed |

No fix proposed — READ finding. Remedy brief routes to CC-BUILD.
