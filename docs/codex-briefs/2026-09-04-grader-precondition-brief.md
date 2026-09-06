# CC BRIEF — GRADER-PRECONDITION: liveness, supervision, and one calendar

**Date:** 2026-09-04 · **Lane:** CC-BUILD · **Authority:** R-IV.252(c)
**Status: CC-ACTIONABLE — R-IV.289.** The ATLAS/AEGIS pass returned and its seven
revisions are applied (R-IV.287). **Code may begin.**

**Actionable at gate `1a8260d6` · 27,454 B LF** — re-attached by R-IV.292(d) after the T1
correction. The delta from the reviewed gate `ed0d99ec` is **one hunk, +12/-3 lines, entirely
the T1 fenced-hypothesis paragraph**; nothing else moved, verified by diff before code
began.

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
loop until the process dies. **The fenced hypothesis in A4 is now FALSIFIED as the cause of the 07-31 outage
(CC-QUERY, 2026-09-06).** The grader reaches bars through `get_ohlc`, which has **no
fallback**, so every row it wrote dates UW liveness: **962 rows on 08-17, 1,862 on 08-27,
573 on 09-02 — all after the grader died on 07-31.** **UW was alive throughout, so a dead
vendor cannot be the grader's cause**, and `DEF-UW-OHLC-DEAD` is a separate, later failure
(onset after 2026-09-02 20:41:55Z).

**T1 still ships, and its justification is now the plain one rather than the hypothesis:**
an unbounded `await run_triton_shadow_grader()` is wrong on its own terms. **Do NOT merge this with
`DEF-UW-OHLC-DEAD`** — repairing the vendor path would make the symptom vanish while the loop
defect (in-memory `last_run`, no timeout) remains, which is the shape this brief exists to
prevent. **The timeout is correct whether or not the
hypothesis holds**, which is why it goes first: it costs nothing if the cause was a
dead process instead.

A timeout that fires must LOG and let the next cycle retry, not re-raise into the
fail-open swallow.

**PINNED VALUE — 300 s, derived, not chosen (R-IV.287(3)).**

```
measured grader pass        ~20 s
floor  = 10 x measured      200 s      (the >=10x rule)
PINNED                      300 s      (15x; headroom for a slow bar-fetch day)
```

**Why a multiple of the measured pass and not a round number picked for comfort.** A
timeout below the real distribution's tail converts a slow pass into a failed one and the
grader loses days it would have completed. **10x is the floor because the measured pass is
a single sample, not a distribution** — there is no p99 to size against, so the multiple
carries the uncertainty the sample cannot.

**Per-fire metric, required:** every fire increments a counter and logs the elapsed time.
**A timeout with no metric is indistinguishable from a timeout that never fires** — the
null-trigger law, and the reason this cannot ship as a bare `asyncio.wait_for`.

**What this leaves for T4.** A fire is a **skip reason**, and T4 is what records it.
Together they answer *"why did this pass not grade?"*; **neither answers it alone** — T1
knows the timeout fired but not what the pass was trying to do, T4 knows a pass was skipped
but not that the cause was a hang. **They ship together or the question stays open.**

### T2 — Durable `last_run`

Today `last_run` is process memory, so a restart re-arms the day and a missed day leaves
no trace. Move it to a table. **This is what converts "did it run?" from unanswerable
to a SELECT** — and it is the precondition for T3, because a sentinel needs something
durable to read.

**Watch the interaction:** durable `last_run` removes the accidental re-arm that deploys
currently provide. Ship T1 and T3 with it or grading gets *less* frequent, not more.
The current behaviour is a bug that is also the only thing keeping the grader alive.

**SHAPE RULED — a GENERIC `job_runs` TABLE, wired for the grader ONLY (R-IV.287(4)).**

One table, job-agnostic columns — job name, started, finished, status, rows touched, skip
reason, error — and **exactly one writer wired in this build: the grader.**

**Generic schema, single wiring, and the split is deliberate.** A grader-shaped table would
be the sixth private bookkeeping surface in this repo, and the weekday-approximation family
is what five private copies of one idea look like. **But wiring every job at once turns a
precondition build into a platform migration**, with a blast radius across jobs this brief
has not measured.

**So: the schema may serve everything; this build proves it on one job.** Other jobs adopt
it when their own work opens them, and **the brief states that they have NOT been
migrated** rather than leaving a half-populated table to imply coverage that does not
exist — an empty row for a job that never wrote is indistinguishable from a job that
never ran.

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

### T5b — CLASSIFICATION BACKFILL (R-IV.287(1))

**T5 classifies at ingest. Existing rows carry no class**, so the 72 permanently-ungradeable
index rows keep occupying the head of every pass until they are labelled. **T5 without T5b
fixes the future and leaves the defect running.**

**THE SEAL INVARIANT, ASSERTED BEFORE AND AFTER EVERY PHASE:**

```
count(id <= 377783 AND fired_at >= '2026-08-17 00:00:00Z') == 843
```

**Any deviation HALTS the phase and reverts it.** This is tripwire T1 of the forward-window
registration (*Seal breach | I1 != 843 | HALT, diagnose, no criterion evaluated*) — **not a
new check invented for this task, the existing one, honoured by a task that writes to the
sealed population's table.** A backfill is exactly the kind of operation that would breach
it silently.

**Phasing — A, B, C, each with its row delta stated BEFORE it runs:**

| phase | what it does | row delta expected | gate to proceed |
|---|---|---|---|
| **A — shadow** | write the class to a NEW column; **no consumer reads it** | every target row classified; **0 rows change any existing column** | seal == 843; the count of classified rows equals the count of targeted rows |
| **B — verify** | compare the shadow class against the known population | **the 72 index rows are identified as such**, and the 15 cash-settled rows inside the seal are among them | seal == 843; **a stated, non-zero expected count that is MET, not merely non-empty** |
| **C — cut over** | the grader's ordering and filter read the class | **0 further writes**; only read-path behaviour changes | seal == 843 after |

**Phase B's gate is the one that matters, and it is written to be falsifiable.** *"Some
rows were classified"* passes trivially and proves nothing — the vacuous-count family.
**The expected count is declared before the phase runs**, per §1.1, and a mismatch in
either direction is a HALT rather than a note.

**Nothing in A or B changes what the grader reads.** The class is inert until C, so a
wrong classification is recoverable by correcting a column — **not by re-grading, which
T7's resolution forbids.**

### T6 — Bounded `lookback_days`

Today `lookback_days = (today - earliest).days + 12` anchored on the oldest ungraded row, which the 72 index rows pin
at 2026-07-02 — so the per-ticker bar window **grows by one day every day, without
bound**. 74 days x 337 tickers on 09-02.

**T5 removes the anchor; T6 puts a ceiling on it anyway.** Both, because a bound that
depends on another fix staying correct is not a bound.

**THE BOUND — >= 20 TRADING DAYS PLUS HOLIDAY SLACK (R-IV.287(5)).**

The longest horizon this brief introduces is **20d** (T9), so the window must cover 20
*trading* days at minimum — **a bound below the longest horizon silently truncates the
horizon it was meant to serve**, and would do so by returning fewer bars rather than by
failing.

**Plus holiday slack, and the slack comes from T7's calendar, never from a multiplier.**
A calendar-days figure computed as `20 x 1.6` is the weekday approximation wearing a
different constant — the same family this brief exists to retire. **T7 supplies the trading
calendar; T6 asks it how many calendar days hold 20 trading days, plus margin.**

**Order: T7 before T6's final value.** T6 can ship a conservative constant first, but its
*correct* value is a question only the calendar can answer.

### T7 — ONE market-calendar utility

Retires `DEF-GRADER-NO-HOLIDAY-CALENDAR` (P3) across all three consumers: the session helpers, the STRIKE
converter window, and this grader loop. **Holidays are data, not logic** — an explicit
list with a stated horizon and a loud failure past it, never a computed rule that
silently treats an unknown year as all-weekdays.

**Sequencing note:** T7 changes which tickers can alarm on a holiday, so it interacts
with `DEF-STRIKE-WATERMARK-NEVER-ALIVE`'s n-gate. Fix the calendar before tuning that gate, or the holiday
defect's blast radius moves underneath the fix.

**RESOLUTION, ON THE FACE (R-IV.287(2)): CALENDAR-CORRECT HORIZONS APPLY TO NEW GRADES
ONLY. NO RE-GRADING, EVER.**

Rows already graded under the old holiday-blind arithmetic **keep their values**. The
calendar changes what is computed from the cutover forward and **touches nothing behind
it.**

**This is not a convenience and it is not a deferral — re-grading would be a
registration breach.** Graded outcomes are the population the forward window and the
sealed holdout are defined over. **Silently recomputing them changes the evidence after
the predictions were registered**, which is the one thing a pre-registration exists to
prevent. A better number obtained that way is worth less than the worse number it
replaced.

**Consequence to state rather than hide: the series is not internally homogeneous.** Grades
before the cutover used a different day-count than grades after it. **Anyone pooling across
the boundary is pooling two definitions**, and the brief says so here so that a later
analyst finds the seam documented instead of discovering it as an anomaly.

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
  and cannot be satisfied on a day anything was deployed. **The window is RULED by R-IV.255(b),
  TERMS NOW SUPPLIED (R-IV.289(b)):** the **first full calendar day after the precondition
  build deploys is DEPLOY-FROZEN** — commits held locally, **no pushes** — and **D3 reads
  the following morning.** Generalized: *an acceptance test that needs a quiet window gets a
  scheduled one.*

  **Dates taken (this lane's call, on spine's suggested shape):**

  | when | what |
  |---|---|
  | **Tue 2026-09-08, after the close** | deploy the precondition build |
  | **Wed 2026-09-09** | **DEPLOY-FROZEN.** Commits held locally, nothing pushed |
  | **Thu 2026-09-10, AM** | **D3 read** |

  **One interaction checked before taking these dates:** the poller-pause watch
  (R-IV.274(a)) runs *through Tue 09-08 close*, so a deploy after that close **does not
  disturb it** — the watch has already concluded. Monday 09-07 is Labor Day, so Tuesday is
  the first RTH session and the earliest honest deploy day.

  **The freeze is the acceptance test, not an inconvenience around it.** D3 asks whether the
  schedule works rather than the restart; **a push during the frozen day silently converts a
  pass into a restart-driven pass** and the test reports success for the wrong reason —
  which is the null-verifier this brief exists to remove.
- D4 — durable `last_run` shows a run for a day with no deploy.
- D5 — the 72 index rows no longer appear in a pass's first 72 slots.
- D6 — `lookback_days` bounded; the measured window stops growing.
- D7 — holiday behaviour verified at all three call sites against one calendar.
- D8 — **the strata readiness table is on the registration face and is TRUE**: every
  stratum either stamped from the first window session or declared NOT STAMPED. A
  present-but-null column satisfies neither and fails this.
- D9 — 10d/20d horizons each carry a resolution rule and a distinct
  not-yet-resolvable state, demonstrated on a row too young to resolve.

## THE BUILD REPORT MUST CARRY (R-IV.289(d))

**Six items. Each is an OBSERVATION, not an assertion that a thing was done.**

1. **Poll sequences per deploy.** Every sample, in order, with its status — not a summary
   verdict. Railway SUCCESS is not app-up; that has now occurred five times.
2. **The deafness test AS AN OBSERVATION.** **What was withheld**, **what fired**, and
   **the latch cleared AND the clearing verified.** *"The sentinel works"* does not satisfy
   this. A green sentinel that was never provoked satisfies nothing (D2).
3. **Seal count before AND after each of A, B, C** — six numbers, each `count(id <= 377783 AND fired_at >= '2026-08-17 00:00:00Z') == 843`.
4. **Phase B's expected count STATED BEFORE IT RAN, and the count MET.** Stating it
   afterwards is fitting the prediction to the result; **the ordering is the whole test.**
5. **The post-condition grep, RE-RUN**, with its output, after the last commit that touches
   `backend/`.
6. **The `/info` issue-type vocabulary AS RETURNED LIVE, quoted, BEFORE the classifier was
   written.** Not the field's documented values — the values the endpoint actually
   returned, on the day.

**Every one of these is written the same way for the same reason:** each names a thing that
could have been skipped and reported as done. **An observation can be wrong; an assertion
that work happened cannot be checked at all.**

## AEGIS HYGIENE (R-IV.287(7)) — binding on every task above

**1 — The deafness test is TEST-LABELLED, AUDIT-LOGGED, and CLEARS ITS LATCH.**
D2 requires the sentinel be *made to fire*. That means deliberately writing an alarm
condition into a live system, so: the fired artifact carries an explicit **TEST** label on
its face, the act is **audit-logged** (who, when, what was induced, what was observed), and
**the latch is cleared afterwards and the clearing is verified** — not assumed.
**An uncleared test latch is a live alarm that everyone has been told to ignore**, which is
strictly worse than never testing.

**2 — The metering script is KEY-SAFE and RETIRED AFTER ONE RUN.**
The out-of-band request for `DEF-UW-OHLC-DEAD`'s metering question (R-IV.279(d)) reads a
credential. It **never prints, logs, or echoes it**; it is **deleted after the single run**,
and the run's *result* — not the script — is what gets filed. **A one-off script that
survives its one use becomes a permanent credential-handling surface nobody owns.**

**3 — The auth header is never logged on any error path. STATED WITH ITS GREP.**

```
grep -rnE "logger\.(error|warning|exception|info).*(headers|Authorization|Bearer|UW_API_KEY)" backend/ --include=*.py
  -> no matches   (run 2026-09-05, at `5bb844d`)
```

**The check is reachable, which is the part worth asserting.** `backend/integrations/uw_api.py` alone
contains **14** logging calls for the pattern to match against, so an empty result is
evidence rather than an artefact of there being nothing to find — **an empty grep over an
empty corpus proves nothing**, and this corpus is not empty. The header is constructed at
`uw_api.py:175` and must stay out of every log call added by this build; **re-run the
grep as a post-condition.**

**4 — Every migration carries a `-- DOWN` section.**
Including T5b's column and T2's `job_runs` table. **A migration without a down
path is a one-way door**, and this build adds a column to the table the sealed holdout
lives in.

## Gates / what NOT to do

- NO changes to what the grader computes. Correctness is settled at 102/102.
- NO second sentinel where `signals_freshness` already covers it.
- NO deploy during a collection window — and note the tension recorded in
  PROJECT_RULES: fewer deploys currently means less grading, which is the defect this
  brief closes, not a reason to deploy more.
- NO holiday logic outside the single utility.

## Open question for the review

**~~D3 requires a day with no deploy.~~ CLOSED — ruled by R-IV.255(b) (R-IV.287(6)).**
It is no longer an open question and is not re-argued here. The concern that raised it
stands as the reason the ruling was needed: **an acceptance test that cannot be run is the
null-verifier this brief exists to remove.**

**Second question, added 2026-09-05 (R-IV.274(c) scope).** **Tide sign cannot be
stamped when the clock starts** — the sink lands one build later, and the poller is
now paused. Either the registration face declares it NOT STAMPED, or the clock waits
for position 2. **ANSWERED by R-IV.275(b) S6: NOT STAMPED AT CLOCK START.** The registration face
declares it; the clock does not wait. The definition is fixed now and the values arrive
with the sinks build, so the amendment does not land after the clock — which was the
constraint that made this a question rather than a preference.
