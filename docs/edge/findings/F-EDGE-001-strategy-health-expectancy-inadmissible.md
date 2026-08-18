F-EDGE-001 — strategy_health "expectancy" is not expectancy
Status: ACTIVE OPERATOR CAVEAT (spine-elevated, 2026-08)
The Watchdog computes expectancy = mean(MFE% − MAE%): excursion
asymmetry from max_favorable/max_adverse, with no exits, no realized
P&L, no costs. Grades A–F, degradation alerts, and committee-facing
health all key on it; <20 signals/30d auto-grades F, so quiet and
broken are indistinguishable. VERDICT: inadmissible as edge evidence
under charter §7 (expectancy after costs). Operator caveat: read
strategy_health grades as excursion diagnostics only. Remediation
routed as REC-EDGE-004. Evidence: health_monitor.py
(_grade_from_metrics, expectancy_components); QS-02/QS-03 results.
