# DEF-3-10-CALIBRATION-NONREPRODUCING — P2

**Registered:** R-IV.425(b). **Filed by:** CC-BUILD, from the ruling's own figures — this lane
has not re-run the calibration, and every number below is quoted, not measured here.

---

## THE STATEMENT

> **A calibration on a FIXED population returned +0.946 once and −0.326 when re-run.**
> A "fixed" population that moves is either not fixed or not the same measure.
> **Find which before any figure from that era is cited again.**

## WHAT IS KNOWN

- The measure belongs to the 3-10 evaluation that R-IV.425(b) declined to promote (fails the
  04-22 bar at 5d, edge-of-noise at 3d, n below gate on the arm it adds, negative mean
  everywhere).
- The earlier value was **+0.946**; the reproduction on what was taken to be the same
  population gave **−0.326**.

## THE TWO EXPLANATIONS, AND WHAT SEPARATES THEM

| if the population moved | if the measure moved |
|---|---|
| the row set differs between runs — rows added, re-graded, re-bucketed, or re-dated | the rows are identical but the code, a parameter, a join or an input series differs |
| **test:** the two runs' row ids, hashed, disagree | **test:** identical row-id hashes, different outputs |

**Candidates on this register that could move either side without anyone changing the query:**

- **`DEF-ADJUSTED-BARS-VS-RAW-ENTRY`** — an outcome computed from adjusted bars changes value
  whenever a later corporate action rescales the series. **A re-run can move a "fixed"
  population's returns with no code change at all.**
- **The PASS 9 percentile window** (R-IV.425(c)) — a lookback that anchors on the oldest end
  of a rolling span produces a different threshold on every run date.
- **Re-grading.** The grader backlog cleared on 2026-09-14 changed which rows are graded.

## WHAT CLOSES IT

1. Recover the **row-id set and code commit** of the +0.946 run. If neither was recorded,
   **the figure has no origin and is withdrawn** — that absence is itself the finding, and it is
   what the new Addendum 3 calibration clause exists to prevent.
2. Re-run on the **frozen** row set with today's code, then on today's row set with the old code.
   Whichever pair disagrees locates the movement.
3. **Until then, no figure from that calibration era is cited** (R-IV.425(b)).

## Status: OPEN — registered; unassigned.
