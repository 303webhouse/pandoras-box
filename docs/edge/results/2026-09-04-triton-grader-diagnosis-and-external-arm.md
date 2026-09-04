# DEF-TRITON-GRADER-DARK — PHASE-0 MECHANISM DIAGNOSIS + R-IV.189(b) EXTERNAL ARM

**FROM:** CC-QUERY · **TO:** spine · **cc:** OLYMPUS-TRITON, EDGE, CC-BUILD, CC-POSITIONS
**Vintage (in-DB UTC): `2026-09-04 21:29:06.834394+00`** · read-only · measure before classify
**Firewall:** every row read is `fired_at < 2026-08-17` (audit population). **No holdout row
was read at any level.** CC-QUERY authored no criterion.

---

# PART A — MECHANISM

## A1. Where the grader lives

`backend/main.py:914-931` — an **in-process `asyncio.create_task` loop** inside the Railway
FastAPI app. Not a cron, not a separate service.

```python
last_run = None                                    # process-local
await asyncio.sleep(180)
while True:
    et = now(America/New_York)
    if et.weekday() < 5 and et.time() >= time(16,15) and last_run != et.date():
        await run_triton_shadow_grader()           # NO TIMEOUT
        last_run = et.date()
    await asyncio.sleep(1800)
```

Three properties of that loop drive everything below: `last_run` is **memory, not a table**;
the grader call has **no timeout**; and the job is **fail-open by design** ("Never raises",
grader docstring) with the loop swallowing exceptions to `logger.warning`.

## A2. Why relaunch cures it — MEASURED

A restart does two things at once: it clears anything blocking inside the coroutine, **and**
it resets `last_run = None`, which re-arms the day.

**The 09-02 correlation is exact.** Commit `6f2de35` at 14:35:30 MDT → Railway deploy →
process restart → 180-second warmup → first loop check (16:41 ET ≥ 16:15, `last_run` None):

```
commit          2026-09-02 14:35:30 MDT
grading began   2026-09-02 14:41:04 MDT   (20:41:04Z)   +5m34s
grading ended   2026-09-02 14:41:55 MDT   (20:41:55Z)
```

180s warmup plus build-and-boot accounts for the interval.

**The `last_run` reset is independently confirmed by a count that cannot otherwise occur.**
`GRADE_LIMIT = 1000` caps one pass at 1,000 rows. **2026-08-27 graded 1,862** — so at least
two passes ran that calendar day, which is impossible within a single process because
`last_run` blocks the second. Six commits landed after 16:15 ET that day (14:17, 14:22,
14:32, 18:18, 18:22, 23:55 MDT). Restarts, not schedule, drive the passes.

## A3. Why it went dark — the outage is not one event, it is FOUR

The grading write history contradicts the "wedged ~08-14, dark to 08-27" framing:

| gap | length | what ended it |
|---|---|---|
| **07-31 → 08-17** | **17 days** | first post-freeze deploy |
| 08-17 → 08-26 | 9 days | deploy |
| 08-26 → 08-27 | 1 day | deploy |
| **08-27 → 09-02** | **6 days** | deploy `6f2de35` |

Before 07-31 the grader ran **daily without a miss** (07-08 → 07-31, 120–283 rows/pass,
~20 seconds each). Every gap since has ended on a deploy, and every burst is a backlog drain
(08-17: 962 rows/21 min · 08-27: 1,862/6 min · 09-02: 573/51 s).

**The 17-day gap coincides exactly with the deploy freeze.** Last pre-freeze commit
`2026-08-02 23:11 MDT`; first post-freeze commit `2026-08-17 14:24 MDT`; FREEZE LAW ran
08-04 → 08-15. **No deploys meant no restarts, and no restarts meant no grading.**

That is the diagnosis in one line: **since 07-31 the grader has not been running on its
schedule at all — it has been running on deploys.** The schedule stopped working and the
deploy cadence masked it, because this repo deploys often enough that the gaps looked like
outages rather than the norm.

## A4. What blocks the loop — FENCED HYPOTHESIS

Nothing in the loop can produce a multi-day gap *while the process lives* except an
`await` that never returns. `await run_triton_shadow_grader()` carries **no `asyncio.wait_for`**
(confirmed: the only timeout in `main.py` is an unrelated `urlopen` at line 1405). If any
UW bar fetch inside it hangs, the loop never reaches `asyncio.sleep(1800)` again and never
sets `last_run` — it is parked until the process dies.

**Labeled FENCED:** I can show the loop *would* park on a hang, and that only restarts have
produced grading since 07-31. I **cannot** show a hang occurred — that needs the Railway
process logs for 07-31 → 08-17, which this lane cannot read. The alternative — that the
process itself died and stayed down — is not distinguishable from here and would produce the
same evidence.

**Two aggravating factors, both measured, both feeding the same fetch path:**

- `lookback_days = (today − earliest).days + 12`, where `earliest` is the oldest ungraded row
  for the ticker. The 72 permanently-ungradeable index rows anchor that at **2026-07-02**,
  so the per-ticker bar window **grows by one day, every day, without bound**. On 09-02 it
  was 74 days × 337 tickers per pass.
- `GRADE_LIMIT = 1000` with `ORDER BY fired_at ASC` — those same 72 rows are the oldest
  ungraded and therefore occupy the **first 72 slots of every pass, permanently**.

Both are consequences of DEF-TRITON-INDEX-UNGRADEABLE. Fixing that classification also caps
the fetch growth.

## A5. Can it recur silently — YES

**The grader is not registered in `signals_freshness`.** R-IV.133(b) ordered that
registration; it is not in the code. The only Triton supervision that exists is
`quota_shed:triton` in `uw_budget_watchdog.py`, which gates the **poller**, not the grader.

So every layer is silent by construction: the job never raises, the loop logs at `warning`
and continues, `last_run` leaves no durable trace of a missed day, and nothing external
checks that grading happened. **A five-week silence would look exactly like the four gaps
above — which is to say, like nothing.** This is the NULL-TRIGGER family: a job whose failure
state is indistinguishable from its idle state.

---

# PART B — EXTERNAL ARM (R-IV.189(b))

## B1. Vendor independence — a substitution, stated

The brief specifies recomputation "from UW daily closes." **No UW price path is reachable
from this lane.** I used **`stable_daily_bars`**, which `backend/stable_engine/bars_yf.py`
populates from **yfinance** — a *different vendor* from the grader's UW `get_ohlc`.

This is **stronger than specified for the arm's purpose**: a UW-vs-UW recompute would share
the vendor and could only catch arithmetic. Cross-vendor catches vendor error too. It is
**weaker in one respect**: a systematic UW-only price error that yfinance shares (both
wrong the same way) would pass. Coverage: 235 of 337 population tickers carry yf bars.

## B2. Sample — 34 rows, stratified, deterministic

All seven weeks × both directions (2 per cell, `row_number` ordered by id — no randomness,
fully reproducible), plus 6 rows drawn specifically from the **post-repair 09-02 batch** per
R-IV.213(f). Batch mix: ROUTINE 16 · BURST 08-17 4 · BURST 08-27 8 · **POST-REPAIR 09-02 6**.
Every row `fired_at < 2026-08-17`; the 09-02 rows are the **53 mixed-path** residue.

Grader logic replicated exactly: entry = `spot_at_fire` if > 0 else `close_on_or_near(fire_date)`;
target = nth Mon-Fri strictly after fire date; `close_on_or_near` tolerance order (0, +1, −1, +2, −2);
`(close−entry)/entry×100`, negated for BEAR, rounded 4.

## B3. RESULT — **PASS, 102 of 102 cells**

Tolerance: |delta| ≤ 0.50 percentage points (cross-vendor).

```
rows sampled            34        rows with no vendor bar    0
cell comparisons       102        within tolerance         102  (100.0%)
                                  outside tolerance          0

by batch                cells   within tol   max |delta|
  ROUTINE                 48       48 (100%)     0.0142
  BURST 08-17             12       12 (100%)     0.0001
  BURST 08-27             24       24 (100%)     0.1985
  POST-REPAIR 09-02       18       18 (100%)     0.0001
```

**94 of 102 cells agree to ±0.0000.** The single largest divergence is MSFT 5d at
**0.1985 pp** — one vendor-close difference on one day, well inside tolerance.

**The post-repair batch is the cleanest in the sample** (max 0.0001). Whatever stopped the
grader did not change what it computes: rows graded on 09-02 by the restarted process
reconcile as exactly as rows graded routinely in July.

## B4. VERDICT ON GRADER TRUST

**The stored grades are arithmetically and vendorially sound. The grader computes correctly.**

Nothing in DEF-TRITON-GRADER-DARK is a correctness defect. It is a **liveness** defect
throughout: the numbers it produces are right; the problem is *when*, and whether anyone
would know if it stopped.

## B5. WHAT THIS ARM DOES NOT TEST — the common-mode limit

Because I replicated `nth_trading_day` exactly, and it has **no holiday calendar**, any
trading-day misalignment is **common-mode and invisible to this arm**. Both sides make the
same mistake and cancel.

This is not hypothetical in the window: **Friday 2026-07-03 was a market holiday**
(Independence Day observed, July 4 falling on a Saturday). `nth_trading_day` counts it as a
trading day. The stored grades for rows fired 06-30 → 07-02 therefore target horizons shifted
by one session, and `close_on_or_near`'s ±2-day tolerance silently supplies a neighbouring
close instead of failing. **My recompute reproduces that shift rather than detecting it.**

A calendar-correctness arm is a separate test requiring an exchange calendar, and it is not
this one. Flagged, not resolved.

---

# PART C — T0 PRECONDITION (R-IV.223(b))

**The external arm PASSES. The T0 precondition on grader trust is SATISFIED.**

Stated in the required terms: the forward-window clock is **not blocked by grader
correctness**. 102 of 102 recomputed cells reconcile against an independent vendor, including
the post-repair batch.

**Two conditions I would put in front of the clock, neither a correctness matter:**

1. **The grader is not on a schedule — it is on the deploy cadence.** A forward window whose
   §2 clock starts "at the first session after P1/P2 verify live" assumes daily grading. Since
   07-31 that has not happened once without a deploy. A quiet week would produce a silent
   grading gap inside the observation window.
2. **It is unsupervised.** R-IV.133(b)'s `signals_freshness` registration is unimplemented.
   The registration binds liveness sentinels onto Triton's instruments precisely so this
   cannot happen — and the instrument that produces the window's outcome data is currently
   outside that binding.

Whether those gate T0 is spine's ruling, not mine. The correctness precondition is met.
