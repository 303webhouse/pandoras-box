# DEF-STRIKE-WATERMARK-HOLIDAY · P2

**Found:** 2026-09-02, in the SPEC-01 D7 boundary computation, before the first
boundary was reached.
**Found by:** CC-BUILD, computing the actual span of the first weekend rather
than assuming the brief's.
**Status:** TICKETED, NOT FIXED — brief Gates: *"Defects encountered are
ticketed, not fixed."*
**Does not block:** SPEC-01 is live in dry-run; the alarm cannot fire before
`baseline_sessions >= 3`.

---

## The defect

`strike_ib_converter_loop()` gates on **weekday only**:

```python
in_window = now_et.weekday() < 5 and dtime(9, 30) <= now_et.time() <= dtime(16, 5)
```

Market holidays are not modeled. On any holiday falling Mon–Fri the converter
runs its full RTH window, finds **zero `pythia_events` rows for every ticker**,
and — once the n-gate is cleared — fires
`🚨 STRIKE watermark: {ticker} silent this session` for **all 8 allowlist
tickers at once**.

The feed is not down. The market is closed.

## Traced, not assumed

```
baseline=2 on a holiday -> 'INSUFFICIENT n=2'  alarm fires: False
baseline=3 on a holiday -> 'SILENT'            alarm fires: True
baseline=5 on a holiday -> 'SILENT'            alarm fires: True
```

## The first holiday misses by one session

Labor Day, **Monday 2026-09-07**, is the first market holiday after deploy.

| session | baseline_sessions |
|---|---|
| 2026-09-03 Thu — deploy day, partial | 1 |
| 2026-09-04 Fri | 2 |
| 2026-09-07 Mon — **LABOR DAY, no events** | **2** — no new `last_event_session`, so no increment |

`BASELINE_SESSIONS_GATE = 3`, so on 09-07 the state renders `INSUFFICIENT n=2`
and **no alarm fires**. That is a one-session margin produced by deploy timing,
**not by design**. Thanksgiving and Christmas will both arrive with
`baseline_sessions` far above 3.

Note the second-order effect: a holiday does not increment the baseline either,
because no new session is observed. Holidays therefore delay the gate as well as
threatening a false alarm past it.

## Why P2

This is the **`DEF-NIGHTLY-FLATLINE` class, exactly** — a guard whose
*legitimate* gap it does not model, producing a guaranteed false red on a
schedule. That defect cost this board a wrong finding before it was caught, and
D7 exists in this brief specifically to catch its recurrence.

The failure mode is worse here in one respect: it fires **8 alarms
simultaneously**, which reads like a feed-wide outage rather than a calendar
artifact. Alarm fatigue on a watermark instrument is the thing that makes a real
silent-ticker event get ignored.

## What D7 actually tests now

The brief assumed a normal Sat–Mon boundary. The real first boundary is:

```
last converter cycle : Fri 2026-09-04 16:05 EDT
Labor Day            : Mon 2026-09-07  — market closed
next converter cycle : Tue 2026-09-08 09:30 EDT
DARK WINDOW SPAN     : 89.4 hours (3d 17h)
```

**89.4h, against the ~65.4h the brief imagined** — a stronger no-false-alarm
test, and the D7 result must state this span rather than "one weekend".

**D7 passing on 09-07 does NOT clear this defect.** It passes because the n-gate
has not opened, not because holidays are handled. Stating that explicitly so a
green D7 is not later cited as evidence the holiday case works.

## PRE-REGISTERED EXPECTATION (R-IV.199(a)) — ACCEPT-UNFIXED

Spine ruled ACCEPT-UNFIXED **with the expectation registered before the window**,
which converts this from a defect that will surprise someone into an instrument
whose misbehaviour is characterized.

**Registered before the fact, 2026-09-03:**

- `baseline_sessions` reaches **3** at Friday 2026-09-04 close (sessions 09-03,
  09-04 and the deploy-day partial).
- **Monday 2026-09-07 is a weekday market holiday and is unmodeled.** After
  **11:00 ET** expect **UP TO 8 LATCHED FALSE ALARMS**, one per allowlist ticker.
- **Clear-notify on Tuesday 09-08** as the feed returns.

**D7 therefore adjudicates TWO lines, not one:**

| line | expectation |
|---|---|
| Sat 09-05 / Sun 09-06 | **ZERO** alarms — the weekday gate holds |
| Mon 09-07 | **count the pre-registered set** — up to 8, latched, after 11:00 ET |

A weekend pass alone is not a D7 pass, and a Monday alarm is not a D7 failure.
**A false alarm predicted to the hour is an instrument characterized, not an
instrument trusted** — the fix below is still owed.

*[Added by CC-BUILD beyond the letter of R-IV.199(b)/(c), so the D7 read has the
expectation on the artifact rather than only in a relay. Revert if the
registration was meant to live only in the ruling.]*

## Fix, when commissioned

A holiday calendar for the converter's RTH window, or an alarm suppressor keyed
on "zero `pythia_events` across **all** allowlist tickers" — market-wide silence
is a calendar signal, not eight independent feed failures. The second is cheaper
and needs no calendar maintenance, and it is strictly better as an instrument:
it distinguishes *market closed* from *this ticker's alert died*, which is the
distinction the watermark exists to make.

Not chosen here. Registration does not wait on the fix.
