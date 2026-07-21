# TRITON-AUDIT — Shadow promotion audit (analysis only, no code changes)

**Date:** 2026-07-21 | **Author:** Coordination lane (Fable)
**Execute on/after:** ~2026-07-27 — deliberately delayed so the ~1,005 currently-pending rows finish their forward-return grading windows, taking graded n from ~1,474 to ~2,400. The audit gets materially stronger by waiting; nothing else depends on it.
**Scope:** read-only SQL + analysis + one output doc. No production code, no schema, no config changes.

## Task 0 — file into place
This file arrives at repo root. `git mv` to `docs/codex-briefs/2026-07-21-triton-shadow-audit-brief.md`, pathspec-commit, push. Execution waits for the date above.

## Context
`triton_flow_shadow`: 2,479 rows (2026-07-02 → 07-20), graded via `fwd_ret_1d/3d/5d` + `graded_at`. Recon (2026-07-21) reported 1,474 graded, 710 positive / 764 negative by `fwd_ret_5d` sign. That pooled split is deliberately NOT treated as a verdict: if Triton detects both bullish and bearish flow, pooling both directions cancels real edge by construction. Direction-conditioned analysis is the entire point of this audit. UW watchdog fully stopped the poller on 2 of 12 collection days (07-10, 07-13) — a known coverage gap, tested below.

## Phase 0 — pre-registration first (mandatory, before any query)
The recon states this table "feeds a pre-registered research study." **Locate the pre-registration document** (search `docs/` for the Triton study design / registration).
- **If found:** its registered endpoints and analysis plan are PRIMARY. Run them exactly as registered and report them first, unmodified. Everything in "Core analyses" below that isn't in the registration runs anyway but is labeled **POST-HOC / exploratory** in the output.
- **If no registration exists:** say so plainly in the output, treat ALL analysis as exploratory, and apply multiple-comparisons caution to any "significant" cut.
Also in Phase 0: confirm the table schema — direction field, any magnitude/conviction/premium fields, ticker, event timestamp — and report grading coverage by week.

## Core analyses (default plan; defer to registration where it exists)
1. **Direction-aligned returns:** define aligned_ret = fwd_ret for bullish-flow rows, −fwd_ret for bearish-flow rows. Report mean/median aligned_ret and hit rate (aligned_ret > 0) per horizon (1d/3d/5d), with binomial 95% CI vs 50%.
2. **Drift baseline:** compare against a matched baseline — same tickers, same period, unconditioned mean fwd_ret (long-side). A rising tape flatters bullish detections for free; edge means beating the drift, not beating zero. Report aligned_ret minus baseline per horizon.
3. **Magnitude/conviction buckets:** if the schema has premium/size/ratio fields, bucket into terciles and repeat #1 — the promotion case, if any, likely lives in the top bucket.
4. **Robustness:** repeat #1 excluding the two watchdog-shed days' surrounding gaps; report weekly stability (a strategy that worked only one week isn't a strategy); simple cumulative aligned-return curve over the collection period.
5. **Data-integrity spot check:** 20 random rows — do fwd_ret values reconcile against actual price history? (Guards the whole audit against a silent grading bug; the house has met fake-healthy before.)

## Output + decision
Write `docs/strategy-reviews/triton-shadow-audit-2026-07.md` with tables for every analysis above, an honest limitations section (coverage gaps, market regime during the window, any schema surprises), and a **recommendation only**: PROMOTE to next stage (paper alerts — explicitly NOT real money), EXTEND shadow (with what would change the answer), or RETIRE. Final decision is not CC's or this brief's: it goes to an Olympus pass (PIVOT synthesis) with Nick.

## Constraints
Read-only DB access. Pathspec-only commit for the output doc. `docs/workstreams.md` ledger update. ACK with the audit doc path and the one-line recommendation.
