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

### STATUS, 2026-09-10 — D3 PASSES; THE BATCH IS PARTIAL

**D3: PASS.** Last deploy Tue 2026-09-08 16:02 ET; **Wednesday and Thursday both
deploy-free**; the grader ran Thu 16:39 ET, `status: ok`, 4.3 s, `timeouts {count: 0}`, sentinel registered and
ok. **A scheduled pass ran with no deploy in the window** — on the second consecutive
deploy-free day. Recorded in full at `docs/edge/results/2026-09-10-d3-aegis-and-regime-n1.md`.

**`DEF-TRITON-GRADER-DARK` closes on this evidence (R-IV.343(c)).**

**D-FINAL STAYS OPEN** until observations 2–4 are recorded (R-IV.343(c)).

#### Thursday's push is PARTIAL, and these are the six items NOT in it

```
BUILT and pushed 2026-09-10
  secret len/present on the PYTHIA rejection line
  gex -> None on both no-data branches

NOT BUILT — named, not implied
  1. grader yfinance fallback
  2. provider column + migration
  3. provider backfill under seal (A/B/C, count at deploy)
  4. fallback-rate alarm / circuit breaker
  5. Path A display fallback
  6. SPY -> allowlist
```

#### VERIFICATION STATE — three states, R-IV.344(c)

**A fix is not closed until its exercising event is observed.** DEPLOYED says the code is
running. EXERCISED says the changed branch was entered in production. **They are different
claims and this column will no longer let them share a cell.**

| fix | state | the exercising event | expected rate |
|---|---|---|---|
| `gex` returns `None` instead of a neutral reading | **NOT-EXERCISED** | a factor cycle where UW GEX is unavailable or stale | ~5% of readings (35 of 695 measured) |
| rejection line carries `secret_len` / `present` | **NOT-EXERCISED** | the next rejected PYTHIA webhook | 3 rejections observed 09-09; rate unestablished |

**Both DEPLOYED 2026-09-10 22:58Z, both NOT-EXERCISED as of this filing.**

**The rates matter and are stated deliberately.** At ~5% of readings, `gex` should exercise
within hours and **its continued non-exercising becomes evidence in its own right** — either
the branch is unreachable or the measured 5% was not a rate. **The webhook figure is NOT a
rate**: three rejections on one day establishes that rejections happen, not how often, and
**an absence dates nothing until the expected event rate across it is known.** So the webhook
line cannot yet convict a silence, and says so rather than implying a schedule.

#### Observations 2, 3 and 4 were NOT RUN on Wednesday

**Not "unrecorded" — NOT RUN.**

| # | observation | state |
|---|---|---|
| 2 | deafness test | **NOT RUN** — Friday morning, controlled write, no deploy |
| 3 | six seal counts across A/B/C | **NOT RUN** — Friday morning with T5b |
| 4 | Phase B's expected count, declared first | **NOT RUN** — with (3) |

**Wednesday's frozen day went to five read-only items** — the 401 read, two corrections,
conventions #14, the DEF corrections and two registrations, and the liveness check. **Those
produced findings and they consumed the day.** The slip was visible on Wednesday and **this
lane did not flag it until spine asked for the deploy.** See the process entry, conventions.



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

---

## PYTHIA v2.5 — FEED RESTORATION WATCH (R-IV.322)

**Deployed by the principal ~15:20 ET 2026-09-08.** Dedicated v2.5 alerts live for
**SPY · QQQ · IWM · SMH**; the old v2.4 alerts for those four are being retired to prevent
duplicate deliveries.

**Owed in tomorrow's report:** first v2.5 event per ticker with its timestamp · any
duplicates seen before the old alerts stopped · watermark baseline starts. The MP-untrusted
rule (R-IV.255(c)) lifts per ticker on its first v2.5 event; SPEC-01 rate re-derivation
(R-IV.233(c)) begins accumulating. **The secret stays on the register.**

### FLAGGED PRE-CLOCK — the restored set IS H-CORE4, exactly

```
H-CORE4      IWM · QQQ · SMH · SPY
v2.5 tickers IWM · QQQ · SMH · SPY      identical
```

**The window's named hypothesis stratum is precisely the set whose feed is restored first.**

**The consequence is a selection effect on the registration, not on the feed.** If the
window clock starts while only these four carry a live v2.5 feed, then any **H-CORE4 versus
rest** comparison is confounded by **feed availability** rather than by market behaviour —
the stratum would look different because it is the only one being measured properly.

**Raised now because the clock has not started.** The precondition order is Amendment 1
filed → P1/P2 verify → clock, so this is still a pre-clock fact and can be declared on the
registration face. **After the clock it would be an excuse.** This lane does not edit the
registration unbidden; the observation is spine's to place.

### And the converter's eight split three ways

```
on v2.5   QQQ · IWM · SMH          (3 of 8)
on v2.4   DIA · TLT · XLE · XLF · XLK   (5 of 8)
v2.5 but NOT in the converter allowlist   SPY
```

**This bears directly on D7's replacement predicate.** The rewritten form scores the `OK`
count against a stated **k of 8** — and three of those eight are about to start a fresh
baseline on a new feed while five stay on the old one. **k must be declared knowing the
split, or it silently measures the restoration rather than the feeds.**

### k DECLARED — R-IV.323(b)

**k = 3 of 8 for the first read: QQQ · IWM · SMH** — the allowlist tickers on the restored
feed. **Rising as dedicated alerts are added** (DIA XLK XLF XLE TLT on the principal's next
TradingView round).

**Declared BEFORE the read, which is the whole point of the rewrite.** The old form scored
an alarm count that returned 1 whether one feed was silent or all eight were dead. **This
one names which three can reach `OK` and why**, so a shortfall identifies a ticker instead
of producing a number.

**SPY-to-allowlist:** R-IV.109(e) is now satisfied — SPY has a dedicated v2.5 alert. **It
rides Thursday's post-D3 batch with the Path A display fallback, not tonight's push.**

---

## DEPLOY + FIRST PASS — 2026-09-08 (observation 1, and part of 2)

**Push 16:02 ET, `39a20e9..bdb790a`, 21 commits, ONE deploy carrying the code AND the un-pause
flags** — flags set beforehand with `--skip-deploys`.

### Observation 1 — poll sequence, deployment `c38df2d9`

```
polls 1-11   BUILDING
poll 12      DEPLOYING
poll 13      UNREADABLE     <- predicate HELD; not treated as terminal
poll 14      SUCCESS
```

**Readiness gate:** `healthy` on two consecutive samples — **not `degraded`**. The
`stable_jobs` provisional flatline and the `signals_freshness` flatline both cleared on the live session, exactly as
`DEF-STABLE-PROVISIONAL-WEEKEND-FLATLINE` said they would, unaided.

**Boot integrity:** startup complete, no traceback, no `ImportError`, and **no
`job_runs table creation skipped` warning** — migration 028's DDL mirror executed.

### Un-pause, confirmed the same three ways as the pause

```
/health.paused_pollers   {"darkpool": false, "tide": false}
[poller_pause] tide poller RUNNING (PAUSE_TIDE_POLLER=false)
[poller_pause] darkpool poller RUNNING (PAUSE_DARKPOOL_POLLER=false)
```

### THE FIRST PASS — and it separates the two defects on its own

```
session_date  2026-09-08
started       20:38:46.091487+00     finished  20:38:57.278960+00     (11 s)
status        ok
rows_touched  0
skip_reason   no_regular_session_bars=650
timeouts      {"count": 0, "last_session": null}
sentinel      {"status": "ok", "last_persist_age_s": 33, "registered": true}
```

**Every task is exercised by that single row.**

**T1** — 11 s against a 300 s bound, and `timeouts.count` reads **0**. Not absent: **zero**. The
metric distinguishes *did not fire* from *not instrumented*, which was its whole
justification.

**T2** — a durable row exists, so *did it run?* is now a `SELECT`. **It started 16:38 ET,
not 16:15, and that is CORRECT rather than late:** the loop takes a 180 s boot delay then
checks every 30 minutes, so the ~16:08 check fell before the 16:15 gate and skipped, and the
16:38 check passed it. **Under the old in-memory flag that interaction was invisible.**

**T3** — the sentinel reads `registered: true`, `status: ok`, `last_persist_age_s: 33`. **The pluggable age source worked
on live data**: 33 seconds, read from `job_runs`, for a job that writes no `signals` row. The
class that would have carried `age = None` forever carries a real age on its first day.

**T4 — and this is the night's finding.** `no_regular_session_bars=650`

### The grader is FIXED and grading NOTHING, and those are now separately visible

**650 of 650 rows skipped, 0 graded, because the bar fetch returned nothing.** The grader is
on **Path A** (`get_ohlc`, no fallback) and `DEF-UW-OHLC-DEAD` is still live — **64 fallback log
lines on this boot** on the Path B side confirm the endpoint is still serving nothing.

```
WARNING triton_grader: no 'r' bars for ARM  -- skip 1
WARNING triton_grader: no 'r' bars for ADBE -- skip 1
INFO    triton_grader: touched=0 fully_graded=0 skipped=650
        reasons={'no_regular_session_bars': 650}
```

**Before T4, this pass would have reported "0 graded, 650 skipped" with no reason —
indistinguishable from "there was nothing to grade."**

**It is the cleanest possible vindication of not merging the two defects** (R-IV.288(b),
R-IV.310). **The loop defect is FIXED:** the pass ran on schedule, bounded, durably
recorded, and the sentinel reads it alive. **The vendor defect is UNFIXED:** it graded
nothing. **Merged, tonight would have looked like a failed build instead of a working build
reporting a separate outage.**

**Liveness is not correctness, and the sentinel says so correctly:** `status: ok` on a pass that
graded zero rows. **A pass that ran and skipped for a stated reason counts as ran**
(R-IV.295(a)) — a rule written before there was a case, now with one.

### Still owed

**Observation 2 — the deafness test.** It requires provoking the sentinel, which means
writing an alarm condition into a live system. **Proposed for Wednesday: it needs NO
DEPLOY**, so it does not disturb D3's frozen day. TEST-labelled, audit-logged, latch cleared
**and the clearing verified**.

**Observations 3 and 4 — T5b's A/B/C**, six seal counts, Phase B's expected count declared
before it runs. Against prod after this deploy, as ruled.

### Schedule of record, R-IV.324

| when | what | deploy? |
|---|---|---|
| **Wed 09-09** | **DEAFNESS TEST** — age the `job_runs` completion by controlled write, TEST-labelled, audit-logged; observe the alarm; restore; clear the latch; **verify the clear**. **T5b A/B/C.** | **NO — frozen day** |
| **Thu 09-10 AM** | **D3 read** | no |
| **Thu 09-10** | post-D3 batch: grader yfinance fallback + provider column **+ MANDATORY provider backfill (R-IV.325(b))**, fallback-rate alarm, Path A display fallback, SPY-to-allowlist | yes |

**The backfill is not optional and not deferrable.** It runs under T5b's discipline — A/B/C,
expected count declared before Phase B (**= the count of graded rows at the moment of the
deploy**), seal `== 843` before and after, and the write touching the new column only.
**The invariant it establishes is `provider IS NULL <-> graded_at IS NULL`, asserted both ways** — so the rule is a query,
not a memory.

**Deploy-day ordering matters and is stated here so it is not improvised:** the expected
count must be taken **at the deploy**, because the grader may run between measuring and
backfilling. Take it, then backfill, then re-assert — **a count measured an hour early is a
different population.**

**D3 stands on LIVENESS ALONE (R-IV.324(b)): a scheduled pass that ran and skipped
satisfies it.** Tonight's pass graded zero and that is not a D3 failure — D3 asks whether
the SCHEDULE works, and the answer does not depend on whether bars arrived.

**T5b's Phase B expected count is declared against the classification predicate on
`triton_flow_shadow` (R-IV.324(d)) — bar-independent**, so the dead vendor path does not block it. **The
seal invariant `count(...) == 843` is tomorrow's meaningful check**, not grading throughput.

**Vendor side:** the principal is checking the UW plan/endpoint status; this lane's three
read-only candidates (deprecation / entitlement / outage) narrow on his answer. **No
further probing from here** — a second lane testing the same endpoint would add calls and
no information.

**Observation 5 — the post-condition grep**, re-run after the last `backend/` commit, which is
Thursday's batch.
