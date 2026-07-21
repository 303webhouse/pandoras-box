# TRITON-EXPLORE — Exploratory pattern mining (hypothesis generation only)

**Date:** 2026-07-21 | **Author:** Coordination lane (Fable), at Nick's request
**Role separation, strict:** This brief is EXPLORATION — it generates hypotheses. `2026-07-21-triton-shadow-audit-brief.md` stays confirmatory and untouched (executes ~07-27). **Holdout law: any row still pending grading as of this brief's run date is NEVER queried here — those rows are the out-of-sample set that later validates whatever this brief finds. Do not peek, do not summarize, do not count them beyond noting the pending total.**

## Task 0 — file into place
Arrives at repo root. `git mv` to `docs/codex-briefs/2026-07-21-triton-explore-brief.md`, pathspec-commit, push. Read-only thereafter; runs whenever a CC slot opens. Does not preempt the DEF-SIGNAL-METADATA reduced-scope fix; must not run concurrently with the 07-27 audit.

## Phase 0
1. **Schema map** of `triton_flow_shadow`: direction field, magnitude/premium/conviction/type fields, ticker, event timestamp, grading columns. Report what exists — analyses below adapt to the real schema.
2. **Instrumentation rule (mandatory):** naive timestamp columns in this database are correct UTC. Read them via `::text` casts in any join logic — the `mcp__postgres__query` serializer falsely adds +6h to naive columns on display (proven in `docs/codex-briefs/def-signal-metadata-phase0-findings.md`). Do not let a display artifact contaminate a time join. This program has already been fooled once this week.
3. **Point-in-time inventory:** list which context tables have genuine historical coverage for 2026-07-02 → present (candidates: regime/stable-regime logs, nightly sector relative strength, bias composite snapshots, market tide, hydra scores, `uw_daily_burn`). Rule: a join is only honest if the context value was knowable at the signal's timestamp. Anything without history (e.g., VIX-at-signal forensic flags exist only post-DEF-ENRICH) goes on the **log-going-forward list**, not into analysis.

## Analyses — graded rows only
1. **Within-Triton cuts (no joins, cheapest first):** aligned_ret (= fwd_ret for bullish-flow rows, −fwd_ret for bearish) per horizon (1d/3d/5d), cut by: ticker and sector, day-of-week, time-of-day bucket, magnitude/premium terciles (per real schema), and clustered-vs-singleton detections (multiple same-ticker same-day fires vs lone fires).
2. **Point-in-time context joins** (inventoried tables only): aligned_ret + hit rate by regime state at signal time, ticker's sector RS bucket, market tide agreement/disagreement.
3. **Honesty requirements:** report the total number of cuts examined; any bucket with n<50 is labeled anecdote, not finding; effect sizes with 95% CIs, no significance theater; every table shows n.

## Output
`docs/strategy-reviews/triton-explore-2026-07.md`: all tables, then a **candidate hypothesis list** — each entry states the feature, the direction of effect, a mechanism guess (why would options flow work better under this condition?), and a pre-specified holdout test — plus the log-going-forward list for features lacking history.

## Handoff after output
The doc feeds an **Olympus interpretive pass in a fresh chat** (not this one): DAEDALUS on flow mechanics (sweep vs block, DTE, premium — which patterns have an options-market reason to exist), PYTHAGORAS on structural context, THALES on regime/narrative plausibility, URSA assigned to kill every pattern he can. Surviving hypotheses get validated against the matured holdout AFTER the 07-27 audit. Exploration → interpretation → out-of-sample confirmation, in that order, never backwards.

## Constraints
Read-only SQL. Pathspec-only commit of the output doc. `docs/workstreams.md` ledger update. ACK with doc path + the top-3 candidate hypotheses in one line each.
