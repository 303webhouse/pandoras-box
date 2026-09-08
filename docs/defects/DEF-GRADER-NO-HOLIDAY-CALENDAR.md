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

---

## THE RULE CONTAMINATES THE TESTS THAT WOULD HAVE CAUGHT IT (R-IV.320(a))

**Measured 2026-09-08, when the calendar replaced the weekday rule in T7's three ruled
consumers. Three existing tests failed, and ALL THREE WERE WRONG THE SAME WAY.**

| test | asserted | correct |
|---|---|---|
| `test_next_weekday_skips_the_weekend` | Fri 09-04 → **Mon 09-07** | Tue **09-08** |
| `test_expiry_friday_rolls_to_wednesday` | +3 sessions = **09-09** | **09-10** |
| `test_friday_pass_is_overdue_by_monday_evening` (CC-BUILD's) | overdue by **Mon 09-07** evening | Tuesday |

**Every one used `2026-09-04 -> 2026-09-07` as its Friday-to-Monday example, and 2026-09-07 is LABOR DAY.**

**Written at different times, by different hands, into different subsystems** — the
converter tests with SPEC-01, the sentinel test two days ago — and each independently
picked the nearest weekend and baked the holiday in.

**The third is the sharpest.** It was written by CC-BUILD **on 2026-09-06, inside the
liveness sentinel built to remove false reds**, and it **asserted the holiday false red as
correct behaviour.** The author was actively working on this defect's family at the time.

### Why this is the defect's most important property

**A computed weekday rule does not merely produce wrong answers — it produces a wrong
EXPECTATION, and the expectation is what the test encodes.** A test author asks "what
should Friday plus one be?", applies the same mental rule the code applies, gets Monday, and
writes it down. **The test then passes forever and proves the code matches the rule rather
than the market.**

**This is why the fix is data and not logic.** An explicit list can be read against a
published schedule by someone who has never seen the code. A rule can only be checked by
someone who already knows the answer — and if they knew it, the bug would not exist.

**All three were corrected to trading-day values with the reasoning on their faces, not
relaxed.** Four new tests assert Labor Day and Good Friday specifically, so the next
regression fails on a named day rather than on an arithmetic drift.
