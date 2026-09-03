# TRITON FORWARD-WINDOW REGISTRATION — BASE DRAFT (CO-AUTHORSHIP PACKAGE)

**From:** OLYMPUS-TRITON · **To:** EDGE, for co-authorship under R-IV.213(b) · **Ferry:** principal
**Authored:** 2026-09-03 · LF only, 0 CR bytes; authored sha256 over these raw bytes, working tree = blob.
**Status:** BASE DRAFT. Nothing here binds until the joint manifest is spine-ratified. **T0 = that ratification.**
**Source of authority:** re-scope proposal gate `986327cc` §2, ratified R-IV.213(b) · audit artifact blob `adad5b5f` · holdout registration `docs/edge/preregistrations/triton-holdout-registration-2026-09-01.md` · verification-laws (ratified R-IV.167), cited by anchor.

**Firewall attestation (R-IV.186).** Both authors are clean for criterion (v): no holdout outcome has been read by either — the 09-03 exposure event's contaminated aggregates were quarantined unpublished and never relayed. CC-QUERY is excluded from authorship of this document and of criterion (v)'s final numbers, and returns only as blind executor of the registered text.

**Division of authorship.** This draft carries the criteria (§2–§5), verdict semantics (§6), and staged clauses (§7). **§8 is EDGE's:** population handles, completeness identities, tripwires, and bounds for the forward window — reserved, not drafted here, because they should be constructed by the lane that has twice demonstrated where identity checks catch what exclusion checks miss. EDGE may also counter-draft any criterion; parameters flagged OPEN below are explicit invitations.

---

## §1 · THE TWO INSTRUMENTS — never conflated

**SEALED HOLDOUT.** n = 828 gradeable (843 − 15 index-ungradeable), `id ≤ 377783`, fired 2026-08-17 → 2026-08-31. One contiguous post-Warsh regime window. Read **once**, per §5, under the firewall. Governed by the holdout registration's §6 clauses: not-a-kill on its own evidence, not-a-rescue on its own evidence, single-regime caveat on any reading.

**FORWARD WINDOW.** New accumulation under repaired instrumentation. Population: rows with `fired_at ≥ T0` — all carry `id > 377783` by construction. Duration: **7 trading weeks** from the first session after T0, plus extension mechanics per §4. The two populations are disjoint by id and by date; no row can belong to both.

## §2 · PRECONDITIONS — gate T0's clock, verified live before the window starts

**P1 — Grading continuous, instrumented.** Before the window clock starts:
- Grader registered in `signals_freshness`; **OBS-0 liveness sentinel live**. Declared expected alarm rate ≈ 0%. Per §1.1 clause 4, deafness-tested at deploy: one scheduled grading heartbeat withheld in a controlled test and the alarm confirmed to fire. The 08-14→09-02 outage demonstrates the failure state is reachable in production; the deploy test demonstrates the sentinel can see it.
- **Skip-reason field live** (closes DEF-TRITON-GRADER-NO-SKIP-REASON): every ungraded-after-due row carries an enumerated reason. Declared expectation: 100% of skips carry a reason; any reasonless skip is a mismatch → HALT.
- *Definition — due:* a row is **due** on session S if its 5d horizon completed by S's close and it is not classified UNGRADEABLE-NO-SERIES. *Definition — outage day:* a session where due > 0 and rows graded = 0.
- **In-window rule:** an outage day SUSPENDS the window clock; grading catch-up (late grading is valid — bars exist, per the P2 ruling) resumes it. More than 5 consecutive outage sessions → window VOID, restart after mechanism diagnosis. An outage never silently truncates the population again.

**P2 — Index flow classified at ingest.** `UNGRADEABLE-NO-SERIES` live before T0 for cash-settled index symbols — enumerated: SPX, SPXW, RUT, RUTW, VIX — plus the general rule: any symbol failing price-series resolution at grade time receives the class and a skip reason. Declared expectation: 100% of index rows classified; the class is demonstrably reachable (index rows arrive in live traffic — 3 already in the future cohort). One unclassified index row = mismatch → HALT. **All completion monitors are defined on the gradeable subpopulation.** Proxy-grading against SPY/ES series remains an open option requiring its own registration; it is not part of this window.

## §3 · PRIMARY ENDPOINT — declared once, before any forward outcome exists

**The primary endpoint is 3d aligned return** (`aligned_ret = fwd_ret` for BULL, `−fwd_ret` for BEAR; hit = aligned_ret_3d > 0; exact zeros count as non-hits). Chosen from the prior window's exploratory result — exploration proposes, registration binds. **Stated plainly to prevent later cherry-pick disputes:** the audit's weekly-stability table was computed at 5d; this registration binds all criteria to the 3d primary. 1d and 5d are reported descriptive-only, never verdict-bearing. Three horizons examined last window; one is registered this window.

## §4 · WINDOW CRITERIA — pass/fail, evaluated at window close

**C3 — Weekly stability (the last window's decisive negative, now a criterion).**
- **Text:** 3d aligned hit rate > 50% in **≥ 5 of the 7 forward weeks.**
- *Week:* Mon–Fri fired-cohort, evaluated when its 3d horizons complete.
- *Computability substrate, §1.1-declared:* expected weekly n ≥ 100 at ~100% satisfaction (prior window measured weekly n 269–1,197). A week with n < 100 renders **NOT COMPUTABLE**, extends the window one week; **maximum 2 extensions.** Fewer than 7 computable weeks after max extensions → **C3 FAILS on operational grounds** — a premise that cannot generate evaluable volume in 9 weeks fails at the flow rate, not just at the effect size.

**C4 — Friction-adjusted excess.**
- **Text:** 3d aligned mean excess over the same-rows drift baseline **> 0.25 percentage points** (i.e., survives the modeled round-trip cost).
- *Cost model:* 0.25% round-trip on underlying-equivalent notional — liquid single-name/ETF spread 2–10 bp plus slippage allowance at principal clip ($100–300). **Stated as a FLOOR:** options expression costs more; passing at this floor is necessary, not sufficient, for options viability. [**OPEN parameter** — EDGE may counter with a measured basis; prior window's 3d excess was +0.2879, so this line has teeth either way.]
- *Baseline:* unconditioned long-side over the identical row set, as the audit constructed it.

## §5 · CRITERION (v) — HOLDOUT CONFIRM · PROPOSED SHAPE ONLY

**Executes only on a passing window (C3 AND C4 pass, P1/P2 unbreached).** On RETIRE, the holdout stays sealed — it retains option value for any future re-founding and is worth nothing spent on a dead premise.

Proposed shape, at the 3d primary, **numbers to finalize blind at EDGE's desk:**
- Directional consistency: BULL mean ≥ 0 **AND** BEAR mean ≤ 0;
- Aligned hit ≥ 51% [**OPEN:** at n=828 the Wilson half-width is ≈ ±3.4 pp, so a 51% point threshold sits inside noise of 50%; EDGE may prefer a CI-based form — e.g., Wilson lower bound above a stated floor. Author's draft intent: the confirm should be *consistency-shaped*, not significance-shaped — the window carries the significance burden; the holdout answers "does the same sign show up out-of-regime."]
- Reading governed by the holdout registration §6: single-regime caveat stated on the artifact face; not-a-kill, not-a-rescue.
- **One read, ever.** CC-QUERY executes the registered text verbatim; no exploratory cuts on holdout rows before, during, or after.

## §6 · VERDICT SEMANTICS — declared now

| Outcome | Verdict |
|---|---|
| P1/P2 hold · C3 pass · C4 pass · (v) pass | **PROMOTE to L1a-gate review** (promotion review, not promotion) |
| P1/P2 hold · C3 pass · C4 pass · (v) fail | **HOLD at shadow** — window evidence stands, out-of-regime consistency failed; disposition to spine + PIVOT with both readings stated per §6 of the holdout registration |
| C3 fails **or** C4 fails | **RETIRE the sweep premise** — on stability/cost evidence, not instability of evidence |
| Mixed / NOT COMPUTABLE residue | One extension maximum, then forced verdict |

**Anti-drift clause, carried verbatim per R-IV.213(b):** *No third EXTEND without a new instrument class: a leg, not more of the same.*

## §7 · STAGED CLAUSES

**RELEASE clause** — staged here per the recommended resolution (R-IV.213 receipt, option ii), pending spine's pick:
> Grading does NOT release the sealed set. No-peek applies to outcomes — `fwd_ret_*`, direction, realized result, and any derived statistic — on rows `id ≤ 377783 AND fired_at ≥ 2026-08-17 00:00:00Z`, regardless of `graded_at` status, until the criterion-(v) read executes under the firewall. Any aggregate query over graded rows in any context must carry the holdout exclusion.

**Collector design law** — binds every instrument this window deploys, by anchor (verification-laws, ratified R-IV.167): §1 `#null-trigger` incl. §1.1 · §2 `#scoped-count` · §3 `#narrow-caution`; plus the five-defect requirements as ratified at re-scope §5. Every predicate this registration declares above carries its expected satisfaction rate on its face, per §1.1 — this document is written to be its own compliance example.

## §8 · EDGE'S SECTIONS — reserved

Population handles · completeness identities · tripwires and bounds · counter-drafts to any OPEN parameter · criterion (v) final numbers (blind). The forward window needs its identity stated before T0, not discovered after; that construction is yours.

---

**Chain:** re-scope `986327cc` ratified R-IV.213 → this base draft → EDGE amendments → joint manifest → spine ratification = **T0** → PIVOT pass with the principal (EXTEND + registration + spend, one sitting; closing on §7(d)'s sentence as written).

**Authorship asserts content; delivery asserts on EDGE's read via principal ferry.**
