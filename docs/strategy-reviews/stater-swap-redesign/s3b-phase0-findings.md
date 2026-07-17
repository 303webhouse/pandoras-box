# S-3b Phase 0.1 Findings — Klines Audit (2026-07-17)

Per the S-3b micro-brief's own precondition: *"Confirm live from Railway, per-symbol, before writing any event-anchoring logic against it: does `integrations.binance_futures.get_klines()` actually return data for all six symbols today, or does it silently fail/return empty for anything beyond BTC... If it's BTC-only or geo-blocked with no fallback, that's a second hard-stop-class finding — flag it the same way §5.1 was flagged, do not improvise a fix inline."*

**Finding: it's worse than "BTC-only." A code-level ticker-format defect likely breaks `get_market_structure_context()`'s klines fetch for all six symbols, including BTC — introduced yesterday by S-3 Phase 1's ticker normalization work, already live in production since `0037375`.**

## The defect

`get_market_structure_context(ticker, entry_price, direction)` (`backend/strategies/btc_market_structure.py:340`) calls, unmodified:

```python
from integrations.binance_futures import get_klines
klines = await get_klines(ticker, "1h", limit=24)   # line 366
```

`get_klines()` (`backend/integrations/binance_futures.py:101`) passes `ticker` straight through as Binance Futures' `symbol` query param with **no format conversion**:

```python
data = await _fetch_json(
    f"{BINANCE_FUTURES_BASE}/fapi/v1/klines",
    params={"symbol": symbol, "interval": interval, "limit": limit},
    use_proxy=True,
)
```

Binance Futures requires a full pair symbol (`BTCUSDT`, `ETHUSDT`, ...). But **both call sites** now hand `get_market_structure_context()` a ticker that's already been through `normalize_crypto_ticker()`, which strips to a bare base symbol (`BTC`, `ETH`, `SOL`, `HYPE`, `ZEC`, `FARTCOIN` — no suffix):

- `backend/strategies/crypto_setups.py:99` — `"ticker": _normalize_crypto_ticker(ticker) or ticker` inside `_build_signal()`, then `crypto_setups.py:486` calls `get_market_structure_context(ticker=sig["ticker"], ...)`.
- `backend/webhooks/tradingview.py:140` — `_process_with_market_structure()` calls `get_market_structure_context(ticker=signal_data["ticker"], ...)`, where `signal_data["ticker"]` was already normalized earlier in the TradingView webhook path (per commit `0037375`'s own description: *"tradingview.py: normalization strictly after HMAC verification"*).

**Both of `get_market_structure_context()`'s production call sites feed it a bare base symbol.** `get_klines("BTC", "1h", limit=24)` is the actual live call — not `get_klines("BTCUSDT", ...)`.

## When this was introduced

`git log -p` on the `crypto_setups.py` ticker line confirms: before commit `0037375` (2026-07-16, "s3(phase1): canonical ticker normalization at ingress"), the field was `"ticker": ticker` — the raw, un-normalized value (which for a TradingView-sourced signal would already be Binance-pair-shaped, e.g. `BTCUSDT`, and would have worked). `0037375` changed it to `_normalize_crypto_ticker(ticker) or ticker`, which strips to the bare base symbol. **This is a regression introduced by S-3 Phase 1, not a pre-existing gap** — `get_market_structure_context()` itself wasn't touched by S-3 and was never audited against the new normalized-ticker convention it now silently receives.

## Confirmed vs. not confirmed

- **Confirmed by direct code read + git blame:** the format mismatch itself (bare base symbol in, full-pair-symbol required by Binance).
- **Confirmed:** `CRYPTO_BINANCE_PERP_HTTP_PROXY` env var exists on the Railway service (checked existence only, never printed the value) — so the geo-block bypass infrastructure the brief assumed ("already-shipped machinery") is at least present.
- **Not confirmed (cannot be, without Railway shell access or an admin trigger endpoint):** what Binance actually returns for `symbol=BTC` when called *through* that proxy from Railway's egress. Direct unproxied calls from this machine to `fapi.binance.com` for both bare (`BTC`) and full-pair (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `HYPEUSDT`, `ZECUSDT`, `FARTCOINUSDT`, `1000FARTCOINUSDT`) symbol forms all returned the same geo-block message (HTTP 200, `{"code": 0, "msg": "Service unavailable from a restricted location..."}`) — geo-blocked here regardless of format, so this environment can't distinguish "invalid symbol" from "geo-block" empirically. The proxy may or may not resolve the geo half; it cannot resolve the format half, since a bare `BTC` is not a valid Binance Futures symbol under any network path.

## Failure mode: honest-labeled, not fake-healthy — but a real, live regression

`_score_volume_profile()` (`btc_market_structure.py:147`) already handles a fetch failure gracefully: `if "error" in profile: return 0, "volume profile unavailable"`. So this doesn't crash and doesn't fabricate a fake score — the `context_label`/reasoning string honestly says "volume profile unavailable." But it means **the volume-profile leg of `get_market_structure_context()`'s score modifier has likely been silently contributing 0 (not a real read) for every crypto signal processed through both call sites since `0037375` deployed yesterday** — a live, currently-running production degradation, not just an S-3b blocker. (CVD-gate and orderbook legs of the same function are separate code paths, not affected by this specific defect — only the volume-profile leg calls `get_klines()`.)

## Why this blocks S-3b Item 2, not Item 1

The brief's own framing: *"Phase 0.1 klines audit... is a hard precondition before any event-anchoring code."* Item 2 (§5.3/§5.4 CVD event detection) explicitly anchors at POC/VAH/VAL pulled from this same `compute_volume_profile()` output — broken input here means Item 2 cannot be built safely. Item 1 (wiring `_fetch_spot_cvd()` into `crypto_tape_health_engine.py`) is structurally independent — it's a separate OKX spot-trades fetch, no dependency on `get_market_structure_context()` or Binance klines at all.

**Stopping before both items regardless**, per the brief's explicit instruction not to improvise around a hard-stop-class finding, and because this finding's live-production scope (a real regression from yesterday's deploy, not just a precondition gap for tonight's work) seems to warrant Nick's/Fable's attention before any further S-3b code — not a unilateral "skip Item 2, proceed with Item 1" call.

## Not done

No fix attempted. No file touched other than this findings doc. Not proceeding to S-3b Item 1 or Item 2.

## Remediation options (not chosen, for Fable/Nick to rule on)

1. **Fix `get_klines()` call sites to append the Binance pair suffix.** E.g. `get_market_structure_context()` (or a thin wrapper) maps the canonical bare symbol to its Binance Futures pair symbol before calling `get_klines()` — needs a real symbol map, since Binance's actual listed pair name isn't always a mechanical `{BASE}USDT` (e.g., some low-price alts list as `1000{BASE}USDT`; unconfirmed whether HYPE/ZEC/FARTCOIN are even listed on Binance Futures at all — would need to check Binance's exchangeInfo endpoint, which itself may be geo-blocked from this environment without the proxy).
2. **Route `get_market_structure_context()`'s klines fetch through the already-sanctioned F-2 per-symbol path** (`jobs/crypto_bars.py`, the same source S-3's regime/cycle engines use) instead of the standalone `integrations.binance_futures.get_klines()` call — consolidates onto one already-audited, already-multi-symbol-proven data path rather than fixing a second one. This is closer to what the brief hinted at ("a different code path from the sanctioned F-2 per-symbol routing").
3. **Confirm scope and defer.** If Nick/Fable judge the volume-profile leg's degradation as low-urgency (score modifier defaults to a labeled 0, doesn't crash or block signal flow), this could be logged as a known-red follow-up rather than an immediate fix, and S-3b re-scoped to Item 1 only (tape-health state, no event-anchoring) until the klines path is separately repaired.

Flagging for Fable/Nick review before any further S-3b work.
