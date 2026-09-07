# FIRST MARKET READ — TRITON, EXPLORE POPULATION (R-IV.297)

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD, OLYMPUS-TRITON, EDGE
**Read vintage (in-DB UTC): `2026-09-07 05:23:37.792538+00`**
**Population:** the audited explore set — `id <= 377783 AND graded_at IS NOT NULL AND
fired_at < TIMESTAMPTZ '2026-08-17 00:00:00+00'` → **n = 6,098**.
**Handles at read time:** identity 6,098 + 73 + 843 = 7,014 = pinned_total **PASS** ·
tripwire 6,098 ∈ [6,045 · 6,099] **PASS** · holdout **untouched, zero rows read.**

## LABELS — these bind every number below

**HYPOTHESIS GENERATION.** Post-hoc exploratory, outside PR-104 §7's registered endpoints.
Nothing here is a finding, nothing promotes, and no recommendation is offered — the numbers
are the deliverable. Inherited from PR-104: **independent grading path · costless ·
candidate-tier · daily-bar grading · Track-A fence.** Inadmissible as realized or
after-cost performance.

**MULTIPLE COMPARISONS.** This read examines **37 cells** across four cuts, at two horizons
each. At 95% confidence roughly one cell in twenty clears by chance alone. No cell below is
corrected for multiplicity, and none should be read as significant on its own.

**DATA WINDOW.** Graded population ends `2026-08-14`. **Zero graded rows in the two most
recent weeks** — no recency arm exists. **Cash-settled index symbols are absent entirely**
(SPX/SPXW/RUT/RUTW/VIX, no price series); findings describe single-name and ETF flow.

**n GATE.** Cells under n=100 render **NOT COMPUTABLE**. **Applied, and no cell failed it** —
the smallest cell is n=333. Stated so the gate's silence is not mistaken for its absence.

**RECONCILIATION.** The overall row reproduces the filed audit exactly: 3d wins 3,177 · 5d
wins 3,114 · aligned 5d mean +0.4858 · drift 5d +0.1752. Same population, same arithmetic.

---

## OVERALL — the denominator every cell is a slice of

| | n | 3d hit | 3d Wilson | 3d aligned | 3d drift | 3d excess | 5d hit | 5d Wilson | 5d aligned | 5d drift | 5d excess |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 6098 | 52.10% | [50.84, 53.35] | +0.4305 | +0.1426 | **+0.2879** | 51.07% | [49.81, 52.32] | +0.4858 | +0.1752 | **+0.3106** |

**Bold hit rates** below mark cells whose Wilson interval excludes 50%. *Excess* = mean
aligned return minus the unconditioned long-side mean **within the same cell** (matched
baseline: same tickers, same days).

---

## (a) DAY-OF-WEEK OF FIRE

| cell | n | 3d hit | 3d Wilson 95% | 3d mean aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d mean aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| Mon | 1192 | **57.05%** | [54.22, 59.83] | +1.1855 | +1.1781 | **43.88%** | [41.08, 46.71] | -0.4761 | -1.0073 |
| Tue | 1185 | 51.05% | [48.21, 53.89] | -0.2710 | -0.3602 | **44.64%** | [41.83, 47.48] | -0.8055 | -0.9384 |
| Wed | 1156 | **43.77%** | [40.94, 46.65] | -0.3896 | -0.1583 | 52.42% | [49.54, 55.29] | +0.3823 | +0.5530 |
| Thu | 1541 | 50.68% | [48.19, 53.17] | +0.5161 | +0.0497 | **57.50%** | [55.01, 59.94] | +1.2522 | +0.9379 |
| Fri | 1024 | **59.08%** | [56.04, 62.05] | +1.1605 | +0.8641 | **55.66%** | [52.61, 58.68] | +2.0631 | +2.0721 |

## (a2) MIDWEEK vs EDGES — Tue–Thu against Mon+Fri

| cell | n | 3d hit | 3d Wilson 95% | 3d mean aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d mean aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| Tue-Thu | 3882 | 48.74% | [47.17, 50.31] | +0.0061 | -0.1374 | **52.06%** | [50.49, 53.63] | +0.3650 | +0.2506 |
| Mon+Fri | 2216 | **57.99%** | [55.92, 60.03] | +1.1739 | +1.0330 | 49.32% | [47.24, 51.40] | +0.6973 | +0.4157 |

## (b) DIRECTION × DAY-OF-WEEK

> **THE EXCESS COLUMN IS AN IDENTITY IN THIS CUT AND IS SUPPRESSED.** Within a
> direction-pure cell the unconditioned long-side baseline and the aligned return are
> the *same quantity* for BULL (excess ≡ 0 exactly) and *exact negatives* for BEAR
> (excess ≡ −2 × drift). Verified in the raw sums: BULL Mon aligned 710.9578, drift
> 710.9578; BEAR Mon aligned 702.1242, drift −702.1242. Reporting a number there would
> be reporting the arithmetic of the definition, not a property of the market. **Drift
> comparison requires a cell containing both directions.**

| cell | n | 3d hit | 3d Wilson 95% | 3d mean aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d mean aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| BEAR Mon | 588 | **56.63%** | [52.60, 60.58] | +1.1941 | *identity* | **40.99%** | [37.08, 45.01] | -1.0210 | *identity* |
| BULL Mon | 604 | **57.45%** | [53.47, 61.33] | +1.1771 | *identity* | 46.69% | [42.74, 50.68] | +0.0544 | *identity* |
| BEAR Tue | 540 | **55.00%** | [50.78, 59.15] | -0.3952 | *identity* | **45.74%** | [41.58, 49.96] | -1.0296 | *identity* |
| BULL Tue | 645 | 47.75% | [43.92, 51.61] | -0.1669 | *identity* | **43.72%** | [39.94, 47.58] | -0.6178 | *identity* |
| BEAR Wed | 544 | **44.49%** | [40.36, 48.69] | -0.1682 | *identity* | **54.60%** | [50.39, 58.73] | +0.5876 | *identity* |
| BULL Wed | 612 | **43.14%** | [39.27, 47.09] | -0.5865 | *identity* | 50.49% | [46.54, 54.44] | +0.1997 | *identity* |
| BEAR Thu | 718 | 49.58% | [45.94, 53.23] | +0.0533 | *identity* | **57.80%** | [54.15, 61.36] | +1.0065 | *identity* |
| BULL Thu | 823 | 51.64% | [48.23, 55.04] | +0.9198 | *identity* | **57.23%** | [53.82, 60.57] | +1.4665 | *identity* |
| BEAR Fri | 491 | **61.71%** | [57.34, 65.90] | +0.9010 | *identity* | **55.60%** | [51.18, 59.94] | +2.1608 | *identity* |
| BULL Fri | 533 | **56.66%** | [52.42, 60.80] | +1.3996 | *identity* | **55.72%** | [51.48, 59.88] | +1.9731 | *identity* |

## (c0) PREMIUM TERCILE — totals, for reference

| cell | n | 3d hit | 3d Wilson 95% | 3d mean aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d mean aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| T1 | 2033 | 51.60% | [49.43, 53.77] | +0.4456 | +0.3523 | **52.19%** | [50.02, 54.35] | +0.8985 | +0.7049 |
| T2 | 2033 | **52.34%** | [50.16, 54.50] | +0.4313 | +0.2169 | **52.24%** | [50.06, 54.40] | +0.5046 | +0.1549 |
| T3 | 2032 | **52.36%** | [50.19, 54.53] | +0.4145 | +0.2947 | 48.77% | [46.60, 50.94] | +0.0540 | +0.0718 |

## (c) PREMIUM TERCILE × DAY-OF-WEEK

| cell | n | 3d hit | 3d Wilson 95% | 3d mean aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d mean aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| T1 Mon | 377 | **60.21%** | [55.19, 65.03] | +1.7107 | +1.3084 | 48.01% | [43.01, 53.05] | +0.9329 | -0.3732 |
| T1 Tue | 381 | 51.71% | [46.70, 56.68] | +0.2304 | +0.1213 | 47.77% | [42.80, 52.78] | -0.1140 | -0.2165 |
| T1 Wed | 423 | **43.26%** | [38.62, 48.02] | -0.4538 | -0.1161 | 51.54% | [46.78, 56.26] | +0.6846 | +1.1246 |
| T1 Thu | 515 | 49.32% | [45.02, 53.63] | +0.2237 | +0.1886 | **56.70%** | [52.39, 60.91] | +1.2625 | +1.1030 |
| T1 Fri | 337 | **55.79%** | [50.45, 60.99] | +0.7420 | +0.3817 | **55.79%** | [50.45, 60.99] | +1.7168 | +1.8173 |
| T2 Mon | 407 | **56.76%** | [51.90, 61.48] | +1.3668 | +1.5896 | 45.95% | [41.16, 50.80] | -0.2390 | -0.5599 |
| T2 Tue | 406 | 50.00% | [45.16, 54.84] | -0.6295 | -0.3811 | **43.84%** | [39.10, 48.70] | -1.0438 | -0.9915 |
| T2 Wed | 382 | **42.15%** | [37.30, 47.15] | -0.5668 | -0.7673 | 50.79% | [45.79, 55.77] | -0.1259 | -0.3976 |
| T2 Thu | 505 | 53.07% | [48.71, 57.38] | +1.0993 | -0.1638 | **61.19%** | [56.87, 65.34] | +1.9348 | +0.9482 |
| T2 Fri | 333 | **60.36%** | [55.02, 65.47] | +0.7134 | +0.9744 | **58.26%** | [52.90, 63.43] | +1.8555 | +1.8572 |
| T3 Mon | 408 | 54.41% | [49.56, 59.18] | +0.5193 | +0.6470 | **37.99%** | [33.41, 42.79] | -2.0145 | -2.0395 |
| T3 Tue | 398 | 51.51% | [46.61, 56.38] | -0.3853 | -0.7999 | **42.46%** | [37.70, 47.37] | -1.2243 | -1.5753 |
| T3 Wed | 351 | 46.15% | [41.01, 51.38] | -0.1194 | +0.4537 | **55.27%** | [50.04, 60.39] | +0.5710 | +0.8989 |
| T3 Thu | 521 | 49.71% | [45.44, 53.99] | +0.2398 | +0.1194 | **54.70%** | [50.41, 58.93] | +0.5803 | +0.7649 |
| T3 Fri | 354 | **61.02%** | [55.84, 65.95] | +1.9796 | +1.2194 | 53.11% | [47.90, 58.24] | +2.5881 | +2.5169 |

## (d) TICKER CLASS — TEMPORARY PROXY RULE

> **TEMPORARY RULE, labeled as such.** `CORE4` = SPY · QQQ · IWM · SMH; `OTHER` =
> everything else. This is a **proxy until S3 ships** and is not the product-type
> instrument class ruled into Amendment 1. It is also **not** `INDEX_TICKERS`
> (`triton_shadow_common.py:20`), which is a $2M premium tier containing six single
> names — do not conflate the two.

| cell | n | 3d hit | 3d Wilson 95% | 3d mean aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d mean aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| CORE4 | 1269 | **60.36%** | [57.64, 63.02] | +0.5929 | +0.6395 | **54.14%** | [51.39, 56.86] | +0.7356 | +0.8353 |
| OTHER | 4829 | 49.93% | [48.52, 51.34] | +0.3878 | +0.1955 | 50.26% | [48.85, 51.67] | +0.4201 | +0.1727 |

---

## INTERNAL STABILITY OF THE TABLE — descriptive only, no market claim

These are observations about **how the numbers behave across horizons**, not about the market.
They are stated because a cell that reverses between 3d and 5d is evidence about the *table*,
and that is a measurement property a reader can check without any interpretation.

**1 — The midweek hypothesis is supported at one horizon and contradicted at the other.**
At 3d the edges clear and midweek does not (Mon+Fri **57.99%** [55.92, 60.03]; Tue-Thu 48.74%,
straddling). At 5d the relation reverses (Tue-Thu **52.06%** [50.49, 53.63]; Mon+Fri 49.32%,
straddling). **Both horizons are drawn from the same rows.**

**2 — Monday reverses sign, and both readings exclude 50.**
3d **57.05%** [54.22, 59.83] · 5d **43.88%** [41.08, 46.71]. Two intervals from one cell,
neither containing 50, pointing opposite ways. The same reversal appears in T3 Mon
(3d 54.41% straddling → 5d **37.99%** [33.41, 42.79]) and in BEAR Mon.

**3 — Friday is the only weekday above 50 at both horizons** (3d **59.08%**, 5d **55.66%**),
and Wednesday the only one below at 3d while above at 5d.

**4 — The premium terciles are flat at 3d and ordered at 5d.**
3d: 51.60 / 52.34 / 52.36 — a 0.76-point spread across the whole premium range. 5d: 52.19 /
52.24 / **48.77** — the monotonic decline the audit reported. The tercile relation the audit
found at 5d **does not appear at 3d.**

**5 — (d) is the only cut whose two horizons agree.** CORE4 clears 50 at both
(3d **60.36%** [57.64, 63.02]; 5d **54.14%** [51.39, 56.86]), with excess positive at both,
while OTHER straddles at both. Every other cut above has at least one cell that reverses.

**None of this is corrected for multiplicity, and none of it is a recommendation.** Cut (d)
rests on a temporary proxy rule that S3 will replace.

---

## WHAT THIS READ DOES NOT ESTABLISH

- **No cell is corrected for multiplicity.** With this many cells at 95%, bold marks are
  expected even under a null.
- **Weekday cells are unequal by construction** — Thursday carries 1,541 rows against
  Friday's 1,024, a 50% spread, before any outcome is considered.
- **Costless.** No friction at any clip size. The largest excess figures here are of the
  same order as the spread on a single option leg.
- **Terciles are global**, cut over all 6,098 rows by `premium_usd`, then crossed with
  weekday — so a tercile means the same thing on every day.
- **The holdout was not read.** Every predicate carries `fired_at < 2026-08-17`.

No recommendation is offered.
