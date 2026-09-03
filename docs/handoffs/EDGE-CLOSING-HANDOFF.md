# EDGE — CLOSING HANDOFF

**Ordered by:** R-IV.230, consolidation of EDGE's functions into spine.
**Authored:** 2026-09-03 by EDGE.
**Save to:** `C:\temp\cc-query-handoff\EDGE-CLOSING-HANDOFF.md`

---

## §0 · STATUS OF THIS DOCUMENT — read this first

Every item is marked **[VERIFIED]**, **[RELAY]**, or **[RECALL]**.

- **[VERIFIED]** — read from origin or disk during this session. Citable.
- **[RELAY]** — ruled, but has no address on disk. **A ruling that lives only in relay is not a
  ruling anyone else can find.** Treat as an owed filing, not settled record.
- **[RECALL]** — EDGE's memory, unverified. **Do not cite. Verify or discard.**

This lane's most expensive errors were all one shape: asserting from the second and third
categories as though they were the first. The marking is this document's most load-bearing feature.

**The largest structural fact in this handoff:** a substantial body of *ratified* doctrine exists
only in relay. `docs/conventions/verification-laws.md` carries §1 (NULL-TRIGGER, §1.1
registration-time law, §1.2 key uniqueness), §2 (scoped-count), §3 (narrow-caution), §4 (ledger
amendment), §5 (reads-disagree). **PROBE-COVERAGE UNVERIFIED, KEYSPACE COLLISION and OVER-BROAD
POSTCONDITION were each ratified and none is filed.** See §2.

**Tooling note, stated without a status claim:** Desktop Commander answered four calls this
session and timed out on the fifth. That is an observation, not a verdict on the tool — the
precise error this lane filed as its own aggravated entry (§1.4). The conditional form is what
survives: DC reads are unreliable *when the desktop app is closed*.

---

## §1 · LEDGER PASS QUEUE

Target: `docs/conventions/falsified-findings-ledger.md` — **13,184 B on origin/main [VERIFIED]**,
carrying E-1..E-13 and a nine-sub-form taxonomy.

A superseded duplicate was renamed this session **[VERIFIED]**:
`C:\trading-hub\docs\codex-briefs\falsified-findings-ledger.md` (8,188 B, untracked) →
`SUPERSEDED-EDGE-DROP-2026-09-02-falsified-findings-ledger.md`. Content unchanged. It described
itself as authoritative while being the copy that was never filed.

### §1.1 · BOOKKEEPING RULING — apply before any count is edited

Two metrics, two denominators, each stating which it is:

- **Crystallization trigger counts (entry × sub-form) PAIRS.** An entry may instance two
  sub-forms; the trigger is a claim about how lanes err, so pairs are the unit.
- **Out-of-family ratio counts ENTRIES.** An entry either fits the family or it does not.

The scoped-count law applied to the ledger's own instruments. Required because the ledger now has
its first **composed entry** (§1.4).

### §1.2 · ORDERING — non-negotiable

**File the enumeration rulings FIRST, with addresses. Only then let a trigger key on a count.**
EDGE asserted "FORECAST-AS-STATE 3 → 4" from relay while the filed ledger read n=1; CC-QUERY
correctly refused to corroborate. A trigger keyed to a count no filed artifact carries is a
self-monitoring count with nowhere to be wrong.

**Every tally files with each member's host artifact and line** (CC-QUERY's amendment, adopted by
TRITON the same turn). A tally whose members have addresses is re-verifiable by any lane in three
minutes; one carrying only a number must be trusted.

### §1.3 · SUB-FORM TAXONOMY — owed rows

| sub-form | what it feels like | status |
|---|---|---|
| ATTRIBUTION FROM RECALL | accountability | ninth, ratified — **[RELAY]** |
| PROBE-COVERAGE UNVERIFIED | a negative result | tenth, ratified R-IV.181(a) — **[RELAY]** |
| FORECAST-AS-STATE | foresight | eleventh, ruled at n=3 — **[RELAY]** |

Widened definition, adopted R-IV.220: **FORECAST-AS-STATE = CONDITIONAL ASSERTED AS ACTUAL.** The
dropped condition may be temporal or situational; cause-is-not-kind.

**Mechanical tell**, adopted into spine's pre-ship check at R-IV.220(2): any future-conditional
verb — *will / would / could* — inside a **findings, rationale, or recommendation** section. In
findings the verb is itself the flag; in recommendations forward tense is expected, so the test is
**load-bearing and unhedged**. Scope widened after CC-QUERY's caveat that a findings-only tell is
narrower than its class — and a detector narrower than its class is a null-verifier in the check.

### §1.4 · OWED ENTRIES

**FORECAST-AS-STATE — four instances:**

1. CC-QUERY's trades-rebuild forecast — *"hard-coded ids will hit wrong rows in the new
   keyspace."* **[RELAY]**, address unconfirmed. Candidate host:
   `docs/edge/results/2026-09-03-trades-rekey-diagnosis.md` (ff551fc, gate dc40970b, 7,816 B).
   **Verify before filing.**
2. `931f35c:docs/defects/DEF-STRIKE-WATERMARK-HOLIDAY.md:50` — *"Thanksgiving and Christmas will
   both arrive with baseline_sessions far above 3."* **[VERIFIED]** by CC-QUERY. Its truth depends
   on the ticket failing — a forecast inside a defect document presuming the defect unfixed, which
   is the sharpest available signal that a claim is conditional. CC-BUILD holds a ready correction
   to the hedged form.
3. `docs/strategy-reviews/triton-shadow-audit-2026-07.md:204` — *"the next window will be
   measurably cleaner rather than merely longer."* **[VERIFIED]** by CC-QUERY. Load-bearing: one of
   two arguments carrying EXTEND SHADOW over RETIRE.
4. EDGE's tooling entry — qualifies only under the widened definition. **[RELAY]**; it is the
   composed entry below.

**EDGE'S TOOLING ENTRY — the ledger's first COMPOSED entry:**

> **Claim:** "EDGE has no access to the ferry path or any disk the principal holds" — asserted as
> structural fact, argued from, and used to obtain a narrowed staging law.
> **Falsified by:** the principal asking *"why not? you have Desktop Commander."* One call returned
> the file.
> **Sub-form 1 — STATUS FROM RECALL** (the act): asserted for weeks without testing, from a memory
> note.
> **Sub-form 2 — CONDITIONAL ASSERTED AS ACTUAL** (the content): the note read *"unreliable when
> the app is closed"* — conditionally true, re-proven the same hour — and shipped without its
> condition. The lesson is **conditional-truths-hardened-into-statuses**, not tool-was-fine
> (spine's correction, adopted).
> **Aggravation:** it was argued, not merely asserted, and **it moved a ruling** — R-IV.173(a) had
> spine own an error that was EDGE's. Re-examined at R-IV.226(b): the authorship/delivery split
> stands as law, only the premise retires, R-IV.171(a) is retroactively vindicated as
> always-satisfiable.
> **What survived:** nothing of the claim.

**CC-QUERY's "never ruled" false negative — ADJUDICATED HERE, EDGE's last ruling:**

> **Claim:** instance (3) "was never ruled."
> **Falsified by:** EDGE did rule it, in the relay admitting CC-BUILD's instance; that ruling never
> reached CC-QUERY's lane.
> **Sub-form: PROBE-COVERAGE UNVERIFIED — third instance.** A search of inbox and disk could not
> have found a ruling that entered neither; a negative shipped without establishing the probe could
> return a positive. Self-caught, self-offered.
> **Cure — CC-QUERY's phrasing law, adopted:** *"not present in my inputs or on disk"* is what a
> lane can attest; *"never ruled"* is a claim about the record.
> **Required note when this class files:** all three PROBE-COVERAGE instances are CC-QUERY's. That
> is not a lane problem — it is the lane running the most probes and self-reporting hardest. State
> the concentration as tracking exposure, or the ledger will read as an indictment of its most
> rigorous contributor.

**Also owed — all admitted, texts held by their offering lanes:**

- **E-14 · erratum-2 source-data error** — OUT-OF-FAMILY / SOURCE-DATA ERROR, **second instance**,
  so SOURCE-DATA ERROR **enumerates**. Out-of-family numerator 3 → 4. **[RELAY]**
- **FENCED-EXPECTATION-OVERTURNED, second instance** — spine's two-objects-one-name expectation,
  falsified by CC-QUERY's identity check. **Enumerates at two.** **[RELAY]**
- **OVER-BROAD POSTCONDITION** — n=4, two actors (CC-BUILD ×3, EDGE ×1), enumerated R-IV.226(c).
  EDGE's instance: I2 demanding an empty interregnum, which would have HALTed at T0 on a measured,
  expected, healthy state. Caught by TRITON pre-ratification, corrected at source.
- **SIL erratum** (OLYMPUS-BOOK) — ADJACENT CITATION with the reasoning-scope extension: *an
  analysis carries its instrument scope or it becomes a different claim.* SLV structure applied to
  SIL. Admitted; awaiting the offering lane's text.
- **CC-BUILD's retired CR-probe** — admitted in principle. Classification turns on DIRECTION: false
  negative → PROBE-COVERAGE; false positive → KEYSPACE COLLISION; cannot-fail → null-verifier.
  **Date it against R-IV.181(a)** — an instance predating spine's adoption of the probe-coverage
  check is backfill; one postdating it is evidence the check is not working, which needs a stronger
  remedy than a ledger note.
- **Spine's un-actioned objection** — class OBJECTION NOT ACTIONED, out-of-family, n=1, inline. It
  opens an axis the ledger has not measured: every prior entry records a **detection** failure;
  this records an **action** failure. A ledger measuring only detection would show a board catching
  everything and fixing nothing, and read as healthy.
- **CC-QUERY's probe-artifact retraction** (range-terminated sed) — admitted; PROBE-COVERAGE.

**STANDING RULE owed at §4B:** *every attribution in this ledger is read from the record, never
from recall — including attributions of the catch.* A ledger whose premise is "another lane caught
it" is a ledger about authorship, and is the one document where attribution-from-recall does most
damage.

**§4B RIDER — owed, and never filed despite EDGE stating in relay that it was:** *the record
includes your own filings; authorship confers no exemption from re-reading before quoting. A draft
you wrote is not the artifact that was filed — it may have been renamed, folded into another
document, corrected by its executor, or never have arrived.* **Operative corollary: your own filed
artifacts are readable — read them rather than reporting uncertainty about them.**

---

## §2 · CONVENTIONS OWED — ratified, unfiled

Target: `docs/conventions/verification-laws.md`.

### §2.1 · The instrument-audit doctrine — three of five members unfiled

| member | failure | status |
|---|---|---|
| null-verifier | a CHECK that cannot fail | filed (pre-existing law) |
| NULL-TRIGGER | a TRIGGER that cannot fire | **filed** §1 |
| PROBE-COVERAGE UNVERIFIED | a READ that cannot see — false negatives | **[RELAY]** |
| KEYSPACE COLLISION | a MATCH that cannot mean — false positives on joins | **[RELAY]** |
| OVER-BROAD POSTCONDITION | a CHECK that fires on the wrong thing — false positives on checks | **[RELAY]** |

**PROBE-COVERAGE operative form:** *before a negative ships, demonstrate the probe could have
produced a positive.* Distinct from INFERENCE FROM ABSENCE as siblings, not duplicates — the
absence law asks of the **population** ("were events expected across this window?"), probe-coverage
asks of the **instrument** ("could this read have returned a positive at all?"). Both must be
answered before a negative is a finding. Answering only the first is how E-1 shipped.

**KEYSPACE COLLISION operative form:** *state the keyspace of every id column in both lists before
the join.* Differing keyspaces mean the join cannot produce a true positive; intersect on a content
key and say on the face which key was used and why. Distinct from probe-coverage **by direction** —
probe-coverage manufactures false negatives, keyspace collision false positives, and a lane that
has internalised the first is fully exposed to the second because here the positives arrive on
schedule.

**OVER-BROAD POSTCONDITION** — CC-BUILD's consequence line should ride the entry verbatim: *"this
is the failure mode that gets assertions deleted."* It is the only member whose failure mode is the
**loss of the instrument** rather than a wrong reading from it, because the cheapest response to a
false alarm is to remove the alarm.

### §2.2 · The unified scope law — four faces, one rule

**A SCOPE-BEARING STATEMENT CARRIES ITS SCOPE, OR IT BECOMES A CLAIM ABOUT A LARGER POPULATION
THAN WAS EXAMINED.**

- a **CITATION** carries its scope (unscoped-citation rule — filed)
- a **COUNT** carries its complement (scoped-count rule — filed §2)
- a **TALLY** carries its members' addresses (**[RELAY]**, this session)
- an **ABSENCE** carries the boundary of what was searched (**[RELAY]**, CC-QUERY's phrasing law)

Each was learned separately and at cost. They should file as **one entry with four faces**, not
four rules a reader must notice are related.

### §2.3 · Other conventions owed

- **Completeness closes at the tail.** Hash and arithmetic are blind to a part truncated *before*
  assembly — its hash is the hash of the short file and the arithmetic sums correctly on short
  inputs. Only reading the end proves it ends. Ruled R-IV.227(b) into the channel's standing form.
- **Every control tests one proposition; a set of controls is complete only when the propositions
  are enumerated first.** EDGE named three (identity, order, seam) and there were four.
- **Assembly inputs persist until the assembled artifact is ratified or filed** — R-IV.227(a). Its
  boundary condition: once filed, a stale input describing itself as authoritative is a *worse*
  hazard than a stale file, because it reads authoritative on its own face.
- **§1.2's minting corollary** (filed, but restate at first use): the gate is **post-mint** —
  collectors mint before their population exists, so uniqueness is measured at first use *as a join
  key*, over the population being keyed.

---

## §3 · ADJUDICATIONS IN PROGRESS

1. **Map §2 amendment — PYTHIA's second death. [RELAY, needs verification]** Map §2 currently reads
   "alert fleet crashed pre-07-24; 07-24 resurrection covered the Pythia fleet only." That line now
   has a sequel: the resurrected fleet **died again in waves 2026-07-27 → 08-05**, 97 tickers,
   undetected five weeks. Sourced to TRITON's relay. **Verify against the artifact before filing.**

2. **Did any Track A population draw on `pythia_events`? [OPEN — expected no, not measured]** Track
   A's sources per Map §1 are tradingview, server_scanner, cta_scanner, crypto_scanner, footprint,
   crypto_engine; PYTHIA is a separate fleet. **But the Track A window (< 2026-08-18) overlaps the
   collapse exactly**, and expected is not measured. One query settles it. Until it runs, no Track A
   figure should be re-cited in a context where a PYTHIA dependency would matter.

3. **Map amendment queue, batched — never dripped:**
   - **§4** — price_history's probable cause (price_collector volume guard, DB 1032 MB vs 300 MB
     abort threshold, 70 refusals/4 min); provenance-hierarchy violation as **hygiene only**
     (causal elevation withdrawn R-IV.29(a)); DEF-SOXS-PRICE-DISCONTINUITY at the corroborated
     **1.52× / 1.51×** shape with the residual ~2.38× stated as *ordinary −3× decay and not a
     defect*; DEF-BARS-NO-PROVENANCE closed (773e7a8).
   - **§5** — orphan ledger **829 = ORPH-SPORADIC 370 + ORPH-POISON 459**, labelled, never merged;
     Fidelity sleeve ruled stale, superseded by the attestation tier scheme; **provenance tiers**
     BROKER-VALIDATED / PRINCIPAL-ATTESTED / UNVERIFIED; REALIZED-LEDGER GAP (24 auto-swept
     expiries carrying NULL realized_pnl — realized aggregates understate losses until backfilled);
     `signal_options_expressions` root cause = asyncpg date bind (EDGE's task-GC hypothesis is
     **dead**, superseded); fake-healthy taxonomy now four members — background_task_failures,
     price_history, cash_flows (table present, no feed path), retention-policy-absent.
   - **§6** — CTA-L clause inheritance from PR-103's restatement; the tag-strip footnote that
     visibility strata are **time-varying**.

4. **PULLBACK_ENTRY rate residual — OPEN.** 223 ghosts in 33 h against a ~7–16/day persisted CTA
   baseline (~16×). Three hypotheses: persisted-baseline undercount · genuine burst ·
   **DB-dependent dedupe broken by the outage** (spine's, and the leading one — UUID ids mean ON
   CONFLICT cannot dedupe, so the suppressor must be a pre-insert signals query, disabled by table
   death). Discriminator: one grep of the CTA scan path for a pre-insert signals query. **EDGE
   claimed this and never ran it.**

---

## §4 · OPEN OFFERS AND STANDING COMMITMENTS

- **CC-BUILD** holds two ready items on the word: the FORECAST-AS-STATE taxonomy row + ledger
  entry, and the line-50 correction on `DEF-STRIKE-WATERMARK-HOLIDAY.md`.
- **OLYMPUS-BOOK** holds the SIL erratum text.
- **Spine** holds the un-actioned-objection entry under its own name.
- **CC-QUERY** holds the probe-artifact retraction and the "never ruled" entry — the latter is
  adjudicated in §1.4 above and needs only filing.
- **R-IV.229 clearance annotation** — TRITON asked, EDGE seconded: the T0 ruling was declared
  before CC-BUILD's PYTHIA finding reached spine's desk. The ratification is correct on the merits
  (the forward window reads `triton_flow_shadow`, not `pythia_events`), but *asked-and-answered-
  post-declaration* is a different record from *never-arose*. **A ruling that survives a question
  it never faced should still show the question.**

---

## §5 · STUDY STATE

### PR-106 — realized discretionary study

**Part 1 COMPLETE and filed [VERIFIED].** Render + three benchmark arms + ten patches + two errata.
Verdict: **every cell SHAPE, not a finding** — n = 14/7/9/12/24, all under the 30 gate. The
pre-registered outcome arrived as predicted.

The three findings that matter and should not be lost:

1. **B1 and B3 are direction-confounded wherever inverse instruments sit** — semis (13 of 14),
   crypto (5 of 12), OTHER (12 of 24). For an inverse vehicle the differential records whether the
   *directional call* was right, not vehicle efficiency or selection. Clean only in ENERGY and
   METALS. **30 of 66 units (45%) are inverse.**
2. **B2 is the only confound-free arm** — it compares an instrument against itself at a fixed
   horizon, so direction cancels. It reads cleanly in every cell **and shows no consistent
   pattern.** That is part 1's strongest honest statement.
3. **The only clean cell is ENERGY and it has seven units.** Semis reverts to effectively
   single-instrument at unit level (12 of 14 are SOXS) — R-IV.86-b's original finding survives and
   EDGE's reversal of it was drawn from map membership rather than traded units.

**Part 2** — options cells, registered, spec closed, **gated on the RH realized backfill**.
**PR-107 candidate** — expression-class comparison on the 8 dual-expression tickers (BITX GDX GUSH
SOXS SQQQ TSLQ URA XLE), the only underlyings expressed both as ETFs and options. Registered as a
candidate, not scheduled; confounded by account (all ETF expression is Fidelity, all options RH),
so any finding is "class-or-account" absent a within-account counterexample.

### Track A — signal-layer

PR-100..105 filed and graded. **Confirmatory counter: 1-of-2** — PR-102 FAILED (sell_the_rip SHORT
UNSTABLE; the aggregate 54.4% is a March-era fossil, Era-2 reads 22.6% with candidate-expectancy
−2.94), PR-105 CONFIRMED (HOLY_GRAIL_1H KILL-CONFIRMED both directions, no flip across the friction
band). **Caveat board entry live:** sell_the_rip SHORT era-conditioned figures govern; the aggregate
does not.

**The infrastructure verdict stands as the study's honest headline:** the system measures signal
mechanics well and realized edge not at all. Build order: trade↔signal linkage (REC-006) · cost
model at grading · NUMERIC migration (REC-005) · intraday grading method.

### Triton forward window

**Registration ratified R-IV.229, T0 = 2026-09-03 [VERIFIED via TRITON's relay].** Gate bb2ae40c /
blob 1fd693ff. EDGE's §8 whole. The window clock begins at the first session after P1/P2 verify
live — **not at T0** — and BUILD is queue position one.

**EDGE's functions on this registration, now spine's:**

- **Tripwire adjudication (T1–T7).** T1 is the sharpest: the sealed count must read **843 at every
  read, forever**; deviation is a **seal breach, not a discrepancy**. T7 (volume outside the
  ~1,900–8,400 band) is deliberately **not** a HALT — a volume surprise is emitter information.
- **C3/C4 evaluation at window close**, against the no-flip band (0.10 / 0.25 / 0.50).
- **Criterion (v) execution**, if and only if the window passes, under the firewall, CC-QUERY as
  blind executor. **The mandatory face statement rides verbatim:** *at n = 828 the sealed holdout
  cannot confirm an effect; it can only fail to refute one. A PASS means the out-of-regime sample
  does not contradict. It may not be cited as independent verification.*

### Holdout

Pinned: **MAX_ID 377783 · n = 843 · effective 828 · k = 15** permanently-ungradeable index rows
(SPX 6, SPXW 6, RUTW 2, VIX 1, RUT 0). Permanence is **inferred from symbol class, not measured on
the 15** — one further read of `prior_5d_ret` would settle it and sits outside the R-IV.140
authorization. **The gate must never be phrased "fully graded"** — 15 rows never grade, so a
completion monitor keyed on it waits forever. A validation criterion is a **separate CONFIRM
registration, not yet drafted.**

---

## §6 · STANDING LAWS SPINE INHERITS

**Map §0 instrument trust rules** — R1 MCP-transport timestamps DEGRADED (Denver lens; retirement
path DEF-MCP-LENS-TZ) · R2 planner estimates DISCARDED, COUNT(*) or nothing · R3 strategy_health
"expectancy" inadmissible (F-EDGE-001) · **R4 written realized_pnl is the ONLY admissible realized
figure; never rebuild P&L from quantity × parts.**

**Charter laws** — pre-registration files and grades *before* queries run · direction-conditioned
populations, pooling structurally impossible · n-gates render INSUFFICIENT with accumulation rate,
never a verdict · the Track-A fence on every artifact · exclusions **enumerated, never
bare-counted** · sections supersede whole, never splice · a rebase invalidates SHA-identity checks
("not an ancestor" never proves "not pushed") · blend from stored values, never displayed ·
aggregations ship grain-labeled · **commit+push vs commit-HOLD stated explicitly.**

**The two mechanical checks**, both cheap and both proven: the **future-conditional verb scan**
(§1.3), and the **digit scan before any disclosure-subject relay** — surviving digits attached to a
ticker mean the warning *is* the leak.

**Verify-before-mutate at the ferry layer** — clearing staged copies on an unverified filing claim
destroys the only other copies.

**RECALL MAY PROPOSE; ONLY THE ARTIFACT MAY ASSERT** — and its standing check: *did I READ this
value in this session, from an artifact whose scope matches the claim?* If it was inferred,
complemented, borrowed from an adjacent scope, recalled as a status, still moving, diagnosed from a
symptom, already-fixed-somewhere-else, or agrees with expectation for a reason not established — it
renders **NOT DETERMINABLE FROM THIS ARTIFACT**, not as a number.

---

## §7 · ONE OPERATOR GATE — for the PIVOT pass

`hub_get_market_profile` is PYTHIA-fed. **The survivor set is six tickers: AMD, AMZN, IWM, RKLB,
SPCX, SPY.** QQQ's feed died 2026-09-01 10:30 ET; SMH 11:30 ET.

A dead ticker's market profile **renders with ordinary formatting** — fake-healthy at the tool
layer, the class Map §5 documents and the hub's own honest-seam standard forbids.

The PIVOT pass is where the **principal** rules on EXTEND, this registration, and the 2.7% spend.
**An MP corpse read into that sitting is the worst-sited stale read available on this board**,
because its consumer is the one person whose decisions no other lane reviews. Gate every MP read on
per-ticker last-event freshness, loudly, or skip MP for non-survivors and say so on the pass's face.

---

## §8 · CLOSING

EDGE was chartered to determine whether the system has trading edge, honestly. The answer it
reached, and the answer it should be remembered for, is that **the question was not yet answerable
— and it proved why rather than guessing.** Phase 0 convicted four instruments. Track A produced
one confirmed kill and one failed confirmation and reported the counter as 1-of-2 rather than
citing the winner. PR-106 part 1 rendered every cell SHAPE because every cell was under gate.

The lane's own errors are enumerated in the ledger it built, and every one was caught by another
lane. That is the finding the ledger exists to preserve: **the check does not work from inside the
lane that needs it.** Consolidation into spine removes a reader. Whatever replaces it, the function
that mattered was never the analysis — it was the second pair of eyes that refused to take a
reassurance.

**Nothing in this document is owed back to EDGE. Everything in it is owed forward.**
