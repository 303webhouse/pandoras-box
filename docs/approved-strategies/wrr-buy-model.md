# WRR Buy Model (Raschke Countertrend)

## Overview
Countertrend mean-reversion strategy based on Linda Raschke's WRR (Widner Range Reversal) Buy Model. Trades snap-back bounces when price is deeply oversold within a bearish regime (or deeply overbought within a bullish regime for the short variant). This is the system's first **countertrend lane** strategy — it bypasses the normal bias-alignment gate under strict conditions.

## Origin
- Linda Bradford Raschke, documented in *Street Smarts* and various public teachings
- Related to George Douglass Taylor's 3-day cycle framework (Taylor Trading Technique)
- Evaluated by Olympus Committee: March 16, 2026 — APPROVED with conditions

## Countertrend Lane Rules (Olympus-Mandated)
This strategy operates under special gating rules that differ from standard trend-aligned strategies:
1. **Whitelisted strategy** — only committee-approved countertrend strategies can use this lane
2. **Bias extreme required** — composite bias must be ≤25 (bearish extreme) for long signals, or ≥75 (bullish extreme) for short signals
3. **Confluence threshold: 90** — five points above the standard MAJOR gate of 85
4. **Half-size positions** — 50% of normal allocation, non-negotiable
5. **Accelerated expiry** — trade ideas expire in 24-48 hours (vs. standard window)
6. **Distinct UI treatment** — tagged as `COUNTERTREND` lane in Trade Ideas, visually differentiated

## Signal Logic

### WRR Long (Buy Day)
1. Composite bias ≤ 25 (deeply bearish — crowd is stretched)
2. Price has declined 3+ consecutive days OR printed a new 20-day low
3. Daily RSI(3) ≤ 15 (extreme short-term oversold)
4. Current bar prints a **reversal candle**: bullish engulfing, hammer, or doji with lower wick > 2x body
5. Volume on reversal bar ≥ 1.5x 20-day average (capitulation volume)
6. Price is within 1 ATR of a key support level (prior swing low, VWAP, or round number)
7. Rate of Change (10-period) is deeply negative (confirms stretched condition)

### WRR Short (Sell Day)
Mirror: composite bias ≥ 75, 3+ up days or new 20-day high, RSI(3) ≥ 85, bearish reversal candle, volume spike at resistance.

## Risk Management

### Stop Loss
Below the reversal candle low minus 0.5 ATR (longs). Above reversal candle high plus 0.5 ATR (shorts). Tight stops are the defining feature — you know exactly where you're wrong.

### Targets
- TP1: 1.5R (take half)
- TP2: 3-day SMA or VWAP reversion (take remainder)
- Max hold: 2-3 days. This is NOT a swing trade.

## Signal Types
- `WRR_LONG` — countertrend long (tagged with lane: COUNTERTREND)
- `WRR_SHORT` — countertrend short (tagged with lane: COUNTERTREND)

## Implementation Notes
- PineScript webhook TBD (needs TradingView alert slot — currently both slots occupied by Artemis and Phalanx)
- Server-side scanner implementation is the likely path (similar to Scout Sniper)
- **Data source: Polygon.io** for daily bars. yfinance as fallback only.
- Alternatively: manual signal entry via Agora UI when conditions visually align

## Pipeline Route
Server-side scanner → `process_signal_unified()` with `lane: countertrend` flag → countertrend scoring rules (in `trade_ideas_scorer.py`) → committee review (if score ≥ 90)

## Applied To
Daily charts on individual equities, ETFs, and potentially BTC (via Stater Swap).

## Status
- **Approved:** March 16, 2026 (Olympus Committee)
- **Titans Approved:** March 17, 2026
- **Build status:** PENDING — awaiting CC brief
- **Trade Ideas generated:** 0 (not yet implemented)
