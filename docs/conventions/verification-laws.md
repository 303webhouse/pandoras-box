# VERIFICATION LAWS — three conventions + one ledger amendment

**Commissioned:** R-IV.163. **Drafted by:** EDGE.
**Proposed path:** `docs/conventions/verification-laws.md` — path is spine's to rule, but it
must be settled before OLYMPUS-TRITON consumes §1 verbatim, since a law quoted from an
unstable path is a citation without a scope.
Ratified in full, R-IV.166, 2026-09-02 — content, §1.1 as adjudicated, and path; addendum-1 folded, R-IV.173/174.
Citable at the section anchors. **This supersedes the “proposed path” qualifier above,
which is EDGE's original text and is left unedited because the body is ratified as written.**
**§4 was applied to the ledger at filing (commit `8a52e91`)**, per its own instruction.

**Sections are individually citable:** `#null-trigger` · `#scoped-count` · `#narrow-caution`.
**§4 is an amendment instruction** to `docs/conventions/falsified-findings-ledger.md`, applied
in the same commit so the ledger is not re-dropped.

---

## 1 · NULL-TRIGGER {#null-trigger}

**A trigger that cannot fire is worse than none.** It converts an unmet condition into
indefinite waiting with no signal.

This is the **dual** of the null-verifier law, not a sub-form of it. The two cover both faces
of an unreachable predicate:

| law | predicate state | failure | what it produces |
|---|---|---|---|
| NULL-VERIFIER | always satisfied | the check cannot fail | false assurance |
| NULL-TRIGGER | never satisfied | the trigger cannot fire | indefinite silence |

Both belong to instrument design, not to the assertion law. The assertion law governs what a
lane may claim; these govern what an instrument can detect.

**Cause is not kind.** Unreachability may be *definitional* (the condition is unsatisfiable by
construction) or *data-population* (the field cannot carry a satisfying value). Both produce the
same object: a predicate that runs clean, raises nothing, and never fires.

**Instances of record:**

- *Definitional* — the Triton holdout's §8 gate, phrased "gated on remediation" and read as
  fully-graded. Fifteen rows are permanently ungradeable, so a completion monitor keyed on full
  grading waits forever. Corrected at Amendment 1B to "graded except the enumerated ungradeable
  set."
- *Data-population* — any registered condition on `chg_pct_day`, 100% NULL across 7,014 rows.
  `chg_pct_day > X` and `chg_pct_day IS NOT NULL` are both unsatisfiable.
- *Sibling on the null-verifier face* — `is_sweep` at 100% TRUE: a stratification yielding one
  cell is a check that cannot fail. One dead field produces each face, which is strong evidence
  the pair is real rather than a distinction drawn for symmetry.

### 1.1 · Registration-time law — ADOPTED WITH AMENDMENT

OLYMPUS-TRITON's proposed form: *every registered predicate declares its expected satisfaction
rate; measured 0% or 100% at registration = HALT.*

**Adopted in principle; the HALT trigger is amended.** As proposed it halts on a *value*, and a
legitimate alarm condition measures 0% at registration by design — an alarm fires on an event
that has not yet occurred. A bare 0%-HALT rule would block every forward alarm ever registered
while still failing to distinguish a working alarm from a null trigger.

The declaration must do the work, not the measurement alone. **Adjudicated form:**

1. Every registered predicate **declares its expected satisfaction rate** before the test runs.
2. The rate is **measured against the registered population** at registration.
3. **HALT on MISMATCH** between declared and measured — not on the value. A predicate declared
   at ~30% and measuring 0% is unreachable, or the population is wrong; either way the
   registration is not ready.
4. Where declared and measured **agree at 0% or 100%**, the registration additionally states
   **the state-change that would move it** and **demonstrates that state is reachable in the
   population**. Undemonstrable reachability = HALT.

Clause 4 carries the whole load. It admits the legitimate alarm — declared 0%, measured 0%,
reachable on a stated event — and catches the null trigger, where the state-change is stated
and *cannot occur*: `chg_pct_day` becoming non-NULL in a population where it never is, or a
holdout becoming fully graded when fifteen of its rows never grade.

---

## 2 · A SCOPED COUNT SHIPS WITH ITS COMPLEMENT {#scoped-count}

**Authorship: CC-QUERY.** Ratified R-IV.161.3.

**A count measured over a scope ships with its complement, or with an explicit statement that
the complement is unmeasured.**

**Mirror pair** with the unscoped-citation rule:

- *UNSCOPED CITATION* — a citation carries its scope, or it becomes a different claim.
- *SCOPED COUNT* — a scoped count carries its complement, or it invites being read as a
  population count.

Both fail identically: **a true number read against a population it was never measured over.**
Neither failure requires anyone to be careless with the number itself.

### Worked example — the k chain

1. The residue census reports **72** cash-settled index rows, correctly scoped and labeled
   ("72 interior rows"; "70 pre-08-14 + 2 inside the stall band"). Scope stated. Complement not
   stated.
2. R-IV.153 formed the expectation **k = 0**, explicitly labeled as an expectation and gated
   pending direct read. *That is the process working, not an error to assign.*
3. The holdout registration §5 filed the caveat form — "effective n = 843 − *k*, *k* unknown and
   ≥ 0" — refusing to assume a value.
4. Direct read: **k = 15** (SPX 6 · SPXW 6 · RUTW 2 · VIX 1 · RUT 0). Table-wide index
   population is **90 = 72 residue + 15 holdout + 3 future cohort**.
5. **The 72 was never wrong.** It was scoped-true, and it was read as population-true.

The complement statement costs one clause. *"72 in the residue; holdout share not yet
measured"* would have left the inference nowhere to go, and the whole chain — expectation,
caveat, correction — would not have needed to exist.

---

## 3 · NARROW CAUTION {#narrow-caution}

**A caution names the one inference it protects, or it decays like an unanchored tripwire.**

Credit: CC-QUERY's measurement; OLYMPUS-TRITON's principle.

A broad caution is unfalsifiable and unbounded, and it fails in both directions. Ignored, it
protects nothing. Over-applied, it retires a usable instrument. A caution anchored to a named
inference can be checked, and it expires when that inference is no longer possible.

Same shape as the tripwire-decay lesson: *a guard must be anchored to the window it guards.*
A caution must be anchored to the **inference** it guards.

### Worked example — the `_TOTAL` 6-call gap

- **Bare anomaly:** named callers sum 562,415 against `_TOTAL` 562,421 — gap 6.
- **First classification (EDGE, withdrawn):** "an instrument whose reading is structurally wrong
  for the question," filed alongside `id_gaps` and planner estimates. *A category assigned from
  a shape, without measuring the thing.*
- **Measurement (CC-QUERY):** the gap is five dated days — 07-15 (2), 07-16, 07-21, 08-18,
  08-27 (1 each). Forty-nine of fifty-four days reconcile exactly. Every day carrying a `_TOTAL`
  row also carries named-caller rows, and the converse. Shape reads as a tagging race at first
  call or at the day boundary.
- **Reclassification:** `_TOTAL` **is** the thing it resembles, to within 0.001%.

### The distinction the example teaches

| class | relation to the resembled quantity | remedy |
|---|---|---|
| CATEGORICALLY-NOT-THE-THING | never that quantity, at any accuracy — sequence burn is not a deletion count; a planner estimate is not a `COUNT(*)` | **DISCARD.** Precision is irrelevant. |
| ACCURATE-WITH-A-KNOWN-RESIDUAL | *is* that quantity, with a bounded characterized discrepancy | **NARROW CAUTION.** Never discard. |

Discarding class two costs a usable instrument. Trusting class one costs a false finding. **Only
one of those is recoverable.**

**Caution of record**, replacing the withdrawn broad form: *`_TOTAL` reconciles to the parts on
49 of 54 days; do not use a small `_TOTAL`-minus-named residual as evidence of an untagged
caller.* That is the only inference the discrepancy could corrupt, and it is exactly the
inference the gap invites.

---

## 4 · AMENDMENT to `docs/conventions/falsified-findings-ledger.md`

Apply in the same commit; the ledger is not re-dropped.

### 4A · Taxonomy — add a ninth sub-form

| sub-form | what it feels like |
|---|---|
| ATTRIBUTION FROM RECALL | accountability |

**Adjudication of the class-marker question (R-IV.161.1).** *EDGE has not received R-IV.161.1's
text and adjudicates the substance visible to it; if the ruling asked something narrower, this
answers the wrong question and should be re-put.* ATTRIBUTION FROM RECALL is a **sub-form of the
assertion law**, not a new class: it asserts a fact from recall rather than from the record. The
fact happens to be *authorship* rather than a figure, which changes the object and not the act.
It earns a marker because it is the one sub-form whose harm lands on another lane rather than on
a number — and because it arrives dressed as care about giving credit correctly, which is why it
does not feel like recall.

### 4B · Standing rule for this ledger

> **Every attribution in this ledger is read from the record, never from recall — including
> attributions of the catch.** A ledger whose organising premise is "another lane caught it" is
> a ledger *about authorship*, and is therefore the single document where attribution-from-recall
> does the most damage.

> **Rider — your own filings are part of the record.** Authorship confers no exemption from
> re-reading before quoting. A draft you wrote is not the artifact that was filed: it may have
> been renamed at filing, folded into another document, corrected by its executor, or never
> have arrived. Origin story, filed because it is the argument: this rider was stated in relay
> as "filed to conventions" and was never written into the file — and in the same session its
> author, holding an open read instrument, declined to assert on two of his own filed artifacts
> rather than reading them. Both were on origin the whole time, one renamed and one folded into
> its parent. **Operative corollary: your own filed artifacts are readable — read them rather
> than reporting uncertainty about them.**

### 4C · New entry

**E-11 · CC-QUERY formed the k = 0 inference**
**Claim:** "CC-QUERY's own k=0 inference is theirs and they own it."
**Artifact:** EDGE relay to spine, 2026-09-02.
**Falsified by:** CC-QUERY, from the record — the k = 0 expectation was formed in R-IV.153,
explicitly labeled as an expectation and gated pending direct read. CC-QUERY had filed the
caveat form *before* the read, endorsing EDGE's fallback.
**Sub-form:** ATTRIBUTION FROM RECALL.
**How it happened:** an ambiguous phrase in CC-QUERY's report ("the inference read a scoped count
as a population count") was read as self-attribution and restated as settled fact, without
reading R-IV.153.
**What survived:** nothing of the attribution. The transferable lesson is CC-QUERY's and is now
§2 of this document.
**Aggravating circumstance, filed because it is the point:** this occurred in the same batch that
delivered a ledger whose premise is that every entry was caught by another lane.

### 4D · Taxonomy scope — LIGHT FIX ADOPTED (R-IV.163 rider)

**Adjudication: adopt the preamble; do NOT freeze a second enumerated group.** Four grounds,
in order of weight:

1. **Two of the three are not failures at all.** Source-data error (E-10) is upstream; a fenced
   expectation overturned by measurement is *the process working*, labeled and gated exactly as
   it should have been; a finding corrected pre-write is a lane catching itself. Enumerating
   them inside a group of failure modes would assign them a category they do not belong to —
   the same category-from-shape error this document's §3 was written to correct.
2. **n = 1 per class.** Each of the three is a single instance. The two-instances-make-a-pattern
   standard applied to NULL-TRIGGER bars enumerating any of them now; freezing a group at n = 1
   would be premature settling, which the ledger itself catalogues as a sub-form.
3. **The E-10 precedent already works.** That entry stated its class and a filing rationale
   inline, carried its own explanation, and needed no group. Generalizing it costs one preamble.
4. **The gatekeeping point is the load-bearing one.** A taxonomy that gatekeeps forces entries
   to fit or be dropped — and the out-of-family entries are disproportionately the interesting
   ones. Without them the ledger is nine analyst errors and nothing else, which reads as a
   confession. With them it shows that upstream data can be wrong, that a correctly-fenced
   expectation can still be overturned, and that a lane can catch itself. That difference is
   what makes it an instrument rather than a penance.

**Preamble text, for insertion above the taxonomy table:**

> The eight sub-forms below scope to **RECALL-ASSERTION failures** — cases where a lane asserted
> something it had not read. They classify; they do not gatekeep. This ledger records falsified
> and corrected findings **regardless of mechanism family**, and an entry outside the
> recall-assertion family states its class in the Sub-form field with a one-line filing
> rationale (the E-10 precedent, now the rule).
>
> A second enumerated group crystallizes when any out-of-family class reaches **two instances** —
> the same standard applied to NULL-TRIGGER. Until then, out-of-family classes live inline.
>
> **Out-of-family count is stated with the entry total** (currently 3 of 12). If that ratio
> climbs, the taxonomy is under-covering, and the count is how anyone notices.

**Sub-form field form for out-of-family entries:** `OUT-OF-FAMILY — <CLASS>`, never `NONE`.
E-10 was filed as "NONE — SOURCE-DATA ERROR"; `NONE` reads as an omission, `OUT-OF-FAMILY` reads
as classified-outside. Amend E-10's field to the positive form when this lands.

**Numbering:** BUILD's held ledger governs. EDGE has not read that file since it was picked up
and does not assert an index for §4C's entry — it files at whatever index the held ledger
assigns, and the three out-of-family entries are identified here by content, not by number.

### 4E · Instance counting — object vs actor

An instance may be distinct by **object** or by **actor**, and both count toward the
two-instances threshold.

- **Distinct by object** — NULL-TRIGGER's two instances: a definitional gate and a
  data-population field. One lane, two different things.
- **Distinct by actor** — ATTRIBUTION FROM RECALL's two instances: two lanes, independently,
  on one event.

The actor form is arguably the **stronger** evidence for a sub-form, because a sub-form is a
claim about **how lanes err**, not about what they err on. Two lanes independently induced
into the same failure by the same ambiguous phrase demonstrates the failure is structural
rather than idiosyncratic. Where the count rests on the actor form, say so — the reading is
defensible and should be visible rather than assumed.

---

## 5 · READS DISAGREE → IDENTITY FIRST {#reads-disagree}

*Structurally this belongs with §§1–3 as a law rather than after an amendment section. It is
appended rather than renumbered, to avoid renumbering a ratified document — the same handling
the vacant sections get. Placement after §4 is deliberate and ratified (R-IV.174(b)).*

**When two lanes' reads of one path disagree, neither is preferred by seniority, recency, or
who spoke last.** The disagreement resolves in this order:

1. **IDENTITY.** Both lanes state **commit + blob SHA** of what they read. Differing SHAs
   close the question immediately — the lanes read different objects, and neither read was
   wrong.
2. **PROBE LOCALIZATION** *(CC-QUERY's corollary).* **Matching SHAs localize the fault to a
   probe, but only a re-read with a DIFFERENT instrument identifies it.** Identity proves one
   lane is misreading; it does not say which, and re-running the same extractor cannot tell
   you. Change the instrument, not the effort.
3. **CONTROL DISCIPLINE** *(CC-BUILD's law).* **A control tests the same proposition as the
   claim.** Existence cannot discriminate presence: confirming a file exists says nothing
   about whether a section within it does.

**Worked example.** Two lanes read one path and reported a five-row patch table and an empty
section. Blob SHAs matched — `13679c0a…`, commit `8b0c25f` — so the object was identical and
the fault was a probe. The probe was a range-terminated extractor (`sed -n '/heading/,/^$/p'`)
that stopped at the blank line immediately after the heading and printed a two-line window;
the table six lines below was never in range. A re-read with a different instrument
(`grep -A 14`) identified which lane was misreading. **The output was an artifact of the probe,
reported as a property of the file** — and it had become an instruction to reconstruct a table
that was already there, which would have produced a duplicate.

The block that held pending identity is what prevented the edit. That is the law's purpose:
not to determine who is right, but to stop an edit until the object is known.
