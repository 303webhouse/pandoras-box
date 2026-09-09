# REGIME FACTOR CENSUS (R-IV.321(b))

**FROM:** CC-BUILD · **TO:** spine · **cc:** EDGE
**Read:** 2026-09-08 15:04 ET, live, read-only via `hub_get_bias_composite`.
**Roster:** `FACTOR_CONFIG` in `backend/bias_engine/composite.py` — **20 factors.**

**Composite at read time:** `+0.04589491798684894` → **NEUTRAL**, all three timeframes.
`active_factor_count 18` · `stale_factor_count 2` · `coverage_ratio 0.94` ·
`excluded_factors ["excess_cape", "savita"]`.

---

> # CORRECTION 2 — 2026-09-09. `dxy_trend` IS ALSO WITHDRAWN. THE INSTANCE IS `gex`.
>
> **CC-QUERY's band-vs-dead read (`docs/edge/results/2026-09-09-band-vs-dead-factor-discrimination.md`) measured what this lane inferred, and the
> inference was wrong a second time.**
>
> `dxy_trend` **is a BAND, not a fabrication**: `current` carries **196 distinct values**,
> `pct_change_5d` **211**, and **raw_data is present on every row.** The zeros are a band
> over a moving dollar index. **Zero dead fields across all six examined.**
>
> **THE ACTUAL LIVE POPULATION IS ONE FACTOR, 35 ROWS:** `gex` emits **35 of 695
> readings (5.0%) at score 0.0 with `raw_data = {}`.** Every other factor: **zero such
> rows.** That is the defect's true shape — **a score emitted with its raw input ABSENT**,
> not a score that happens to be zero.
>
> **The mechanism this lane found was right; the instance was wrong.** `gex` is one of the
> `neutral_reading()` callers identified on 2026-09-08. **The helper does fabricate, and it fabricates
> in `gex`** — not in `dxy_trend`, whose no-data branch exists but is not being taken.
>
> ### The error, stated once because it is the same error twice
>
> **First correction:** I read four zero scores as a common cause without checking what zero
> MEANS in each scorer. **Second correction:** I read `neutral_reading()` on `dxy_trend`'s no-data branch as
> evidence the branch was TAKEN. **Both are the same mistake — inferring runtime behaviour
> from static reading, and stopping at the first plausible mechanism.**
>
> **THE DISCRIMINATOR, which is CC-QUERY's and is now the rule:**
>
> ```
> raw varying   under a constant score   ->  BAND     (working as designed)
> raw ABSENT    under any score          ->  FABRICATION (the defect)
> ```
>
> **A score alone can never distinguish them.** The raw payload is the only witness, and it
> is the thing this lane did not look at until CC-QUERY did.
>
> **Bookkeeping, from the source:** `dxy_trend` reads 2 distinct scores / 588 zeros in the
> R-IV.330 artifact and 3 / 634 in this one — **the trailing-7-day window moved one day
> between reads.** Same conclusion; stated so the two figures do not read as a contradiction.

> # CORRECTION — 2026-09-08 evening. THE CENTRAL CLAIM OF FINDING 1 IS WITHDRAWN.
>
> **This census asserted:** *"A factor that computes something does not land on exactly
> 0.000 — four of them doing so simultaneously is a signature, not a market state."*
>
> **THAT IS FALSE, and it is false for three of the four.** Found by tracing the routes
> R-IV.329(b) asked for, before the fix could claim completeness — which is exactly what
> that instruction was for.
>
> **0.0 IS THE DESIGNED MIDDLE BAND of three of these factors:**
>
> ```
> spy_trend_intraday   _score_ema_distance:   -0.3 < pct   <= 0.3   -> 0.0
> breadth_intraday     _score_breadth_ratio:   0.8 < ratio <= 1.2   -> 0.0
> copper_gold_ratio    _score_copper_gold:    -1.0 < spread<= 1.0   -> 0.0
> ```
>
> **A market sitting near its 9 EMA, with balanced up/down volume and copper in line with
> gold, produces exactly 0.000 on all three — correctly.** The simultaneity I called a
> signature is what a quiet tape looks like through banded scorers.
>
> **AND THE EXCLUSION FIX ALREADY EXISTS FOR THEM.** All three return `None` when data is
> missing, and `factor_scorer.py:87-97` **deletes the Redis key** on a `None` return, *"so composite
> excludes this factor instead of using an old cached fallback reading."* **That is
> R-IV.329(b)'s ruled fix, already built, already working.**
>
> **What survives, and it is narrow and real:** `dxy_trend` is the ONE fabricating instance.
> Its `compute_score()` is typed **`-> FactorReading`, not `Optional[FactorReading]`** — it **cannot return `None`**, so the
> scorer's key-deletion path can never fire for it. On the no-data branch it returns
> `neutral_reading()` (`bias_filters/dxy_trend.py:28,34`), a fresh-stamped 0.0. **And `dxy_trend` is independently
> confirmed dead** — `factor_history` holds 0 rows for it since 2026-07-23.
>
> **So: one confirmed dead factor fabricating a neutral, not four.** The defect is real, the
> mechanism is real, and **the population was overstated four-fold by this lane.**
>
> **Why the error happened, since it is the reusable part:** the four zero-readers were
> handed to this lane as suspects, and **all four being zero was treated as evidence of a
> common cause without reading what zero MEANS in each scorer.** A shared value is not a
> shared mechanism. **The check that would have caught it — read the scoring band — costs
> one grep, and was not done until the ruling asked for the other three routes.**

## FINDING 1 — FOUR FACTORS READ 0 AND ARE MARKED FRESH

**All four of spine's named suspects, and they are exactly the ones that read zero:**

| factor | score | staleness | `is_stale` | counted as |
|---|---|---|---|---|
| `spy_trend_intraday` | **0** | 161 s | **false** | **ACTIVE** |
| `breadth_intraday` | **0** | 130 s | **false** | **ACTIVE** |
| `copper_gold_ratio` | **0** | 154 s | **false** | **ACTIVE** |
| `dxy_trend` | **0** | 153 s | **false** | **ACTIVE** |

**No other factor reads 0.** Every one of the remaining fourteen carries a non-zero value,
several of them precise to fifteen decimals (`credit_spreads -0.0277`,
`market_breadth -0.4877`). **A factor that computes something does not land on exactly
0.000 — four of them doing so simultaneously is a signature, not a market state.**

**`dxy_trend` is independently confirmed dead.** The Moby Dick census (`3bbddd58`) measured
`factor_history` at **0 rows for `dxy_trend`**, with the table's last write of any factor on
**2026-07-23**. It has now read a fresh, active `0` for **47 days**.

## FINDING 2 — THE COVERAGE METRIC CANNOT SEE THEM

`coverage_ratio 0.94` is computed from `active_weight_sum` over factors present in `active`.
**All four zero-reading factors ARE in `active`** — they are not stale, not excluded.

```
reported   18 of 20 active, coverage 0.94, 2 excluded (excess_cape, savita)
actual     14 of 20 carrying a measured value
           4 contributing 0.0 without having measured anything
```

**The self-monitor reports 94% coverage while four of its eighteen "covered" factors are
dead.** It cannot report otherwise: a null rendered as 0.0 satisfies every test coverage
applies — present, not stale, in range.

**This is the null-verifier law on a decision surface.** `coverage_ratio` was surfaced
(R-IV.47(d)) precisely so the compute-then-discard `active_weight_sum` would become visible
— and the number it surfaces cannot fall when a factor dies.

## FINDING 3 — THE COMPOSITE IS PULLED TOWARD NEUTRAL BY CONSTRUCTION

A dead factor contributes **0.0**, which is not "no opinion excluded from the mean" — it is
**"neutral, weighted, included."** Four of eighteen actives voting neutral without measuring
anything **drags the composite toward zero**, and the composite reads **+0.046, NEUTRAL**.

**This lane cannot quantify the pull, and the reason is Finding 4.**

## FINDING 4 — EVERY WEIGHT IN THE PAYLOAD IS `null`

```
"name": "vix_term",           "weight": null
"name": "tick_breadth",       "weight": null
...  all 18, without exception
```

**A consumer cannot weight, audit, or reproduce the composite from this surface.** The tool
returns per-factor scores and a composite, and **nothing connecting the two.** Not in
spine's four suspects and not asked for — reported because the census could not compute the
corrected composite without it, which is itself the finding.

## FINDING 5 — THE THREE TIMEFRAMES ARE IDENTICAL

`swing`, `daily` and `intraday` return **the same composite to seventeen decimal places**,
the same eighteen factors, the same coverage, the same exclusions.

**`spy_trend_intraday` and `breadth_intraday` are intraday factors by name.** A swing read
that is byte-identical to an intraday read is not a coincidence at that precision. **Either
the timeframe parameter does not discriminate, or the per-timeframe sub-scores are computed
and then discarded before serialization** — `composite.py:932-935` computes
`timeframe_scores` from `tf_active`, so the machinery exists.

**NOT DIAGNOSED HERE.** Stated as a measurement with its two candidate explanations named.

## SOURCE PATHS — the half this census owed (added 2026-09-08)

**Traced for the four dead factors. The declared sources are in the modules' own headers:**

| factor | module | declared source |
|---|---|---|
| `copper_gold_ratio` | `bias_filters/copper_gold_ratio.py` | *"yfinance COPX (copper miners ETF), GLD (gold ETF)"* |
| `spy_trend_intraday` | `bias_filters/spy_trend_intraday.py` | *"yfinance SPY"* |
| `dxy_trend` | `bias_filters/dxy_trend.py` | computed composite; imports `neutral_reading()` |
| `breadth_intraday` | `bias_filters/breadth_intraday.py` | reads a cached JSON payload (breadth) |

**Two of the four declare yfinance**, which is notable against the standing tension: this
lane recorded on 2026-09-05 that yfinance is *declared fallback, de-facto primary*, and
these two name it as **primary in their own headers**. **A third surface for that tension.**

**And yfinance's measured failure was on BREADTH SYMBOLS specifically** — `^ADVN`,
`^DECLN` and their variants, HTTP 404, while all 15 equity tickers succeeded.
**`breadth_intraday` is a breadth factor.** That is a candidate mechanism for one of the four,
and it is a LEAD not a finding: the module reads a cached payload, so whether the cache is
fed by the failing symbols is unread.

**`bias_filters/copper_gold_ratio.py` names COPX and GLD** — both of which appear in the measured
`/ohlc/1d` fallback list. They resolve through Path B, which falls back and works, so a dead
`copper_gold_ratio` is **not** explained by the UW outage. **Named to close it off, not to blame it.**

## What this census did NOT do

**7-DAY HISTORY WAS NOT READ.** The live payload does not carry it and reading history is a
DB question that belongs with CC-QUERY. **It is the one item of R-IV.321(b) still
outstanding.**

*(Source paths WERE traced — added above on 2026-09-08. This paragraph originally said they
were not, and is corrected rather than deleted so the sequence is legible: the census was
filed with that half owed, and the half was paid the same day.)*

**`excess_cape` and `savita` are correctly excluded** and are the only two the system admits
to missing. **`excess_cape` was the last factor `factor_history` ever recorded** (2026-07-23,
per the Moby Dick census) — so the one factor the roster knows is absent is also the last
one that was alive. Noted; not interpreted.
