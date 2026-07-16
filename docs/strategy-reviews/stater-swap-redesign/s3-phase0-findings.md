# Stater Swap v2 — S-3 Phase 0 Findings (R-2: Keep-List Upgrades)

**Date:** 2026-07-16 | **Brief:** `docs/codex-briefs/2026-07-16-stater-swap-s3-keep-list-upgrades-brief.md`
**Scope:** Read-only reconnaissance per §1 (1.1–1.10). No code changes.

## ⚠️ Blocking finding — STOP before Phase 1 per the brief's own rule (§1 preamble)

**§4.4's assumption that FROTH signals are "per-symbol per the matrix" is false at the code level.** All four froth-side vendor wrapper functions are **hardcoded to a single symbol (BTC)** with no symbol parameter at all — not "works for BTC today, extensible later," but structurally incapable of returning another symbol's data without a code change:

- `get_quarterly_basis()` (`backend/bias_filters/binance_client.py:222`) — `_SYMBOL = "BTC"` (line 21), literal `"BTCUSDT"` (line 250), single global cache key `"quarterly_basis"` (line 243).
- `get_25_delta_skew()` (`backend/bias_filters/deribit_client.py:74`) — hardcoded `currency="BTC"` in the request body (line 100), cache key `"skew_25d"` (line 93).
- `get_funding_rate()` (`backend/bias_filters/coinalyze_client.py:150`) — `_SYMBOL="BTC"` (line 22, with an explicit in-code comment: "hardcoded to BTC today... multi-symbol parametrization is an R-2/R-3 prerequisite"), `BTC_PERP_SYMBOLS=["BTCUSDT_PERP.A"]` (lines 29-31).
- `get_open_interest()` (`backend/bias_filters/coinalyze_client.py:240`) — same hardcoding pattern.

**Why this matters:** `symbol-capability-matrix.md`'s per-symbol "LIVE" cells for these four data types (e.g. ETH funding via `ETHUSD_PERP.A`, ETH skew via Deribit) were verified during S-1 by **probing the raw vendor endpoints directly** — never by calling these wrapper functions, which cannot express a symbol at all today. Calling `get_funding_rate()` "for ETH" would silently return **BTC's** funding rate mislabeled as ETH's — a fake-healthy trap, the exact failure class this whole program has been hunting (P0 wrong-asset quote, UW `data:null`, the two S-1 committee-smoke-pass findings). §4.4's "honest N/A elsewhere" plan implicitly assumes a per-symbol call is at least *attemptable* (returning N/A on failure); it isn't — there's no symbol argument to attempt with.

**This also affects the CAPITULATION column, not just FROTH.** `btc_bottom_signals.py`'s existing 9 signals (§1.1) are the SAME orchestration layer calling these SAME BTC-hardcoded client functions (`_fetch_funding_signal` → `get_funding_rate()`, `_fetch_basis_signal` → `get_quarterly_basis()`, `_fetch_skew_signal` → `get_25_delta_skew()`, `_fetch_oi_signal` → `get_open_interest()`). The module's very name (`btc_bottom_signals.py`) reflects this: it was never built to be per-symbol. §4.3 says these 9 computations ship "unchanged" — correct, but "unchanged" means "still BTC-only," which collides with **Committee Addendum A-5's explicit requirement**: *"full two-column dial for BTC/ETH."* ETH cannot get a real, non-fabricated CAPITULATION or FROTH reading from any of these four data types without a client-layer parametrization change.

**What's unaffected:** liquidations, stablecoin APRs, spot orderbook skew, VIX spike (the other 5 of 9 capitulation signals) — need re-checking individually for symbol-generality, not yet done (see follow-up note below), but at minimum the 4 explicitly named in §4.4 (basis/skew/funding/OI) are confirmed BTC-locked.

**Options, not decided here:**
1. **Parametrize the four client functions** to accept a symbol arg, routing per the matrix's already-verified per-symbol vendor endpoints (e.g. `ETHUSD_PERP.A` for funding, OKX-fallback per-symbol for basis). Real code change to `coinalyze_client.py`/`deribit_client.py`/`binance_client.py` — bigger than "reuse as-is," but not a new vendor (doesn't violate the zero-new-vendor hard rule) and is the only way to satisfy Addendum A-5 for real.
2. **Ship BTC-only for these four data types**, ETH (and everyone else) explicitly `N/A` with a reason like `SINGLE_SYMBOL_CLIENT_NOT_YET_PARAMETRIZED` — honest, zero new code risk, but does not meet Addendum A-5's "full two-column for BTC/ETH" as written; would need explicit sign-off that this requirement is deferred.
3. **Hybrid** — parametrize only funding + skew (matrix already shows both LIVE for ETH, lowest-risk extensions) for real BTC/ETH coverage on those two cells, leave basis/OI BTC-only-with-honest-N/A for ETH (matrix shows these as OKX-fallback/more experimental).

Per the brief's own instruction ("If any finding contradicts this brief's assumptions, STOP and flag to Fable before Phase 1"), **no Phase 1+ code has been written.** Everything below is Phase 0 reconnaissance only.

---

## 1.1 — Bottom Signals inventory (`btc_bottom_signals.py` + `btc_signals.py`)

All 9 signal computations, orchestrated together via `update_all_signals()` (`btc_bottom_signals.py:578-642`, `asyncio.gather`):

| # | Signal | Fetch fn | Client call | Measures |
|---|---|---|---|---|
| 1 | `skew_25delta` | `_fetch_skew_signal` (431-464) | `deribit_client.get_25_delta_skew()` (437) | Options fear gauge |
| 2 | `quarterly_basis` | `_fetch_basis_signal` (538-571) | `binance_client.get_quarterly_basis()` (544) | Contango/backwardation |
| 3 | `perp_funding` | `_fetch_funding_signal` (290-321) | `coinalyze_client.get_funding_rate()` (296) | Long/short crowding |
| 4 | `stablecoin_aprs` | `_fetch_stablecoin_signal` (467-500) | `defillama_client.get_stablecoin_aprs()` (473) | Leverage-demand proxy |
| 5 | `term_structure` | `_fetch_term_structure_signal` (396-428) | `coinalyze_client.get_term_structure()` (402) | Hedging urgency |
| 6 | `open_interest` | `_fetch_oi_signal` (324-357) | `coinalyze_client.get_open_interest()` (330) | Accumulation/trap divergence |
| 7 | `liquidations` | `_fetch_liquidations_signal` (360-393) | `coinalyze_client.get_liquidations()` (366) | Long vs short liq composition |
| 8 | `spot_orderbook` | `_fetch_orderbook_signal` (503-535) | `binance_client.get_spot_orderbook_skew()` (509) | Orderbook depth imbalance |
| 9 | `vix_spike` | `_fetch_vix_signal` (258-287) | `yf.Ticker("^VIX")` (264-265) | Macro capitulation |

**Cadence + trigger:** `bias_scheduler.py:2171-2184`'s `refresh_btc_bottom_signals()` calls `update_all_signals()`, registered `bias_scheduler.py:2657-2662` as an APScheduler interval job **every 5 minutes, 24/7** (existing, pre-S-3). Also triggerable via `POST /btc/bottom-signals/refresh` and the clear-override route. **The read route (`GET /btc/bottom-signals`) is cache-only** — no live fetch on read, serves in-memory state lazy-loaded from Redis.

**Staleness:** each signal stamps `updated_at` at fetch time; Redis TTL is a flat 24h (`REDIS_TTL_SECONDS=86400`) with no age-threshold check anywhere — `last_update` at the payload's top level is stamped at *request* time, not last-fetch time, so it doesn't reflect true data age. **No existing staleness contract to reuse — §4.2's contract is genuinely new work**, not a wrap of something already there.

**Current response shape** (`GET /btc/bottom-signals`): `{signals: {<id>: {name, description, status, value, threshold, source, auto, updated_at, notes, [manual_override]}, ...9}, raw_data: {...}, confluence: {firing, total, pct, verdict, verdict_level}, last_update, api_status, api_keys, api_errors}`.

**Follow-up not yet done:** confirm whether liquidations/stablecoin-APRs/spot-orderbook (the 3 of 9 not named in §4.4) are also BTC-hardcoded at the client level — likely yes given they're the same module, not independently re-verified this pass.

## 1.2 — Froth-side inputs (see blocking finding above for the core result)

**No new-polling risk regardless of the hardcoding issue:** all four functions are already invoked every 5 minutes by the existing `btc_bottom_signals.py` cadence. Reusing them (even BTC-only) hits the same 300s module-level cache — zero incremental vendor call volume either way.

## 1.3 — CVD gate + market structure internals (`btc_market_structure.py`)

**CVD real data path:** `_fetch_cvd()` (line 179) does not call vendor clients directly — it hits the hub's own `GET /api/crypto/market` internally (`crypto_market.py`), which tries Binance perp trades first (`fapi.binance.com`), 451-geo-blocks on Railway (expected, silently handled), and falls back to OKX trades. **OKX is the real live CVD data path today**, consistent with every other S-1-era Binance-geo-block finding. 60s local TTL cache.

**POC/VAH/VAL:** `compute_volume_profile()` (lines 43-144) — 50-bin volume-at-price histogram from 1H klines, POC = max-volume bin, Value Area expands from POC alternating toward the larger adjacent bin until ≥70% of volume is captured.

**Score coupling:** `total_modifier = vp_score + cvd_score + ob_score` (line 401): volume-profile −10..+10, CVD −15..+10, orderbook −15..+10 → actual summed range **−40..+30** (the module's own docstring claims "−45 to +35" — a pre-existing doc/code mismatch, not introduced by or fixed in this pass). **This brief must not alter any of this — confirmed, only a staleness wrap applies.**

## 1.4 — Session-extreme availability

**YES, derivable with zero new plumbing.** `crypto_sessions.py`'s `get_partition()` already classifies any timestamp into ASIA/LONDON/NY; it's pure-function, no I/O, so it has no high/low tracking itself. But `crypto_bars.py::fetch_crypto_ohlc(base, use_daily=False)` already pulls **15-minute** bars per-symbol through the sanctioned F-2 vendor routing (live-verified across all three vendors in S-1) — today only called with `use_daily=True` by the regime job, but the 15m path already works. `crypto_setups.py:190-210`'s `_get_session_range()` proves the exact bar-filter-and-reduce pattern already exists in this repo (legacy, hardcoded hours, wrong vendor path — but the aggregation logic is a solved problem). A new session-extreme function needs only to: fetch 15m bars via the sanctioned routing, tag each bar's partition via `get_partition()`, filter to the current partition's most recent occurrence, min/max the highs/lows.

## 1.5 — Ticker ingress re-verification + HMAC ordering

All three ingress points confirmed unchanged from the S-2-era investigation:
- `crypto_setups.py::_build_signal()` sets `"ticker": ticker` at **line 97**; still Binance-native (`symbol: str = "BTCUSDT"` default).
- `bias_scheduler.py::run_crypto_scan_scheduled()` sets `"ticker"` at **line 3563**; still Yahoo-style hyphenated (`CRYPTO_TICKERS`, lines 3493-3497).
- `tradingview.py::receive_tradingview_alert()` — secret verification at **lines 255-260**; `alert.ticker` first used at **line 263** (after). All seven crypto-capable handler functions (Scout, Holy_Grail, Exhaustion, Sniper, Phalanx, Artemis, generic) set `"ticker"` only inside the post-verification `try` block (lines 282-297+). **Confirmed: ticker-writing cannot occur before verification in any path — safe insertion point for normalization.**
- `normalize_crypto_ticker(raw_ticker: Optional[str]) -> Optional[str]` (`crypto_bars.py:38`) — unchanged signature, returns `None` on unresolvable input, never guesses.

## 1.6 — `CRYPTO_TICKERS` blast radius + FA-1 pre-flight

**Correction to the brief's assumption: there is no single `CRYPTO_TICKERS` list — there are four, independently scoped:**

| Location | Format | Purpose | Contains MATIC/UNI/APT? |
|---|---|---|---|
| `bias_scheduler.py:3493` (list) | `'BTC-USD'` style | Crypto Scanner's tracked-symbol universe — **the one the S-1 dormancy finding and this brief's §3.4 actually mean** | MATIC-USD, UNI-USD, APT-USD — all three, this is the one to prune |
| `tradingview.py:56` (set) | base symbol, no suffix | Asset-class classification for any incoming TV alert (`is_crypto_ticker()`) | MATIC, UNI present; APT absent |
| `analytics/price_collector.py:27` (set) | base symbol | Price-collection scope | None of the three present |
| `analytics/calendar_context.py:27` (`_LIKELY_CRYPTO_TICKERS`) | base symbol | Earnings-calendar exclusion heuristic | None of the three present |

**Only `bias_scheduler.py`'s list is in scope for §3.4's prune.** The `tradingview.py` set serves a different purpose (any future TV alert on MATIC/UNI should still classify as crypto, even though the Crypto Scanner no longer scans them) and should NOT be touched — pruning it would be a scope-incorrect side effect, not requested by the brief.

**FA-1 pre-flight** (live query, 2026-07-16): zero rows in `unified_positions` and zero rows in `signals` (any status) referencing `MATIC-USD`/`UNI-USD`/`APT-USD` — confirmed via direct SQL. **The prune is safe per §3.4's own rule** (zero open positions, zero unresolved signals → proceed with removal from `bias_scheduler.py`'s list only).

## 1.7 — Known-red baseline

`cd backend && python -m pytest tests/ -q`, 2026-07-16: **18 failed, 297 passed, 1 skipped, 203 errored** — byte-for-byte identical FAILED test names to the S-2-recorded baseline (same 2 scanner + 2 countertrend + 14 `test_uw_api_mapping.py`, same 203 pre-existing environment errors). **Unchanged, as expected.**

## 1.8 — Bypass-retirement tracker

`scripts/crypto_dual_write_diff_report.py`, 2026-07-16: **3 comparison rows, unchanged from S-2's completion report** — all three are one-off tagged test signals from S-1/S-2 verification passes, none real, none counting toward the n≥30 retirement bar. No `bias_scheduler.py` touch has occurred yet in S-3.

## 1.9 — Hub MCP registration pattern

Confirmed `SCHEMA_VERSION = "v2.0"` (`hub_mcp/__init__.py:9`). New tools require: (1) name added to `decorators.py`'s `REGISTERED_TOOL_NAMES` whitelist (assert-checked at decoration time), (2) a `tools/<noun>.py` file following `crypto_quote.py`'s exact shape (`DESCRIPTION` constant, `@mcp_tool(name=..., description=DESCRIPTION)`, response via `make_response()` from `envelope.py` — never a raw dict), (3) a side-effect import line in `tools/__init__.py`.

**Equity parity reference:** `hub_get_market_profile` (`tools/market_profile.py:34`) — envelope statuses `ok` (current-session levels) / `stale` (prior-session levels + `staleness_seconds`) / `unavailable` (`data=None`) / exception → `error` string.

**Asset-class guard correction:** the bare-ticker disambiguation guard lives in `hub_get_quote` (`tools/quote.py:100-147`), **not** in `hub_get_crypto_quote` — the crypto tool has no guard; it always treats its input as crypto (that's the whole point of it being a dedicated crypto tool). `hub_get_crypto_market_profile` should follow `hub_get_crypto_quote`'s pattern (no guard needed) rather than trying to replicate `hub_get_quote`'s disambiguation logic, which exists specifically because that tool is the shared equity/crypto entry point.

## 1.10 — `/api/crypto/state/{symbol}` wiring targets

Three placeholder fields, all via `_field_envelope(None, True, state=None, note=_NOT_YET_BUILT_R1/R2)`: `session` (line 742), `tape_health` (line 743, `_NOT_YET_BUILT_R2`), `regime` (line 744). Real fill sources already exist for two: `session` ← `crypto_sessions.get_session_state()` (same call the `/crypto/clock` route already makes); `regime` ← `crypto_regime_log` + `crypto_gate_loader.get_gate_config()` (same query `/crypto/regime` already makes, including the existing `_shape()` helper). `tape_health` has no source yet — it's this brief's own Phase 3 output (`crypto_tape_health_log`, not yet built). **Purely additive** — the existing real BTC funding/OI/basis fields (lines 705-740) sit in a separate code block, untouched by this wiring.

---

## Summary — proceeding

Items 1.1, 1.6, 1.7, 1.8, 1.9, 1.10 confirm the brief's assumptions cleanly or provide corrected, non-blocking detail. Items 1.2 (and its 1.1 corollary for CAPITULATION) surface a genuine contradiction between §4.3/§4.4's "reuse as-is" framing and Committee Addendum A-5's "full two-column BTC/ETH" requirement. **No Phase 1+ code shipped in this pass** — flagging for a decision on the three options above before continuing.
