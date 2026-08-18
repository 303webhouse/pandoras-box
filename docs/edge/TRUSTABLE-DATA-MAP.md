# TRUSTABLE DATA MAP v1.0 — EDGE Phase 0 deliverable · 2026-08-18
Charter: EDGE lane v1.0. Every number cites its spec block; horizons
labeled everywhere; seam vocabulary: VALUE / DEGRADED / UNAVAILABLE /
DISCARDED.

## §0 · INSTRUMENT TRUST RULES
R1 — MCP-transport timestamps: DEGRADED always. Serializer renders
naive-UTC through a Denver lens (+6h MDT / +7h MST; session_tz =
Etc/UTC — the skew is the serializer alone). Convictions: QS-01
B-block; 07-31 drill reading (to_char exhibit QS-04-1: stored
07:02:16 vs read 13:02); ORPH-1b DST flip at 03-08; caught live
in-flight twice during the 08-18 batch. Rule: compute intervals,
buckets, and text renders IN-DB; correct any transport-rendered
timestamp by the session offset before quoting. RETIREMENT PATH:
DEF-MCP-LENS-TZ (spine-authored, P2) — on acceptance (rows
27774/27777 identical via MCP tool and SQL to_char), converted
surfaces exit DEGRADED.
R2 — Planner estimates (n_live_tup et al.): DISCARDED. Three
stats-rot sites (diff_log 0→11,313; forward_returns 0→22,942;
stable_daily_bars). COUNT(*) or nothing. (REC-003)
R3 — strategy_health "expectancy": inadmissible as edge evidence —
costless, exit-blind MFE−MAE excursion math (F-EDGE-001, filed).
Its 41 grade-transition alerts inherit the defect.
R4 — (spine standing caveat, 08-17, all lanes) written realized_pnl
is the ONLY admissible realized figure; never rebuild P&L from
quantity × parts until the NUMERIC migration lands (REC-005).
Conventions: blend from stored values, never displayed ones ·
verbatim execution protects against repair, not transcription —
results headers record any spec-diff · every non-census figure cites
its spec block · horizons labeled on every status claim · sections
supersede whole, never splice · a rebase invalidates SHA-identity
checks — verify the successor SHA or the content; "not an ancestor"
never proves "not pushed" · specs are written to survive an executor
who doesn't know what the answer should look like: exhaustive dumps
over targeted lookups, errors returned unedited. Windowing:
id-ranges preferred; in-DB time-bucketing is VALUE.

## §1 · ROSTER, ROSETTA, DELIVERY PATHS
Naming has three layers: RAW strings frozen in the DB · CODENAMES
(display layer, backend/config/strategy_aliases.py) · RELABELS
(in-pipeline: any LONG scoring ≥85 → APIS_CALL behind the L0 liquid
gate; any SHORT ≥85 → KODIAK_CALL). Apis/Kodiak are tiers, not
strategies. The signals table is a palimpsest of handler eras —
every status carries its horizon. signal_outcomes.signal_type is a
SECOND vocabulary, never rosetta'd; seven orphan types (PHALANX_*,
BULL_WALL, MANUAL_LONG, RESISTANCE_REJECTION, PULLBACK_ENTRY,
TWO_CLOSE_VOLUME) have no signals-side counterpart — emission
occurred that signals never recorded.
Roster (counts = QS-01-C0, horizon 08-03; statuses as labeled):
Holy_Grail 6,146 — LIVE (TV + server_scanner)
Artemis 3,385 — LIVE (TV; absorbs "sniper"-era alerts)
sell_the_rip 2,983 (Achilles) — LIVE (TV + server_scanner)
CTA Scanner 2,404 (Midas/Hector types) — LIVE (TV + cta_scanner)
Crypto Scanner 830 @08-03 — died 07-03 (TV-only; not in the 07-24
  Pythia rebuild set); RESUMED ~08-04+ — adjudicated from QS-04-2/4
  (45 covered rows, all post-08-03; zero pre-August coverage in its
  lifetime) and CORROBORATED by STRIKE-Q2 (Sat 08-15 attributes
  entirely to Crypto Scanner/ATOM-USD ×12, path ungated by design).
  Resumption UNORDERED — governance flag open; onset dating QS-05-1.
Footprint_Imbalance 455 @08-03 (514 @08-18) — LIVE; ungradeable
  under current method (§6).
CVD_ABSORPTION 349 — source-killed 07-23 (+1 quarantined
  CVD_DIVERGENCE 07-24). Session_Sweep 149 — TV dark since 07-22;
  engine path fired only 07-22 (cutover-shaped, unresolved).
Scout 44 → "Scout Sniper" (B.2) · Exhaustion 13 (~03-31 tombstone) ·
Sniper 7 → Artemis handler (~04-16) · Whale_Hunter 2 (Triton) ·
smoke/test/case-variant 8 — excluded from all analysis.
Never-materialized / adjacent: Nemesis — BUILT (live countertrend
gate, wrr module, pre-mapped aliases), zero emissions = expected L2.
Icarus — never wired by the repo's own docstring; UNAVAILABLE by
construction. Funding_Rate_Fade + Liquidation_Flush — wired in the
crypto_setups engine (Binance-direct); write path proven exactly
once (3 Session_Sweep rows, 07-22); engine silent 27 days as of
08-18: UNAVAILABLE-in-practice. Triton — triton_flow_shadow: 6,321
rows firing continuously 07-01→08-17, 66.0% graded (QS-03-E1 rerun,
08-18); outside signal_outcomes by design.

## §2 · DEAF WINDOWS & DEATH CERTIFICATES
Charter P3 distinction: never-fired / fired-no-delivery /
delivered-no-grading. Census horizon 08-03T02:21Z (QS-01-C2);
tombstones 07-31 (QS-03-D1); QS-04 supplements 08-18.
Crypto Scanner: dead 07-03→~08-04 (TV alert not rebuilt in the
Pythia-only 07-24 resurrection); RESUMED ~08-04+ — see §1;
pre-August rows remain UNAVAILABLE for grading (no outcomes exist).
Session_Sweep: dark since 07-22 both paths; 07-22 reads as a
half-completed cutover; cause open. CVD_ABSORPTION: intentional
kill 07-23, not deafness. crypto_engine: UNAVAILABLE-in-practice
(§1). Superseded-not-deaf: Exhaustion ~03-31 · Scout ~04-09 ·
Sniper ~04-16 · Whale_Hunter ~04-24 (tombstone dating via
strategy_health; deaths were silent — background_task_failures
holds 0 rows, the failure log itself fake-healthy).
Fleet context: alert fleet crashed pre-07-24; resurrection covered
the Pythia fleet only; Circuit Breaker alerts never existed until
built 07-30. RULE: zero signals inside a deaf window = UNAVAILABLE,
never underperformance; per-strategy clean windows exclude the
above.

## §3 · CLOCK VERDICT
All four core tables (signals, signal_outcomes,
bias_composite_history, factor_readings) store TRUE UTC.
Adjudicated on two independent dates: 08-03 (ages +1h02/+1h02/
+10m/+10m) and 08-18 (15m/15m/3m/3m), QS-03 original + verbatim
rerun, both filed. Historical backbone: QS-02-D3 six-month
market-hours fingerprint tracking the 03-08 DST transition exactly.
DEF-TIMESTAMP-NAIVE-SHIFT: DEMOTED — spine ledger AMENDED 08-17 on
29b5bb7 evidence (write-defect → serializer-side read artifact).
Successor brief DEF-MCP-LENS-TZ (spine-authored, P2) delivered;
its acceptance retires §0-R1 for converted surfaces. The once-
queued write-side fix is dead. Standing rules per §0-R1.

## §4 · PRICE DATA & PROVENANCE
Internal price history DOES NOT EXIST: price_history = 0 rows (real
COUNT, QS-02-E2). Known consumers (get_spy_daily_closes,
get_price_bars, get_signals_for_backtest) return empty series
silently; endpoint blast-radius enumeration = open backlog.
RULES: every price series is EXTERNAL (UW primary, yfinance
fallback), per-series provenance labels, never mix providers inside
one test unlabeled (P10). GRADING PROVENANCE: score_signals walks
DAILY yfinance bars, stop-checked-before-target within each bar —
same-bar ambiguity resolves pessimistically; costs absent entirely;
intraday strategies on daily bars is a category error (§6).
Quote layer: DEF-QUOTE-PRIORCLOSE-VINTAGE stands (cross-source
verify SPY/QQQ/SMH prior_close); UW /option-contracts caps at 500
(pass expiry + option_type); greeks caller-side cap fix deferred.
signal_forward_returns: FROZEN June 7–9 batch (22,942 rows / 11,471
pre-June signals) — vintage artifact, not a pipeline.

## §5 · OUTCOME SYSTEMS, COVERAGE, REALIZED LAYER
signal_outcomes = SYSTEM OF RECORD; every confirmed reader sits on
it (grader; dashboard hit-rates; Watchdog→strategy_health→committee
via so.outcome). signals-side columns = projection/annotation under
the outcome_source guard (BAR_WALK · ACTUAL_TRADE/Ariadne ·
COUNTERFACTUAL · PROJECTED_FROM_BAR_WALK); dual-write atomic since
Phase C (05-09); the 11,313-row diff log records the one-time May
8–11 backfill; post-May divergence unlogged at that writer.
CREATION: PENDING placeholder with the signal (99.9% within 5s),
unconditional in the unified pipeline. 'PENDING' is a STRING — zero
NULLs; outcome IS NOT NULL is not a resolution test
(DEF-EDGE-SPEC-B2). AXES LAW (QS-04-2): status and outcome are
independent — EXPIRED-status with HIT_T2-outcome is common; neither
proxies the other. signals-side outcome=NULL is BY DESIGN for
EXPIRED/INVALIDATED; graded-ness keys on outcome_source there.
COVERAGE: 902 signals lack outcome rows, independently reproduced
(QS-04-4 = QS-02 reading key): Crypto Scanner 830 (entire pre-Aug
life) + ~70-row March pre-unification tail. Post-08-03 Crypto
Scanner rows ARE covered (CS-45). Auto-DISMISSED conflict signals
still get graded → all populations stratify by signals.status.
signal_options_expressions: 0 rows despite both entry points wired
and live, B2_SHADOW_MODE=true (STRIKE-Q2 CR-6) — fake-healthy
candidate, cause unattributed, build-lane queue.
RESOLUTION (08-02 snapshot): STOPPED_OUT 9,484 · HIT_T1 2,907 ·
EXPIRED 2,100 · HIT_T2 1,097 · PENDING 368 · INVALIDATED 287;
EXPIRED = age>10d regardless of price; resolver live. This
distribution is pooled across strategy/direction/status and is
INADMISSIBLE as performance evidence; stratified reads are Phase 1
(charter law 2).
ORPHANS — LIVE MECHANISM: 370 outcome rows with no parent (#370:
08-10, fourth era; profile Feb–Mar 141 / Apr–May 0 / Jun–Jul 228 /
Aug ≥1). Classes @08-03: 134 stem-twin-recoverable / 61 UUID /
174 structured parentless. Duplicates ZERO (re-tested at source) —
counts inflation-safe; but signals-anchored joins DROP orphaned
events → coverage accounting is a three-ledger sum: matched (G1v2)
+ orphaned (ORPH) + unwritten (902). Stem-matching is many-to-many
(~21× fan-out) — attribution-only, not a repair key without a
tiebreak.
REALIZED LAYER — THE PHASE-1 BLOCKER: trades/trade_legs carry the
admissible schema (pnl_dollars, pnl_percent, rr_achieved,
risk_amount, per-leg commission) but 342 rows link to FOUR distinct
signal_ids (~1%); trade_legs holds 36 rows. After-cost per-strategy
P&L is NOT COMPUTABLE today. REC-EDGE-006: APPROVED and routed
(spine 08-17) — joint read-only Phase 0 serving 006+005, then two
separate ATLAS-lens briefs; design laws bind the build: (a) every
new trade carries signal_id OR an explicit NO_SIGNAL/DISCRETIONARY
marker — absence becomes a statement, never a gap; (b) backfill
links only where derivable with stated confidence; underivable rows
stay unlinked and LABELED. Book state: canonical table is
Robinhood-RECONCILED through 8/17 EOD with an unreconciled
FIDELITY_ROTH sleeve (46 rows: 4 OPEN / 42 CLOSED) — an unmeasured
gap, not an absent one (P5). §0-R4 caveat applies. Fake-healthy on
record: Watchdog graded crypto_scanner daily through 08-17 across a
period with zero gradeable outcomes (F-EDGE-001); remediation
folded into REC-004 — strategy_health will render UNGRADED/DEAD for
zero-lifetime-outcome strategies.

## §6 · POPULATIONS & n, PER DIRECTION
Source: QS-04-2 (G1v2, horizon 08-18) at 29b5bb7; windows per §2.
SIGNAL-LAYER ONLY — §4 grading caveats apply; candidate-screening
figures, never edge claims (§7). Strata: NON-DISMISSED (ACTIVE +
COMMITTEE_REVIEW + EXPIRED statuses) vs DISMISSED (auto-conflict).
VISIBILITY LAW (STRIKE-Q2 CR-1/CR-3): NON-DISMISSED is not
"operator-shown" — surfacing is additionally governed by L0
surface-suppression (SUPPRESS_ALWAYS incl. HOLY_GRAIL_1H,
HOLY_GRAIL_15M, PULLBACK_ENTRY, TRAPPED_LONGS, ARTEMIS_LONG) plus
feed criteria (status='ACTIVE', <24h, user_action IS NULL, category
and feed_tier filters). Visibility-conditioned strata are a joint
Phase-1 × STRIKE axis. n-gate: 250 verdicts per direction. Verdicts
= STOPPED_OUT / HIT_T1 / HIT_T2. All figures independently
recomputed by CC-SHELL, 08-18.
NON-DISMISSED verdicts:
Holy_Grail LONG 2,753 @ 13.6% T1+ — PASS (zero T2 in entire
  history, both directions — structural)
Holy_Grail SHORT 3,023 @ 20.9% — PASS
Artemis LONG 1,598 @ 32.4% — PASS
Artemis SHORT 1,419 @ 37.8% — PASS
CTA Scanner LONG 1,280 @ 34.4% — PASS
CTA Scanner SHORT 461 @ 37.1% — PASS
sell_the_rip SHORT 1,623 @ 54.4% — PASS, with mandatory caveats:
  990 non-dismissed rows aged out unresolved (37.9% of graded) and
  volume is March-dominated (QS-01-C1) — sub-window stability
  required before any Phase-2 claim.
Insufficient n: Scout ~15 non-dismissed · Session_Sweep 3
non-dismissed · smokes.
DISMISSED strata: HG-L 347 @10.1 · HG-S 331 @14.5 · ART-L 375
@23.2 · ART-S 405 @33.1 · CTA-L 247 @30.4 · STR 320 @55.6.
FINDING — the conflict filter is NON-MONOTONIC: it strips worse
signals from HG/Artemis (dismissed mixes below non-dismissed) and
better ones from STR (55.6 vs 54.4), CTA-L likewise inverted. No
single directional bias exists; Phase 1 keeps strata separate
everywhere.
METHOD-INCOMPATIBLE: Footprint_Imbalance — ZERO verdicts ever,
either direction, either stratum (514 signals @08-18); population
is EXPIRED/PENDING by construction on daily bars. CVD_ABSORPTION —
165 verdicts, 100% DISMISSED; non-dismissed population = 14 rows,
all PENDING (source-killed with pendings stranded).
Open anomaly: CS-45 — resumption CONFIRMED (§1); onset dating
QS-05-1.

## §7 · VERDICT — WHAT THIS DATA CAN ANSWER TODAY
ANSWERABLE NOW (signal layer, labels attached): direction-
conditioned resolution mixes for HG / Artemis / CTA / STR at n≥250
per direction; non-dismissed-vs-DISMISSED divergence incl. the
non-monotonic filter; operator-visibility conditioning (joint with
STRIKE per §6 visibility law); era/deaf attribution; regime & bias
conditioning as PRE-REGISTERED Phase-2 tests (P6 caveats;
poisoned-factor exclusion re-runs mandatory).
NOT ANSWERABLE — every path routes through infrastructure:
charter-§7 EDGE (after-cost expectancy per direction) — grading is
costless AND realized linkage is ~1% (REC-006, now APPROVED, build
pending); intraday strategies (Footprint, scalp-class) until an
intraday grading method exists; anything citing strategy_health
expectancy or its 41 alerts (F-EDGE-001; corpse-grading fix folded
into REC-004); portfolio-level realized edge (P5 sleeve); any P&L
rebuilt from parts (§0-R4).
CONDITIONAL: Triton — 6,321 shadow rows firing continuously
07-01→08-17, 66.0% graded, independent grading path; candidate-
level analysis legal now; costs still absent.
THE INFRASTRUCTURE VERDICT (charter's predicted honest outcome,
formally accepted by spine 08-17 as the success case): the system
measures signal mechanics well and realized edge not at all. Build
order: trade↔signal linkage (REC-006, approved) · cost model at
grading · NUMERIC migration (REC-005, ruled) · intraday grading
method. Phase 1 OPENS at the signal layer under these labels;
realized-layer Phase 1 gated on the REC-006 build. Phase 2 remains
pre-registration-only, direction-conditioned, test-count disclosed.
Open anomalies carried: CS-45 resumption (confirmed, UNORDERED —
governance), live orphan mechanism (#370).
