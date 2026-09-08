# DEF-BIAS-NULL-AS-NEUTRAL · P1

**Registered** 2026-09-08 by R-IV.321(c). **Confirmed live the same day** — measured, not
inferred. **Status:** OPEN. **P1: decision surface.**
**Census of record:** `docs/edge/results/2026-09-08-regime-factor-census.md`

---

## The defect

**A factor with no data renders as `0.0`, is marked `is_stale: false`, and is counted
`active_weight_sum`.** `0.0` on this scale is not "absent" — it is **NEUTRAL**, a real reading. So a
dead factor votes, and votes for no change.

## Measured 2026-09-08 15:04 ET

```
spy_trend_intraday   score 0   staleness 161s   is_stale false   `active_weight_sum`
breadth_intraday     score 0   staleness 130s   is_stale false   `active_weight_sum`
copper_gold_ratio    score 0   staleness 154s   is_stale false   `active_weight_sum`
dxy_trend            score 0   staleness 153s   is_stale false   `active_weight_sum`
```

**No other factor in the roster reads 0.** The remaining fourteen all carry non-zero values,
several to fifteen decimal places. **A factor that computes something does not land on
exactly 0.000; four doing so at once is a signature, not a market state.**

**`dxy_trend` is independently confirmed dead:** the Moby Dick census measured
`factor_history` at **0 rows** for it, with `factor_history`'s last write of any factor on
**2026-07-23**. It has read a fresh, active `0` for **47 days**.

## Why P1

**It is a decision surface.** The composite feeds every committee member's directional
context. A dead factor does not abstain — **it dilutes**, pulling the composite toward
neutral in proportion to its weight, and nothing downstream can tell that vote from a
measured one.

**And neutral is the most expensive place to be wrong.** A wrong directional read is
argued with; a spurious NEUTRAL suppresses the argument.

## The distinction the code does not make

```
absent   ->  exclude from the mean; the denominator shrinks; coverage falls
neutral  ->  include at 0.0; the denominator holds; coverage unchanged
```

**These are different facts and the system has one representation for both.** Kin to
`DEF-MP-DEAD-RENDERS-AS-QUIET`, where a dead feed rendered as a quiet market, and to the `compute-then-discard`
family generally: **the failure is never the absence, it is the absence wearing a value.**

## Fix shape — not chosen here

**A factor with no reading must be `excluded_factors`UDED, not scored 0.0**, and its exclusion must reach
`coverage_ratio` so the loss is visible. That is the same fix as
DEF`coverage_ratio` and the two should ship together — excluding a factor that
coverage cannot report is a half fix.

## Not determined here

**Why each of the four is dead.** Source paths were not traced; that needs the per-factor
map the census could not build from the live payload. **Four are identified; none is
diagnosed.**
