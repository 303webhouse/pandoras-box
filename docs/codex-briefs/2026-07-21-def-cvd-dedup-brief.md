# DEF-CVD-DEDUP — CVD_ABSORPTION firing every tick; cooldown ineffective

**Date:** 2026-07-21 | **Author:** Coordination lane (Fable)
**Priority:** Runs NEXT, before DEF-SIGNAL-METADATA and before the crypto alert-floor decision. The Discord spam is the symptom; the disease is track-record pollution — a one-week-old PROVISIONAL strategy is accruing dozens of pseudo-replicated rows that will poison its own eventual promotion audit.

## Task 0 — file into place
This file arrives at repo root. `git mv` to `docs/codex-briefs/2026-07-21-def-cvd-dedup-brief.md`, pathspec-commit, push.

## Context + evidence
- D3 (`3436a01`) registered the tape-health job at 15-minute intervals for the first time; CVD event detection runs after each computation (`crypto_market.py`). The class went from 3 lifetime fires (07-18) to **57+ in under two days, cadence ~every 15 minutes** (Phase 3 session's own distribution check, 2026-07-21).
- The S-3b brief §5.7 specified dedup: per-symbol, per-event-type, **per-level** cooldown window, config-driven, via a `signals` table lookback. Something about that is absent or ineffective in the live path.
- Candidate hypotheses to test, not assume: (a) cooldown never implemented in the event path; (b) implemented but keyed on the exact level value, and POC/VAH/VAL drift a few dollars every 15-min recompute → key never repeats → cooldown never matches; (c) lookback window shorter than the 15-min cadence; (d) the lookback query interacts badly with the confirmed table-wide `created_at` ~+6h offset (see DEF-SIGNAL-METADATA S2, brief at repo root). If root cause turns out to BE the timestamp offset, say so and coordinate — the fix may belong in that brief's scope; do not double-fix.

## Tasks
1. **Phase 0 (read-only, root cause in writing):** locate §5.7's implementation (or its absence) in the CVD event path. Pull the 57+ rows: inter-fire spacing per symbol, per event type, and the anchor-level values across consecutive fires — the level-drift hypothesis is confirmed or killed by that one query.
2. **Fix:** make the cooldown effective per §5.7's intent. Design is yours; one requirement — the dedup key must tolerate small anchor-level drift (a level band or rounded bucket, not exact-value equality). Window config-driven (`crypto_cycle_config`, existing loader), no new table.
3. **Data hygiene — DECISION GATE:** propose (do NOT apply) a tag/annotation for the burst rows so CVD_ABSORPTION's provisional track record isn't contaminated by pseudo-replication — wrap-in-place precedent per DEF-ENRICH-CLOBBER. Needs explicit approval; ATLAS flag if schema-adjacent. Grading machinery untouched either way.
4. **Tests:** repeat event within window at same/near level → suppressed; after window → allowed; different symbol → independent; different event type → independent.
5. **Verify live:** across several post-deploy ticks, fire cadence drops to genuine-events-only; Discord drip stops. Report before/after cadence numbers in the completion doc.

## Explicitly downstream of this brief
The crypto alert-floor decision (pending with Nick) waits for this fix: the score distribution pulled during Phase 3 is ~two-thirds duplicates, and a floor calibrated against noise is a floor calibrated wrong. Re-run the distribution query post-fix and include it in the completion doc.

## Constraints
Pathspec-only commits. 4-step deploy verify for any Railway change. No schema changes without ATLAS flag. Completion doc `docs/codex-briefs/def-cvd-dedup-completion.md` + `docs/workstreams.md` ledger update. ACK with completion path and the post-fix cadence + clean score distribution.
