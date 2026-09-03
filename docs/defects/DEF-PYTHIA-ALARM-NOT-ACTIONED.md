# DEF-PYTHIA-ALARM-NOT-ACTIONED · P1

**Found:** 2026-09-03, during the R-IV.228 webhook-loss diagnosis, by checking whether
the existing watchdog had fired before concluding one was needed.
**Status:** TICKETED. **The detection half needs no fix.**

---

## The defect is not detection. It is what happens after detection.

`pythia_staleness_watchdog_loop` has been firing correctly for approximately five weeks. Live evidence, read
from Redis this session:

```
alarm:pythia_stale:  AAPL AVGO FXI GOOGL HYG INTU ISRG META
                     MSFT NVDA QQQ SMH TLT TSLA XLK ZS     = 16 latches
```

Sixteen latches, matching the sixteen dead liquid-20 tickers exactly. With `LATCH_TTL` at
7200s each re-arms about every two hours of RTH — roughly **1,200 alarm deliveries** over
the period. **The feed still lost 206 of 212 tickers.**

Every component worked: the roster was correct, the session-aware threshold avoided the
weekend false-positive it was built to avoid, the latch prevented per-cycle spam, the
alarms were delivered. **The condition persisted anyway.**

## Why P1

An alarm that fires and produces no action is **worse than no alarm**, because it
consumes the attention budget that a real alarm needs and it creates a false belief that
the condition is monitored. The board has spent this week building instruments on the
premise that detection is the hard part. **This is the counter-example: detection was
solved, and the outcome was identical to having no detector at all.**

## The compounding instance, which CC-BUILD owns

SPEC-01 shipped a **second** per-ticker liveness instrument for the same condition,
without this lane ever checking whether the first was already alarming. Had it checked,
five dark tickers would have been known before the allowlist was authored.

**A new detector for an already-alarming condition is not redundancy — it is a second
alarm nobody will act on**, and it cost a build slot that could have gone to the
response path.

## Fix, when commissioned — not chosen here, and the shape matters

The fix is **not** another detector, and not a louder one. Candidates, all in the
response half:

1. **Escalation on persistence.** A latch that re-arms N times without the condition
   clearing is a different event from a first alarm, and should not look the same.
2. **Aggregate over per-ticker.** Sixteen simultaneous per-ticker alarms read as noise;
   *"16 of 20 roster tickers dark"* reads as an outage. The aggregate is the actionable
   object and it does not currently exist.
3. **A standing precondition check.** Any brief whose preconditions include feed liveness
   tests it **at build time** against the existing watchdog state, rather than assuming
   it and discovering otherwise in a dry-run.

Item 3 is the one that would have caught SPEC-01, and it is cheap: read the latch set
before writing an allowlist.
