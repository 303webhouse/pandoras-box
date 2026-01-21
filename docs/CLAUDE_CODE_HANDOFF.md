# Trading Hub - Claude Code Handoff Document
## Complete Strategy & Implementation Specification

---

# PART 1: EQUITY SWING TRADING (PRIMARY)

## Strategy: CTA Replication

### Core Indicators: 20/50/120 Day SMAs

| Zone | Condition | Bias | Action |
|------|-----------|------|--------|
| **MAX_LONG** | Price > 20/50/120 SMAs | BULLISH | Buy pullbacks to 20 SMA |
| **DE_LEVERAGING** | Price < 20, above 50 | NEUTRAL | Watch 50 SMA, reduce size |
| **WATERFALL** | Price < 50 SMA | BEARISH | Short bias, fade rallies |
| **CAPITULATION** | 20 SMA < 120 SMA | BEARISH | Sell rallies only, no longs |

### Signal Types (Priority Order)

1. **GOLDEN_TOUCH** (Score: 100)
   - First touch of 120 SMA after 50+ days above
   - 5-8% correction from recent high
   - 20 SMA still above 120 (uptrend intact)
   - **Rare but highest probability**

2. **TWO_CLOSE_VOLUME** (Score: 80)
   - 2 consecutive closes above 50 SMA
   - Volume >10% above 30-day average
   - **Primary entry signal**

3. **VOLUME_BREAKOUT** (Score: 60)
   - Price crosses above 50 SMA
   - Volume >10% above 30-day average

4. **PULLBACK_ENTRY** (Score: 50)
   - In MAX_LONG zone
   - Price pulls back to within 1.5% of 20 SMA
   - Bounce confirmed

5. **ZONE_UPGRADE** (Score: 40)
   - Transition to more bullish zone
   - Use as watchlist alert, wait for confirmation

### Risk Management

- **Stop Calculation:** Key SMA - (ATR × 1.5)
- **Target Calculation:** Entry + (Risk × 2.0) for 2:1 R:R
- **Max Daily Loss:** User-configurable
- **Position Sizing:** Based on risk per trade

### Filters (Reject Signals When)

1. **VIX Divergence:** VIX rising + Price rising = FAKE RALLY
2. **Window of Weakness:** Monday-Wednesday after monthly OPEX
3. **Low Volume:** Volume < 30-day average on breakout
4. **Poor R:R:** Calculated R:R < 1.5:1

---

# PART 2: BTC/CRYPTO INTRADAY (SECONDARY)

## Key Horizontal Levels Framework

### Session-Based Levels (Auto-calculate daily)
| Level | Definition | Use |
|-------|------------|-----|
| Overnight High | Asia+EU session high | Resistance, range boundary |
| Overnight Low | Asia+EU session low | Support, range boundary |
| Yesterday Close | 4PM ET close | Gap fill trading |
| Today Open | Midnight UTC | Control pivot |
| Yesterday High | Prior day high | Trap zone, liquidity |
| Yesterday Low | Prior day low | Support reference |
| Weekly Open | Monday open | Institutional reference |
| Monthly Open | First of month | Fund performance level |

### Volume Profile Levels
- **POC (Point of Control):** Price with most volume - acts as magnet
- **VAH (Value Area High):** Upper 70% volume boundary
- **VAL (Value Area Low):** Lower 70% volume boundary
- **Poor Highs/Lows:** Single prints - unfinished auctions

### Structural Levels (Weekly 4H Chart Review)
- Swing highs/lows where control shifted
- Confirmed by CVD (Cumulative Volume Delta) shifts
- Mark and track across all timeframes

### Event Levels
- CPI release price
- FOMC reaction levels
- ETF announcement levels
- Major news prints

## BTC Intraday Trading Rules

### DO
- Trade REACTIONS at levels, not the levels themselves
- Wait for resolution before entry
- Look for order flow confirmation (delta flip, volume exhaustion)
- Use multiple level confluence for higher probability

### DO NOT
- Initiate positions directly at major levels
- Trade random lines (they'll look meaningful by coincidence)
- Ignore the three-player dynamic (reversal traders, breakout traders, smart money)

### Three-Player Dynamic at Levels
1. **Reversal Traders:** Expect bounce/rejection
2. **Breakout Traders:** Enter on level breaks
3. **Smart Money:** Traps both groups before real move

### Level Validation Criteria
- Aligns with logical market reference
- Order flow confirmation present
- Clear participant interest (volume, delta)
- Historical significance
- Broader structure alignment

---

# PART 3: IMPLEMENTATION FILES

## PineScript Indicators (TradingView)

### File: `docs/pinescript/cta_context_indicator.pine`
**Purpose:** Always-on context display
- CTA Zone background coloring
- 20/50/120/200 SMAs
- VIX divergence warning
- Distance to key levels table

### File: `docs/pinescript/cta_signals_indicator.pine`
**Purpose:** Entry signal detection
- Golden Touch signals
- Two-Close confirmations
- Volume breakouts
- Pullback entries
- Entry/Stop/Target lines
- Signal table with R:R

### TradingView Webhook Format
```json
{
  "symbol": "{{ticker}}",
  "signal_type": "TWO_CLOSE_VOLUME",
  "direction": "LONG",
  "price": {{close}},
  "time": "{{time}}"
}
```

## Backend Scanner

### File: `backend/scanners/cta_scanner.py`
**Functions:**
- `run_cta_scan()` - Full scan of watchlist + S&P 500
- `analyze_ticker_cta(ticker)` - Detailed single ticker analysis
- `scan_ticker_cta(ticker)` - Get signals for one ticker

**Returns signals with:**
- Entry price
- Stop price  
- Target price
- R:R ratio
- Confidence level
- Context (zone, SMAs, volume)

### File: `backend/api/cta.py`
**Endpoints:**
- `GET /cta/scan` - Run full scan
- `GET /cta/analyze/{ticker}` - Analyze single ticker
- `GET /cta/signals/{ticker}` - Get signals for ticker
- `POST /cta/scan/custom` - Scan custom ticker list

---

# PART 4: FRONTEND REQUIREMENTS

## Signal Card Component

Display each signal as an actionable card:

```
┌─────────────────────────────────────────────────┐
│  🎯 AAPL - LONG                      Score: 85  │
│  Signal: Two-Close + Volume                     │
│  Zone: MAX_LONG                                 │
│  ─────────────────────────────────────────────  │
│  Entry:  $228.50                                │
│  Stop:   $224.00  (-2.0%)                       │
│  Target: $237.50  (+3.9%)                       │
│  R:R:    2.0:1                                  │
│  ─────────────────────────────────────────────  │
│  [✓ TAKE TRADE]  [✕ DISMISS]  [⏸ WATCHLIST]    │
└─────────────────────────────────────────────────┘
```

## Signal Priority Display

Order signals by:
1. Watchlist tickers first
2. Signal priority score (Golden Touch > Two-Close > etc.)
3. Confidence level (HIGH > MEDIUM > LOW)

## Filter Controls

Allow user to filter by:
- Signal type (Golden Touch, Two-Close, etc.)
- Zone (MAX_LONG only, exclude CAPITULATION, etc.)
- Minimum R:R ratio
- Watchlist only vs all

## CTA Zone Dashboard

Display current zone for:
- SPY (market overall)
- User's watchlist tickers

Color-coded:
- Green: MAX_LONG
- Yellow: DE_LEVERAGING  
- Orange: WATERFALL
- Red: CAPITULATION

---

# PART 5: DATA FLOW ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                            │
├─────────────────┬─────────────────┬─────────────────────────────┤
│  TradingView    │  CTA Scanner    │  External (Optional)        │
│  Webhooks       │  (Python)       │  - Unusual Whales           │
│                 │                 │  - SpotGamma                 │
│                 │                 │  - Coinalyze (crypto)        │
└────────┬────────┴────────┬────────┴──────────────┬──────────────┘
         │                 │                       │
         ▼                 ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SIGNAL PROCESSOR                             │
│  1. Deduplicate signals                                         │
│  2. Score by priority                                           │
│  3. Apply filters (VIX, Window of Weakness)                     │
│  4. Calculate Entry/Stop/Target                                 │
│  5. Validate R:R                                                │
│  6. Rank and sort                                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND DISPLAY                             │
│  - Signal cards with action buttons                             │
│  - Zone dashboard                                               │
│  - Filter controls                                              │
│  - Position tracker                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

# PART 6: INTEGRATION CHECKLIST

## Backend Tasks
- [ ] Add `from backend.api.cta import router as cta_router` to main.py
- [ ] Add `app.include_router(cta_router)` to main.py
- [ ] Install dependencies: `yfinance`, `pandas_ta` (if not already)
- [ ] Create `/data/` directory for watchlist storage if missing

## Frontend Tasks
- [ ] Create CTA Signal Card component
- [ ] Create CTA Zone Dashboard component  
- [ ] Add CTA Scanner section to main UI
- [ ] Connect to `/cta/scan` endpoint
- [ ] Add filter controls
- [ ] Add "Run CTA Scan" button

## TradingView Setup
- [ ] Add CTA Context indicator to charts
- [ ] Add CTA Signals indicator to charts
- [ ] Set up webhook alerts to Trading Hub endpoint

---

# PART 7: SIGNAL SCORING REFERENCE

| Signal Type | Base Score | With Volume | Watchlist Bonus |
|-------------|------------|-------------|-----------------|
| GOLDEN_TOUCH | 100 | N/A | +10 |
| TWO_CLOSE_VOLUME | 80 | Required | +10 |
| VOLUME_BREAKOUT | 60 | Required | +10 |
| PULLBACK_ENTRY | 50 | Optional | +10 |
| ZONE_UPGRADE | 40 | Optional | +10 |

**Confidence Levels:**
- HIGH: All criteria met + volume confirmed
- MEDIUM: Most criteria met
- LOW: Marginal setup, use smaller size

---

# PART 8: TESTING CHECKLIST

## Equity Swing Trading
- [ ] CTA zones calculate correctly for SPY
- [ ] Golden Touch detects on historical data (rare)
- [ ] Two-Close + Volume signals appear after breakouts
- [ ] VIX divergence warning triggers
- [ ] Stop/Target calculations match ATR formula

## BTC Intraday
- [ ] Session levels auto-calculate daily
- [ ] Level display on frontend
- [ ] Level-based alerts working

## Integration
- [ ] Signals flow from scanner to frontend
- [ ] Signal cards display correctly
- [ ] Take Trade / Dismiss actions work
- [ ] Position tracking updates

---

# PART 9: BTC INTRADAY TIME WINDOWS

## Key Trading Sessions (All Times in NY/ET)

| NY Time (EDT) | UTC | What Happens | Why It Matters |
|---------------|-----|--------------|----------------|
| **8pm-9pm Sun-Thu** | 00 UTC | One of the five **highest-vol hours**; Garman-Klass σ spike | Asia session hand-off + perp funding reset |
| **4am-6am** | 08-10 UTC | London cash FX open → depth builds, spreads compress | Good for passive fills / iceberg execution |
| **11am-1pm** | 15-17 UTC | **Peak global volume, vol & illiquidity** | Best window for breakout scalps; slippage risk higher |
| **3pm-4pm** | 19-20 UTC | **ETF fixing window** - 6.7% of all spot BTC volume | Creation/redemption hedging; watch for late-day "basis snap" |
| **Fri 3:55pm-4pm** | 19:55-20:00 UTC | CME "BRRNY" reference-rate calculation; BTC Friday futures expire; ETF NAV set | Micro-spikes in spot and CME basis; beware into the print |

## Session Bias Rules

- **Fade mean-reversion ideas** until after 15-17 UTC volume crest; direction tends to persist during peak cluster
- **Treat 00 UTC Asia open as "reset"**; European flow often unwinds Asia extremes by 08-10 UTC

---

# PART 10: BTC DERIVATIVE BOTTOM-SIGNALS CHECKLIST

## The Comprehensive Framework
*"We are not guessing price; we are identifying the structural exhaustion of sellers and the reset of leverage."*

### Signal 1: 25-Delta Skew - Extreme Negativity
| Signal | Options Skew drops significantly below zero (Puts much more expensive than Calls) |
|--------|-------|
| Mechanic | Market is panic-bidding Puts; dealers must short futures to hedge, exacerbating sell-off |
| Reversal | When skew hits extreme lows, market is fully hedged; dealers buy back hedges creating vanna/charm tailwind |

### Signal 2: Quarterly Basis - Compression to Parity
| Signal | Annualized Futures premium collapses to near 0% (or flips negative) |
|--------|-------|
| Mechanic | In bull market, futures trade at premium (contango) for leverage demand |
| Trigger | Compression toward ~0% confirms speculative longs are washed out, leverage reset |

### Signal 3: Perp Funding - The Negative Flip
| Signal | Funding rates flip from positive to negative across major venues |
|--------|-------|
| Mechanic | Shorts are now paying Longs; crowd is chasing downside |
| Trigger | Creates fuel for short squeeze; no incentive for shorts to hold through grind higher |

### Signal 4: Stablecoin APRs - The Apathy Floor
| Signal | Borrow rates for USDT/USDC collapse to base rate (near 0%) |
|--------|-------|
| Mechanic | DeFi stablecoin borrowing is primarily for levering into risk assets |
| Trigger | Low APRs = apathy, speculative froth gone, no one rushing to leverage up |

### Signal 5: Term Structure - Inversion
| Signal | Near-dated futures trade HIGHER than far-dated futures |
|--------|-------|
| Mechanic | Market willing to pay premium to hedge RIGHT NOW (derivatives yield curve inversion) |
| Trigger | Urgency = forced selling/capitulation; unsustainable, marks end of trend |

### Signal 6: Open Interest (OI) - The Divergence Trap
| Signal | Large OI build-up into bearish price candles (Price Down + OI Up) |
|--------|-------|
| Mechanic | Aggressive shorts opening late OR longs averaging down |
| Trigger | Price tick up = late shorts immediately underwater; "last shoe" about to drop |

### Signal 7: Liquidation Composition - The "80/20" Rule
| Signal | Total liquidation volume dominated by Longs (>80%) |
|--------|-------|
| Mechanic | Bottom cannot form if shorts getting squeezed (choppy turbulence) |
| Trigger | >80% Long liquidations = over-leveraged bulls forcibly ejected from market |

### Signal 8: Spot Orderbook Skew - The Wall of Bids
| Signal | Bid-side liquidity heavily outweighs Ask-side at 1-10% depth |
|--------|-------|
| Mechanic | Derivatives noisy; Spot is truth |
| Trigger | Thicker Bid side = smart money/whales deploying passive capital to catch the knife |

### BONUS: VIX Spike - Macro Confirmation
| Signal | VIX (CBOE Volatility Index) spikes vertically (30+) |
|--------|-------|
| Mechanic | BTC acts as high-beta liquidity sponge; VIX explosion = global margin call |
| Trigger | If signals 1-8 firing while VIX crushing equities = generational opportunity |

## The Cluster Effect (Execution Logic)
**No single metric is a silver bullet. The signal is the CLUSTER.**

### Bottom Checklist:
- [ ] Skew: Extreme Negative (Fear peaked)
- [ ] Funding: Flips Negative (Shorts crowded)
- [ ] OI: Rising into the lows (Trap set)
- [ ] Spot Book: Bid-side dominance (Absorption)
- [ ] Basis: Compressing near 0% (Leverage reset)
- [ ] Stable APRs: Collapse to Base Rate (Apathy)
- [ ] Liqs: >80% Longs (Bulls washed out)
- [ ] Macro: VIX Spiking (Global capitulation)

**THE VERDICT:** When forced sellers (Long Liqs) dump into passive buyers (Spot Book), while dealers hedge (Skew) and funding flips negative... that's a bottom.

---

# PART 11: ETF FLOW STRUCTURE

## Two Markets - Critical Understanding

### Secondary Market (What You See on Screen)
- Where retail trades ETF shares on exchange
- Just trading existing shares
- **Does NOT automatically mean new BTC was bought**

### Primary Market (The "Flows")
- Between ETF and authorized participants/market makers
- Where new ETF shares get created/redeemed
- **This is what people mean by "flows"**

## Creation Process (Positive Flow)
1. Heavy buying pressure in secondary market
2. ETF price trades rich to NAV
3. Market maker sells ETF shares (goes short)
4. MM goes to ETF primary market to create units
5. MM delivers BTC to get newly created ETF shares
6. MM uses shares to flatten short

**Result:** Creation = positive flow, ETF now holds more BTC

## Redemption Process (Negative Flow)
1. Heavy selling in secondary market
2. MM buys ETF shares (goes long)
3. Instead of dumping, MM redeems with ETF
4. MM gives ETF shares, gets back BTC
5. That's a redemption

**Result:** Redemption = negative flow, ETF shrinks

## Critical Insight: Volume ≠ Flows
- 2B traded does NOT mean 2B of BTC was bought
- If Alice buys 100 shares and Bob sells 100 shares = 100 volume, ZERO creation
- ETF only moves when MM inventory gets offside enough
- **Timing quirk:** Creations settle T+1, trades settle T+2 - heavy buying Day 1 may show creation Day 2

---

*Document generated from Ryan's Market Profile + Order Flow educational materials*
*For use with Trading Hub implementation*
