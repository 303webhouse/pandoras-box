# S-3b Phase 0.1 Fix — Completion Note (2026-07-17)

Implements Fable's ruling rev-2 (supersedes Option A), fixing the ticker-format defect found during the S-3b klines audit (`s3b-phase0-findings.md`) across all three legs of `get_market_structure_context()`.

## What changed

**LEG 1 — volume profile (`backend/strategies/btc_market_structure.py:358-380`): rerouted, not format-fixed.** Replaced the direct `integrations.binance_futures.get_klines()` call with `jobs.crypto_bars.fetch_crypto_ohlc()` — the F-2 per-symbol bar source, already canonical-ticker-native, already matrix-gated on `bar_walk_source.status == "LIVE"`, already the exact source `hub_get_crypto_market_profile` uses (S-3 §1.4/§6.3, empirically proven live for BTC/ETH per Fable's two probes). No symbol conversion needed for this leg — the bug simply doesn't exist on this path. Two fidelity notes, both inherited from the shipped pattern being mirrored, not introduced here: (1) volume is a `1.0` placeholder (time-at-price, not volume-weighted — F-2 bars carry no per-bar volume); (2) `fetch_crypto_ohlc(use_daily=False)` returns 15m-granularity bars, so the `[-24:]` slice is ~6h of coverage, not the original 24h the "1H klines" comment implied — `hub_get_crypto_market_profile` has this exact same discrepancy under the same variable name (`bars_1h`), so this mirrors shipped behavior byte-for-byte rather than silently "improving" it.

**LEG 2 — CVD (`:382-395`) and LEG 3 — orderbook (`:397-419`): format fix via one conversion choke point.** Added `get_binance_futures_symbol()` to `backend/config/crypto_symbol_matrix.py` — a single `{BASE}USDT` mapping dict for all six symbols, no inline concat anywhere. Both legs now resolve the canonical ticker to its Binance Futures pair symbol before calling out (Leg 2 → `/api/crypto/market?symbol=BTCUSDT`, which already has internal OKX fallback for the perp legs; Leg 3 → `get_orderbook_depth("BTCUSDT", ...)`, no fallback, honest `NA:BINANCE_FUTURES_UNAVAILABLE` label added when the fetch comes back empty). The mapping is explicitly documented as format-only, not a live-coverage claim — Binance Futures listing status for HYPE/ZEC/FARTCOIN specifically is UNVERIFIED (this environment is geo-blocked from testing `fapi.binance.com` directly), and `fapi.binance.com` is already documented GEO_BLOCKED from Railway for all six symbols per the existing `binance_quarterly_basis` matrix cells (2026-07-13) and reconfirmed by `bias_filters/binance_client.py`'s shipped S-3 comment (`d0ed66e`, 2026-07-16). Whichever way that resolves at runtime, the existing honest-failure path (`{"error": ...}` → labeled 0, never a fabricated number) already handles it correctly — this fix only ensures a *correctly-formatted* attempt is made, not a doomed "invalid symbol" one.

## Scope check (Condition 3)

Found two additional unconverted call sites beyond the originally-flagged klines call, both in the same function, same defect class — reported before touching them ([[fix-scope AskUserQuestion]]), user chose "fix all three legs." No further unconverted sites found in this audit.

## Tests (Condition 2)

`backend/tests/test_s3b_market_structure_fetch_boundary.py`, 7 tests, all passing:
- Canonical→pair mapping for all six symbols + one no-coverage case (untracked symbol → `None`).
- Leg-1 reroute: canonical ticker in → real (non-error) profile out, mocking `fetch_crypto_ohlc`; a second test confirms an honest-unavailable degrade when the bar source returns `[]`.
- Legs 2/3: mocked assertions that the *pair* symbol (not the bare canonical form) is what actually reaches the vendor call — locks the boundary against a future normalization pass reintroducing this exact regression.

Full suite: `18 failed, 353 passed, 1 skipped, 203 errors` — byte-for-byte identical failed-test composition to baseline, `+7` from these new tests, errors unchanged. No new red.

## Pollution assessment (Condition 4) — report-only, no writes

Queried `signals` where `asset_class = 'CRYPTO'`:
- Since `0037375` (2026-07-16T22:26:50Z): **2 rows total**, neither carries a `market_structure` key in `enrichment_data`.
- **Across the entire table history (977 CRYPTO rows, back to 2026-03-03): zero rows have ever carried `market_structure` enrichment.** `get_market_structure_context()`'s output has apparently never actually landed in persisted `enrichment_data` — not just since yesterday's deploy, but ever. There is no historical "polluted" data to quarantine from this specific persistence path, because it was never populated in the first place. (`tradingview.py::_process_with_market_structure()` is the only call site that writes this key; `crypto_setups.py`'s scanner path applies the score modifier inline but never persists the breakdown.)
- No zeroed-modifier-without-label rows found, because no rows carrying the modifier's breakdown exist at all to check. **No backfill performed or proposed** — nothing to backfill.

**Separate, out-of-scope finding, flagging only:** the 2 recent CRYPTO/BTC rows (`Session_Sweep` strategy, `2026-07-17T19:53Z` and `20:23Z`) carry clearly non-crypto, equity-shaped `enrichment_data` (`rvol`, `atr_14`, `sector_3_10`, `iv_rank_uw_shadow` fields) with `current_price` ~$27-28 — nowhere near BTC's real price (~$64,000). Looks like a ticker-collision or misclassification bug unrelated to the fetch-boundary defect this brief covers. Not investigated further, not touched.

## Deploy status

Code + tests committed and pushed (blackout retired per `PROJECT_RULES.md`). **Condition 5's post-deploy live check (VP leg non-degraded for BTC + ETH) is being run by Fable via a separate live surface, not by CC** — per explicit instruction, since `get_market_structure_context()` has no debug endpoint and its output has never appeared in persisted data (see pollution assessment above), making a CC-side live check impractical without sending synthetic test signals through the production webhook, which was declined in favor of Fable's own verification path.

**Holding here — not proceeding to S-3b Items 1/2 until Fable reports the VP-leg live check clears.**
