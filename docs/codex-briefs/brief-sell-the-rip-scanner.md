# Brief: Sell the Rip Scanner v1 (with Sector Rotation Layer)

**Priority:** Phase 1 — New strategy addition
**Target:** Railway backend (`backend/scanners/`)
**Estimated time:** 3-4 hours
**Source:** Trading Committee strategy evaluation (March 10, 2026)
**Repo:** `303webhouse/pandoras-box` (branch: `main`)

---

## Overview

Build a server-side scanner that detects short opportunities when stocks in confirmed downtrends (or in sectors under active institutional distribution) bounce into resistance and get rejected. This is the "sell the rip" pattern — fading relief rallies that run out of buyers at predictable technical levels.

The scanner has two modes:
1. **Confirmed Downtrend** — Stock is below 50 SMA, 20 EMA < 50 SMA, ADX ≥ 20. Triggers on EMA/VWAP rejection.
2. **Early Detection** — Stock may still be above 50 SMA, but its sector ETF is in active distribution relative to SPY. Triggers on 20 EMA rejection with relaxed ADX (≥ 15). Lower base score.

A sector relative strength (RS) layer tracks rolling 10-day and 20-day returns of sector ETFs vs SPY to detect institutional rotation. This is computed daily pre-market and cached in Redis.

---

## Architecture

Two new files + two modifications:

### New Files

#### 1. `backend/scanners/sector_rs.py` (~80 lines)

Daily pre-market job that computes sector relative strength scores.

**Data source:** yfinance — pulls 25 trading days of daily close prices for SPY + 11 sector ETFs.

**Sector ETFs:**
```python
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLY": "Consumer Discretionary",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
    "XLB": "Materials"
}
```

**Computation:**
```python
def compute_sector_rs():
    # Pull 25 trading days of closes for SPY + all sector ETFs
    # For each sector ETF:
    #   rs_10d = (sector_return_10d - spy_return_10d)
    #   rs_20d = (sector_return_20d - spy_return_20d)
    # Classify:
    #   "ACTIVE_DISTRIBUTION" = rs_10d < -1.0% AND rs_20d < -1.0%
    #   "POTENTIAL_ROTATION"  = rs_10d < -0.5% OR rs_20d < -0.5%
    #   "NEUTRAL"             = neither threshold met
    #   "SECTOR_STRENGTH"     = rs_10d > +1.0% AND rs_20d > +1.0%
    # Write to Redis key "sector_rs:{ETF}" with 18h TTL
    # Also write "sector_rs:updated_at" timestamp
```

**Redis schema:**
```json
{
    "sector_rs:XLK": {
        "rs_10d": -2.3,
        "rs_20d": -4.1,
        "classification": "ACTIVE_DISTRIBUTION"
    },
    "sector_rs:updated_at": "2026-03-10T08:00:00Z"
}
```

**Staleness check:** If `sector_rs:updated_at` is >18h old during a trading day, log warning and scanner falls back to confirmed-downtrend-only mode (skips early detection, skips sector scoring modifiers).

**Scheduling:** Run at 8:00 AM ET (pre-market) via existing cron/scheduler infrastructure on Railway. If yfinance fails, log error and retain previous day's scores (don't overwrite with bad data).

---

#### 2. `backend/scanners/sell_the_rip_scanner.py` (~250 lines)

Modeled on `backend/scanners/cta_scanner.py` architecture. Runs every 5 minutes during market hours (9:35 AM - 3:55 PM ET).

**Scan universe:** Same ticker list as CTA Scanner (~200+ tickers).

**Required data per ticker (from Polygon.io or yfinance fallback):**
- Current price, OHLCV for current and prior 5 bars
- 20 EMA, 50 SMA (pre-computed or calculated from 60 bars of daily data)
- ADX (14-period) with +DI / -DI
- RSI (14-period)
- ATR (14-period)
- VWAP (intraday)
- Volume (current bar + 5-bar average)

**Ticker-to-sector mapping:** Stored in `backend/config/sector_mapping.json`. Simple dict:
```json
{
    "AAPL": "XLK",
    "MSFT": "XLK",
    "JPM": "XLF",
    "KKR": "XLF",
    "XOM": "XLE",
    "NEM": "XLB"
}
```
Updated manually ~quarterly. If ticker not in mapping, skip sector RS scoring (use absolute-only mode for that ticker).

---

### Scan Logic

#### Mode 1: Confirmed Downtrend (base score 45)

All must be true:
1. Price < 50 SMA
2. 20 EMA < 50 SMA (confirms trend structure, not just a dip)
3. ADX ≥ 20
4. -DI > +DI (bearish directional bias)
5. RSI < 55 (bounce is weak — hasn't built real momentum)

Then ONE of these triggers:

**Trigger A — EMA Rejection (`SELL_RIP_EMA`):**
- Price touched or exceeded 20 EMA within last 3 bars (high ≥ EMA × 0.998)
- Current bar closing below 20 EMA
- Bearish candle pattern: close < open (red candle) AND (close is in bottom 40% of the bar's range, OR current volume < 75% of 5-bar average volume — i.e., buying exhaustion)

**Trigger B — VWAP Rejection (`SELL_RIP_VWAP`):**
- Price touched or exceeded VWAP within last 3 bars
- Current bar closing below VWAP
- Same bearish candle / volume exhaustion confirmation as Trigger A
- Additional: price must also be below 20 EMA (VWAP rejection while already below the EMA is the strongest form)

#### Mode 2: Early Detection (base score 35)

All must be true:
1. Sector ETF classification = "ACTIVE_DISTRIBUTION" (both RS windows negative >1%)
2. ADX ≥ 15 (relaxed from 20 — catches trends forming earlier)
3. -DI > +DI
4. RSI < 55
5. Price is below 20 EMA (may still be above 50 SMA)

Trigger: Same EMA rejection logic as Trigger A above.

**Note:** Early detection ONLY fires when sector is in ACTIVE_DISTRIBUTION. POTENTIAL_ROTATION is not sufficient — we need strong evidence of institutional rotation to justify the relaxed criteria.

---

### Deduplication with Holy Grail

Before emitting a signal, check if a Holy Grail short signal was emitted for the same ticker within the last 30 minutes (query Redis signal cache or recent signals from PostgreSQL).

- **If Holy Grail already fired:** Don't emit a separate Sell the Rip signal. Instead, boost the existing Holy Grail signal's gatekeeper score by +8 and append a note to the signal metadata: `"confluence": "sell_rip_confirms"`.
- **If Sell the Rip fires first:** Emit normally. If Holy Grail fires within 30 min after, Holy Grail gets the +8 confluence boost instead.
- **If only Sell the Rip fires (no Holy Grail):** Emit as standalone signal. This covers the cases Holy Grail can't (VWAP rejection, early detection mode, ADX 15-24 range).

---

### Signal Output

```python
signal = {
    "ticker": "KKR",
    "strategy": "sell_the_rip",
    "signal_type": "SELL_RIP_EMA",  # or SELL_RIP_VWAP or SELL_RIP_EARLY
    "direction": "SHORT",
    "entry_price": 90.32,
    "stop_loss": 93.15,        # Above bounce high + 0.2 ATR
    "target_1": 87.50,          # Prior swing low or 1.5R
    "target_2": 85.00,          # 2.5R or next major support
    "adx": 22.5,
    "rsi": 48.3,
    "atr": 2.15,
    "volume_ratio": 0.68,       # Current bar vol / 5-bar avg
    "sector_etf": "XLF",
    "sector_rs_10d": -2.3,
    "sector_rs_20d": -4.1,
    "sector_classification": "ACTIVE_DISTRIBUTION",
    "scan_mode": "confirmed",   # or "early_detection"
    "confluence_holy_grail": false,
    "timeframe": "daily",       # Scanner runs on daily bars
    # Convexity fields
    "expected_move": 5.80,
    "suggested_spread_width": 5.0,
    "suggested_dte_min": 14,
    "suggested_dte_max": 21,
    "time_stop_bars": 3,
    "time_stop_date": "2026-03-13",
    "convexity_grade": "A"
}
```

Route through: `POST /webhook/internal` → `process_signal_unified()` with standard gatekeeper scoring.

---

### Scoring Integration

**File:** `backend/scoring/trade_ideas_scorer.py`

**FIND:**
```python
    # Holy Grail Pullback Continuation (Raschke-style)
    "HOLY_GRAIL": 45,
    "HOLY_GRAIL_1H": 50,
    "HOLY_GRAIL_15M": 40,
```

**INSERT AFTER:**
```python

    # Sell the Rip — Negative momentum fade
    "SELL_RIP_EMA": 45,          # Confirmed downtrend, EMA bounce rejection
    "SELL_RIP_VWAP": 48,         # Confirmed downtrend, VWAP rejection (stronger)
    "SELL_RIP_EARLY": 35,        # Early detection (sector distribution, relaxed criteria)
```

**Scoring modifiers (add to existing modifier logic):**

```python
# Sector RS modifiers for Sell the Rip signals
if signal_type.startswith("SELL_RIP"):
    sector_class = signal.get("sector_classification", "NEUTRAL")
    if sector_class == "ACTIVE_DISTRIBUTION":
        score += 10  # Strong institutional rotation out of sector
    elif sector_class == "POTENTIAL_ROTATION":
        score += 5   # Mild sector weakness
    elif sector_class == "SECTOR_STRENGTH":
        score -= 10  # Sector is strong — this rip might be real

    # Volume exhaustion bonus
    vol_ratio = signal.get("volume_ratio", 1.0)
    if vol_ratio < 0.65:
        score += 5   # Very weak buying on the bounce
    elif vol_ratio < 0.75:
        score += 3

    # ADX strength bonus
    adx = signal.get("adx", 0)
    if adx >= 30:
        score += 5   # Very strong trend
    elif adx >= 25:
        score += 3

    # Holy Grail confluence bonus
    if signal.get("confluence_holy_grail"):
        score += 8
```

---

### Filters (pre-scan, skip these tickers)

```python
SELL_RIP_FILTERS = {
    "min_avg_volume_50d": 500_000,     # Skip illiquid names
    "min_price": 10.0,                  # Skip penny stocks
    "max_vix": 45,                      # Too chaotic above 45
    "earnings_proximity_days": 3,       # Skip if earnings within 3 days
    "min_adx": 15,                      # No signal in trendless markets
    "max_rsi": 55,                      # Bounce has too much momentum above 55
}
```

**Bias engine alignment filter:** Check current bias state from Redis. Only emit signals when bias is URSA MINOR or stronger (URSA MAJOR also qualifies). Skip emission during NEUTRAL, TORO MINOR, TORO MAJOR regimes. This prevents the scanner from generating short signals when the macro picture doesn't support it.

---

### Gatekeeper Routing

**NOT pre-qualified.** Signals go through standard gatekeeper scoring. The scanner must prove its value before earning auto-committee routing.

Add to gatekeeper strategy recognition:

**File:** `/opt/openclaw/workspace/scripts/pivot2_committee.py`

No changes needed for V1. Signals route through Railway gatekeeper scoring. If a signal scores high enough to pass the threshold, it gets posted to Discord with the committee buttons like any other signal. Promotion to `TV_COMMITTEE_STRATEGIES` set (pre-qualified) happens after 3 weeks of quality data showing >55% win rate.

---

### Discord Embed Context

When a Sell the Rip signal reaches the committee, include sector RS data in the embed for Nick's context:

```
📉 SELL THE RIP — KKR (EMA Rejection)
Mode: Confirmed Downtrend | ADX: 22.5 | RSI: 48.3

Sector: XLF (Financials)
  RS vs SPY: -2.3% (10d) / -4.1% (20d)
  Classification: 🔴 ACTIVE DISTRIBUTION

Volume on bounce: 68% of avg (buying exhaustion)
Expected move to swing low: $5.80
Convexity Grade: ⭐ A

📊 Suggested Options Setup:
  $5 wide put spread | 14-21 DTE
  ⏰ Time stop: 3 bars — exit by Mar 13

Entry: $90.32 | Stop: $93.15 | T1: $87.50 | T2: $85.00
```

When VIX > 30, append:
```
⚠️ VIX > 30 — Put debit spread short leg offsets vega gain.
Consider narrower spread or single-leg put for more convexity.
```

This is handled by the existing embed builder in `committee_context.py` — just add the sector RS and convexity fields to the context dict.

---

## Config File

**New file:** `backend/config/sector_mapping.json`

Initial mapping for the full scan universe (~200 tickers). Here's the structure — CC should populate from the existing CTA Scanner ticker list:

```json
{
    "_meta": {
        "description": "Ticker to sector ETF mapping for Sell the Rip scanner",
        "last_updated": "2026-03-10",
        "update_frequency": "quarterly"
    },
    "AAPL": "XLK",
    "MSFT": "XLK",
    "GOOGL": "XLC",
    "AMZN": "XLY",
    "META": "XLC",
    "NVDA": "XLK",
    "JPM": "XLF",
    "KKR": "XLF",
    "BX": "XLF",
    "APO": "XLF",
    "XOM": "XLE",
    "CVX": "XLE",
    "NEM": "XLB",
    "GLD": null,
    "SPY": null
}
```

ETFs (SPY, QQQ, GLD, etc.) map to `null` — they don't belong to a sector, so sector RS scoring is skipped for them. The scanner still evaluates them on absolute criteria.

---

## Convexity Optimization (Options-First Design)

This scanner is designed for options trades, not stock shorts. The following features ensure maximum convexity — defined risk with large upside on put debit spreads.

### Additional Scanner Output Fields

Add these to every signal:

```python
# Convexity fields
"expected_move": 5.80,          # Distance from entry to prior swing low ($)
"suggested_spread_width": 5.0,  # Rounded to nearest standard strike width
"suggested_dte_min": 14,        # Minimum DTE for put debit spread
"suggested_dte_max": 21,        # Maximum DTE (sweet spot for theta balance)
"time_stop_bars": 3,            # Exit if no follow-through in 3 trading days
"time_stop_date": "2026-03-13", # Calculated at signal time
"convexity_grade": "A",         # A/B/C grade (see grading below)
```

### Expected Move Calculation

```python
def calc_expected_move(ticker_data, entry_price):
    # Find prior swing low (lowest low in last 20 bars before the bounce started)
    # Distance = entry_price - swing_low
    # If no clear swing low, fallback to 1.5 * ATR * 2 (expected 2-leg move)
    # suggested_spread_width = round to nearest $2.50 or $5 standard width
    #   If expected_move <= 3.00: suggest $2.50 wide
    #   If expected_move <= 7.50: suggest $5.00 wide
    #   If expected_move > 7.50: suggest $10.00 wide
```

### Convexity Grading (V1 — technical factors only)

Grade based on data the scanner already computes (no options API needed):

```
Grade A (high convexity — prioritize):
  - Sector = ACTIVE_DISTRIBUTION
  - Volume ratio < 0.70 (strong buying exhaustion)
  - ADX ≥ 25 (strong trend)
  - Expected move ≥ suggested spread width

Grade B (moderate convexity — acceptable):
  - Sector = ACTIVE_DISTRIBUTION or POTENTIAL_ROTATION
  - Volume ratio < 0.80
  - ADX ≥ 20
  - Expected move ≥ 70% of suggested spread width

Grade C (low convexity — flag, consider skipping):
  - Sector = NEUTRAL or STRONG
  - Volume ratio ≥ 0.80 (buying not exhausted)
  - ADX < 20
  - Expected move < 70% of suggested spread width
```

Assign grade based on best-fit (majority of criteria). Display in embed with star rating.

### Time Stop

**Critical for preserving capital.** If the rejection doesn't produce follow-through (price below signal bar low) within 3 trading days, exit the spread at market.

Rationale: A bounce that consolidates sideways for 3+ days after the "rejection" may be building a base for reversal, not failing. Theta bleeds 25-30% of a 14-21 DTE spread's extrinsic value in 5 days of sideways action. The time stop cuts losers before theta damage becomes significant.

Include `time_stop_date` in signal output. Display in Discord embed. Log in outcome tracking (Brief 04) whether time stop was triggered.

### VIX-Based Embed Warning

When VIX > 30, append to Discord embed:

```
⚠️ VIX > 30 — Put debit spread short leg offsets vega gain.
Consider narrower spread or single-leg put for more convexity.
```

No scanner logic change — just a conditional line in the embed builder based on current VIX from Redis cache.

---

## Files Changed Summary

| File | Action | Location | Est. Lines |
|------|--------|----------|------------|
| `backend/scanners/sector_rs.py` | **NEW** | Railway (auto-deploy) | ~80 |
| `backend/scanners/sell_the_rip_scanner.py` | **NEW** | Railway (auto-deploy) | ~250 |
| `backend/config/sector_mapping.json` | **NEW** | Railway (auto-deploy) | ~200 |
| `backend/scoring/trade_ideas_scorer.py` | MODIFY | Railway (auto-deploy) | ~30 added |
| `docs/approved-strategies/sell-the-rip.md` | **NEW** | Repo (docs only) | ~100 |

---

## Verification Steps

1. **Sector RS:** Run `sector_rs.py` manually. Confirm Redis keys populated with reasonable values. Check that XLE has positive RS (energy is strong right now) and XLK/XLF have negative RS.

2. **Scanner dry run:** Run `sell_the_rip_scanner.py` once during market hours. Log output should show which tickers were scanned, which passed filters, and which (if any) triggered signals. In current crisis regime, expect 5-15 signals across the universe.

3. **Scoring:** Submit a test signal via internal webhook. Confirm signal_type is recognized and score falls in expected range (35-70 depending on modifiers).

4. **Dedup:** Manually trigger a Holy Grail short and Sell the Rip EMA signal on the same ticker within 30 min. Confirm only one signal passes through with the +8 confluence boost.

5. **Bias filter:** Set bias to TORO MINOR via Redis override. Run scanner. Confirm zero signals emitted.

6. **Staleness fallback:** Delete `sector_rs:updated_at` from Redis. Run scanner. Confirm it operates in absolute-only mode (no early detection signals, no sector scoring modifiers) and logs a warning.

---

## Strategy Documentation

After build, create `docs/approved-strategies/sell-the-rip.md` with the standard format:
- Core logic, entry/stop/target rules
- Signal types and scoring
- Webhook payload schema
- Pipeline route
- Sector RS integration details
- Filters and bias alignment requirements

---

## V1.1 Scope (post-launch, ~2 weeks)

After base scanner proves the pattern:

- **IVR filter + display:** Add IV Rank from Polygon options API. Soft filter at IVR < 50. Display in embed.
- **Options chain integration:** Pull nearest ATM put bid/ask from Polygon. Suggest specific strikes and estimate spread debit.
- **Spread debit % warning:** If estimated debit > 50% of spread width, flag in embed: "Convexity is low — consider waiting."
- **Options volume liquidity filter:** Skip tickers where ATM put volume < 500 contracts/day.
- **Strike-level embed:** Full "Buy $90P / Sell $85P, ~$1.80 debit, 1.78:1 R:R" in the embed.

---

## What's NOT in V1

- **Support/resistance detection** — too subjective to automate cleanly. Add in V2 after base pattern proves itself.
- **Individual stock RS vs sector** — V2 optimization. Sector-level RS is sufficient for V1.
- **Bull-side rotation signals** — the sector RS data supports it, but scope V1 to short-only.
- **Pre-qualification** — scanner must earn its way to auto-committee routing via 3 weeks of quality data.
- **Intraday timeframes** — V1 scans daily bars. 15m/1H intraday scanning is V2 scope.
- **Options chain API calls** — V1.1 scope. V1 uses technical data only for convexity grading.
