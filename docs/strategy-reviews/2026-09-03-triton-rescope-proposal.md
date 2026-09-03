# TRITON RE-SCOPE PROPOSAL — EXTEND · FORWARD WINDOW · LEG RE-FOUNDING

**Filed by:** OLYMPUS-TRITON · **Under:** R-IV.152 (commission) · R-IV.190 (clock)
**Authored:** 2026-09-03 · Clock: filing commit `ae14b6f0` 2026-09-03 02:56:51Z, due 09-04 02:56Z — filed inside the window.
**Line endings:** LF only, 0 CR bytes; the authored sha256 is over these raw bytes, working tree = blob (gate-value convention).
**Inputs, all consumed from origin:** audit artifact `docs/strategy-reviews/triton-shadow-audit-2026-07.md` (blob `adad5b5f`) · element census `docs/edge/results/2026-09-01-triton-element-tracking-census.md` · k/burn artifact (sha256 `4557c775…`) · holdout registration `docs/edge/preregistrations/triton-holdout-registration-2026-09-01.md` · `docs/conventions/verification-laws.md` (ratified R-IV.167; header annotation update pending) · PR-104 · PR-106 Part 1.
**Decision rights:** recommendation only. Ratifies at spine; closes at an Olympus/PIVOT pass with the principal (§7). No build orders issue from this document.

---

## §1 · DISPOSITION — EXTEND SHADOW

Adopting the audit's face recommendation, mapped honestly onto the June verdict semantics: the evidence is "either-alive" — 3d aligned hit 52.10% [50.84, 53.35] clears 50%, both directions point the intended way unpooled — so the KILL branch is not selected; and "alive" was pre-registered as *unblocked behind gates*, never as *build*. Against promotion, on the artifact's face: 5d straddles 50%; excess over drift is +0.31 on a **costless** basis; the premium terciles **invert** the promotion hypothesis (largest tercile worst, 48.77%); weekly hit rate spans 22.70%→82.54% with the aggregate carried by a single week. EXTEND is the alive branch executed with its gates made explicit in §2.

Scope boundary intact: this disposes of the **sweep premise only**. Dark-pool, absorption, tide, and timing pillars are untouched in both directions.

## §2 · FORWARD-WINDOW REGISTRATION SKELETON

Two out-of-sample instruments, never conflated:

- **SEALED HOLDOUT** — n=828 (843 − 15 index-ungradeable), `id ≤ 377783`, fired 08-17→08-31, one contiguous post-Warsh regime window. Read **once**, against a criterion registered blind under the R-IV.186 firewall (authored by EDGE + OLYMPUS-TRITON without CC-QUERY input, spine-ratified, CC-QUERY blind executor). The registration's §6 not-a-kill / not-a-rescue clauses govern the reading.
- **FORWARD WINDOW** — new accumulation under repaired instrumentation. T0 = spine ratification of this registration. Population: rows fired ≥ T0 (all carry `id > 377783` by construction). Duration: 7 trading weeks, then forced verdict.

Criteria, operationalized from the artifact's (i)–(v). Each is §1.1-compliant: expected satisfaction declared at registration, measured against the population, HALT on declared-vs-measured mismatch, 0%/100% agreements demonstrate reachability.

1. **(i) Grading continuous.** Grader registered in `signals_freshness` with an OBS-0 liveness sentinel; skip-reason field live (closes DEF-TRITON-GRADER-NO-SKIP-REASON); zero outage days, an outage being no grading run on a completed session holding gradeable rows.
2. **(ii) Index flow classified.** `UNGRADEABLE-NO-SERIES` assigned at ingest for cash-settled index symbols; completion monitors target the gradeable subpopulation only. Proxy-grading against SPY/ES series remains an open option, not a commitment.
3. **(iii) Weekly stability, pre-registered:** aligned 5d hit rate above 50% in **≥ 5 of the 7 forward weeks**. A week with n < 100 renders NOT COMPUTABLE and extends the window one week, maximum two extensions. The 22.70→82.54 instability was the decisive negative of the last window; it is now a criterion, not an observation.
4. **(iv) Friction-adjusted excess:** spread + commission modeled at principal clip size ($100–300); criterion = 3d aligned excess over drift **> 0 after modeled costs**. Converts the costless +0.31 into an executable claim or a retirement.
5. **(v) Holdout confirm:** the sealed 828 read once, post-forward-window, per the firewall. Criterion text is DRAFT-FOR-CO-AUTHORSHIP with EDGE; proposed shape — directional consistency (BULL mean ≥ 0 AND BEAR mean ≤ 0 at 3d) plus 3d aligned hit ≥ 51% — with numbers final only at the blind registration.

**Verdict semantics, declared now:** all five pass → PROMOTE to L1a-gate review. Criterion 3 or 4 fails → **RETIRE the sweep premise** — this time on stability/cost evidence rather than instability of evidence. Mixed otherwise → one extension maximum, then forced verdict. No third EXTEND without a new instrument class: a leg, not more of the same.

## §3 · R-IV.152 ANSWERS

**Q1 — Triad re-founded.** `flow AND dp AND tide → fully_confirmed` is dissolved as a design commitment: two of its three legs have never persisted a row, so it was never a tested design — only a drawn one. Replacement principle (ratified R-IV.154; this document is its worked example): **no leg gates anything until it has accumulated history and passed its own pre-registered marginal test; confluence is an interaction hypothesis and cannot precede its marginals.** Legs with history today: sweep flow (this EXTEND) and footprint (558 rows, live since 03-18; marginal test never run — eligible for its own registration after the forward window ships). Dark pool and tide are candidates, admissible only post-sink, post-accumulation, post-marginal-test. The `fully_confirmed` state is retired from the design vocabulary.

**Q2 — Flow-leg provenance: UPGRADE, not replace.** `flow_events` (97,201 rows, yfinance-backed, single `railway_poller` source) violates UW-primary but is disclosed and consistent, with continuity value. Overlap migration: UW fields dual-written source-tagged → agreement validated → primacy flips, yfinance demoted to fallback. **AEGIS budget sizing precedes any call increase** (07-17 watchdog-shed precedent). Priority MEDIUM — mislabeled-risk class, not active harm.

**Q3 — Sinks: typed tables preferred; `uw_snapshots` CANDIDATE-NOT-PREFERRED.** Its shape (`dashboard_type` · `time_slot` · `raw_summary` · `signal_alignment`) is a periodic dashboard-capture semantic; overloading saves one migration and muddies two meanings. If legs are ratified as candidates: `darkpool_prints` (typed, per-print) and `market_tide_history` (typed, per-snapshot), and the dp enricher **additionally writes its computed keys into `enrichment_data`** — the one-line fix for the silent no-op. The never-called `insert_uw_snapshot()` writer is flagged for deprecation review, not this lane's call.

**Q4 — Vacuous-conditioning sweep: COMMISSIONED, NOT YET RETURNED** — stated per the complement discipline rather than assumed. What the census already proves: no dark-pool key has ever existed in `enrichment_data`, so any extant reader has been reading absence since inception. Declared expectation: zero scoring consumers (`confluence_bonus=0` by founding design); display-path readers possible. Tripwire on return: any scoring consumer found → immediate defect registration at elevated severity. No disposition in this proposal conditions on the result.

**Q5 — Whale: FOLD-AND-PARK.** Not keep — dormant five months, two rows ever. Not kill — the audit's scope boundary rules the verdict silent on Mode-A absorption. Folded: the dormant path is design space for a future leg, revivable only by its own registration, which must answer why revival targets anything mega-cap-shaped when **two independent instruments converge against that tier** — PR-106's worst personal cell and the audit's premium-tercile inversion. The `DARK_POOL` classification half is contingent on the dp sink existing; it cannot classify on data that does not persist. The commissioned reachability read is not yet returned; parked status does not condition on it.

## §4 · SINK ECONOMICS + PAUSE-OR-PERSIST

Measured (k/burn artifact `4557c775…`): `darkpool_ticker` 12,320 calls, ~251/day, 07-09→09-01, weekday-shaped, live. `market_tide` 2,926 calls, ~71/day, Redis 60s TTL. **15,246 metered calls — 2.7% of all UW spend — for data persisting nowhere**, and the two discarded feeds are exactly the two missing triad legs. `_TOTAL` caution in its narrow ratified form: reconciles 49 of 54 days; a small `_TOTAL`-minus-named residual is not evidence of an untagged caller.

**Call: PERSIST, with a hard pause date.** The spend's only value is the sink, and the sink's economics are favorable precisely because acquisition is already running and paid. Therefore: sink briefs release to BUILD's queue on ratification of this proposal (builds were correctly HELD until it, R-IV.152). **If no sink is live by forward-window T0, the dark-pool poller pauses by flag** — rollback-flag pattern, 48-hour watch; any breakage identifies the hidden runtime consumer the Q4 sweep has not yet found, which is itself diagnostic. Tide follows the same rule at lower stakes. Proposed queue order, ATHENA/spine governing: grader mechanism diagnosis → sinks → flow-leg upgrade.

## §5 · COLLECTOR DESIGN LAW

Every collector and consumer this track registers forward carries the five defects as requirements:

1. **Liveness:** OBS-0 sentinel + `signals_freshness` registration, day one (DEF-TRITON-GRADER-DARK).
2. **Retention gated on consumer liveness** — no deletion policy may outrun the liveness of any consumer holding an unexercised claim on the row (DEF-TRITON-RETENTION-DARK).
3. **Field liveness at registration:** every conditioning field declares expected cardinality and satisfaction rate; HALT on mismatch; 0%/100% agreements demonstrate reachability (DEF-TRITON-DEAD-FIELDS → verification-laws §1.1).
4. **Every skip records its reason,** taxonomy enumerated at design time (DEF-TRITON-GRADER-NO-SKIP-REASON).
5. **Ungradeable-by-construction classified at ingest;** completion monitors target the gradeable subpopulation (DEF-TRITON-INDEX-UNGRADEABLE).

Conventions binding by anchor — `docs/conventions/verification-laws.md`, ratified R-IV.167: **§1 `#null-trigger`** including the §1.1 registration-time law · **§2 `#scoped-count`** — every census-shaped figure ships with its complement's status · **§3 `#narrow-caution`** — every instrument caution names the one inference it protects. Pending at EDGE under R-IV.198(d): ruled-key uniqueness measured before first use; adopted provisionally here for any key this track mints.

## §6 · REGISTER — DEFECTS + OPEN ITEMS

**Registered:** GRADER-DARK (P2 — **RECOVERED 09-02 20:41:55Z, not resolved**; mechanism diagnosis commissioned; the watchdog-premise contradiction — 307 graded rows on fire-dates recorded as fully shed — and the re-key rider are dual-routed into that diagnosis) · RETENTION-DARK (P3 — fix BLOCKED pending residue documentation; any restored policy must be grader-gated) · DEAD-FIELDS · GRADER-NO-SKIP-REASON · INDEX-UNGRADEABLE (ongoing — index rows continue to arrive ungradeable in the future cohort).

**Requested, unconfirmed:** DARKPOOL-NO-SINK · TIDE-NO-SINK — mechanism now measured; registration re-requested with this filing.

**Open:** Amendment 2 grade-identity check on the 09-02 repair (53 mixed-path rows entered audit_n; retroactive sample re-grade requested) · RELEASE clause restoration into the holdout registration (demonstrated hole, per the halt doc) · Q4 sweep result · Q5 reachability read · verification-laws header still carries the pre-ratification citation bar (one-line BUILD fix).

## §7 · ROUTING

Per the audit artifact's face and R-IV.190: final disposition is an **Olympus pass with the principal — PIVOT synthesis**, spine-ratified. The pass decides: (a) EXTEND ratification and the forward-window registration of §2; (b) the PAUSE-OR-PERSIST confirmation — the 2.7% is the principal's spend; (c) collector scope and queue release under §3–§4; (d) the plain-language accounting this track owes the principal: six days of machinery, one exposure event caught in twenty-five seconds by its own tripwire, a premise neither killed nor promoted, and an instrument set now clean enough that the next answer will be believable.

**Authorship asserts content; delivery asserts on BUILD's read.**
