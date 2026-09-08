# THIRD MARKET READ — IS IT THE TAPE? (R-IV.302)

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD, OLYMPUS-TRITON, EDGE
**Read vintage (in-DB UTC): `2026-09-07 05:23:37.792538+00`**
**Population:** the audited explore set, n = 6,098 · **holdout untouched, zero rows read.**
**Labels:** HYPOTHESIS GENERATION · post-hoc · **costless** · candidate-tier · daily-bar ·
**Track-A fence.** No recommendation.
**SPY weekly return** computed from `stable_daily_bars` (yfinance), last close of week vs last
close of prior week.

---

## FOR THE COLLECTOR DESIGN LAW — ON THE FACE, AS DIRECTED

> **No underlying quote is stored at print time anywhere in the record.** Probed every `raw`
> key across the population: the only bid/ask-like keys are `total_ask_side_prem` and
> `total_bid_side_prem`, which are **option-premium aggregates on the alert**, not a two-sided
> market on the underlying. `spot_at_fire` is a single price. Control: the same probe returns 2
> keys for `prem`, so it discriminates.
>
> **A costless signal is unmeasurable.** Every excess figure in these three reads is a
> before-friction number, and no retrospective query can convert it — the quote was never
> captured. **The sinks build stores the NBBO at print**, and only signals collected after that
> lands can be measured net of cost.

---

# (b) THE DISCRIMINATOR — ANSWERED FIRST, BECAUSE IT DECIDES THE READ

Spine's test: *if each direction wins only in its own kind of week, the signal is the tape.*

**Neither branch. BULL and BEAR win and lose the SAME weeks, together.**

| week | BEAR 3d hit | BULL 3d hit |
|---|---|---|
| 2026-06-29 | 26.5% | 35.6% |
| 2026-07-06 | 52.5% | 48.1% |
| 2026-07-13 | 44.9% | 38.3% |
| 2026-07-20 | 29.8% | 26.8% |
| **2026-07-27** | **83.0%** | **82.1%** |
| 2026-08-03 | 63.6% | 59.3% |
| 2026-08-10 | 51.3% | 45.9% |

**Pearson r (BEAR hit vs BULL hit across the seven weeks) = +0.962.**

**If the signal were direction-specific, this correlation would be NEGATIVE** — a week whose
tape favours longs makes BULL right and BEAR wrong, by construction of the aligned metric.
It is +0.96. **A common weekly factor moves both sides at once**, and the signal's direction
call is not what determines whether it is right.

That also rules out simple up-tape drift: **BEAR wins in the same weeks BULL does.**

---

# THE HEADLINE — ONE WEEK IS THE ENTIRE RESULT

| population | n | 3d hit | 3d excess |
|---|---|---|---|
| pooled | 6,098 | **52.10%** | **+0.2879** |
| **excluding week 2026-07-27** | 4,901 | **44.66%** | **−0.9023** |
| excluding 07-27 and 08-03 | 3,879 | **40.35%** | **−1.3625** |

**Remove one week of seven and the direction-aligned result inverts** — from +0.29 excess to
**−0.90**, and from above 50% to below it. The audit's 3d cell, the only one that cleared 50%
at 95% in the first read, is produced by 1,197 rows in a single week.

---

# (a) PER WEEK — AND NO, THE CARRYING WEEKS ARE NOT THE BIG TAPE WEEKS

| week | SPY wk % | n | aligned 3d hit | aligned mean | week uncond. mean | **within-week excess** | CORE4 n | CORE4 3d hit |
|---|---|---|---|---|---|---|---|---|
| 2026-06-29 | **+2.166** | 269 | **30.48%** | −3.3336 | +0.8776 | **−4.2112** | 50 | *NOT COMPUTABLE (n=50)* |
| 2026-07-06 | +1.366 | 876 | 50.11% | −0.1108 | −0.3639 | +0.2531 | 153 | 71.24% |
| 2026-07-13 | −1.544 | 1,045 | 41.53% | −1.1770 | +0.0829 | −1.2599 | 202 | 53.96% |
| 2026-07-20 | −0.587 | 1,022 | **28.47%** | −3.7199 | +0.0668 | **−3.7867** | 249 | **12.85%** |
| **2026-07-27** | +1.096 | 1,197 | **82.54%** | +5.7686 | +0.6074 | **+5.1612** | 277 | **91.70%** |
| 2026-08-03 | **+3.511** | 1,022 | 61.06% | +1.0799 | +0.2352 | +0.8447 | 227 | 83.26% |
| 2026-08-10 | +0.398 | 667 | 47.83% | +0.9628 | −0.2552 | +1.2181 | 111 | 51.35% |

**The carrying week is not a big week.** SPY's largest week is **08-03 at +3.511%** — hit 61%.
Its second largest is **06-29 at +2.166%** — hit **30.5%, the second worst of the seven.**
The carrying week, **07-27, is +1.096%** — fifth of seven by magnitude.

```
Pearson r, SPY weekly return   vs aligned 3d hit : +0.341
Pearson r, |SPY weekly return| vs aligned 3d hit : +0.151
```

**Neither the direction nor the size of SPY's week explains which weeks carry.** So the common
weekly factor found in (b) is real but is **not SPY's weekly move** — this read locates it and
does not identify it.

**Within-week excess is positive in 4 of 7 weeks**, but the sum is dominated by 07-27's
**+5.16**; the next largest contribution is +1.22. So the second branch of spine's test —
*aligned sweeps beat the week's own drift within-week* — holds in most weeks but is carried in
magnitude by the same single week.

---

# (c) IN FLAT WEEKS THE SIGNAL IS STRONGLY NEGATIVE

| band | weeks | n | 3d hit | Wilson 95% | aligned mean | excess |
|---|---|---|---|---|---|---|
| **FLAT** \|ret\| < 1% | 07-20, 08-10 | 1,689 | **36.12%** | [33.87, 38.43] | −1.8706 | −1.8102 |
| MID 1–2% | 07-06, 07-13, 07-27 | 3,118 | **59.69%** | [57.95, 61.40] | +1.7889 | +1.6302 |
| LARGE \|ret\| ≥ 2% | 06-29, 08-03 | 1,291 | **54.69%** | [51.95, 57.41] | +0.1602 | −0.2088 |

**The answer to (c) is no — and worse than no.** In flat weeks the aligned hit rate is
**36.12%**, an interval nowhere near 50 and on the wrong side of it. The signal is not merely
absent when the tape is quiet; it is **inverted**.

**But the band cut is week-labelling in disguise, and should not be read as a magnitude
effect.** With seven weeks, each band holds two or three of them: FLAT *is* 07-20 + 08-10, and
07-20 is the 28.5% week. MID contains the carrying week. The bands re-report the weekly
pattern under a different name, and their intervals understate uncertainty badly because the
effective n is **weeks, not rows**.

---

# WHAT THIS READ ESTABLISHES, AND WHAT IT DOES NOT

**Established:**

- **BULL and BEAR are positively correlated across weeks at r = +0.962.** The direction call
  does not determine correctness; a common weekly factor does. **This is the strongest single
  result in the three reads**, and it does not depend on any cost assumption.
- **The pooled 3d edge is one week.** Ex-07-27 the excess is **−0.9023** and the hit rate
  **44.66%**.
- **In flat SPY weeks the aligned hit is 36.12%.**

**Not established:**

- **What the weekly factor is.** It is not SPY's weekly return (r = +0.34) and not its
  magnitude (r = +0.15). Locating it needs a candidate — dispersion, realised vol, a single
  event in the forward window — and each is a separate read.
- **Anything about cost.** No underlying quote exists at print time; see the face note.
- **Anything with 7 effective observations.** Every weekly cut here has n = 7 in the unit that
  matters. Row-level Wilson intervals **overstate confidence** wherever the variation is weekly,
  which is everywhere in this read.

**Multiplicity:** these three reads have now examined **≈70 cells** across two horizons on one
population of 6,098 rows, each read directed at the cut that looked strongest in the previous
one. No correction is applied at any stage.

No recommendation is offered.
