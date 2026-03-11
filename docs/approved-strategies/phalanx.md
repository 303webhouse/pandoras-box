# Phalanx v1.5 (Absorption Wall Detector)

## Overview
Detects institutional order flow absorption: two consecutive bars with matched total volume (within 5%), matched delta ratio (within 3%), and matched buy percentage (within 3%), while price barely moves (stall < 0.30 ATR). Indicates a large order absorbing directional pressure at a specific price level.

Directional lean from approach: price falling INTO wall = bullish support (PHALANX_BULL), price rising INTO wall = bearish resistance (PHALANX_BEAR).

This is a LEVEL IDENTIFICATION signal, not a trade generator. No stop/target. Dual purpose:
1. Standalone ORDER_FLOW context card in Trade Ideas
2. Future confluence enrichment — boosts score of other signals near the wall level

## PineScript Source
`docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine`

## Indicators Required
- Intrabar (1m) volume data via `request.security_lower_tf()` — TradingView only, cannot run server-side
- Volume MA (20-bar) — min 2.0x RVOL to fire
- ATR (14-period) — price stall measurement
- Approach slope (3-bar SMA of close change) — directional context

## Signal Logic

### Core Detection (Two-Bar Wall)
1. Both bars are absorption bars: near-zero delta (|delta/volume| <= 8%) + high RVOL (>= 2.0x)
2. Volume match: total volume within 5% tolerance between the two bars
3. Delta ratio match: within 3% tolerance
4. Buy percentage match: within 3% tolerance
5. Price stall: HL2 moved less than 0.30 ATR between bars
6. Bar range overlap (optional, default on): bars must overlap in price range
7. Only fires on confirmed bar close (no repaint)

### Directional Context
- **PHALANX_BULL**: 3-bar approach slope < 0 (price was falling INTO the wall = support)
- **PHALANX_BEAR**: 3-bar approach slope > 0 (price was rising INTO the wall = resistance)

### Optional Level Filter
Can restrict to only fire near manually specified price levels (disabled by default).

## Risk Management
N/A — Phalanx is a level identification signal, not a trade signal. No entry/stop/target.

## Signal Types
- `PHALANX_BULL` — bullish absorption wall (institutional support)
- `PHALANX_BEAR` — bearish absorption wall (institutional resistance)

## Signal Category
`ORDER_FLOW`

## Webhook Payload
JSON with: ticker, strategy ("AbsorptionWall" migrating to "Phalanx"), direction, signal_type, entry_price (close at wall), timeframe, delta_ratio, buy_pct, buy_vol, sell_vol, total_vol, rvol

## Pipeline Route
`/webhook/tradingview` → `process_phalanx_signal()` → `process_signal_unified()`

Wall level cached in Redis at `phalanx:wall:{TICKER}` with 4-hour TTL for future confluence enrichment.

## TradingView Alert Setup
- Add indicator to 15m chart (or 5m for higher frequency)
- Alert condition: **"Any alert() function call"** — NOT the named alertcondition() entries (those send pipe-delimited format that fails Pydantic validation)
- Webhook URL: `https://pandoras-box-production.up.railway.app/webhook/tradingview`
- Can use watchlist alerts to cover many tickers at once

## Applied To
15-minute charts on liquid equities and ETFs. Best on SPY, QQQ, and high-volume individual names.

## Future Enhancement
Confluence enrichment: when scoring other signals (CTA, Artemis, etc.), check Redis for nearby Phalanx wall levels. If signal entry_price is within 0.5 ATR of a cached wall AND direction matches: +10 confluence bonus. Separate brief.
