# PR-102 — sell_the_rip SHORT: Era Stability · v1.1
Status: REGISTERED · Mode: CONFIRM (the set's only test)
Inherits PR-100 v1.1. Mandated by Map §6 before any Phase-2 claim.
DISCLOSURE (v1.1): pooled-era figures for this pair were seen
(QS-01-C1 volume profile; QS-04-2 pooled-era mix). Era-SPLIT
statistics have been computed nowhere prior to this test. The
criterion, direction, window, and threshold below were fixed
before any split is computed.
HYPOTHESIS: sell_the_rip SHORT's resolution profile is stable
outside its March-dominated era. POPULATION: sell_the_rip · SHORT
· NON-DISMISSED · verdict rows. WINDOWS: Era-1 = ids ≤ in-DB
boundary(2026-04-01); Era-2 = after, to run horizon; boundary id
recorded. CRITERION: STABLE iff (a) era T1+ Wilson CIs overlap OR
|ΔT1+| < 10 points, AND (b) candidate-expectancy same sign both
eras. Era-2 gate: 250 verdicts, else "INSUFFICIENT n=<x> ·
accumulation ≈<r>/wk". OUTCOMES: STABLE / UNSTABLE / INSUFFICIENT
— filed whichever. Multiple-comparisons: Track A confirmatory
test #1. Fence applies to all outputs.

---

## §7 — FORMAL ADJUDICATION

Rendered by EDGE 2026-08-21 · graded PASS R-IV.40(c) · ROW BASIS: TA-102a/b
verbatim rows (`docs/edge/results/2026-08-20-T7-TRACKA-RESULTS.md`), fresh transfer,
per the grade-artifacts law · **SIGNAL-LEVEL — inadmissible as realized /
after-cost performance until Track B exists.**

**VERDICT: UNSTABLE — BOTH CRITERIA FAILED.**

Era boundary id 5600 (TA-102a, in-DB). Population: `sell_the_rip` · SHORT ·
NON-DISMISSED · verdict rows · window < 2026-08-18 00:00Z.

| era | n | T1+ | rate | Wilson95 | candidate-expectancy |
|---|---|---|---|---|---|
| Era-1 (<04-01) | 1,269 | 803 | 63.3% | [60.6, 65.9] | **+1.42** |
| Era-2 (04-01 → window) | 354 (gate ✓) | 80 | 22.6% | [18.5, 27.3] | **−2.94** |

Candidate-expectancy is n-weighted, costless, projected, daily-bar (PR-100 labels).

- **Criterion (a):** CIs disjoint AND |Δ| = 40.7 ≥ 10 → **FAIL**
- **Criterion (b):** sign flips → **FAIL**

STRIKE LINEAGE: none — first grounds, artifact-based.

**MEANING OF RECORD:** the aggregate 54.4% is a March-era fossil; era-conditioned
figures govern (caveat board, R-IV.40(c)).

Counter: confirmatory #1 FAILED · #2 CONFIRMED — **1-of-2, stated.** Eras
recombine to the aggregate exactly (spine-verified).
