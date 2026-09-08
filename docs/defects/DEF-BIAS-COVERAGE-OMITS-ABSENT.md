# DEF-BIAS-`coverage_ratio`ERAGE-OMITS-ABSENT · P1

**Registered** 2026-09-08 by R-IV.321(c). **Confirmed live the same day.** **Status:** OPEN.
**P1: the composite's self-monitor is a null verifier.**
**Census of record:** `docs/edge/results/2026-09-08-regime-factor-census.md`

---

## The defect

`coverage_ratio` reports the fraction of factor weight that is `active_weight_sum`. **A factor that is
present, fresh and scored `0.0` counts as active** — so a dead factor rendered as neutral
(`DEF-BIAS-NULL-AS-NEUTRAL`) **raises coverage rather than lowering it.**

**The metric cannot fall for the failure it exists to detect.**

## Measured 2026-09-08 15:04 ET

```
reported   active 18 of 20   coverage_ratio 0.94   excluded ["excess_cape", "savita"]
actual     14 of 20 carrying a measured value
           4 counted as covered while contributing 0.0 without measuring anything
```

**0.94 while four of the eighteen are dead.** Every test coverage applies is satisfied by a
null rendered as 0.0: present, not stale, in range.

## Why this is the null-verifier law and not merely an inaccuracy

`coverage_ratio` was surfaced under R-IV.47(d) **precisely to stop
`active_weight_sum` being computed and discarded** — the compute-then-discard family's first fix. It
became visible, and **the visible number cannot report the thing it was surfaced to
report.**

**A monitor that only moves when something else already told you is not a monitor.** It
would have to fall when a factor dies; it rises.

## The second half, from the ruling

**Factors missing from the ROSTER are not counted as excluded at all.** `excluded_factors` is computed
over `FACTOR_CONFIG`, so the roster defines the universe — **and the roster is the thing
that could be incomplete.** Weights are normalised to sum to 1.00 across whatever is in it,
so **dropping a factor from the roster leaves coverage reading 1.00 with one fewer input.**

**Measured today the roster is complete** — 18 active + 2 excluded = 20 = `FACTOR_CONFIG`. **The
defect is structural, not currently realised**, and it is registered because the metric
would be silent if it were.

## Fix shape — not chosen here

**Coverage counts MEASURED factors, not present ones**, and a null-scored factor is
excluded and named. **Ships with `DEF-BIAS-NULL-AS-NEUTRAL`**; either alone leaves the pair intact.

**And the roster needs a source outside itself** — an expected-factor list the config is
checked against, so absence from the config is detectable. Without it, this half of the
defect is unfixable by construction: **a set cannot notice what was never in it.**
