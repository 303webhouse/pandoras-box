# UW AS THE PRIMARY SOURCE OF DAILY BARS — CLOSED: NO (R-IV.435(d))

**R-IV.433(d) prepared it; R-IV.435(d) CLOSED it: NO.** yfinance stays primary for bars. **Author:** CC-BUILD.
**Written:** 2026-09-17 13:32 UTC (07:32 MDT). **Code read at:** 2bc8a59 plus the R-IV.432/433 working tree.
**Inputs:** call volumes below are READ FROM CODE (universe sizes, cadences), not measured.
The measured half — how many calls each consumer actually makes today — is CC-QUERY's census
(R-IV.433(a)) and the governor's per-caller counters. Where a number is not known it is a named
slot, not a guess.

---

## THE DECIDING FACT (R-IV.435(d)) — A 365-DAY HARD CEILING

**UW returns at most one year of daily bars: 410 sessions requested, 252 returned.** Measured by
CC-QUERY. That ends it on its own, before any budget question:

- the Stable backfill is **5 years**, and MA200 / 52-week metrics need more than one year;
- a multi-year consumer cannot be served at ANY price, so the move could only ever have been
  partial — which means two vendors inside one series, the APH seam by construction;
- and the volume answer fails too: **~29,000 calls on a heavy weekday against a 28,000 hub
  budget**, so it does not fit even with the reserve released.

**Decision: NO. yfinance stays primary for daily bars.** What ships instead was already ruled and
is already built: vendor and basis on every stored row (conventions #20) and announced
substitution (conventions #21). The section below is the pricing as it stood when the question
was open; it is kept because it records what was measured, not to reopen it.

## THE ANSWER AS IT STOOD BEFORE THE CEILING WAS MEASURED

**Daily bars on UW cost roughly 1,000–3,500 calls a trading day at today's universes, which fits
under the 40,000 account limit. The cost is not the constraint. Four other things break first**:
the governor's after-hours gate, UW's unmeasured history depth, a basis change across every
stored series, and UW's missing coverage of index symbols.

## 1. THE BUDGET TODAY (from code)

| | calls/day |
|---|---|
| UW account limit (`x-uw-token-req-limit`) | 40,000 |
| reserve held for spend this process does not make (`UW_FOREIGN_RESERVE`) | 12,000 |
| hub budget (`DAILY_BUDGET`) | 28,000 |
| safety buffer | 2,000 |
| **per-caller quota table, summed** (incl. the new `ohlc_grader`, 200) | **25,000** |
| headroom inside the hub budget | 1,000 |

*The comment beside `DAILY_BUDGET` in `uw_api_cache.py` says 20,000. The arithmetic gives
28,000. The comment is stale.*

**R-IV.438(a):** that spend is no longer attributed to the VPS collector — the host was
inactive for months and those processes never ran. The remaining hypothesis is the leaked key,
rotated 2026-09-17. **If the post-rotation meter shows the gap gone, the 12,000 reserve is
releasable.**
`account_shed()` still sheds tiers by UW's own counter if it returns. Releasing it is a
one-constant change, and it is the principal's call.

## 2. WHAT UW-PRIMARY DAILY BARS WOULD COST

**UW has no batch bar endpoint.** `/api/stock/{ticker}/ohlc/1d` is one call per ticker, where
yfinance downloads a hundred tickers in one request. So the bill is tickers x runs.

| consumer | today | tickers | runs/day | **UW calls/day** | notes |
|---|---|---|---|---|---|
| Stable Engine nightly (`stable_jobs`, 21:00 ET) | yfinance batch | 690 + 5 benchmarks | 1 | **695** | 15-day refresh; a split-type event would need a full refetch (R-IV.428(a)(2)) |
| CTA scanner (`cta_scanner`, hourly in RTH) | yfinance, per ticker, 1y | up to 200 | ~7 | **up to 1,400** | the largest single item |
| CIRCE'S STEW (16:30 ET) | yfinance batch | ~240 | 1 | **~240** | |
| shadow grader (17:40 ET) | yfinance batch | ~270 on its first pass, then SLOT | 1 | **~270, then less** | its second-vendor check is already UW (<= 40) |
| equity outcome grading (`outcome_resolver`, `score_signals`) | yfinance | SLOT (distinct tickers with pending rows) | SLOT | **SLOT** | census |
| other daily-bar scanners (sell_the_rip, hybrid, wh_reversal, sector_rs) | yfinance | SLOT | SLOT | **SLOT** | census |
| universe cache, A3 forward returns, Triton grader | **already UW** (`ohlc_bars`, `triton_flow_shadow`) | — | — | 0 new | yfinance is their fallback today |
| macro/bias factors (^VIX, ^TNX, DX-Y.NYB, ...) | yfinance | — | — | **not movable** | UW does not carry Yahoo-style indices; yfinance is primary BY DESIGN |

**Read from code: ~2,600 calls/day** (695 + 1,400 + 240 + 270) **before the SLOTs.** Plausibly
**3,500 with them.** Caching changes the CTA line most: `get_ohlc` caches for 60 seconds, which
does not span an hourly scan.

**Against the budget:** 3,500 does not fit in today's 1,000 headroom. It fits comfortably once
the reserve is released (up to ~13,000 headroom), or if the CTA scan stops re-downloading a
year of history every hour (a same-day cache would cut its line to ~200).

## 3. WHAT BREAKS — in the order it would bite

1. **The governor's after-hours gate.** Outside RTH, STANDARD callers keep 25% of their quota
   and BACKGROUND keep 0% (`NON_RTH_QUOTA_FACTOR`). The Stable nightly runs at 21:00 ET, so a
   STANDARD tag would need a quota of about 2,800 to spend 695 after hours. A BACKGROUND tag could
   not run at all. **An after-hours bulk job is exactly what the gate was built to stop.** It
   needs its own rule: a scheduled-job tier, or a named exemption for the nightly.
2. **History depth is unmeasured.**
   - The Stable backfill is 5 years (1,264 sessions), and its MA200 and 52-week metrics need more
     than a year.
   - `get_bars` caps UW lookback at 730 days. Phase 0 probed flow, dark pool and GEX, **not
     stock OHLC depth**.
   - Until that is measured, backfills stay on yfinance, and a store with two vendors inside one
     series is the APH seam again.
3. **A basis change across every stored series.**
   - The Stable store is yfinance `auto_adjust=True`: split AND dividend adjusted.
   - UW is split-adjusted on the one event observed (KORU), with its dividend convention
     unobserved.
   - Switching vendors changes the basis of every price and requires a **full rebuild** of the
     store and every metric, not an incremental swap. A partial refresh is what produced the APH
     seam.
   - Each row then has to say which vendor and basis it is on (conventions #20).
4. **Coverage.**
   - Yahoo-style indices stay on yfinance by design.
   - Some universe members may be absent from UW: ETFs, share classes (BRK.B, BF.B), recent
     listings. Every absence is a fallback, which conventions #21 now announces on `/health`.
   - **The fallback rate is unknown until it is tried.**
5. **Throughput.**
   - The token bucket sustains 120 calls a minute across all callers, so the nightly's 695
     calls take ~6 minutes at best.
   - The circuit breaker opens for 5 minutes after 5 failures, and one bad stretch stalls the
     nightly into its retry loop.
   - The nightly already has a completion-backed retry until 23:59 ET.
6. **Intraday bars are out of scope.** Holy Grail's 1H and Scout Sniper's 15m are not daily bars
   and are not priced here.

## 4. WHAT THE PRINCIPAL IS BEING ASKED

- **Release the 12,000 foreign reserve?** This is the enabling decision; without it the move
  does not fit.
- **Which consumers move?** A reasonable first cut:
  - the Stable nightly (695);
  - CIRCE (240) and the shadow grader (270), whose outcomes most need a vendor on the row.
- **Which stay on yfinance?**
  - the backfills and anything needing more than 2 years of history, until UW depth is
    measured;
  - Yahoo indices, permanently.
- **CTA (1,400):** move it with a same-day cache (~200), or leave it on yfinance.

## 5. WHAT IS STILL NEEDED BEFORE THE NUMBER IS FINAL

- CC-QUERY's census (R-IV.433(a)): every daily-bar consumer, its vendor, its fallback.
- Measured per-caller counts for a full trading day (`uw:daily_requests_by_caller:{date}`).
- A UW stock-OHLC depth probe: how many sessions `/ohlc/1d` returns for SPY and for a
  small-cap, and whether it is split- and dividend-adjusted.
- The SLOT rows above.
