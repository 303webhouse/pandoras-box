# Board conventions

Rules that generalize past the incident that produced them. Each entry names its origin
and, where one exists, a worked example — a convention without a worked example is a
slogan.

Three laws live in `verification-laws.md` — NULL-TRIGGER (`#null-trigger`) · A SCOPED
COUNT SHIPS WITH ITS COMPLEMENT (`#scoped-count`) · NARROW CAUTION (`#narrow-caution`).
The sub-form taxonomy lives in `falsified-findings-ledger.md`. Operational conventions file
here; laws file there.

---

## A header states settled buckets only

**R-IV.136(c), generalized. Two instances.**

Where a series is bucketed by period, a header count describes **settled** buckets. The
current bucket is **PARTIAL by default, not by exception** — it is incomplete by
construction until its period closes, and a reader must not have to infer that from
context.

This is not a caveat to add when someone notices; it is the default state of the newest
bucket in every such rendering. A header that silently includes a partial bucket
understates or overstates without ever being wrong on its face, which is why it survives
review.

---

## A PERIOD AVERAGE IS NOT A DAILY BAND

**EDGE-authored. Worked examples: ARTEMIS_LONG, crypto_scanner.**

Expected-rate bands derive from **observed daily distributions**, never from a period
total divided by its days. Below the n-gate they render **INSUFFICIENT**, never a number.

A period average and a daily band answer different questions, and the average's narrowness
is an artifact of aggregation rather than a property of the series. Dividing 622 rows by
their 41-day span yields ≈15/day and looks like a band; the days themselves ran
`20 · 5 · 10 · 23 · 13 · 12 · 30 · 11`. **One of eight days fell inside the derived band**,
with a 6× spread across the range — not a band with outliers, a band that fails to
characterize the series it claims to describe.

**Worked examples**

- **ARTEMIS_LONG** — band ≈15–20/day, derived as a period average from 622 rows over
  07-03 → 08-17. Measured d0–d7: `20 · 5 · 10 · 23 · 13 · 12 · 30 · 11`. **1 of 8 in
  band.** WITHDRAWN by its author.
- **PULLBACK_ENTRY, CTA arm** — band ≈7–16/day; observed `17 · 20 · 17`, all above.
  Flagged same class.
- **crypto_scanner** — the inverse failure, and the reason this convention has teeth: a
  rate stated without its distribution cannot tell a live emitter from a dying one. Its
  daily counts decayed `161 → 93 → 47 → 14` before stopping entirely; any period average
  over that window would have described none of those days.

Both re-derivations live in SPEC-01's watermark work, from observed daily distributions,
n-gated.

**Why it matters beyond tidiness.** An expected-rate band is the instrument that decides
whether an absence is a defect. A band that does not characterize its series will call a
healthy day anomalous and a dead day normal — and per the absence law, *an absence dates
nothing until you establish the expected event rate across it*. A wrong rate is worse than
no rate, because it licenses a conclusion.

---

## SCOPE BY A COLUMN THAT SPANS THE WINDOW

**R-IV.151(b). Worked example: the Triton element census.**

A column populated from date X **cannot scope a query whose window opens before X**.
Absence seen through such a filter is a **population-boundary artifact, not a
measurement** — the rows are there; the filter cannot see them.

This is inference-from-absence, mechanized. The query returns a smaller number, no error,
and every downstream reader takes the shortfall for a finding about the world.

**Worked example.** `source` was populated from 2026-07-21. Filtering
`source = 'footprint'` returns **148 of 558 rows (27%)** — reading four months of live
history as absent. `strategy` and `signal_type` span the full window and return **558**.
Same population, same question, three columns; two answer it and one reports a boundary.

**The check, before any scoped query is trusted:** establish that the scoping column is
populated across the whole window, not merely present in the schema. A column's existence
says nothing about its coverage, and `NOT NULL` on new rows is compatible with NULL on
every old one.

Kin to the absence law — *an absence dates nothing until you establish the expected event
rate across it* — and to the vacuous-column family, where a filter that matches nothing
runs clean and returns something shaped like an answer.

## AN AMENDMENT CITES THE BYTES IT CHANGES

**R-IV.162(e).**

Every **replacement** quotes the exact text it replaces, verified against the filed blob at
cut time. Every **addition** declares ADDITION and names its insertion point by quoted
neighbor text. **Bare section numbers are not anchors.**

**Worked example.** Three amendments in one week — §4 (R-IV.138) · §6 (R-IV.145) · §8
(Amendment 1B) — were cut against a section numbering the filed artifact never had. Each
converted a replacement into a stop or an improvised insertion: §4 had nothing to replace and
forced a restructure, §6's clause text never arrived and the section was opened as a
placeholder, §8 did not exist and the gate was applied as an addition with the substitution
flagged on its face.

The failure is not that the amendments were wrong — their content was correct every time. It
is that a bare section number cannot be verified before the cut, so the mismatch surfaces at
apply time in the receiving lane rather than at authoring time in the sending one.

Origin: R-IV.162.


## A GATE VALUE NAMES ITS TREE

**R-IV.187(e), spine-authored.**

Every fingerprint states **which bytes it hashes** — the working-tree file, or the git blob.
**For a CRLF-bearing file these are different numbers for identical content**, and a gate
quoted without its tree is a value that will fail against a correct object.

Equality between the two is **proven by normalization round-trip, never assumed**: strip the
CRs from the working-tree bytes and the result must equal the blob byte-for-byte.

**Worked example — the five-artifact filing of 2026-09-02.** Three `.md` files were already
LF, so working-tree and blob hashes agreed (`3c478c9b` · `b60d31af` · `beb1eabd`). Two JSONs
carried CRLF and diverged: `rh_crosscheck.json` gated at `8ae7405a` / 33,313 B in the working
tree and landed as `beeb0927` / 31,500 B in the blob; `rh_unit_attribution.json` `15bd1bac` /
3,436 → `c4a16e1c` / 3,285. CR-stripping each working-tree file reproduced its filed blob
exactly, which is what turned an alarming hash mismatch into a stated convention. The repo is
uniformly `i/lf` with `core.autocrlf=true`, so a Windows checkout restores CRLF and the
working-tree gate returns.

**Corollary on instruments.** The CR count itself must be measured with an instrument that
counts *characters*, not lines: `grep -c $'\r'` reports matching lines and gave 123 on a file
containing zero CRs. `tr -cd '\r' | wc -c` is correct. A gate value is only as good as the
probe that produced it.

**STRENGTHENED, R-IV.303(e): THE AUTHOR STATES THE TREE.**

Checking both forms is the receiver's safety net, not the protocol. **The lane that publishes
a gate says which tree it names — raw or LF-normalised — on the manifest, every time.**

**Worked example, 2026-09-06/07, two artifacts from the same lane in two days:**

| artifact | gate | tree it named |
|---|---|---|
| Moby Dick census | `3bbddd58` | **LF** (raw and LF were identical — the file had no CRLF) |
| first market read | `5f3da161` | **RAW/CRLF** (its LF form is `19bfcdb8`) |

**Neither was wrong, and that is the problem.** A receiver who assumes either convention is
right half the time and reports a dead gate the other half — and a dead gate sends the
publishing lane to re-stage a file that was correctly staged, which is the cost already
recorded under *A NEGATIVE FINDING STATES ITS SEARCH SCOPE*.

**The receiver still checks both** — that is what caught this — **but a value published
without its tree is an incomplete measurement**, in the same way a length published without
its unit is.

## DOCUMENT CONTENT TRAVELS BY FILE

**R-IV.202(d).**

**Never by `python -c`, never by an unquoted heredoc.** Shell metacharacters inside document
text are **data, not syntax**, and every layer between the author and the file is one
more chance for a layer to disagree about which it is looking at.

Write the content to a file, then let the file do the writing: `python script.py`, not `python -c "..."`. A
quoted heredoc is safer than an unquoted one but still passes the body through the
shell's here-document handling, which is enough to lose a backslash.

**Three instances in one session, 2026-09-02, none of which reached origin:**

| what was meant | what was written | caught by |
|---|---|---|
| the two-character escape `\r` | a real CR byte | the both-trees hash check from A GATE VALUE NAMES ITS TREE |
| the same escape, in the repair | a real CR byte again, so the fix was a silent no-op | an assertion that no CR may survive |
| the term `baseline_sessions` | nothing — the shell ran it as command substitution and wrote the empty result | reading the rendered paragraph |

The third is the sharpest. **The shell did not error.** It ran a command, got nothing,
and wrote nothing where a term belonged. A silent substitution is indistinguishable from
text that was never typed, and it survives any check that greps for what should be
absent rather than reading what is present.

**The durable forms.** Build shell-significant characters from character codes when they
must appear in content — `chr(96)` for a backtick, `chr(92) + chr(114)` for the escape — and assert the
postcondition **positively**: not *"the wrong thing is gone"* but *"the right thing is
present, exactly once, and nothing else changed."* Where it applies, the round-trip is
strongest: undo the edit and the result must equal the source bytes.

A fourth instance occurred while authoring this very entry, and its assertions caught it
before the file was staged: a placeholder was substituted into a slot that already
carried backticks, producing a doubled pair. **An entry about quoting is written with
placeholders for every shell-significant term, and checks each one after writing.**

A fifth instance, POSITIONS' (R-IV.281(d)), extends the rule past the shell: `subprocess.run(text=True)`
under the Windows locale **decoded successfully and produced mangled em-dashes.** Nothing
raised. The text stayed plausible — it simply stopped matching its anchors, and only an
assertion caught it.

**So: explicit UTF-8 on every subprocess read of document text.** This instance is the
sharpest of the five, because the other four corrupted content at a point where something
*could* have failed. **A successful decode into the wrong characters cannot fail**, which
puts it in the null-verifier family rather than the quoting one: the operation reports
success and the damage is downstream, in a comparison that quietly finds nothing.

Kin to *rendering catches what diffs miss* — all five were invisible in a diff and
obvious on the rendered line.


## A DEFECT REGISTERED BY RULING IS FILED IN THE SAME COMMIT AS THAT RULING'S OTHER FILINGS

**R-IV.263(b).**

**A DEF name cited twice with no file is a phantom by definition.** Not by judgement,
not on review — by definition, because the second citation proves the name is being
used as a reference and the missing file proves there is nothing to refer to.

Registration and filing are one act. A ruling that registers a defect and files three
other artifacts in the same breath must file the defect too, or the name enters
circulation with nothing behind it. **The phantom sweep re-runs monthly** and is
mechanical: regex the DEF-shaped names out of every document, index the filenames
case-insensitively, and difference the sets.

**WORKED EXAMPLE — the sweep of 2026-09-05, at HEAD 7dbed6b.** Thirty-four true
phantoms. Three were **load-bearing on a registered window**: a name cited inside a
pre-registration, doing argumentative work, with no artifact anywhere to check it
against. That is the failure mode — not untidiness, but a citation that cannot be
verified because its referent does not exist.

**PHANTOM DOES NOT MEAN UNADDRESSED, and the distinction is the useful part.** Of the
five phantoms in this lane's domain, two were already resolved in substance and had
simply never acquired an artifact: `DEF-BARS-NO-PROVENANCE` was **closed in code** at `773e7a8`, and
`DEF-DB-VOLUME-CEILING` was **superseded** by a registration that holds its content. A phantom is a
bookkeeping fact about the repository, not a claim about the defect. Stub it, record
what its citations say, and mark plainly whether anything is actually open.

**Two probe disciplines the same sweep demonstrated**, both worth carrying:

- **Case-insensitive filename matching.** The first pass matched only uppercase
  `DEF-` while briefs are named lowercase, mis-scoring **18 registered defects as
  phantoms** — including two with 23 citations each. The same family as the
  range-terminated `sed` range that made a present table look empty.
- **Report the complement.** The raw set difference was 58; 24 were probe artifacts or
  misclassifications. Publishing 58 would have been a scoped count shipped without its
  complement, and the number that survived scrutiny is 34.

**Concurrency note, because the sweep hit it:** the repo is written while it is swept.
`DEF-SOXS-PRICE-DISCONTINUITY` was filed *between* the sweep's first and last pass and moved from phantom to
filed mid-run. **A sweep therefore states its vintage and its HEAD**, and is true as of
that instant and not after.


## A LANE STAGES A SETTLED MANIFEST

**R-IV.271(b).**

A lane hands over **one table**: paths, gates **measured at stage time**, and **no edits
to any listed file until the receiving lane confirms filing**. The receiver picks up from
the manifest and from nothing else — not from a directory listing, not from what happens
to be on a ferry path.

**Supersession is announced, with the dead gates named.** CC-QUERY's form is the model:
when revised stubs replaced earlier ones, the superseded values were stated as dead rather
than left to be discovered as mismatches.

**Worked example — 2026-09-05, why this rule exists.** A pickup of five artifacts
returned **two gates that matched**:

- Two gates named in the ruling matched **no file on any reachable path**; they had been
  superseded before pickup, and the supersession was not announced.
- Two files were present carrying **neither** stated gate.
- One file changed **during the task** — 5,206 B on first read, 8,884 B minutes later.
- One file in the source tree was **newer than the copy already filed**, so the filed
  copy was stale on arrival.

**None of that is anyone's error.** Each lane was doing correct work on its own artifacts.
**The failure is concurrent editing of a set that is simultaneously being read** — the
same shape as a sweep whose subject is written mid-run, which is why a sweep states its
vintage and HEAD.

**The receiving lane's obligation follows from this:** re-hash at apply time, never trust a
gate measured earlier in the same session, and **file only what gates — reporting the rest
by address rather than guessing which version was meant.** A gate that has moved is not a
mismatch to be resolved by judgement; it is a question for the staging lane.


## ONE AUTHOR PER FILE

**R-IV.279(b).**

**While a file sits under a lane's manifest, only that lane edits it.** Another lane's
facet is **RELAYED to the author as text, for the author to insert** — never appended
directly to the file.

**This is the companion to *A LANE STAGES A SETTLED MANIFEST*, and the two divide cleanly:**
that rule governs the **handover** — do not read a moving target. This one governs the
interval **between** handovers — do not be the thing that moves it.

### Worked example — 2026-09-05, two lanes annotating two files

Two DEFs under POSITIONS' manifest were annotated by CC-BUILD **and** by POSITIONS on the
same day, neither lane seeing the other's edit until the gates disagreed. What this lane
measured on `DEF-ACCOUNT-LABEL-DUP.md` alone:

| observation | gate / size |
|---|---|
| first pickup | 5,206 B |
| changed mid-task, same day | `66ca733f` · 8,884 B |
| after this lane appended its own facet | `3cd3fb92` · 9,979 B |
| gate named in the ruling | `c6aa2ba8` · 13,577 B |
| transient, caught mid-write | `ac5f1c85` |
| settled | `de40dafe` · 15,651 B |

**Its sibling moved the same way**, and at one point **neither copy was a superset of the
other**: POSITIONS' was smaller (8,379 B) than this lane's (8,805 B) while each held a facet
the other lacked. **Filing either one verbatim would have silently destroyed a measured
finding.**

### What it cost, stated plainly

**Two gates named in a live ruling were dead before the ruling could be executed.** A
filing had to stop, watch the files across three consecutive samples to prove they had
settled, and then justify filing at a gate the ruling did not name. **None of that is
anyone's error** — both lanes were doing correct work on their own findings.

**And the resolution was itself the churn.** The gates moved *because* POSITIONS pulled
this lane's facets from origin and merged them. **The fix and the symptom were the same
event**, which is exactly why it cannot be detected as a problem while it is happening.

### The rule, restated as the thing that should have happened

**CC-BUILD's facets should have traveled to POSITIONS as text**, and POSITIONS should have
inserted them. One writer, one manifest, one gate that means something. **A gate is a
promise about a file's contents; a second author makes that promise unkeepable** — not by
breaking it, but by making it undecidable which lane's copy the promise was about.


## A NEGATIVE FINDING STATES ITS SEARCH SCOPE

**R-IV.281(a).**

**A negative is a property of where you looked, never of the thing sought.** Report it with
the scope attached — the paths, the patterns, the window — so a reader sees the hole
instead of inferring an absence.

**Worked example — 2026-09-05.** This lane reported a staged census as *"not on any
reachable path"* **three times**. The sweep was by full content hash, which felt
exhaustive, over `C:\th-build`, `C:\trading-hub` and Downloads. **The ferry directory
`C:\temp\cc-query-handoff` was not among them.** The file was there the whole time, gate matching
exactly — and this lane had already filed **sixteen** artifacts from that same directory.

**The cost was not the wasted search.** The finding was relayed as a property of the
artifact, so another lane was sent to re-stage a file that was correctly staged, and a
ruling was written around a failure class (*said-staged-wasn't*) that had not occurred.
**A mis-scoped negative does not merely fail to find a thing; it manufactures a different
problem elsewhere.**

**Probe-coverage family, search-boundary form.** Its siblings are a `limit=` that is not a
parameter of the endpoint, a `cut -c` truncation read as a truncated document, and a
`grep -c` counting lines where characters were meant. **Each reports a property of the
instrument as a property of the subject** — here the instrument is the set of places
searched.

**A fourth sibling, offered under R-IV.286(a) and found while authoring against this very
rule.** A guard was written to prove an edit had NOT moved a gated document body. It
extracted that body as *"from the start marker to the following heading"* — and the edit
had just inserted new prose immediately before that heading. **The guard hashed the body
plus the insertion and reported the body had moved.** It had not.

**The instrument's window was defined relative to a landmark the edit relocated.** A
false positive, caught because it fired before the write rather than after — but the same
construction returns a false NEGATIVE the moment an edit lands *inside* the window instead
of beside it. **A verifier whose scope is defined relative to the thing it verifies is
measuring an unknown region**, and it is only luck which direction the error runs.

**The fix was to anchor the window to the structure being protected** — the blockquote's
own line prefixes — rather than to whatever happened to follow it.

**The operational form: when something cannot be found, name the paths searched before
concluding anything.**


## FERRY ARTIFACTS ARE NAMED BY LOCAL DATE

**R-IV.281(b), from CC-QUERY.**

**A staged file's name carries the LOCAL date it was written. The UTC vintage lives inside
the document**, on its face, where it can be read precisely.

**Worked example:** `2026-09-06-MOBY-DICK-CENSUS-PHASE0.md` was written **2026-09-05 18:13 MDT**, and its own
face states the in-DB vintage `2026-09-06 00:11:34.310740+00`. The name and the vintage differ by a day
and **both are correct** — they are answering different questions.

**Existing names stand. Renaming for cosmetics creates dead gates**, which is a real cost
paid to fix an unreal one: every ruling, manifest and chain line that cites the old name
now cites nothing. **The name is an address, not a claim about time** — and the document's
face is where a time claim belongs.


## A LIVENESS PROBE IS A CONSUMER THAT FAILS WHEN THE SOURCE DIES

**R-IV.293(e), from CC-QUERY.**

**Never a counter that measures traffic.** A probe must be something that **stops working**
when the thing it watches stops working. A counter keeps counting.

**Worked example — the UW bar outage, 2026-09-05.**

| instrument | what it read across the outage | dated the onset? |
|---|---|---|
| `ohlc_bars` burn counter | **1,689–2,018 calls/day, straight through** | **NO** |
| the grader (`get_ohlc`, no fallback) | wrote 962 / 9 / 1,862 / 573 rows, then **could not write** | **YES** |

**The counter was not broken and it was not lying.** Calls really were being made at the
usual rate — **and every one of them was failing into a silent fallback.** *Traffic
continued; service did not.* **A metric that cannot distinguish those two is not a health
signal**, whatever it is named.

**The grader dated the outage because it CONSUMES the thing.** No fallback, so no bars means
no rows, and **the absence of rows is the measurement.** It was never designed as a probe;
it became the only one available because it was the only consumer that could not paper over
the failure.

**The rule this yields for anything built to watch a source:**

- **A probe with a fallback is not a probe.** The fallback is exactly the mechanism that
  destroys the signal — see `DEF-UW-OHLC-DEAD`, where a working fallback hid a dead primary for
  days.
- **Count failures, never volume**, and only where a failure can actually surface.
- **Prefer a real consumer over a synthetic ping.** A synthetic ping tests the endpoint; a
  real consumer tests the endpoint *as this system uses it*, which is the question that
  matters and the one the SMH read answered.

### Instance 2 — the same shape, one day later, in a supervision task written to prevent it

**R-IV.295(c).** The grader-precondition brief's T3 said *register the grader in
`signals_freshness`*. That module reads **every** age from `SELECT source, MAX(created_at) FROM signals GROUP BY source` — and **the grader never writes a
signals row.** The registered class would have carried no age forever, so its staleness
branch could not fire.

**A probe that reads a table the source never writes cannot fail when the source dies.**
Same law as the burn counter, arrived at from the opposite direction: there the instrument
measured the wrong quantity, here it would have measured the right quantity **in a place
the quantity never appears.**

**What makes it worth recording is where it was found.** Not in legacy code — **in a task
written to add supervision, in a brief written to remove instruments that cannot fail,
reviewed and ruled CC-ACTIONABLE.** It was caught at build time by reading the query the
module actually runs. **The defect class survives being written down by people actively
looking for it**, which is the case for verifying at the point of construction rather than
trusting review.

**Kin to the null-trigger law.** There the trigger could not fire; here the probe cannot
fail. **Both are instruments that report success by construction**, and neither can be
caught by inspecting its output — only by asking what it would do if the thing it watches
were dead.


## APPENDS GO THROUGH WHOLE-FILE REWRITES, AND NEW FILES ARE NORMALIZED TO THE TREE'S CONVENTION

**R-IV.317(c), from CC-POSITIONS.**

**The creating tool's default is not the repo's.** A file is written in whatever the tool
emits; the tree has its own convention; **nothing reconciles the two unless someone does.**

### Two shapes, and only one of them is visible

**1 — A new file in the wrong convention.** Measured on this lane's own work, 2026-09-07:

```
NEW this session (Write tool / heredoc)        neighbours in the same directories
  instrument_class.py       uniform LF           stable_jobs.py    uniform CRLF (239)
  job_runs.py               uniform LF           main.py           uniform CRLF (2,172)
  market_calendar.py        uniform LF           test_webhooks.py  uniform CRLF (40)
  test_market_calendar.py   uniform LF
  028_job_runs.sql          uniform LF
```

**Six of seven new files landed LF beside uniform-CRLF neighbours.** The seventh,
`poller_pause.py`, reads CRLF — **because it has already been through git**, which is the
tell: the tree's convention is applied on checkout, so a file only looks conformant after
it has made the round trip. **Until then the working tree is inconsistent with itself and
nothing complains.**

**2 — An append in a different convention from its base.** `cat >>` writes LF; if the
base is CRLF the file becomes **MIXED**, which is the shape that actually breaks things.
Measured on two staged artifacts: **173 CRLF + 38 LF**, and **102 CRLF + 32 LF** — in
both cases a CRLF body with an LF appendix.

**The mixed case REQUIRES a CRLF base.** Appending LF to an LF file just stays LF, which is
why this lane's own `cat >> backend/tests/test_instrument_class.py` append produced a clean file and looked fine: **the base
had never been through git.** *The bug needs the tree's convention to have been applied
once already*, so it appears on mature files and not on new ones — the opposite of where a
reader would look.

### The rule

**Append by whole-file rewrite** — read, modify, write the whole thing in one convention —
**never by `>>` onto a file whose terminators you have not checked.**
**Normalize new files to the tree's convention at creation**, not at the next commit.

### Why it is worth a convention rather than a lint

**A mixed file's LF gate is stable and its raw gate is not.** Measured live on 2026-09-07:
two staged files read MIXED and then uniform CRLF **minutes apart**, same content, while
**the LF gate was identical across both reads.** A raw-tree gate went dead in that interval;
the LF gate did not move.

**So the damage is not corruption — it is that a gate stops meaning anything.** Two lanes
hash the same file and disagree, each correctly. Kin to *A GATE VALUE NAMES ITS TREE*: that
rule says publish which tree you measured, **this one says stop producing files that have
two answers.**


## A DERIVED VALUE CANNOT WITNESS ITS OWN INPUT

**R-IV.336(a).**

**Raw varying under a constant score is a BAND. Raw absent under any score is
FABRICATION. The payload is the only witness.**

```
raw varies, score constant   ->  BAND        working as designed
raw ABSENT, score present    ->  FABRICATION the defect
```

**A score cannot tell you which it is.** Zero is a legitimate output of most scoring bands
and also the value a fabricated reading carries; **the two are identical at the output and
distinguishable only at the input.**

### Worked example — the same lane getting it wrong twice in two days

| attempt | the inference | why it failed |
|---|---|---|
| 2026-09-08 | four factors reading exactly 0.0 must share a cause | **0.0 is the designed middle band of three of them.** A quiet tape produces it correctly |
| 2026-09-08 evening | `dxy_trend` calls `neutral_reading()` on its no-data branch, so it fabricates | **the branch exists and is not taken.** 196 distinct raw values say so |

**Both are the same error: inferring runtime behaviour from static reading, and stopping at
the first plausible mechanism.** Reading the code established that a fabrication path
*existed*. **Only the data could say whether it FIRED**, and the data said it did not — in
`dxy_trend`. It fires in `gex`, 35 of 695 readings, which no amount of code-reading would
have distinguished.

### Why this is a convention and not a note about one module

**The pattern generalises to every derived surface in this register.** A composite score, a
`max_loss`, a `coverage_ratio`, an `indicators_source` — each is a value computed from an
input, and **in every one of those cases this board has been misled by reading the output.**

**The rule that follows: when a derived value looks wrong, the question is never "what does
this value mean?" It is "what was the input, and was there one?"** If the input is not
stored, that is the finding — and it is why the sinks build stores raw payloads rather than
conclusions.

**Kin to the null-verifier law from the other side.** There, an instrument could not report
failure. Here, an output cannot report its own provenance. **Both are cured by the same
move: keep the evidence, not the verdict.**


## ORDERS ON BUILD DAYS NAME WHAT THEY DISPLACE; SLIPS ARE FLAGGED WHEN VISIBLE

**R-IV.343(d). Entered under BOTH names.**

**Two halves, and neither excuses the other.**

**Spine's half:** five read-only items were ordered onto a scheduled build day **without
stating what they displaced.** An order that adds work to a fixed day is a scheduling
decision whether or not it is written as one — **and the lane receiving it cannot weigh it
against the build unless the trade is named.**

**BUILD's half:** the lane executed all five **and did not flag the slip**, which was
visible from the first hour of the day. **A slip noticed and not reported is a slip
concealed**, however unintentionally; the schedule was public, the day was finite, and
nothing was said until the deploy was asked for.

### The worked example

**2026-09-09 was the frozen day before a scheduled Thursday batch.** It went to a webhook
401 read, two corrections of this lane's own findings, a conventions entry, two defect
corrections, two registrations, and a liveness check. **Every one produced something.** The
eight-item batch was not started, and **the two report observations scheduled for that day
— the deafness test and T5b's A/B/C — were not run.**

**Thursday's push shipped two of eight items.**

### The rule

- **An order landing on a build day names what it displaces**, or states that it displaces
  nothing.
- **A lane that sees a slip reports it in the turn it becomes visible**, not when the
  deliverable is called for.
- **Neither is satisfied by good work on the substituted items.** The findings from that
  Wednesday were real and are filed; **they are not a defence, because the question was
  never whether the work was worth doing — it was what it cost.**

**Kin to the register's oldest habit:** *state the scope with the finding.* Here the scope
is a day, and the cost is the thing that went unstated.
