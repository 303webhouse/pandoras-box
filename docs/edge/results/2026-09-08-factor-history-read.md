# FACTOR HISTORY — THE READ INVERTS THE EXPECTATION (R-IV.330)

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD
**Vintage (in-DB UTC): `2026-09-09 02:30:57.997130+00`** · read-only

## HEADLINE — HISTORY EXISTS, AND MY EARLIER CENSUS WAS WRONG

**`factor_readings` is alive and dense.** It is the table of record for per-factor readings,
and I did not check it.

| table | rows | last write | rows in last 7 days | factors |
|---|---|---|---|---|
| **`factor_readings`** | **327,828** | **2026-09-09 02:20:54** | **11,654** | **28** |
| `bias_composite_history` | 32,614 | 2026-09-09 02:20:56 | 851 | — (`factor_scores` jsonb) |
| `factor_history` | 4,507 | 2026-07-23 08:00:00 | **0** | 8 |
| `bias_history` | **0** | — | 0 | — |

**Correction I own.** The Moby Dick census (R-IV.269, leg (b)) stated that *"the whole
factor-history surface has been dark ~6 weeks."* **That is false.** I queried one table named
`factor_history`, found its last write on 07-23, and reported a property of the *surface* from
one member of it. `factor_readings` — 25× larger, differently named, currently writing — was
never probed.

Same family as the case-sensitivity miss in the phantom sweep: **a probe that covered one
candidate, reported as coverage of the class.** The consequence here is larger, because a
"no history exists" finding was about to become the justification for the third sink
(R-IV.329(a)(3)). **It should not.** The sink's justification has to be re-derived from what
is actually missing, which is narrower and is set out below.

`factor_history` and the `excess_cape` factor both stop at exactly `2026-07-23 08:00:00.501827`
— they are the same series written to two places, and that one series did die then. That is
what I saw, and I generalized it.

## THE 0.0 FACTORS — 7-DAY SERIES AND WHETHER THEY VARY

`dxy_trend`, the factor behind R-IV.321(b), **has a full week of history and does vary — barely:**

| factor | rows 7d | distinct scores | range | zero rows | avg |
|---|---|---|---|---|---|
| **`dxy_trend`** | 696 | **2** | −0.15 … 0.00 | **588 of 696 (84.5%)** | −0.0233 |
| `gex` | 696 | 3 | −0.30 … 0.00 | 509 (73.1%) | −0.0608 |
| `spy_trend_intraday` | 696 | 4 | −0.70 … 0.20 | 484 (69.5%) | −0.0359 |
| `copper_gold_ratio` | 696 | 4 | −0.70 … 0.70 | 470 (67.5%) | +0.0244 |
| `breadth_intraday` | 486 | 5 | −0.30 … 0.70 | 62 (12.8%) | +0.1879 |
| `tick_breadth` | **98** | 16 | −0.96 … 0.00 | 3 | −0.4167 |

**So a 0.0 reading is distinguishable from a dead one — for these six.** `dxy_trend` reads 0.0
in five of every six observations and −0.15 otherwise. It is **live, two-valued, and mostly
neutral** — not dark.

**`tick_breadth` is the exception worth flagging:** 98 rows against 696 for its peers, and its
last reading is `2026-09-08 20:00:16` while the others wrote at `2026-09-09 02:20`. It is
thinning, not dead.

## THE ACTUAL DEFECT IS THE OPPOSITE SHAPE — SIX FACTORS HAVE ZERO VARIANCE

| factor | rows 7d | distinct scores | pinned at |
|---|---|---|---|
| `initial_claims` | 696 | **1** | +0.40 |
| `iv_regime` | 696 | **1** | +0.20 |
| `mcclellan_oscillator` | 696 | **1** | −0.10 |
| `sahm_rule` | 696 | **1** | +0.50 |
| `spy_200sma_distance` | 663 | **1** | +0.60 |
| `yield_curve` | 696 | **1** | +0.10 |

**Six of eighteen live factors returned a single value across ~700 readings in seven days.**
They are not 0.0 and they are not dark — they are **constant**, which for a scoring input is
the dead-field shape: it contributes a fixed offset and cannot discriminate between any two
moments. A weekly-cadence macro series (claims, Sahm, yield curve) being flat intraday is
expected; `spy_200sma_distance` and `iv_regime` being flat for a week are not obviously so.

**This is a different finding from the one the ruling anticipated, and it is checkable the same
way** — variance over a window, per factor, which `factor_readings` supports today.

## TEN FACTORS ARE GENUINELY DARK

| factor | rows all-time | last reading | silence |
|---|---|---|---|
| `excess_cape` | 1,438 | 2026-07-23 | **47 days** |
| `savita` | 3 | 2026-06-09 | 92 days |
| `polygon_oi_ratio` | 531 | 2026-03-04 | 188 days |
| `polygon_pcr` | 558 | 2026-03-04 | 188 days |
| `put_call_ratio` | 1,074 | 2026-03-04 | 188 days |
| `high_yield_oas` | 1,085 | 2026-03-04 | 188 days |
| `vix_regime` | 1,085 | 2026-03-04 | 188 days |
| `breadth_momentum` | 545 | 2026-02-27 | 193 days |
| `options_sentiment` | 542 | 2026-02-27 | 193 days |
| `dollar_smile` | 39 | 2026-02-27 | 193 days |

**Nine of the ten stopped in a two-week span (02-27 → 03-04)** — one event, not ten. That
clustering is the diagnosis worth having and it is not in any document I have seen.

## WHAT THE THIRD SINK'S JUSTIFICATION SHOULD REST ON INSTEAD

Not *"no reading is kept"* — readings are kept, at ~100/day/factor, back to 2025-04-24.
The narrower true statements:

1. **`bias_history` is empty (0 rows)** while `bias_composite_history` is not — one of the two
   is dead and the naming does not say which is canonical.
2. **`factor_history` is a stale duplicate** of a series that also lives in `factor_readings`;
   two tables, one series, one of them frozen since 07-23.
3. **Nothing records why a factor stopped.** Ten dark factors, nine of them stopping inside two
   weeks, and no artifact anywhere states the cause — the same no-skip-reason shape as
   `DEF-TRITON-GRADER-NO-SKIP-REASON`.

**Note:** `docs/defects/DEF-FACTOR-HISTORY-DARK.md` exists on disk. I have not read it, so I do
not know whether it rests on my incorrect generalization. **If it cites the Moby census leg (b),
it needs the correction above.** Flagged rather than assumed.
