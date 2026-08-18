# PR-100 — Track A Definitions Lock · v1.1
Status: REGISTERED · v1.0 filed 2026-08-18 pre-data; v1.1 amends
pre-grading, pre-data, to conform to spine criteria (a)(c)(e)(f)(g).
No Track A query has executed as of this amendment.
Mode: DEFINITIONS (DESCRIPTIVE→EXPLORE mapping per spine: all
descriptive PRs are EXPLORE for eligibility — findings become
future pre-registrations, never conclusions).
DIRECTIONS LAW (a): LONG and SHORT are separate populations. No
table, metric, or denominator may pool directions; a pooled figure
is inadmissible and must not be computed. No exceptions in Track A.
STRATA (b): NON-DISMISSED = status IN (ACTIVE, COMMITTEE_REVIEW,
EXPIRED); DISMISSED separate; never pooled. NON-DISMISSED ≠
operator-shown (Map §6 visibility law); tags are time-varying
(DEF-L0-TAG-STRIP-ON-RESCORE); visibility strata out of Track A.
THREE-LEDGER DENOMINATOR LAW (c): every denominator carries its
coverage accounting per Map §5 — matched (in-table) + orphaned
(side-ledger n for the population) + unwritten (no-row n) — stated
alongside the table. Clean windows cited BY Map section (§1 eras,
§2 deaf windows).
RESOLUTION DEFINITIONS (e): per DEF-EDGE-SPEC-B2, 'PENDING' is a
string; outcome IS NOT NULL is not a resolution test. Buckets:
verdict = STOPPED_OUT/HIT_T1/HIT_T2 · administrative = EXPIRED/
INVALIDATED · in-flight = PENDING · no-row = join miss. EXPIRED
TREATMENT, explicit: outcome=EXPIRED is its own administrative
bucket, EXCLUDED from verdict denominators, reported alongside
with its n; status=EXPIRED remains inside NON-DISMISSED (axes are
independent — Map §5 axes law).
N-GATE RENDERING (f): gate = 250 verdicts per direction per
stratum. Sub-gate cells render exactly: "INSUFFICIENT n=<x> ·
accumulation ≈<r>/wk" — never a verdict, never an unlabeled rate.
TRACK-A FENCE (g): every Track A table, figure, and summary
carries: "SIGNAL-LEVEL — inadmissible as realized/after-cost
performance until Track B exists (F-EDGE-001 boundary)." Required
output element; no downstream artifact may shed it.
ANCHORING: signals-anchored exact join on signal_id (varchar);
orphans (370 @08-10) live in a separate outcomes-anchored side
ledger, never merged. EXCLUSIONS (listed, never silent): smoke/
test/case-variant (8); Crypto Scanner pre-08-04 era (UNAVAILABLE);
Footprint_Imbalance, CVD_ABSORPTION (method-incompatible, Map §6).
WINDOWS: id-range keyed; era boundary ids computed IN-DB and
recorded (lens-immune, §0-R1); accrual horizon stated per table.
METRICS: T1+ = (HIT_T1+HIT_T2)/verdicts with Wilson 95% CI;
candidate-expectancy = mean signals.outcome_pnl_pct, ALWAYS
labeled projected/costless/daily-bar/pessimistic-same-bar (§4);
excursion (MFE/MAE) ALWAYS named excursion, never expectancy
(spine law 08-18); holding = days_to_outcome. INSTRUMENTS: §0
R1–R4 inherited; SELECT-only verbatim CC path; heavy scans outside
07:30–14:00 MT.
