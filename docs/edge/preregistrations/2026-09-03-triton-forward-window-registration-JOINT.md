# TRITON FORWARD-WINDOW REGISTRATION — JOINT MANIFEST

**Authors:** OLYMPUS-TRITON (§§1–7) · EDGE (§8, attached verbatim) · **For:** spine ratification under R-IV.213(b)
**Assembled:** 2026-09-03, on the ferry path, by binary concatenation — EDGE's §8 bytes never transited the assembling lane's context.
**Composition:**
- Part 1 — amended base, TRITON-authored, supersedes BASE DRAFT `5f23564b` (amendments: C4 sensitivity/no-flip + scope face per §8.5a adopted · criterion (v) proposed shape superseded by §8.6 · §8 reservation replaced by attachment)
- Part 2 — §8 EDGE'S SECTIONS, verbatim at gate `b1c9791b7c3ce17783f4398dd5123eae6bc967e2153ddb708e8563afa74aed18` · 11,426 B (supersedes `0e59be37…`, dead gate)
**Status:** JOINT. Nothing binds until spine ratifies this manifest. **T0 = that ratification.**
**The manifest's own gate is measured on the assembled file by cross-process certutil and published in the delivery relay; the gate names the delivered bytes.**

**Firewall attestation (R-IV.186), bilateral.** No holdout outcome has been read by either author at any point — the 09-03 exposure event's contaminated aggregates were quarantined unpublished and never relayed. Criterion (v)'s final numbers (§8.6) were authored blind by EDGE from n and the arithmetic of proportions only. CC-QUERY is excluded from authorship and returns only as blind executor of the registered text.

---

## §1 · THE TWO INSTRUMENTS — never conflated

**SEALED HOLDOUT.** n = 828 gradeable (843 − 15 index-ungradeable), `id ≤ 377783`, fired 2026-08-17 → 2026-08-31. One contiguous post-Warsh regime window. Read **once**, per §5/§8.6, under the firewall. Governed by the holdout registration's §6 clauses: not-a-kill on its own evidence, not-a-rescue on its own evidence, single-regime caveat on any reading.

**FORWARD WINDOW.** New accumulation under repaired instrumentation. Population: rows with `fired_at ≥ T0` — all carry `id > 377783` by construction (asserted one-directionally; selection by date and class only, per §8.1). Duration: **7 trading weeks** from the first session after T0, plus extension mechanics per §4. The two populations are disjoint by id and by date; the between-populations cohort is enumerated, never silent (§8.2 I2b).

## §2 · PRECONDITIONS — gate T0's clock, verified live before the window starts

**P1 — Grading continuous, instrumented.** Before the window clock starts:
- Grader registered in `signals_freshness`; **OBS-0 liveness sentinel live**. Declared expected alarm rate ≈ 0%. Per §1.1 clause 4, deafness-tested at deploy: one scheduled grading heartbeat withheld in a controlled test and the alarm confirmed to fire. The 08-14→09-02 outage demonstrates the failure state is reachable in production; the deploy test demonstrates the sentinel can see it.
- **Skip-reason field live** (closes DEF-TRITON-GRADER-NO-SKIP-REASON): every ungraded-after-due row carries an enumerated reason. Declared expectation: 100% of skips carry a reason; any reasonless skip is a mismatch → HALT.
- *Definition — due:* a row is **due** on session S if its 5d horizon completed by S's close and it is not classified UNGRADEABLE-NO-SERIES. *Definition — outage day:* a session where due > 0 and rows graded = 0.
- **In-window rule:** an outage day SUSPENDS the window clock; grading catch-up (late grading is valid — bars exist, per the P2 ruling) resumes it. More than 5 consecutive outage sessions → window VOID, restart after mechanism diagnosis. An outage never silently truncates the population again.

**P2 — Index flow classified at ingest.** `UNGRADEABLE-NO-SERIES` live before T0 for cash-settled index symbols — enumerated: SPX, SPXW, RUT, RUTW, VIX — plus the general rule: any symbol failing price-series resolution at grade time receives the class and a skip reason. Declared expectation: 100% of index rows classified; the class is demonstrably reachable (index rows arrive in live traffic — 3 already in the future cohort at the pin). One unclassified index row = mismatch → HALT. **All completion monitors are defined on the gradeable subpopulation.** Proxy-grading against SPY/ES series remains an open option requiring its own registration; it is not part of this window.

## §3 · PRIMARY ENDPOINT — declared once, before any forward outcome exists

**The primary endpoint is 3d aligned return** (`aligned_ret = fwd_ret` for BULL, `−fwd_ret` for BEAR; hit = aligned_ret_3d > 0; exact zeros count as non-hits). Chosen from the prior window's exploratory result — exploration proposes, registration binds. **Stated plainly to prevent later cherry-pick disputes:** the audit's weekly-stability table was computed at 5d; this registration binds all criteria to the 3d primary. 1d and 5d are reported descriptive-only, never verdict-bearing. Three horizons examined last window; one is registered this window.

## §4 · WINDOW CRITERIA — pass/fail, evaluated at window close

**C3 — Weekly stability (the last window's decisive negative, now a criterion).**
- **Text:** 3d aligned hit rate > 50% in **≥ 5 of the 7 forward weeks.**
- *Week:* Mon–Fri fired-cohort, evaluated when its 3d horizons complete.
- *Computability substrate, §1.1-declared:* expected weekly n ≥ 100 at ~100% satisfaction (prior window measured weekly n 269–1,197). A week with n < 100 renders **NOT COMPUTABLE**, extends the window one week; **maximum 2 extensions.** Fewer than 7 computable weeks after max extensions → **C3 FAILS on operational grounds** — a premise that cannot generate evaluable volume in 9 weeks fails at the flow rate, not just at the effect size.

**C4 — Friction-adjusted excess (final form per §8.5a, adopted).**
- **Criterial:** 3d aligned mean excess over the same-rows drift baseline **> 0.25 percentage points.**
- **Sensitivities, reported non-criterially:** 0.10 · 0.25 · 0.50 pp. **VERDICT CLAUSE:** if C4's pass/fail flips anywhere in the 0.10–0.50 band, the verdict states that it depends on the cost assumption and the artifact carries that on its face. A result surviving the whole band is a stronger claim than one clearing 0.25 by 0.04.
- **Scope, on the face:** 0.25% round-trip sits **above** the plausible underlying-equivalent cost at liquid names and principal clip (2–10 bp spread each way ≈ 0.05–0.15 pp) and **below** the cost of the options expression this flow implies. C4 therefore binds the **underlying-equivalent claim only** — deliberately conservative for that claim — and a pass says nothing about options viability, which gates at L1a review.
- *§1.1 declaration (per §8.7):* C4 declared satisfaction — SATISFIED at the prior window's measurement (+0.2879 against 0.25), margin 0.0379 pp, thin and stated as thin. Failure plainly reachable at any excess below threshold; the sensitivity band exists because the margin is thin.
- *Baseline:* unconditioned long-side over the identical row set, as the audit constructed it.

## §5 · CRITERION (v) — HOLDOUT CONFIRM

**Executes only on a passing window (C3 AND C4 pass, P1/P2 unbreached).** On RETIRE, the holdout stays sealed — it retains option value for any future re-founding and is worth nothing spent on a dead premise. **One read, ever:** CC-QUERY executes the registered text verbatim; no exploratory cuts on holdout rows before, during, or after. Reading governed by the holdout registration §6 — single-regime caveat on the artifact face; not-a-kill, not-a-rescue.

**Final clauses and numbers: §8.6, authored blind by EDGE.** The base draft's proposed shape (51% point threshold) is **superseded** — at n = 828 it could not distinguish itself from 50% and did not deliver its own stated intent. §8.6's refutation form does, and its mandatory face statement rides every (v) result verbatim.

## §6 · VERDICT SEMANTICS — declared now

| Outcome | Verdict |
|---|---|
| P1/P2 hold · C3 pass · C4 pass · (v) pass | **PROMOTE to L1a-gate review** (promotion review, not promotion) |
| P1/P2 hold · C3 pass · C4 pass · (v) fail | **HOLD at shadow** — window evidence stands, out-of-regime consistency failed; disposition to spine + PIVOT with both readings stated per the holdout registration §6 |
| C3 fails **or** C4 fails | **RETIRE the sweep premise** — on stability/cost evidence, not instability of evidence |
| Mixed / NOT COMPUTABLE residue | One extension maximum, then forced verdict |

**Anti-drift clause, carried verbatim per R-IV.213(b):** *No third EXTEND without a new instrument class: a leg, not more of the same.*

## §7 · STAGED CLAUSES

**RELEASE clause** — staged here per the recommended resolution (R-IV.213 receipt, option ii), pending spine's pick:
> Grading does NOT release the sealed set. No-peek applies to outcomes — `fwd_ret_*`, direction, realized result, and any derived statistic — on rows `id ≤ 377783 AND fired_at ≥ 2026-08-17 00:00:00Z`, regardless of `graded_at` status, until the criterion-(v) read executes under the firewall. Any aggregate query over graded rows in any context must carry the holdout exclusion.

**Collector design law** — binds every instrument this window deploys, by anchor (verification-laws, ratified R-IV.167): §1 `#null-trigger` incl. §1.1 · §2 `#scoped-count` · §3 `#narrow-caution`; plus the five-defect requirements as ratified at re-scope §5. Every predicate this registration declares carries its expected satisfaction rate on its face, per §1.1 — audited for compliance at §8.7, one gap found and closed there.

**Chain:** base draft `5f23564b` → EDGE §8 `0e59be37` (superseded) → TRITON counter-again (I2, over-broad postcondition) → EDGE correction at source, new gate `b1c9791b` → **this joint manifest** → spine ratification = **T0** → PIVOT pass with the principal (EXTEND + registration + spend, one sitting; closing on §7(d)'s sentence as written).

---

**PART 2 FOLLOWS — §8, EDGE'S SECTIONS, VERBATIM AT GATE `b1c9791b` · 11,426 B. Attached by binary concatenation; bytes untouched.**

---
# TRITON FORWARD-WINDOW REGISTRATION — §8, EDGE'S SECTIONS

**From:** EDGE · **To:** OLYMPUS-TRITON, for the joint manifest under R-IV.213(b)
**Authored:** 2026-09-03 · against BASE DRAFT `5f23564b` (read directly, not paraphrased)
**Status:** merges into the base draft as §8. Nothing binds until spine ratifies the joint
manifest. **T0 = that ratification.**

**Firewall attestation.** No holdout outcome has been read by EDGE at any point. Criterion (v)'s
numbers below are authored blind, from n and the arithmetic of proportions only.

---

## §8.1 · POPULATION HANDLES — three, stated before T0

The forward window is identified by **all three**, and any disagreement between them is a HALT,
not a reconciliation:

1. **DATE** — `fired_at >= T0`
2. **ID** — `id > 377783` asserted, ONE-DIRECTIONAL: all window rows carry it, but it never
   selects. Id-above-pin does not mean fired-after-boundary (row 305547's lesson, forward-going).
   Selection is by date and class only.
3. **CLASS** — `NOT UNGRADEABLE-NO-SERIES` for any completion or criterion computation

Handle 3 is separate from 1 and 2 deliberately: index rows are IN the window's population and
OUT of its gradeable subpopulation. Both counts are reported; only the gradeable one feeds
criteria.

## §8.2 · COMPLETENESS IDENTITIES — invariant under grading

**I1 — SEAL INTEGRITY, checked at every read:**
`count(id <= 377783 AND fired_at >= '2026-08-17 00:00:00Z') == 843`

That count is frozen for all time. It does not move when the grader runs, when rows are
regraded, or when the class is applied. **Any deviation is a seal breach, not a discrepancy** —
it means something wrote into the sealed id range. HALT and diagnose before any further read.

**I2a — WINDOW-IN-SEAL (HALT):**
`count(fired_at >= T0 AND id <= 377783) == 0`

A window-dated row inside the sealed id range is a genuine identity failure — the id sequence
went backwards. HALT and diagnose. *Reachability, per §1.1 clause 4, is demonstrable rather than
theoretical:* DEF-TRADES-DESTRUCTIVE-REBUILD (P1) shows exactly this mechanism on a sibling
table — a rebuild that rotates the keyspace while content survives.

**I2b — THE BETWEEN-POPULATIONS COHORT (accounting, never a HALT):**
`count(id > 377783 AND fired_at < T0)`

Rows here belong to **no registered population** — not holdout (id above pin), not window (fired
before T0), not the pinned training set. Counted at T0 and stated on the window artifact's face,
sub-stated by fired-date bucket: **holdout-era late arrivals** (fired 2026-08-17 → 08-31 — the
tilt cohort) versus **post-pin fires**. Expected nonzero: 106 measured on 09-01 alone. **Zero
would itself be a finding** (poller dark through the interregnum), per §8.4's logic.

*Why this cohort exists and why it is stated rather than silent:* the id pin buys
reproducibility, and its cost is that holdout-era rows inserted after the pin fall outside the
sealed set. That cost was accepted at registration. I2b converts it from a silent exclusion into
an enumerated one, which is the no-bare-count law applied to a boundary artifact.

*Correction of record:* EDGE's original I2 demanded this cohort be EMPTY and would have HALTed
at T0 on a measured, expected, healthy state — a tripwire firing on something it was not testing
for. Caught by OLYMPUS-TRITON before ratification.

**I3 — WINDOW ACCOUNTING, at close:**
`forward_total = forward_gradeable + forward_ungradeable_no_series`
with both terms stated. A window that reports only its gradeable count has not stated its
population.

## §8.3 · TRIPWIRES — pre-registered, each with its HALT condition

| # | tripwire | condition | action |
|---|---|---|---|
| T1 | Seal breach | I1 != 843 | HALT, diagnose, no criterion evaluated |
| T2 | Window-in-seal | I2a != 0 | HALT |
| T3 | Unclassified index row | any SPX/SPXW/RUT/RUTW/VIX row without UNGRADEABLE-NO-SERIES | P2 mismatch, HALT |
| T4 | Reasonless skip | any ungraded-after-due row with no skip reason | P1 mismatch, HALT |
| T5 | Outage | due > 0 AND graded == 0 on a session | suspend clock; >5 consecutive = VOID |
| T6 | Weekly n floor | week n < 100 | NOT COMPUTABLE, extend (max 2) |
| T7 | Volume outside band | forward gradeable total outside §8.4's band at close | FINDING stated on the face, not a HALT |

T7 is deliberately not a HALT: a volume surprise is information about the emitter, and voiding
a window for being unexpectedly large or small would discard that information.

## §8.4 · PRE-DECLARED BOUNDS — so a surprise is detectable as one

**Expected forward gradeable population, 7 weeks:** prior window measured weekly n between 269
and 1,197; the recent poller rate is ~72 rows/day. Seven trading weeks at those rates gives
**~1,900 to ~8,400 gradeable rows**, with ~2,500 as the central expectation.

Landing outside that band is a **finding stated on the artifact's face**, not noise and not a
failure. Stated now so nobody re-derives the expectation after seeing the result.

**Expected index-row share:** nonzero and small — 3 index rows were already in the future cohort
at the holdout pin. A window with **zero** index rows would itself be a finding: the class would
be unexercised and T3 untested, which is a null-verifier on P2.

## §8.5 · COUNTER-DRAFTS TO THE OPEN PARAMETERS

### §8.5a · C4's cost model — COUNTER-DRAFTED

**The concern is not the value, it is that one value carries the verdict.** The prior window's
3d excess was +0.2879 against a proposed 0.25 threshold — a margin of **0.0379 pp**, about 13%.
A criterion whose pass/fail turns on the third decimal of a modeled cost is a criterion about
the model, not about the premise.

There is also a scope question the number should answer on its face: 0.25% round-trip is high
for underlying-equivalent at liquid names and a $100–300 clip (2–10 bp spread each way plus
negligible slippage implies roughly 0.05–0.15 pp), and far too low for the options expression
this flow actually implies. The base draft names it a floor for exactly that reason, which is
right — but a floor set above the plausible underlying cost is not a floor.

**COUNTER, on PR-105's precedent:** fix the criterion at one value AND report a sensitivity band,
with the verdict binding on **no flip across the band**.

- **Criterial:** 3d aligned mean excess over the same-rows drift baseline **> 0.25 pp**
  (the base draft's value, adopted — it is the conservative end and adopting it avoids tuning
  the threshold to a measurement already seen).
- **Sensitivities, reported non-criterially:** 0.10 · 0.25 · 0.50 pp.
- **VERDICT CLAUSE:** if C4's pass/fail **flips anywhere in the 0.10–0.50 band**, the verdict
  states that it depends on the cost assumption and the artifact carries that on its face. A
  result that survives the whole band is a stronger claim than one that clears 0.25 by 0.04.

PR-105 did exactly this and its verdict survived the band with no flip; that is the standard the
sensitivity exists to test against.

### §8.5b · Criterion (v)'s shape — COUNTER-DRAFTED, and the base draft's intent is right

TRITON's stated intent — *consistency-shaped, not significance-shaped* — is correct, and a 51%
point threshold does not deliver it. At n = 828 the Wilson 95% half-width at p = 0.5 is
**±3.41 pp**, so a 51% point estimate carries an interval of roughly [47.6, 54.4]. It cannot
distinguish itself from 50% in either direction.

**The honest form is a REFUTATION test.** At this n the holdout cannot confirm; it can only fail
to refute. Building it as a confirmation invites the result to be read as a second independent
verification, which it is not and cannot be.

## §8.6 · CRITERION (v) — FINAL NUMBERS, AUTHORED BLIND

Executes only on a passing window (C3 AND C4 pass, P1/P2 unbreached). All three clauses at the
3d primary, on the gradeable subpopulation (n = 828).

**(v)-1 · DIRECTIONAL CONSISTENCY.** Both direction subgroups' **aligned** mean >= 0 — that is,
BULL raw `fwd_ret_3d` mean >= 0 AND BEAR raw `fwd_ret_3d` mean <= 0.
*Ambiguity fixed:* the base draft's "BULL mean >= 0 AND BEAR mean <= 0" reads in RAW terms while
§3 defines the primary in ALIGNED terms. Stated both ways above so the executor cannot pick
the wrong one.
*Declared satisfaction:* HIGH if the window passed. *Failure reachable:* yes — one direction
carrying the whole effect fails this, which is precisely what it is for.

**(v)-2 · NON-REFUTATION.** Wilson 95% **upper** bound on the aligned hit rate **>= 50%**.
Fails only if the holdout positively excludes 50% — which requires an observed rate below
**~46.6%**.
*Declared satisfaction:* HIGH. *Failure reachable:* yes, at any true rate below ~46.6%.
*Why an upper bound and not a point threshold:* this asks "does the out-of-regime sample
contradict?", not "does it prove?". Underpowered evidence cannot confirm, but it can refute.

**(v)-3 · EXCESS SIGN.** 3d aligned mean excess over the same-rows baseline **>= 0**. Sign
agreement only; no magnitude threshold, because magnitude at n = 828 is inside noise.
*Declared satisfaction:* HIGH. *Failure reachable:* yes, a sign flip.

**MANDATORY FACE STATEMENT on any (v) result, verbatim:**

> Criterion (v) is a REFUTATION test, not a confirmation. At n = 828 the sealed holdout cannot
> confirm an effect; it can only fail to refute one. A PASS means the out-of-regime sample does
> not contradict the window's finding. It does not mean the finding was confirmed twice, and it
> may not be cited as independent verification. Single-regime caveat applies per the holdout
> registration §6: not-a-kill, not-a-rescue.

## §8.7 · COMPLIANCE AUDIT OF THE JOINT DOCUMENT

**§1.1 — one gap found.** P1's alarm rate, P1's skip-reason rate, P2's classification rate and
C3's weekly-n substrate all declare an expected satisfaction rate with reachability shown. **C4
declares none.** Supplied here so the document is the compliance example it claims to be:

> C4 declared satisfaction: SATISFIED at the prior window's measurement (+0.2879 against 0.25),
> margin 0.0379 pp — thin, and stated as thin. Failure plainly reachable at any excess below the
> threshold, and the sensitivity band at §8.5a exists because the margin is thin.

**§1.2 — measured and non-applicable, stated rather than silent.** This registration performs no
cross-list join: every criterion computes on one table, and the baseline is same-rows. No key
uniqueness measurement is required. **If any join is introduced** — proxy grading, an external
price join, a cross-source baseline — §1.2 binds at that moment and `(rows, distinct_keys)` is
stated before first use as a join key.

**FORECAST-AS-STATE tell — run on the base draft, one hit, adjudicated CLEAN.** "An outage never
silently truncates the population again" is a future indicative in a rule section. Adjudicated as
a statement of the rule's intent rather than a load-bearing finding: it carries no argument and
nothing depends on its truth. No hedge required. Reported because running the tell and finding
nothing is a result worth recording.

---

**Merge note.** §§8.1–8.7 attach to BASE DRAFT `5f23564b` unchanged; §8.5a and §8.5b are
counter-drafts to parameters the base draft flagged OPEN and are TRITON's to accept, reject, or
counter again. On agreement, the joint manifest ships for spine ratification and T0 begins there.
