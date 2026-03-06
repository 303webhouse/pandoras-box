# Holy Grail Pullback Continuation (Raschke)

## Overview
Continuation entry strategy based on Linda Raschke's "Holy Grail" setup. Enters in the direction of a strong trend (ADX ≥ 25) after a pullback to the 20 EMA, on the confirmation candle that closes back in the trend direction.

## PineScript Source
`docs/pinescript/webhooks/holy_grail_webhook_v1.pine`

## Indicators Required
- ADX (14-period) — must be ≥ 25 (strong trend)
- DI+ / DI- (14-period) — determines trend direction
- 20 EMA — pullback target
- RSI (14-period) — optional filter (long: RSI < 70, short: RSI > 30)

## Signal Logic

### Long Setup
1. ADX ≥ 25 (strong trend confirmed)
2. DI+ > DI- (uptrend)
3. Previous bar pulled back to within 0.15% of 20 EMA (touch tolerance)
4. Current bar closes above the 20 EMA (confirmation)
5. RSI < 70 (not overbought)

### Short Setup
1. ADX ≥ 25 (strong trend confirmed)
2. DI- > DI+ (downtrend)
3. Previous bar pulled back to within 0.15% of 20 EMA
4. Current bar closes below the 20 EMA (confirmation)
5. RSI > 30 (not oversold)

## Risk Management

### Stop Loss
Below the pullback bar's low (longs) or above the pullback bar's high (shorts).

### Targets
- TP1: 2.0R from entry (risk = entry − stop)
- No TP2 in current PineScript (single target)

### Cooldown
5 bars between signals on the same chart.

## Signal Types
- `HOLY_GRAIL_1H` — 1-hour timeframe (higher base score, cleaner pullbacks)
- `HOLY_GRAIL_15M` — 15-minute timeframe (lower base score, noisier)

## Webhook Payload
JSON with: ticker, strategy ("holy_grail"), direction, entry_price, stop_loss, target_1, adx, rsi, timeframe, rvol (carries DI spread)

## Pipeline Route
`/webhook/tradingview` → `process_holy_grail_signal()` → `process_signal_unified()`

## Trade Ideas Generated
8 all-time (as of Mar 6, 2026)

## Known Issues
- ETF signals (QQQ, SMH) crash the committee pipeline due to yfinance fundamentals 404. Fix in progress.

## Applied To
Multi-chart: SPY, QQQ, individual equities on 15m and 1H timeframes.
