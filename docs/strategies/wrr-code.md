# WRR-CODE: the coded WRR (working name; the principal names it)

| field | value |
|---|---|
| signal_type / strategy keys | `NEMESIS_LONG` / `nemesis_wrr` (`backend/strategies/wrr_buy_model.py:158-159`) |
| emitting code | `scan_wrr` (`wrr_buy_model.py:77-199`) → `run_wrr_and_process` → `process_signal_unified(signal, source="wrr_scanner")` (`:218`) |
| side | LONG only (`:160`). No short side exists in code |
| grid cell | **WITH-TREND LONG.** A washout dip-buy in a name above its 200-day (`:128-131`); R-IV.823(c)2 places it here as a candidate |
| incumbent it would replace | none named |
| schedule / trigger | `CronTrigger(mon-fri, 16:20 ET)`, id `wrr_daily_scan` (`backend/scheduler/bias_scheduler.py:2862-2863`); job `run_wrr_scan_job` (`:2361`), importing `run_wrr_and_process` (`:2379`) |
| status | **SHADOW**: `NEMESIS_LONG` in `SUPPRESS_ALWAYS` (`backend/config/l0_routing.py:64`). **BROKEN until 314fc21** (2026-10-09): it had never emitted a row (below) |
| bucket ceiling | **UNSET.** It is neither before-the-turn nor flow-originated, so R-IV.823(c)3–4 don't apply. Needs a ruling before SURFACE |
| lifetime tries counter | **0** |

## Rules as coded (HEAD = 314fc21)
| # | rule | where |
|---|---|---|
| universe | `build_scan_universe(max_tickers=200, respect_muted=True)` | `:86` |
| bars | daily, `get_bars(ticker, 1, "day", from_date=today−400d)`, needs ≥ 205 bars | `:39`, `:111-113` |
| 1 | close > SMA200 (simple mean of the last 200 closes) | `:128-131` |
| 2 | RSI(3) ≤ 10. A plain-mean RSI, not Wilder; 100 when there are no losses | `:29`, `:42-55`, `:133-136` |
| 3 | ROC(10) ≤ −8% | `:31`, `:138-143` |
| 4 | volume ≥ 1.5× the mean of the 20 *prior* bars | `:32`, `:145-148` |
| 5 | reversal candle: close > open AND (lower wick ≥ 2× body OR body > 60% of range) | `:58-74`, `:150-152` |
| levels | stop = low × 0.98; one target at 3R | `:164-165` |
| flags | `countertrend: True`, `half_size: True` | `:166-167` |

**Pipeline gate** (`backend/signals/pipeline.py`): `_is_nemesis` (`:746`) routes Nemesis rows to a
branch that **records** the countertrend verdict in `triggering_factors.countertrend_gate` with
`"enforced": False` (`:761`). The row is always saved. The March 25/75 thresholds and the live
−1..+1 composite are on different scales (`:725-740`), which is why it is not enforced.

## Where it differs from the approved spec (nemesis.md)
1. LONG only; the spec has both sides.
2. Names: `NEMESIS_LONG`/`nemesis_wrr`, not `WRR_LONG` with a lane.
3. **Adds** a 200-day trend filter the spec doesn't have. This is what makes it with-trend.
4. No bias test in the scanner. The pipeline records it unenforced.
5. No 3-down-days / 20-day-low test.
6. RSI(3) ≤ 10, not ≤ 15, and a plain-mean RSI.
7. ROC(10) ≤ −8%; the spec gives no number.
8. Candle: no engulfing comparison, no doji branch.
9. Volume: equivalent (20 prior bars).
10. No ATR or support-proximity test.
11. Stop low × 0.98, not low − 0.5 ATR.
12. One 3R target, not TP1 1.5R + TP2 reversion.
13. No 2–3 day hold or expiry.
14. Committee threshold 90 is defined (`pipeline.py:128`) and used nowhere.
15. Universe 200 (scan universe), not the 207-ticker watchlist.
16. Bars from UW `get_bars`, not Polygon.
17. Schedule 16:20, not 16:15.
18. Suppressed (L0), not surfaced in a countertrend lane.

## Evidence so far
- **Zero rows, ever.** The permitted count in 314fc21's message is
  `SELECT COUNT(*) FROM signals WHERE strategy = 'nemesis_wrr' OR signal_type LIKE 'NEMESIS%';` → 0.
- Cause, per 314fc21: the job imported a nonexistent `run_wrr_scan` and swallowed the error
  while APScheduler reported success, and the 60-day default bars window could never pass the
  205-bar guard.
- 314fc21's dry run: 197 tickers scanned, 0 hits (one session).
- Replay V-CODE is Task 5 (R-IV.809(g)).

## Kill rule
LAB proposal (SPINE and QUERY decide): retire if the V-CODE replay fails stage 1 market-adjusted at
1–3 days against control (C) (same date, all universe names above their 200-day), or fails stage 2.

## Change log
- 2026-03-17: built (9f40b4a); 2026-03-17 wired with a broken import (22d47de); 2026-04-15 bars to UW (7e19fbf).
- 2026-10-09: 314fc21: import, bars window and gate-scale fixes; L0 SHADOW. Card v0.
