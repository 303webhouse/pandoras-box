# DEF-BALANCE-COLUMN-SEMANTICS

**Severity:** P2 · **Registered:** 2026-08-25 (R-IV.80d condition 7) ·
**FILED AS A DOCUMENT:** 2026-09-05 (R-IV.264(c))
**Status:** OPEN — undiagnosed. No mechanism asserted, and one previously asserted has been
**withdrawn** (see FALSIFIED).
**Owner:** CC-POSITIONS (evidence) · CC-BUILD (surface)
**Surface:** `account_balances.balance` — and its relationship to `account_balances.cash`
**Binding consequence in force:** *"Balance/cash columns untouched — semantics undefined"*
(R-IV.80d condition 7). No import, backfill or normalizer may write either column.

> **LINEAGE — registered in relay, never filed.** Cited as established in **4 documents
> across 5 citation lines** with no file of this name in the tree:
>
> | document | line(s) |
> |---|---|
> | `docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.80d.md` | 78 |
> | `docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.94b.md` | 22 · 69 |
> | `docs/incidents/RH-BOOK-DISCREPANCY.md` | (§4a) |
> | `docs/incidents/RH_FACE_AND_CASH_EVENTS.md` | (§1c) |
>
> Spine's `n=5` is the **line** count; the **document** count is 4. Both are listed because
> conflating them is the error this lane has now made or caught three times.

---

## THE DEFECT

`balance` has **no defined meaning**. Measured against the only two candidate readings, on
the Robinhood row at the 2026-08-25 read:

| if `balance` means… | expected | actual | verdict |
|---|---|---|---|
| account value | ≥ cash, ≈ 1070.00 + 478.50 = **1548.50** | 835.69 | inconsistent |
| cash | **1070.00** | 835.69 | inconsistent |

**835.69 is inconsistent with both.** That is the defect: not that the number is wrong, but
that there is no reading of the column under which it is right.

### `balance` never sees positions

Complete write path (Phase 0b §8.1):

1. `POST /balances/update` — **a human typing a screenshot figure** (`updated_by='pivot_screenshot'`)
2. `cash_flows` — `balance = balance + amount` (`updated_by='cash_flow'`)

**Three other writers move `cash` and never touch `balance`.** No position-derived quantity
enters `balance` inside the DB at all — so marks, long legs and short legs are all incapable
of moving it.

---

## FALSIFIED — do not re-derive these

- **"Structurally impossible."** POSITIONS' original phrasing, **withdrawn**. It was
  mechanism-from-symptom: you cannot call a value of an *undefined* quantity impossible.
- **Short-leg subtraction.** At the 08-25 read every RH position was a **net-long debit
  structure** — 0 credit structures, 0 negative marks (min +0.005), position value **+$478.50**,
  not a liability. A debit spread's pair cannot net below zero. The rescue would require
  `balance` to be position-aware, and per the write path it is not.
- **Magnitude as a semantics answer.** R-IV.94b established the normalized 08-25 figure
  (~$800) but explicitly **did not advance this defect** — *"recording that plainly rather
  than treating a magnitude as a semantics answer."*

---

## NEW EVIDENCE — 2026-09-05 · a fake-healthy vintage

Live read, `account_balances`:

| account_name | balance | cash | updated_at | updated_by | age |
|---|---|---|---|---|---|
| ROBINHOOD | **835.69** | 596.31 | 2026-09-04 19:52:33Z | `auto` | 22 h |
| FIDELITY_ROTH | 8842.09 | 4623.81 | 2026-09-04 18:02:42Z | `auto` | 23 h |
| BROKERAGE_LINK_401K | **11642.35** | **11642.35** | 2026-06-09 23:46:03Z | `pivot_screenshot; consolidated 401A+403B 2026-07-23` | **87 d** |

**1 · `updated_at` describes the ROW, not the `balance` column — so `balance` reports a
freshness it does not have.** The Robinhood `balance` is **835.69**, identical to the value
filed 2026-08-25 whose true vintage was **2026-08-24 17:01:35Z**. Twelve days later the value
has not moved, but `updated_at` now reads 22 hours old. The row was stamped by a cash-only
write:

```
account_balances.ROBINHOOD updated_at  2026-09-04 19:52:33.942846+00
unified_positions id 410 updated_at    2026-09-04 19:52:33.942846+00
                                       -> IDENTICAL TO THE MICROSECOND
```

id 410 is the PLTR round trip closed 2026-09-04. Its cash adjustment stamped the balances
row. **Anyone reading `balance` alongside `updated_at` gets a false vintage** — a stale
hand-typed figure wearing an automatic timestamp. This is the fake-healthy family, and it is
new since the 08-25 filing.

**2 · One row uses the two columns interchangeably.** `BROKERAGE_LINK_401K` carries
`balance == cash` **exactly** (11,642.35 both). Whatever the columns are supposed to mean,
that row does not distinguish them.

**3 · `updated_by` contradicts its own `updated_at` by 44 days.** The string says
*"consolidated 401A+403B **2026-07-23**"* on a row stamped **2026-06-09**. Either the
consolidation did not touch `updated_at`, or the annotation is wrong. Cross-refs
`DEF-ACCOUNT-LABEL-DUP`.

**4 · The gap is stable while its components churn.** Robinhood, both reads:

```
 2026-08-25   balance 835.69   cash 1070.00 + positions 478.50 = 1548.50   gap 712.81
 2026-09-05   balance 835.69   cash  596.31 + positions 936.38 = 1532.69   gap 697.00
```

> **Baseline caution.** `RH-BOOK-DISCREPANCY` reports the 08-25 gap as **713.50**. That is
> measured against the **broker app total (~835.00)**, not against DB `balance` (835.69):
> `1548.50 − 835.00 = 713.50` versus `1548.50 − 835.69 = 712.81`. The 69-cent difference is
> the whole reason `balance` was called the accurate column — it agrees with the app to
> $0.69. Quoting 713.50 against `balance` silently swaps the baseline; both figures are
> correct and they answer different questions.

Cash fell $473.69 and marked position value rose $457.88 — near-offsetting, as expected when
cash buys positions — while `balance` did not move at all. **The gap's stability does not
resolve the semantics**, though: if `balance` were account value frozen at 08-24, the account
would have gained $697 on an $836 base in eleven days (+83%), which is not plausible; if it
were cash, it contradicts the DB's own `cash` of 1070.00 on 08-25. Both readings still fail.
Recorded as a measurement, not a conclusion.

---

## THE DEFECT PROPAGATES INTO HISTORY — 2026-09-05

`balance_snapshots` re-snapshots `account_balances.balance` daily. Because that column is
frozen, **the snapshot history inherits the freeze and renders it as a flat line.**

543 rows carry **32 distinct balance values (5.9% variety)**, and **four of eight series are
literally constant**: `BROKERAGE_LINK_401K` (31 rows, 1 value), `Interactive Brokers`
(90 rows, 1 value), `FIDELITY_ROTH` (7 rows, 1 value), `ROBINHOOD` (7 rows, 1 value).

**`ROBINHOOD` shows seven consecutive daily snapshots of 835.69** — the same stale
hand-typed figure whose true vintage is **2026-08-24 17:01:35Z**. A chart of that series
shows a flat, healthy-looking week that is an artifact of the writer, not of the account.

This is the same failure as the `updated_at` finding above, one layer out: **a stale value
acquiring an appearance of currency by being re-recorded.** Fixing column-level vintage
without fixing the snapshot job leaves the false history in place.

Full series inventory in `DEF-ACCOUNT-LABEL-DUP` → *`balance_snapshots` — report-only
analysis*.

---

## WHAT SURVIVES, STATED WEAKLY

The two columns have **uncoordinated provenance and different vintages**, so comparing them
licenses no inference in either direction. *A stale hand-typed `balance` against an
auto-drifted `cash` is not evidence of a semantics defect; it is evidence that the comparison
is not a test.* The RH face stays **undiagnosed** and no substitute mechanism is claimed.

---

## RELATED, DELIBERATELY NOT MERGED

**`DEF-CASH-EVENTS-UNTRACKED`** is cross-referenced, not folded in (R-IV.94b §5):
*"the semantics defect is about what the column **means**; this is about a real event having
**no way in**."* Two defects, one surface.

---

## WHAT RESOLVES IT

A **Robinhood activity export** for the disputed window fixes `true_cash` directly and
collapses the reconciliation line to a point. No Fidelity artifact can reach it — the $250
withdrawal that opened this ticket is a Robinhood event. Only the principal can place it.

---

## STATUS

Registration only. **No fix authorized, no rows touched.** Condition 7 stands: no writer may
touch `balance` or `cash` until this closes.

---

## FACET — fake-healthy vintage in the hub (CC-BUILD annotation, R-IV.265(e))

**A cash-only write stamps `updated_at` on the WHOLE ROW**, so a hand-typed balance that
has not been touched in twelve days reads as twenty-two hours fresh in
`hub_get_portfolio_balances`. The row has one timestamp and several columns with different
vintages, and the timestamp describes whichever column was written last.

**Measured on origin 2026-09-05**, which is worse than the twelve-day case:

```
BROKERAGE_LINK_401K   balance 11,642.35   updated_at 2026-06-09   88 DAYS
FIDELITY_ROTH          balance  8,842.09   updated_at 2026-09-04    1.2 days
ROBINHOOD              balance    835.69   updated_at 2026-09-04    1.2 days
```

**The staleness flag cannot discriminate.** `is_stale` returns true for all three — for the
1.2-day rows and the 88-day row alike — so a consumer that checks it learns only that
something is over a day old, which is true of everything.

**And the summary string understates by an order of magnitude:** *"Some balances >24h
old"* for a row 88 days stale. Technically true, and it is the third instance of this
phrasing family — after MP's *"feed quiet this session"* on a 38-day-dead feed and the
watermark's original *"up to 8"* count. **A phrase that stays true as the magnitude grows
is not a warning; it is a floor.**

**Held per R-IV.265(e); the committee has been told.** Scoped into the ledger-integrity
build (position 1b) as column-level vintage: **no hand-typed balance wearing a write
timestamp.**
