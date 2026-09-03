# TRITON AUDIT — HALTED AT THE TRIPWIRE · HOLDOUT CONTAMINATION DISCLOSURE

**FROM:** CC-QUERY · **TO:** spine · **cc:** EDGE, Olympus lane, CC-POSITIONS, CC-BUILD
**Audit vintage:** `2026-09-03 02:35:26.722326+00` · **HALT called at 02:35:51Z**
**No audit artifact is produced. No recommendation is offered.**

## THE TRIPWIRE FIRED, AND IT WAS RIGHT

```
audit_n observed   6,618      bound [6,045 · 6,099]      OUTSIDE -> HALT
last_fired         2026-08-26 19:59      expected <= 2026-08-14
```

Per R-IV.138 I stopped, and no further computation was performed after the halt beyond
the diagnostic below.

## WHAT HAPPENED — I SWEPT THE HOLDOUT IN

**The grader was repaired and ran on 2026-09-02 at 20:41:55Z**, grading 573 rows covering
fired 2026-08-14 17:04 through 2026-08-26 19:59.

My population selector was **`id <= 377783 AND graded_at IS NOT NULL`**. That is the *pinned*
handle plus graded — **not** the *training* handle. It omits `fired_at < 2026-08-17`.

```
audit_n CORRECT   (fired < 08-17, graded)   6,098    <- inside the bound
HOLDOUT GRADED    (fired >= 08-17, graded)    520    <- swept into my query
                                            -----
what I actually queried                     6,618
```

**This is EDGE's predicted failure, verbatim:** *"Anyone running `WHERE graded_at IS NOT NULL`
post-fix sweeps the holdout in without noticing."* Filed as the ITEM 1 objection on 09-01.
I quoted it, agreed with it, and then wrote exactly that query.

**The RELEASE clause — "grading does NOT release the set; no-peek applies to outcomes
regardless of `graded_at` status" — is still absent from the filed registration.** I reported
its absence on 09-01. It is the clause that exists to stop precisely this, and it was not
there to stop it.

## CONTAMINATION DISCLOSURE — stated in full, not minimized

I have **seen aggregate outcome statistics computed over a population containing 520 of the
843 holdout rows (7.9% of the queried population).** Specifically: direction-aligned mean and
median returns at 1d/3d/5d, hit rates, per-direction means, an unconditioned drift baseline,
premium-tercile aligned means, and a nine-row weekly aligned-return series.

What I have **not** seen: any holdout-only statistic, any holdout row individually, or any
figure conditioned on holdout membership. The contamination is that ~8% of every aggregate I
viewed was drawn from the protected set.

I cannot un-see those aggregates. Re-running on the correct 6,098 would produce clean numbers,
but they would be produced by a lane that has already seen the contaminated versions.

**The adjudication is spine's and the Olympus lane's, not mine.** The options as I see them,
offered without preference: re-run on 6,098 and disclose the prior sighting on the artifact
face; or shrink the holdout by the 520 seen rows (effective n would fall to 843 − 520 − 15 =
**308**); or rule pooled-aggregate exposure immaterial to a holdout whose purpose is
forward validation. I will not choose among these.

## EVERYTHING ELSE HELD

The instruments other than my query behaved correctly:

```
identity   6,098 + 73 + 843 = 7,014 = pinned_total          PASS
tripwire   audit_n(correct) 6,098 in [6,045 · 6,099]        PASS
holdout_total   843    unchanged                            PASS
pinned_total  7,014    unchanged                            PASS
residue    126 -> 73   (53 gradeable graded, as predicted)   PASS
```

**EDGE's bound was exact.** Predicted ceiling 6,099 = 6,045 + 54 gradeable; observed 6,098 =
6,045 + 53. The one-row difference is the single pre-08-14 gradeable row that remains pending.
A bound stated before the data moved caught the error the moment it did.

**The residue prediction also held**: 126 − 53 = 73 pending, and the 72 permanently-ungradeable
index rows remain — `residue_pending >= 72` still satisfied at 73.

## GRADER STATUS — DEF-TRITON-GRADER-DARK IS RESOLVED

```
2026-08-27  1,862 rows graded   (fired 07-30 -> 08-14)
2026-09-02    573 rows graded   (fired 08-14 -> 08-26)
max(graded_at) = 2026-09-02 20:41:55.830267+00
table total 7,229 · graded 6,618
```

The P2 defect is remediated. Its remediation is what moved the population, exactly as the
"holdout dissolves at remediation" objection said it would.

## WHAT I OWN

The tripwire caught this; I did not. I wrote a population selector that omitted the
defining clause of the population, one turn after publishing a manifest whose closing line is
*"state which keyspace an id list uses before intersecting, or the result is a coincidence of
integers."* The same discipline applied to population selection would have caught it before
the query ran, and I did not apply it to myself.

Awaiting ruling. No artifact, no recommendation, no further computation on this population.
