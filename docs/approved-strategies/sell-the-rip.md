# Sell the Rip — Negative Momentum Fade

**Type:** Counter-rally fade (trend continuation, short bias)
**Timeframes:** Daily bars (scanner runs every 5 min during market hours)
**Signal pipeline:** Gatekeeper scored (not pre-qualified — must earn promotion via 3 weeks >55% win rate)
**Signal generation:** Server-side scanner on Railway (`backend/scanners/sell_the_rip_scanner.py`)
**Added:** March 2026

## Overview

Detects short opportunities when stocks in confirmed downtrends (or in sectors under active institutional distribution) bounce into resistance and get rejected. Fades relief rallies that run out of buyers at predictable technical levels (20 EMA, VWAP).

Two scan modes:
- **Confirmed Downtrend** — Stock structurally broken down, bouncing into overhead resistance
- **Early Detection** — Stock not yet fully broken, but its sector is in active distribution relative to SPY

## Sector Relative Strength Layer

A daily pre-market job (`backend/scanners/sector_rs.py`) computes rolling 10-day and 20-day returns of 11 sector ETFs (XLK, XLF, XLE, XLV, XLI, XLP, XLY, XLU, XLRE, XLC, XLB) minus SPY returns. Results cached to Redis with 18h TTL.

**Classifications:**
- `ACTIVE_DISTRIBUTION` — Both 10d and 20d RS < -1.0% (institutional money leaving the sector)
- `POTENTIAL_ROTATION` — Either 10d or 20d RS < -0.5%
- `NEUTRAL` — Neither threshold met
- `SECTOR_STRENGTH` — Both 10d and 20d RS > +1.0%

Ticker-to-sector mapping lives in `backend/config/sectors.py`.

If Redis data is stale (>18h), scanner falls back to confirmed-downtrend-only mode (no early detection, no sector scoring).

## Scan Logic

### Mode 1: Confirmed Downtrend

**Preconditions (all must be true):**
1. Price < 50 SMA
2. 20 EMA < 50 SMA (trend structure confirmed)
3. ADX ≥ 20
4. -DI > +DI (bearish directional bias)
5. RSI < 55 (bounce is weak)

**Triggers:**

| Signal Type | Trigger | Base Score |
|-------------|---------|------------|
| `SELL_RIP_EMA` | Price touched 20 EMA in last 3 bars, current bar closing below EMA with bearish candle or volume exhaustion | 45 |
| `SELL_RIP_VWAP` | Price touched VWAP in last 3 bars, current bar closing below VWAP (must also be below 20 EMA) | 48 |

### Mode 2: Early Detection

**Preconditions (all must be true):**
1. Sector = `ACTIVE_DISTRIBUTION`
2. ADX ≥ 15 (relaxed)
3. -DI > +DI
4. RSI < 55
5. Price below 20 EMA (may still be above 50 SMA)

| Signal Type | Trigger | Base Score |
|-------------|---------|------------|
| `SELL_RIP_EARLY` | Same EMA rejection as Trigger A above | 35 |

### Confirmation Requirements

Bearish candle: close < open AND one of:
- Close in bottom 40% of bar range
- Current volume < 75% of 5-bar average (buying exhaustion)

## Risk Management

### Stop Loss
Above the bounce high + 0.2 ATR buffer

### Targets
- **T1:** Prior swing low or 1.5R
- **T2:** 2.5R or next major support

### Time Stop
3 trading days. If price has not broken below the signal bar low within 3 bars, exit at market. Prevents theta bleed on stalled trades.

## Options Setup (Convexity-First Design)

The scanner outputs options-specific fields for put debit spreads:

- **Expected move:** Distance from entry to prior swing low (20-bar lookback)
- **Suggested spread width:** $2.50 / $5.00 / $10.00 based on expected move
- **DTE guidance:** 14-21 DTE sweet spot
- **Convexity grade:** A/B/C based on sector RS, volume exhaustion, ADX strength, expected move vs spread width

### Convexity Grades

| Grade | Criteria | Action |
|-------|----------|--------|
| A | Sector ACTIVE_DISTRIBUTION, vol ratio < 0.70, ADX ≥ 25, expected move ≥ spread width | Prioritize |
| B | Sector ACTIVE_DISTRIBUTION or POTENTIAL_ROTATION, vol ratio < 0.80, ADX ≥ 20, expected move ≥ 70% of spread width | Acceptable |
| C | Sector NEUTRAL/STRONG, vol ratio ≥ 0.80, ADX < 20, expected move < 70% of spread width | Consider skipping |

### VIX Warning
When VIX > 30, embed displays warning that the short leg of a put debit spread offsets vega gains — consider narrower spread or single-leg put.

## Scoring

Base scores: `SELL_RIP_EMA` = 45, `SELL_RIP_VWAP` = 48, `SELL_RIP_EARLY` = 35

**Modifiers:**

| Category | Condition | Modifier |
|----------|-----------|----------|
| Sector RS | ACTIVE_DISTRIBUTION | +10 |
| Sector RS | POTENTIAL_ROTATION | +5 |
| Sector RS | SECTOR_STRENGTH | -10 |
| Volume | Ratio < 0.65 | +5 |
| Volume | Ratio < 0.75 | +3 |
| ADX | ≥ 30 | +5 |
| ADX | ≥ 25 | +3 |
| Confluence | Holy Grail short within 30 min | +8 |

## Filters

| Filter | Value | Rationale |
|--------|-------|-----------|
| Min avg volume (50d) | 500,000 | Skip illiquid names |
| Min price | $10.00 | Skip penny stocks |
| Max VIX | 45 | Too chaotic above 45 |
| Earnings proximity | 3 days | Bounce could be legitimate repricing |
| Min ADX | 15 | No signal in trendless markets |
| Max RSI | 55 | Bounce has real momentum above 55 |
| Bias alignment | URSA MINOR or stronger | Don't short in bullish regimes |

## Deduplication with Holy Grail

When both Sell the Rip and Holy Grail short fire on the same ticker within 30 minutes:
- First signal emits normally
- Second signal merges as confluence boost (+8 to gatekeeper score) instead of duplicate committee run
- Metadata tagged: `"confluence": "sell_rip_confirms"` or `"confluence": "holy_grail_confirms"`

## Signal Payload

```json
{
    "ticker": "KKR",
    "strategy": "sell_the_rip",
    "signal_type": "SELL_RIP_EMA",
    "direction": "SHORT",
    "entry_price": 90.32,
    "stop_loss": 93.15,
    "target_1": 87.50,
    "target_2": 85.00,
    "adx": 22.5,
    "rsi": 48.3,
    "atr": 2.15,
    "volume_ratio": 0.68,
    "sector_etf": "XLF",
    "sector_rs_10d": -2.3,
    "sector_rs_20d": -4.1,
    "sector_classification": "ACTIVE_DISTRIBUTION",
    "scan_mode": "confirmed",
    "confluence_holy_grail": false,
    "timeframe": "daily",
    "expected_move": 5.80,
    "suggested_spread_width": 5.0,
    "suggested_dte_min": 14,
    "suggested_dte_max": 21,
    "time_stop_bars": 3,
    "time_stop_date": "2026-03-13",
    "convexity_grade": "A"
}
```

## Pipeline Route

`sell_the_rip_scanner.py` (every 5 min) → `POST /webhook/internal` → `process_signal_unified()` → gatekeeper scoring → Discord signal embed (if score passes threshold)

## Key Files

| File | Purpose |
|------|---------|
| `backend/scanners/sector_rs.py` | Daily sector RS computation → Redis |
| `backend/scanners/sell_the_rip_scanner.py` | Main scanner (confirmed + early detection modes) |
| `backend/config/sectors.py` | Ticker → sector ETF mapping |
| `backend/scoring/trade_ideas_scorer.py` | Scoring with sector/volume/ADX/confluence modifiers |

## V1.1 Planned (post 3-week evaluation)

- IV Rank filter + display (Polygon options API)
- Strike-level suggestions with estimated debit
- Spread debit % warning (>50% of width = low convexity)
- Options volume liquidity filter (<500 contracts/day = skip)
- Promotion to pre-qualified if win rate >55%
