# DEF-GRADER-NO-HOLIDAY-CALENDAR · P3

**Registered:** 2026-09-04 (R-IV.252(c)). **Status:** OPEN, folded into the P1/P2
precondition build as ONE market-calendar utility retiring the whole family.

---

## The defect

**Three independent instruments each approximate the trading calendar with weekday
arithmetic, and none of them models holidays.** Each was written correctly in
isolation; the defect is that there are three of them and no calendar.

| site | approximation | consequence |
|---|---|---|
| `services/read_only/market_profile.py` session helpers | weekday-only session dates | a holiday reads as a normal session |
| `jobs/strike_ib_converter.py` | `weekday() < 5 and 09:30-16:05` weekday gate | runs its full window on a market holiday |
| `main.py:914-931` grader loop | weekday + after-16:15 gate | attempts a pass on a holiday with no bars to grade |

## Why it is a family and not three tickets

The same missing abstraction produces different failures at each site:

- `DEF-STRIKE-WATERMARK-HOLIDAY` — the STRIKE watermark alarm fires on a weekday holiday because
  zero events looks like a dead feed. Pre-registered for 2026-09-07 (Labor Day).
- The grader burns a pass, and its unbounded `lookback_days` grows by another day.
- Session-date arithmetic labels the holiday as the current session, so anything
  keyed on "today's session" compares against a session that never happened.

**One utility fixes all three. Three separate fixes would leave the fourth consumer
to rediscover it**, which is what happened here — the weekday approximation was
copied forward each time precisely because it was correct enough to pass review.

## Fix, when built — shape, not chosen here

A single market-calendar module the three consumers call, exposing at minimum: is this
date a trading session, what is the previous/next session, and how many sessions lie
between two dates. **Holidays are data, not logic** — a hardcoded list is acceptable
and honest where a computed rule is not, provided it carries an explicit horizon and a
loud failure past that horizon rather than silently treating an unknown year as
all-weekdays-are-sessions.

**Note the interaction with `DEF-STRIKE-WATERMARK-NEVER-ALIVE`'s n-gate:** raising or lowering that gate changes which
tickers can alarm on a holiday. Fix the calendar first, or the holiday defect's blast
radius changes underneath the fix.
