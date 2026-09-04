# CC BRIEF — GRADER-PRECONDITION: liveness, supervision, and one calendar

**Date:** 2026-09-04 · **Lane:** CC-BUILD (draft) · **Authority:** R-IV.252(c)
**Status: DRAFT FOR ATLAS/AEGIS.** Spine runs the review here; **no code is written
until that pass returns.** Position one next week.

**Source of record:** `docs/edge/results/2026-09-04-triton-grader-diagnosis-and-external-arm.md` (CC-QUERY, gate 551f9430).
Every mechanism claim below is that document's; this brief adds only the build shape.

---

## What this fixes, in one line

**Since 2026-07-31 the grader has not run on its schedule — it has run on deploys.**
Four gaps, each ended by a restart rather than a scheduled pass; the 17-day one is
exactly the 08-04→08-15 freeze. The failure state is indistinguishable from the idle
state, so five weeks of silence looked like nothing.

**The defect is LIVENESS, NEVER CORRECTNESS.** The R-IV.189(b) external arm passed
**102 of 102 cells** cross-vendor. Nothing written is wrong. Do not let the build drift
into re-validating output — that question is answered.

## Binding conditions

1. **Fix liveness, not correctness.** Any task that changes what the grader *computes*
   is out of scope and needs its own authority.
2. **The deafness test is part of the deploy, not a follow-up.** A sentinel that has
   never been shown to fire is not a sentinel. This is the whole lesson of
   `DEF-PYTHIA-ALARM-NOT-ACTIONED` — 1,200 correct alarm deliveries produced zero action, and of
   `DEF-STRIKE-WATERMARK-NEVER-ALIVE` — an alarm structurally unable to fire.
3. **ONE calendar utility**, not three fixes. See `DEF-GRADER-NO-HOLIDAY-CALENDAR`.
4. **No new detector for a condition an existing detector already reports.** Check
   `signals_freshness` first — SPEC-01 shipped a second liveness instrument without
   checking whether the first was already alarming, and it cost a build slot.

## Tasks

### T1 — Timeout on the grader call

`asyncio.wait_for` around the grader call. Today `await run_triton_shadow_grader()` carries none, so a single hung UW bar fetch parks the
loop until the process dies. **This is the fenced hypothesis in A4** — the diagnosis
can show the loop *would* park and cannot show that it did, because that needs Railway
process logs this lane cannot read. **The timeout is correct whether or not the
hypothesis holds**, which is why it goes first: it costs nothing if the cause was a
dead process instead.

A timeout that fires must LOG and let the next cycle retry, not re-raise into the
fail-open swallow.

### T2 — Durable `last_run`

Today `last_run` is process memory, so a restart re-arms the day and a missed day leaves
no trace. Move it to a table. **This is what converts "did it run?" from unanswerable
to a SELECT** — and it is the precondition for T3, because a sentinel needs something
durable to read.

**Watch the interaction:** durable `last_run` removes the accidental re-arm that deploys
currently provide. Ship T1 and T3 with it or grading gets *less* frequent, not more.
The current behaviour is a bug that is also the only thing keeping the grader alive.

### T3 — Register in `signals_freshness` + liveness sentinel + DEAFNESS TEST

R-IV.133(b) ordered this registration and **it is not in the code.** Register the
grader, add the sentinel, and **demonstrate at deploy that the sentinel can fire** —
force the condition, observe the alarm, record the observation in the build report.

Under `verification-laws.md` section 1.1 the sentinel is a registered predicate: declare its expected
satisfaction rate, measure it against the population, and where declared and measured
agree at 0%, state the state-change and **demonstrate it is reachable**.

### T4 — Skip reasons

When a pass grades nothing, record WHY. Today "graded 0 rows" and "did not run" are
the same observation from outside. A skip reason is what separates them.

### T5 — Index/cash-settled classification at ingest

Classify at write time so the **72 permanently-ungradeable index rows stop occupying
the first 72 slots of every pass** under `ORDER BY fired_at ASC` with `GRADE_LIMIT = 1000`. Same defect
family as DEF-TRITON-INDEX-UNGRADEABLE.

**This is also the fix that caps T6**, so T5 lands first.

### T6 — Bounded `lookback_days`

Today `lookback_days = (today - earliest).days + 12` anchored on the oldest ungraded row, which the 72 index rows pin
at 2026-07-02 — so the per-ticker bar window **grows by one day every day, without
bound**. 74 days x 337 tickers on 09-02.

**T5 removes the anchor; T6 puts a ceiling on it anyway.** Both, because a bound that
depends on another fix staying correct is not a bound.

### T7 — ONE market-calendar utility

Retires `DEF-GRADER-NO-HOLIDAY-CALENDAR` (P3) across all three consumers: the session helpers, the STRIKE
converter window, and this grader loop. **Holidays are data, not logic** — an explicit
list with a stated horizon and a loud failure past it, never a computed rule that
silently treats an unknown year as all-weekdays.

**Sequencing note:** T7 changes which tickers can alarm on a holiday, so it interacts
with `DEF-STRIKE-WATERMARK-NEVER-ALIVE`'s n-gate. Fix the calendar before tuning that gate, or the holiday
defect's blast radius moves underneath the fix.

## Done definition

- D1 — tests green; deploy verified four-step with the poll sequence reported.
- D2 — **DEAFNESS TEST OBSERVED AND RECORDED**: the sentinel was made to fire, and
  the build report states what was done and what was seen. **A green sentinel that was
  never provoked does not satisfy this.**
- D3 — a scheduled pass runs with **no deploy in the window**, proving the schedule
  works rather than the restart. **This is the acceptance test for the whole brief**
  and cannot be satisfied on a day anything was deployed.
- D4 — durable `last_run` shows a run for a day with no deploy.
- D5 — the 72 index rows no longer appear in a pass's first 72 slots.
- D6 — `lookback_days` bounded; the measured window stops growing.
- D7 — holiday behaviour verified at all three call sites against one calendar.

## Gates / what NOT to do

- NO changes to what the grader computes. Correctness is settled at 102/102.
- NO second sentinel where `signals_freshness` already covers it.
- NO deploy during a collection window — and note the tension recorded in
  PROJECT_RULES: fewer deploys currently means less grading, which is the defect this
  brief closes, not a reason to deploy more.
- NO holiday logic outside the single utility.

## Open question for the review

**D3 requires a day with no deploy.** This repo deploys often, and the board's cadence
this week was multiple deploys daily. Either the acceptance window is deliberately
quiet, or D3 cannot be satisfied — and an acceptance test that cannot be run is the
null-verifier this brief exists to remove. **Spine to rule on how that window is
reserved.**
