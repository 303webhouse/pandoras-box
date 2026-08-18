# PR-100 — Track A Definitions Lock
Status: REGISTERED · Filed 2026-08-18, before any Track A query ran
Mode: DEFINITIONS (this filing adds DESCRIPTIVE and DEFINITIONS
modes to template law; spine grades the addition)
All Track A PRs inherit these definitions; none may redefine them.
STRATA: NON-DISMISSED = status IN (ACTIVE, COMMITTEE_REVIEW,
EXPIRED); DISMISSED separate; NEVER pooled. NON-DISMISSED ≠
operator-shown (Map §6 visibility law); suppression tags are
time-varying (DEF-L0-TAG-STRIP-ON-RESCORE) — visibility-conditioned
strata are out of Track A scope, joint with STRIKE later.
OUTCOME BUCKETS: verdict = STOPPED_OUT/HIT_T1/HIT_T2 ·
administrative = EXPIRED/INVALIDATED · in-flight = PENDING ·
no-row = join miss. Status and outcome are independent axes.
ANCHORING: signals-anchored exact join on signal_id (varchar).
Orphans (370 @08-10) are a separate outcomes-anchored side ledger,
never merged into signals-anchored tables.
EXCLUSIONS: smoke/test/case-variant rows (8); Crypto Scanner
pre-08-04 era (0 outcome rows — UNAVAILABLE); Footprint_Imbalance
and CVD_ABSORPTION (method-incompatible, Map §6) — listed, not
silently dropped.
WINDOWS: id-range keyed. Era boundaries computed IN-DB as "max id
with created_at < boundary-date", recorded in results (lens-immune
per §0-R1). Deaf windows produce absence, not contamination (Map
§2); accrual horizons stated on every table.
METRICS VOCABULARY: resolution facts from signal_outcomes (system
of record). T1+ rate = (HIT_T1+HIT_T2)/verdicts, Wilson 95% CI.
"Candidate-expectancy" = mean signals.outcome_pnl_pct — ALWAYS
labeled: projected, costless, daily-bar-graded, pessimistic
same-bar (Map §4); never presented as charter-§7 expectancy.
Excursion = max_favorable/max_adverse, ALWAYS named excursion
(spine ruling 08-18), never expectancy. Holding time =
days_to_outcome. n-gate: 250 verdicts per direction per stratum.
INSTRUMENTS: §0 R1–R4 inherited; SELECT-only via CC verbatim path;
heavy scans outside 07:30–14:00 MT.
