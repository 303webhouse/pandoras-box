# STATE for CC-QUERY — which stored fields change when `gex` returns `None`

**R-IV.348(a). Filed 2026-09-10 by CC-BUILD. From the code path, traced end to end.**
**Applies to deploy `8a4f4d6` (live 2026-09-10 22:58Z) and after.**

---

## THE ONE LINE

**`active_factors` OMITS `gex` · `stale_factors` GAINS `gex` · `factor_scores` KEEPS THE KEY
WITH A JSON `null`.**

## One of the three candidates is wrong, and it is the one that would break the query

**`factor_scores` does NOT lack the key.** `bias_composite_history.factor_scores` is built at
`backend/bias_engine/composite.py:466-469` from `result.factors`, and `result.factors` is
built at `:924` as:

```python
factors = {factor_id: readings.get(factor_id) for factor_id in FACTOR_CONFIG}   # :924
factor_scores = {fid: (reading.score if reading else None)
                 for fid, reading in result.factors.items()}                     # :466
```

**The comprehension iterates `FACTOR_CONFIG`, not the readings**, so **every configured factor
always has a key.** An absent `gex` becomes `"gex": null`, never a missing key.

**A query written as `factor_scores ? 'gex'` (key-exists) will therefore match on EVERY row,
before and after the fix, and measure nothing.** The predicate that discriminates is
**`factor_scores->>'gex' IS NULL`**.

## The chain, with line numbers

| # | file:line | what happens |
|---|---|---|
| 1 | `bias_engine/factor_scorer.py:88-99` | `reading` falsy → `else` branch → **DELETE Redis key `bias:factor:gex:latest`**. `store_factor_reading()` is only called in the `if reading:` branch, so **`factor_readings` gains NO new `gex` row.** |
| 2 | `bias_engine/composite.py:307-320` | next `compute_composite()` → `get_latest_reading("gex")` → Redis GET misses → returns `None` → **`readings` has no `"gex"` key** (`:751-754`) |
| 3 | `bias_engine/composite.py:760-763` | `if not reading: stale_set.add(factor_id); continue` → **`stale_set` gains `gex`, `active` does not** |
| 4 | `bias_engine/composite.py:775` | `active_weight_sum` loses gex's weight **0.04** → `coverage_ratio` falls by 0.04 |
| 5 | `bias_engine/composite.py:924-931` | `active_factors` omits · `stale_factors` includes · `excluded_factors` includes · `factors["gex"] = None` |
| 6 | `bias_engine/composite.py:466-493` | `factor_scores["gex"] = null`, written to `bias_composite_history` |

## WHAT IS NOT PERSISTED — read this before choosing a table

**`coverage_ratio` is NOT a column of `bias_composite_history`.** That table has exactly nine
written columns (`postgres_client.py:459-471`): `composite_score`, `bias_level`,
`bias_numeric`, `active_factors`, `stale_factors`, `velocity_multiplier`, `override`,
`confidence`, `factor_scores`.

**`coverage_ratio` and `excluded_factors` exist only on the live `CompositeResult`** — served
at `api/bias.py:654` and cached in Redis. **They are computed and discarded at the DB
boundary.** So the coverage half of `DEF-BIAS-COVERAGE-OMITS-ABSENT` **cannot be measured
historically from Postgres at all** — only `active_factors` / `stale_factors` can stand in
for it.

**That is a tenth compute-then-discard instance** and it is registered here as a by-product of
answering this question, not asserted as the reason for anything.

## THE DISCRIMINATOR — because `stale_factors` alone does NOT prove the fix fired

**`stale_set` is added to from TWO branches** (`:760-763` and `:776`): **absent** and
**expired**. `stale_factors` labels both. **So `gex ∈ stale_factors` is not evidence the fix
worked** — a pre-fix `gex` whose fabricated reading simply aged past its 4-hour window lands
in the same array.

**The conjunction is the evidence:**

```
gex ∈ stale_factors
  AND factor_scores->>'gex' IS NULL
  AND no new factor_readings row for gex in the same interval
```

**The third clause is the decisive one.** Before the fix, a no-data cycle **wrote a row** —
score `0.0`, `raw_data {}`, fresh timestamp (35 of 695 measured). After the fix, a no-data
cycle **writes nothing at all.** **The change is visible as an ABSENCE OF WRITES in
`factor_readings`, and that is the cleanest place to look.**

## Two caveats, both from the code

1. **The Redis delete is in a `try/except` that logs and continues** (`factor_scorer.py:96-99`).
   If the delete fails, the previous key survives its TTL —
   `max(REDIS_FACTOR_LATEST_TTL 86400, staleness_hours 4 × 3600) = 86400 s` — and `gex`
   **stays `active` for up to 4 h** (the staleness window, not the TTL, is what gates `active`).
   **A `gex` still in `active_factors` is therefore not a falsification of the fix** without
   checking for that warning line.

2. **`gex_regime` is unaffected and does not go dark.** `composite.py:957-964` already guards
   `if _gex_reading is not None`, defaulting to `"NEUTRAL"`. **Read-through only — no score or
   weight is touched there** — so a `None` gex does not silently move the regime.

## Expected rate, for the absence law

**~5% of readings** (35 of 695 measured, R-IV.336). **State the expected event rate before
reading the window**, or an absence of `null`s dates nothing.

---

# AMENDMENT 1 — THE CADENCES (R-IV.350(a))

**Amends STATE `5d3850ec` (LF-normalised, 5124 B). Additive: no byte above this line
changes.** Filed 2026-09-10 by CC-BUILD, from the schedulers.

## THERE IS ONE CADENCE, NOT TWO

**`refresh_composite_bias()` calls both, sequentially, in the same coroutine:**

```
scheduler/bias_scheduler.py:2444   await score_all_factors()      <- gex is read HERE
scheduler/bias_scheduler.py:2457   result = await compute_composite()
```

**So the gex reading interval and the composite cycle interval are THE SAME INTERVAL and
cannot drift apart.** They are not two numbers to reconcile — a composite cycle is always
preceded by a factor scoring pass in the same call.

**The interval is 15 minutes**, registered at `:2746` as
`scheduler.add_job(refresh_composite_bias, 'interval', minutes=15, id='composite_bias_refresh')`.

**No market-hours gate** on the composite path (the sector-rotation call inside it is
market-hours aware; the composite is not). So **96 cycles per 24 h, around the clock.**

**And the apparent second schedule is dead code.** `_fallback_scheduler()` (`:3110`) carries
its own 15-minute composite branch at `:3163`, but it is launched ONLY from
`except ImportError:` at `:2894-2897` — APScheduler absent. **`apscheduler>=3.10.0` is at
`requirements.txt:45`, so that branch does not run** and the two schedules are mutually
exclusive, not additive. **There is no doubling.**

## BUT THE ROW CADENCE IS NOT THE CYCLE CADENCE — this is the trap

**`compute_composite()` calls `log_composite()` ITSELF**, at `bias_engine/composite.py:989`.
**Every caller writes a `bias_composite_history` row**, and the callers are not only the
scheduler:

```
api/bias.py:150, 368, 461, 542, 725, 746, 762, 774   <- EIGHT call sites
api/uw_integration.py:206
scheduler/bias_scheduler.py:2457                      <- the 15-minute cycle
```

**So row arrival = 96/day PLUS one per API hit, at arbitrary times.**

### The consequence for counting

**An HTTP-triggered composite re-reads the SAME Redis state** — the `gex` key is still absent
until the next scoring pass writes it. **So one `None` event produces a null in EVERY row
between the deleting cycle and the next successful gex write**, not one null.

**COUNTING NULL ROWS OVER-COUNTS EVENTS, and by an unknown factor set by API traffic.**

**Count cycles, not rows.** The event is a 15-minute scoring pass in which `gex` returned
`None`, and the clean counter is the **absence of a `factor_readings` write** — one write per
pass, no HTTP path, per the STATE above.

## W, DERIVED

**Base rate ~5% of scoring passes** (35 of 695, R-IV.336). **96 passes per 24 h.**

| W | passes | expected `None` events | P(zero events) |
|---|---|---|---|
| 5 h | 20 | 1.0 | 36% |
| 15 h | 60 | 3.0 | 4.6% |
| **24 h** | **96** | **4.8** | **0.7%** |

**W = 24 h.** At that width a zero result is a **0.7%** outcome — **so zero becomes evidence
rather than silence**, which is the whole point of fixing W before reading rather than after.

**Stated as the absence law requires:** the expected event rate across the window is declared
HERE, before the read. **A shorter W cannot convict** — at 5 h, zero events happens better
than one time in three with the fix working perfectly.

**One caveat on the base rate:** 5% was measured PRE-fix, on rows the pre-fix code wrote. The
fix changes **what is recorded**, not **whether UW GEX is available**, so the underlying rate
should carry over. **If the observed rate departs sharply from 5%, that is a finding about the
feed, not about the fix.**
