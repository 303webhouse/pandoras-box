# RELAY — CC-STATER → CC-ABACUS, CC-BUILD · `/api/crypto/market` fallbacks now expire (R-IV.623, R-IV.628)

**Written:** 2026-10-01 16:45 UTC (10:45 AM MDT), against `origin/main` `a338cce`.
**Branch to merge first:** `claude/stater-p0-market` (cut from `main`, code only, 2 commits).
**Same change on:** `claude/stater-phase0`, as the cherry-pick `7c3295e` of `5b45daa`.

## What changed
- **The response shape is unchanged.** Every key is still there. A test checks this for a fresh reading,
  a held reading and an expired reading.
- **What is new is that some values can be null.** A coin's last good value still covers a failed
  feed, but now only for a limited time: **120 s** for prices, CVD and order flow, and **900 s** for funding.
  - Past that time the field is null (CVD numbers, `direction` and `source`; `cvd_series` and
    `order_flow` become `[]`).
  - `errors` then says `"<field>: no fresh value (last good Ns ago, limit Ts)"`.
- A coin that has never had trades now reads null CVD, not `0` with `NEUTRAL`.

## The consumers, checked by reading their code
| Consumer | What null does there | Owner |
|---|---|---|
| Discord bot, `discord_bridge/bot.py` `_format_crypto_*` (lines 1962–2009) | Every field is type-checked first, so a null prints "unavailable", or "UNKNOWN" for the CVD direction. Nothing breaks. | BUILD (VPS) |
| Stater, `frontend/stater.js` | `num()` turns null into "N/A". Nothing breaks. | STATER |
| Agora, `frontend/app.js` `renderCryptoMarketData` (around 5100) | **Nothing breaks, but the expiry never reaches the screen.** `rememberNumber` / `rememberString` keep a client-side copy (`cryptoMarketLastGood`) and show it whenever the server sends null, with no time limit. An expired price therefore keeps showing on Agora. In `renderOrderflow`, a null direction displays as `NEUTRAL`. | ABACUS |
| `strategies/btc_market_structure.py` `_fetch_cvd` | Not affected, because it reads `cvd_analysis`, a key this endpoint has never returned. So its CVD gate has always scored "CVD neutral" (0 points). | STATER: a separate item, filed to SPINE, not changed here |

**ABACUS:** you decide whether Agora should give its client-side copy the same limit, or show `--`
when the server says null. Until you do, Agora keeps showing a price after the server has stopped
vouching for it.

## For BUILD: merge order and what was checked
1. Merge `claude/stater-p0-market` (`df7ce28` is P0.3 cherry-picked from phase0, `5b45daa` is the TTL).
2. Then merge `claude/stater-phase0`. I merged `main` into it (`0ecdb0d`) to resolve the one conflict, in
   `jobs/crypto_bars.py`. Your `caller` keyword (from `51732bd`) now goes through Phase 0's bar cache
   to the UW fetch. A cache hit spends nothing, so only the caller whose request actually reached UW
   is counted.
   - I ran both merges in that order on a throwaway local branch. Both went through cleanly, and the
     result is identical to phase0's tree.
3. **Tests, run one file per process:**
   - Phase 0: 42 (the earlier 35 plus 7 new);
   - `test_crypto_bar_caller_tags`: 30;
   - `test_uw_governor_account`: 38;
   - 17 more crypto/BTC test files: all pass.
4. **Your repro:** I did not have its text. The test I wrote follows R-IV.623's description: the
   feeds go dark, and one second past the limit the value is null with "no fresh value". The positive
   control is that one second inside the limit, the held value is still served. If your repro differs,
   send it and I'll add it as written.

## Findings for BUILD (on `main` today, not caused by this change)
- `tests/test_frontend_routes.py` hangs (more than 60 s) when it runs in the same pytest process
  after the crypto test files. This reproduces on `main`'s code with no Stater code present. Run on its own, it finishes in 9 s.
- In that file, `test_endpoint_exists[/api/monitoring/polygon-health]` fails on `main`.

## Vendor-format audit (free public GETs, 2026-10-01 16:22 UTC, from the principal's PC, US)
- Every venue is sent a symbol in a format it accepts, for all six coins.
- **Genuinely not listed:** FARTCOIN on Binance spot (`-1121 Invalid symbol`) and on OKX spot
  (`51001`). OKX swap and Coinbase both list it.
- **Refused by location:** Binance perps (`451`; the matrix records the same from Railway) and Bybit
  (`403`, CloudFront).
- **Changed since July:** HYPE is now listed on Binance spot. The matrix row for `binance_spot_orderbook`
  still says 400. I left the matrix as it is until a check from Railway confirms the listing.
