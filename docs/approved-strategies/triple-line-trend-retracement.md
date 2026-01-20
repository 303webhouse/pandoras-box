# Triple Line Trend Retracement (VWAP + Dual 200 EMA)

## Indicators Required
- VWAP (anchored, reset daily)
- 200 EMA based on 1-minute chart (displayed on all timeframes)
- 200 EMA based on 5-minute chart (displayed on all timeframes)
- ADX (14-period) for trend strength filtering

## Core Logic

### Long Setup:
- Price is above all three lines (VWAP, 200 EMA 1-min, 200 EMA 5-min)
- All three lines are stacked bullish (price > VWAP > 200 EMA 1-min > 200 EMA 5-min, or similar bullish order)
- Lines are separated by at least 10 points (no tangling)
- ADX > 25
- 200 EMA 1-min is sloping upward
- Time is after 10:00 AM ET
- Entry trigger: Price pulls back to the EMA/VWAP zone and forms a bullish engulfing candle or hammer, OR price breaks above the pullback high

### Short Setup:
- Price is below all three lines
- All three lines are stacked bearish (price < VWAP < 200 EMA 1-min < 200 EMA 5-min, or similar bearish order)
- Lines are separated by at least 10 points
- ADX > 25
- 200 EMA 1-min is sloping downward
- Time is after 10:00 AM ET
- Entry trigger: Price pulls back to the EMA/VWAP zone and forms a bearish engulfing candle or shooting star, OR price breaks below the pullback low

## Risk Management

### Stop Loss:
2-5 points beyond the furthest EMA/VWAP line in the zone, OR below/above the pullback swing low/high (whichever is tighter)

### Take Profit:
- Target 1: 1:1 risk/reward (take partial, e.g., 50%)
- Target 2: Trail remainder using 200 EMA 1-min, or fixed 50+ point target

### Time Exit:
If trade has not reached Target 1 within 60 minutes, close or tighten stop to breakeven

## No-Trade Conditions
- Before 10:00 AM ET
- ADX < 25
- Lines are within 10 points of each other (tangled/choppy)
- 200 EMA 1-min is flat (no slope)

## Timeframe
- Chart: 5-minute
- Instrument: NQ, ES, or similar liquid index futures

## Signal Classification
- **APIS CALL**: Long signal + Toro bias + strong alignment
- **KODIAK CALL**: Short signal + Ursa bias + strong alignment
- **BULLISH TRADE**: Long signal meeting criteria but weaker macro alignment
- **BEAR CALL**: Short signal meeting criteria but weaker macro alignment
