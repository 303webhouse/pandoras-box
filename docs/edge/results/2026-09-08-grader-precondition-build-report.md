# BUILD REPORT — GRADER PRECONDITION (R-IV.289(d))

**FROM:** CC-BUILD · **TO:** spine · **cc:** EDGE, OLYMPUS-TRITON
**Brief:** `docs/codex-briefs/2026-09-04-grader-precondition-brief.md`, actionable at `1a8260d6`
**Status:** OPEN — D7 recorded below; the five deploy-dependent observations fill after the
Tue 2026-09-08 post-close push.

**The report contract requires six items. Each is written as an OBSERVATION, never as an
assertion that work happened**, because each names something that could have been skipped
and reported as done.

| # | observation | state |
|---|---|---|
| 1 | poll sequences per deploy | PENDING — post-push |
| 2 | deafness test: what was withheld, what fired, latch cleared **and the clearing verified** | PENDING — post-deploy |
| 3 | seal count before AND after each of A/B/C (six numbers) | PENDING — T5b |
| 4 | Phase B's expected count **stated before it ran**, and met | PENDING — T5b |
| 5 | post-condition grep, re-run | PENDING — after the last `backend/` commit |
| 6 | `/info` issue-type vocabulary as returned live, **before the classifier was written** | **DONE — recorded on the brief's face 2026-09-07** |

---

## D7 — the pre-registered IWM read (R-IV.318(c))

**Registered expectation:** at 11:00 ET on Monday 2026-09-07, **exactly 1 alarm (IWM);
zero = failure.** Settled by clock either way.

### What this lane can and cannot state

**THIS LANE DID NOT TAKE THE 11:00 ET MONDAY SAMPLE.** No read was performed at that
instant, and the process log buffer (500 lines) does not reach back to it. **The reading
below is a LIVE read taken 2026-09-08 14:40 ET**, on the first real session after the
holiday. Stated first so nothing here is mistaken for the registered sample.

**Monday 2026-09-07 was Labor Day** — a market holiday that is also a weekday. The
converter's gate is `et.weekday() < 5`, so **it ran, found no events because the market was
shut, and counted the day as a session with no arrivals.** That is
`DEF-STRIKE-WATERMARK-HOLIDAY` precisely, and it means the registered read landed on a day
whose expected event rate was **zero by construction**.

### The live read, 2026-09-08 14:40 ET

```
gate_sessions 3   session_date 2026-09-08

IWM   SILENT
DIA   INSUFFICIENT n=1      QQQ   INSUFFICIENT n=1
SMH   INSUFFICIENT n=1      TLT   INSUFFICIENT n=1
XLE   INSUFFICIENT n=1      XLF   INSUFFICIENT n=1
XLK   INSUFFICIENT n=1
```

**Alarm count: 1. Alarming ticker: IWM.** On its face, the registered expectation is met.

### But the predicate does not discriminate, and that is the finding

**Seven of the eight tickers sit at `n=1`, below the 3-session baseline gate, so they are
STRUCTURALLY INCAPABLE OF ALARMING.** Running the registered predicate against two worlds:

```
WORLD A — only IWM silent, seven feeds ALIVE    alarms = 1   ['IWM']
WORLD B — ALL EIGHT FEEDS DEAD                  alarms = 1   ['IWM']
```

**"Exactly 1 alarm (IWM)" returns 1 in both.** It cannot distinguish the expected world
from total failure. **D7's own acceptance predicate is a null verifier** — the law this
build exists to enforce, found in the acceptance test of the build enforcing it. That is the
second time in this brief: T3's literal form was the first.

### What WOULD discriminate, and what it says

**The count of tickers reading `OK`**, not the count alarming. `OK` requires
`baseline_sessions >= 3` AND `seen_this_session` — it cannot be reached by a dead feed or by
a gated one.

**Measured now: ZERO tickers read `OK`.** Not one of the eight is confirmed alive. The seven
non-alarming tickers are non-alarming **because they are below the gate, not because they
are healthy**, and the registered predicate counts them as if the distinction did not exist.

### Verdict, stated in the honest form

**NOT SETTLED BY THIS READ.** The registered sample was not taken; the day it was registered
for had a zero expected event rate; and the predicate it would have been scored against
cannot separate success from total failure. **Recording "1 alarm, as expected" would be true
and would mean nothing.**

**Recommended replacement, for spine:** score on `OK` count against a stated expectation,
on a day with a non-zero expected event rate. Until `n >= 3` exists for more than one
ticker, **no alarm-count predicate on this surface can be informative** — which is the
`DEF-STRIKE-WATERMARK-NEVER-ALIVE` n-gate interaction already registered, arriving as an
acceptance-test problem rather than a monitoring one.
