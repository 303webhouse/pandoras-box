# DEF-RTH-GATE-IGNORES-CALENDAR

**Filed:** 2026-09-23 (R-IV.488(f)) · **For:** the R-IV.482(j) DEF list
**Severity:** low — a mislabelled dot and a pointless run, not a wrong number
**Due:** before Thanksgiving, **2026-11-26**

## What is wrong

`is_rth()` (`backend/jobs/stable_jobs.py:73`) and `is_market_hours()`
(`backend/stable_engine/job_status.py:49`) both decide "is the market open" with a
weekday test plus a clock window. Neither consults
`backend/stable_engine/market_calendar.py`, which sits in the same package and
exists precisely to answer this from an explicit, auditable holiday list.

So on a weekday market holiday both return **True**.

## What that does, measured

Measured 2026-09-23 with the deployed code:

| date | `is_trading_day` | `is_rth` | `session_pair` |
|---|---|---|---|
| Thanksgiving 2026-11-26 (Thu) | False | **True** | `(11-25, 11-24)` |
| Christmas 2026-12-25 (Fri) | False | **True** | `(12-24, 12-23)` |

Consequences, in order of how much they matter:

1. `stable_strip_loop` runs every 10 minutes all day on a closed market. Wasted
   vendor calls, nothing more.
2. `is_market_hours()` returning True means the health dot resolves to an *open*
   state rather than `closed`, so the tile reads as a live session on a day the
   market never opened.

## What it does NOT do

**It does not produce a wrong number.** `session_pair` routes through
`market_calendar.is_trading_day`, so on a holiday it correctly resolves to the
last completed session and the strip shows that session's change — which is the
right thing to show when the market is shut. This was initially reported (and
retracted, R-IV.488(b)) as "serves a prior session's change as live, all day,
green"; the first half is true and correct behaviour, only the label is wrong.

## Fix

Route both gates through the calendar:

```python
# stable_jobs.is_rth / job_status.is_market_hours
from stable_engine.market_calendar import is_trading_day_or_none
open_today = is_trading_day_or_none(dt.date())
if open_today is not True:      # None (past horizon) is not True, and must not be
    return False
```

`is_trading_day_or_none` is the non-raising form, which is what a health read and a
background loop need. **None must not be collapsed to True** — past the calendar
horizon the honest answer is "cannot confirm", and the loop should stand down
rather than assume a session.

Size: two call sites, one import each; a test per gate over the two dates above.

## Related

- `market_calendar.py` — the module these should have used; its own docstring
  argues the case (a rule-based calendar "reports the market OPEN on Juneteenth
  and Good Friday, every year, silently").
- R-IV.487 — the 09-22 wrong-number defect; this is adjacent but distinct, and was
  explicitly found NOT to be its cause.
