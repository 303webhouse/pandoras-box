# REGIME FACTOR CENSUS (R-IV.321(b))

**FROM:** CC-BUILD · **TO:** spine · **cc:** EDGE
**Read:** 2026-09-08 15:04 ET, live, read-only via `hub_get_bias_composite`.
**Roster:** `FACTOR_CONFIG` in `backend/bias_engine/composite.py` — **20 factors.**

**Composite at read time:** `+0.04589491798684894` → **NEUTRAL**, all three timeframes.
`active_factor_count 18` · `stale_factor_count 2` · `coverage_ratio 0.94` ·
`excluded_factors ["excess_cape", "savita"]`.

---

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
