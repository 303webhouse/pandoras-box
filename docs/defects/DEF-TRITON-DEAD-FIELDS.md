# DEF-TRITON-DEAD-FIELDS

**Class:** degenerate conditioning field — a split that cannot split, a filter that cannot
pass. NULL-VERIFIER and NULL-TRIGGER, one instance of each, in the same table.
**Severity:** **P2** — assigned by spine at R-IV.265(d). *(Stubbed UNASSIGNED on
2026-09-05: no severity appeared in any citing document; assignment discharged same day.)*
**Status:** **OPEN**
**Surface:** `triton_flow_shadow.is_sweep` · `triton_flow_shadow.chg_pct_day`
**Stubbed:** 2026-09-05 per R-IV.262(b), from citing documents only. **No new
investigation was performed for this stub.**

**First citation:** `docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:33`

## What is known

Measured table-wide, **n = 7,014**:

| field | state | consequence |
|---|---|---|
| `is_sweep` | **100% TRUE** — 7,014 TRUE / 0 FALSE / 0 NULL, **one distinct value** | any stratification yields **one cell** |
| `chg_pct_day` | **100% NULL** — 7,014 of 7,014 | any filter matches **nothing** |

Confirmed again on the audit population (6,045 graded rows at the time of the pre-flight):
`is_sweep` 6,045 TRUE / 0 FALSE / 0 NULL.

**Both run clean.** Neither raises, neither warns, and each returns something shaped like an
answer. A one-cell "split" reads as a result with no contrast; a filter matching nothing reads
as a legitimately empty population.

The pair is unusual and worth keeping together: **one dead field produces each face of the
same law.** `is_sweep` is a **check that cannot fail** (NULL-VERIFIER); `chg_pct_day` is a
**condition that cannot be satisfied** (NULL-TRIGGER). That coincidence in a single table is
the strongest available argument that the two faces are one object.

## What is FALSIFIED — do not re-derive these

- that the fields are **sparsely populated** — they are *degenerate*, not sparse; there is no
  threshold at which they become usable
- that a `chg_pct_day` filter would **error or warn** — it returns an empty set silently
- that `is_sweep` **discriminates anything** — it has one value, so every row is in every
  bucket it defines
- that these were **caught by the audit's own analysis** — they were caught by a pre-flight
  field census run *before* computation, which is the only reason no result conditioned on them

## Fix direction, as recorded in the citing documents

Field liveness declared **at registration**: every conditioning field states its expected
cardinality and satisfaction rate, HALT on mismatch, and **0% / 100% agreements demonstrate
reachability** rather than passing silently → `verification-laws §1.1`.

Until then, any registered split on either field renders **NOT APPLICABLE — DEAD FIELD**,
never a one-cell result.

## Lineage

Cited in **4 documents**, on **4 lines** (counts stated separately per R-IV.262(c)):

- `docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:33`
- `docs/edge/results/2026-09-01-triton-holdout-pin-and-residue-census.md:97`
- `docs/handoffs/BOOK-CLOSING-HANDOFF.md:270`
- `docs/strategy-reviews/2026-09-03-triton-rescope-proposal.md:58`
