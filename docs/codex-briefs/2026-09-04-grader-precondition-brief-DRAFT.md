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

**Definition pinned by R-IV.275(b) S3, and T5 remains the SINGLE implementation of it
(R-IV.275(c)) — the strata task does not build a second one.** Classify **by PRODUCT
TYPE**: cash-settled index / ETF / single name.

**NOT by `INDEX_TICKERS`.** Measured 2026-09-05: that set is
`{SPY, QQQ, SMH, NVDA, AVGO, MSFT, GOOGL, AMZN, META}` — **nine members: three ETFs and
exactly six single names, and zero cash-settled index products.** It is a **$2M premium
FLOW-TIER bucket**, and its name is the whole trap: a reader looking for an instrument
class finds a set called *INDEX_TICKERS* and uses it, silently classifying six of the
largest single names in the book as indices.

**A set named for a class it does not encode is worse than an absent one** — the absent
one makes you go and look.

**SOURCE RULED — R-IV.279(e). Two inputs, and neither is `INDEX_TICKERS`:**

| class | source |
|---|---|
| ETF vs equity | **UW `/info` issue type**, per ticker |
| cash-settled index | **the list carried in `DEF-TRITON-INDEX-UNGRADEABLE`: SPX · SPXW · RUT · RUTW · VIX** |

**`INDEX_TICKERS` IS NEVER CONSULTED FOR CLASSIFICATION**, and the grader build **renames it to
what it is — a premium tier — so the word stops lying.** The rename is part of this task,
not a tidy-up deferred to later: while the name survives, the next reader repeats the
mistake, and a comment saying *"not really an index"* has never once stopped anyone.

**Two build facts measured 2026-09-05, both of which shape the work:**

- **`/info` already exists in the client** — `uw_api.py:408`, with a **24-hour cache**. So
  S4's sector map and S3's issue type come from the same call, and the cache makes a
  per-ticker one-time map cheap. **They should be fetched together, once.**
- **No code reads an issue-type field today.** `issue_type` appears nowhere in `backend/`.
  This is new consumption of an existing endpoint, so **the field's presence and its
  vocabulary must be verified against a live response before the classifier is written** —
  not assumed from the endpoint's name. If a ticker has no issue type it is **UNMAPPED**,
  the same rule S4 gives sector, and never guessed.

**S4's sector map absorbs the duplicated SPDR literal (R-IV.281(c)) — and the duplication
is larger than the census reported.** The census cites two files. **Measured 2026-09-05 by
CC-BUILD: 10 declaration sites across 9 files**, counting any place where ≥ 9 of the 11
SPDR tickers appear within an 8-line window:

```
analytics/calendar_context.py  api/flow_radar.py  api/stable.py (x2)
discord_bridge/bot.py  indicators/sector_rotation_3_10.py
scanners/hybrid_scanner.py  scanners/universe.py
stable_engine/strip.py  stable_engine/universe.py
```

**The shapes differ** — some are ticker sets, some ticker→name maps, one is a
name→ticker map — **which is why they drifted apart without anyone noticing.** One of the
ten carries 9 of 11, not 11 of 11: `scanners/hybrid_scanner.py:978`. **Whether that is a deliberate
subset or a decayed copy is unread**, and the S4 build must decide rather than assume.

**Scope note, stated so it is not silently widened:** S4 needs **one** sector source. It
does **not** need all ten call sites migrated in the grader build — that is a larger
refactor with its own blast radius. **What this task owes is the single source and a
declaration of which sites it supersedes**, so the eleventh copy is never written.

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

### T8 — Per-row OBSERVATIONAL strata stamps

**Added by R-IV.270(b), confirmed in scope by R-IV.274(c); the same strata Amendment 1
declares on the registration face (R-IV.273(b)).** Six strata recorded per row from the
first window session: sector, instrument class, day-of-week, DXY trend sign,
footprint-present, tide sign.

**The governing rule is R-IV.270(b)'s:** *fields exist before the window clock starts, or
they are declared NOT STAMPED on the registration face.* **So this task's deliverable is
not six columns — it is a truthful readiness table**, and a stratum that cannot be stamped
must be declared missing rather than quietly omitted. A column that exists and is null for
the first three weeks is the worse outcome: it reads as measured-and-absent.

**Readiness measured 2026-09-05 by CC-BUILD, not assumed:**

| stratum | source | ready |
|---|---|---|
| instrument class | **T5 already builds this** | **YES — do not build it twice** |
| day-of-week | row timestamp + T7's calendar | YES |
| sector | existing sector / theme membership | YES, but needs one definition: **sector of record AT INGEST**, never as-of-read — a stratum re-derived at analysis time is not a stratum |
| DXY trend sign | `backend/analytics/price_collector.py` carries DXY | **NEEDS A DEFINITION** — trend over what lookback, and which sign at exactly zero |
| footprint-present | `signals.source = 'footprint'` — **a JOIN, not a stamp**; there is no footprint table or column | **NEEDS A WINDOW DEFINITION** — present *within what interval of the row* |
| tide sign | **NO SINK.** Redis-only at `board:tide:latest`, 1800 s TTL | **NO — see below** |

**UPDATE 2026-09-05 — R-IV.275(b) SUPPLIES EVERY DEFINITION THIS TABLE WAS MISSING.**
The three open definitions are now closed and the blocked one is deferred *with its
definition fixed*, which is the difference between a stratum that is missing and a stratum
that is undefined:

| stratum | now |
|---|---|
| **S1** day-of-week | from `fired_at` (ET). **Cells are unequal by construction** (Thu 1,572 vs Fri 1,035 in the pinned population) and are **reported, never rebalanced** — rebalancing would manufacture a population that never fired |
| **S2** DXY trend sign | **PROXY DECLARED** — UUP daily closes from `stable_daily_bars`, `sign(close[t−1] − close[t−6])`, stamped at fire. **The proxy is declared, not silent**: UUP is not DXY, and the face says so |
| **S3** instrument class | by PRODUCT TYPE (see T5) — **one implementation, in T5** |
| **S4** sector | one-time ticker→sector map from UW `/info`, cached. **A ticker with no map is UNMAPPED, never guessed** |
| **S5** footprint-present | a footprint row, **same ticker + same trading date** (the census join key); **strategy-scoped, never source-scoped**; the under-count figure **is dated whenever cited** |
| **S6** tide sign | **DEFERRED COMPUTATION.** Net premium sign of the 5-minute market-tide bar containing `fired_at`, from `market_tide_history`, once the sink ships and backfills. **Face states NOT STAMPED AT CLOCK START** |

**S5's "strategy-scoped, never source-scoped" is the load-bearing clause**, and it is the
same distinction that made `signals.source = 'footprint'` a join rather than a stamp: `source` records which
producer wrote the row, not which strategy the row belongs to, and joining on the wrong one
silently changes the population.
The three definitions are cheap but they are *decisions*, not implementation: each one
silently determines what the seven-week window can later claim.

#### The tide-sign collision — raised, not resolved here

**Tide sign cannot be stamped when the window clock starts, and this is now certain
rather than likely.** The chain, each link measured or ruled:

1. Tide persists **nowhere but Redis** — `board:tide:latest`, 1800 s TTL. Verified 2026-09-05. It is
   one of the two compute-then-discard feeds the re-scope §4 named.
2. R-IV.273(c) **paused the tide poller** — executed 2026-09-05. So even the Redis value
   stops after the current TTL.
3. R-IV.273(d) orders **grader P1/P2 (position 1) → sinks + backfill (position 2)**.
4. The precondition order is **Amendment 1 filed → P1/P2 verify live → clock starts.**

**The clock therefore starts at the end of position 1, and the tide sink lands in position
2.** Spine's own clause already hedges it — *"tide sign when the sink exists"* — so this
is a sequencing consequence to be declared, not a contradiction to be fixed.

**Two branches, and the choice is spine's:** either the registration face declares tide
sign **NOT STAMPED** for the window, or the clock waits for position 2. **This lane does
not choose**, and flags only that the second branch delays the clock by a whole build.

**One trap worth naming.** Sinks ship *with backfill from UW history*, so tide sign for the
window's early sessions will become computable **after the fact**. A backfilled stratum is
legitimate data and is not a legitimate *registration*: analysing it later is the
hypothesis generation the ruling already face-labels, and treating it as prospectively
registered would be the amendment landing after the clock — exactly what the precondition
order forbids. **If tide sign is declared NOT STAMPED, later backfill does not undeclare
it.**

### T9 — 10d/20d horizons

**Added by R-IV.270(b), in scope per R-IV.274(c).** The grader gains 10-day and 20-day
horizons alongside what it grades today.

**This is the one task in this brief that touches what the grader computes**, and the
brief's own gate says not to. The gate holds for **correctness** — settled at 102/102 and
not to be re-litigated — while this adds *new* horizons beside it. **Stated explicitly so
the reviewer rules on it rather than discovering the tension.**

Two conditions, both from defects already registered:

- A horizon needs the **bounded** window of T6 and the **calendar** of T7. A 20-day
  horizon computed on an unbounded, holiday-blind window inherits both defects and
  multiplies them by two more horizons.
- Each horizon states **its own resolution rule and its own not-yet-resolvable state.**
  A row 6 days old is not an unresolved 10-day grade; it is a row whose 10-day horizon has
  not arrived, and the two must not share a value. This is the vacuous-column family
  (QS-02's PENDING string, DEF-EDGE-SPEC-B2) arriving by a new route.

**Definition pinned by R-IV.275(b) H2:** the horizons live in **NEW columns with their OWN
completion marker** (`graded_20d_at`).

**`graded_at` KEEPS ITS MEANING — 5d terminal — FOREVER, AND MAY NOT MOVE.** The seal count,
the residue, the tripwire identity and the RELEASE predicate all key on it. **Widening
`graded_at` to mean "graded at some horizon" would silently redefine four registered
quantities at once**, including the holdout's release condition — which is the one
predicate in this system that must not move under any circumstance.

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
- D8 — **the strata readiness table is on the registration face and is TRUE**: every
  stratum either stamped from the first window session or declared NOT STAMPED. A
  present-but-null column satisfies neither and fails this.
- D9 — 10d/20d horizons each carry a resolution rule and a distinct
  not-yet-resolvable state, demonstrated on a row too young to resolve.

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

**Second question, added 2026-09-05 (R-IV.274(c) scope).** **Tide sign cannot be
stamped when the clock starts** — the sink lands one build later, and the poller is
now paused. Either the registration face declares it NOT STAMPED, or the clock waits
for position 2. **ANSWERED by R-IV.275(b) S6: NOT STAMPED AT CLOCK START.** The registration face
declares it; the clock does not wait. The definition is fixed now and the values arrive
with the sinks build, so the amendment does not land after the clock — which was the
constraint that made this a question rather than a preference.
