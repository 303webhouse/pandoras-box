# Stater Swap v2 — S-1 Phase 3 Findings (F-3: Crypto Data Path on the Hub)

**Date:** 2026-07-14 | **Brief:** `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md`

## What shipped

### F-3.1 — `hub_get_crypto_quote` MCP tool
- `backend/services/read_only/crypto_quote.py` (new): mirrors `services/read_only/quote.py`'s shape. Checks `data is not None` explicitly (not just HTTP status) per the Phase 1 fake-healthy finding; requires hyphenated `{SYM}-USD` format internally; dispatches to UW when `crypto_symbol_matrix`'s `uw_crypto_quote` status is `LIVE` (BTC/ETH/SOL/ZEC), falls back to OKX ticker otherwise (HYPE/FARTCOIN); bounds-checks the returned spot price via `crypto_sanity_bounds.check_price` before trusting it.
- `backend/hub_mcp/tools/crypto_quote.py` (new): the MCP tool wrapper, `make_response()` envelope, registered in `decorators.py`'s `REGISTERED_TOOL_NAMES` and `tools/__init__.py`'s import list.
- Description authored in `docs/specs/hub-mcp-tool-descriptions-2026-05-14.md` (new "Tool 15" section — flagged that this doc was already 5 tools stale before this pass, not backfilled here) and the `backend/hub_mcp/README.md` tool table.

### F-3.2 — Asset-class guard on `hub_get_quote` (the P0 fix)
- Added `asset_class: Optional[str] = None` param. A bare mention of one of the six tracked symbols (BTC, ETH, SOL, HYPE, ZEC, FARTCOIN) with no `asset_class` now returns an explicit disambiguation error instead of silently resolving to the colliding equity/ETF ticker. Explicit `asset_class="EQUITY"` still reaches the real stock/ETF (respects deliberate intent); explicit `asset_class="CRYPTO"`, or an unambiguous hyphenated ticker (`BTC-USD`), routes straight to the same crypto-quote logic `hub_get_crypto_quote` uses — no duplicated implementation.

### F-3.3 — Consolidated `/crypto/state/{symbol}` envelope
- Added to `backend/api/crypto_market.py` (the router that already owns `/crypto`, resolves to `/api/crypto/state/{symbol}` — confirmed the correct home over `board_state.py`, which owns a different prefix).
- Per-field house labeling contract (`as_of`/`data_age_seconds`/`degraded`), reimplemented locally as `_field_envelope()` — matches the repo's existing pattern of no shared helper module (both `board_state.py` and `stable.py` independently reimplement the same 4-field contract; this is now a third, deliberately consistent copy, not a new convention).
- Fields: `session`, `funding`, `open_interest`, `basis`, `tape_health`, `regime` — plus top-level `tier` and `capabilities` (the full matrix entry) so the UI/committee can render per-symbol coverage from one payload, no client-side guessing.
- `funding`/`open_interest`/`basis` are real, live data **for BTC only** (the only symbol the `bias_filters` vendor clients currently support — multi-symbol parametrization is the R-2/R-3 prerequisite Phase 1 already flagged). Every other tracked symbol gets an honest `null` + `degraded=true` with an explicit note, never a silently mislabeled BTC value.
- `session`, `tape_health`, `regime` are honest nulls for every symbol including BTC — none of R-1/R-2 has shipped yet. The envelope ships now so those phases integrate against a stable shape once, per the brief.

### F-3.4 — Redis TTL audit for 24/7 crypto cache keys

Audited every existing crypto-adjacent Redis key in the repo (not just what F-3 touches):

| Key | TTL | Verdict |
|---|---|---|
| `btc:bottom_signals` / `btc:bottom_signals:raw` | 86,400s (24h) | Flat duration, not tied to equity session boundaries — no fix needed. Not touched by F-3. |
| `cache_signal(...)` for crypto trade-idea signals | 14,400s (4h) | Comment already says "longer TTL for crypto since it's 24/7" — already correctly reasoned pre-Stater-Swap. No fix needed. |

**Conclusion: no existing crypto Redis TTL carries an equity-hours assumption.** Both use flat, always-valid durations that behave identically 24/7 — there was nothing to change.

**F-3 introduces no new Redis cache layer.** `hub_get_crypto_quote` and `/crypto/state/{symbol}` both call directly into `bias_filters/{coinalyze,binance}_client.py` (for BTC) and UW/OKX (for quotes), all of which already have their own in-memory TTLs sized for a 24/7 market (Phase 1: 300s data cache, 900s/3600s degrade/dead health thresholds — none tied to market-hours). Adding a second Redis caching layer on top would duplicate that reasoning for no benefit; verified live that repeated calls return fresh, correctly-cached-underneath data (funding/OI/basis calls in the smoke test below completed in ~0.01-0.16s, consistent with hitting the vendor clients' existing in-memory cache, not a cold network call every time).

## Live verification (before commit, on the actual Railway container)

All of the following were run directly against the real, unmodified backend modules (via an overlay of just the new/changed files):

| Call | Result |
|---|---|
| `hub_get_crypto_quote("BTC-USD")` | `status=ok`, spot=$64,481.33, source=UW, live |
| `hub_get_crypto_quote("HYPE")` | `status=ok`, spot=$65.11, **source=OKX** (fallback correctly engaged since UW has no HYPE data) |
| `hub_get_crypto_quote("FARTCOIN")` | `status=ok`, spot=$0.14, source=OKX |
| `hub_get_crypto_quote("NOTASYMBOL")` | `status=unavailable`, explicit "not a recognized crypto symbol" error |
| `hub_get_quote("BTC")` bare | `status=unavailable`, disambiguation error naming both `hub_get_crypto_quote` and `asset_class="EQUITY"` as next steps — **P0 fixed** |
| `hub_get_quote("BTC-USD")` | `status=ok`, spot=$64,481.33, source=UW — unambiguous notation routes automatically |
| `hub_get_quote("BTC", asset_class="EQUITY")` | `status=ok`, spot=$28.54, ticker=BTC — **the real ETF, reachable only on explicit ask, matching the brief's "never the ETF silently" requirement** |
| `hub_get_quote("BTC", asset_class="CRYPTO")` | `status=ok`, spot=$64,481.32, source=UW |
| `hub_get_quote("AAPL")` control | `status=ok`, spot=$314.86, ticker=AAPL — unchanged behavior for non-colliding tickers |
| `GET /api/crypto/state/BTC` | Real funding (0.559%, FIRING), OI ($1.97B, NEUTRAL), basis (-3.09%, NEUTRAL), all `degraded=false`, fresh `as_of`; session/tape_health/regime honest null+degraded |
| `GET /api/crypto/state/HYPE` | Capability flags correctly carried (tier 3, full matrix entry); funding/OI/basis honest null+degraded with explicit "not yet wired" note; session/tape_health/regime null+degraded |
| `GET /api/crypto/state/NOTASYMBOL` | Clean error, no partial/garbage response |

## Not done / explicitly deferred

- `docs/specs/hub-mcp-tool-descriptions-2026-05-14.md` and `hub_mcp/README.md`'s tool table were already 5 tools stale before this pass (`hub_get_quote`, `hub_get_options_chain`, `hub_get_trade_ideas`, `hub_get_market_profile`, `hub_get_chart_indicators`) — flagged in both docs, not backfilled (out of F-3 scope).
- Multi-symbol parametrization of `bias_filters/{coinalyze,deribit,binance,defillama}_client.py` remains an R-2/R-3 prerequisite — `/crypto/state/{symbol}` is built to integrate that work once it lands (fields are already shaped for it), not to pre-empt it.
- Session/tape-health/regime logic (R-1/R-2) — envelope fields exist and are honestly null; no placeholder logic invented.
