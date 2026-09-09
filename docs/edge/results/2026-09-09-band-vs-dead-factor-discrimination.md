# BAND vs DEAD — THE ZERO-VARIANCE SIX, AND THE REAL NULL-AS-NEUTRAL POPULATION (R-IV.332(b))

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD
**Vintage (in-DB UTC): `2026-09-09`** · read-only · window = trailing 7 days

## HEADLINE — ZERO DEAD FIELDS. ALL SIX ARE BANDS.

BUILD's band lesson applied: for every one of the six, **the raw input varies while the score
holds constant.** None is fabricating a score from an absent input.

| factor | raw key | rows | **distinct raw** | raw range | distinct score |
|---|---|---|---|---|---|
| **`iv_regime`** | `vix` | 695 | **123** | 14.01 – 16.59 | **1** |
| `iv_regime` | `iv_rank` | 695 | 93 | 2.7 – 15.3 | 1 |
| `mcclellan_oscillator` | `mcclellan` | 695 | 5 | −49.28 – −2.85 | 1 |
| `spy_200sma_distance` | `pct_distance` | 662 | 5 | 7.55 – 9.00 | 1 |
| `yield_curve` | `spread_pct` | 695 | 3 | 0.40 – 0.43 | 1 |
| `initial_claims` | `latest` | 695 | 2 | 203,000 – 206,000 | 1 |
| `sahm_rule` | `sahm_value` | 695 | 2 | −0.07 – −0.03 | 1 |

**`raw_data` is present on 695 of 696 rows for all seven factors examined.** Nothing here is dead.

## THREE OF THE SIX BEHAVE AS PREDICTED — AND THREE DO NOT

**Predicted-slow, confirmed slow.** `initial_claims` (2 raw values, weekly series),
`sahm_rule` (2 values, −0.07 to −0.03), `yield_curve` (3 values, 0.40 to 0.43). A constant
score on a genuinely static input is a band doing its job, exactly as spine anticipated.

**Not slow, and the band is wide:**

- **`iv_regime` is the standout.** **123 distinct VIX values spanning 14.01 → 16.59**, and
  **93 distinct `iv_rank` values spanning 2.7 → 15.3**, all mapping to the single score
  **+0.20**. A band wide enough to absorb a **2.58-point VIX move** and a **12.6-point iv_rank
  move** without the score responding once in a week.
- **`mcclellan_oscillator`** ranges **−49.28 → −2.85** — a 46-point swing in a breadth
  oscillator — at one score.
- **`spy_200sma_distance`** ranges **7.55% → 9.00%** from its 200-day SMA at one score.

**Those three are not "a banded scorer on a slow input."** The input moved materially and the
band swallowed it. Whether the bands are correctly placed is a scoring-design question, not a
data question — **but it is now measurable**, and the measurement says the flat scores are
band width, not input staleness.

## `dxy_trend` — BAND, NOT FABRICATED

`raw_data` present on every row, and richly varying:

```
current        196 distinct values   98.650 – 99.614
pct_change_5d  211 distinct values   −1.0234 – +0.4477
score            3 distinct values   zeros on 634 of 695 rows (91.2%)
```

**The zeros are a band.** The scorer sees a moving dollar index and emits 0.0 for most of its
range. Not a null read as neutral.

> **Window-drift note.** My R-IV.330 read put `dxy_trend` at **2 distinct scores / 588 zeros of
> 696**; this read, one day later, gives **3 / 634 of 695**. The trailing-7-day window moved.
> Both readings support the same conclusion; stated so the two figures do not look like a
> contradiction.

## THE LIVE POPULATION FOR DEF-BIAS-NULL-AS-NEUTRAL IS **ONE FACTOR, 35 ROWS**

Probed every live factor for the actual defect shape — **a score emitted while `raw_data` is
absent or empty**:

| factor | rows 7d | raw absent | **raw empty** | score = 0 | **ZERO WITH NO RAW** |
|---|---|---|---|---|---|
| **`gex`** | 695 | 0 | **35** | 509 | **35** |
| `breadth_intraday` | 530 | 0 | 0 | 62 | **0** |
| `copper_gold_ratio` | 695 | 0 | 0 | 470 | **0** |
| `dxy_trend` | 695 | 0 | 0 | 634 | **0** |
| `spy_trend_intraday` | 695 | 0 | 0 | 549 | **0** |
| `tick_breadth` | 98 | 0 | 0 | 3 | **0** |

**`gex` is the entire population: 35 readings — 5.0% of its week — where the score is 0.0 and
`raw_data` is `{}`.** Every other zero in every other factor carries a populated raw payload
and is therefore a band.

That is a far narrower defect than "six zero-variance factors," and it is the count spine asked
for: **1 factor, 35 rows.** It is also the only place in this set where a consumer cannot
distinguish "GEX is neutral" from "GEX was unavailable" — because for those 35 readings the
score says neutral and nothing says unavailable.

## WHAT THIS DOES NOT ESTABLISH

- **Whether the bands are correctly placed.** `iv_regime` absorbing a 2.58-point VIX move may
  be deliberate. This read measures the width, not its justification.
- **Why `gex` empties its raw.** The 35 rows show the symptom; the cause is in the scorer, not
  the table.
- **Anything outside the trailing 7 days.** `factor_readings` holds 327,828 rows back to
  2025-04-24; a longer window would give band widths far more precisely than a week does.
