# Zweig indicators: DISPLAY-ONLY regime context (R-IV.877(b), Task 9)

**Status:** display only. **Not a signal, a filter or a gate**: nothing in the hub reads these
to decide anything. Dated 2026-10-12.
**Code:** `backend/stable_engine/zweig.py` (rules, backfill, nightly update), table `stable_zweig`,
route `GET /api/stable/zweig` (not on any screen; a display needs the principal's approval).
Nightly at 22:30 ET (`bias_scheduler`, job `zweig`).

## 1 · Breadth Thrust
**Published definition** (Martin Zweig, *Winning on Wall Street*, 1986, as summarised by the sources
below):
- ratio = advancing / (advancing + declining) issues, daily;
- the 10-day exponential moving average of the ratio;
- a **thrust** is that EMA rising from **below 0.40** to **above 0.615** within **10 trading days**.

Sources:
- [McClellan Financial, "A Breadth Thrust Signal"](https://www.mcoscillator.com/learning_center/weekly_chart/a_breadth_thrust_signal/)
- [thetrading.tools, Zweig Breadth Thrust](https://www.thetrading.tools/concepts/zweig-breadth-thrust)
- [babypips, Zweig Breadth Thrust](https://www.babypips.com/forexpedia/zweig-breadth-thrust)

Zweig counted 14 thrusts since 1945. Sources also note there is no single official version:
exchange, universe and smoothing vary.

**Implementation.** EMA with α = 2/11; a thrust fires on the first session the EMA exceeds 0.615
within 10 sessions of its last reading below 0.40; one thrust per arming.

**INPUT: SUBSTITUTE.** Zweig used NYSE issues.
- **No free source of NYSE advance/decline counts exists:** Yahoo serves none (^ADVN, ^DECLN,
  ^ADV, ^DECL, ^NYAD all empty, measured 2026-10-12); the free Unicorn archive stopped in 2020;
  the rest are paid feeds.
- The ratio here is the **advancing share of the Stable Engine universe**
  (`backend/stable_engine/data/universe.csv`, 690 names, a median of 547 counted per day).
  - The backfill counts it from yfinance daily closes; the nightly update counts it from
    `stable_daily_bars`.
  - The universe is **today's names** (survivorship-biased) and **theme-weighted toward
    technology**.
- **The thresholds were calibrated on NYSE breadth and are applied unchanged. A thrust on the
  substitute is NOT a Zweig thrust**, and the payload says so.
- **Measured:** the substitute fires **36 thrusts from 2006 to 2026**, about two a year, against
  Zweig's 14 in 81 years. The substitute is far noisier than NYSE breadth. A real NYSE A/D feed
  (paid) would be needed for the indicator to mean what Zweig meant.

## 2 · Four Percent Model
**Published definition** (Zweig, *Winning on Wall Street*, 1986):
- weekly closes of the Value Line Composite;
- **BUY** when the index rises **4%** or more from a weekly low;
- **SELL** when it falls **4%** or more from a weekly high.

Sources:
- [CXO Advisory, Martin Zweig's Four Percent Model](https://www.cxoadvisory.com/technical-trading/martin-zweigs-four-percent-model-indicator/)
- [Stocks & Commodities, "The 4% Indicator Revisited"](https://store.traders.com/stcov2814inr.html)

CXO's independent tests are sceptical of its net value, and note the 4% threshold may be fitted
to the original data.

**Implementation.**
- The weekly close is the last session of each calendar week.
- After a BUY, track the highest weekly close since; after a SELL, the lowest since.
- Before the first signal the state is UNKNOWN; no position is assumed.

**INPUT: SUBSTITUTE.** Zweig used the Value Line Composite (geometric).
- Yahoo serves no history for it (^VALUG: one row, measured 2026-10-12).
- The **Value Line Arithmetic index (^VALUA, from 2006)** is used.
- The arithmetic index drifts above the geometric one, and CXO Advisory flags that the two can
  signal differently.
- **Measured:** 139 signals, 2006–2026.

## 3 · What the payload carries
`GET /api/stable/zweig?days=N`:
- `display_only: true`;
- `sources`, with both substitutes named;
- `latest`, `series` (adv_share, EMA, thrust state, the Value Line weekly close, the 4% state and
  signal);
- `recent_thrusts`.

## Change log
- 2026-10-12: v0 (R-IV.877(b)).
