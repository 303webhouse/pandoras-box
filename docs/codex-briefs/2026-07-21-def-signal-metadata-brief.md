# DEF-SIGNAL-METADATA — Provenance + timestamp integrity for signal rows

**Date:** 2026-07-21 | **Author:** Coordination lane (Fable)
**Priority:** Small, post-Phase-3. Three confirmed symptoms, likely 1-2 shared roots. Investigation-first.

## Task 0 — file into place
This file arrives at repo root. `git mv` to `docs/codex-briefs/2026-07-21-def-signal-metadata-brief.md`, pathspec-commit, push.

## Evidence (three independent sightings, same theme)

**S1 — `source` column is fiction, table-wide.** Recon finding (2026-07-21, four-agent recon report): `log_signal()`'s INSERT never sets `source`, so the DB default `'tradingview'` silently stamps every row regardless of true origin. Provenance via `source` is unusable anywhere in the table; V1's forensic check last night saw `source: tradingview` on rows written by non-webhook writers.

**S2 — `signals.created_at` runs ~6h hot.** def-feed-triage-completion.md V1 secondary observation: `created_at` on checked rows reads roughly 6 hours later than both the epoch embedded in the signal_id and the notifier log's fetch time — the exact MDT/UTC offset signature.

**S3 — `age_minutes` in the ideas feed runs ~12h hot.** Coordination-lane observation 2026-07-20: `hub_get_trade_ideas` returned `newest_at: 2026-07-20T13:55:xx` signals (fresh, ~50 min old at read time) with `age_minutes ≈ 778` (~13h). Note S2+S3 may compound: a naive +6h write offset plus a naive read-side comparison could produce ~12h of phantom age.

## Tasks

1. **Phase 0 (read-only, root cause in writing before any edit):**
   a. Map every timestamp hop for a signal row: each writer's timestamp construction → DB column types (`timestamptz` vs naive) → each API reader → each age/staleness computation. Document tz-awareness at every hop.
   b. Enumerate ALL current callers of `log_signal()`. F-4 made `process_signal_unified()` settled law — confirm whether any live writer still uses the side door, and list them. (Report only; rerouting writers is its own decision.)
   c. Confirm which writers are affected by S1/S2 (all? subset?).
2. **Fix — timestamps:** tz-aware UTC end-to-end. House rule applies: never hardcode offsets; `zoneinfo` only where a zone is genuinely needed. Fix the age computation(s) to compare aware-to-aware.
3. **Fix — source:** pass the true source through the write path(s) so new rows carry real provenance. Historical backfill is a **DECISION GATE**: propose a `strategy → source` backfill mapping in the completion doc, but do NOT apply it without explicit approval (data migration territory — ATLAS flag if pursued).
4. **Tests:** assert tzinfo present on written timestamps; assert `source` ≠ default for each live writer path; age-computation unit test against a fixed fixture (known write time vs known now).
5. **Verify live post-deploy:** a fresh signal shows sane `age_minutes`; `created_at` ≈ signal_id epoch; a new row from each writer carries its correct `source`.

## Constraints
Pathspec-only commits. 4-step deploy verify. No schema changes without ATLAS flag (column defaults count). Completion doc `docs/codex-briefs/def-signal-metadata-completion.md` + `docs/workstreams.md` ledger update. ACK with completion path.
