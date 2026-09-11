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
