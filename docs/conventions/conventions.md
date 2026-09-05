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

Kin to *rendering catches what diffs miss* — all four were invisible in a diff and
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
