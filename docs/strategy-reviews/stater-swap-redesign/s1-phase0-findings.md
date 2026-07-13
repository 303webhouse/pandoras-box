# Stater Swap v2 — S-1 Phase 0 Findings (Read-Only Investigation)

**Date:** 2026-07-13 | **Brief:** `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md`
**Repo state:** `main` @ `08f9162` (docs commit ahead of `39c7008`, the Titans-reviewed baseline)
**Scope:** Read-only. No code changed in this phase. All four sub-items (0.1–0.4) investigated in parallel; each finding below is file:line-sourced, not inferred.

---

## 0.1 — Crypto signal write-path trace

### Summary

The repo has **three distinct crypto signal-emission paths**, not the single `log_signal`-only path the committee brief assumed. Two already route through `process_signal_unified`; one writes via `log_signal` directly and is **already documented in-code as a known bypass** (tagged, not hidden):

1. `backend/strategies/crypto_setups.py` (BTC-native funding/session/liquidation engine, 3 strategies, 5-min loop) → `process_signal_unified` ✅
2. `backend/webhooks/tradingview.py` (TradingView Pine alerts on crypto-tagged tickers) → `process_signal_unified` ✅
3. `backend/scheduler/bias_scheduler.py::run_crypto_scan_scheduled()` ("Crypto Scanner" — equities CTA logic applied to a hardcoded ticker list, 30-min loop) → `log_signal` directly ⚠️ **the actual bypass**

**Scope implication for Phase 4 (F-4):** the brief describes F-4 as "route crypto signals through `process_signal_unified`" as if crypto were monolithic. It isn't — 2 of 3 emission paths are already compliant. F-4's dual-write/cutover work is narrower than scoped: it applies specifically to the `bias_scheduler.py` "Crypto Scanner" path.

### Call sites (file:line)

| File:Line | Function | Write path | Notes |
|---|---|---|---|
| `backend/strategies/crypto_setups.py:478` (import), `:504` (call) | `run_crypto_scan()` | `process_signal_unified(sig, source="crypto_engine")` | Applies `btc_market_structure.get_market_structure_context()` scoring modifier (477–502) before pushing each of 3 strategy signals through the pipeline. |
| `backend/main.py:384` (import), `:385` (call) | `crypto_scan_loop()` (async background task) | invokes `run_crypto_scan()` | Started at app startup (90s warm-up sleep), loops every 300s, 24/7. Schedules path #1. |
| `backend/webhooks/tradingview.py:22` (import), `:155` (call) | `_process_with_market_structure()` | `process_signal_unified(signal_data, source=source, **kwargs)` | Applies BTC market-structure filter only when `asset_class == "CRYPTO"` (line 130). |
| `backend/webhooks/tradingview.py:371,455,539,599,664,856,943` | 7 strategy handlers in `receive_tradingview_alert` fan-out | all call `asyncio.ensure_future(_process_with_market_structure(...))` | `is_crypto_ticker()` (116–125) classifies BTCUSD/ETHUSD/etc. (incl. `.P`/`PERP` suffixes) before this fires. |
| `backend/scheduler/bias_scheduler.py:3486` (import), `:3585` (call) | `run_crypto_scan_scheduled()` | `log_signal(trade_signal)` directly, then `update_signal_with_score(...)` at `:3586` | **The bypass.** Uses `scanners.cta_scanner.analyze_ticker_cta` (equities CTA logic) against `CRYPTO_TICKERS` (3467–3471, 15 tickers), scored via a standalone `scoring.trade_ideas_scorer.calculate_signal_score()` — not the bias-engine `apply_scoring()` the pipeline uses. |
| `backend/scheduler/bias_scheduler.py:3575–3580` | same function, just above the `log_signal` call | comment + tag | In-code admission: *"L1a bypass-leak tag: this crypto path calls log_signal directly, skipping the chokepoint (no scoring/feed-tier/L0/L1 gate)."* Sets `trade_signal["triggering_factors"]["bypass_source"] = "bias_scheduler_crypto"`. |
| `backend/scheduler/bias_scheduler.py:2953→3017` (`_scanner_loop`) | production trigger | calls `run_crypto_scan_scheduled()` | 24/7, every 30 min. Started via `asyncio.create_task(_scanner_loop())` at `:2798` — the normal/production branch (APScheduler import succeeds). |
| `backend/scheduler/bias_scheduler.py:3029→3180` (`_fallback_scheduler`) | fallback trigger | also calls `run_crypto_scan_scheduled()` | Only reachable if `import apscheduler` raises (2813–2816) — not the live path in normal deploys, but an equally-unbypassed duplicate if it ever runs. |
| `backend/scheduler/bias_scheduler.py:3620–3622` | `trigger_crypto_scan_now()` | also calls `run_crypto_scan_scheduled()` | Defined but **never called anywhere else in the repo** — dead/unwired manual trigger. |
| `backend/analytics/api.py:61` (import), `:2072–2087` | `log_signal_endpoint()` (`POST /log-signal`) | `log_signal(data, ...)` directly | Generic manual/external signal-insert API, not crypto-specific, but a live bypass-capable call site for any `asset_class`. Self-tags `bypass_source = "analytics_log_signal_endpoint"` (2079–2085). |
| `backend/signals/pipeline.py:1151` | `process_signal_unified()` definition | — | See governance delta below. |
| `backend/database/postgres_client.py:1395` | `log_signal()` definition | — | See governance delta below. |
| `backend/signals/pipeline.py:1347` | inside `process_signal_unified`, step 4 | `await log_signal(signal_data)` | **`log_signal` is an internal step of `process_signal_unified`, not an alternative to it** — called only after 9 prior gating/enrichment steps. |
| `backend/scheduler/bias_scheduler.py:3203` | `run_cta_scan_scheduled()` (equities CTA) | imports `log_signal` but never calls it; calls `process_signal_unified` at `:3361` | Vestigial import — evidence the equities CTA path migrated onto the unified pipeline and the crypto counterpart did not. |

Non-crypto `process_signal_unified` call sites (confirmed compliant, repo-wide grep): `backend/webhooks/whale.py:254`, `footprint.py:220`, `backend/scanners/holy_grail_scanner.py:353`, `scout_sniper_scanner.py:391`, `sell_the_rip_scanner.py:655`, `wh_reversal.py:243`, `wh_accumulation.py:170`, `backend/strategies/wrr_buy_model.py:199`, `backend/api/flow_ingestion.py:279`, `bias_scheduler.py:3361`. `scripts/` tree has **zero** call sites for either function.

`backend/strategies/btc_market_structure.py` never calls either function directly — it's a pure scoring/enrichment library (`get_market_structure_context`, def at line 340) invoked by both crypto_setups.py:477 and tradingview.py:132.

### Scanner registry / invocation map

No single "crypto scanner registry" file exists — three independent trigger mechanisms feed two different code paths:
- `backend/main.py:378–390` (`crypto_scan_loop`) — 5-min cadence → `process_signal_unified` ✅
- `backend/scheduler/bias_scheduler.py:2953` (`_scanner_loop`) — 30-min cadence → `log_signal` directly ⚠️
- `backend/webhooks/tradingview.py:217` (`receive_tradingview_alert`) — event-driven HTTP → `process_signal_unified` ✅

### Governance delta: what `log_signal` skips

`process_signal_unified` (`backend/signals/pipeline.py:1151–1499`) is a ~24-step chokepoint; `log_signal` (`backend/database/postgres_client.py:1395–1487`) is one internal step of it — a raw `INSERT INTO signals ... ON CONFLICT (signal_id) DO NOTHING` plus timestamp/calendar normalization. Direct callers of `log_signal` skip everything below:

| Governance component | Pipeline location | Skipped by direct `log_signal`? |
|---|---|---|
| L0.1a signal_type suppression gate | `pipeline.py:1194–1198`, tagged 1314–1327 | Yes — `config/l0_routing.py:29–34` docstring explicitly names this exemption: *"the crypto scanner (bias_scheduler.py crypto path) writes via log_signal directly and is NOT covered — by design."* |
| L1a auction+flow quality gate | `pipeline.py:1333–1343` | Yes |
| Full bias-engine scoring (`apply_scoring()`) | `pipeline.py:1208–1209` | Yes — substituted with a simpler standalone scorer |
| Feed tier v1/v2 classification + hard-floor reject (score<30 not persisted) | `pipeline.py:1211–1288` | Yes — no floor; nothing blocks a low-quality crypto signal from persisting |
| Countertrend rejection bail-out | `pipeline.py:1290–1296` | Yes |
| Lightning-card dedup/merge | `pipeline.py:1298–1312` | Yes |
| Dedup / cooldown (DB-backed) | equities caller does `has_recent_active_signal()` at `bias_scheduler.py:3259` | Yes — crypto path's import at `:3486` omits this check; fresh timestamp baked into every `signal_id` (`:3520`) means `ON CONFLICT` never dedupes. (Note: `crypto_setups.py` path has its own separate 30-min in-memory `_can_fire`/`_mark_fired` cooldown, lines 58–70 — process-local, lost on restart, weaker than a DB cooldown but present.) |
| Catalyst↔signal confluence flagging | `pipeline.py:1357–1361` | Yes |
| `write_signal_outcome` (PENDING accuracy tracking) | `pipeline.py:1352–1355` | Yes — **this is the direct cause of the 0.2 finding below** |
| Generic enrichment | `pipeline.py:1393–1401` | Yes |
| score_v2 + ceiling caps | `pipeline.py:1403–1427` | Yes |
| Conflicting-signal short-circuit | `pipeline.py:1446–1459` | Yes — a LONG and SHORT crypto signal for the same ticker can both persist/broadcast |
| Redis cache + WS broadcast | `pipeline.py:1461–1471` | Re-implemented manually right after `log_signal` (`bias_scheduler.py:3594,3597`) — happens, just outside the chokepoint with none of the above gates having run first |
| Position-linked signal tagging | `pipeline.py:1473–1477` | Yes |
| Committee-review flagging | `pipeline.py:1479–1483` | Yes — crypto bypass signals can never trigger committee review regardless of score |

**Net assessment:** `log_signal` is a bare persistence primitive, not a parallel lightweight pipeline. The gap is already documented in three places in the codebase itself (`l0_routing.py:29–34`, `bias_scheduler.py:3575–3580`, `l1_gate.py:5–7`) — Phase 0 confirms scope and effect, it doesn't discover a hidden defect.

---

## 0.2 — Schema check: crypto asset-class support in outcome tracking

### `signals` table

`asset_class` column exists: `VARCHAR NOT NULL`, **no column default** — every writer must supply it explicitly.

| asset_class | count |
|---|---|
| EQUITY | 13,804 |
| CRYPTO | 963 |

Crypto breakdown by strategy/ticker convention:

| strategy | ticker format | rows | outcome resolved | outcome NULL |
|---|---|---|---|---|
| `Crypto Scanner` | Yahoo-style (`ETH-USD`, `BTC-USD`, `DOGE-USD`, `NEAR-USD`, 12 tickers) | 830 | 200 | 630 |
| `Session_Sweep` | exchange-native (`BTCUSDT` only) | 133 | 1 | 132 |

`outcome_source` split on the 201 resolved crypto rows: `BAR_WALK` 118, `COUNTERFACTUAL` 83 (written by an unrelated path, `backend/analytics/api.py:2519` — out of scope for this brief, noted only for completeness).

### `signal_outcomes` table

18 columns, **no `asset_class` column and no FK to `signals`** — the only join key is the free-text `signal_id` string.

Joining crypto `signals` rows to `signal_outcomes` on `signal_id`:
- `Session_Sweep` (133 rows) — **all** have a matching row (`symbol='BTCUSDT'`, outcome `PENDING`/`EXPIRED`).
- `Crypto Scanner` (830 rows) — **zero** matches (`symbol IS NULL`). Root cause: this strategy writes via the `log_signal` bypass (0.1), which never reaches `write_signal_outcome()`.

### `outcome_resolver.py` behavior on non-equity symbols

Actual path: `backend/jobs/outcome_resolver.py` (the standard `backend/outcome_resolver.py` path referenced in the brief does not exist — corrected here for Phase 2 planning).

- Never touches `signal_outcomes` or `asset_class` — reads exclusively from `signals` (query at 148–159), writes back to `signals.outcome*` (190–197). Zero hits for `asset_class`/`signal_outcomes` in this file.
- Hands the raw `ticker` string to `yfinance` with **zero format validation**:
  ```python
  # outcome_resolver.py:59-66
  bars = yf.download(ticker, start=signal_ts, interval=interval,
                      progress=False, auto_adjust=False, prepost=False)
  ```
- Whether crypto resolves at all is an **accident of ticker-string compatibility with Yahoo Finance**, not a designed feature:
  - `Crypto Scanner`'s Yahoo-format tickers (`BTC-USD`) happen to work → 118 rows resolved via `BAR_WALK`.
  - `Session_Sweep`'s Binance-native format (`BTCUSDT`) is not recognized by yfinance → `yf.download` returns an empty frame → hits the silent-return path at `outcome_resolver.py:71-72` (`if bars is None or bars.empty: return None, None, None`). **This is indistinguishable from "signal hasn't touched target/stop yet"** (line 129 uses the identical return value for that case) — no error is logged for an empty-but-successful frame; only `yf.download` *raising* logs a warning (67–69).
  - Empirical confirmation: 132/133 `Session_Sweep` signals sit permanently `outcome IS NULL`.

### Does the `log_signal` bypass populate `signal_outcomes`? No.

`write_signal_outcome()` is called exactly once in the whole pipeline flow, immediately after `log_signal` inside `process_signal_unified` (`pipeline.py:1345-1355`). The `bias_scheduler.py` crypto path calls `log_signal()` directly and never reaches this line — confirmed both by code trace and empirically (830/830 `Crypto Scanner` rows have no `signal_outcomes` match; every `Session_Sweep` row, which must be reaching `write_signal_outcome` through some other path, does).

### Implications for Phase 2 (F-2)

1. Any crypto outcome-tracking design must fix the ticker-format problem **before** it reaches `outcome_resolver.py` — a canonical crypto ticker convention (the brief already specifies `BTC-USD` style) needs to be enforced upstream, not assumed.
2. `outcome_resolver.py` needs to fail loud (not silently return `(None, None, None)`) when a symbol format is unresolvable, so "no touch yet" and "will never resolve" stop being indistinguishable — this is a real bug class, not crypto-specific, but crypto is what exposed it.
3. Fixing the `bias_scheduler.py` Crypto Scanner bypass (F-4) is a **prerequisite** for `Crypto Scanner` signals ever getting outcome rows at all — F-2 and F-4 are more coupled than the brief's phase ordering implies.

---

## 0.3 — Crypto vendor client inventory

All four dedicated vendor clients live in `backend/bias_filters/` (**not** `backend/integrations/` as the brief assumed — that directory only holds `binance_futures.py`, a fifth, separate Binance client). All four are async (`httpx.AsyncClient`) with an identical in-module dict-cache pattern (no shared client infrastructure).

| Vendor | File | Auth mode | Base URL(s) | Timeout | Retry | Staleness handling | Callers |
|---|---|---|---|---|---|---|---|
| Coinalyze | `backend/bias_filters/coinalyze_client.py` | API key — `COINALYZE_API_KEY` (+ aliases `COINALYZE_KEY`, `COINALYZE_TOKEN`, line 34) | `api.coinalyze.net/v1` primary; `www.okx.com/api/v5` OKX fallback | 30.0s (line 84); OKX leg 15.0s (107) | None — HTTP 429 does one `sleep(60)` then gives up (87–90); other failures log + return `None` | Write-time timestamp only (e.g. line 205) — not an upstream-data-age check. 5-min cache TTL (`CACHE_TTL_SECONDS=300`, line 29) is the only freshness gate | `backend/bias_filters/btc_bottom_signals.py:47-49` → `backend/api/btc_signals.py:24` |
| Deribit | `backend/bias_filters/deribit_client.py` | None — public endpoints (docstring line 6) | `www.deribit.com/api/v2` | 30.0s (line 47) | None | Same write-time-timestamp pattern; 5-min TTL (line 22) | `btc_bottom_signals.py:56` → `btc_signals.py:24` |
| Binance | `backend/bias_filters/binance_client.py` | None — public market data. `CRYPTO_BINANCE_PERP_BASE`/`CRYPTO_BINANCE_PERP_HTTP_PROXY` env vars configure endpoint/proxy routing, not auth | `data-api.binance.vision/api/v3` (spot, "geo-friendly mirror"); `fapi.binance.com` (futures, overridable); `okx.com/api/v5/market` (fallback) | 10.0s (line 50) | None — HTTP 451 (geo-block) triggers silent fallback to OKX rather than retry (58–63) | Per-result timestamp; TTLs differ by type (orderbook 60s, basis 300s, lines 26–27) | `btc_bottom_signals.py:70` → `btc_signals.py:24` |
| DeFiLlama | `backend/bias_filters/defillama_client.py` | None — public API | `yields.llama.fi` | 30.0s (line 52) | None | Write-time timestamp; 15-min TTL (line 27, "yields don't change that fast") | `btc_bottom_signals.py:63` → `btc_signals.py:24` |

**No hardcoded credential values found in any of the four files** — all reads go through `os.getenv`.

### Notable per-vendor findings

- **Coinalyze:** the only auth-gated client of the four. Key-lookup strips surrounding quotes (line 37, "suggesting past incidents with quoted env values") and sends the key both as a header and a query-string fallback ("when proxies strip custom headers," line 81). All four public functions have full parallel OKX-fallback logic hardcoded in-file.
- **Deribit:** cleanest — single provider, no fallback, no auth. `get_25_delta_skew()` hand-parses Deribit instrument names (`BTC-28JAN26-100000-P`) with a bare `except (ValueError, KeyError, IndexError): continue` (163–164) that silently drops malformed instruments with no count/log.
- **Binance:** the module is explicitly built around Binance Futures being geo-blocked on Railway (comment line 3; 451-handling 58–63) — **the geo-block risk the brief flags as "unverified" already has defensive code in place**; Phase 1's job is to verify it actually triggers from Railway's region, not to discover whether the code handles it. **Vendor sprawl beyond brief scope:** four independent Binance implementations exist in the repo with no shared code — `bias_filters/binance_client.py` (this one), `integrations/binance_futures.py` (separate cache/geo-handling, used by crypto strategies), `api/crypto_market.py` (own multi-exchange waterfall incl. Bybit), `analytics/price_collector.py` (`_fetch_binance_klines`, historical bar backfill, `raise_for_status()` with no surrounding try/except — one bad response aborts the whole backfill run). **Any Phase 1 vendor-sanction work needs to scope explicitly which of these four call sites it's touching** — this is materially more vendor sprawl than "one Binance client."
- **DeFiLlama:** simplest, single endpoint, no fallback provider if down.

### yfinance crypto fallback — confirmed live, not just documented

`PROJECT_RULES.md:135` documents yfinance as crypto fallback. This is **actively executing code in at least three places**, not dead documentation:

1. `backend/bias_filters/macro_confluence.py:72` — `yf.Ticker("BTC-USD")` for the bias engine's macro confluence gate. **Not a fallback here — the only source**, called unconditionally.
2. `scripts/committee_context.py:633-654` — normalizes bare crypto symbols to `-USD` convention, calls `yf.download` for committee technical enrichment (EMA/RSI/MACD/ATR). Notably, `docs/codex-briefs/brief-committee-data-access-fix.md:136-146` **already proposed replacing this exact path** because "yfinance is unreliable — prices can be $20K+ stale" for crypto — but the proposed Polygon-based fix was **never implemented** (confirmed via grep: no `get_live_price`/`polygon_client`/`get_crypto_price` symbols present). This directly conflicts with `PROJECT_RULES.md`'s Polygon-is-dead-code ruling — any S-1+ work should not resurrect that proposed fix, but should be aware the underlying staleness warning is still live and unaddressed.
3. `backend/scheduler/bias_scheduler.py:3467-3471` — `CRYPTO_TICKERS` list feeds `scanners/cta_scanner.py`, which itself calls `yf.Ticker`/`yf.download` internally (lines 57–67, 1837) — a third, one-level-removed yfinance-crypto entry point.

### File paths referenced
`backend/bias_filters/{coinalyze,deribit,binance,defillama}_client.py`, `backend/bias_filters/btc_bottom_signals.py`, `backend/api/btc_signals.py`, `backend/integrations/binance_futures.py`, `backend/strategies/{crypto_setups,btc_market_structure}.py`, `backend/api/crypto_market.py`, `backend/analytics/price_collector.py`, `backend/bias_filters/macro_confluence.py`, `scripts/committee_context.py`, `backend/scheduler/bias_scheduler.py`, `docs/codex-briefs/brief-committee-data-access-fix.md`.

---

## 0.4 — Webhook HMAC coverage: crypto vs equity

### Bottom line: YES — identical check, same route, applied uniformly before any asset-class branching

The crypto alert path (`BTCUSDT.P` via Holy Grail / Exhaustion PineScript) hits the exact same endpoint and the exact same validation call as equities. **This P0-adjacent concern in the committee brief is not a live defect** — verified clean.

### Details

- Single route: `@router.post("/tradingview")` — `backend/webhooks/tradingview.py:217`, mounted at `backend/main.py:1338` → public path `/webhook/tradingview`. No separate crypto route exists anywhere in `backend/webhooks/` (confirmed via full scan of `@router.post/get` decorators in the package).
- The check is **not** a request-signature HMAC over the raw body — it's a constant-time shared-secret string compare (`hmac.compare_digest`) against a `secret` field in the JSON body (`backend/utils/webhook_auth.py:106`, called from `tradingview.py:251-256`).
- This call happens once, immediately after payload parsing (`tradingview.py:243`) and **before** any strategy dispatch (`strategy_lower` branching starts at line 281).
- Two early-return branches exist before the secret check (lines 230–241, for `signal=="FOOTPRINT"` and `source/strategy/alert_type` containing "pythia") — both keyed on payload content type, not ticker/asset-class, and neither matches Holy Grail/Exhaustion payloads regardless of symbol.
- `is_crypto_ticker(alert.ticker)` (116–125) is consulted only **downstream** of the secret check, for `asset_class` tagging and cooldown-window selection — it plays no role in whether/how the secret check runs.
- Enforcement flag: `WEBHOOK_TV_ENFORCE` (`tradingview.py:43-44`). Unset/not `1`/`true`/`yes` → OBSERVE mode (logs match/mismatch, never rejects). Set to enforce → missing configured secret = 503, mismatched/missing supplied secret = 401. Read at request time (no redeploy to flip), applied identically to crypto and equity traffic. Runtime value not read (that's Railway env state, out of scope for a code investigation).
- `WEBHOOK_HERMES_ENFORCE` (`backend/webhooks/hermes.py:72`) is a **distinct** flag gating a **different** endpoint (`/api/webhook/hermes`, catalyst/analysis events) — not part of the TradingView crypto/equity path. Do not conflate the two in Phase 1+ work.

---

## Cross-cutting implications for Phase 1+

1. **F-4 scope correction:** only the `bias_scheduler.py` "Crypto Scanner" (30-min loop, `run_crypto_scan_scheduled`) needs dual-write/cutover. `crypto_setups.py`'s 3 strategies and the TradingView crypto webhook path are already governance-compliant. This shrinks F-4's blast radius considerably.
2. **F-1/F-2 sequencing dependency:** the Crypto Scanner bypass is *why* 830/963 crypto signals have no `signal_outcomes` row. Fixing F-4 (routing) and F-2 (resolver/ticker format) together — rather than strictly F-2 before F-4 per the brief's phase order — may be more efficient; flagging for Nick/ATHENA rather than unilaterally resequencing.
3. **Binance vendor sprawl is bigger than scoped:** 4 independent Binance client implementations exist, not 1. Phase 1's Symbol Capability Matrix and vendor-sanction work needs to explicitly name which of the four it covers (this brief's F-1 focuses on `bias_filters/binance_client.py`, used by `btc_bottom_signals.py`) and flag the other three as a known-sprawl item for a future cleanup (candidate for `docs/build-backlog.md` v4, Phase 5).
4. **Geo-block handling already exists in code** — Binance client already has 451-detection + OKX fallback. Phase 1's live-test is about confirming Railway's actual region behavior, not building new handling.
5. **Ticker-format canonicalization is a hard Phase 2 prerequisite**, not a nice-to-have: `outcome_resolver.py` silently, permanently stalls on any non-Yahoo-format crypto ticker (proven by `Session_Sweep`'s 132/133 permanently-NULL outcomes). The brief's `BTC-USD`-style canonical convention (F-3) must land before or alongside F-2, since F-2 is the resolver's crypto-awareness fix.
6. **HMAC/webhook concern is closed** — no code change needed for 0.4; the brief's webhook-check item is satisfied by existing code.
7. **Stale-crypto-price risk is real and currently unaddressed:** `macro_confluence.py`'s bias-engine gate uses yfinance BTC-USD unconditionally, with a documented (but never-fixed) "$20K+ stale" risk from a prior brief. Out of S-1's direct scope (that file isn't a Stater Swap module), but worth a backlog flag since F-3's new `hub_get_crypto_quote` may end up as the natural fix once it ships.
