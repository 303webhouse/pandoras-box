# Stater Swap v2 — S-1 Phase 2 Findings (F-2: Outcome-Tracking Parity)

**Date:** 2026-07-13 | **Brief:** `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md`
**Scope:** Extend `backend/jobs/outcome_resolver.py` (the 15-min BAR_WALK walker — canonical per Titans amendment A1) into an asset-class-aware core. Daily-walker (`score_signals.py`) crypto support remains explicitly deferred to S-4.

## What shipped

- `backend/jobs/crypto_bars.py` (new): ticker normalization (`normalize_crypto_ticker`) mapping any of the raw ticker formats actually found in `signals.ticker` (Yahoo-style `BTC-USD`, Binance-native `BTCUSDT`, TradingView `.P`-suffixed) to one of the six tracked base symbols; per-symbol bar dispatch (`fetch_crypto_bars`) via each symbol's `bar_walk_source` in `crypto_symbol_matrix.py` — UW crypto OHLC for BTC/ETH/SOL, Binance spot klines for ZEC, OKX candles for HYPE/FARTCOIN. A symbol with no `LIVE` bar source (or an unrecognized ticker) returns `[]` — the caller leaves it shadow-only/ungraded, never falls back to yfinance (the exact bug that silently broke `Session_Sweep` in the first place).
- `backend/jobs/outcome_resolver.py`: extracted the touch-detection walk (WIN/LOSS/same-bar-tie logic) into a shared `_walk_touch()` used by both the unchanged equity/yfinance path and the new async crypto path (`_walk_bars_crypto`). `resolve_signal_outcomes()` now selects `asset_class` and branches on it.

## Pre-wiring verification (per Nick's explicit condition on ZEC)

The Phase 1 matrix marked ZEC's bar-walk source ("Binance spot klines") as deferred-verify — Phase 1 only confirmed ZEC's *ticker* exists on Binance spot, not that 15-minute kline history actually works. Live-verified before any wiring, from inside the Railway container:

| Source | Symbol(s) | Interval | Result |
|---|---|---|---|
| UW crypto OHLC | BTC-USD, ETH-USD, SOL-USD | 15m | LIVE — 5 real candles each |
| Binance spot klines | ZECUSDT | 15m | **LIVE — 5 real candles, confirmed** |
| OKX candles | HYPE-USDT-SWAP, FARTCOIN-USDT-SWAP | 15m | LIVE — 5 real candles each |

All three per-symbol sources now confirmed at the actual granularity the 15-min walker uses (Phase 1 had only tested 1-day candles).

## End-to-end proof (task 2.2)

Inserted one real shadow-test signal into `signals` (not a simulation — a genuine row, via the actual production `resolve_signal_outcomes()` function):

- `signal_id`: `S1_PHASE2_SHADOW_TEST_BTC_20260713` (row `id=14893`, left in place as documented evidence, `strategy='S1_Phase2_ShadowTest'`, `signal_type='SHADOW_TEST'` — will not be picked up by strategy-name-based dashboard filters)
- Ticker `BTC-USD`, `asset_class='CRYPTO'`, `direction='LONG'`, `signal_ts=2026-07-13T18:20:00Z`, `entry=61900`, `target_1=62200`, `stop_loss=60000` — constructed against real, already-observed BTC 15m bars (target chosen to be touched by the 19:45Z bar, high=62225.07, confirmed before the test).
- Result: `outcome='WIN'`, `outcome_pnl_pct=0.4847%` (exact match: `(62200-61900)/61900*100`), `outcome_resolved_at`=real timestamp, **`outcome_source='BAR_WALK'`**.

## Unplanned but directly relevant discovery: the fix already resolved real stuck signals

The same resolver run (executed for the shadow-test proof, `backfill_days=1`) also touched real production signals already pending in the last day:

- **3 real `Session_Sweep` (BTCUSDT) crypto signals resolved** (`LOSS`, `BAR_WALK`) — these are exactly the signals Phase 0 found permanently stuck at `outcome IS NULL` because `outcome_resolver.py` handed `yfinance` a Binance-native ticker it can't parse. This is empirical proof the F-2 fix works on real, not just synthetic, data.
- **1 real equity signal (`ARTEMIS_NKE`) also resolved correctly** (`WIN`, `BAR_WALK`) via the unchanged yfinance path — confirms the `_walk_touch()` extraction did not regress equity behavior.
- Current state: of 133 total `Session_Sweep` crypto signals, 4 are now resolved (3 from this run + 1 pre-existing outlier from 2026-05-19), **129 remain `outcome IS NULL`** — those are older than the 1-day window I tested with.

## Two things flagged for Nick before this ships (not decided unilaterally)

### 1. The resolver only runs during equity market hours — a real gap for a 24/7 asset

`backend/main.py`'s `outcome_resolver_loop()` gates every 15-min tick on `et.weekday() < 5 and 9 <= et.hour < 16` (NYSE hours). This predates Stater Swap entirely and was never crypto-aware. Effect: even with F-2's fix, crypto signals will only get walked Mon–Fri 9am–4pm ET — a BTC signal that fires Saturday night won't resolve until Monday morning at the earliest, despite the "15-minute" walker's name. This is a scheduling/cadence gap, not a resolver-logic gap — closer to R-1's session-engine territory than F-2's scope. **Not fixed in this pass** — flagging rather than silently expanding scope. Recommend either a dedicated 24/7 crypto-only resolver loop (small, additive) as a fast-follow, or explicit deferral to R-1/S-2.

### 2. Deploying this will functionally clear the 129-signal backlog — is that acceptable without a dry run?

The brief's task 2.3 is explicit: *"No historical backfill in S-1. If a backfill is ever run later, it follows dry-run + apply with hard-stop gates."* I did not run a backfill script. But once this code deploys, the **normal always-scheduled job** (default `backfill_days=60`, next fires at the next equity-market-hours tick per finding #1 above) will pick up all 129 still-`NULL` `Session_Sweep` signals in its ordinary sweep, since they fall inside the 60-day window — the same mechanical effect as a backfill, just via the regular schedule rather than a dedicated script. This is worth an explicit yes/no rather than assuming: the 129 signals are real historical data feeding into future win-rate/promotion-gate math (per PROJECT_RULES's Outcome Tracking Semantics), and grading them all at once with brand-new logic, unreviewed, has some of the same risk profile the brief's dry-run-first instinct is protecting against — even though it isn't a bespoke backfill operation.

## Nick's decisions on the two flagged items (2026-07-13)

1. **129-signal backlog:** ship it — let the normal scheduled job clear it. Not treated as a "backfill" requiring dry-run gates; the 3 real signals resolved during testing graded correctly (matches expected outcome given real price action), and this is the ordinary effect of a bug fix on an always-running job, not a bespoke historical operation.
2. **24/7 scheduling gap:** fix now, not deferred to R-1. Implemented as a small additive change — see below.

### 24/7 crypto resolver loop (implemented per decision #2)

`backend/main.py`'s `outcome_resolver_loop()` is now scoped to `asset_class_filter="EQUITY"` only (unchanged equity-hours gate, Mon–Fri 9am–4pm ET). A new, independent `crypto_outcome_resolver_loop()` runs `resolve_signal_outcomes(asset_class_filter="CRYPTO")` on the same 15-min cadence with **no market-hours gate** — crypto now resolves around the clock. The two loops never double-process the same signal (each is scoped to exactly one `asset_class`). `resolve_signal_outcomes()` gained an `asset_class_filter` parameter to support this split; verified live (both filters run cleanly, no cross-contamination, no errors) before deploying.

## Not touched (explicitly out of scope for F-2)

- `score_signals.py` (daily walker) — crypto support deferred to S-4 per Titans amendment A1.
- The market-hours scheduling gate in `main.py` (see finding #1) — flagged, not fixed.
- No signal older than the resolver's normal 60-day window was touched; no dedicated backfill script was written or run.
