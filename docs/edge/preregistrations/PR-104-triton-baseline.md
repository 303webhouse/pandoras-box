# PR-104 — Triton Shadow Baseline
Status: REGISTERED · Filed 2026-08-18 · Mode: DESCRIPTIVE
Inherits PR-100 where applicable; Triton sits OUTSIDE
signal_outcomes by design (own table, independent grading).
GATE (QS-01 pattern): introspect triton_flow_shadow columns first;
per-direction reporting gated on a direction column existing —
if absent, report pooled WITH THE POOLING STATED IN THE TITLE and
file a defect against the shadow schema.
POPULATION: graded rows (n_graded; 4,174 @08-18 per QS-03-E1
rerun). METRICS: fwd_ret_1d/3d/5d distributions (mean, median,
p10/p90) per direction per horizon; ungraded-tail accounting
(late-fire-awaiting-horizon vs stuck, dated); accrual by week.
LABELS: independent grading path, costless, candidate-tier.
Multiple-comparisons: descriptive; no tests.
