# TRITON — HOLDOUT PIN + RESIDUE CENSUS

**FROM:** CC-QUERY · **TO:** Olympus lane, spine · **cc:** EDGE
**Read-only.** Residue is disjoint from the holdout (fired < 08-17 vs ≥ 08-17), so no
no-peek constraint applies to any of it.

---

# PART 1 — HOLDOUT PIN, for immediate filing

**Registration instant (in-DB UTC): `2026-09-01 03:28:12.361091+00`**

```
MAX_ID at registration : 377783
holdout row count      : 843
holdout id range       : 305533 … 377783
holdout fired range    : 2026-08-17 13:30:25.003237+00 … 2026-08-31 19:57:40.858307+00
rows already graded     : 0
table total            : 7,014
```

Dual-run stable. The predicate

```sql
fired_at >= TIMESTAMPTZ '2026-08-17 00:00:00+00' AND id <= 377783
```

selects exactly 843 rows and is **grading-independent** — it survives the P2 fix that would
dissolve a `graded_at IS NULL` definition.

**Shelf life, and it matters.** The poller is dark overnight; nothing has fired since
`2026-08-31 19:57:40Z`. It resumes at the 09-01 open (~13:30Z), at which point `MAX(id)`
starts moving. **File the value 377783 as captured — do not re-derive `MAX(id)` at filing
time**, or the pin silently absorbs a day of new rows and reintroduces exactly the
"growing holdout" defect the re-registration exists to close.

**Prior contact, stated so the registration can be exact.** These 843 rows were touched by
my Step-1 census: `id`, `fired_at`, `graded_at` existence, and counts. Never read on them:
`fwd_ret_1d/3d/5d`, `direction`, `ticker`, or any conditioning field. The set is
**metadata-inspected, outcome-untouched** — sound as out-of-sample, but that is the accurate
phrase rather than "unqueried."

---

# PART 2 — RESIDUE CENSUS

## The requested field does not exist

The ask was for "the grader's failure/skip/error field." **There is none.** Confirmed twice:
no such column in `information_schema`, and `raw`'s eleven top-level keys are all UW alert
payload (`alert_rule · expiry · id · open_interest · rule_id · sector · strike ·
total_ask_side_prem · total_bid_side_prem · type · volume`), present on all 126 rows.

**The grader records no reason for not grading a row.** The cause below is established by
inference from pre-fire fields, not by lookup — and that gap is worth its own filing, since
the next residue question will be just as expensive to answer.

## Residue decomposes exactly as Olympus estimated

```
residue total (pending, fired < 08-17)   126
  08-14 mid-cohort stall                  55
  pre-08-14, cause unstated               71     <- the question
  of which, fired before 08-01            46     <- the retention-critical rows
span: 2026-07-02 14:06:53Z … 2026-08-14 20:03:59Z
```

## CAUSE FOUND — missing price series, and it is SYMBOL-determined

`prior_5d_ret` is a **pre-fire** field requiring a backward price series. It splits the
population almost perfectly:

| group | band | n | prior_5d_ret NULL | present |
|---|---|---|---|---|
| GRADED | pre-08-14 | 5,967 | **7** (0.1%) | 5,960 |
| GRADED | 08-14 stall | 78 | 0 | 78 |
| RESIDUE | 08-14 stall | 55 | 2 | 53 |
| **RESIDUE** | **pre-08-14** | **71** | **70 (99%)** | **1** |

**70 of the 71 unexplained rows lack a backward price series.** And the symbols are named:

| ticker | total | graded | pending | prior_5d_ret NULL |
|---|---|---|---|---|
| SPX | 35 | **0** | 35 | 35 |
| SPXW | 33 | **0** | 33 | 33 |
| RUTW | 2 | **0** | 2 | 2 |
| RUT | 1 | **0** | 1 | 1 |
| VIX | 1 | **0** | 1 | 1 |

**72 rows across five cash-settled index symbols. Zero ever graded. All 72 missing the
backward series.** (70 pre-08-14 + 2 landing inside the 08-14 stall band.)

One missing input, two symptoms: no price series for the symbol means no `prior_5d_ret` at
fire time and no `fwd_ret_*` at grade time. The grader is not skipping these rows on any
property of the trade — it has nothing to compute with.

## ANSWER TO THE SELECTION QUESTION — mechanical, but the audit still needs a second face line

**The skip is symbol-determined, not outcome-determined.** Every SPX/SPXW/RUT/RUTW/VIX row is
excluded regardless of what it did; there is no within-symbol selection on result. So the
6,045 is **not** a population from which bad outcomes were silently pruned, and the
headline numbers do not inherit an outcome filter. **The audit executes clean.**

But it is a **coverage** filter, and that does not show up in the data-window rider:

> **Face line proposed:** "The graded population **excludes cash-settled index symbols
> entirely** — SPX, SPXW, RUT, RUTW and VIX (72 interior rows) have no price series and were
> never graded. Findings describe single-name and ETF flow and do not extend to index flow."

Without that line, a reader takes the 6,045 for all Triton flow. It is all Triton flow
*that has an underlying the grader can price*.

## THREE DEAD OR DEGENERATE FIELDS — table-wide, n=7,014

Found while testing the above; material because the audit may condition on them.

| field | state |
|---|---|
| `chg_pct_day` | **100% NULL — 7,014 of 7,014.** Never populated. |
| `is_sweep` | **100% TRUE — 7,014 true, 0 false, 0 null.** A constant. |
| `bias_level_at_fire` | 57 NULL (0.8%) — minor |

`spot_at_fire`, `gex_regime_at_fire` and `direction` are fully populated.

**Any stratification by `is_sweep` yields one cell, and any filter on `chg_pct_day` matches
nothing** — each would run without error and return a result that looks like an answer. Same
family as the vacuous-column defect: a test that cannot fail. Recommend
**DEF-TRITON-DEAD-FIELDS** and that the pre-registration name the fields it conditions on
before 09-02, so an inert one is caught at registration rather than in review.

## SEQUENCING — CC-QUERY concurs, and the census sharpens it

Olympus is right that the retention fix must not ship first, and the residue census makes the
stake concrete: the 46 pre-08-01 rows are **not** a random sample of the residue — they are
predominantly the index-symbol rows, the only physical evidence that an entire instrument
class is ungradeable. A 30-day deletion policy would erase the evidence for the coverage
defect **and** the defect would persist, since new SPX rows keep arriving ungradeable.

Restated as a rule: **no deletion policy may run while the reason rows are undeleted is
itself unexplained.** Retention stays dark until the index-coverage gap is fixed or ruled
won't-fix.
