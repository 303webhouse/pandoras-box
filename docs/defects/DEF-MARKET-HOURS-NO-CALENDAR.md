# DEF-MARKET-HOURS-NO-CALENDAR — P2

**Registered:** R-IV.419(f). **Verified:** 2026-09-16, CC-BUILD.
**Family:** the grader's holiday defect (`DEF-GRADER-NO-HOLIDAY-CALENDAR`) and
`DEF-STRIKE-WATERMARK-HOLIDAY` — a weekday test standing in for a market calendar.
**Next occurrence: 2026-11-26.**

---

## THE STATEMENT

> **Two "is the market open?" functions test the day of the week, not the market
> calendar — so on every weekday holiday they say YES, and every market-hours feed reads
> DEAD all day.**

## THE TWO FUNCTIONS

`backend/stable_engine/job_status.py`
```python
def is_market_hours(dt_et=None) -> bool:
    dt = dt_et or now_et()
    if dt.weekday() >= 5:
        return False
    mins = dt.hour * 60 + dt.minute
    return 9 * 60 + 30 <= mins <= 16 * 60
```

`backend/jobs/stable_jobs.py`
```python
def is_rth(dt) -> bool:
    """Roughly regular trading hours 09:30-16:00 ET on weekdays (holidays best-effort)."""
    if not is_weekday(dt):          # is_weekday = dt.weekday() < 5
        return False
    ...
```

"Holidays best-effort" — **there is no holiday handling in either.**

## PROVEN BY A DIFFERENTIAL, not by reading

Same instant, three answers:

| at 2026-11-26 12:00 ET (Thanksgiving) | answer |
|---|---|
| `stable_engine.market_calendar.is_trading_day` | **False** |
| `job_status.is_market_hours` | **True** |
| `stable_jobs.is_rth` | **True** |

**Upcoming weekday holidays, per `market_calendar`:** 2026-11-26 · 2026-12-25 · 2027-01-01.

## THE CONSEQUENCE

`job_status.feed_flatline()` exempts market-hours-only feeds **outside** market hours — a
movers feed that stops at the close is expected, not dead. On a holiday `is_market_hours()`
says the market is open, so the exemption does not apply: **a feed that correctly produced
nothing is judged to have died.** The principal's dashboard shows DEAD on every market-hours
feed for the whole session, and the flatline alerting fires on a day when silence is correct.

**This is the opposite failure to a missed outage, and it costs the same thing: a DEAD that is
sometimes false teaches the reader to ignore DEAD.**

## THE FIX — the one calendar

**Both functions consult `stable_engine.market_calendar.is_trading_day(d)`**, and treat its
`None` (outside the calendar's coverage) as the weekday fallback **stated in the result**, not
as a silent guess.

**And there are more copies than these two.** `is_trading_day()` is independently defined in:

```
backend/stable_engine/market_calendar.py   <- the calendar of record
backend/discord_bridge/bot.py
backend/jobs/score_signals.py
backend/scheduler/bias_scheduler.py
```

**A holiday definition held in four places will disagree with itself** the first time one is
updated. The fix routes every "open?" question through `market_calendar` — which is also what
R-IV.419(e) requires of the `/api/stable/*` `session` field: **the same helper as the DEAD check,
so the two cannot disagree.**

## Status: OPEN — registered; the fix lands with the `session` field (R-IV.419(e)).
