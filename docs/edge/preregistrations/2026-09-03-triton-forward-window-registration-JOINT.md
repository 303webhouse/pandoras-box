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

**Chain:** base draft `5f23564b` → EDGE §8 `0e59be37` (superseded) → TRITON counter-again (I2, over-broad postcondition) → EDGE correction at source, new gate `b1c9791b` → **this joint manifest** → spine ratification = **T0** → PIVOT pass with the principal (EXTEND + registration + spend, one sitting; closing on §7(d)'s sentence as written). → **R-IV.273** — EXTEND + test blessed at PIVOT pass; Amendment 1 pending; spend PAUSED. Disposition filed at `docs/edge/2026-09-05-pivot-pass-disposition.md`, verbatim region gate `0427de59`. → **R-IV.275** — Amendment 1: observational strata. → **R-IV.301** — H-CORE4 declared. → **R-IV.306.** → **R-IV.323.**

## AMENDMENT 1 · DECLARED OBSERVATIONAL STRATA

**Spine-authored, R-IV.275(b). Filed by CC-BUILD 2026-09-05 under R-IV.273(b)'s
precondition order: Amendment 1 filed → P1/P2 verify → clock. THE AMENDMENT NEVER LANDS
AFTER THE CLOCK, and this filing is what makes the clock startable.**

**Wording is as issued.** The relay's hard-wrap line breaks were rejoined — including two
that split identifiers mid-token — and no word was changed, added, or removed. Gate over
the amendment body: `73bfd3a0`, `1511` bytes UTF-8, LF.

> DECLARED OBSERVATIONAL STRATA (hypothesis generation only; criteria and verdict semantics unchanged). Recorded per row at ingest from the first window session unless marked deferred:
> 
> **S1 day-of-week** — from `fired_at` (ET); cells are unequal by construction (Thu 1,572 vs Fri 1,035 in the pinned population) and are reported, never rebalanced.
> 
> **S2 DXY trend sign** — PROXY DECLARED: UUP daily closes (`stable_daily_bars`); `sign(close[t−1] − close[t−6])`; stamped at fire.
> 
> **S3 instrument class** — by PRODUCT TYPE: cash-settled index / ETF / single name. NOT by `INDEX_TICKERS`, which is a $2M premium tier holding six single names.
> 
> **S4 sector** — one-time ticker→sector map from UW `/info`, cached; a ticker with no map is UNMAPPED, never guessed.
> 
> **S5 footprint-present** — a footprint row for the same ticker on the same trading date (the census join key); strategy-scoped, never source-scoped; the under-count figure is dated whenever cited.
> 
> **S6 tide sign** — DEFERRED COMPUTATION: net premium sign of the 5-minute market-tide bar containing `fired_at`, computed from `market_tide_history` once the sink ships and backfills. Face states NOT STAMPED AT CLOCK START. Definition fixed here; values arrive later.
> 
> **H2 10d/20d horizons** — stored in NEW columns with their OWN completion marker (`graded_20d_at`). `graded_at` keeps its meaning (5d terminal) forever: the seal count, the residue, the tripwire identity, and the RELEASE predicate all key on it and none may move.

**S2 ANNOTATION (R-IV.281(c)) — the stronger ground for the UUP proxy.** The census
established that `dxy_trend` is a **computed bias-engine composite** (`backend/bias_engine/composite.py:134`,
*"DXY 5d trend + SMA20 context + VIX interaction"*) that **was never persisted per row in
any form.** So the proxy is not a workaround for a table that went dark: **a per-row DXY
stamp has never existed**, and no amount of repairing `factor_history` would have produced one.
**The proxy is the only construction available, not the cheaper of two.**

**NAMED HYPOTHESIS STRATUM — H-CORE4. Spine-authored, R-IV.301(c). DECLARED NOW,
PRE-CLOCK.**

`H-CORE4 = {SPY, QQQ, IWM, SMH}` — named from the first market read's finding (**3d 60.4%, n = 1,269**,
filed at `docs/edge/results/2026-09-06-triton-first-market-read.md`). **Criteria and verdict semantics are unchanged by this
declaration**; it names a stratum, it does not add an endpoint.

**It is declared before the clock for the reason the whole precondition order exists:** a
stratum named after seeing the window's own outcomes is not a hypothesis, it is a
description. **This one is named from the EXPLORE population, which is disjoint from the
window** — that is what makes pre-declaration meaningful rather than ceremonial.

**CC-BUILD annotation, not part of the spine-authored declaration — H-CORE4 IS NOT
HOMOGENEOUS UNDER S3.** Measured 2026-09-07 while building the S3 classifier: SPY, QQQ and
IWM are `etf_broad`; **SMH is not.** SMH matches none of R-IV.301(c)'s three ETF sub-classes
and lands in `etf_other` — a bucket this lane added because six of the fifteen tickers on
the measured bar path match no sub-class (COPX, GLD, HYG, RSP, SMH, TLT). **Stated here so
that a later cut by S3 does not silently split H-CORE4 three-to-one and read the split as a
result.**

**H-CORE4 — PRIOR RESOLVED. Spine-authored, R-IV.306(a), from the second read
(gate `ef52c6f7`). Verbatim; gate over the quoted text only: `50ba06a6`, `399` bytes.**

> H-CORE4 was named from a first-read cell in a population the third read (8d1f4e92) shows is carried by one week. Its own weekly series — 32.0 · 71.2 · 54.0 · 12.9 · 91.7 · 83.3 · 51.4 — tracks the pooled shape: 87.9% across 2026-07-27 and 08-03, 42.2% across the other five. H-CORE4 is a name for those two weeks. The declaration stands as a pre-clock named list; its prior is regime beta.

**UNIT OF INFERENCE — DECLARED PRE-CLOCK. Spine-authored, R-IV.306(b). Verbatim; gate
`83d1a64b`, `433` bytes.**

> For every stratum cut (S1–S7, H-CORE4), the WEEK is the unit of inference. Row-level Wilson intervals are reported for scale and never cited as the confidence of a weekly-varying quantity. No stratum result is reported as significant unless it holds in ≥5 of 7 computable weeks (mirroring C3) or a stated week-level test is applied. The grader sentinel's §1.1 predicate is unaffected — pass completion is not a market outcome.

**CC-BUILD note on the two summary figures, checked not assumed:** the simple means of that
series are **87.5** and **44.3**, against the stated **87.9** and **42.2**. **The stated
figures are n-WEIGHTED, and that is the correct form** — the weeks hold unequal row counts
(the third read's carrying week alone is 1,197 of 6,098). Recorded so a later reader who
averages the seven printed numbers and gets a different answer knows why, rather than
filing an erratum against a correct line.

**FEED-AVAILABILITY CONFOUND — DECLARED PRE-CLOCK. Spine-authored, R-IV.323(a).
Verbatim; gate over the quoted text only: `4a1870be`, `363` bytes.**

> PYTHIA v2.5 feed restored 2026-09-08 for exactly the H-CORE4 set (SPY QQQ IWM SMH), the remaining universe still on the collapsed v2.4 feed. The window's rows (triton_flow_shadow) are UW-sourced and unaffected. Any stratum whose source is PYTHIA/TradingView-delivered is CONFOUNDED by feed availability for the restoration period and is reported with that caveat.

**CC-BUILD read, answering the ruling's question (R-IV.323(a)) — S5 IS AFFECTED.**
`signals.source = 'footprint'` is **TradingView-delivered**, not internal:

```
backend/webhooks/footprint.py:1-4   "Receives footprint imbalance signals ... from
                                     TradingView's 'Footprint Alert for Pandora'
                                     PineScript indicator."
backend/webhooks/footprint.py:227   @router.post("/footprint")
backend/webhooks/footprint.py:206   "source": "footprint"
backend/webhooks/footprint.py:220   process_signal_unified(signal_data, source="footprint")
```

**So S5 (footprint-present) CARRIES THE CAVEAT BY NAME.**

**One distinction that matters and is easy to lose:** footprint is a **DIFFERENT Pine
indicator** from PYTHIA, so **the RE10045 mechanism does not automatically apply to it** —
that was PYTHIA's own array bug. **What it shares is the DELIVERY CHANNEL**, and the
confound the declaration names is availability, not the specific kill. **S5 is confounded
because it arrives the same way, not because it broke the same way.**

**Measured, for scale:** the Moby Dick census put footprint at **577 rows, 17 tickers,
through 2026-09-04 18:45** — so it was **alive four days ago**, and this is a caveat about
a live feed's coverage rather than a dead one.

**S1–S4, S6 and H2 are unaffected by this clause** on their sources as declared: day-of-week
and instrument class are derived, sector comes from UW `/info`, DXY from
`UUP`, tide from UW once the sink lands. **S5 is the only TradingView-delivered
stratum in Amendment 1.**

**Face label, carried from the ruling: hypothesis generation, not verdict.** Criteria and
verdict semantics are unchanged by this amendment; nothing here can move a pass/fail.

**S6 is the one stratum that is NOT STAMPED at clock start**, and it says so on this face
rather than appearing as a column full of nulls. Its *definition* is fixed here and its
*values* arrive with the sinks build — the order that matters, because a definition
authored after seeing the data is not a registration. **A later backfill does not undeclare
it.**


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

---

# CLOCK STARTED — R-IV.381(b)

**→ R-IV.381 — clock started.**

## P1 and P2, declared on the face with their evidence

### P1 — GRADING IS CONTINUOUS

| component | evidence | vintage |
|---|---|---|
| **today's pass** | `rows_touched 971`, `status ok`, 76 s | 2026-09-14 16:17 ET |
| **the fallback** | `no_regular_session_bars` **absent** (1,000 on 09-11); yfinance path entered and provider recorded per row | 2026-09-14 |
| **the sentinel** | T3 reads `job_runs` via `last_completed`, session-gated by `market_calendar`, SLO 26 h | live since `c38df2d9` |

**SATISFIED.** The grader runs, grades, and its grading is visible in a durable ledger.

### P2 — THE GRADER IS SUPERVISED

| component | evidence | vintage |
|---|---|---|
| **deafness test** | alarm forced to `flatline` by a controlled write, observed on the first poll, restored, **clear verified against the database** | 2026-09-11 14:48 ET |
| **both legs forced** | `_pass_overdue` AND the 26 h age — ageing one leg only would have left the alarm correctly silent and proved nothing | same |
| **timeout guard** | `TRITON_GRADER_TIMEOUT_S = 300`, `timeouts {count: 0}` | live |

**SATISFIED.** The sentinel has been shown to fire, and shown to clear.

## THE CLOCK

```
T_clock  =  first session after  =  Tue 2026-09-15
window   =  7 weeks
end      =  Fri 2026-10-30       (as stated in R-IV.381(b))
```

## WINDOW OF RECORD (R-IV.382(b)) — SETTLED

```
T_clock        Tue 2026-09-15
blind reads    seven, weekly, every FRIDAY:
                 2026-09-18  2026-09-25  2026-10-02  2026-10-09
                 2026-10-16  2026-10-23  2026-10-30
sessions       34            <- the registered n
week 1         PARTIAL, 4 sessions (Tue-Fri), declared
C3 gate        ">= 5 of 7" counts READS, not sessions
```

> **NEVER "7 WEEKS" WITHOUT "34 SESSIONS" BESIDE IT.**
>
> The window is seven weekly reads over **34 sessions**, not 35. Week 1 is short by one
> session because the clock starts on a Tuesday. **Quoting the duration without the count
> lets a reader reconstruct 35 from "7 x 5" and compare against a population that does not
> exist.**

**C3's threshold counts READS.** Five of seven Friday reads, each read standing on whatever
sessions preceded it — **so the partial first week costs the window one session and costs
C3 nothing**, because week 1 still produces exactly one read.

### ARITHMETIC CHECK, because n is registered

**Measured against `market_calendar`:**

```
Tue 2026-09-15 -> Fri 2026-10-30
  calendar days      45   =  6.43 calendar weeks
  TRADING days       34   =  6.8 trading weeks
  holidays in window  0
exactly 35 trading days (7 x 5) from Tue 2026-09-15 ends  Mon 2026-11-02
```

**Fri 2026-10-30 is 34 trading days — ONE TRADING DAY SHORT of 7 x 5.**

**Reported, not resolved.** The discrepancy is one session, and it is trivial in effect and
not trivial in kind: **`n` is registered, and a window stated as "7 weeks" that measures
6.8 will be quoted as 7 by whoever reads the prose rather than the date.**

**Both readings are defensible** — week 1 is a partial Tue–Fri, so "seven calendar weeks
ending on a Friday" lands on 10-30, while "thirty-five trading days" lands on 11-02.
**EDGE's call.** The window below is written to the stated end date and will be amended in
one line if the other reading is preferred.

**No holiday falls inside either version**, so the two differ by exactly one session and by
nothing else.

## S7 and S6

- **S7 stamps at or before the start** — retrofittable from bars, so it does not gate
  T_clock.
- **S6 stays deferred to SINKS-B**, as declared. Its tide-sign stratum needs
  `market_tide_history`, which does not exist until the sinks build ships, and SINKS-B is
  itself gated on the quota layer and the transfer.

---

# AMENDMENT 3 · R-IV.485 — READ CADENCE, WINDOW OF RECORD, AND THE BAR VENDOR

**Filed on the face by CC-BUILD, 2026-09-23, per R-IV.485(f).**
**Supersedes for cadence:** R-IV.382(b)'s read schedule. Everything else in this manifest stands.
**Prior:** Amendment 1 (observational strata, R-IV.275); Amendment 2 (bar vendor as a pinned
instrument property, 2026-09-23).

**BLINDNESS LINE, carried verbatim as R-IV.485 requires:**

> Blind: no hit rate, grade or outcome from the forward window has reached spine; QUERY reported
> only definition-independent facts.

**Why this amendment exists.** The read schedule as previously written implied a read was due
2026-09-18, and the bar vendor was held to the window only by accident. Both are corrected here so
the registration says on its own face what a reader must execute, without reconstructing it from
rulings.

## A3(a) · C3 stands — reads LAG their cohort by one week

A read evaluates a **Mon–Fri fired cohort** once its **3d horizons are complete**. A Friday signal
completes the following **Wednesday**, so a Friday read cannot evaluate that same Friday's cohort.
**Each Friday read evaluates the PREVIOUS week's cohort.** The lag is one week, always, and it is a
property of the 3d horizon, not a scheduling choice.

## A3(b) · WINDOW OF RECORD — amending R-IV.382(b)

**Cohorts (7):**

| cohort | fired sessions |
|---|---|
| W1 | Tue 2026-09-15 → Fri 2026-09-18 — **partial, 4 sessions** (T_clock is a Tuesday) |
| W2 | 2026-09-21 → 2026-09-25 |
| W3 | 2026-09-28 → 2026-10-02 |
| W4 | 2026-10-05 → 2026-10-09 |
| W5 | 2026-10-12 → 2026-10-16 |
| W6 | 2026-10-19 → 2026-10-23 |
| W7 | 2026-10-26 → 2026-10-30 |

**34 sessions, unchanged.**

**Reads (7 Fridays), each evaluating the cohort one week behind it:**

| read | date | evaluates |
|---|---|---|
| 1 | 2026-09-25 | W1 |
| 2 | 2026-10-02 | W2 |
| 3 | 2026-10-09 | W3 |
| 4 | 2026-10-16 | W4 |
| 5 | 2026-10-23 | W5 |
| 6 | 2026-10-30 | W6 |
| 7 | 2026-11-06 | W7 |

**C3's "≥5 of 7" counts these reads**, and no others.

**The last read date (2026-11-06) is NOT the last cohort session (2026-10-30).** They differ by
exactly the one-week lag, and conflating them is a live error this build already made once: the
first bar pin keyed on 11-06 as though it were the window's end.

## A3(c) · NO READ WAS DUE 2026-09-18

Read 1 falls on **2026-09-25**. Nothing is late, and **no extension is consumed.**

## A3(d) · EXTENSION MECHANICS

An extension adds **one cohort week at the end**. Its read follows **one week after that cohort
closes**, on the same lag as every other read. An extension therefore adds one cohort AND one read,
never a read without a cohort.

Unchanged and still binding, §8's anti-drift clause: *"No third EXTEND without a new instrument
class: a leg, not more of the same."*

## A3(e) · THE BAR VENDOR IS PART OF THE INSTRUMENT

**Triton's bars stay on yfinance for the whole window. A UW fix elsewhere does not switch Triton
mid-window.** A population whose bar vendor changes mid-window is not one population.

**As implemented (R-IV.497(d)):** the pin is keyed to the **row's own `fired_at` session**, not to
the date the grader runs. A row fired in 2026-09-15 … 2026-10-30 grades on yfinance **whenever it
is graded** — in this window, after it, or in a backfill years later. The earlier form keyed on the
run date and would have reverted an in-window row to UW on any run after the window closed; QUERY
found that, and it is fixed rather than documented around.

`fetch_r_close_index(..., pinned=...)` is required and keyword-only, so no caller can inherit a
default that answers for rows it never looked at. A ticker whose rows span the window boundary
fetches **two series and never merges them** — mixing providers inside one measurement is the
cross-adjustment seam this repo forbids elsewhere and would forbid here.

**And the grades are append-only.** A grade a read has consumed is **never overwritten**: the
update is conditional on the row still being ungraded, and every grade — first or re-grade — is
appended to `triton_grade_versions`, so a re-grade lands **beside** its predecessor and both stay
readable. Enforced at the write, because the selection's `graded_at IS NULL` is today's caller and
not a guarantee.

## A3(f) · HOW A READ CITES THIS

QUERY executes each read **from this blob, as of the read**, and **names the blob on the read's
face**. The blob is this file's git object id; the id in force before this amendment was
`57cb26a3`.

---

# AMENDMENT 4 · R-IV.521 — SESSION GAPS AND GRADE PROVENANCE

**Filed by:** CC-BUILD, 2026-09-24, on SPINE's order R-IV.522(b)5.
**Prior:** Amendment 1 (observational strata, R-IV.275); Amendment 2 (bar vendor as a pinned
instrument property, R-IV.489(a)); Amendment 3 (read cadence, window of record, bar vendor,
R-IV.485).

**Verbatim as issued. Nothing below this line to the end of the amendment is this lane's wording.**

> TRITON — AMENDMENT 4 · R-IV.521 · issued 2026-09-24 by SPINE (Fable 3)
>
> Session gaps and grade provenance. Issued before any read, on provenance evidence only; no
> outcome was observed (CC-QUERY's R-IV.518 check read nullness aggregates only).
>
> (a) Finding. When the pinned vendor had no bar for a horizon session, the grader's close lookup
> used a neighbouring session's close and recorded nothing to show it. The vendor held 2026-09-22
> for about one symbol in five, and 15 W1 rows are known to have been graded across that gap. No
> grade records the date of the bar it used, so no grade made before this amendment can be shown
> free of the fault.
>
> (b) Provenance. Every grade records the session date of the close it used. A grade is valid only
> when that date is its horizon session.
>
> (c) No substitution. A horizon session is a weekday on which the exchange traded. If the pinned
> vendor returns no bar for it after three separate requests, that horizon stays ungraded; no other
> session's close is used.
>
> (d) New class in §P2: UNGRADEABLE-SESSION-GAP — a horizon left ungraded under (c) when a read's
> grading runs. It is excluded from that read and listed on the read's face with ticker, horizon
> and session.
>
> (e) Fresh grading. Immediately before a read executes, its cohort is graded afresh under (b) and
> (c), and the new grades are appended as new versions. The read uses those versions and names
> them on its face. Grades made before this amendment are kept unchanged and used by no read.
>
> (f) A read executes only if (b)–(e) are live and verified, and session gaps are no more than 5%
> of its cohort's gradeable horizons. Otherwise it postpones under the registration's extension
> provision, its face says why, and SPINE rules on what follows. Read 1 remains scheduled for
> 2026-09-25 on these terms.
>
> (g) Nothing else changes: metric, horizons, cohorts, vendor pin, nulls and read schedule stand,
> except as (f) allows.

## A4 · AS IMPLEMENTED — this lane's note, not part of the amendment

**(b) Provenance.** `triton_grade_versions` carries `entry_session`, `session_1d`, `session_3d`,
`session_5d` and `session_gaps`. The session is written **beside the figure it produced**, in the
same insert, so a return and its provenance cannot be separated by a later write. The columns were
**added and never backfilled**: NULL means "graded before provenance was recorded", which is
exactly what (e) calls such a grade — kept, and used by no read.

**(c) No substitution.** The old lookup `close_on_or_near` is the fault in (a): it returned a bare
float, so a neighbour's close was indistinguishable from the session's own. It now returns **the
close and the session it came from**, and its substituting behaviour is **unchanged for callers
outside the window**, which R-IV.522(b)2 preserved. In-window grading uses `close_on_session`,
which takes the session or nothing and **cannot substitute at all** — the rule is enforced by the
absence of the capability, not by a caller remembering to check.

**"Three separate requests"** is counted in `triton_session_bar_attempts`, keyed
`(ticker, session_date, provider)`. Separate **in time**, not three calls in one breath: the vendor
served different coverage to identical requests days apart (R-IV.517(b)), so a same-pass retry
would mostly re-ask a cache and name a recoverable absence permanent. The nightly pass counts one
attempt per pass and holds the horizon meanwhile under `session_bar_absent_retrying`. The
fresh-grade command of (e) must reach a verdict *before* a read, so it makes the attempts itself —
each a real vendor round trip, each recorded — and only then names a gap. Same threshold, same
counter, and no verdict is ever reached on one failure.

**A horizon session is a weekday the exchange traded.** `nth_trading_day` walks Mon–Fri with no
holiday calendar (it mirrors a3, v0). That is safe here only because **no exchange holiday falls
inside the window through the last read's horizons** — 2026-09-15 to 2026-11-06 contains none,
measured against `market_calendar`'s explicit list on 2026-09-24 and reported under R-IV.522(b)4
before deploying. The grader no longer trusts that memory: an in-window horizon the calendar does
not call a session is **refused loudly** and graded by nothing. A test asserts the emptiness of the
holiday set inside the window, and a second asserts that every one of the 34 in-window sessions has
all three horizons landing on a session — so an extension of the window fails the suite rather than
grading across a holiday.

**(d) The class.** `UNGRADEABLE-SESSION-GAP` is returned by the grading pass as a **list of
`{row_id, ticker, horizon, session}`**, not a count. A count answers how many and never which, and
(d) requires the face to name ticker, horizon and session.

**(e) Fresh grading.** `python -m jobs.triton_fresh_grade --cohort W1`. It appends to
`triton_grade_versions` and records attempts, and **writes nothing into `triton_flow_shadow`** — not
the returns, not `provider`, and above all not `graded_at`. Overwriting the pre-amendment grades
would destroy the comparison that shows what the substitution did, which is why (e) keeps them. A
test parses the command's AST and fails if any live string in it names `graded_at` or an update of
the shadow table.

**Cohorts** are derived, not stored: W1 begins at T_clock (Tue 2026-09-15) and each later cohort is
that Mon–Fri week, through W7 ending 2026-10-30. That is 4 + 5×6 = **34 sessions**, which is
R-IV.485(b)'s own figure — the arithmetic is the check, and a test asserts it.

**Blob chain.** The id in force before this amendment was `c6203e4b`; before Amendment 3,
`57cb26a3`.
