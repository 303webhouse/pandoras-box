# Dark Pool Whale Hunter v2

## Overview
Detects algorithmic execution fingerprints: consecutive bars with matched total volume transacting at the same price level (POC — Point of Control). Identifies institutional accumulation/distribution by finding 3+ bars where both the volume and the POC price are nearly identical, suggesting a large order being executed in slices.

## PineScript Source
`docs/pinescript/webhooks/whale_hunter_v2.pine`

## Indicators Required
- Lower-timeframe volume profile (1m bars for POC approximation)
- RVOL (20-bar) — minimum 1.5x to fire
- SMA 50/200 + ADX (14-period) — regime context
- ATR (14-period) — trade framework
- 50-bar swing high/low — structural context

## Signal Logic

### Core Detection
1. Calculate POC for each bar using lower-timeframe volume data (highest-volume price level)
2. Compare consecutive bars: volume within 8% tolerance AND POC within 0.2% tolerance
3. Require 3 consecutive matched bars (configurable, min 2)
4. RVOL ≥ 1.5x on the signal bar
5. Time filter: exclude 12-1 PM ET lunch

### Directional Bias
- **Bullish whale**: Close > POC on both latest bars (buying above the institutional level)
- **Bearish whale**: Close < POC on both latest bars (selling below the institutional level)
- **Contested**: Mixed closes (no clear direction)

### Structural Context
- Signal near 50-bar swing low + bullish = structural confirmation (stronger)
- Signal near 50-bar swing high + bearish = structural confirmation (stronger)
- Structural confirms get larger visual markers and a flag in the alert payload

## Risk Management

### Stop Loss
0.85 ATR from entry.

### Targets
- TP1: 1.5R
- TP2: 2.5R

## Signal Types
- `WHALE` with lean field: BULLISH / BEARISH / CONTESTED

## Webhook Payload
JSON with: signal, ticker, tf, lean, poc, price, entry, stop, tp1, tp2, rvol, consec_bars, structural (bool), regime (BULL/BEAR/RANGE), adx, vol, vol_delta_pct, poc_delta_pct, time

## Pipeline Route
`/webhook/whale` → `whale.py` handler

## Current Status
- PineScript in repo and webhook-capable
- **TradingView alerts NOT yet configured** — needs alerts set on target charts pointing to `/webhook/whale`
- Backend handler exists (`backend/webhooks/whale.py`) but may need payload format verification against the v2 PineScript JSON structure
- Trade Ideas generated: 0 (alerts not configured)

## Optional: DXY Macro Context
Can color background based on Dollar Index weakness/strength (disabled by default).
