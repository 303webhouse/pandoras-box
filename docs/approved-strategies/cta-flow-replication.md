# CTA Flow Replication Strategy

## Overview
Swing trading strategy that replicates CTA (Commodity Trading Advisor) trend-following behavior using a 20/50/120 SMA framework. Scans for entries where price interacts with key moving averages in ways that predict institutional flow.

## Indicators Required
- SMA 20, SMA 50, SMA 120, SMA 200
- ATR (14-period) for stops, targets, and scaling
- ADX (14-period) for trend strength
- Volume (30-day average for ratio calculation)
- VWAP (20-period rolling)

## CTA Zones
Price position relative to the three core SMAs determines the regime:

| Zone | Condition | Bias |
|------|-----------|------|
| **MAX_LONG** | Price > SMA 20 > SMA 50 > SMA 120 | BULLISH |
| **DE_LEVERAGING** | Price < SMA 20, Price >= SMA 50 | NEUTRAL |
| **WATERFALL** | Price < SMA 50 | BEARISH |
| **CAPITULATION** | SMA 20 < SMA 120 | BEARISH |
| **TRANSITION** | Mixed alignment | NEUTRAL |

---

## Signal Types (9 total)

### HIGH_CONVICTION Category

#### 1. GOLDEN_TOUCH (LONG)
First touch of 120 SMA after an extended rally. Rare, highest-conviction setup.
- Price must have been above 120 SMA for 30+ days
- Current price within 2% of 120 SMA (touching/testing)
- Correction of 5-8% from recent high
- Volume at touch candle >= 2.0x average (confirmation of institutional interest)
- Volume >= 1.5x average in session
- **Stop:** 0.5 ATR below 120 SMA
- **T1:** Midpoint to T2 or nearest SMA resistance
- **T2:** ATR-based per zone profile

#### 2. TWO_CLOSE_VOLUME (LONG)
Confirmed breakout above 50 SMA with volume.
- Price closed above 50 SMA for 2 consecutive days (was below before)
- Volume >= 1.5x 30-day average
- **Stop:** 0.5 ATR below 50 SMA
- **T1/T2:** ATR-based per zone profile

### TREND_FOLLOWING Category

#### 3. PULLBACK_ENTRY (LONG)
Pullback to 20 SMA in Max Long zone.
- Zone must be MAX_LONG
- Price pulled back to within 1% of 20 SMA
- Volume >= 1.5x average
- **Stop:** 0.5 ATR below 20 SMA
- **T1/T2:** ATR-based per zone profile

#### 4. ZONE_UPGRADE (context only)
Zone transition to a more bullish state. Not a standalone signal — adds context to other signals on the same ticker.

### MEAN_REVERSION Category

#### 5. TRAPPED_SHORTS (LONG)
Short squeeze setup where shorts are trapped.
- ADX > 25 (strong trend required)
- Price above VWAP 20 and SMA 20
- Short interest or volume pattern suggesting trapped sellers
- **Stop:** 0.5 ATR below VWAP or 20 SMA
- **T1/T2:** ATR-based per zone profile

#### 6. TRAPPED_LONGS (SHORT)
Long squeeze where longs are trapped.
- ADX > 25 (strong trend required)
- Price below VWAP 20 and SMA 20
- **Stop:** 0.5 ATR above VWAP or 20 SMA
- **T1/T2:** ATR-based per zone profile

### BREAKDOWN Category

#### 7. BEARISH_BREAKDOWN (SHORT)
Price breaks below key support with volume confirmation.
- Price breaks below 50 SMA or 120 SMA
- Volume confirms the break
- **Stop:** 0.5 ATR above broken SMA level
- **T1/T2:** ATR-based per zone profile

#### 8. DEATH_CROSS (FILTER)
50 SMA crosses below 200 SMA. Reframed as a "no new longs" filter rather than a standalone short signal. When active, suppresses all LONG signals on the ticker.

### REVERSAL Category

#### 9. RESISTANCE_REJECTION (SHORT)
Price rejected at major SMA resistance.
- Price tests SMA 50 or SMA 120 from below and fails
- Bearish candle pattern at the level
- **Stop:** 0.5 ATR above the resistance SMA
- **T1/T2:** ATR-based per zone profile

---

## Risk Management

### Stops
All stops use a 0.5 ATR buffer beyond the anchor level (SMA or structure).

### R:R Profiles
Target multipliers are zone-dependent (configured in `config/signal_profiles.py`):
- Higher R:R in favorable zones (MAX_LONG for longs)
- Lower targets in adverse zones

### R:R Warning
Signals with R:R < 2.0:1 are flagged with `rr_warning` and `filtered_low_rr = True`. These are informational flags — the signal is still emitted but downstream consumers can filter or deprioritize.

### Invalidation Levels
Each signal includes an `invalidation_level` — a price where the thesis breaks. Separate from the stop loss; this is a structural level that negates the setup entirely.

---

## Signal Context Fields

Every signal includes:

| Field | Source | Description |
|-------|--------|-------------|
| `sector` | M16 | Sector classification for correlation awareness |
| `tick_bias` | M15 | Current TICK breadth composite bias |
| `tick_aligned` | M15 | Whether signal direction aligns with TICK bias |
| `regime` | M5 | Market regime (TRENDING, RANGE_BOUND, VOLATILE, TRANSITIONAL) |
| `category` | H11 | Signal category (HIGH_CONVICTION, MEAN_REVERSION, etc.) |
| `rr_ratio` | setup | Risk/reward ratio |
| `rr_warning` | H10 | Warning if R:R < 2.0 |
| `confluence` | scorer | Multi-signal confluence on same ticker |
| `bias_alignment` | scorer | How signal aligns with composite bias |

---

## Confluence Scoring
When multiple signals fire on the same ticker in the same direction:
- 2+ aligned signals: +25 priority boost
- Golden Touch + Trapped Shorts: +40 boost ("squeeze into trend")
- Golden Touch + Two-Close Volume: +25 boost ("trend + volume confirmation")
- Conflicting directions (LONG + SHORT): All signals demoted to LOW confidence

---

## Volume Requirements
- General threshold: 1.5x 30-day average
- Golden Touch at touch candle: 2.0x average
- Volume is checked at the signal generation level, not as a post-filter
