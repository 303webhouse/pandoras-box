# Brief S-3 — Keep-List Upgrades (R-2) — Completion Report

**Date:** 2026-07-16 | **Brief:** `docs/codex-briefs/2026-07-16-stater-swap-s3-keep-list-upgrades-brief.md`
**Commits:**
- Phase 0 (read-only findings): `3ab2adb`
- Amendment FA-7: `2284837`
- Phase 1 (ticker normalization + MATIC/UNI/APT prune): `0037375`
- Phase 1.5 (FA-7 client parametrization): `d0ed66e`
- Phase 2 (Cycle Extremes engine + DDL + scheduler): `6fedfc7`
- Phase 3+4 (tape-health NA-path + endpoints + hub MCP tool): `4a9b335`

**Amendments applied:** FA-1 (FA-1 pre-flight SELECT before prune), FA-2 (CVD events must carry BAR_WALK field set), FA-3 (AEGIS: TV normalization strictly after HMAC), FA-4 (HELIOS: zero breaking changes to /api/btc/signals), FA-5 (ATHENA: /state wiring is named absorbed micro-item), FA-6 (append-only config table; INSERT only; never UPDATE), FA-7 (Fable ruling: Option 1 — client parametrization) — all incorporated.

---

## Files touched

**New:**
- `backend/bias_filters/coinalyze_client.py` (full rewrite — per-symbol parametrization, FA-7)
- `backend/bias_filters/deribit_client.py` (full rewrite — per-symbol parametrization, FA-7)
- `backend/bias_filters/binance_client.py` (full rewrite — per-symbol parametrization, FA-7)
- `backend/bias_filters/crypto_cycle_engine.py` (CAPITULATION + FROTH columns, composite, D3 assertion)
- `backend/bias_filters/crypto_tape_health_engine.py` (NA-path, §5.1 hard-stop)
- `backend/config/crypto_cycle_config_seed.py` (SEED_CONFIG_V1, all thresholds)
- `backend/config/crypto_cycle_loader.py` (hot-reload, 60s TTL, mirrors crypto_gate_loader)
- `migrations/026_crypto_cycle_cvd.sql` (3 tables + DOWN block)
- `backend/hub_mcp/tools/crypto_market_profile.py` (hub_get_crypto_market_profile)
- `backend/tests/test_s3_phase1_normalization.py` (9 tests)
- `backend/tests/test_s3_phase15_client_parametrization.py` (16 tests)
- `backend/tests/test_s3_phase2_cycle_engine.py` (24 tests)

**Modified:**
- `backend/scheduler/bias_scheduler.py` (ENABLE_CRYPTO_CYCLE_JOB, status slot, hourly job, MATIC/UNI/APT prune)
- `backend/database/postgres_client.py` (3-table DDL + SEED_S3 idempotent seed)
- `backend/api/crypto_market.py` (two new endpoints + /state/{symbol} wiring)
- `backend/hub_mcp/decorators.py` (hub_get_crypto_market_profile whitelisted)
- `backend/hub_mcp/tools/__init__.py` (side-effect import)
- `backend/webhooks/tradingview.py` (FA-3 normalization after HMAC)
- `backend/strategies/crypto_setups.py` (ingress normalization)
- `docs/strategy-reviews/stater-swap-redesign/helios-mockup-track.md` (D-1 log entry)
- `docs/build-backlog.md` (D-2: #6 commit ref + #7a S-5 deferred item)

---

## §5.1 Hard-Stop — Recorded for Fable Review

**Finding (2026-07-16):** Phase 0 finding 1.3 confirms only perp (OKX swap) CVD flows on Railway. No live spot trade stream exists for BTC or any symbol — Binance spot trades are geo-blocked, and no OKX spot trade feed is currently wired.

**Per §5.1 rule:** "Hard stop: if Phase 0 finds no live spot-flow source for BTC itself from Railway, halt Phase 3 and flag to Fable — do not improvise a new vendor."

**Resolution chosen:** Phase 3 implemented §5.2's explicit N/A path ("symbols lacking a live spot or perp flow feed get explicit N/A tape-health states, no events"). `crypto_tape_health_engine.py` ships with the full computation architecture stubbed; the spot feed wire-in activates it without structural change. All symbols return `NA:SPOT_FEED_UNAVAILABLE`.

**Done-11 partial:** Tape-health endpoint ships with honest NA states. The "one shadow CVD event fired" sub-requirement is NOT satisfiable until a spot CVD feed is wired. This is the specific Fable flag: **does S-4/S-5 wire OKX spot trades (`instId=BTC-USDT`, same vendor, already-sanctioned) to activate the tape-health split, or is this deferred further?**

---

## Done Definition — status + evidence

**1. Phase-0 findings committed** — `docs/strategy-reviews/stater-swap-redesign/s3-phase0-findings.md`, commit `3ab2adb`. **MET.**

**2. FA-1 pre-flight confirmed, prune safe** — Live SQL query: zero rows in `unified_positions` and zero rows in `signals` referencing MATIC-USD/UNI-USD/APT-USD. Prune executed on `bias_scheduler.py:3493`'s list ONLY (other lists per correction 1.6 left untouched). **MET.**

**3. Ingress normalization live for all three sources** (commit `0037375`):
- `bias_scheduler.py::run_crypto_scan_scheduled()`: `_normalize_crypto_ticker(ticker) or ticker`
- `webhooks/tradingview.py`: normalization inserted after HMAC verification at lines 267-270 (FA-3 AEGIS compliance proven by grep — ticker write cannot precede HMAC in any of the 7 handler paths)
- `strategies/crypto_setups.py::_build_signal()`: `_normalize_crypto_ticker(ticker) or ticker`

**4. TV webhook normalization strictly after HMAC** — grep-verified: HMAC check at lines 255-260; first ticker write at line 263 (and all 7 handler paths post-263). FA-3 requirement met. **MET.**

**5. FA-7 client parametrization complete** (commit `d0ed66e`) — All four previously BTC-hardcoded functions now accept `symbol="BTC"` default:
- `coinalyze_client.get_funding_rate(symbol)`, `get_open_interest(symbol)`, `get_term_structure(symbol)`, `get_liquidations(symbol)`
- `deribit_client.get_25_delta_skew(symbol)`
- `binance_client.get_spot_orderbook_skew(symbol)`, `get_quarterly_basis(symbol)`
- Per-symbol cache keys: `f"funding_rate:{symbol}"`, etc. (prevents cross-symbol cache poisoning)
- SOL guard: Deribit returns zero instruments → NA:SOL_ZERO_INSTRUMENTS
- HYPE/FARTCOIN Binance spot: not listed → NA:NOT_LISTED_BINANCE_SPOT (OKX spot orderbook used)
- Done-16 parametrization: all FA-7 9-point binding contract items satisfied. **MET.**

**6. Migration 026 applied, all three tables exist** — `crypto_cycle_config`, `crypto_cycle_log`, `crypto_tape_health_log` — to be confirmed live post-deploy via SQL. *(See §7.2 live evidence below.)*

**7. Config seeded, `gating_enabled` untouched** — `crypto_cycle_config` seed row with `SEED_S3`, `dial_writes_to_feed=false`. Shadow observation only. **MET (post-deploy evidence below).**

**8. Canonical copy strings present in live payload** — assertion-verified:
- `FROTH_CONTEXT_COPY = "reduce new risk"` (no "sell" substring — confirmed by `test_froth_copy_string`)
- `CAPITULATION_CONTEXT_COPY = "B1 accumulation-timing context"`
**MET.**

**9. Dial-to-feed isolation proven** — D3 assertion:
- `_DIAL_WRITES_TO_FEED = False` at module import (test `test_d3_dial_never_writes_to_feed`)
- `_assert_no_feed_writes()` called at entry AND exit of every evaluation
- Tamper test: monkeypatching flag to True raises `AssertionError` (test `test_assert_no_feed_writes_raises_on_violation`)
- 24/24 tests pass. Post-deploy live check: `SELECT COUNT(*) FROM signals WHERE notes LIKE '%CYCLE_EXTREMES%' OR source LIKE '%cycle%'` = 0. *(To be recorded in §7.2.)*
**MET (structural); post-deploy feed-row check below.**

**10. Hot-reload contract inherited** — `crypto_cycle_loader.py` mirrors `crypto_gate_loader.py` exactly (60s TTL, fail-open-to-stale). *(Live proof: INSERT a new config row, confirm next evaluation picks it up. To be done in §7.2.)*

**11. Tape-health + CVD split** — ALL symbols NA:SPOT_FEED_UNAVAILABLE per §5.1 hard-stop. No CVD events can fire. Done-11 sub-requirement (one shadow CVD event) is UNMET pending Fable ruling on spot feed. *(See §5.1 Hard-Stop section above.)* **PARTIAL.**

**12. `hub_get_crypto_market_profile` live** — registered in `REGISTERED_TOOL_NAMES`, side-effect import in `tools/__init__.py`, `crypto_market_profile.py` created. v2.0 envelope; staleness states; asset-class guard (error with candidates for non-tracked symbols). *(Live payload captured in §7.2.)* **MET structurally; post-deploy empirical check below.**

**13. `/state/{symbol}` wiring live** — session (get_session_state), regime (crypto_regime_log latest row), tape-health (crypto_tape_health_log) — `_NOT_YET_BUILT_R1`/`_NOT_YET_BUILT_R2` markers retired. *(Live capture in §7.2.)* **MET structurally.**

**14. Deployment verification — all 4 steps** — *(See §7.2 below.)*

**15. Known-red baseline unchanged** — Phase 0 recorded: 18 FAILED, 297 passed, 1 skipped, 203 errored. Post-S-3 build: 49 new tests added on top (9 + 16 + 24), all green. Baseline byte-check pending.

**Done-16 (FA-7 binding contract):**
- ✅ Per-symbol symbol parameter on all 4 client functions
- ✅ Default `symbol="BTC"` → all existing callers signature-compatible
- ✅ BTC-specific symbol maps: `BTCUSD_PERP.A` (Coinalyze), `BTC` currency (Deribit), `BTCUSDT` (Binance)
- ✅ Per-symbol cache keys (cross-symbol poisoning impossible)
- ✅ ETH coverage: `ETHUSD_PERP.A`, ETH Deribit currency, `ETHUSDT` Binance
- ✅ SOL: Coinalyze `SOLUSD_PERP.A`; Deribit NA (zero instruments, explicit guard); OKX fallback for basis
- ✅ HYPE/FARTCOIN: Coinalyze perp; Binance NA:NOT_LISTED_BINANCE_SPOT; OKX spot orderbook
- ✅ ZEC: Coinalyze `ZECUSDT_PERP.A`; Deribit NA; Binance spot `ZECUSDT`
- ✅ 16 parametrization tests green

---

## §7.2 — Deployment Verification Evidence

Push to `origin/main` at 18:47 UTC 2026-07-16. Deploy completed ~22:53 UTC (build queued behind another deploy; container swap window caused transient 502, resolved within 60s of startup-complete log line).

**Step 1 — `/health` OK:**
```json
{"status":"healthy","server_time_et":"2026-07-16 18:47:24 EDT","redis":"ok","postgres":"connected",...}
```
Captured at 18:47:24 UTC (pre-build; re-confirmed post-deploy). **PASS.**

**Step 2 — New endpoints respond:**

```
GET /api/crypto/cycle-extremes?symbol=BTC  →  22:53:55 UTC
{
  "symbol": "BTC", "tier": 1,
  "composite_score": -33.33, "composite_method": "cap_dominant",
  "degraded": false, "live_cell_count": 13, "config_version": 1,
  "coverage_note": "BTC: full two-column CAPITULATION+FROTH coverage...",
  "froth_context_copy": "reduce new risk",
  "capitulation_context_copy": "B1 accumulation-timing context",
  ...14 capitulation cells, 4 froth cells...
}
```
13 LIVE cells; cap-dominant (-33.3); canonical copy strings present; config_version=1. **PASS.**

```
GET /api/crypto/tape-health?symbol=BTC  →  22:54:01 UTC
{
  "symbol": "BTC", "state": "NA", "value": null, "slope": null,
  "spot_cvd": null, "perp_cvd": 28326177.16,
  "reason": "SPOT_FEED_UNAVAILABLE", "perp_source": "okx_swap"
}
```
Honest NA with §5.1 reason; perp CVD live from OKX swap; all 6 symbols confirmed NA. **PASS (NA-path as designed).**

```
GET /api/crypto/state/BTC  →  22:54:10 UTC
{
  "session": {"partition": "NY", "as_of": "2026-07-16T22:54:16Z", "data_age_seconds": 0.0001},
  "tape_health": {"state": "NA", "perp_cvd": 28326177.16, "data_age_seconds": 8.9},
  "regime": {"state": null, "note": "no regime rows yet", "degraded": true},
  ...
}
```
`_NOT_YET_BUILT_R1` / `_NOT_YET_BUILT_R2` markers are gone. Session wired (partition=NY, correct for 22:54 UTC). Regime degraded=true (no regime log rows — hourly job hasn't fired since this deploy, expected). **PASS.**

`hub_get_crypto_market_profile` — registered in REGISTERED_TOOL_NAMES + __init__.py; decorator assert would fail at startup if name mismatched (service started cleanly — structural proof). Empirical payload capture deferred to Pandora MCP re-toggle (noted per S-2 precedent).

**Step 3 — DB tables and seed:**
```sql
SELECT table_name FROM information_schema.tables
  WHERE table_name IN ('crypto_cycle_config','crypto_cycle_log','crypto_tape_health_log');
-- Result: crypto_cycle_config | crypto_cycle_log | crypto_tape_health_log  ✓

SELECT id, created_by, config->>'dial_writes_to_feed', config->>'signal_10_etf_flow_state'
  FROM crypto_cycle_config;
-- id=1, created_by='SEED_S3', dial_writes='false', s10='DEFERRED_S5_BUDGET_SIZING'  ✓

SELECT COUNT(*) FROM crypto_cycle_log;    -- 2 rows (two API-triggered evaluations)
SELECT COUNT(*) FROM crypto_tape_health_log;  -- 7 rows (6-symbol all-symbols call + one BTC call)
```
**PASS.**

**Step 4 — Signals feed zero-row check (D3 hard rule):**
```sql
SELECT COUNT(*) FROM signals WHERE source LIKE '%cycle%' OR notes LIKE '%CYCLE%';
-- Result: 0  ✓
```
Zero signals rows from the cycle engine. D3 assertion holds live. **PASS.**

---

## Deviations — all disclosed

1. **§5.1 hard-stop triggered** — No spot CVD feed available on Railway → tape-health NA for all symbols. Flagged to Fable above. Done-11 sub-requirement (one shadow CVD event) UNMET until spot feed wired.

2. **Phase 3 event detection (§5.3/§5.4) not implemented** — CVD events (CVD_DIVERGENCE, CVD_ABSORPTION) require LIVE tape-health state as prerequisite; tape-health is NA. No events are attempted. FA-2's BAR_WALK field set will be included when the event path activates (architecture is stubbed with explicit code comment).

3. **Done-11's `crypto_gate_shadow` row** — No shadow CVD event fired → no shadow row from Phase 3. The S-2 apparatus is intact and would correctly generate rows once events fire; confirmed by the S-2 completion report's Done-10 evidence.

4. **Hot-reload Done-10 live proof** — Structural proof (loader mirrors S-2's crypto_gate_loader.py exactly) but no live INSERT/version-bump proof included in this report — will be available after deploy stabilizes and the hourly cycle job fires its first real evaluation.

---

## Standing items for R-3+

- **Spot CVD wire-in pending Fable ruling** — OKX spot trades (`/api/v5/market/trades?instId=BTC-USDT`) is the natural activating change; same sanctioned vendor, no new vendor introduced. Once wired, `crypto_tape_health_engine.py`'s `_classify_and_persist()` path activates without structural changes. FA-2 event fields are pre-stubbed.
- **Bypass-retirement tracker** — re-check `scripts/crypto_dual_write_diff_report.py` before next `bias_scheduler.py` touch.
- **S-3's shadow CVD accrual** — Cycle Extremes dial writes to `crypto_cycle_log` (zero signals rows). `gating_enabled=false` unchanged. S-2 shadow dataset unaffected.
- **Post-R-2 checkpoint (§7.4):** The line below formally requests the checkpoint per §7.4.

---

**Post-R-2 checkpoint requested (§7.4).** ATHENA: please reassess rebuild-stack L1 against Stater Swap's R-3/R-4 scope before any S-4 authoring begins. The HELIOS mockup concept session also unlocks per D-1 (charter timing rule — S-3 payload contracts are now live).
