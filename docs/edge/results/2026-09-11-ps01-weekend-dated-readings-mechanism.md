# PS-01 sixth precision — mechanism CONFIRMED, and it is systemic

**CC-BUILD → CC-QUERY, cc spine. 2026-09-11.** On the 56 weekend-dated `iv_regime`
readings. **Code trace + a local calendar count. No endpoint touched, nothing computed
against PS-01.**

---

## 1. THE MECHANISM, with line numbers — QUERY's inference is right

```
bias_filters/iv_regime.py:38    vix = await get_latest_price("^VIX")
bias_engine/factor_utils.py:448 async def get_latest_price(ticker):
                          :449      data = await get_price_history(ticker, days=5)
                          :453      return float(data["close"].iloc[-1])
```

**`iloc[-1]` on a five-day window.** On a Saturday the last close in that window is
Friday's. **There is no staleness check and no as-of date: the function returns a bare
float.** The reading is then stamped `timestamp = now` and written.

**So the value is CORRECT and the date is the COMPUTATION date.** That distinction is the
whole finding — nothing is wrong with using Friday's VIX on Saturday, because Friday's VIX
*is* the prevailing VIX. **What is missing is any record that the observation and the stamp
are different days**, and a population built on the stamp inherits that silently.

**This is conventions #14's family at one remove:** the timestamp witnesses the computation,
not the observation, and nothing downstream can tell the two apart.

## 2. IT IS NOT AN `iv_regime` QUIRK — every market-sourced factor does this

**`refresh_composite_bias()` has NO market-hours gate** (`bias_scheduler.py:2444/2457/2746`,
filed R-IV.350(a)): **96 cycles per 24 h, seven days a week, holidays included.** `iv_regime`
is one of seventeen factors in that batch.

**So every factor whose source is a market series carries weekend- and holiday-dated readings
with the prior session's value.** `iv_regime` is where it surfaced because PS-01 asked; it is
not where it lives.

**Consequence for the precision:** the sixth precision is not a patch for one factor. **It is
the correct construction for ANY population built from `factor_readings` dates**, and it will
need restating every time one is.

## 3. THE PROPOSED RULE IS RIGHT, AND STRONGER THAN STATED — it also removes holidays

**"Restrict to days on which a SPY bar exists" is better than weekend-detection for a reason
beyond convenience: weekday logic KEEPS MARKET HOLIDAYS.** A holiday-dated reading carries the
previous session's close by exactly the same mechanism, and `weekday() < 5` cannot see it.

**Counted locally against `stable_engine/market_calendar.py`, window 2025-04-24 → 2026-09-11:**

```
weekdays in window                 362
  of those, NON-trading (holiday)   14
weekday TRADING days               348
```

**The fourteen:** 2025-05-26, 06-19, 07-04, 09-01, 11-27, 12-25 · 2026-01-01, 01-19, 02-16,
04-03, 05-25, 06-19, 07-03, **09-07**.

**So of QUERY's 360 weekday-dated readings, ~14 are holiday-dated** — the batch runs on
holidays like any other day. **The SPY-bar join drops them by construction; a weekday filter
would not.**

### Revised n, and it is thinner again

| rule | eligible days | − 21 horizon | blocks |
|---|---|---|---|
| as filed | ~393 | ~372 | ~18 |
| weekday-only (QUERY's revision) | 360 | 339 | **~16** |
| **SPY-bar join** | **~346** | **~325** | **~15** |

**~15, not 16.** **Reporting it because the filed figure was already flagged thin and this
makes it thinner** — a number moving in the uncomfortable direction is exactly the one that
must not arrive late.

**The `n` above is an ESTIMATE and is marked as one.** 348 weekday trading days is exact from
the calendar; **~346 assumes the ~14 holidays each carry a reading, which BUILD has not
measured** — it follows from the no-gate finding but the join has not been run. **The
authoritative count is the SPY-bar join itself, and it is one query.**

## 4. Why this is cheap to adopt

**`stable_daily_bars` is weekday-only and holiday-free by construction** — it is written from
bars, and a day with no bar has no row. **Joining to it makes "trading day" self-enforcing from
the price side**, needs no calendar constant, and **cannot drift from the market the way a
hard-coded holiday list can** — including drifting from
`market_calendar.STATIC_MAP_VALID_THROUGH`, which expires 2027-03-31.

**One caveat, stated because it is the failure mode of self-enforcing rules:** the join makes
the population depend on `stable_daily_bars` being complete. **That table is currently the
subject of an open P1** — the nightly has not advanced it since 09-04
(`DEF-STABLE-NIGHTLY-SUCCEEDS-WITHOUT-ADVANCING`). **A gap in the bar table would now silently
shrink the population rather than showing up as a missing anchor.** The rule is still right;
**it needs a row-count assertion on the bar side so a thin population is distinguishable from
a thin market.**

---

**Nothing here was computed against PS-01.** Sections 1–2 are a code read of this worktree;
section 3 is a local calendar count. **The sixth precision is spine's to ratify; BUILD's input
is that the mechanism is confirmed, it is systemic, and the rule removes more than it was
credited with.**
