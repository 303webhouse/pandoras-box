# DEF-CVD-DEDUP — Completion Report

Date: 2026-07-21
Brief: `docs/codex-briefs/2026-07-21-def-cvd-dedup-brief.md`
Code + config commit: `e14a8bd` (2 files, 5 new tests) — plus `crypto_cycle_config` version id=4, shipped via direct SQL alongside the code
Railway deploy: SHA `e14a8bd`, 4-step verification below, live cadence re-verified ~2h post-deploy

## Root cause (Phase 0, written before any edit)

Located §5.7's implementation: `backend/bias_filters/crypto_tape_health_engine.py::_check_cvd_cooldown()` / `_fire_cvd_events()`. It is **fully implemented and mechanically correct** — a `signals` table lookback keyed on `signal_id LIKE 'CRYPTO_CVD_{event_type}_{symbol}_{level_name}_%'`, config-driven cooldown window, no new dedup table. Hypothesis (a) from the brief ("never implemented") is **false**.

**Actual defect:** `cvd_events.absorption_cooldown_seconds` / `divergence_cooldown_seconds` defaulted to **900 seconds** — exactly equal to the tape-health job's own 15-minute polling interval, which D3 (`3436a01`) enabled for the first time ever earlier this session. Real-world tick-to-tick gaps oscillate around 900s due to ordinary scheduler jitter and execution latency (bar fetch, volume-profile compute, DB round trips), so the cooldown query (`timestamp > NOW() - INTERVAL '900 seconds'`) only suppressed on the ticks where the gap happened to land under 900s — essentially a coin flip. Confirmed live: CVD_ABSORPTION went from 3 fires ever (as of 2026-07-19) to 57+ in under two days once the schedule went live, with observed inter-fire gaps at the SAME (symbol, event_type, level_name) clustering right at 898-902 seconds — dead center on the boundary, exactly as this mechanism predicts.

**Hypothesis (b) from the brief ("keyed on the exact level value, drift defeats it") is false as stated.** Read `_build_cvd_event_signal()`: the dedup key (embedded in `signal_id`, matched via `LIKE`) is the level **NAME** (`POC`/`VAH`/`VAL` — a stable 3-way category), not the drifting numeric `level_price`. Confirmed with a direct test (`test_cooldown_key_is_level_name_not_numeric_price`): two events at the same category but different numeric prices (100.05 vs 100.31) produce identical dedup-key prefixes. "Tolerate small anchor-level drift" was already satisfied by the existing design — no key-structure change was needed.

**Hypothesis (d) (interaction with the created_at offset) is not implicated.** The cooldown query correctly uses the `timestamp` column, and the gap analysis was done via server-side SQL interval arithmetic (`created_at - LAG(created_at)`), which is unaffected by client-side display concerns regardless. (Separately, and importantly: the "confirmed table-wide created_at +6h offset" referenced in this brief's own §4d has since been found to be a viewing-tool artifact, not a real database bug — see DEF-SIGNAL-METADATA's Phase 0 findings, `docs/codex-briefs/def-signal-metadata-phase0-findings.md`. It never affected this analysis, but the brief's citation of it as established fact no longer holds.)

## Fix

1. Widened both cooldowns to **1800 seconds** (2x the 15-minute polling interval, real margin against jitter) via a new `crypto_cycle_config` version (id=4, hot-reload, no code change to the query itself).
2. Updated the code-level fallback default (`cvd_cfg.get(cooldown_key, 900)` → `1800`) so a config-fetch failure fails toward the safe/wide side, not back into the bug.
3. Updated `backend/config/crypto_cycle_config_seed.py`'s documented default to 1800 for future re-seeds, with the root cause noted inline.
4. No key-structure change (per-level granularity is deliberate per §5.7's own spec and was never the defect).

## Data hygiene proposal (Task 3 — proposed only, NOT applied, needs explicit approval)

44 `CVD_ABSORPTION` rows total; 41 of them landed between the D3 schedule going live (`2026-07-21T03:31:00Z`, real time) and this fix's deploy (`2026-07-21T~12:32:00Z`, real time) — the pseudo-replicated burst window. Proposed tag, mirroring DEF-ENRICH-CLOBBER's wrap-in-place precedent: add a `quarantine_meta`-style key to `enrichment_data` (e.g. `{"dedup_burst_2026_07_21": true}`) for exactly these 41 signal_ids, identified by `strategy = 'CVD_ABSORPTION' AND created_at >= '2026-07-21T03:31:00' AND created_at < '2026-07-21T12:32:00'`. This would NOT touch `signals.outcome`, `signal_outcomes`, or any grading-machinery column — purely an annotation so a future promotion audit (e.g. TRITON-AUDIT-style) can exclude/flag these as known-duplicated rather than treat them as 41 independent observations. **Not applied — awaiting explicit approval per the brief's own decision-gate instruction.**

## Tests

5 new tests in `backend/tests/test_s3b_cvd_event_detection.py`:
- `test_seed_cooldowns_have_real_margin_over_polling_interval` — a regression guard that would have caught the original bug (asserts the seed default is ≥2x the 15-min polling interval; fails against the old 900s value).
- `test_fire_events_passes_widened_cooldown_seconds_to_check` / `test_fire_events_falls_back_to_widened_default_when_config_key_missing` — confirm the widened value threads through correctly in both the config-present and config-missing-key cases.
- `test_cooldown_key_is_level_name_not_numeric_price` — confirms hypothesis (b) is structurally false (the existing key design).
- Pre-existing dedup-logic tests (cooldown blocks/clears, fail-closed on DB error, second-trigger-in-cooldown-doesn't-double-fire) all still pass unchanged — the fix is a config-value change, not a logic change, so none of these needed rewriting.

Full suite: `18f/1s/203e` unchanged from baseline, passed 460 → 464.

## Deploy verification (PROJECT_RULES.md 4-step standard)

1. Railway status SUCCESS.
2. SHA `e14a8bd76bdb9d610472916df6b6e47321c96652` exact match to pushed commit.
3. Live empirical check: confirmed via direct query that every same-`(symbol, event_type, level_name)` repeat since deploy has a gap of **30:03 minimum** (30:03, 45:01, 45:03, 45:04, 1:00:03, 1:00:05, 1:14:59 observed across BTC/ETH/ZEC pairs) — zero violations of the new 1800s window, vs. the pre-fix pattern of 898-902s repeats. No errors in Railway logs referencing `crypto_tape_health`/`crypto_cvd_events` since deploy.
4. Not needed — no silence >5 min.

## Before/after cadence (per the brief's own required report)

- **Before:** 3 lifetime fires (through 2026-07-18) → 57+ in <2 days once the 15-min schedule went live (2026-07-21T03:31Z onward), same-level repeats every ~899-902 seconds.
- **After (this fix, live since ~2026-07-21T12:32Z real time):** same-level repeats now measured at 30:03–1:14:59 minutes — every observed post-deploy repeat respects the new 1800s floor, with several genuinely independent (different symbol or level) events filling in the rest of each hour's count. No same-`(symbol, level)` pair has re-fired within the cooldown window since deploy.

## Explicitly downstream (per the brief)

The pending crypto alert-floor decision was waiting on this fix since the pre-fix score distribution was dominated by pseudo-replicated noise. Re-running that distribution now (post-fix) would need another ~24-48h of clean data to be meaningful (only ~2.5 hours of genuinely-deduped data exists at report time) — flagging as a natural follow-up rather than re-running prematurely on too small a post-fix sample.

## Notable process note

An unrelated, more consequential finding surfaced while investigating this brief: DEF-SIGNAL-METADATA's own motivating evidence (a "confirmed table-wide `created_at` +6h offset") turned out to be a viewing-tool artifact, not a real bug — see `docs/codex-briefs/def-signal-metadata-phase0-findings.md`. This does not change anything in this completion report (the CVD-DEDUP root cause and fix stand independently, verified via server-side interval arithmetic that was never exposed to the client-parsing artifact) but is noted here since this brief's own §4d hypothesis cited that now-corrected claim.

## ACK

Completion doc: this file. Post-fix cadence: same-level repeats now ≥30 minutes, zero violations observed. Data-hygiene tag proposed, not applied — awaiting approval.
