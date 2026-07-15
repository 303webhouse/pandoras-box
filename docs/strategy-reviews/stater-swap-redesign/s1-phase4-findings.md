# Stater Swap v2 — S-1 Phase 4 Findings (F-4: L0 Routing Dual-Write)

**Date:** 2026-07-14 | **Brief:** `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md`
**Hard rule honored:** no live cutover in this pass. This ships the shadow dual-write only, per Nick's explicit instruction ("Dual-write only — no cutover without my diff-report greenlight").

## Scope, per Phase 0's correction

Phase 0 found only ONE of the three crypto signal paths bypasses governance: `bias_scheduler.py`'s `run_crypto_scan_scheduled()` ("Crypto Scanner," 30-min loop) calls `log_signal()` directly. `crypto_setups.py`'s 5-min engine and the TradingView webhook path already route through `process_signal_unified`. F-4 therefore only touches the Crypto Scanner bypass — the other two paths are untouched (already compliant).

## Why not just call `process_signal_unified()` directly on a shadow signal_id

Investigated before writing any code. `process_signal_unified()` had no shadow/dry-run parameter — the only existing flag (`skip_scoring`) turns off scoring only, not persistence, cache, broadcast, or committee flagging. Calling the full function on a copy with a distinct signal_id would still:

- Post to Discord twice (the iv_regime divergence alert inside `apply_scoring`, and the feed-tier-v2 divergence alert)
- Broadcast a second "new signal" WebSocket event the dashboard displays
- Flag the shadow copy for committee review if its score qualifies
- Write a real `catalyst_confluence` event
- **Worst case: the conflict-check step (`_check_and_clear_conflicting_signals`) can DISMISS a real, already-broadcast production signal** for the same ticker if the shadow signal's direction happens to conflict with it — the single most dangerous side effect for a same-ticker dual-write.

## What shipped

- **`backend/signals/pipeline.py`**: `process_signal_unified()` gains a `shadow: bool = False` parameter. When `True`, every gating/scoring/classification step (L0 shadow gate, bias snapshot, `apply_scoring`, feed-tier v1/v2, ceiling caps) runs exactly as normal — this is the decision logic the diff report needs — but the function returns immediately **before** persistence, with lightning-card dedup and the feed-tier-v2 Discord alert also suppressed under `shadow=True`. Default `False`: zero behavior change for every existing caller (equity signals, the TradingView webhook path, `crypto_setups.py`'s compliant engine — none of them pass `shadow=True`, so this is purely additive).
- **`backend/jobs/crypto_dual_write_shadow.py`** (new): `shadow_write_crypto_signal(trade_signal, real_signal_id)` — builds a deep copy with a distinct `SHADOW_{signal_id}` id, runs it through `process_signal_unified(shadow=True)`, and writes the comparison into `crypto_dual_write_shadow` (migration 024). Swallows all errors (a shadow-write failure must never affect the real signal that already completed). Gated by a Redis hot-toggle (`crypto_dual_write:enabled`, default on, fail-open on Redis error) — mirrors `uw_budget_watchdog.py`'s proven `quota_shed:triton` pattern per brief F-4.3's hot-reload requirement. (`system_config` in Postgres was investigated and found to be unused/aspirational schema — not a working pattern to build on.)
- **`backend/scheduler/bias_scheduler.py`**: `run_crypto_scan_scheduled()` calls `shadow_write_crypto_signal()` once, **after** the real `log_signal`/`update_signal_with_score`/`cache_signal`/`broadcast_signal_smart` sequence already completed — the dual-write can never delay or risk the real signal path.
- **`migrations/024_crypto_dual_write_shadow.sql`** (+ mirrored in `postgres_client.py::init_database()`): evidence-only table, mirrors `triton_flow_shadow`'s "nothing reads this for scoring" precedent. Includes the `-- DOWN` rollback block per AEGIS A2.
- **`scripts/crypto_dual_write_diff_report.py`** (new, mirrors `l0_shadow_measure.py`/`l1_shadow_measure.py`'s exact pattern — reads `.mcp.json`, never prints the DB URL): reports shadow-row count, the brief's own readiness bar (>=48h OR n>=30), real-vs-shadow score/status per row, L0 would-suppress distribution, feed-tier v1-vs-v2 divergence, and committee-flag count. **Does not gate or auto-approve anything** — unlike the L0/L1 shadow-measure scripts (which assert a pass/fail safety invariant), this one is pure reporting; the cutover decision is Nick's, in writing, per brief F-4.2.

## Live verification (before commit)

Ran the full mechanism end-to-end against the real Railway container (not simulated):

1. `process_signal_unified(shadow=True)` on a synthetic `BTC-USD` signal: computed score=13.0 (real gating ran — L0 verdict `KEEP`/`not in any suppress set`, L1 verdict `out_of_scope`, feed_tier=`watchlist`), confirmed **zero row written to the real `signals` table** for the shadow signal_id.
2. `shadow_write_crypto_signal()` end-to-end: real path's ad hoc score (55) vs. the chokepoint's real `apply_scoring` score (13) — a substantial divergence, exactly the kind of signal the diff report exists to surface. Row landed correctly in `crypto_dual_write_shadow` with all fields populated; confirmed the real `signals` table was still untouched.
3. `scripts/crypto_dual_write_diff_report.py` run locally against that test row: correctly reported 1 row, "NOT YET MET" on the readiness bar (0 hours elapsed), the score/status comparison table, L0 distribution, feed-tier comparison, and the "Nick's written greenlight required" disclaimer.

Test data cleaned up after verification (both the synthetic shadow row and confirmed no synthetic rows ever reached the real `signals` table).

## Also fixed while here

`backend/jobs/outcome_resolver.py`'s Phase 2 import (`from jobs.crypto_bars import ...`) was at module level, which broke `tests/test_outcome_resolver_phase_b.py`'s collection (that test imports via `from backend.jobs.outcome_resolver import _walk_bars`, a dotted convention where a top-level `jobs` import doesn't resolve, even though it works fine in production where uvicorn runs with `cwd=backend/`). Moved the import inside `_walk_bars_crypto()` (matching this same file's existing lazy-import convention for `database.postgres_client`). Confirmed fix: the previously-broken test file now collects and passes.

## Not done / explicitly deferred

- **No cutover.** The `bias_scheduler.py` `log_signal` bypass is untouched and still runs exactly as before — this ships evidence-gathering only.
- Diff report readiness bar (48h/n=30) will need real crypto signal volume to accumulate before it's meaningful — reported honestly as "NOT YET MET" until then, not faked.
