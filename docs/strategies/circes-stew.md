# CIRCE'S STEW | Fade the Breakout

| field | value |
|---|---|
| signal_type / strategy keys | `CIRCES_STEW` / `circes_stew`, both sides; direction in `direction` (`backend/scanners/circes_stew.py:42-44`; `backend/jobs/circes_stew_job.py:216-221`); source `circes_stew` or `circes_stew_unsurfaced` (`circes_stew.py:57-58`) |
| emitting code | trigger `circes_stew.py:86-136` (pure); daily pass `circes_stew_job.py`; driven by `backend/jobs/stable_jobs.py:502-551` |
| side | BOTH |
| grid cell | **BEFORE THE TURN**, LONG and SHORT. It fades a fresh 20-day breakout that closed back inside within 1–4 bars, with no trend confirmation |
| incumbent it would replace | none named |
| schedule / trigger | once per trading session after the close: 16:30 ET, retried every 15 min until 20:00 ET (`circes_stew_job.py:45-47`); not a CronTrigger |
| status | **SHADOW since 2026-09-17** (d990abb, deployed 05:50 UTC; `docs/strategy-reviews/2026-09-16-circes-stew-shadow-record.md:5`). Row `status: "SHADOW"` (`circes_stew_job.py:227`) with an inline `l0_shadow` SUPPRESS tag (`:233-237`). **Not in `l0_routing.SUPPRESS_ALWAYS`**: the job suppresses itself and does not route through `process_signal_unified` |
| bucket ceiling | **B3 or TAIL only** (C5; R-IV.823(c)3, R-IV.830(g)). **SHORT: no-fly flag "entering parabolic shorts too early" (mandatory). LONG: no flag** (principal, 2026-10-09) |
| lifetime tries counter | **1**: the unfiltered SPY null case (one parameter set; holds 5/10/20 reported) |

## Rules as coded
- **Trigger: Turtle Soup failed breakout** (`circes_stew.py:13-26`), daily, N = 20 (`:48`):
  - SHORT: breach bar B has `high[B] > max(high of the prior 20 bars)`;
  - the first close back below that level lands on the evaluated bar, 0–3 bars after B
    (`CONFIRM_BARS = 4`, `:49`);
  - B−1 must not itself be a breach that closed outside its level;
  - LONG mirrors this on lows.
  - Only the last bar is evaluated, so a failure fires once.
- **Location gate on the FIRE CLOSE** (R-IV.430(a)):
  - `va_location(trig.close, vah, val)` (`circes_stew_job.py:110`) against the prior session's
    value area;
  - `outside` and `edge` pass (`circes_stew.py:53`); `mid` and unknown do not;
  - edge = the outer 25% of the value area (`:51`), PROVISIONAL until 30 fires.
- **Levels** (`:168-174`): entry at the fire close, stop at the failed extreme, target 2R (`:54`).
- **Ceiling:** 10 a day (`:50`). Over it, none surface.
- **Universe:** tickers PYTHIA covered in the last 5 sessions (`circes_stew_job.py:49`).
  **Bars:** yfinance daily, split- and dividend-adjusted (`PRICE_BASIS`, `:59`). Any return graded under the skill is re-priced on split-adjusted, dividend-unadjusted bars (R-IV.830(a)).

**Two code facts the record should carry:**
1. The scanner's docstring (`circes_stew.py:28-33`) still says the *extreme* is located against
   the value area. The job locates the *close* (`circes_stew_job.py:110`), as R-IV.430(a) ruled.
   The docstring is stale.
2. `va_location` is **direction-blind** (`circes_stew.py:139-150`). A SHORT whose close sits in
   the lower edge band (near VAL) passes the gate as `edge`, the same as one at VAH.

## Rules as approved
Olympus 2026-04-22 §2.1 "Turtle Soup", ADD (PROVISIONAL)
(`docs/strategy-reviews/raschke/olympus-review-2026-04-22.md:157-204`). Its backtest gates
(`:181-188`): Sharpe > 0.8, PF > 1.4, max DD < 15R, ≥ 100 trades, positive in both rotation
regimes, ≥ 60% of winners at the value-area edge.

## Trade side (TA-135, in summary; TA owns this section)
- **Horizon finding.** The shadow record's −0.30R is at a 10-session hold, which **the ceiling
  forbids**:
  - B3 is a one-session trade: CIRCE fires on a close, so entry is the next open.
  - TAIL is convexity held across sessions.
  - The record is evidence neither for nor against either, and C5 leaves no 3–10 session
    expression.
- **Evidence bar, B3:**
  - one-session grading on CIRCE's own fire dates;
  - n ≥ 30 fires AND ≥ 20 distinct dates;
  - market-adjusted headline, long and short reported separately;
  - split by market state; **a range-only result is a CONDITIONAL edge.**
- **Evidence bar, TAIL:** no win-rate bar. Report the distribution and the sleeve spend.
- **TA writes no note at all** if stage 2 fails on vega, or if the result doesn't beat a
  same-date control of all names at a value-area edge.
- CIRCE stays in shadow.

## Evidence so far
- **Null case, SPY only, unfiltered** (no location gate, no regime). 2020-01-02 → 2026-09-16,
  yfinance, split-adjusted, dividends excluded
  (`docs/strategy-reviews/2026-09-16-circes-stew-shadow-record.md:71-81`):

  | hold | trades | win rate | expectancy | PF |
  |---|---|---|---|---|
  | 5 | 226 | 36.3% | −0.24R | 0.73 |
  | **10 (primary)** | 226 | 31.9% | **−0.30R** | 0.69 |
  | 20 | 225 | 32.0% | −0.29R | 0.71 |

  These are in R, not market-adjusted. It is one symbol, and it is the baseline the gated
  strategy must beat, not a verdict on it (`:83-90`). By the horizon finding above, it is
  outside both B3 and TAIL.
- Shadow fires since 2026-09-17: counts come with the census (R-IV.809(f)).

## Kill rule
Per TA-135: if the B3 bar is reached and fails, or stage 2 fails on vega, no note is written and
CIRCE stays in shadow. Retirement is SPINE's and QUERY's (09-23 S2).

## Change log
- 2026-04-22: Olympus ADD (PROVISIONAL). 2026-09-16: built (d990abb). 2026-09-17: SHADOW deployed.
- 2026-10-09: card v0 (R-IV.823(g), R-IV.830(g)).
