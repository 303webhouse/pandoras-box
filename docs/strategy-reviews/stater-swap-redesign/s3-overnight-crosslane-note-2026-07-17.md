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

Both jobs run `interval, hours=1` (`backend/scheduler/bias_scheduler.py`), last fired `17:14Z` (regime) / `17:37Z` (cycle) — next natural firings expected ≈`18:14Z` / ≈`18:37Z`. **The two INSERT rows are the evidence of the proof precondition landing; confirmation that the next scheduled evaluation stamps `config_version=3`/`config_version=2` (zero redeploys) was not yet observable synchronously within this check** (both jobs are hourly, no on-demand trigger endpoint exists). This differs from the S-2 DD-8 proof's immediate-pickup framing — that proof's timing is not reproducible on demand here without an admin trigger. Follow-up: re-query `MAX(config_version)` on both log tables after `18:40Z` to close this out.

## c) pytest full suite — STOP, do not proceed

`python -m pytest --tb=no -q` from repo root: **collection was interrupted, 0 tests collected**, not a pass/fail/error count comparable to the recorded baseline (`18f/297p/1s/203e`, commit `d0ed66e`).

```
ERROR stable_market_board_LATEST/stable_market_board/tests/test_metrics_synthetic.py
ImportError: ModuleNotFoundError: No module named 'stable'
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

Root cause: **`stable_market_board_LATEST/` is a completely untracked, never-committed directory** (`git ls-files` returns nothing for it; `git log` has no history for it) sitting in `C:\trading-hub`'s working tree. It is a self-contained standalone project (own `README.md`, `.env.example`, `.gitignore`, `requirements.txt`, `run_dashboard.bat/sh`, `install_check.py`, `make_shortcut.ps1` — 28 files, 567 KB) — not part of this repo, unrelated to Stater Swap or the crypto subsystem. Its one test file imports `from stable.metrics import ...`, which only resolves inside that standalone project's own environment, not from `c:\trading-hub` as pytest rootdir. There is no `pytest.ini`/`pyproject.toml`/`setup.cfg` at repo root scoping collection away from it, so a bare full-suite `pytest` invocation walks into it and aborts collection for the entire run.

**This is a genuine NEW red under the gate's own criteria** ("any NEW red = STOP, report, do not proceed") — a full collection abort is strictly worse than the baseline's 18 known failures, and no valid pass/fail diff can be produced until this is resolved. Per instruction: **stopping here, not proceeding to the S-3b brief's Phase 0.1 klines audit or any event-anchoring code.**

Not touched: the directory itself (unfamiliar, untracked, possibly Nick's in-progress work dropped in deliberately — not deleted or moved without confirmation).

## d) Fable hub-side verification

Fable cross-lane, 2026-07-17 17:36Z via Pandora MCP: hub_get_crypto_market_profile(BTC) ok/fresh (POC 64093.97, NY session, 7 bars) proving S-3 Phase-4 live post-deploy; hub_get_crypto_quote(BTC) live 63958 UW, web cross-check within 0.1%; hub_get_quote(SPY) live 745.97; board state tide BULLISH, kill-switch inactive. Scheduler-fire + hot-reload + known-red evidence delegated to CC Phase 0.0 (desktop bridge down); Fable re-verifies via VPS curl when bridge restored.

## Status

**Phase 0.0 does NOT clear.** (a) and (b)'s precondition both pass; (b)'s full confirmation is pending the next hourly firing (~18:14Z/~18:37Z, not yet due at time of writing, ~17:56Z); (c) is a hard stop pending Nick's decision on `stable_market_board_LATEST/` (exclude from pytest scope vs. relocate out of the repo working directory vs. something else). Not proceeding into the S-3b brief itself until this clears.
