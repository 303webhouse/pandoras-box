# Stater Swap v2 — Symbol Capability Matrix (S-1 Phase 1, F-1 / A-1)

**Date:** 2026-07-13 | **Universe:** BTC, ETH, SOL, HYPE, ZEC, FARTCOIN (Nick decision D2, 2026-07-12)
**Machine-readable artifact:** `backend/config/crypto_symbol_matrix.py`
**Method:** Every cell below was live-tested from inside the actual Railway container (`railway ssh` into the running `pandoras-box` service — real network egress from Railway's region, not a local machine or `railway run`, which only injects env vars locally). One benign read per vendor per symbol, plus vendor meta/discovery calls where available. Raw evidence (HTTP status codes, response bodies) is quoted below; no cell is asserted without a verified reason. No credential values are reproduced anywhere in this document.

## Why the four existing vendor clients needed a different testing approach

Phase 0 investigation found `backend/bias_filters/{coinalyze,deribit,binance,defillama}_client.py` are **all hardcoded to BTC only** — none accept a symbol parameter (Coinalyze uses a fixed `BTCUSDT_PERP.A` aggregate symbol, Deribit hardcodes `currency: "BTC"`, Binance hardcodes `symbol: "BTCUSDT"`, DeFiLlama is a market-wide stablecoin-yield gauge with no BTC-specific selector at all). This matrix therefore tests the **vendors' actual APIs directly** (same auth mode, same base URLs, same fallback chains as the existing clients — just parameterized by symbol) to answer "does the vendor have this data," which is a separate question from "does our current code request it." Parametrizing the four client modules for multi-symbol use is **not** done in this brief — it's flagged as an R-2/R-3 prerequisite (see Cross-cutting notes).

## Summary table

| Symbol | Tier | Coinalyze (funding/OI/liq/term) | Deribit (25Δ skew) | Binance Futures (basis) | Binance Spot (orderbook) | UW crypto quote | TV coverage | BAR_WALK source |
|---|---|---|---|---|---|---|---|---|
| BTC | 1 | LIVE | LIVE (838 instr.) | GEO_BLOCKED → OKX LIVE | LIVE | LIVE | LIVE | UW OHLC — LIVE |
| ETH | 1 | LIVE | LIVE (662 instr.) | GEO_BLOCKED → OKX LIVE | LIVE | LIVE | LIVE | UW OHLC — LIVE |
| SOL | 2 | LIVE | **listed, 0 instruments** | GEO_BLOCKED → OKX LIVE | LIVE | LIVE | LIVE | UW OHLC — LIVE |
| HYPE | 3 | LIVE (thin) | UNAVAILABLE | GEO_BLOCKED → OKX LIVE | UNAVAILABLE (400) | **UNAVAILABLE (fake-healthy)** | UNAVAILABLE → fixed | OKX candles — LIVE |
| ZEC | 3 | LIVE | UNAVAILABLE | GEO_BLOCKED → OKX LIVE | LIVE | LIVE (quote only) | UNAVAILABLE → fixed | Binance spot klines (live-verified S-1 Phase 2) — **not UW** |
| FARTCOIN | 3 | LIVE (thin) | UNAVAILABLE | GEO_BLOCKED → OKX LIVE | UNAVAILABLE (400) | **UNAVAILABLE (fake-healthy)** | UNAVAILABLE → fixed | OKX candles — LIVE |

**Binance-fail fallback (all 6 symbols): OKX.** Verified — see below.

## Headline findings (in order of importance)

### 1. Binance Futures IS geo-blocked from Railway — confirmed, not theoretical

```
GET https://fapi.binance.com/fapi/v1/ping  (from inside the Railway container)
→ HTTP 451
→ {"code": 0, "msg": "Service unavailable from a restricted location according to
   'b. Eligibility' in https://www.binance.com/en/terms. ..."}
```

Same 451 for all 6 symbol-specific ticker calls. Per the brief's hard rule, the resolution is **REPLACE, not evade** — no proxy/VPN. Good news: `backend/bias_filters/binance_client.py` **already has this handled** — it silently falls through to OKX on any non-200 (including 451). Verified: OKX SWAP tickers returned real data (HTTP 200) for all 6 symbols. No code change needed for this specific gap; it's a confirmation, not a new build.

### 2. UW's crypto endpoint has a fake-healthy trap — same failure class as the P0 wrong-asset quote

`api_spec.yaml` (present at repo root, UW's own OpenAPI spec) documents crypto endpoints the current `uw_api.py` client never wired up: `/api/crypto/{pair}/state`, `/api/crypto/{pair}/ohlc/{candle_size}`, `/api/crypto/whale-transactions`. Testing them directly (via the internal `_uw_request` helper, so real auth/rate-limit/circuit-breaker behavior applies):

```
GET /api/crypto/BTC-USD/state  → HTTP 200, {"data": {"close_24h": "62058.8", ...}}   ✅ real data
GET /api/crypto/HYPE-USD/state → HTTP 200, {"data": null}                            ⚠️ fake-healthy
GET /api/crypto/FARTCOIN-USD/state → HTTP 200, {"data": null}                        ⚠️ fake-healthy
```

**A naive `if response.ok: covered = True` check would have marked HYPE and FARTCOIN as covered.** The endpoint returns HTTP 200 with a null payload rather than a 404 — this is the exact "confidently wrong" pattern URSA's Phase-1 review flagged for the wrong-asset ETF trap. Any F-3 `hub_get_crypto_quote` implementation **must check `data is not None`, not just HTTP status**, before returning a value. Recorded as a required implementation note for F-3.

Ticker format matters too: the hyphenated form (`BTC-USD`) is required — the no-hyphen form (`BTCUSD`) returned `{"data": null}` for **every** symbol tested, including BTC. Confirms the brief's `BTC-USD`-style canonical convention (F-3) is not just a style preference — it's the only format that actually works against this endpoint.

### 3. UW quote coverage and UW bar-walk (OHLC) coverage are NOT the same thing — ZEC proves it

`/api/crypto/ZEC-USD/state` returns real current-price data (HTTP 200, real OHLCV). But `/api/crypto/ZEC-USD/ohlc/1d` returns `{"data": []}` — an empty candle history, despite the live quote working. This means **ZEC can get a live quote from UW but cannot use UW as its BAR_WALK bars source** — a distinct fact from HYPE/FARTCOIN, which fail on both endpoints identically. This nuance would have been missed by testing only the quote endpoint (which is what a naive coverage check would do). ZEC's recommended bar-walk source is Binance spot klines (ZEC is confirmed listed on Binance spot, unlike HYPE/FARTCOIN). Update (S-2 docs pass, 2026-07-15): the candle-history pull WAS live-verified during S-1 Phase 2 — 5 real 15m candles pulled pre-wiring (`s1-phase2-findings.md`, "Pre-wiring verification") — this line originally deferred that verification and is corrected here rather than left stale. Note: 15m interval was what Phase 2 verified; the 1d interval S-2's regime classifier needs is live-checked in `s2-phase0-findings.md` §0.2.

### 4. Coinalyze already covers all six symbols — Hyperliquid sanction NOT triggered

The brief's conditional (task 1.3): *"if Coinalyze lacks Hyperliquid-native pairs... Hyperliquid public API enters as a sanction candidate."* Discovery call to Coinalyze's `/future-markets` endpoint (4,633 markets) found an aggregated symbol for all six tickers, including `HYPEUSDT_PERP.A` and `FARTCOINUSDT_PERP.A` — and a live funding-rate read against both returned HTTP 200 with real data. Coinalyze's own `/exchanges` endpoint lists "Hyperliquid" (code `H`) as a supported source exchange, consistent with HYPE/FARTCOIN's aggregate data plausibly being Hyperliquid-sourced under the hood (not independently confirmed which exchange feeds a given `.A` aggregate).

**Since Coinalyze already has coverage, the brief's trigger condition for sanctioning Hyperliquid as a 5th vendor was not met — no new vendor added.** Per the brief's instruction to "surface as a one-line confirm for Nick" if this became live: **Nick, no action needed — Hyperliquid was tested (works great, keyless, all 6 symbols in its 232-asset universe) and is recorded as a verified, ready-to-activate backup in case Coinalyze's thin HYPE/FARTCOIN aggregation (only 1 discovered symbol vs. 2-3 for the majors) ever proves unreliable — but it is not sanctioned or wired into any code today.**

### 5. TradingView ticker classification gap — HYPE, ZEC, FARTCOIN were not tagged as crypto at all

`backend/webhooks/tradingview.py`'s `CRYPTO_TICKERS` set ("top 20 crypto by market cap") includes BTC/ETH/SOL but not HYPE/ZEC/FARTCOIN. `is_crypto_ticker()` would have returned `False` for these three, meaning an incoming PineScript alert on any of them would **not** get `asset_class="CRYPTO"` tagging, the BTC market-structure filter, or crypto-specific cooldown windows — it would silently fall through equity-path handling. This is foundational asset-tagging infrastructure (not strategy logic), so it's fixed as part of this Phase 1 pass: `HYPE`/`ZEC`/`FARTCOIN` and their `USD`/`USDT` pair variants added to the set. See the `s1(phase1)` commit.

## Full per-vendor evidence log

### Coinalyze
- Auth confirmed present (`COINALYZE_API_KEY` env var set — value not read/printed).
- `/exchanges` → HTTP 200, 8+ exchanges including Hyperliquid (code `H`).
- `/future-markets` → HTTP 200, 4,633 markets. Discovered aggregated (`.A`) symbols for all 6 tickers: `BTCUSD_PERP.A`/`BTCUSDC_PERP.A`/`BTCUSDT_PERP.A`, `ETHUSD_PERP.A`/`ETHBTC_PERP.A`/`ETHUSDT_PERP.A`, `SOLUSD_PERP.A`/`SOLUSDT_PERP.A`/`SOLUSDC_PERP.A`, `HYPEUSDT_PERP.A` (only 1 candidate), `ZECUSDT_PERP.A`/`ZECUSDC_PERP.A`, `FARTCOINUSDT_PERP.A` (only 1 candidate).
- `/funding-rate` read against the discovered symbol for each of the 6 tickers → HTTP 200, non-empty payload, all 6.

### Deribit
- `/public/get_currencies` → HTTP 200. Currency list: XRP, USYC, USDT, USDE, USDC, STETH, SOL, PAXG, MATIC, LINK, EURR, ETH, BUIDL, BTC, BNB, BCH, AVAX, ADA. **HYPE, ZEC, FARTCOIN absent.**
- `/public/get_book_summary_by_currency` (kind=option): BTC → 838 instruments; ETH → 662 instruments; **SOL → 0 instruments** (currency exists but no active options market — `get_25_delta_skew()`-style logic will correctly report "insufficient options data," this is not a bug, just an empty market).

### Binance (Futures — geo-check) + Binance (Spot mirror) + OKX (fallback)
- Futures (`fapi.binance.com/fapi/v1/ping` and per-symbol ticker): **HTTP 451 for all 6 symbols**, verbatim body quoted above.
- Spot mirror (`data-api.binance.vision`): BTC/ETH/SOL/ZEC → HTTP 200 with real prices (BTC $62,143.58, ETH $1,766.85, SOL $74.71, ZEC $496.39). HYPE/FARTCOIN → **HTTP 400 `{"code":-1121,"msg":"Invalid symbol."}`** — not a geo issue, these tokens simply aren't listed on Binance spot.
- OKX SWAP fallback: all 6 symbols → HTTP 200 with real ticker data, including HYPE and FARTCOIN (OKX lists perpetual swaps for both).

### DeFiLlama
- `/pools` → HTTP 200, 15,410 pools. Confirmed **not symbol-specific** — a market-wide stablecoin-yield sentiment gauge, applies as B1 context to all 6 symbols uniformly, not a per-symbol coverage cell.

### Hyperliquid (backup candidate, not sanctioned)
- `POST /info {"type": "meta"}` → HTTP 200, 232-asset universe. All 6 target symbols present by name (BTC, ETH, SOL, HYPE, ZEC, FARTCOIN). Public, keyless, single endpoint.

### UW (Unusual Whales) — new endpoint family, not previously wired into `uw_api.py`
- `/api/crypto/{pair}/state`: BTC-USD/ETH-USD/SOL-USD/ZEC-USD → HTTP 200 with real OHLCV. **HYPE-USD/FARTCOIN-USD → HTTP 200 with `data: null`** (fake-healthy — see Finding 2). No-hyphen ticker format (`BTCUSD` etc.) returns `data: null` for every symbol regardless of coverage — hyphenated format is required.
- `/api/crypto/{pair}/ohlc/1d`: BTC-USD/ETH-USD/SOL-USD → HTTP 200 with real candles. **ZEC-USD → HTTP 200 with an empty array** despite `/state` working (see Finding 3). HYPE-USD/FARTCOIN-USD → empty array, consistent with no coverage.
- `/api/crypto/whale-transactions` (filtered `token_symbol=BTC`, `limit=1`) → reachable, non-empty.

## Credential handling (F-1 task 1.7)

No new vendor was sanctioned in this pass (Hyperliquid was verified but not sanctioned — see Finding 4), so there is no new credential to enroll in rotation. For completeness:
- **Coinalyze** (`COINALYZE_API_KEY`, + aliases `COINALYZE_KEY`/`COINALYZE_TOKEN`): existing Railway env var, handling unchanged by this brief.
- **Deribit, Binance (spot/futures), OKX, DeFiLlama, Hyperliquid, UW crypto endpoints**: all keyless/public (UW crypto reuses the existing `UW_API_KEY` Bearer token already in rotation — no separate crypto-specific key). Nothing new to rotate.

## Cross-cutting notes for Phase 2+ (F-2, F-3, R-2/R-3)

1. **Vendor client parametrization is a separate, larger lift than "sanctioning."** All four `bias_filters/*_client.py` modules need refactoring to accept a symbol parameter before any Tier-2/3 strategy or Cycle Extremes panel can actually read non-BTC data through them. This matrix confirms the *vendor APIs* support the universe; the *client code* does not yet. Flagging for R-2/R-3 sizing, not fixing here (out of F-1's verification scope).
2. **F-3's `hub_get_crypto_quote` must null-check UW's `data` field, not just HTTP status** (Finding 2) — a required implementation detail, not a suggestion.
3. **F-2's resolver bars-source decision is per-symbol, not universal**: UW OHLC for BTC/ETH/SOL; Binance spot klines for ZEC (UW quote works, UW OHLC doesn't); OKX candles for HYPE/FARTCOIN. A single "use UW for crypto bars" rule would silently break ZEC/HYPE/FARTCOIN outcome tracking exactly like the `Session_Sweep` ticker-format bug found in Phase 0.
4. **SOL's Deribit "coverage" is nominal, not functional** — the currency is listed but zero option instruments exist. Any code checking "is SOL a Deribit currency" without also checking instrument count would report false coverage.
