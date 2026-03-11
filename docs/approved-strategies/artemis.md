# Artemis v2.1 (VWAP Band Mean Reversion)

## Overview
Mean-reversion strategy that trades bounces off VWAP standard deviation bands (VAH/VAL). Two modes: Normal (trend + confirmation candle at band) and Flush (exhaustion reversal after 3%+ move). Gated by weekly AVWAP context for directional bias.

## PineScript Source
`docs/pinescript/webhooks/hub_sniper_v2.1.pine`

## Indicators Required
- VWAP with ±2 standard deviation bands (20-bar lookback)
- ADX (14-period) — min 20 for trend strength
- RSI (14-period) — directional filter
- RVOL (20-bar) — 1.25x for normal mode, 2.0x for flush mode
- ATR (14-period) — stop calculation
- Weekly AVWAP (context gate)

## Signal Logic

### Normal Mode (Long)
1. Not in flush mode (price hasn't moved 3%+ in 5 bars)
2. Price touches or comes within 0.25 ATR of VAL (lower band)
3. Price closes above VAL (bounce confirmed)
4. ADX > 20 (trending market)
5. RSI < 60 (not overbought)
6. RVOL ≥ 1.25x
7. Bullish confirmation candle (engulfing or hammer) with ≥ 1.2x RVOL
8. AVWAP gate: price above weekly AVWAP (with 0.1 ATR buffer)
9. Time filter: after 10 AM ET, not during 12-1 PM lunch
10. R:R ≥ 1.5 at TP1 (minimum quality gate)

### Normal Mode (Short)
Mirror of long at VAH (upper band), with RSI > 40, bearish confirmation candle, price below weekly AVWAP.

### Flush Mode (Long)
1. Price dropped 3%+ in 5 bars OR moved > 2 ATR downward
2. Price touches VAL zone
3. Bullish exhaustion: RVOL ≥ 2.0x + lower wick > 0.5x body + RSI hook from oversold
4. AVWAP gate passes

### Flush Mode (Short)
Mirror: price rallied 3%+ into VAH with bearish exhaustion candle.

## Risk Management

### Stop Loss
0.85 ATR below the low (longs) or above the high (shorts).

### Targets
- TP1: 1.5R
- TP2: 2.0R
- Optional: AVWAP as extra target marker

## Signal Types
- `ARTEMIS_LONG` — long signal (can upgrade to `APIS_CALL` at score ≥ 85)
- `ARTEMIS_SHORT` — short signal (can upgrade to `KODIAK_CALL` at score ≥ 85)

## Webhook Payload
JSON with: ticker, strategy ("Artemis"), direction, entry_price, stop_loss, target_1, target_2, risk_reward, timeframe, adx, adx_rising, rsi, rvol, mode (Normal/Flush), avwap_ctx, avwap_buf_atr, prox_atr

## Pipeline Route
`/webhook/tradingview` → `process_artemis_signal()` → `process_signal_unified()`

## Trade Ideas Generated
6 all-time (as of Mar 6, 2026)

## Applied To
15-minute charts on individual equities and ETFs.
