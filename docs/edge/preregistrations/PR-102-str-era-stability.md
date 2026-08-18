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
