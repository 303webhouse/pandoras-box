# Scout Sniper v3.1 (15m Early Warning)

## Overview
15-minute reversal scanner that detects RSI hooks at oversold/overbought extremes with volume confirmation and reversal candle patterns. Produces early warning signals (not full trade signals) that should be confirmed by higher-timeframe setups. Includes TRADEABLE/IGNORE classification and a built-in 0-6 quality score.

## PineScript Source
`docs/pinescript/webhooks/scout_sniper_v3.1.pine`

## Indicators Required
- RSI (14-period) — oversold < 30 (long hook), overbought > 70 (short hook)
- RVOL (20-bar) — Tier A ≥ 1.6x, Tier B ≥ 1.1x
- 15-minute VWAP — longs must be below VWAP, shorts above (quality gate)
- SMA 50/120/200 — regime filter (bullish/bearish/mixed alignment)
- HTF VWAP (1H default) — TRADEABLE requires alignment
- Daily VWAP — target calculation
- ATR (14-period) — stop and target calculation

## Signal Logic

### Long Setup
1. RSI was < 30 on previous bar and is now rising (oversold hook)
2. Price is at or below 15m VWAP
3. Reversal candle: hammer, bullish doji, or bullish engulfing
4. RVOL ≥ 1.1x (Tier B) or ≥ 1.6x (Tier A)
5. Cooldown: 4 bars since last signal
6. Time filter: not first 15 min, not 12-1 PM ET lunch

### TRADEABLE vs IGNORE
- TRADEABLE: Signal + HTF VWAP aligned + SMA regime not bearish (or Tier A override)
- IGNORE: Signal fires but regime doesn't confirm

### Quality Score (0-6)
1. Time filter OK (+1)
2. HTF regime aligned (+1)
3. RVOL: Tier A (+2) or base (+1)
4. SMA regime aligned (+1)
5. Not near structural resistance/support (+1)

## Risk Management

### Stop Loss
Structure mode (default): below signal bar low + 0.15 ATR buffer
ATR mode: 0.8 ATR from entry

### Targets
- VWAP targets (default): TP1 = nearest VWAP (daily or HTF), TP2 = further VWAP
- R-multiple fallback: TP1 = 1.5R, TP2 = 2.0R
- Trending override option: force R-targets when SMA 50/120/200 fully aligned

## Signal Types
- `SCOUT_ALERT` — early warning, low priority, 30-min TTL in cache

## Webhook Payload
JSON with: ticker, strategy ("ScoutSniper"), timeframe, direction, tier (A/B), status (TRADEABLE/IGNORE), score, sma_regime, price, rsi, rvol, plan_printed, entry, stop, tp1, tp2, htf_tf, htf_vwap, d_vwap

## Pipeline Route
`/webhook/tradingview` → `process_scout_signal()` → `process_signal_unified()` (skip_scoring=True, cache_ttl=1800)

## Trade Ideas Generated
21 all-time (as of Mar 6, 2026)

## Note
The Railway handler currently accepts all Scout signals regardless of TRADEABLE/IGNORE status. The `status` field in the payload could be used server-side to filter noise.
