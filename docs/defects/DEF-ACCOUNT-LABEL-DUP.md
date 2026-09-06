# DEF-ACCOUNT-LABEL-DUP

**Severity:** P2 · **Registered:** 2026-08-25 (R-IV.80d condition 3) ·
**FILED AS A DOCUMENT:** 2026-09-05 (R-IV.264(c))
**Status:** **DISPUTE RESOLVED 2026-09-05 (R-IV.268(a)) — REMEDIATION OPEN.**
The question *"what are the accounts"* is answered. The **data still carries aliases on 6 of
9 surfaces**; `unified_positions` is clean, nothing else is. Do not read the resolved header
as a clean book — see **REMAINING SURFACE** below.
**Owner:** CC-POSITIONS (evidence) · CC-BUILD (surface) · principal (the plan-type fact)
**Surface:** `unified_positions.account` · `account_balances.account_name` · the canonical
account vocabulary in `docs/feat-position-lifecycle.md`
**Binding consequence in force:** *"One account label, canonical. **Do not write under
both.**"* (R-IV.80d condition 3)

> **LINEAGE — registered in relay, never filed.** Cited as established in **3 documents
> across 4 citation lines** with no file of this name in the tree:
>
> | document | line(s) |
> |---|---|
> | `docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.80d.md` | 74 |
> | `docs/feat-position-lifecycle.md` | 19 |
> | `docs/incidents/FIDELITY_IMPORT_PHASE1A_PREWRITE_CENSUS.md` | 185 · 189 |

---

## THE DEFECT — a three-way vocabulary disagreement

Measured live, 2026-09-05. **No two of these three sources agree:**

| source | labels actually present |
|---|---|
| **canonical vocabulary** (`feat-position-lifecycle.md:18`) | `ROBINHOOD` · `FIDELITY_ROTH` · **`FIDELITY_401A`** |
| **`unified_positions.account`** | `ROBINHOOD` (288) · `FIDELITY_ROTH` (66) · **`FIDELITY`** (1) |
| **`account_balances.account_name`** | `ROBINHOOD` · `FIDELITY_ROTH` · **`BROKERAGE_LINK_401K`** |

Three consequences, each independently checkable:

1. **`FIDELITY_401A` — the declared canonical label — exists in NEITHER table.** The
   vocabulary of record names an account that no row anywhere uses.
2. **`BROKERAGE_LINK_401K` holds a balance ($11,642.35) and has never held a position row.**
3. **`FIDELITY` holds a position row and has no balance row at all.**

## THE PLAN-TYPE ERROR

`BROKERAGE_LINK_401K` is the merged label for the Fidelity **401A + 403B** consolidation of
2026-07-23. **One of the two enum labels it merges is factually wrong** — Fidelity states
**403(b)**, the label says **401K**
(`FIDELITY_IMPORT_PHASE1A_PREWRITE_CENSUS.md:184`). The name asserts a plan type the broker
contradicts.

**AHRP is DESCOPED from tradeable aggregates** as of 2026-08-25, so this row must never be
summed into a sizing figure regardless of what it is called.

---

## NEW EVIDENCE — 2026-09-05 · condition 3 was breached two days ago

**`FIDELITY` is a brand-new fourth label, created 2026-09-03.**

```
 account   rows  open  first_seen   last_seen
 FIDELITY     1     1  2026-09-03   2026-09-03      <-- id 409, SOXS 30 @ 49.9433, basis 1,498.30
```

Before 2026-09-03 this label did not exist. id 409 was written under a label that is **not
canonical, has no `account_balances` row, and duplicates the Fidelity identity already served
by `FIDELITY_ROTH`.** R-IV.80d condition 3 says *"one account label, canonical — do not write
under both,"* and the book now carries **two Fidelity labels in `unified_positions` and a
third in `account_balances`.**

Flagging the breach; **not repairing it.** A remap is a write against a disputed vocabulary
and needs the canonical target settled first — which is the defect.

**Corroborating annotation error.** The `BROKERAGE_LINK_401K` row's `updated_by` string reads
*"pivot_screenshot; consolidated 401A+403B **2026-07-23**"* while its `updated_at` is
**2026-06-09 23:46:03Z** — the annotation post-dates its own row stamp by **44 days**. Either
the consolidation never touched `updated_at` or the note is wrong. Cross-refs
`DEF-BALANCE-COLUMN-SEMANTICS`.

---

## WHAT IS NOT THE DEFECT

- **The write-target recommendation does not resolve it.** `FIDELITY_ROTH` is recommended for
  position writes on the narrow ground that it is *the only label with existing position
  rows* — keeping one account's history in one place. The census says so explicitly:
  *"this recommendation does not resolve DEF-ACCOUNT-LABEL-DUP; it only picks a write target"*
  (`:189`).
- **`BROKERAGE_LINK_401K` being untouched is deliberate, not an oversight.** The lifecycle
  build declared the canonical vocabulary and left that label alone as a **frozen dispute**
  (`feat-position-lifecycle.md:19`).
- **The space-vs-underscore split is a separate surface** living in `account_balances`, and
  **binding condition 7 bars touching that table** — so the split cannot be repaired from
  this side even if the vocabulary were settled.

---

## RESOLUTION — 2026-09-05 · R-IV.268(a)

**PRINCIPAL FACT OF RECORD: the Roth IRA and the "401k BrokerageLink" are ONE account.**

The premise of the dispute was wrong. There was never a 401A-vs-403B plan-type question to
settle, because there are not two Fidelity accounts — there is one, and the labels were
describing the same thing three ways.

| | |
|---|---|
| **Tracked set** | **TWO accounts: `ROBINHOOD` · `FIDELITY_ROTH`** |
| **Canonical labels** | `ROBINHOOD` · `FIDELITY_ROTH` |
| **Aliases to retire** | `FIDELITY` · `FIDELITY_401A` · `BROKERAGE_LINK_401K` — and every case/spacing variant below |
| **`breakout_prop`** | stays **descoped** |

### Executed — `unified_positions` is clean

**id 409 remapped `FIDELITY` → `FIDELITY_ROTH`**, 2026-09-05, preimage → single guarded
statement → postimage, rowcount 1, with a pre-commit invariant check that zero non-canonical
rows remained. **Position economics untouched** — quantity, entry price, cost basis, entry
date, marks, status and `position_id` all verified unchanged; the label alone moved.

```
 before   ROBINHOOD 288 rows (18 open) · FIDELITY_ROTH 66 (3 open) · FIDELITY 1 (1 open)
 after    ROBINHOOD 288 rows (18 open) · FIDELITY_ROTH 67 (4 open)
```

Census note: the stored string was **`'FIDELITY'` uppercase**, length 8, no whitespace — the
order described it as lowercase `fidelity`. A case-sensitive predicate would have missed it.

---

## REMAINING SURFACE — 3 of 9 surfaces still carry aliases

Full schema scan 2026-09-05, updated after the R-IV.272 folds. **Six surfaces are now clean;
three are HELD for the ledger-integrity build.**

| surface | state | detail |
|---|---|---|
| `unified_positions.account` | **CLEAN** ✅ | id 409 remapped, R-IV.268(b) |
| `portfolio_snapshots.account` | **CLEAN** ✅ | ROBINHOOD only |
| `positions.broker` | **CLEAN** ✅ | empty |
| `trades.account` | **FOLDED** ✅ | `robinhood` (132) → ROBINHOOD · `FIDELITY` (1) → FIDELITY_ROTH · R-IV.272 |
| `closed_positions.account` | **FOLDED** ✅ | `robinhood` (5) → ROBINHOOD · `FIDELITY` (1) → FIDELITY_ROTH · R-IV.272 |
| `cash_flows.account_name` | **FOLDED** ✅ | `FIDELITY_401A` (1) → FIDELITY_ROTH · R-IV.272 |
| `account_balances.account_name` | **HELD** | `BROKERAGE_LINK_401K` (1) — BUILD, ledger-integrity build |
| `account_balances.broker` | **HELD** | `fidelity` (2) · `robinhood` (1) — a **lowercase second vocabulary**, still unaddressed |
| `balance_snapshots.account_name` | **HELD** | six variants, **529 rows** — see the analysis below |

**Post-fold counts, 2026-09-05:** `trades` ROBINHOOD 312 / FIDELITY_ROTH 48 ·
`closed_positions` ROBINHOOD 117 / FIDELITY_ROTH 42 · `cash_flows` ROBINHOOD 17 /
FIDELITY_ROTH 14. Each write was a guarded statement with a pre-commit invariant asserting
zero non-canonical values remaining on that column. **Label-only: no amounts, dates,
quantities or statuses were touched.**

The `cash_flows` row carried a real flow — **ACH deposit $170.78, `activity_date` 2026-04-23,
`imported_from` manual** (id 15). It moved account label only.

### The fold repaired a live measurement, not just tidiness

`DEF-RH-COVERAGE-GAP`'s **25 of 33** was re-derived before the write, per R-IV.272(b):

```
 predicate                                     tickers found
 account = 'ROBINHOOD'   (case-sensitive)  ...........  1     <-- before the fold
 upper(account) = 'ROBINHOOD'              ........... 25
 account ignored entirely                  ........... 25
 account = 'ROBINHOOD'   AFTER the fold    ........... 25     <-- repaired
```

**The 25-of-33 figure on origin is CORRECT** and needs no correction — it was derived
case-insensitively. But **24 of those 25 tickers were reachable only under lowercase
`robinhood`**; only WFC sat under uppercase. Anyone re-deriving with the obvious
case-sensitive predicate would have got **1**, and concluded the in-DB backfill source did
not exist. The fold removes that trap. `BTCZ` additionally carries rows under *both*
accounts, which bears on its worked line in that defect.

### `balance_snapshots` — report-only analysis, R-IV.272(b). READ BEFORE RETIRING ANYTHING.

**⚠ The premise of R-IV.268(c) does not survive measurement.** That order says the
`BROKERAGE_LINK_401K` row *"is a duplicate of FIDELITY_ROTH; retire it (do not sum it)."*
**The two carry different values and always have:**

```
 FIDELITY_ROTH        8,842.09
 BROKERAGE_LINK_401K 11,642.35
```

`BROKERAGE_LINK_401K` is **not a value-duplicate** — it is the exact arithmetic sum of the
two retired series, verified on the consolidation date:

```
 2026-07-23   Fidelity 401A 11,075.62 + Fidelity 403B 566.73 = 11,642.35   EXACT
```

So retiring it *as a duplicate* would not deduplicate a figure — it would **remove $11,642.35
of recorded balance from the book.** Whether that is right turns on what R-IV.268(a)'s "one
account" means: one *relationship* holding a Roth sleeve **and** a BrokerageLink sleeve with
distinct balances, or one *balance* recorded twice. **The data cannot distinguish these and I
am not choosing.** Stated before BUILD acts, because "retire the duplicate" and "delete
$11.6k" are the same statement under one reading and opposite under the other.

**Series inventory** — three Fidelity series overlap completely on **90 shared dates**
(2026-03-20 → 07-23), and their values do **not** agree; they are three distinct magnitudes,
so a naive sum triple-counts in magnitude rather than duplicating a number:

| series | rows | date range | balance range |
|---|---|---|---|
| Fidelity Roth | 114 | 03-20 → 08-26 | 8,233.52 – 8,842.09 |
| Fidelity 401A | 90 | 03-20 → 07-23 | 10,107.90 – 11,075.62 |
| Fidelity 403B | 90 | 03-20 → 07-23 | 233.15 – 566.73 |
| BROKERAGE_LINK_401K | 31 | 07-24 → 09-04 | 11,642.35 *(constant)* |
| FIDELITY_ROTH | 7 | 08-27 → 09-04 | 8,842.09 *(constant)* |

The vocabulary changed **twice**: 07-23/24 (401A + 403B → BROKERAGE_LINK_401K, same day the
IB series ends) and 08-26/27 (spaced → underscore).

**IB orphans:** `Interactive Brokers`, **90 rows, 2026-03-20 → 2026-07-23, every balance
0.00.** A zero-valued series for a broker whose `account_balances` row was deleted 07-23; the
deletion never reached the snapshot history.

**The whole table is a fake-healthy time series.** 543 rows carry **32 distinct balance
values — 5.9% variety — and four of the eight series are literally constant:**

| series | rows | distinct balances |
|---|---|---|
| BROKERAGE_LINK_401K | 31 | **1** |
| Interactive Brokers | 90 | **1** |
| FIDELITY_ROTH | 7 | **1** |
| ROBINHOOD | 7 | **1** |
| Fidelity 403B | 90 | 3 |
| Fidelity 401A | 90 | 4 |
| Fidelity Roth | 114 | 5 |
| Robinhood | 114 | 14 |

It reads as daily account history and contains almost none. The mechanism is
`DEF-BALANCE-COLUMN-SEMANTICS` propagating: the job re-snapshots a frozen
`account_balances.balance` every day, so **`ROBINHOOD` shows 7 consecutive daily rows of
835.69 — the same stale hand-typed figure whose true vintage is 2026-08-24 17:01:35Z.**
Any chart drawn from this table shows flat lines that are an artifact of the writer, not the
account.

### Three consequences worth naming before anyone writes

1. **`trades.account` splits the Robinhood ledger nearly in half.** 180 rows `ROBINHOOD`,
   **132 rows `robinhood`** — 42% under a case variant. Any case-sensitive
   `WHERE account = 'ROBINHOOD'` silently drops a third of the ledger and returns a clean
   result. `trades` is the backfill source named in `DEF-RH-COVERAGE-GAP`, so this bears
   directly on that defect's 25-of-33 figure.
2. **`balance_snapshots` triple-counts Fidelity.** `Fidelity Roth`, `Fidelity 401A` and
   `Fidelity 403B` are three separate 90–114-row series for what the principal's fact says
   is **one account**. Any historical account-value chart summing them overstates.
3. **`Interactive Brokers` has 90 snapshot rows** for a broker whose `account_balances` row
   was deleted 2026-07-23. The deletion did not reach the snapshot history.

### Not executed, and why

R-IV.268(b) says *"any other alias rows, same treatment."* In `unified_positions` that was one
row and it is done. The six surfaces above are a **different act**: 529 snapshot rows, 133
ledger rows, and a live `cash_flows` entry, across tables where `account_balances` is
explicitly BUILD's under (c) and `closed_positions`/`positions` are deprecated pending the
migration wave. **Held for explicit authorization per surface.** A blanket case-fold across
`trades` is a ledger write and is not covered by a one-row remap order.

---

## STATUS

**Dispute resolved. `unified_positions` remediated. Six surfaces outstanding.** Retiring the
alias *names* in one table does not retire the alias *data* in the others, and the resolved
header must not be read as a clean book.

---

## FACET — the hub lowercases on output (CC-BUILD annotation, R-IV.271(d)) — HELD

**Tool renderings are never query predicates.** `hub_get_portfolio_balances` and `hub_get_positions` emit
lowercased account strings — `lower-case` — while the stored values are
uppercase — `UPPER-CASE`. Confirmed in the live payload: the tool returns
`robinhood / fidelity_roth / brokerage_link_401k` against DB rows `ROBINHOOD / FIDELITY_ROTH / BROKERAGE_LINK_401K`.

**The trap this sets.** Anyone writing a predicate from what the tool *shows* writes
`WHERE account_name = 'fidelity_roth'` and matches **zero rows**, silently. A filter that matches nothing runs
clean and returns something shaped like an answer — the vacuous-column family.

**The rule:** DB predicates on account are **case-insensitive or use the stored form**.

### POSITIONS note — this facet is a candidate MECHANISM for the alias contamination

The two findings compose. BUILD measures that **the hub emits `robinhood` where the DB stores
`ROBINHOOD`**; POSITIONS measured that **`trades` held 132 rows under lowercase `robinhood`**
(42% of the Robinhood ledger) before the R-IV.272 fold. A writer that round-trips a value
through the tool — reads a rendered account string and writes it back — produces exactly that
contamination, in exactly that case.

**Candidate, not established.** No write path has been traced, and the lowercase rows could
equally come from an importer with its own casing. Recorded because the two measurements were
taken independently by different lanes and happen to fit, which is worth a trace rather than
an assumption. The trace is BUILD's; the fold has already removed the symptom, so **if
lowercase rows reappear in `trades` after 2026-09-05, that is the round-trip confirmed.**
Never copy an account string out of a tool rendering into a query.

**HELD.** It rides the account-enum collapse in the ledger-integrity build, because the
canonical two-value enum is where the casing gets settled once rather than defended at
every call site.
