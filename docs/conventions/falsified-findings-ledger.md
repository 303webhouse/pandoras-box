# FALSIFIED FINDINGS LEDGER

**Established:** R-IV.130, board-wide and standing.
**Founding entries:** EDGE. Spine's ruling said "six"; the artifacts support **ten** — filed
rather than trimmed to a number. The count is stated, not forced.
**Consolidated 2026-09-02**, superseding the earlier nine-entry draft whole (no-splice): adds
E-10 and the eighth sub-form.

## Why this ledger exists

A finding that is quietly corrected leaves the corrected version looking like it was always
right. This ledger preserves the strike lineage: what was claimed, what refuted it, who caught
it, and what survived. Every entry reached a filed artifact or a board relay before it was
caught.

## Sub-form taxonomy

Each entry names the sub-form of **RECALL MAY PROPOSE; ONLY THE ARTIFACT MAY ASSERT** that
produced it. Naming sub-forms is the point: none of them *feels* like recall in the moment.

The nine sub-forms below scope to **RECALL-ASSERTION failures** — cases where a lane
asserted something it had not read. They classify; they do not gatekeep. This ledger records
falsified and corrected findings **regardless of mechanism family**, and an entry outside the
recall-assertion family states its class in the Sub-form field with a one-line filing
rationale (the E-10 precedent, now the rule).

A second enumerated group crystallizes when any out-of-family class reaches **two instances** —
the same standard applied to NULL-TRIGGER. Until then, out-of-family classes live inline.

**Out-of-family count is stated with the entry total** (currently **3 of 13**). If that ratio
climbs, the taxonomy is under-covering, and the count is how anyone notices.

| sub-form | what it feels like |
|---|---|
| INFERENCE FROM ABSENCE | reasoning |
| COMPLEMENT AS MEASUREMENT | arithmetic |
| ADJACENT CITATION | sourcing |
| STATUS FROM RECALL | context |
| PREMATURE SETTLING | precision |
| MECHANISM FROM SYMPTOM | diagnosis |
| PARTIAL APPLICATION | having already fixed it |
| COINCIDENT AGREEMENT | confirmation |
| ATTRIBUTION FROM RECALL | accountability |

**COINCIDENT AGREEMENT** deserves its note: a number that matches expectation for the wrong
reason. Two instances, both caught by CC-QUERY — 969 pending rows against a "~1,000 holdout"
(different populations, similar size, would have read as integrity confirmed), and OTHER's
excl-zero-window 17 against its non-broker-validated 17. It is the hardest sub-form to catch,
because the usual cue that something is wrong — a number that looks wrong — is exactly what is
absent.

**Standing rule for this ledger (§4B).**

> **Every attribution in this ledger is read from the record, never from recall — including
> attributions of the catch.** A ledger whose organising premise is "another lane caught it"
> is a ledger *about authorship*, and is therefore the single document where
> attribution-from-recall does the most damage.

---

## E-1 · B0's absence is a result
**Claim:** "Every unit is single-exit, so B0 rendered nowhere — the degeneracy catch prevented
66 arithmetic identities."
**Artifact:** PR-106 part-1 findings read, F9; propagated to the arms artifact's face.
**Falsified by:** CC-QUERY, from the normalized fills file — 7 of 34 fill-resolvable units are
MULTI-EXIT; B0 was owed for all seven and could not render because the spec never specified how
multi-exit status is determined.
**Sub-form:** INFERENCE FROM ABSENCE.
**What survived:** nothing of the claim. A spec gap read as a data property.

## E-2 · 32 PRINCIPAL-ATTESTED-INTERIOR
**Claim:** ledger-wide tier composition is "34 BROKER-VALIDATED / 32 PRINCIPAL-ATTESTED-INTERIOR."
**Artifact:** findings read F8; written into the MANDATORY Clause-1 form, so it propagated to
every arm table by instruction.
**Falsified by:** CC-QUERY — the ledger carries four tiers: BV 34 · PAI 16 · MANUAL 14 ·
CSV_RECONCILE 2. The 32 was 66 − 34.
**Sub-form:** COMPLEMENT AS MEASUREMENT.
**What survived:** the BROKER-VALIDATED count. Sixteen units were labeled with a tier they do
not carry. *Note: the part-1 render was always correct four-tier; only the arms artifact
collapsed non-BV into PAI.*

## E-3 · OTHER is weakest against the market
**Claim:** "OTHER underperformed SPY on both mean and beat count — the book's bulk is where the
market comparison is weakest."
**Artifact:** findings read F6.
**Falsified by:** CC-BUILD composition — OTHER is 12 of 24 inverse (SQQQ 6, TSLQ 5, SRTY 1), so
B3 inherits the long-reference confound already identified for B1.
**Sub-form:** PARTIAL APPLICATION — the confound was applied to B1 and not its sibling arm.
**What survived:** the confound is real and reaches B3 in every cell holding inverse units; B3
is clean only in ENERGY and METALS.

## E-4 · Rolling shutdown
**Claim:** the 08-17/18 staggered last-rows show a rolling per-path shutdown.
**Artifact:** T7-ADJUDICATION v1.0, F1.
**Falsified by:** T6-D/T6-C — server_scanner was emitting at 13:23Z 08-18 and CTA pushed 7/7
that day. Emitters lived; persistence failed per-row.
**Sub-form:** INFERENCE FROM ABSENCE.
**What survived:** the stagger is real and reflects per-source emission schedules.

## E-5 · Temporal precedence exonerates the flip
**Claim:** ae99def is exonerated because every dead path's last row precedes the deploy.
**Artifact:** T7-ADJUDICATION v1.0, F2 grounds.
**Falsified by:** the ruled death bracket [04:12Z, 13:23:37Z] contains the 06:26:30Z deploy.
**Sub-form:** INFERENCE FROM ABSENCE.
**What survived:** the exoneration, on different grounds.

## E-6 · Enrichment-path NaN
**Claim:** ae99def is exonerated because the poison lives in the yfinance-fallback enrichment
path, which the flip cannot reach.
**Artifact:** T7-ADJUDICATION v1.1, F2 grounds.
**Falsified by:** call order — enrichment runs after the INSERT; crypto rows died
pre-enrichment; the 97-symbol shape demands a global source. Poison source UNATTRIBUTED.
**Sub-form:** MECHANISM FROM SYMPTOM.
**What survived:** the exoneration, finally grounded on code-asserted topology. A conclusion
that outlived two of its three arguments was never resting on them.

## E-7 · AMAT in the semis roster
**Claim:** AMAT is a semis/DRAM member of the PR-106 universe.
**Artifact:** the PR-106 sector map as filed.
**Falsified by:** it appears in neither extraction — not the RH 115, not the Fidelity 26.
Authored from domain knowledge while writing the roster.
**Sub-form:** STATUS FROM RECALL, in its purest form — a universe member invented rather than
measured.
**What survived:** nothing. Struck at Amendment 3.

## E-8 · Unknown emitters behind PULLBACK_ENTRY
**Claim:** ~300 post-07-03 PULLBACK_ENTRY rows are not attributable to any known emitter.
**Artifact:** EDGE relay; adopted into a spine defect text before correction.
**Falsified by:** filed QS-02-F1 — CTA Scanner is and always was the dominant emitter (1,171 vs
Crypto Scanner's 335). The premise dropped QS-110-C2's Crypto-Scanner-only scope.
**Sub-form:** ADJACENT CITATION — a real figure quoted outside the scope that produced it.
**What survived:** the rate residual (223 ghosts in 33h against a ~7–16/day baseline), still open.

## E-9 · Semis is no longer single-instrument
**Claim:** the semis cell gained instruments, so R-IV.86-b's single-instrument finding is
reversed.
**Artifact:** EDGE relay to spine, pre-render.
**Falsified by:** CC-BUILD composition — the traded units are 12 SOXS + 1 RAMZ + 1 SOXL. The map
gained instruments; the trades did not.
**Sub-form:** ADJACENT CITATION — map-level evidence offered for a unit-level claim.
**What survived:** R-IV.86-b's original finding, intact. Crypto's half of the reversal stands.

## E-10 · OTHER-cell and ledger-wide realized totals
**Claim:** OTHER total realized $159.83, expectancy $6.66; ledger-wide $1,124.23, expectancy
$17.03.
**Artifact:** the part-1 render, `PR-106-RESULTS-PART1`.
**Falsified by:** broker records — ids 91 (NBIS) and 92 (ICE) carried filed realized values of
−0.20 and −0.52 against actual −40.40 and −8.92; net −$48.60.
**Sub-form:** **OUT-OF-FAMILY — SOURCE-DATA ERROR.**
**Why it is filed with the others:** E-1 through E-9 are analyst inference errors. E-10 is the
first whose cause is upstream data, and the ledger must not imply every falsification is an
analyst's. A study can be reasoned correctly end to end and still carry wrong numbers if the
ledger beneath it is wrong — the argument for broker reconciliation as infrastructure rather
than hygiene.
**What survived:** every count, both win rates, both average wins, four of five cells, all gate
statuses, all arm values. The correction moves money, not structure.

## E-11 · k = 0 for the Triton holdout
**Claim:** the Triton holdout contains no index-symbol rows — `k = 0`, so effective validation
n = 843 (stated R-IV.153).
**Artifact:** none. Labeled proposal-only throughout; **no artifact ever shipped it.**
**Falsified by:** direct read — CC-QUERY's `TRITON-K-CAPTURE-AND-BURN-SWEEP`, as-of
2026-09-02 18:48:49Z: **k = 15** (SPX 6 · SPXW 6 · RUTW 2 · VIX 1 · RUT 0). Effective
validation n = 828.
**Mechanism:** a residue-scoped count — 72, every query behind it predicated
`fired_at < 08-17` — read as a table-wide population count.
**Sub-form:** **OUT-OF-FAMILY — FENCED-EXPECTATION-OVERTURNED.** Filing rationale: the expectation was
fenced as a proposal, carried a stated unknown into the registration (`n = 843 − k`, *k*
unknown), and was overturned by the measurement the fence called for. **The machinery
functioned.** It is filed so the ledger records the case where the guard held, not only the
cases where it did not.
**What survived:** the registration's caveat form, vindicated — §5 filed the unknown rather
than assuming zero, so the shortfall arrived as an expected quantity instead of a surprise at
validation time.

## E-12 · XLF id 170 realized −97.72
**Claim:** XLF id 170 realized **−97.72** (ruled R-IV.139).
**Artifact:** the R-IV.139 ruling. **Never reached the database.**
**Superseded by:** R-IV.157 — **−95.99**, corrected before any write.
**Mechanism:** the 06-22 and 06-24 adds were averaged into a basis that predates them.
**Sub-form:** **OUT-OF-FAMILY — COMPUTATION CORRECTED PRE-WRITE.** Caught at
execution review, which is where it was supposed to be caught.
**What survived:** everything downstream. The correction is 1.73 on a single unit and touched
no aggregate, because no aggregate had been computed from the wrong figure yet.

## E-13 · CC-QUERY formed the k = 0 inference
**Claim:** "CC-QUERY's own k=0 inference is theirs and they own it."
**Artifact:** EDGE relay to spine, 2026-09-02.
**Falsified by:** CC-QUERY, from the record — the k = 0 expectation was formed in R-IV.153,
explicitly labeled as an expectation and gated pending direct read. CC-QUERY had filed the
caveat form *before* the read, endorsing EDGE's fallback.
**Sub-form:** ATTRIBUTION FROM RECALL.
**How it happened:** an ambiguous phrase in CC-QUERY's report ("the inference read a scoped
count as a population count") was read as self-attribution and restated as settled fact,
without reading R-IV.153.
**What survived:** nothing of the attribution. The transferable lesson is CC-QUERY's and is
now §2 of `verification-laws.md`.
**Aggravating circumstance, filed because it is the point:** this occurred in the same batch
that delivered a ledger whose premise is that every entry was caught by another lane.

*Filed at E-13, not EDGE's §4C index of E-11: the held ledger's sequence assigns
(R-IV.164(b)). EDGE identifies its entries by content, not by number.*

---

## Standing check

Before any figure ships: **did I READ this value in this session, from an artifact whose scope
matches the claim?** If it was inferred, complemented, borrowed from an adjacent scope, recalled
as a status, still moving, diagnosed from a symptom, already-fixed-somewhere-else, or agrees
with expectation for a reason not established — it renders **NOT DETERMINABLE FROM THIS
ARTIFACT**, not as a number.

**Every inference entry above was caught by another lane; none by its author.** That is the
ledger's real finding: the check does not work from inside the lane that needs it, which is why
cross-lane verification is load-bearing rather than ceremonial.
