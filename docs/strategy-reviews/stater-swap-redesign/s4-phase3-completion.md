# S-4 Phase 3 — Completion Report

Date: 2026-07-21
Brief: `docs/codex-briefs/2026-07-16-stater-swap-s4-strategy-layer-brief.md` §4
Phase 0 findings (governing precondition source): `docs/strategy-reviews/stater-swap-redesign/s4-phase0-findings.md` §0.4
Code + config commit: `bb0a56f` (backend + notifier, 4 files, 21 new tests) — plus `crypto_gate_config` versions id=4 and id=5, shipped via direct SQL alongside the code
Railway deploy: SHA `bb0a56f`, 4-step verification below
VPS deploy: `scripts/signal_notifier.py`, SHA-256 `d7f23d3746c3457b77398639df0d263aa7789f1a8012295a77ad87d88b71e1ee`

All three named deliverables (§4.1 display, §4.2/§4.3 gating rules) plus a small addendum (Risk-line display bug + a read-only score-distribution report) are complete, tested, and deploy-verified.

---

## 4.1 — Carry-asymmetry display

**What shipped:** `scripts/signal_notifier.py::post_crypto_signal_alert` now renders a first-class "⚖️ Carry Asymmetry" line on `Funding_Rate_Fade` cards only, immediately below Phase 2's funding-cost line (not buried in it, per DAEDALUS's rule). Formula: `abs(funding.rate_pct) / sizing.stop_distance_pct * 100` — reuses `funding.rate_pct` (already fetched, already degraded-gated) and `sizing.stop_distance_pct` (already computed by `calculate_breakout_position()`, unused elsewhere in the embed). No new vendor call, no new scoring dimension. Correctly scoped inside the existing `if state:` guard, so a `/crypto/state` fetch failure no-ops cleanly rather than crashing.

**Verification:** 4 tests (shown for Funding_Rate_Fade, hidden for other strategies, hidden when stop_distance_pct missing, hidden when funding is degraded). Adversarially re-verified: arithmetic sanity-checked against realistic numbers (funding 0.05%/8h, stop_distance_pct 0.3% → ≈17% of stop distance/settlement — sane, not off by 10x/100x, which this codebase has a documented history of getting wrong elsewhere).

## 4.2 — Negative-funding-fade LONG entry floor

**What shipped:** `backend/strategies/crypto_setups.py::check_funding_rate_fade`'s qualification floor moved from a single pre-direction-split check to per-branch: SHORT (positive funding) keeps `abs_rate >= 0.0003` unchanged; LONG (negative funding) now requires `abs_rate >= 0.0005` for the [0.0003, 0.0005) band — ATLAS's "stronger structural trigger" (Phase 0 §0.4, SATISFIED), reusing the function's own existing HIGH-confidence boundary rather than inventing a new dimension.

**Design revision, disclosed in full:** the first implementation shipped this floor raise directly/unflagged, reasoning that a threshold *raise* on a strategy with zero live fires ever could only reduce risk. An adversarial verify pass (4 independent reviewers, one specifically tasked with judging this decision) found that reasoning contained a real flaw: it answered "does this increase fire count" when the governing documents asked "is this consistent with the shadow-first posture" — and it silently overrode Phase 0 §0.4's own explicit conclusion ("shadow-tag by default... regardless") rather than engaging with it. The reviewer proposed a concrete, low-cost middle path; it was adopted.

**Final design (shadow-gated):** the LONG branch's [0.0003, 0.0005) delta zone — the only band where behavior actually changes — is logged every time it's hit (`logger.info`, includes the computed `abs_rate` and current enforcement state) but only actually rejects the signal once `master_rules.funding_fade_negative_floor_raise_enabled` is `true` in `crypto_gate_config` (hot-reload, 60s TTL, no redeploy). The flag defaults `false` — today's 0.0003 floor keeps firing exactly as before until Nick/Titans opt in. Fails open (defaults to not-enforced) if the config fetch itself errors.

**Verification:** 8 tests covering both branches, both flag states, and the fail-open-on-config-error path. Adversarially re-verified against the actual code (not just the diff) by two independent passes — the first (pre-revision) confirmed the original unflagged version was mechanically correct; the second (judgment-focused) is what triggered the revision above.

## 4.3 — No negative-funding-fade LONGs at Tier 3

**What shipped:** `backend/bias_filters/crypto_gates.py::evaluate_gates` gained a new, regime-independent block: `tier == 3 AND strategy == "Funding_Rate_Fade" AND direction in _LONG_DIRECTIONS AND master_rules.get("tier3_blocks_negative_funding_fade_longs", True)` → `_block("TIER3_NEG_FUNDING_FADE_LONG_BLOCK")`. Mirrors the existing `BTC_TREND_DOWN_T3_BLOCK` pattern exactly — same `_block()` closure, same config-read convention, same shadow table. "Negative-funding-fade LONG" is inferred from strategy+direction alone (no funding-rate sign threaded into the evaluator) since `check_funding_rate_fade` only ever emits LONG on negative funding — confirmed as an exact, not approximate, proxy.

**Shadow-only, confirmed by trace:** `evaluate_gates()` always computes and persists the verdict to `crypto_gate_shadow`; `maybe_enforce_gate()`'s first line (`if not config.get("gating_enabled"): return False`) means no code path reaches `UPDATE signals` while `gating_enabled` stays `false` (confirmed still `false` on the live config).

**Verification:** 5 tests (Tier-3+LONG blocked, Tier-3+SHORT unaffected, Tier-1 LONG unaffected, non-Funding_Rate_Fade strategy at Tier 3 unaffected, shadow-row shape). Adversarially re-verified: correct `_LONG_DIRECTIONS` set reuse (includes the "BUY" alias), correctly independent of `regime_master` (a standalone `if`, not nested in the `TREND_DOWN` `elif` chain), live config confirmed via direct query.

## Config changes

`crypto_gate_config` bumped twice, append-only (never UPDATE), each verified before/after:
- **id=4**: adds `master_rules.tier3_blocks_negative_funding_fade_longs = true` (§4.3).
- **id=5**: adds `master_rules.funding_fade_negative_floor_raise_enabled = false` (§4.2, shadow gate).

Both shipped via direct SQL (psycopg2 against the `.mcp.json` connection string — the postgres MCP tool is read-only, matching the established write mechanism used throughout this program). Both verified post-ship: new key present with the correct value, all prior keys unchanged.

## Addendum (mid-Phase-3 request)

1. **Risk-line display bug, fixed.** `post_crypto_signal_alert`'s R:R/Risk line previously rendered `"$0 (?%)"` when `position_sizing` was absent or incomplete (`sizing.get("risk_usd", risk)` silently substituted a raw price-delta formatted as a dollar figure; `sizing.get("risk_pct", "?")` defaulted to a literal `"?"`). Now: real `$`/`%` only render when both are genuinely present; otherwise a clearly-labeled `Risk/unit: $X.XX` (the raw price distance) instead. Confirmed byte-identical output for the normal/populated case; confirmed the old bug's exact symptom is now structurally unreachable.
2. **Crypto signal score distribution, reported (read-only, no fix).** CVD_ABSORPTION min/median/max = 3/21/38 (n=57 at report time), Session_Sweep = 21/38/48 (n=19). **Two findings surfaced during this check, not part of the original ask:**
   - CVD_ABSORPTION volume increased live during the investigation (3 fires ever as of Phase 0 → 57+ and climbing every ~15 min) — directly caused by this session's own DEF-FEED-TRIAGE D3 fix, which enabled the tape-health job's 15-min schedule for the first time ever. `_detect_cvd_events()` appears to lack dedup/cooldown now that it's actually exercised on a real cadence. Not fixed here — flagged as directly relevant to "the pending crypto alert-floor decision" and likely needing its own look.
   - `signals.created_at` runs ~6 hours ahead of true UTC — confirmed with hard evidence (signal_id-embedded epoch timestamps cross-checked against the `created_at` column on multiple rows), not scoped to crypto (also seen on equity rows during DEF-FEED-TRIAGE's V1). Root-cause hypothesis (not verified by direct testing): a `timestamp without time zone DEFAULT NOW()` column being evaluated under a non-UTC session timezone. Not fixed — flagged for its own investigation given how broadly it could distort date-based signal analysis.

## Test suite

21 new tests (`backend/tests/test_s4_phase3_funding_fade_gating.py`), covering: both 4.2 floor branches, both 4.2 flag states, 4.2's fail-open-on-config-error path, all 5 of 4.3's Tier-3 block conditions, 4.1's carry-asymmetry scoping/gating, and both Risk-line paths (populated and missing/incomplete sizing). Full suite (`cd backend && pytest tests/ -q`): **18 failed / 460 passed / 1 skipped / 203 errors** — failures/skips/errors byte-identical to the pre-existing known-red baseline; passed count grew by exactly the 21 tests this brief contributed (439 → 460).

## Adversarial verification

Given this touches live trading-strategy gating logic, a 4-agent adversarial verify workflow ran against the diff before deploy: independent correctness checks for §4.2, §4.3, and §4.1+the Risk-line fix (all three: **no discrepancies found**, one cosmetic non-functional nit on §4.3 — the seed file wasn't updated with the new key, consistent with how prior config-version keys were also never backfilled into the seed, not a regression), plus a dedicated judgment review of the original unflagged §4.2 decision (verdict: **mistake, should be reverted** — acted on, see §4.2 above). This is the first time in this engagement a post-implementation adversarial pass changed a shipped design before deploy, rather than only confirming or finding minor bugs.

## Deploy verification (PROJECT_RULES.md 4-step standard)

**Railway:** (1) status SUCCESS (2) SHA `bb0a56f` exact match to pushed commit (3) live curl confirming the deployed code behaves correctly (4) — checked if silent >5 min.

**VPS:** byte-exact `scp`, SHA-256 verified identical local/remote (`d7f23d37...`), `python3 -m py_compile` clean, prior version backed up in place (`signal_notifier.py.pre-s4phase3-backup-20260721`).

## Constraints honored

Investigation-first recon refresh before any edit (confirmed nothing had drifted since Phase 0's 2026-07-19 findings, re-verified Funding_Rate_Fade's live fire count was still 0). Config-driven, hot-reloadable, no new config table (§6). No migration needed (JSONB column, plain INSERT). Pathspec-only commits. Shadow-first honored for both gating rules in the final shipped design. Zero breaking changes to existing embed fields or the equity Analyze/Dismiss path.

## Open items / follow-ups (not blocking, not built here)

- CVD_ABSORPTION's apparent missing dedup/cooldown, now that D3's scheduling fix exercises it on a real cadence — worth its own look, feeds directly into the pending crypto alert-floor decision.
- `signals.created_at`'s ~6-hour UTC offset — worth its own dedicated investigation given its breadth.
- Two new untracked brief files appeared at repo root during this session (`2026-07-21-def-signal-metadata-brief.md`, `2026-07-21-triton-shadow-audit-brief.md`) — left alone, not yet actioned, per standing practice for coordination-lane drops.
