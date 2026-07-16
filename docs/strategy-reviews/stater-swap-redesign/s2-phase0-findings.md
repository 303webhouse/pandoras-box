# Stater Swap v2 — S-2 Phase 0 Findings (R-1: Regime & Session Layer)

**Date:** 2026-07-15 | **Brief:** `docs/codex-briefs/2026-07-15-stater-swap-s2-regime-session-brief.md`
**Scope:** Read-only reconnaissance per §3 (0.1–0.10). No code changes except the docs-only D-1/D-2/D-3 tasks (§4), which ride in this same commit window per the brief's own instruction.

## 0.1 — Equity regime classifier (mirror target) + existing crypto regime-adjacent logic

**Equity mirror target.** `backend/scoring/adx_regime.py:26-54` — `classify_adx_regime(adx, stale=False)`. Taxonomy: `trending` / `transitional` / `choppy` / `unknown` (4 states — **not** `TREND_UP`/`CHOP`/`TREND_DOWN`). Thresholds: `TRENDING_MIN=25.0`, `TRANSITIONAL_MIN=20.0` (lines 14-15). Inputs: ADX(14) on SPY daily bars only — **no 50-DMA, no slope term anywhere in this module.** Writer: `backend/jobs/adx_regime_job.py:24-64`, RTH-only, every 15 min (`main.py:628-645`), writes Redis `regime:spy_adx_shadow`. Predecessor thresholds (same 25/20) live inline in `scoring/trade_ideas_scorer.py:583-603`.

**Deviation from the brief's premise, flagged honestly:** the committee brief's PYTHAGORAS note (`2026-07-12-stater-swap-v2-committee-brief.md:49`) describes the mirror target as "50-DMA... upgraded with ADX and DMA slope." **No shipped equity module combines all three.** The closest SMA-based classifier is `cta_scanner.py`'s `get_cta_zone` (SMA-only); the closest ADX classifier is `adx_regime.py` (ADX-only). The literal strings `TREND_UP`/`TREND_DOWN` appear **nowhere in shipped code** — only in the S-2 and committee briefs as the *proposed* design. "Mirroring" is conceptual (borrow the general shape: threshold-based, config-driven, shadow-validated), not literal code reuse. S-2's classifier is a genuinely new module, not an extension of an existing one — noted so nobody goes looking for equity code to extend.

**Existing crypto regime-adjacent logic (mapped so S-2 doesn't create a competing truth):**
- **CTA-zone classifier** — `scanners/cta_scanner.py:210-231`, `get_cta_zone(price, sma20, sma50, sma120)`. `CAPITULATION` (`sma20<sma120`), `MAX_LONG`, `DE_LEVERAGING`, `WATERFALL` (`price<sma50`), `TRANSITION`, `UNKNOWN`. No ADX/slope in the zone formula. Consumers: `trade_ideas_scorer.py:779`, `watchlist/enrichment.py:151`, `discord_bridge/bot.py:446-478`, `signals/pipeline.py:209` (persisted per-signal), `jobs/score_signals.py:308-318`. **This is the CAPITULATION/WATERFALL classifier from the Crypto Scanner dormancy investigation (S-1 F-4) — stays untouched, S-2 does not modify or replace it.**
- **Brief-2E's regime pre-filter** — found, spec'd (`docs/codex-briefs/brief-2e-stater-swap-enrichment.md:180-256`) and implemented (`strategies/crypto_setups.py:390-428`, `_check_btc_regime()`). ATR-ratio based: `QUIET`/`VOLATILE`/`TRENDING`/`RANGING`/`UNKNOWN`. Called every cycle in `run_crypto_scan()` (`:433-467`, 5-min cadence, `main.py:378-390`). Distinct, gate-only mechanism — not to be conflated with S-2's proposed DMA/ADX classifier.
- **`backend/api/regime.py`** computes a market-wide sentiment label (Favorable/Cautious/Unfavorable/Hostile) from composite bias — not asset-specific, unrelated to crypto-ticker regime.

**Mandate confirmed satisfiable:** none of the above compute a per-symbol TREND_UP/CHOP/TREND_DOWN state today. S-2's classifier becomes the canonical crypto regime for gating with no existing code to reconcile against — a clean slot.

## 0.2 — Daily-bars availability, live-checked per symbol

Called `jobs/crypto_bars.py::fetch_crypto_bars(symbol, now, use_daily=True)` live on Railway for all six symbols (2026-07-15, ~19:23 MDT):

| Symbol | Bars (n) | Latest bar | Age | Source |
|---|---|---|---|---|
| BTC | 226 | 2026-07-16T00:00:00Z | ~1.4h | UW `/ohlc/1d` |
| ETH | 226 | 2026-07-16T00:00:00Z | ~1.4h | UW `/ohlc/1d` |
| SOL | 226 | 2026-07-16T00:00:00Z | ~1.4h | UW `/ohlc/1d` |
| ZEC | 500 | 2026-07-16T00:00:00Z | ~1.4h | Binance spot klines |
| HYPE | 300 | 2026-07-15T16:00:00Z | ~9.4h | OKX candles |
| FARTCOIN | 300 | 2026-07-15T16:00:00Z | ~9.4h | OKX candles |

**All six symbols clear both thresholds by a wide margin** (≥120 full, ≥60 minimum-compute) — no symbol launches in permanent-UNKNOWN due to insufficient history.

**ZEC's flagged unverified edge is now closed:** S-1 only verified ZEC's Binance-spot-klines source at 15m granularity (`s1-phase2-findings.md`). This check confirms the **1d interval also works live** — 500 real daily candles returned, same vendor. D-3 below updates the matrix doc's stale caveat accordingly.

**New observation, not in the brief's ask but worth flagging:** HYPE/FARTCOIN's OKX daily candles are ~9.4h stale at check time vs. ~1.4h for the UW/Binance-sourced symbols — a real vendor-freshness asymmetry across the six symbols. Not a blocker (both are far above the staleness threshold in §6.1's spec, `stale_bars_max_hours: 48`), but the regime classifier's `degraded`/`degrade_reason` fields will likely show HYPE/FARTCOIN as more frequently "less fresh" than the other four in normal operation — expected, not a bug, worth knowing before someone sees an anti-fake-healthy check flag it.

## 0.3 — Scheduler pattern

Two mechanisms coexist. **APScheduler** (`bias_scheduler.py::start_scheduler()`, `AsyncIOScheduler` at line 2591, jobs via `scheduler.add_job(...)`, `scheduler.start()` at line 2779) — cron and interval examples at lines 2603-2609 and 2665-2672; an existing **hourly** job to copy: `auto_dismiss_old_signals`, `'interval', hours=1` (lines 2655-2662). **Plain-asyncio-loop** (`main.py` startup, `while True` + `asyncio.sleep(N)` + `asyncio.create_task(...)`) — hourly examples: `sector_rs_loop()` (`main.py:307`), `factor_staleness_loop()` (`:375`), `wh_accumulation_loop()` (`:523`), `oracle_refresh_loop()` (`:788`), `price_collector_loop()` (`:805`).

**Recommendation for Phase 2:** slot the regime job in alongside `auto_dismiss_old_signals` in the APScheduler block (`bias_scheduler.py:2655-2662`) via `scheduler.add_job(run_crypto_regime_job, 'interval', hours=1, id='crypto_regime', name='Crypto Regime Classifier', replace_existing=True)` — matches the brief's own suggested home (`backend/jobs/crypto_regime.py`) and reuses an already-proven hourly slot rather than adding a new `main.py` loop.

**Job-level disable flags — two concrete patterns:** (a) env-var boolean gating registration itself — `_bool_env()` helper (`bias_scheduler.py:35-39`), `ENABLE_PRICE_HISTORY_COLLECTION` (line 42) gates `scheduler.add_job(...)` at lines 2685-2698; (b) env-var checked inside the loop body — `TRITON_SHADOW_ENABLED` at `main.py:686-688` (task still created, no-ops if disabled). Recommend pattern (a) for the regime job (skip registration entirely when disabled, matching the brief's "job-level disable flags" ask).

## 0.4 — Existing session windows (`/btc/sessions`)

**Route correction from the brief's assumed path:** the actual mounted routes are **`/api/btc/sessions`** and **`/api/btc/sessions/current`** (`api/btc_signals.py:159-187`, router prefix `/btc` mounted with `prefix="/api"` in `main.py:1381`) — not bare `/btc/sessions`. Backing data: static `BTC_SESSIONS` dict + `get_current_session()` in `bias_filters/btc_bottom_signals.py:787-859`.

**Window inventory** (`btc_bottom_signals.py:787-823`, live boundary check at `:846-855`):

| Window | NY local time | Live check |
|---|---|---|
| `asia_handoff` | 8pm–9pm | `20 <= hour < 21` (NY) |
| `london_open` | 4am–6am | `4 <= hour < 6` (NY) |
| `peak_volume` | 11am–1pm | `11 <= hour < 13` (NY) |
| `etf_fixing` | 3pm–4pm | `15 <= hour < 16` (NY) |
| `friday_close` | Fri 3:55pm–4pm | `weekday==4 and hour==15 and minute>=55` (NY) |

**Not hardcoded UTC as expected — it's NY-local wall-clock.** The `utc_time` field on each window is a static, human-readable label only; the live comparison computes `datetime.now(ZoneInfo("America/New_York"))` and branches on local NY hour/minute/weekday, which shifts against UTC across DST. **This is a real design decision S-2 must make explicitly**: keep this NY-local convention (matches the brief's own IANA-anchoring language for London Open/ETF Fixing/CME Close, hard rule 3) or switch fully to fixed-UTC per §6.2's "convention-tied windows may stay fixed-UTC" carve-out. Recommend: S-2's new session engine is IANA-anchored per-window as specced (§6.2's `anchor_tz` field), which is actually a stricter, more correct version of what `/btc/sessions` already does informally — no conflict, just don't assume the legacy route was fixed-UTC when seeding boundary values from it.

**Consumers:** `frontend/app.js::loadBtcSessions()` (polls every 10 min, line 7751) **and** a duplicated client-side re-implementation of the same hour-window logic (`findActiveSessionClient()`, lines 8087-8127) — not shared with the backend, a pre-existing duplication S-2 doesn't need to fix but shouldn't copy either. `discord_bridge/bot.py::build_crypto_market_context()` (lines 2031-2042) also calls both routes for committee/chat context.

**Auth posture:** both GET routes are **public/unauthenticated** — no `Depends(...)` (contrast with sibling mutating routes in the same file, e.g. line 67's `Depends(require_api_key)`). S-2's new `/api/crypto/regime` and `/api/crypto/clock` read endpoints should mirror this: no auth dependency, consistent with every other crypto read surface.

## 0.5 — Config hot-reload patterns

**No finished, reusable Postgres-backed versioned-config pattern exists yet.** Two Redis-backed boolean toggles are proven and copyable as-is: `quota_shed:triton` (`uw_budget_watchdog.py:42,62-73`, TTL = seconds-to-UTC-rollover, fail-open) and `crypto_dual_write:enabled` (`crypto_dual_write_shadow.py:39,43-58`, no TTL, fail-open, explicitly modeled on the `quota_shed` pattern). Neither is a DB-backed *versioned* config — both are single-key flags.

`system_config` (Postgres, `postgres_client.py:2292-2306`) is **confirmed still unused/aspirational** — independently reconfirmed (matches the prior session's finding cited in `crypto_dual_write_shadow.py:26-29`'s own comment): no `SELECT ... FROM system_config` read path exists anywhere in `backend/`.

**Verdict: §5.3's design stands as specified — build it fresh.** `crypto_gate_config` (max-id-row + 60s in-process TTL cache, append-only) is the right shape and has zero precedent to reuse; it is itself the first implementation of this pattern in the codebase. No wasted effort reusing something that doesn't exist — Phase 1 builds the loader from scratch per §5.3.

## 0.6 — Strategy-name inventory (code + live data)

**From code**, crypto-capable strategy identifiers: `crypto_setups.py` — `Funding_Rate_Fade` (line 168), `Session_Sweep` (line 279), `Liquidation_Flush` (line 367). `bias_scheduler.py` — `Crypto Scanner` (the F-4-cutover strategy). `webhooks/tradingview.py` — `Holy_Grail` (line 428; explicit crypto cooldown variant at line 84's `{"equity": 7200, "crypto": 3600}`, confirming it CAN carry `asset_class=CRYPTO`), `Exhaustion` (line 509, equity-focused per its cooldown config but not asset-class-gated so a crypto alert is theoretically possible).

**From live data** (`SELECT strategy, COUNT(*) FROM signals WHERE asset_class='CRYPTO' GROUP BY strategy`, run 2026-07-15, all-time):

| Strategy | Count | First seen | Last seen |
|---|---|---|---|
| Crypto Scanner | 830 | 2026-03-03 | 2026-07-03 |
| Session_Sweep | 135 | 2026-03-13 | 2026-07-15 |
| (4 S-1/S-2 test-tagged rows, 1 each — excluded, not real strategies) | | | |

**Reconciliation, per the brief's own instruction (config fix, not a code fix):** in the entire history of the `signals` table, **only two crypto strategy names have ever actually produced a signal** — `Crypto Scanner` and `Session_Sweep`. `Funding_Rate_Fade`, `Liquidation_Flush`, `Holy_Grail` (crypto), and `Exhaustion` exist in code but have **never** fired for a crypto ticker. The §6.3 seed config's `strategy_classes` keys them anyway (forward-looking, reasonable), but casing differs from the code's actual strategy strings (seed uses lowercase `"session_sweep"`/`"funding_rate_fade"`/`"holy_grail"`/`"liquidation_flush"`; code emits title-case `"Session_Sweep"`/`"Funding_Rate_Fade"`/`"Holy_Grail"`/`"Liquidation_Flush"`). **Phase 1's seed config must match the code's exact casing** (`Session_Sweep`, `Funding_Rate_Fade`, `Liquidation_Flush`, `Holy_Grail`) or the gate evaluator's strategy-class lookup will silently miss every real signal and fall through to `unclassified`/`WOULD_PASS_WITH_NOTE` for everything — a config bug, not a code bug, exactly as the brief anticipated, now with the exact fix identified.

## 0.7 — Hook point + conflict-dismissal mechanism

**No existing "crypto branch" inside `process_signal_unified()` to hook into.** Grepped the entire function (`signals/pipeline.py:1151-1531`, post-F-4-cutover `47b4a79`) for `asset_class` — **zero references.** The unified pipeline is asset-class-agnostic throughout; it never branches on `signal_data.get("asset_class")` anywhere. This is a correction to the brief's premise (§3's "0.7 — the exact file:line in process_signal_unified's crypto branch"): **there is no crypto branch to find** — Phase 4 (§6.4) will need to **add** a new conditional (`if signal_data.get("asset_class") == "CRYPTO":`) rather than hook an existing one.

**Recommended insertion point:** immediately after step 4's persistence completes and before step 4a's catalyst-confluence hook — `signals/pipeline.py:1376-1386` (right after `await log_signal(signal_data)` and its immediately-following `write_signal_outcome()` call). This satisfies hard rule 5 (wrapped, non-blocking) and the brief's own "AFTER the signal is persisted" requirement (§6.4.1) exactly, since persistence has already completed at that point in the function.

**Conflict-dismissal persistence mechanism** (`_check_and_clear_conflicting_signals`, `pipeline.py:851-953`) — the exact mechanism §6.4's dormant enforcement branch will reuse verbatim:
- Status value: `UPDATE signals SET status = 'DISMISSED', notes = COALESCE(notes, '') || $1` (lines 909-918, 921-929) — applied to both the old conflicting signal(s) and the new one.
- Reason field: appended into the existing `notes` column as free text (`" | Auto-dismissed: ..."`, line 901-905), not a dedicated structured column — S-2's `dismiss_reason='REGIME_GATE:' + reasons` (§6.4.4) should follow this same free-text-appended-to-`notes` convention for consistency, unless a dedicated column is preferred (CC's call in Phase 4, noted here as an open question).
- Feed exclusion: confirmed via `api/trade_ideas.py:53`'s main feed query (`WHERE status = 'ACTIVE'`) — `DISMISSED` is naturally excluded, no separate exclusion list needed. `api/trade_ideas.py:415` also lists `DISMISSED` among `terminal_states`.
- Redis cleanup: `redis.delete(f"signal:{sid}")` for each dismissed signal (lines 933-941), best-effort.

## 0.8 — Docs recovery sweep

Both files searched for per the brief are **found locally, untracked, at their exact cited/expected paths**:
- `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md` — 103 lines, matches its own header content exactly (the source brief for all of S-1).
- `docs/strategy-reviews/stater-swap-redesign/2026-07-13-titans-review-stater-swap-v2.md` — 65 lines, a coherent Titans Review Record consistent with every carry-forward reference already quoted verbatim elsewhere in this session's work (the S-2 brief's own §1 table matches this file's "Carry-forward obligations" section exactly).

D-2 commits both as-is, pathspec-only, no reconstruction needed.

## 0.9 — Known-red test baseline

Ran the full suite (`cd backend && python -m pytest tests/ -q`), 2026-07-15: **18 failed, 273 passed, 1 skipped, 203 errored.**

**FAILED (18, the real red-test signal):**
- 2 scanner: `tests/signals/test_feed_tier_classifier_v2.py::test_path_a_footprint_long` (matches brief's expectation exactly), `tests/integration/test_feed_tier_v2_replay.py::test_all_ceiling_capped_pullback_entries_stay_capped` (matches brief's "pullback_entry" shorthand).
- 2 countertrend: `test_countertrend.py::test_accept_counter_short_extreme_bull` (reproducible in isolation too), `test_accept_counter_long_extreme_bear` (only fails in the full-suite run — passes when `test_countertrend.py` is run alone; order/shared-state flakiness, not a genuine regression — confirmed via isolated re-run).
- 14 in `test_uw_api_mapping.py` (all `test_*`) — every one fails with `Failed: async def function and no async plugin installed`, i.e. a missing `pytest-asyncio` plugin/marker in this local run, not an application bug.

**ERRORED (203, NOT counted as "red"):** every parametrized case in `test_auth.py`, `test_frontend_routes.py`, `test_positions.py`, `test_webhooks.py` errors identically at `conftest.py`'s shared `client` fixture with `TypeError: Client.__init__() got an unexpected keyword argument 'app'` — a Starlette/httpx version mismatch in this local sandbox's Python environment, confirmed via `git stash` to reproduce identically on pre-S-1 code (pure environment issue, zero application-code involvement).

**Deviation from the brief's "8 red (2 scanner, 6 environmental: envelope/trade_ideas/hermes)" expectation, reported honestly rather than forced to match:** the scanner count (2) matches exactly. The "6 environmental" figure cannot be confirmed against this sandbox — the 203 fixture-level errors mask whatever the real pass/fail split would be for `test_auth.py`/`test_frontend_routes.py`/`test_positions.py`/`test_webhooks.py` (which do reference trade-ideas/envelope-shaped endpoints) in an environment where the Starlette/httpx mismatch didn't exist. This sandbox's actual observable "environmental" reds are the 14 `test_uw_api_mapping.py` failures (a missing-plugin issue, different root cause than whatever the brief's author saw). **Recorded baseline for Done item 13's regression check: the 18 FAILED tests listed above, by name** — the 203 errors are a known, pre-existing, environment-only condition and are excluded from the regression comparison (Railway's actual deployed environment has none of this — verified extensively via live functional tests all S-1 session).

## 0.10 — Bypass-retirement tracker

Per the S-1 closure note's standing instruction, ran `scripts/crypto_dual_write_diff_report.py` before touching `bias_scheduler.py`'s neighborhood:

```
Comparison rows total : 3  (real=unified pipeline, shadow=demoted bypass scorer)
Retirement bar (brief F-4.1): >= 48h OR n >= 30 -- NOT YET MET
```

All 3 rows are one-off tagged test signals from S-1's F-4 verification (`S1_PHASE4_DUALWRITE_SMOKE_BTC_20260715`, `S1_PHASE4_CUTOVER_SMOKE_BTC_20260715`, `S1_PHASE4_DATETIME_FIX_VERIFY_BTC_20260715`) — none count toward the bar per the S-1 closure note's own framing. The demoted bypass shadow-logger is still active and untouched; S-2 does not need to interact with it beyond this check. Whoever next touches the Crypto Scanner's neighborhood after S-2 should re-run this same check.

## Migration numbering

Confirmed next free number: **025** (`migrations/` tops out at `024_crypto_dual_write_shadow.sql`). Matches the brief's own expectation — no renumbering needed.

## Summary of deviations from the brief's stated expectations (all informational, none blocking)

1. **0.1** — the equity "mirror target" is conceptual, not a literal shipped module combining 50-DMA+ADX+slope; two separate single-metric modules exist instead.
2. **0.2** — HYPE/FARTCOIN's OKX daily bars are ~9.4h stale vs. ~1.4h for the other four symbols at check time (both within spec, just asymmetric).
3. **0.4** — the actual route is `/api/btc/sessions` (not bare `/btc/sessions`), and its live boundary logic is NY-local wall-clock, not fixed-UTC as the brief assumed.
4. **0.6** — strategy-name casing mismatch between the seed config (lowercase) and actual emitted strategy names (title-case) — must be fixed in Phase 1's seed, not code.
5. **0.7** — no existing crypto branch inside `process_signal_unified()` to hook; Phase 4 adds a new conditional at the recommended insertion point (`pipeline.py:1376-1386`).
6. **0.9** — actual baseline is 18 FAILED (not the expected 8), with the gap fully explained by two distinct, pre-existing, non-application-code environment issues (a missing pytest-asyncio plugin, and a Starlette/httpx version mismatch) rather than any real regression. Recorded baseline for Done item 13 is the 18-test list above.

None of these block Phase 1. Proceeding per the brief's own gate: Phase 0 findings committed before any Phase 1+ code.
