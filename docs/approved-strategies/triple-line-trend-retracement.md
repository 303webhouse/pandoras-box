# Triple Line Trend Retracement (VWAP + Dual 200 EMA)

## Indicators Required
- VWAP (anchored, reset daily)
- 200 EMA based on 1-minute chart (displayed on all timeframes)
- 200 EMA based on 5-minute chart (displayed on all timeframes)
- ADX (14-period) for trend strength filtering

## Regime Pre-Filter (REQUIRED)
Before looking for setups, classify the current market regime:
- **Trending**: ADX > 25, clear directional SMAs → Triple Line ACTIVE
- **Range-bound**: ADX < 20, SMAs flat/tangled → Triple Line INACTIVE
- **Volatile expansion**: VIX spike, wide ranges → Triple Line INACTIVE

Only take Triple Line setups in trending regimes.

## Core Logic

### Long Setup:
- Price is above all three lines (VWAP, 200 EMA 1-min, 200 EMA 5-min)
- All three lines are stacked bullish (price > VWAP > 200 EMA 1-min > 200 EMA 5-min, or similar bullish order)
- Lines are separated by at least 0.5 ATR (no tangling)
- ADX > 25
- 200 EMA 1-min is sloping upward
- Time is after 10:00 AM ET
- Entry trigger: Price pulls back to the EMA/VWAP zone and forms a bullish engulfing candle or hammer

### Short Setup:
- Price is below all three lines
- All three lines are stacked bearish (price < VWAP < 200 EMA 1-min < 200 EMA 5-min, or similar bearish order)
- Lines are separated by at least 0.5 ATR
- ADX > 25
- 200 EMA 1-min is sloping downward
- Time is after 10:00 AM ET
- Entry trigger: Price pulls back to the EMA/VWAP zone and forms a bearish engulfing candle or shooting star

**Note:** This is a pullback strategy ONLY. Do NOT enter on breakouts above/below the line zone.
Add-on entries on breakout continuation are permitted only when already positioned from a pullback entry.

## Line Separation
Minimum separation between VWAP, 200 EMA 1-min, 200 EMA 5-min: **0.5 ATR**
(The old fixed 10-point threshold only worked for NQ. ATR-based scales across all instruments.)

## CTA Level Check (REQUIRED)
Before entering, verify price is NOT running into a major SMA level:
- Do NOT enter long if SMA 50/120/200 is within 1 ATR ABOVE entry
- Do NOT enter short if SMA 50/120/200 is within 1 ATR BELOW entry
These levels act as magnets and resistance — entering into them kills R:R.

## Risk Management

### Stop Loss:
2-5 points beyond the furthest EMA/VWAP line in the zone, OR below/above the pullback swing low/high (whichever is tighter)

### Targets
- TP1: 1.5R (take 1/3 off, move stop to breakeven)
- TP2: 2.0R (take 1/3 off, trail stop at 1R)
- TP3: Trail remainder with 1 ATR trailing stop
Minimum acceptable R:R at entry: 1.5:1. Do not take setups below this.

### Time Exit:
If trade has not reached TP1 within 60 minutes, close or tighten stop to breakeven

## Position Scaling
- Initial entry: 25-40% of full position size
- Confirmation add: After first target hit or trend continuation signal, add 25-40%
- Never exceed 100% of calculated position size
- If stop is hit before adding, loss is limited to partial size

## No-Trade Conditions
- Before 10:00 AM ET
- ADX < 25
- Lines are within 0.5 ATR of each other (tangled/choppy)
- 200 EMA 1-min is flat (no slope)
- Market regime is range-bound or volatile expansion (see Regime Pre-Filter)
- Price is running into major CTA SMA level within 1 ATR (see CTA Level Check)

## Timeframe
- Chart: 5-minute
- Instrument: NQ, ES, or similar liquid index futures

## Signal Classification
- **APIS CALL**: Long signal + Toro bias + strong alignment
- **KODIAK CALL**: Short signal + Ursa bias + strong alignment
- **BULLISH TRADE**: Long signal meeting criteria but weaker macro alignment
- **BEAR CALL**: Short signal meeting criteria but weaker macro alignment
