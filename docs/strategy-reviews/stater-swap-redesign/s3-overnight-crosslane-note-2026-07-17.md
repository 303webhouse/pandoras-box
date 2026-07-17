# S-3 Overnight Cross-Lane Note — 2026-07-17

Phase 0.0 stop-gate evidence, ahead of the S-3b spot-CVD wire-in micro-brief's own Phase 0.1 klines audit. Window checked: `computed_at >= 2026-07-17T02:15:00Z` (post-restart of the `cdec3e8` push).

## a) SQL vs deployed DB — regime + cycle logs

**`crypto_regime_log`**: 90 rows, 6 distinct symbols, span `03:14:08Z` → `17:14:10Z` (≈15 hourly cycles × 6 symbols). Latest `config_version` at time of check: **2**. Per-symbol values on the latest cycle (`17:14:0[7-10]Z`) are genuinely distinct, not zeroed/duplicated:

| symbol | regime_state | price |
|---|---|---|
| BTC-USD | CHOP | 64000.32 |
| ETH-USD | CHOP | 1848.94 |
| SOL-USD | CHOP | 75.50 |
| HYPE-USD | CHOP | 60.508 |
| ZEC-USD | CHOP | 554.59 |
| FARTCOIN-USD | CHOP | 0.1353 |

All six read CHOP simultaneously — a legitimate synchronized regime read (not the fake-healthy failure signature, which is identical/zeroed *prices*, not identical *states*). **PASS.**

**`crypto_cycle_log`**: 102 rows, 6 distinct symbols, span `03:14:07Z` → `17:37:11Z`. Latest `config_version` at time of check: **1**. Per-symbol values across the last 3 observed cycles show real diversity — `composite_score` ranges **-33.3 to 100**, `tier` 1-3, `composite_method` flips between `froth_dominant`/`cap_dominant`, `live_cell_count` 7-13. **PASS**, clearly not the six-identical-or-zeroed fake-healthy pattern.

(Note: `crypto_regime_log.config_version` and `crypto_cycle_log.config_version` track two separate append-only config tables — `crypto_gate_config` and `crypto_cycle_config` respectively — so their version numbers are independent, not expected to match each other.)

## b) Hot-reload proof

No post-restart (≥ `02:15Z`) config bump existed in either `crypto_gate_config` or `crypto_cycle_config` prior to this check — both were still on their pre-restart versions (`crypto_gate_config` id=2 from the S-2 `2026-07-16` proof; `crypto_cycle_config` id=1, seed-only, never bumped).

INSERT'd one benign trivial-field bump per table at `~17:55Z` (`scripts/s3b_phase0_hotreload_proof.py`, S-2 DD-8 pattern — append-only, never UPDATE):

- `crypto_gate_config` **id=3**, `created_by='S3B_PHASE0_HOTRELOAD_PROOF'`: `regime.stale_bars_max_hours` 48 → 49.
- `crypto_cycle_config` **id=2**, `created_by='S3B_PHASE0_HOTRELOAD_PROOF'`: `tape_health.staleness_seconds` 120 → 121.

Both jobs run `interval, hours=1` (`backend/scheduler/bias_scheduler.py`), last fired `17:14Z` (regime) / `17:37Z` (cycle) before the INSERT. **Confirmed via background poll (`scripts/s3b_phase0_hotreload_poll.py`):**

- `crypto_regime_log`: `config_version=3` first observed at `2026-07-17T19:30:31.188Z` (symbol `FARTCOIN-USD`).
- `crypto_cycle_log`: `config_version=2` first observed at `2026-07-17T19:30:50.266Z` (symbol `FARTCOIN`).

Both picked up the new config on their next natural hourly firing, zero redeploys, zero code touched between the INSERT and the pickup — same mechanism S-2's DD-8 proof established. **PASS, item (b) fully closed.**

## c) pytest full suite — initial STOP, resolved, now PASS

First attempt (`python -m pytest --tb=no -q` from repo root): **collection was interrupted, 0 tests collected** — a bare root-level invocation walked into `stable_market_board_LATEST/`, a completely untracked, never-committed directory (`git ls-files`/`git log` show no history for it) sitting in `C:\trading-hub`'s working tree. It's a self-contained standalone project (own `README.md`, `.env.example`, `.gitignore`, `requirements.txt`, `run_dashboard.bat/sh`, `install_check.py`, `make_shortcut.ps1` — 28 files, 567 KB), unrelated to Stater Swap or the crypto subsystem. Its one test file does `from stable.metrics import ...`, which only resolves inside that project's own environment, not from this repo's root:

```
ERROR stable_market_board_LATEST/stable_market_board/tests/test_metrics_synthetic.py
ImportError: ModuleNotFoundError: No module named 'stable'
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

Stopped and reported per the gate's own wording. **Nick's ruling: exclude it from pytest scope, leave the folder in place.** Added `pytest.ini` at repo root (`addopts = --ignore=stable_market_board_LATEST`, additive-only, doesn't touch pytest's other default discovery behavior, doesn't touch the folder itself).

Also discovered along the way: the recorded `18f/297p/1s/203e` baseline was produced by a *narrower* command than a bare root `pytest` — `cd backend && python -m pytest tests/ -q` (per `s3-phase0-findings.md` §1.7), scoped to `backend/tests/` only. A bare root-level run (even with the exclusion in place) also picks up untracked `scripts/test_close_double_tap.py` / `scripts/test_prod_close_double_tap.py` and produced a different, non-comparable count (27 failed / 410 passed). Re-ran with the **exact baseline-matching command**:

```
cd backend && python -m pytest tests/ -q
18 failed, 346 passed, 1 skipped, 79 warnings, 203 errors in 11.59s
```

**18 failed — identical count to baseline.** Confirmed byte-for-byte identical composition, not just count: same 2 feed-tier/scanner (`test_feed_tier_v2_replay.py`, `test_feed_tier_classifier_v2.py`) + 2 countertrend (`test_countertrend.py`) + 14 `test_uw_api_mapping.py` = 18. **203 errors — same count, same pre-existing environment class** (async-fixture collection errors on `test_positions.py`/`test_webhooks.py`, unchanged from every prior baseline this engagement). Passed: 297 → 346 (**+49**, matches the S-3 completion report's "49 new tests across 3 test files"). Skipped: 1 → 1, unchanged. **No NEW red. PASS.**

## d) Fable hub-side verification

Fable cross-lane, 2026-07-17 17:36Z via Pandora MCP: hub_get_crypto_market_profile(BTC) ok/fresh (POC 64093.97, NY session, 7 bars) proving S-3 Phase-4 live post-deploy; hub_get_crypto_quote(BTC) live 63958 UW, web cross-check within 0.1%; hub_get_quote(SPY) live 745.97; board state tide BULLISH, kill-switch inactive. Scheduler-fire + hot-reload + known-red evidence delegated to CC Phase 0.0 (desktop bridge down); Fable re-verifies via VPS curl when bridge restored.

## Status

**Phase 0.0 fully clears: (a) PASS, (b) PASS, (c) PASS.** No redeploys triggered anywhere in this check.

Moved on to the S-3b brief's own Phase 0.1 klines audit next — that audit surfaced a separate, second hard-stop-class finding (a ticker-format defect in `get_market_structure_context()`'s Binance klines fetch, live in production since yesterday's `0037375`, worse than the brief's anticipated "BTC-only" case). Written up separately: `docs/strategy-reviews/stater-swap-redesign/s3b-phase0-findings.md`. **Not proceeding to S-3b Item 1 or Item 2** pending Nick/Fable ruling on that finding — this note's own Phase 0.0 scope is otherwise fully closed.
