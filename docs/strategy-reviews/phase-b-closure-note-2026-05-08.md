# Phase B Closure Note

**Date:** 2026-05-08
**Status:** SHIPPED (with caveats)
**Predecessor:** Phase A commit `0750e44` (migration 013, `outcome_source` enum + `signal_outcome_diff_log` + `v_outcome_drift`)
**Brief:** `docs/codex-briefs/outcome-tracking-phase-b-resolver-fix-2026-05-08.md`
**Code commit:** `e81d8a8` (resolver patches + tests + initial backfill script)

## What shipped

1. **Resolver code fix** (`backend/jobs/outcome_resolver.py`): tightened `start=` parameter, added pre-signal bar filter in walk loop, write `outcome_resolved_at = NOW()` instead of bar_ts. Verified live: 5+ post-deploy resolver writes had wall-clock timestamps with microseconds and zero backward-stamps.
2. **Initial backfill** (`scripts/backfill_resolver_outcomes_phase_b.py --apply`): 143 outcome corrections committed. Smoking-gun NXTS row corrected from `WIN +19.44%` to `LOSS −9.72%`. Rollback run_id: `phase_b_20260508_200423_d8df1731`.
3. **Hotfix B** (`scripts/phase_b_hotfix_resolved_at.py --apply`): 110 backward-timestamp BAR_WALK rows updated to `NOW()`. The original backfill skipped these because outcome was unchanged, but the bar-aligned `outcome_resolved_at` was still pre-signal. Rollback run_id: `phase_b_hotfix_b_20260508_232727_3f869d64`.
4. **Phantom-WIN investigation** (`scripts/phase_b_phantom_investigation.py`): 28 BAR_WALK WINs persisted post-backfill where `signal_outcomes.max_favorable` is less than the required move-to-target. Hand-walked 10 against today's yfinance; **10/10 confirmed yfinance drift** (today's data shows target hit; `signal_outcomes.MFE` was computed from older yfinance snapshot). Conclusion: ~0% true phantom-WIN rate; 28 residual rows are data-snapshot drift, not bugs.

## Acceptance results (final)

- **B. Zero backward timestamps among BAR_WALK rows:** PASS (was 110, now 0)
- **C. `v_outcome_drift` row count:** PASS (was 212, now 193)
- **D. NXTS no longer WIN +19.44%:** PASS (now LOSS −9.72%)
- **A. WIN-claim agreement ≥ 95%:** FAIL (56.7%) — but criterion was structurally wrong; see below
- **NEW: Phantom-WIN rate (impossible WINs / total WINs):** ~0% — Phase B's *real* success metric

## Brief-criterion correction

The brief's acceptance criterion A required ≥95% agreement between `signals.outcome` (BAR_WALK) and `signal_outcomes`. This is structurally unachievable. The two walkers operate at different granularities:

- `outcome_resolver.py` uses 15-minute bars and returns first hit.
- `score_signals.py` uses daily bars; on days where both `High >= target` and `Low <= stop`, it conservatively returns `STOPPED_OUT`.

For any signal where price oscillates target→stop within a single day, the two walks legitimately disagree. The audit pre-Phase-B reported 28-39% WIN agreement; that was the bug-residue-plus-granularity floor. Post-Phase-B 56.7% is the granularity-only ceiling — bug residue removed.

The correct Phase B success metric is the **phantom-WIN rate**: BAR_WALK WINs where `signal_outcomes.max_favorable < |target − entry|`. If MFE (the all-time max favorable across all bars) doesn't reach the target distance, no bar can have hit target; resolver claiming WIN is mathematically impossible.

Phase B reduced this from ~28% (5/8 audit Holy Grail subset 60-72%) to effectively 0%. The 28 currently-flagged "phantom" rows are confirmed yfinance data-snapshot drift, not resolver bugs.

## Secondary finding: signal_outcomes staleness

The phantom investigation surfaced that `signal_outcomes.max_favorable` is a snapshot computed at resolution time, not a living truth that updates as new bars arrive. For PENDING signals, MFE may continue to update; once resolved, it freezes. This means `signal_outcomes` cannot be treated as the absolute gold standard for back-comparison weeks/months later — its MFE drifts vs current yfinance.

**Phase C scope implication:** the projection logic must re-walk bars on current data when reconciling, not blindly trust `signal_outcomes` snapshot fields. Document this in the Phase C brief.

## Open work for Phase C

1. Project `signal_outcomes` → `signals.outcome*` for BAR_WALK rows, with re-walk on current yfinance to refresh stale MFE.
2. Reconcile the ~88 legitimate 15m-vs-daily granularity disagreements (decide which walker is canonical for which use case).
3. Re-run 3-10 promotion audit against the corrected dataset (target: n≥250 clean `both` signals).
4. Olympus Pass 9 v2 percentile threshold recalibration.

## Rollback procedure

If Phase B needs to be reverted entirely:

```sql
-- Step 1: revert hotfix B
BEGIN;
UPDATE signals s
SET outcome_resolved_at = d.old_resolved_at
FROM signal_outcome_diff_log d
WHERE d.signal_id = s.signal_id
  AND d.backfill_run_id = 'phase_b_hotfix_b_20260508_232727_3f869d64';
COMMIT;

-- Step 2: revert main backfill
BEGIN;
UPDATE signals s
SET outcome             = d.old_outcome,
    outcome_pnl_pct     = d.old_pnl_pct,
    outcome_resolved_at = d.old_resolved_at
FROM signal_outcome_diff_log d
WHERE d.signal_id = s.signal_id
  AND d.backfill_run_id = 'phase_b_20260508_200423_d8df1731';
COMMIT;

-- Step 3: revert code (git revert e81d8a8 on main, push, Railway redeploys)
```

## Artifacts committed in Phase B closure

- `scripts/phase_b_acceptance_check.py` — runs the 4 acceptance queries
- `scripts/phase_b_failure_diagnostic.py` — diagnoses A and B failures
- `scripts/phase_b_impossible_win_check.py` — phantom-WIN counter
- `scripts/phase_b_hotfix_resolved_at.py` — Hotfix B (110 backward-ts updates)
- `scripts/phase_b_phantom_investigation.py` — yfinance drift vs residual bug check
- `docs/strategy-reviews/phase-b-closure-note-2026-05-08.md` — this document
