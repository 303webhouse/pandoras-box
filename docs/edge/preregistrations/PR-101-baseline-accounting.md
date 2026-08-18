# PR-101 — Baseline Accounting, Gate-PASS Pairs
Status: REGISTERED · Filed 2026-08-18 · Mode: DESCRIPTIVE
Inherits PR-100. No hypotheses, no thresholds, no verdicts.
POPULATION: the seven §6 gate-PASS pairs — Holy_Grail L/S, Artemis
L/S, CTA Scanner L/S, sell_the_rip S — each reported in BOTH strata
(NON-DISMISSED primary table, DISMISSED parallel table).
METRICS per pair per stratum: n by outcome bucket; T1+ + Wilson CI;
candidate-expectancy (mean, median, p10/p90 of outcome_pnl_pct,
labeled per PR-100); days_to_outcome (median, p90); excursion
summary (median MFE%, median MAE% — named excursion); monthly
accrual table (in-DB month buckets).
DONE-WHEN (charter Phase 1): one auditable document, zero unlabeled
numbers, every table carrying n, stratum, horizon, and seam labels.
Data integrity: signals VALUE · signal_outcomes VALUE ·
outcome_pnl_pct DEGRADED-by-method (§4, labeled) · MCP transport
timestamps not used (in-DB bucketing only).
Multiple-comparisons: descriptive; no tests in this PR.
