# VERIFICATION-LAWS ADDENDUM 3 — laws found by running the instruments

**FROM:** CC-BUILD. **Commissioned:** R-IV.359(b) (Law 2), R-IV.343(a) (Law 1), R-IV.403(a) (Law 3);
calibration clause R-IV.354(a), filed R-IV.425(d).
**Target:** `docs/conventions/verification-laws.md` (ratified R-IV.166).
**All three laws below were produced by a verification failing in production, not by review.**

**NOTE ON NUMBERING:** Laws 1 and 3 were each filed as their own artifact —
`verification-laws-instance-readiness-gate.md` (2026-09-10) and
`verification-laws-instance-prescribed-instrument.md` (2026-09-16, gate `b4046f12`).
**Neither is restated here** — this file cites them so the numbering is explicit rather
than invented, and none is maintained in duplicate (conventions #9).

---

## LAW 1 — THE READINESS GATE PROVES LIVENESS, NOT IDENTITY

**Filed in full at `docs/conventions/verification-laws-instance-readiness-gate.md`.**
Ratified as Step 3 of record by R-IV.344(a); the three-line form settled at R-IV.348(b).

**One line:** a gate that cannot distinguish the two states either side of the event it
gates is a null verifier for that event, however well it works for its own.

---

## LAW 2 — INDEPENDENCE IS OF THE QUESTION, NOT THE MECHANISM

> **Two confirmations that share a domain measure the domain.**
> **A claim about a RUNTIME is not confirmed by any number of reads of a CONFIGURATION
> SURFACE.**

### The worked example

**The question:** does `RAILWAY_GIT_COMMIT_SHA` exist in the running container?

**Two measurements were taken, by different mechanisms, and both said NO:**

| # | mechanism | result | what it actually measured |
|---|---|---|---|
| 1 | `railway variables` listing | not among the 14 names returned | **the control plane's variable list** |
| 2 | a service variable set to `${{RAILWAY_GIT_COMMIT_SHA}}` | **resolved to EMPTY, length 0** | **the control plane's reference resolver** |
| 3 | `/health.build` after the deploy | **PRESENT — and it was the pushed SHA** | **the container** |

**At the time, measurement 2 was filed as *"a second, independent confirmation by a
different mechanism."* It was a different mechanism IN THE SAME DOMAIN.**

**A listing and a resolver are both the configuration surface.** Neither can see a process
environment. **They were not independent of the question; they were independent of each
other and jointly blind to the thing being asked.**

### Why "different mechanism" felt like independence, and was not

**The two mechanisms fail differently, which is exactly what makes them feel independent.**
A listing can omit; a resolver must answer. Getting the same answer from both therefore
*feels* like corroboration — and would be, for a question about configuration.

**The error is not using two mechanisms. It is not asking what DOMAIN each one can see.**

> **Independence is a property of the relationship between a measurement and a QUESTION,
> not between two measurements.**
> Two instruments pointed at the same wrong place agree perfectly.

### The rule

**Before calling a second measurement a confirmation, state what each one physically
reads.** If the answer is the same substrate — the same table, the same API, the same
config store, the same process — **the second measurement bounds the first's precision, not
its correctness.**

**The check is one sentence:** *"what would have to be true for BOTH of these to be wrong
in the same direction?"* **If that sentence has a short answer, they are not independent.**
Here the answer was four words: *the control plane lies.* Not lies maliciously — simply
does not enumerate what the platform injects at runtime.

### THE SCOPE SENTENCE IS WHAT SAVED IT — and that is the transferable part

**The filing that got the answer wrong also contained this, verbatim:**

> *"It does not prove the variable is absent from the container at runtime — a platform may
> inject at runtime what it does not list."*

**That sentence is the difference between a wrong finding and a bounded one.** The
conclusion was wrong; the claim was not, because the claim named the domain it had
measured and declined to generalise past it.

**So Law 2 has a corollary that costs nothing and pays whenever the law is broken:**

> **A NEGATIVE FINDING STATES THE DOMAIN IT SEARCHED** (conventions #10, applied to
> substrate rather than to file paths).
> **When the domain turns out to be the wrong one, a finding that named it is corrected;
> a finding that did not is retracted.**

### A second instance, four days later, in a different subsystem

**2026-09-13.** A convergence check — account counter versus hub counter — returned
`other = 0`, and was filed as confirming that a foreign API consumer had stopped.

**It was taken on a Sunday.** A weekday-only consumer reads zero on a Sunday; so does a
stopped one. **Monday returned `other = 6,140`.**

**Same law, different surface:** the measurement and the question shared a domain — *"is
this process running?"* was answered by *"is this process spending?"* on a day the process
was never scheduled to spend. **And the discriminator had been filed four hours earlier for
the nightly job, against a weekend gap, by the same lane.**

> **A law is not learned when it is written. It is learned when it is applied to the next
> subsystem, which looks nothing like the one that produced it.**

### A third instance — the lane that wrote the law, on a database (R-IV.416(b))

**Filed under CC-BUILD's name, because CC-BUILD committed it.**

**The question (2026-09-16):** does the lots/legs build start from an empty schema?

**The measurement:** a search of `migrations/` and `backend/` for DDL creating a lots table.
**It found none, and the survey reported "no lots/legs schema exists."** A `backend/` file did
match — `api/unified_positions.py` — and was dismissed unread as "probably a comment."

**The truth:** `position_lots` had existed in production since **2026-08-26**, created by
`scripts/feat_position_lifecycle_phase1.py` with a one-time backfill. The matched file held its
live `GET` and `POST` routes. **Of 34 open positions, 14 carried a lot and 20 carried none.**

**Same law, third surface.** The first instance read a configuration surface to answer a
question about a runtime; this one **read SOURCE CODE to answer a question about a DATABASE.**
A table is created by whatever ran against the database — a migration, a startup hook, or a
script run once by hand — and **no search of the migrations directory can see the third.**
The two confirmations it did have (no DDL in `migrations/`, no DDL in `backend/`) shared a
domain, and the domain was not the one being asked about.

**What it would have cost, had the build proceeded on it:** a create-if-missing that silently
does nothing against the existing table, inserts that then fail on columns that do not exist,
and **a backfill that gives 14 positions a second lot and doubles their quantity** — every row
individually valid, the sum wrong.

**And the corollary held again.** The survey's negative named its scope ("migrations/ and
backend/"). That is why the correction was a correction and not a retraction: the scope
sentence said exactly which domain had been searched, and the answer was in a different one.

> **The dismissed hit is the part to keep.** The search DID find the evidence and the
> author did not read it. A negative finding is not bounded only by where it looked, but by
> **what it looked at and chose not to open.**

**Instance count: 3.** All self-inflicted, all caught by a later measurement rather than by
review — **and the third committed by the lane that wrote the law.**

---

## LAW 3 — THE DIFFERENTIAL PROBE

> **Vary the input across a range where the correct output MUST differ.**
> **If the outputs do not differ, the instrument is not reading the input.**

**Full worked example filed at
`docs/conventions/verification-laws-instance-prescribed-instrument.md` (gate `b4046f12`).**
Ratified R-IV.403(a). In one line: `TZ='<zone>' date` returned one wall clock for five
zones spanning sixteen hours of real offset, exit status 0 on every call, because the
machine ships no tzdata and the implementation falls back to UTC instead of failing.

### Why it is not Law 1 and not Law 2 — the reason it was filed separately

**Not Law 1 (the readiness gate).** That law governs an instrument returning a TRUE fact
about the WRONG QUESTION — the gate really was green, it simply could not speak to
identity. Law 3's instrument returns a **FALSE** fact: a wall clock attributed to a zone it
never consulted. Law 1's remedy is to add the missing question; here there is no missing
question, only an answer that was never measured.

**Not Law 2 (shared domain).** Law 2 governs TWO measurements that feel independent, and
its remedy — measure in another domain — presumes a second reading exists to corroborate
against. **Law 3's failure is available to a single instrument in isolation, with nothing
to compare it to.** That is precisely why it needs its own test: Law 2 tells you when your
second opinion is worthless; Law 3 tells you when your *first* one is, before you go
looking for a second.

**The distinct property is the FALLBACK.** The lookup fails, and the implementation's
response to a failed lookup is to answer anyway. **The failure is handled — just not
reported.** Kin: conventions **#17** (a health surface never fails closed) and **#18** (a
negative read reports the partition). All three are a component answering when its honest
answer was *"I cannot."*

### THE COMPANION INFERENCE RULE (R-IV.387(a))

> **AN ABSENCE IS ONLY EVIDENCE WHEN THE INSTRUMENT COULD HAVE SHOWN A PRESENCE.**

Registered on the RAMZ line-cut absence; **that instance belongs to CC-POSITIONS and its
detail stays on its own face** (conventions #9) — it is cited here because it is the other
half of this law and should not be filed away from it.

**The two fit together as test and licence.** The probe is the TEST: does this instrument
discriminate at all? The companion rule is the INFERENCE the test licenses: **until the
probe passes, a silence carries no information.** Run in the wrong order — trusting a
silence and only afterwards asking whether the instrument could have spoken — the answer
arrives after the conclusion has already been filed.

### THE STANDARD (R-IV.403(a))

**Any gate, filter or predicate whose failure mode is SILENCE gets a differential probe
before it is trusted.** The probe needs no knowledge of the correct answer — only two
inputs that cannot legitimately share one output. It is therefore cheap enough to have no
excuse: a filter that may not be filtering, a `WHERE` clause that may not bind, a gate
whose predicate may be constant, a decoder guessing an encoding, a counter that returns
`None` for both "unconfigured" and "unreachable".

### FIRST APPLICATION — inward, the same hour it was ratified

**The disconnect meter, probed against its own summary.** Four scenarios were fed to the
REAL tail block, lifted verbatim from the source rather than re-implemented:

| scenario | 429s | no_acct | no_hub | rate |
|---|---|---|---|---|
| redis dead, foreign burning ~21,000/h | 0 | 0 | **n** | `no data` |
| healthy, foreign traffic genuinely zero | 0 | 0 | 0 | **`0`** |
| account exhausted — Tuesday's void | **n** | **n** | 0 | `no data` |
| meter never ran | — | — | — | **exit 3** |

**Before the probe the summary had two columns and conflated the first and third.** Four
causes now carry four signatures.

**And the probe corrected the author, not only the instrument.** The suspicion that
prompted it — *"this is the same collapse a third time"* — was WRONG, and the probe is what
established that: genuine zero prints `0`, an absent input prints `no data`, and they were
already distinct. The real defect was narrower: `no data` did not say WHICH input was
absent, and the two have different owners (vendor header vs our own Redis counter).

> **A probe does not only catch defects. It SIZES them** — and an alarm that has been
> sized is worth more than one that has been raised, because the register is asked to act
> on it.

**Instance count: 1 filed (the clock), 1 inward (the meter, above), 1 companion
(R-IV.387(a), POSITIONS'). The standard is now standing, not commissioned.**

---

## COMPANION TO LAW 3 — THE KILL THAT REPORTED SUCCESS (R-IV.404(c))

> **AN ACTION'S RETURN VALUE IS A REPORT ABOUT THE REQUEST, NOT ABOUT THE WORLD.**
> **NEVER DESTROY A WORKING INSTRUMENT YOU HAVE NOT PROVEN YOU CAN REPLACE.**

### The instance

**2026-09-16, re-arming the disconnect meter.** The running meter had to be stopped so a
patched version could take its place. `Stop-Process` was issued against the parent of the
process tree. **It returned success.**

**The tree survived.** The parent died; the worker — `python3.12.exe`, four levels down
through a `cmd` → `node` → `railway.exe` → `cmd` chain — kept running, **holding the old
code**. It was found by enumerating processes afterwards rather than by reading the return
value, and stopped explicitly, leaf by leaf.

### Why this is not a tidiness note

**Both the old worker and the new one write to the same CSV.** Had the orphan survived the
re-arm, the run would have had two writers on one file, sampling on independent ten-minute
clocks, **one of them running the code whose summary conflated two causes.**

**And every row either process wrote would have been well-formed.** No parse error, no
truncation, no exception — just a file with roughly twice the expected rows, interleaved
from two code versions, with no column recording which process wrote which line. **The
corruption would have presented as a slightly busy but entirely valid CSV**, and the
disconnect read would have been computed from it.

> **That is the register's oldest failure wearing new clothes: not a crash, an answer.**

### Why it sits beside Law 3 rather than inside it

**Law 3 asks whether an INSTRUMENT reads its input.** This asks whether an **ACTION**
achieved its effect. Different questions.

**The shared root is that in both cases the report was generated by the actor, not by the
state.** `TZ= date` reported on its own execution, not on the timezone database.
`Stop-Process` reported on the signal it sent, not on what remained running. **Neither
instrument is lying; both are answering a narrower question than the one being asked of
them, and the gap is invisible in the return value.**

The check is the same shape in both: **go and look at the thing itself.** For an
instrument, probe it with inputs it must distinguish. For a destructive action, **enumerate
the state afterwards** — the survivors, not the exit code.

### The sequencing rule, which is the more valuable half

**The relaunch path was proven BEFORE anything was killed.** `railway run` had begun
refusing with *"Multiple services found"* — the very command that had armed the meter in the
first place. Had the kill come first, the working instrument would have been destroyed and
the replacement would have failed, **with no way back and the window hours away.**

> **The order is: prove the replacement, then destroy the original. Never the reverse, and
> never on the strength of "it worked last time" — the launch command had worked last time,
> and had since stopped working.**

**A working instrument is an asset. Reaching for it is a two-step operation whose first step
costs a single command.**

---

## THE CALIBRATION CLAUSE — A CALIBRATED FIGURE CARRIES ITS ORIGIN

**Ordered R-IV.354(a); it never landed; filed R-IV.425(d).**

> **DRAFTING NOTE, stated so it is not mistaken for the ruling's text:** R-IV.354(a) itself
> did not reach this lane and is not filed in either tree or the ferry. This clause is written
> from R-IV.425's statement of the defect it exists to prevent, and from the two live cases
> below. **Spine corrects the wording if it departs from what R-IV.354(a) said.**

### The clause

> **Every calibrated figure — a threshold, a percentile, a correlation, an expectancy, a
> hit rate — is cited WITH ITS ORIGIN or it is not cited.**

**The origin is four things, all of which must be recoverable later:**

1. **The population** — the exact row set (ids, or a hash of the ids), not a description of it.
   *"The 04-22 cohort"* is a description; a description can silently re-select.
2. **The measure** — the code, at a commit, with its parameters.
3. **The input vintage** — when each series was read. **An adjusted price series is not the same
   input on two different days** (see `DEF-ADJUSTED-BARS-VS-RAW-ENTRY`).
4. **The window** — the actual first and last date used, as dates, not as "252 days".

**The test that makes this more than bookkeeping: re-running with the same origin must reproduce
the figure.** A figure that cannot be re-run from its origin is a claim about a moment, and is
cited as one or not at all.

### Why this is a verification law and not a documentation rule

**A calibration is an instrument whose output becomes someone else's input.** A threshold feeds a
gate; a percentile feeds a suppression; a correlation feeds a promotion decision. **If its origin
is lost, a later disagreement cannot be located**, and the register is left choosing between two
numbers with no way to say which is wrong. That is Law 2 in time rather than in space: two
readings that share a name are not confirmations of each other unless they share an origin.

### The two cases that forced it

**1. The 3-10 calibration (R-IV.425(b), `DEF-3-10-CALIBRATION-NONREPRODUCING`).** On a population
described as fixed, **+0.946 once and −0.326 on re-run.** Without the first run's row set and
commit, the register cannot tell whether the population moved or the measure did — and until it
can, no figure from that era is cited.

**2. The PASS 9 VIX percentile (R-IV.425(c)).** The shadow gate's thresholds were described as
*"the 5th and 90th percentile of the last 252 trading days."* **Read in the code, they were the
5th and 90th percentile of the OLDEST 252 calendar dates with a reading in a 378-day span** —
`DISTINCT ON (DATE(timestamp))` forces an ascending order, so `LIMIT 252` keeps the start of the
span; weekends count; and the date is the database session's (UTC by default), not the market's.
The Pass 9 reconstruction (R-IV.425(c)) puts today's window end at 2026-07-04. **The description and
the origin disagreed for the whole life of the gate, and the promotion review was built on the
description.** Recording the actual first and last date (item 4) would have shown it on day one.

**Instance count: 2.** Both found by re-running or re-reading, not by the figure itself — which is
the point: **a calibrated figure never announces that its origin has drifted.**
