# GRADER BAR PROVENANCE + DEF-UW-OHLC-DEAD ONSET (R-IV.288)

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD
**Vintage (in-DB UTC): `2026-09-06 05:51:53.034907+00`** · read-only

## (a) THE 09-02 RUN USED UW BARS. THE CERTIFICATE DOES NOT NEED RESTATING.

**Three independent proofs, any one sufficient.**

**1 — Path.** The grader reaches bars through `fetch_r_close_index` →
`get_ohlc(...)` at `backend/integrations/uw_api.py:223`. **`get_ohlc` has no fallback** — it
returns `None` when UW yields nothing. The yfinance fallback cited in DEF-UW-OHLC-DEAD lives
at `:663`, inside `get_bars(...)` — **a different function the grader never calls.**

**2 — Shape.** `fetch_r_close_index` keeps a bar only if
`market_time == "r"`, then reads `start_time`/`date` and `close`. `_fetch_yfinance_bars`
(`:1569`) emits Polygon shape — `o/h/l/c/v/vw/t/n`. It carries **no `market_time`, no
`start_time`, no `date`, no `close`.** A yfinance bar fails three separate field checks and
is dropped. Even if the fallback were reachable, the index would come back empty and every
row would be skipped.

**3 — Cache cannot bridge.** `CACHE_TTLS["ohlc"] = 300` (5 minutes). Nothing cached from a
prior day could serve a 20:41Z run.

**Therefore the 573 rows graded at `2026-09-02 20:41:55Z` could only have come from live UW
bars.** The grader is, incidentally, a UW-ohlc liveness probe: **it grades nothing unless UW
serves.**

**Consequence for R-IV.241:** the external arm was **cross-vendor for every row class** —
grader UW, recompute yfinance. No per-class restatement is required and the scope does not
move.

**The 0.0001 is not a same-vendor fingerprint**, and the sample says so independently:
`BURST 08-17` also shows max |delta| **0.0001**, and **94 of 102 cells are exactly 0.0000
across all four batches**. Near-exactness is a property of liquid tickers on which UW and
yfinance agree to the cent, not of the post-repair batch.

**Offered, not applied:** a provenance line on the artifact's face — *"grader bars UW
(`get_ohlc`, no fallback path, `market_time='r'` filter); recompute bars yfinance
(`stable_daily_bars`); vendor separation proven, not assumed."* That strengthens the
certificate from asserted independence to demonstrated. Not applied unilaterally — the
artifact is gated at `551f9430…` and the settled-manifest rule bars edits to a listed file
until BUILD confirms filing.

## (b) ONSET BOUNDED — THE FENCED HYPOTHESIS IS FALSIFIED

The grader's own writes date UW liveness, because it cannot grade without UW bars:

```
2026-08-17 20:38:09Z    962 rows graded   -> UW /ohlc/1d ALIVE
2026-08-26 20:32:39Z      9 rows          -> ALIVE
2026-08-27 20:28:16Z  1,862 rows          -> ALIVE
2026-09-02 20:41:55Z    573 rows          -> ALIVE   (last proof of life)
2026-09-05             measured DEAD by CC-BUILD, twice, incl. a fresh boot
```

**ONSET: after `2026-09-02 20:41:55Z`, at or before `2026-09-05`.**

**NOT at or before 07-31.** UW `/ohlc/1d` demonstrably served on 08-17, 08-27 and 09-02 —
all after the grader's 07-31 death. **One mechanism does not explain both.** The grader's
outage is the `last_run`-in-memory / no-timeout loop diagnosed at R-IV.241; DEF-UW-OHLC-DEAD
is a separate, later failure. **T1 is not the fix for the grader's cause**, and consolidating
them would leave the loop defect unfixed behind a repaired vendor path.

**Burn data gives no onset signal, and that is itself the defect's shape.** `ohlc_bars` runs
1,689–2,018 calls/day straight through 09-04 (09-05's 722 matches the weekend level of
641/644 on 08-29/08-30). Calls keep being made and consumers keep getting bars — **a silent
fallback leaves no volume signature.** The only instrument that dated this was a consumer
that has no fallback.
