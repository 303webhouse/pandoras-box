# DEF-STRIKE-SESSION-COUNTS-INFLATED · P2

**Found:** 2026-09-03, SPEC-01 D1 step-4 dry-run, by checking a counter against the
source table instead of reading it.
**Status:** TICKETED, NOT FIXED (brief Gates).

---

## The defect

`strike_ib_session_counts`.`ib_events` **counts cycles-in-window, not events.** The bump runs once per
returned row per cycle:

    for rec in events:
        await _session_counts_bump(conn, ev["ticker"], session_date, "ib_events")

and the read looks back **two hours** on a **five-minute** cadence. An event therefore
lands in up to **2h / 5min = 24** consecutive result sets and is counted every time.

## Measured, 2026-09-03

    strike_ib_session_counts   IWM  ib_events = 24   signals_emitted = 0   rejects = 0
    pythia_events              IWM  actual IB breaks today = 1
                                    one ib_break_down at 14:31:40.155Z

**A 24x overcount of a single event**, and the 24 is exactly the number of cycles the
two-hour window holds.

## Why P2 rather than cosmetic: it is not a scale factor

The multiplier is **the number of cycles an event survives in the window**, so it
depends on **when in the session the event fires**:

| fire time (ET) | cycles before the 16:05 close | counted |
|---|---|---|
| 10:31 | 24, the full window | 24x |
| 15:00 | about 13 | 13x |
| 15:55 | about 2 | 2x |

**An event late in the session is counted fewer times than an identical event early.**
That is not a uniform inflation that divides out — it is a **time-of-day-dependent
multiplier** that manufactures a spurious intraday gradient.

**This is the table the addendum designates as the substrate for any future daily-rate
band**, and the one its DELETION LAW protects precisely so a decay instrument can be
derived from it later. A band derived from these counts would inherit a pattern created
entirely by the counter, and it would look like a real intraday effect.

## Scope — which columns are affected

| column | affected | why |
|---|---|---|
| `ib_events` | **YES** | bumped per row per cycle |
| `rejects` | **YES, same mechanism** | a rejecting event re-rejects every cycle |
| `signals_emitted` | no | bumped only on a true insert, which dedup makes once |
| `pythia_events` | no | bumped with n=0, a touch rather than a count |

**`rejects` inflates identically** and was invisible today only because today's single
event passed validation. A day with one malformed event would report dozens of rejects.

## Second-order: dry-run does not dedup its logging

`if dry: continue` returns before `emitted_ids` is populated, so the same event re-logs a `STRIKE DRY-RUN would emit:` line
every cycle. Today's single event produced up to 24 such lines and rotated the 500-line
log buffer, which is why the dry-run lines were **not readable** by the time the session
was reviewed. **The evidence D1 step 4 asks for was destroyed by the volume of its own
logging.**

## Fix, when commissioned — not chosen here

Count distinct events, not rows-seen. The event id is already selected and already
carried into metadata as `pythia_event_id`. Either track seen ids per session, or bump only for
rows whose `pythia_event_id` exceeds a per-session high-water mark. **Do not fix by narrowing the
lookback window** — that trades an overcount for a miss, and the two-hour window is what
absorbs restarts.

**Historical counts already written are inflated and must not be treated as a
baseline.** Today's IWM row is the only data so far: one real event, recorded as 24.
