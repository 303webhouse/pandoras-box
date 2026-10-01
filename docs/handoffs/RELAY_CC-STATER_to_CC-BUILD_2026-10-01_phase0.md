# RELAY — CC-STATER → CC-BUILD · Stater Phase 0 for review (R-IV.619)

**Branch:** `claude/stater-phase0`. It is stacked on `claude/stater-scope` (docs only), which is
stacked on `origin/main` `b0ada46`. Nothing is merged or deployed. SPINE rules before you merge.
**Scope:** fixes only, in CC-STATER-owned files. No shared code, schema, migrations or `main.py`
changed.

## Commits, in SPINE's order
| # | Commit | What changes for a reader |
|---|---|---|
| P0.1 | `fix(stater): crypto GETs read stored rows…` | `GET /api/crypto/cycle-extremes` and `GET /api/crypto/tape-health` serve the newest stored row per symbol. They no longer run the engines, insert log rows or fire CVD events. The scheduler jobs are the only writers. Stale after one missed run (tape 1,200 s, cycle 4,500 s). `jobs/crypto_bars.py` shares one bar set per (symbol, interval, vendor) for 5 min (15m) / 1 h (daily). |
| P0.2 | `fix(stater): BTC/ETH/SOL bars from Coinbase Exchange public, not UW` | `config/crypto_symbol_matrix.py`: BTC/ETH/SOL `bar_walk_source` is now `coinbase_exchange_candles` (`api.exchange.coinbase.com`, free, no key), with an OKX public fallback. No tracked symbol routes bars to UW. 15-minute bars use two pages (about 6.8 days, measured) versus UW's 500 rows (about 5.2 days), so the outcome resolver's reach grows. The regime job labels the source `COINBASE`. |
| P0.3 | `fix(stater): /crypto/market keeps each coin's cache, fallbacks and CVD state apart` | The response cache, `_last_good` and the CVD trend state are keyed by canonical pair. `BTC`, `BTC-USD`, `btc` and `BTCUSDT.P` all become `BTCUSDT`. **The response shape is unchanged** (tested), so Agora `app.js` and the Discord bot need nothing. |
| P0.6 | `fix(stater): POST /btc/bottom-signals/reset declared before /{signal_id}` | The reset now reaches its handler instead of returning 422. |
| P0.4/5 | `fix(stater): honest readings and a crypto-only signal feed` | See the three items below this table. |

**P0.4/5 details:**
- **Session block:** it now reads keys that exist, via `utils.crypto_sessions.session_block_fields`, so `state` is the partition. This applies to `/crypto/state` and `hub_get_crypto_state`.
- **Tape stale limit:** shared, at one cadence plus grace (1,200 s).
- **New endpoint:** `GET /api/crypto/signals` (gated, read-only, projected columns, every row marked `shadow`).
  - `/api/trade-ideas` and `EXCLUDE_CRYPTO_SQL` are untouched.
  - Stater reads the new route, asks `/market` for full pairs, and shows N/A rather than 0.
  - Pins: `v2.css?v=39`, `stater.*?v=2`.

## Things for you to check at review
- **`hub_get_crypto_state`.** It is `services/read_only/crypto_state.py`, which is owned. Its `session.state` changes from always-null to the partition name, and its tape block reads fresh for a full cadence instead of going stale after 600 s. Additive and honest, but the committee skills read it.
- **Outcome resolver for crypto.** Bars now come from Coinbase. The tuple shape is unchanged and sorted ascending, as before.
- **UW quota table.** `uw_governor.QUOTAS["outcome_resolver"]` (4,500) also covered crypto bars. After the merge that caller's crypto share drops to zero, so the quota could be lowered. That is your file and your call.
- **Test side effect.** Running the full backend suite rewrites the tracked `data/watchlist.json`. It is not from this branch; it happens on `main` too.

## Measured, from the governor's own counts (`GET /api/uw/health/by_caller`)
- **No Stater tab open:** `outcome_resolver` 75 → 78 → 81 between 05:59 and 06:33 UTC on 2026-10-01, about 12 calls an hour.
- **One `GET /api/crypto/state/BTC` costs exactly 1 UW call:** 3 GETs moved the counter 81 → 84. The page made that call every 30 s, which is 2,880 a day from this route alone.
- **`/tape-health` was not measured live**, because a GET on today's `main` writes rows. Its code path adds up to 3 bar pulls per poll (BTC/ETH/SOL CVD event detection).
- **After:** tests prove zero UW calls from these GETs and from bars for all six symbols, each with a positive control. Re-take the same counter snapshots after deploy to confirm.

## Still open in this lane (not in this branch)
- The geo-blocked strategy engine (`crypto_setups.py` reads `fapi.binance.com`, HTTP 451 from Railway).
- The cycle engine counts top signals as capitulation.
