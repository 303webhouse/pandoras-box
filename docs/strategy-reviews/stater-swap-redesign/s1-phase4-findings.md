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

## Addendum (2026-07-15): Crypto Scanner dormancy investigation + F-4 plumbing smoke test

The diff report sat at 0 shadow rows ~17-40h post-deploy. Fable directed a read-only root-cause trace before any fix, plus a single tagged synthetic signal through both paths as a plumbing smoke test. Findings:

**Root cause — market condition, not a bug.** Live-ran `analyze_ticker_cta()` (the exact function `run_crypto_scan_scheduled()` calls per ticker) against production:
- 12/15 tracked tickers (BTC, ETH, SOL, XRP, ADA, AVAX, DOGE, DOT, LINK, LTC, ATOM) sit in `CAPITULATION` zone (`sma20 < sma120` — structural downtrend); NEAR-USD in `WATERFALL` (`price < sma50`). All bearish.
- The scanner's signal set (Golden Touch, Pullback Entry, Volume Breakout, Two-Close-Volume, Zone Upgrade) is long-only trend-continuation logic, and this path calls `analyze_ticker_cta()`/`analyze_ticker_cta_from_df()` with `allow_shorts` defaulted `False` — structurally cannot emit SHORT regardless of regime.
- Bearish structure + long-only criteria = zero qualifying setups everywhere, every cycle. Correct output, not a failure.

**Ruled out:**
- **Scheduler health** — `_scanner_loop()` (started via `asyncio.create_task` at boot) has fired every 30 min without interruption; `mcp_ping` uptime traced continuously back to the Phase 4 deploy; the outer `try/except` around `run_crypto_scan_scheduled()` has never tripped.
- **L0.1a enforcement (`02111cd`, 2026-07-03 07:42 MT)** — its own commit message states Crypto Scanner "bypasses the chokepoint (untagged) -> NOT suppressed by this flip." Confirmed in code: `cta_scanner.py` has zero references to `l0_routing`/`L0_ENFORCE`/`l0_shadow`. Enforcement only filters `/api/trade-ideas` + `hub_get_trade_ideas` read surfaces — never signal generation or this path's direct `log_signal()` write. Timing vs. the last real signal (2026-07-03) is coincidental.
- **Binance** — this scanner path has zero Binance dependency. `analyze_ticker_cta()` fetches via `yf.Ticker(ticker).history(...)` directly; confirmed live, yfinance returning fresh data (BTC $64,968.98, 366 rows, current through today). Binance is used elsewhere (bar-walk resolver, funding/OI clients) but not here.
- **Git history 7/2-7/4** — no commits in that window touch `cta_scanner.py`, the crypto ticker universe, or any Binance client.

**Secondary bug found along the way:** 3/15 `CRYPTO_TICKERS` — `MATIC-USD`, `UNI-USD`, `APT-USD` — return `"possibly delisted; no price data found"` from yfinance every cycle, silently skipped (`error: Insufficient data`), no escalation. 20% of the universe has been dead weight indefinitely. Logged as a backlog quick-fix item (`docs/build-backlog.md` Tier 2 #5), not fixed here (needs a deploy; root cause reported first per instruction).

**F-4 plumbing smoke test.** Fired one clearly-tagged synthetic signal through both paths, live on Railway, following F-2's test-row convention (distinctive `strategy`/`signal_type`, left in place as documented evidence rather than deleted):
- `signal_id`: `S1_PHASE4_DUALWRITE_SMOKE_BTC_20260715`, `strategy: 'S1_Phase4_DualWriteSmoke'`, `signal_type: 'SMOKE_TEST'`, ticker `BTC-USD` — will not be picked up by any real-strategy-name dashboard filter.
- Real path: `log_signal()` + `update_signal_with_score()` (the exact two calls the real bypass makes) — row landed correctly.
- Shadow path: `shadow_write_crypto_signal(trade_signal, signal_id)` (the exact F-4 call site) — landed in `crypto_dual_write_shadow` with `real_signal_id` pointing at the row above, `shadow_signal_id = 'SHADOW_S1_PHASE4_DUALWRITE_SMOKE_BTC_20260715'`.
- `scripts/crypto_dual_write_diff_report.py` re-run: picked up the row cleanly (n=1, real_score=42 vs shadow_score=8, would_suppress=false, feed_tier_v1=watchlist).
- **This row does not count toward the readiness clock.** Per Fable's ruling, the 48h/n>=30 bar restarts from whenever the Crypto Scanner resumes producing real signals — this test proves the mechanism works, it does not seed real evidence. No bar-lowering.

No code changed, no deploy made. Backlog updated (`docs/build-backlog.md`) with the watchdog item + delisted-ticker note before its held commit pushes.

## F-4 Cutover (2026-07-15): inverted shadow — unified pipeline is now primary

Fable ruled cutover greenlit per an "inverted-shadow" recommendation: rather than waiting for organic shadow volume to clear the 48h/n>=30 bar (unlikely at the observed signal rate — see dormancy addendum above), `process_signal_unified` becomes the PRIMARY writer immediately, and the original ad hoc bypass scorer is demoted to a comparison-only shadow-logger. The diff report keeps running until n>=30 REAL (unified-path) signals accumulate, at which point the demoted bypass logger retires entirely — no bar-lowering, the readiness clock restarts from cutover.

**What shipped:**
- `backend/scheduler/bias_scheduler.py::run_crypto_scan_scheduled()`: now calls `process_signal_unified(trade_signal, source="crypto_scanner")` for real — persistence, scoring (`apply_scoring`), feed-tier classification, Redis cache, WebSocket broadcast, committee flagging, and cross-strategy conflict-dismissal all run exactly as they do for every other signal source (`crypto_setups.py`'s `source="crypto_engine"`, the TradingView webhook path, the equity CTA scanner's `source="cta_scanner"`). The old ad hoc `calculate_signal_score()` call is kept but only feeds the demoted comparison row below — no longer authoritative, no longer persisted directly.
- `backend/jobs/crypto_dual_write_shadow.py`: `shadow_write_crypto_signal()` replaced with `log_bypass_shadow_comparison(unified_result, bypass_score, bypass_bias_alignment, bypass_triggering_factors)`. Same `crypto_dual_write_shadow` table (migration 024, reused — no schema change), roles inverted: `real_*` columns now hold the actual persisted unified-pipeline result; `shadow_*` columns hold the demoted bypass scorer's output, recorded for comparison only, never touching the real `signals` table.
- `scripts/crypto_dual_write_diff_report.py`: re-framed from "gates cutover" to "tracks retirement" of the demoted bypass logger. Same n>=30/48h bar, same non-gating discipline (reports only, retirement still requires Nick's explicit go-ahead).

**Pre-deploy fan-out/Discord behavior review** (checklist item — confirmed via full read of `process_signal_unified` plus a 4-agent parallel research pass before touching any code):

| Mechanism | New under cutover? | Expected behavior for crypto |
|---|---|---|
| `signal_notifier.py` crypto Discord embed (VPS cron, Take/Pass/Watching, no Analyze button) | **No — already live today.** This cron polls the `signals` table directly and doesn't care which write path produced a row; Crypto Scanner signals have gotten this embed since before S-1. `is_signal_crypto()` (`scripts/signal_notifier.py:453-459`) checks `asset_class == "CRYPTO"` first, which our `trade_signal` sets explicitly and `process_signal_unified` never overwrites — confirmed correctly routed regardless of ticker format. |
| Feed-tier v2 divergence Discord alert (`DISCORD_WEBHOOK_ZEUS_TA_FEED`, confirmed configured) | Yes — was suppressed under `shadow=True`, now live. | Fires only when `tier_v2 == "top_feed"`. Confirmed structurally unreachable for crypto right now: `apply_scoring()`'s Pythia cross-reference (`pipeline.py:575-576`) sets `feed_tier_ceiling = "watchlist"` whenever a ticker has no Pythia market-profile coverage (true for all crypto today), and `classify_signal_tier_v2` returns `"watchlist"` immediately on that ceiling regardless of score (`feed_tier_classifier_v2.py:260-261`) — before any top_feed path is evaluated. Real but dormant until Pythia gains crypto coverage (separate, unscoped future item). |
| iv_regime VIX-gate Discord alert (`DISCORD_WEBHOOK_ALERTS`, confirmed configured) | No behavior change. | Scoped to `strategy in {"Holy_Grail"}` (`pipeline.py:44,598`). Crypto Scanner's strategy name is `"Crypto Scanner"` — block is skipped entirely, no effect. |
| Committee auto-run (`scripts/committee_railway_bridge.py`, 3-min poll on `status='COMMITTEE_REVIEW'`, cap 10/day) | Yes — genuinely new. The bypass never set this status; the unified path's `_maybe_flag_for_committee()` does, at score>=85. | Contradicts its own queue-endpoint comment claiming manual-only (`committee_bridge.py:48-49`) — it auto-runs a 4-agent committee pass on ANY qualifying signal, crypto included, with per-field enrichment fetches (IV rank, max-pain, options data) failing soft to `None` for tickers that lack it (`committee_bridge.py:255-256`), not crashing. Feed-tier ceiling does NOT block this — confirmed independent gates (feed-tier reads `feed_tier_ceiling`, committee-flagging reads only raw `score`/`score_v2`, `pipeline.py:140` vs `575-576`, never cross-referenced). Live DB query found crypto/crypto-pattern signals have **never** crossed 85 historically (max 72 properly-tagged, 73.7 mistagged-as-equity) — real mechanism, low near-term probability, not independently fire-tested for a crypto ticker in this specific automated path (distinct from the manually-invoked 7-persona Olympus committee already validated on BTC-USD in the S-1 closure smoke pass). Monitored going forward via the diff report's `would_flag_committee` column. |
| Lightning-card dedup (`api/hydra.py::check_lightning_card_match`) | Runs for real now (was skipped under `shadow=True`). | Confirmed safe no-op: `lightning_cards` rows are written exclusively by the equity-only HERMES+HYDRA path (`webhooks/hermes.py`) with plain equity symbols — an exact-string match against `"BTC-USD"` can never coincidentally hit, so this always returns no match, no exception, no logged trace either way. |
| Dashboard rendering (`frontend/app.js`) | No change. | Crypto signals already route through a dedicated `createCryptoSignalCard` (pre-cutover, since `asset_class=CRYPTO` was already set by the bypass) with no Analyze button, committee badge, or options/greeks fields at all — so even a crypto signal that reaches `COMMITTEE_REVIEW` renders exactly like any other crypto card. The only real surfacing of a crypto committee-flag is the auto-run above, wherever its own output posts. |
| Cross-strategy conflict-dismissal (`_check_and_clear_conflicting_signals`) | Reachable for real now (was shadow-only). | Confirmed **not practically triggerable across the three crypto signal sources** — `crypto_setups.py` writes ticker as `"BTCUSDT"`, the Crypto Scanner writes `"BTC-USD"`, and the TradingView webhook path writes whatever raw string TradingView sends. The check matches on exact `UPPER(ticker)` string equality, so these never collide for the same underlying coin. Only same-format, same-strategy conflicts (e.g. two Crypto Scanner signals on the same ticker within 24h, opposite direction) can dismiss each other — identical to how the equity CTA scanner has always behaved. |

**Related, pre-existing bug found incidentally (not introduced by this cutover, not fixed here):** `backend/webhooks/tradingview.py::is_crypto_ticker()` doesn't recognize hyphenated tickers like `"BTC-USD"` — its `CRYPTO_TICKERS` set contains `'BTCUSD'` (no hyphen) and only strips `.P`/`PERP`/`-PERP` suffixes, not a general `-USD` quote-currency suffix. A TradingView alert sending `"BTC-USD"` would get `asset_class` silently miscomputed as `"EQUITY"`. Does **not** affect this cutover (`bias_scheduler.py` sets `asset_class` explicitly on its own `trade_signal` dict, and `process_signal_unified` never recomputes it), but live DB query during this research confirmed 79 existing signals already mistagged this way (none have ever crossed the committee threshold). Added to backlog as a small, separate quick-fix item.

**Verdict:** no blocking risk identified. The one genuinely new, real mechanism (committee auto-run) is gated by a threshold crypto signals have never crossed historically, fails soft on missing enrichment data, and is monitored via the diff report. Proceeding to deploy.
