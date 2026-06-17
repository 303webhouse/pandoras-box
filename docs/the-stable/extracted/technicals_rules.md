# TECHNICALS Agent — Extracted Rules & Frameworks

> **Purpose:** Consolidated technical analysis rules, frameworks, and actionable guidelines extracted from all education documents in `docs/the-stable/`. Designed as the knowledge base for the TECHNICALS agent — the pure technical analysis expert on the AI trading committee.
>
> **Source Documents:** 12 HTML files, 2 TXT files, 2 DOCX files, ~36 PNG page scans across 9 directories/standalone images.
>
> **Note:** Two PDF files (Flow Playbook Intraday.pdf, CTA Strategy Replication Cheat Sheet.pdf) could not be read due to environment limitations and are not reflected here.

---

## Table of Contents

1. [VWAP Trading Rules & Setups](#1-vwap-trading-rules--setups)
2. [Support/Resistance Methodology](#2-supportresistance-methodology)
3. [Moving Average Systems (EMA/SMA/RVWAP Rules)](#3-moving-average-systems-emasma-rvwap-rules)
4. [Volume Analysis Framework](#4-volume-analysis-framework)
5. [Indicator Rules (RSI, MACD, Bollinger, etc.)](#5-indicator-rules-rsi-macd-bollinger-etc)
6. [Chart Pattern Assessment](#6-chart-pattern-assessment)
7. [Market Microstructure & Time-of-Day Rules](#7-market-microstructure--time-of-day-rules)
8. [Entry/Exit Timing Rules](#8-entryexit-timing-rules)
9. [Scalping Reference Levels](#9-scalping-reference-levels)
10. [Flow-Confirmed Technical Setups](#10-flow-confirmed-technical-setups)
11. [CTA/Systematic Strategy Replication Rules](#11-ctasystematic-strategy-replication-rules)
12. [Bottom/Top Signal Checklists](#12-bottomtop-signal-checklists)

---

## 1. VWAP Trading Rules & Setups

### Core VWAP Framework

- **VWAP is the institutional fair-value anchor.** It represents the average price paid by all participants weighted by volume. Price above VWAP = buyers in control; price below = sellers in control. *[Source: vwap_trading_guide.html]*

- **Standard Deviation Bands define trade zones:**
  - **Balance Zone (within +/-0.3 SD of VWAP):** This is the NO-TRADE ZONE. Price is in equilibrium; no directional edge exists. Do not initiate positions here. *[Source: vwap_trading_guide.html]*
  - **Expansion Zone (+/-1 SD):** Directional momentum is building. This is where breakout/trend trades initiate. A decisive move through +/-1 SD with volume confirms directional conviction. *[Source: vwap_trading_guide.html]*
  - **Extreme/Reversion Zone (+/-2 SD):** High-probability mean-reversion territory. Price at +/-2 SD is statistically extended; fade back toward VWAP. This is the primary VWAP reversion setup. *[Source: vwap_trading_guide.html]*

- **VWAP Mean Reversion Strategy (Crude Oil validated):** Enter at +/-2 SD from VWAP, target VWAP touch. Historical win rate: ~70%. Risk/reward: 1:1. Stop: beyond the 2 SD band. *[Source: comprehensive_crude_oil_guide.html]*

- **Position sizing is inverse to VWAP proximity.** The closer price is to VWAP, the smaller the position (less edge). The further from VWAP (toward 2 SD), the larger the position (more edge). *[Source: vwap_trading_guide.html]*

### Multi-Timeframe VWAP

- **Layer VWAP across timeframes:** Use weekly VWAP for swing context, daily VWAP for session bias, and session-based VWAP for intraday execution. Confluence of multiple VWAP levels at the same price creates high-conviction zones. *[Source: vwap_trading_guide.html]*

- **Rolling VWAP periods:** 2-day (ultra-short-term flow), 3-day (short-term), 7-day (weekly equivalent), 30-day (monthly anchor). These supplement the standard session VWAP. *[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt]*

- **Pre-market VWAP protocol:**
  1. Mark prior session's VWAP close and its SD bands on the chart.
  2. Assess overnight/pre-market VWAP position relative to prior session.
  3. Identify the no-trade zone (within +/-0.3 SD of developing VWAP).
  4. Plan entries only at SD band levels or beyond.
  *[Source: vwap_trading_guide.html]*

### VWAP Interaction Rules

- **Gap opens relative to VWAP:** If price gaps above prior VWAP, the prior VWAP becomes support; if below, it becomes resistance. The first retest of prior VWAP after a gap is a high-probability trade. *[Source: vwap_trading_guide.html]*

- **VWAP slope matters:** A flat VWAP indicates balance/chop (avoid directional trades). A sloping VWAP confirms directional bias (trade in the direction of the slope). *[Source: vwap_trading_guide.html]*

- **Volume-weighted confirmation:** VWAP tests with declining volume are weak (likely to break). VWAP tests with increasing volume are strong (likely to hold). Always confirm VWAP levels with volume context. *[Source: vwap_trading_guide.html]*

### VWAP for Specific Assets

- **Crude Oil VWAP:** VWAP mean reversion at +/-2 SD is the highest-probability crude setup. Combine with term structure context (backwardation = bullish bias, contango = bearish bias). *[Source: comprehensive_crude_oil_guide.html]*

- **Gold VWAP:** Gold trades around VWAP during consolidation phases. Use VWAP reversion after event-driven extensions (CPI, NFP, FOMC). *[Source: gold-trading-guide.html]*

- **Bitcoin VWAP:** Session-based VWAP is critical due to 24/7 trading. Use the 00:00 UTC reset as the daily VWAP anchor. VWAP deviations are wider in crypto due to higher volatility. *[Source: comprehensive_btc_levels_guide.html]*

---

## 2. Support/Resistance Methodology

### Level Hierarchy (Priority Order)

1. **Session-Based Levels (highest priority for intraday):**
   - Yesterday's high, low, and close
   - Overnight high and low
   - Weekly open and monthly open
   - Prior session's VWAP close
   *[Source: comprehensive_btc_levels_guide.html]*

2. **Volume Profile Levels:**
   - Point of Control (POC): highest volume node; acts as magnet and equilibrium
   - Value Area High (VAH): upper boundary of 70% volume; resistance in downtrends, support in uptrends
   - Value Area Low (VAL): lower boundary of 70% volume; support in downtrends, resistance in uptrends
   - Poor highs/lows: single-print extremes with no volume buildup; vulnerable to revisit
   - High Volume Nodes (HVN): areas of acceptance; price tends to consolidate here
   - Low Volume Nodes (LVN): areas of rejection; price tends to move quickly through these
   *[Source: comprehensive_btc_levels_guide.html, How Price Moves.html]*

3. **Structural Levels:**
   - Swing highs and swing lows on the daily/4H timeframe
   - Round psychological numbers ($50K, $60K, etc.)
   - Multi-touch trendlines (minimum 3 touches)
   *[Source: comprehensive_btc_levels_guide.html]*

4. **Event-Driven Levels:**
   - Pre-event range boundaries (before CPI, FOMC, etc.)
   - Post-event equilibrium (new range established after event)
   - Liquidation cluster levels (derived from OI and leverage data)
   *[Source: comprehensive_btc_levels_guide.html, Trading the News PNGs]*

### Level Validation Rules

- **A level is valid only when it aligns with a logical reference point AND has order flow confirmation AND volume/delta support.** All three conditions must be present. A naked horizontal line without volume profile or flow context is not a tradeable level. *[Source: comprehensive_btc_levels_guide.html]*

- **Never initiate positions directly at major levels.** Wait for price to interact with the level, observe the resolution (break or hold), then trade the pullback or reclaim. The first touch of a level is for observation, not entry. *[Source: comprehensive_btc_levels_guide.html]*

- **Three-player dynamic at every level:**
  1. Reversal traders: positioned for the level to hold (fade the move)
  2. Breakout traders: positioned for the level to break (trade momentum)
  3. Smart money: watching both groups to exploit whichever side gets trapped
  - Identify which group is likely to get trapped. Trade with the group that will benefit from the trap. *[Source: comprehensive_btc_levels_guide.html]*

- **Stop placement rule:** Place stops beyond obvious levels to account for manipulation/stop hunts. If the "obvious" stop is at the level itself, place yours beyond the next structural reference. The market hunts the obvious stops. *[Source: comprehensive_btc_levels_guide.html]*

### The "High-Rise" Model for Price Levels

- **Floors = bid limits** (support): clusters of resting buy orders that halt downward movement.
- **Ceilings = ask limits** (resistance): clusters of resting sell orders that cap upward movement.
- **Walls = icebergs**: large hidden orders that absorb flow without appearing on the book.
- **Vacant floors = liquidity vacuums**: gaps in the order book where price will travel rapidly. These are the zones between support and resistance where there is nothing to slow price down.
*[Source: How Price Moves.html]*

### Level Freshness and Decay

- **First touch of a level is the strongest.** Each subsequent touch weakens the level as resting orders get absorbed. By the 3rd-4th touch, expect the level to break. *[Source: comprehensive_btc_levels_guide.html]*

- **Stale levels lose relevance.** A level from 3+ months ago with no recent interaction has diminished validity. Prioritize recent (within 1-2 weeks) levels for intraday trading. *[Source: comprehensive_btc_levels_guide.html]*

---

## 3. Moving Average Systems (EMA/SMA/RVWAP Rules)

### Standard Moving Average Setup

The standard indicator system uses three tiers of moving averages:

**EMAs (Exponential Moving Averages) — Short-term/momentum:**
- **EMA 9:** Ultra-short-term momentum. Used for scalp entries and exits. Price above EMA 9 = immediate bullish momentum. *[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt]*
- **EMA 20:** Short-term trend. The primary trend filter for intraday trades. Price above EMA 20 = short-term bullish; below = bearish. *[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt]*
- **EMA 55:** Medium-term momentum bridge. Used less frequently; disabled by default. *[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt]*

**SMAs (Simple Moving Averages) — Structural/positional:**
- **SMA 50:** Intermediate-term trend. Widely watched institutional level. Price below SMA 50 = intermediate downtrend confirmed. *[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt, comprehensive_crude_oil_guide.html]*
- **SMA 120:** Medium-to-long-term trend. Approximates the 6-month moving average. *[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt]*
- **SMA 200:** Long-term trend. The single most important trend filter. Price above SMA 200 = secular uptrend; below = secular downtrend. Institutional allocation decisions reference this level. *[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt, comprehensive_crude_oil_guide.html]*

**Rolling VWAPs — Volume-weighted trend anchors:**
- **2-Day RVWAP:** Ultra-short flow anchor (captures last 2 sessions of volume-weighted price)
- **3-Day RVWAP:** Short-term flow anchor
- **7-Day RVWAP:** Weekly flow equivalent
- **30-Day RVWAP:** Monthly flow anchor; analogous to institutional cost basis over the month
*[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt]*

### CTA Three-Speed MA System

- **20 SMA ("Gas Pedal" — Green):** Fast trend signal. Price above 20 SMA = CTAs adding longs. Break below = first warning. *[Source: CTA Flow Replicator PNG]*
- **50 SMA ("Brake" — Orange):** Medium trend. Break below 50 SMA = CTA selling starts in earnest. This is the critical threshold. *[Source: CTA Flow Replicator PNG]*
- **120 SMA ("Floor" — Red):** Slow trend/structural support. Break below 120 SMA = full CTA short positioning likely. *[Source: CTA Flow Replicator PNG]*

**CTA Zone Rules:**
- **Above all three SMAs (Green Zone):** Safe to hold longs and buy dips. CTAs are providing long flow support. *[Source: CTA Flow Replicator PNG]*
- **Between 20 and 50 SMA (Yellow Zone):** Trimming positions, raising cash. Momentum fading. *[Source: CTA Flow Replicator PNG]*
- **Between 50 and 120 SMA (Red Zone):** Active shorting/hedging zone. CTAs are sellers. *[Source: CTA Flow Replicator PNG]*
- **Below all three SMAs (Grey Zone):** Maximum bearish positioning. High volatility regime. *[Source: CTA Flow Replicator PNG]*

### Moving Average Cross Rules

- **EMA 9 crossing above EMA 20:** Short-term bullish momentum signal. Useful for entry timing in the direction of the larger trend. *[Source: Ryans AIO MAs and RVWAP Joint Indicator.txt]*
- **Price closing below SMA 50 after being above:** Intermediate trend reversal warning. Reduce position size and tighten stops. *[Source: CTA Flow Replicator PNG, comprehensive_crude_oil_guide.html]*
- **SMA 50 crossing below SMA 200 (Death Cross):** Long-term bearish signal. Historically significant but often lagging; best used as confirmation, not initiation. *[Source: comprehensive_crude_oil_guide.html]*
- **SMA 50 crossing above SMA 200 (Golden Cross):** Long-term bullish signal. Same caveat — lagging but confirming. *[Source: comprehensive_crude_oil_guide.html]*

### MA as Dynamic Support/Resistance

- **In an uptrend:** EMAs 9/20 act as dynamic support for pullback entries. SMA 50 is the "line in the sand" — a close below invalidates the uptrend. *[Source: comprehensive_crude_oil_guide.html]*
- **In a downtrend:** EMAs 9/20 act as dynamic resistance for short entries. SMA 50 is the ceiling. *[Source: comprehensive_crude_oil_guide.html]*
- **SMA 200:** The most significant dynamic level. Extended moves away from SMA 200 tend to revert. The further price is from SMA 200, the higher the reversion probability. *[Source: comprehensive_crude_oil_guide.html]*

---

## 4. Volume Analysis Framework

### Core Volume Principles

- **Volume confirms price.** A price move on increasing volume is genuine; a price move on decreasing volume is suspect and likely to reverse. *[Source: How Price Moves.html, comprehensive_crude_oil_guide.html]*

- **Volume precedes price.** Volume expansion often appears before the price breakout. Watch for volume surges while price is still in a range — this indicates accumulation or distribution. *[Source: How Price Moves.html]*

- **Relative volume (RVOL) is more meaningful than absolute volume.** Compare current volume to the average for that time of day and day of week. RVOL > 2x normal signals institutional participation. *[Source: How Price Moves.html, Flow Trading Crypto PNGs]*

### Volume Profile Analysis

- **Point of Control (POC):** The price level with the highest traded volume in a given period. POC acts as a magnet — price tends to return to POC. It represents fair value for that session. *[Source: comprehensive_btc_levels_guide.html, How Price Moves.html]*

- **Value Area (VA):** The range containing 70% of traded volume.
  - Trading within the VA = balanced/range-bound market.
  - Trading outside the VA = directional/trending market.
  - VA migration (shift of entire VA higher or lower session over session) confirms trend direction.
  *[Source: comprehensive_btc_levels_guide.html]*

- **High Volume Nodes (HVN):** Areas of price acceptance. Price tends to slow down and consolidate at HVNs. They act as support/resistance. *[Source: comprehensive_btc_levels_guide.html]*

- **Low Volume Nodes (LVN):** Areas of price rejection. Price moves quickly through LVNs. They represent levels where participants want to transact quickly (get through fast). LVNs between HVNs create "air pockets" where price can gap/slide rapidly. *[Source: comprehensive_btc_levels_guide.html, How Price Moves.html]*

- **Poor highs/lows:** Session extremes formed by single prints (no volume buildup at the high or low). These are "unfinished business" — the market is likely to revisit and test beyond these levels. *[Source: comprehensive_btc_levels_guide.html]*

### Cumulative Volume Delta (CVD)

- **CVD measures the net difference between buying and selling volume over time.** Rising CVD = buyers dominant; falling CVD = sellers dominant. *[Source: How Price Moves.html, Flow Trading Crypto PNGs]*

- **CVD divergence from price is a high-probability signal:**
  - Price making new highs but CVD declining = buying exhaustion (bearish divergence)
  - Price making new lows but CVD rising = selling exhaustion (bullish divergence)
  *[Source: How Price Moves.html]*

- **CVD persistence vs. spikes:** Favor persistent CVD trends over single-bar spikes. A spike in CVD that immediately reverses is noise. Sustained CVD movement over multiple bars/candles confirms genuine flow. *[Source: Flow Trading Crypto PNGs]*

- **Day-Trader Day signature:** On range-bound days, CVD ends approximately where it started. Buyers and sellers are in balance — the net delta is near zero despite intraday swings. *[Source: ES Scalping Reference Guide PNGs]*

### Volume at Time of Day

- **Volume follows a U-shape pattern in equities:** High volume at open (9:30-10:30 ET), low volume midday (11:00-14:00 ET), high volume at close (15:00-16:00 ET). *[Source: Market Microstructure PNGs]*

- **Crypto volume patterns:**
  - 00:00 UTC (8pm ET): Asia session open + funding reset = highest volatility hour
  - 08:00-10:00 UTC (4-6am ET): London open, depth builds
  - 15:00-17:00 UTC (11am-1pm ET): Peak global volume overlap (US + Europe)
  - 19:00-20:00 UTC (3-4pm ET): ETF fixing window
  *[Source: Bitcoin Intraday Cheat Sheet PNG]*

### Volume Screening Criteria

- **Crypto scalping volume requirements:**
  - 1-day spot volume > $500-800M
  - Order book depth within +/-0.5% of mid-price > $10K
  - Spreads < 4 basis points
  - ATR > 1.5% (sufficient volatility for scalping edge)
  *[Source: Crypto Scalping Considerations PNGs]*

---

## 5. Indicator Rules (RSI, MACD, Bollinger, etc.)

### RSI (Relative Strength Index)

- **Standard overbought/oversold thresholds:** RSI > 70 = overbought (prepare for pullback); RSI < 30 = oversold (prepare for bounce). *[Source: comprehensive_crude_oil_guide.html]*

- **RSI divergence is more reliable than absolute levels:**
  - Price makes higher high + RSI makes lower high = bearish divergence (high probability reversal)
  - Price makes lower low + RSI makes higher low = bullish divergence (high probability reversal)
  *[Source: comprehensive_crude_oil_guide.html]*

- **RSI in trending markets:** In strong trends, RSI can remain overbought/oversold for extended periods. Do not fade a strong trend solely because RSI is extended. Use RSI divergence, not absolute levels, in trending conditions. *[Source: comprehensive_crude_oil_guide.html]*

### Bollinger Bands

- **Standard setup:** 20-period SMA with 2 standard deviation bands. *[Source: comprehensive_crude_oil_guide.html]*

- **Bollinger Band squeeze:** When bands narrow significantly (low volatility), a large directional move is imminent. The squeeze itself does not predict direction — wait for the breakout direction before entering. *[Source: comprehensive_crude_oil_guide.html]*

- **Bollinger Band walk:** In a strong trend, price "walks" along the upper or lower band. This is not a reversion signal — it confirms trend strength. Only fade when price starts pulling back inside the bands with volume confirmation. *[Source: comprehensive_crude_oil_guide.html]*

- **2 SD band touch = reversion candidate.** This aligns with the VWAP +/-2 SD reversion rule. Price touching the 2 SD Bollinger Band has a statistical tendency to revert toward the mean (20 SMA). *[Source: comprehensive_crude_oil_guide.html]*

### MACD

- **MACD histogram expansion:** Increasing histogram bars confirm momentum in the current direction. *[Source: comprehensive_crude_oil_guide.html]*

- **MACD histogram contraction:** Decreasing histogram bars (even while still positive/negative) signal weakening momentum — early warning of potential reversal or consolidation. *[Source: comprehensive_crude_oil_guide.html]*

- **MACD crossover:** Signal line crossover is a lagging but confirming signal. Use it for trend confirmation, not initiation. *[Source: comprehensive_crude_oil_guide.html]*

### Footprint Charts / Order Flow Indicators

- **Footprint absorption:** Large resting orders absorbing aggressive flow without price moving. When aggressive sellers hit a bid level repeatedly and the bid refreshes (absorbs the selling), this is bullish absorption — institutions are buying. Reverse for bearish absorption. *[Source: How Price Moves.html, daily_trading_plan_card.html]*

- **Footprint delta divergence:** When aggressive buying (delta positive) fails to push price higher, or aggressive selling (delta negative) fails to push price lower, the market is absorbing the flow. This is a reversal signal. *[Source: How Price Moves.html, daily_trading_plan_card.html]*

- **Volume climax:** Extremely high volume on a single bar, often with a long wick/tail. This represents exhaustion — the last burst of buying/selling before reversal. Look for volume > 3x average on a single bar with price rejection (wick). *[Source: daily_trading_plan_card.html]*

### Confirmation Trinity

- **DOM (Depth of Market) + Tape (Time & Sales) + Cumulative Delta must agree.** No single order flow indicator is sufficient. All three must point in the same direction for a valid order flow signal:
  - DOM: shows resting order imbalance
  - Tape: shows actual execution flow (who is lifting offers vs. hitting bids)
  - CVD: shows net cumulative flow over time
  *[Source: How Price Moves.html]*

---

## 6. Chart Pattern Assessment

### Pattern Success Rates (Crude Oil Benchmarks)

These are historical success rates for common chart patterns. Use as probability guides, not certainties:

| Pattern | Win Rate | Notes |
|---------|----------|-------|
| Flag/Pennant | ~65% | Continuation pattern; must appear within an existing trend |
| Head & Shoulders | ~55% | Reversal; requires volume confirmation on neckline break |
| Double Top/Bottom | ~60% | Reversal; second touch should have lower volume than first |
| Triangle (sym/asc/desc) | ~58% | Breakout direction determined by prior trend and volume |
| Channel | ~70% | Highest success rate; trade bounces within, breakout for trend |

*[Source: comprehensive_crude_oil_guide.html]*

### Pattern Quality Criteria

- **Volume confirmation is mandatory.** A pattern without volume support is not valid. Breakouts must occur on volume > 1.5x the average volume within the pattern. *[Source: comprehensive_crude_oil_guide.html]*

- **Time symmetry:** The longer a pattern takes to form, the more significant the eventual breakout. A head-and-shoulders forming over 3 weeks is more significant than one forming over 3 hours. *[Source: comprehensive_crude_oil_guide.html]*

- **False breakout identification:** A breakout that immediately reverses back inside the pattern on heavy volume is a "shakeout" — the true move is often in the opposite direction. *[Source: comprehensive_btc_levels_guide.html]*

- **Pattern within pattern:** Higher-timeframe patterns override lower-timeframe patterns. A bullish flag on the 5-minute chart within a bearish head-and-shoulders on the daily chart has lower probability. Always check the higher timeframe context. *[Source: comprehensive_crude_oil_guide.html]*

### Day Types as Patterns

- **High-Volume Trend Day:** Strong directional move on a catalyst. One-directional with minimal pullbacks. Front-month volatility crushes as directional certainty increases. These are "hold and add" days — do not fade. *[Source: ES Scalping Reference Guide PNGs, How Price Moves.html]*

- **Day-Trader Day (Two-Way/Grind):** Range-bound, +/-6-15 points in ES. Multiple failed breakouts. CVD ends near flat. Strategy: fade the extremes, don't chase breaks. *[Source: ES Scalping Reference Guide PNGs]*

- **Low-Range Day:** Very tight range, minimal volume. Typically precedes a high-volatility day. Reduce position size and wait for the range expansion. *[Source: How Price Moves.html]*

- **News-Driven Day:** Characterized by gap + initial volatility burst + range establishment. Trade the range AFTER the dust settles (30-60 min post-event), not during the initial chaos. *[Source: How Price Moves.html, Trading the News PNGs]*

- **Institutional Rebalancing Day:** End-of-month/quarter flows create predictable directional pressure. Large block execution concentrated in 14:30-16:00 ET window. *[Source: How Price Moves.html, Market Microstructure PNGs]*

---

## 7. Market Microstructure & Time-of-Day Rules

### Equity Market Session Timing (US Eastern)

| Session | Time (ET) | % Daily Vol | Characteristics |
|---------|-----------|-------------|-----------------|
| Pre-Market | 04:00-09:30 | ~4% | Spreads 2-10x wider; information-based trading; news digestion |
| US Open | 09:30-10:30 | ~15% | "U-shape" peak; highest volatility; retail + institutional overlap |
| Mid-Day | 10:30-14:30 | ~50%+ | VWAP/TWAP algos dominate; HFT = 70% of exchange trading; lower directional conviction |
| Closing Period | 14:30-16:00 | 15-20% | MOC orders; institutional rebalancing; large block execution preferred venue |
| After Hours | 16:00-21:00 | 3-5% | Thin liquidity; wide spreads; news-driven moves exaggerated |
| Asian Session | 21:00-02:00 | Variable | Global equity exposure; FX-correlated moves |
| European Open | 02:00-04:00 | Variable | "Overnight drift" phenomenon; sets the tone for US open |

*[Source: Market Microstructure PNGs]*

### Crypto Session Timing (UTC / ET)

| Session | Time (UTC) | Time (ET) | Signal |
|---------|-----------|-----------|--------|
| Asia Open + Funding Reset | 00:00 UTC | 8-9pm ET | Highest-vol hours; session hand-off; perp funding reset |
| London FX Open | 08:00-10:00 UTC | 4-6am ET | Depth builds; good for passive fills |
| Peak Global Volume | 15:00-17:00 UTC | 11am-1pm ET | Best for breakout scalps; US + Europe overlap |
| ETF Fixing Window | 19:00-20:00 UTC | 3-4pm ET | 6.7% of spot BTC volume; watch for basis snap |
| CME BRRNY Reference Rate | 19:55-20:00 UTC | 3:55-4pm ET (Fri) | Micro-spikes around CME reference rate calculation |

*[Source: Bitcoin Intraday Cheat Sheet PNG]*

### Crypto Session Bias Rule

- **Fade mean-reversion setups until after the 15:00-17:00 UTC volume crest.** Before peak volume, the market is still establishing direction. After the crest, mean-reversion becomes higher probability as volume declines. *[Source: Bitcoin Intraday Cheat Sheet PNG]*

- **Treat 00:00 UTC Asia session as a "reset."** The Asia open + funding reset creates a natural inflection point. Prior session trends may reverse or accelerate here. Do not carry strong directional conviction through this transition. *[Source: Bitcoin Intraday Cheat Sheet PNG]*

### Spread and Execution Cost Rules

- **Spread costs vary 3-10x across time periods.** Pre-market and after-hours spreads can be 10x wider than regular session. Always factor spread cost into expected profit for time-of-day-dependent trades. *[Source: Market Microstructure PNGs]*

- **Best execution windows:**
  - Large block execution: 14:30-16:00 ET (closing period MOC/TWAP)
  - Intraday liquidity: 09:30-10:30 ET (tightest spreads, deepest book)
  - Information-based trades: 04:00-09:30 ET pre-market (price discovery)
  - Global macro trades: 02:00-04:00 ET (European open)
  *[Source: Market Microstructure PNGs]*

- **Crypto execution:** Use maker/post-only orders on entry to reduce costs from ~$5-8 (taker) to ~$1-3 (maker) per $10K position. In illiquid hours, step down position size. *[Source: Crypto Scalping Considerations PNGs]*

### Algorithmic Dominance

- **HFT represents ~70% of US equity exchange trading during mid-day.** During 10:30-14:30 ET, price action is dominated by algorithmic VWAP/TWAP execution. Directional signals during this window are less reliable. *[Source: Market Microstructure PNGs]*

- **VWAP/TWAP algos compress volatility midday.** These algorithms slice large orders across the session, anchoring price near VWAP. This is why mid-day is typically range-bound — it is mechanically forced to be. *[Source: Market Microstructure PNGs]*

### Crude Oil Session Timing

| Session | % Daily Vol | Volatility |
|---------|-------------|------------|
| Asia | ~15% | Low |
| Europe | ~25% | Medium |
| US Regular | ~40% | High |
| US Close | ~10% | Medium-High |

*[Source: comprehensive_crude_oil_guide.html]*

---

## 8. Entry/Exit Timing Rules

### Entry Trigger Checklist

Before any entry, ALL of the following must be confirmed:

1. **Higher-timeframe level present:** A clear support/resistance level from the daily or 4H chart is nearby. *[Source: daily_trading_plan_card.html]*
2. **Liquidity identified:** Where are the stop clusters? Where will trapped traders exit? *[Source: daily_trading_plan_card.html]*
3. **Regime appropriate:** Is the current market regime (trending/ranging/volatile) compatible with the setup? *[Source: daily_trading_plan_card.html]*
4. **Entry trigger fired:** One of the following specific triggers must occur:
   - Price sweep + close back inside (stop hunt reversal)
   - Footprint absorption at level (institutional buying/selling)
   - Delta divergence (aggressive flow failing to move price)
   - Volume climax (exhaustion spike with rejection wick)
   *[Source: daily_trading_plan_card.html]*

### Position Scaling Rules

**Equity/Futures Scaling:**
- **Initial entry:** 25-40% of intended position. Enter on the first valid signal. *[Source: How Price Moves.html]*
- **Confirmation add:** 30-50% of intended position. Add when the initial thesis is confirmed (price moves in your direction with volume). *[Source: How Price Moves.html]*
- **Momentum add:** 10-25% of final intended position. Add on continued momentum; this is the "runner" portion. *[Source: How Price Moves.html]*

**Alternative Scaling (Crude Oil):**
- Enter 1/3 of intended position at the initial signal.
- Add 1/3 on confirmation (price holds and volume supports).
- Add final 1/3 on pullback to entry/support within the move.
*[Source: comprehensive_crude_oil_guide.html]*

**News Event Scaling:**
- Pre-event: maximum 25% of normal position
- During event: maximum 15% of normal position (reduce exposure)
- Post-event (new range forming): gradually scale to 50%
- New structure confirmed: full 100% position allowed
*[Source: Trading the News PNGs]*

### Exit/Profit-Taking Rules

- **Tiered profit-taking:**
  - Take 33% at first resistance/support (nearest structural level)
  - Take 33% at structural rebuilding level (next significant level)
  - Hold 34% as a runner with trailing stop
  *[Source: How Price Moves.html]*

- **Alternative (Crude Oil):**
  - Take 50% at 1:1 risk/reward (lock in breakeven on the trade)
  - Trail the remaining 50% with a structural stop
  *[Source: comprehensive_crude_oil_guide.html]*

- **VWAP reversion exit:** When entering a VWAP mean-reversion trade at +/-2 SD, the primary target is VWAP itself. Take at least partial profits at VWAP touch. *[Source: vwap_trading_guide.html]*

### Invalidation Rules

- **Break beyond wick extreme:** If price breaks beyond the extreme of the entry candle's wick, the setup is invalidated. Exit immediately. *[Source: daily_trading_plan_card.html]*
- **15-minute time stop:** If the trade has not moved in your favor within 15 minutes of entry, the thesis is likely wrong. Exit or reduce to minimum size. *[Source: daily_trading_plan_card.html]*
- **Context change:** If the macro/regime context changes after entry (e.g., unexpected news, circuit breaker trigger), reassess immediately regardless of P&L. *[Source: daily_trading_plan_card.html]*

### Circuit Breaker Rules (Risk Management)

- **2 consecutive losses = mandatory 30-minute break.** Step away, reassess market conditions, review if the regime has changed. *[Source: daily_trading_plan_card.html]*
- **3 consecutive losses = done for the day.** No more trading. The market is not aligning with your read. Forcing trades after 3 losses leads to tilt and larger drawdowns. *[Source: daily_trading_plan_card.html]*

### Stop Loss Strategies

- **Structural stop:** Place beyond the next structural level past your entry. This gives the trade room to breathe while maintaining a logical invalidation point. *[Source: comprehensive_btc_levels_guide.html]*

- **Volatility-adjusted stop:** During high-volatility events, widen stops proportionally. A normal 0.5% stop may need to be 1-2% during CPI/FOMC. *[Source: Trading the News PNGs]*

- **Time-based stop:** Exit after a predetermined time if the trade hasn't moved. Useful for news trades and scalps. *[Source: Trading the News PNGs, Crypto Scalping Considerations PNGs]*

- **3-bar rule (scalping):** If a scalp hasn't moved in your direction within 3 bars on your execution timeframe, exit. The setup has failed. *[Source: Crypto Scalping Considerations PNGs]*

---

## 9. Scalping Reference Levels

### ES (E-Mini S&P 500) Scalping Reference

- **Contract specs:** $50 per point, $12.50 per tick. Typical daily turnover ~3M contracts. *[Source: ES Scalping Reference Guide PNGs]*

- **Scalping defined:** Trading from one price level to the next clear reference point. Not holding for trend — executing between structural levels. *[Source: ES Scalping Reference Guide PNGs]*

- **Key reference points for ES scalps:**
  - Prior session's POC, VAH, VAL
  - Overnight high/low
  - Yesterday's high/low/close
  - Developing VWAP and SD bands
  - Round numbers (xx00, xx50)
  *[Source: ES Scalping Reference Guide PNGs]*

- **ES session characteristics for scalping:**
  - **Open (8:30-10:30 ET):** High volatility, wide ranges. Best for directional scalps. *[Source: ES Scalping Reference Guide PNGs]*
  - **Mid-Day (10:30-14:00 ET):** Range-bound, grind. Day-Trader Day mechanics dominate. Fade extremes. *[Source: ES Scalping Reference Guide PNGs]*
  - **Close (15:00-16:15 ET):** Institutional flows, MOC. Directional bias returns. *[Source: ES Scalping Reference Guide PNGs]*

- **Day-Trader Day scalp range:** +/-6-15 points in ES. On these days, buy the low of the range, sell the high. Multiple failed breakouts are the norm — fade every breakout attempt. *[Source: ES Scalping Reference Guide PNGs]*

- **Scalper psychology rules:**
  1. Act fast — hesitation costs money
  2. Avoid FOMO — missed trades are not losses
  3. Accept small losses immediately — do not hold and hope
  4. Maintain discipline — follow the system, not your emotions
  *[Source: ES Scalping Reference Guide PNGs]*

### Crypto Scalping Reference

- **Timeframe selection:**
  - 5-15 seconds: Click/tape trading (requires dedicated DOM)
  - 1-5 minutes: Simple DOM scalping (most accessible)
  - 15-second: Latency/arbitrage (requires infrastructure)
  *[Source: Crypto Scalping Considerations PNGs]*

- **Crypto screening for scalp candidates:**
  - 1-day spot volume > $500-800M
  - Depth within +/-0.5% > $10K
  - Spread < 4 bps (basis points)
  - ATR > 1.5%
  *[Source: Crypto Scalping Considerations PNGs]*

- **Cost awareness:** Fixed costs (taker fees) of $5-8 per side on a $10K position. Maker fees ~$1-3. The scalp target must exceed 2x the round-trip cost to be profitable after slippage. *[Source: Crypto Scalping Considerations PNGs]*

- **Crypto scalp risk limits:**
  - Max risk per trade: 0.1-0.4% of capital
  - Consecutive daily risk cap: 3% of capital
  - Hit daily cap = stop trading for the day
  *[Source: Crypto Scalping Considerations PNGs]*

---

## 10. Flow-Confirmed Technical Setups

### Order Flow + Technical Level Confluence

- **The highest-probability trades occur when a technical level aligns with order flow confirmation.** A horizontal support level is just a line on a chart until order flow confirms buyers are actually present. *[Source: How Price Moves.html, comprehensive_btc_levels_guide.html]*

- **Flow confirmation at levels requires:**
  1. Resting bid/ask orders visible on DOM at the level (pre-positioned interest)
  2. Tape showing absorption (large volume transacted without price moving through the level)
  3. CVD showing net buying (at support) or net selling (at resistance) at the level
  *[Source: How Price Moves.html]*

### Crypto Open Interest (OI) Flow Signals

- **OI thresholds for Binance BTC-Perp (single venue):**
  - $250-400M change in OI within 1 hour = worth tracking (notable positioning)
  - $600-800M change in OI within 3 hours = meaningful flow (institutional-scale)
  - $1B+ change in OI = dominant flow day (ignore other signals, follow the flow)
  *[Source: Flow Trading Crypto PNGs]*

- **Global OI thresholds (all venues combined):**
  - $1.5-2.5B change per session = notable
  - $3-4B change per session = high-signal event
  - $5B+ in 24 hours = regime shift (trend-defining event)
  *[Source: Flow Trading Crypto PNGs]*

### OI + Price Confirmation Matrix

| Price | OI | Interpretation |
|-------|-----|----------------|
| Rising | Rising | Fresh longs opening — bullish (genuine buying) |
| Rising | Falling | Short covering — bullish but exhaustible (squeeze, not new demand) |
| Falling | Rising | New shorts opening — bearish (genuine selling). But if CVD diverges, potential trap |
| Falling | Falling | Long liquidation — bearish but exhaustible (forced selling, not new conviction) |

*[Source: Flow Trading Crypto PNGs]*

### Spot-to-Futures Flow Dynamics

- **Spot leads perpetual futures.** When a significant spot buy occurs, perp markets adjust within milliseconds. Monitor spot exchanges (Coinbase, Binance Spot) for the primary signal; perps are the derivative. *[Source: spot_flows_futures_impact.html]*

- **Basis as a flow indicator:** Cash-and-carry basis (futures premium over spot) reflects directional conviction. Expanding basis = growing bullish conviction (longs paying up for leverage). Compressing basis = conviction fading. *[Source: spot_flows_futures_impact.html, BTC Derivative Bottom-Signals PNGs]*

- **Funding rate as positioning gauge:**
  - Positive funding (longs pay shorts): Market crowded long. Potential for long squeeze.
  - Negative funding (shorts pay longs): Market crowded short. Potential for short squeeze.
  - Extreme funding in either direction = crowded trade = contrarian opportunity.
  *[Source: Flow Trading Crypto PNGs, BTC Derivative Bottom-Signals PNGs]*

### ETF Flow Signals (Bitcoin / Gold)

- **ETF volume does not equal ETF flows.** Trading volume on an ETF is secondary market activity. Actual flows are creation/redemption by Authorized Participants (APs). Only creation/redemption data represents genuine new demand/supply. *[Source: Crypto ETF Flow Structure.html]*

- **ETF fixing window (Bitcoin):** The ETF NAV calculation occurs around 19:00-20:00 UTC (3-4pm ET). This represents ~6.7% of daily spot BTC volume concentrated in one hour. Watch for price impacts during this window. *[Source: Bitcoin Intraday Cheat Sheet PNG]*

- **ETF premium/discount:** An ETF trading at a persistent premium to NAV signals excess demand (bullish for the underlying). A persistent discount signals excess supply (bearish). *[Source: Crypto ETF Flow Structure.html]*

### Dealer Gamma Flow

- **Long gamma regime:** Dealers are long gamma (typically when SPX is between strikes with high open interest). Dealers sell rallies and buy dips to hedge → suppresses volatility → mean-reversion strategies work best. *[Source: Price_Insensitive_Flows_Guide.docx, market_positioning_guide.html]*

- **Short gamma regime:** Dealers are short gamma (typically after a large move away from strike clusters). Dealers buy rallies and sell dips to hedge → amplifies volatility → momentum strategies work best. *[Source: Price_Insensitive_Flows_Guide.docx, market_positioning_guide.html]*

- **Gamma flip level (GEX zero):** The price level where dealer gamma exposure flips from long to short. Above this level = long gamma (mean reversion); below = short gamma (momentum/trend). This is one of the most important levels for regime identification. *[Source: Price_Insensitive_Flows_Guide.docx, market_positioning_guide.html]*

### Positioning Analysis Rules

- **"Ask who's trapped before asking if it's cheap."** Before evaluating whether a price is a good entry, identify which participants are offside (losing money) and what their forced actions will be (liquidation, margin calls, hedging adjustments). Trade in the direction that forces the trapped side to exit. *[Source: market_positioning_guide.html, Finding an Edge.txt]*

- **"Value is irrelevant in times of market stress; it's all about positions."** During dislocations, fundamental value does not determine price — forced flows from positioned participants do. Technical levels derived from positioning (liquidation clusters, gamma levels, margin call prices) are more relevant than fundamental fair value. *[Source: Finding an Edge.txt, market_positioning_guide.html]*

- **Key positioning tells:**
  - OI changes (new positions being established)
  - COT data (Commitment of Traders — commercial vs. speculative positioning)
  - Dealer gamma exposure (GEX)
  - Put/call skew (options market directional lean)
  - Funding rate / basis (crypto leverage positioning)
  *[Source: market_positioning_guide.html]*

### Liquidity Vacuum Trading

- **Vacuum identification:** A liquidity vacuum is a zone in the order book with minimal resting orders between two structural levels. Price will travel through this zone rapidly with minimal resistance. *[Source: How Price Moves.html]*

- **Vacuum pullback signature:** Low volume, shrinking delta, price moving quickly. The move itself has low participation — it is the absence of opposing orders, not the presence of aggressive orders, that drives the move. The move stops at the next structural level where resting orders exist. *[Source: How Price Moves.html]*

- **News events create fiscal liquidity vacuums:** During major news events, order books thin by 50%+ as market makers widen spreads and pull resting orders. This creates temporary vacuums that amplify the initial price reaction. After 5-7 minutes, a new equilibrium forms. *[Source: Trading the News PNGs]*

---

## 11. CTA/Systematic Strategy Replication Rules

### CTA Three-Speed Framework

CTAs (Commodity Trading Advisors) and systematic trend followers use moving average systems to mechanically allocate. By replicating their signals, you can anticipate their flow:

- **20 SMA (Fast/Gas Pedal):** The first signal CTAs respond to. When price crosses above 20 SMA, fast CTAs begin building longs. When below, they start cutting. *[Source: CTA Flow Replicator PNG]*

- **50 SMA (Medium/Brake):** The critical threshold. A close below 50 SMA triggers medium-speed CTA selling. This is when aggregate CTA flow meaningfully shifts. *[Source: CTA Flow Replicator PNG]*

- **120 SMA (Slow/Floor):** The structural anchor. A close below 120 SMA triggers slow CTA selling — these are the largest, slowest-moving funds. When even these are selling, the trend reversal is confirmed. *[Source: CTA Flow Replicator PNG]*

### CTA Zone Trading Rules

- **Green Zone (above all 3 SMAs):** CTAs are providing systematic long flow. Buy dips to MAs. This is the "with the wind" regime. *[Source: CTA Flow Replicator PNG]*

- **Yellow Zone (below 20, above 50):** Fast CTAs are cutting, but medium/slow CTAs still long. Reduce position size. This is the caution zone — momentum is fading but the trend isn't broken. *[Source: CTA Flow Replicator PNG]*

- **Red Zone (below 50, above 120):** Medium CTAs are actively selling. Short or hedge. This is the "against the wind" regime for longs. Only the slowest CTAs are still providing support. *[Source: CTA Flow Replicator PNG]*

- **Grey Zone (below all 3 SMAs):** All CTA speeds are short/flat. Maximum bearish systematic flow. High volatility regime. Only take short trades or stay flat. *[Source: CTA Flow Replicator PNG]*

### Price-Insensitive Mechanical Flows

These flows are not driven by technical analysis or fundamentals — they are mechanical and predictable:

- **Index rebalancing:** S&P 500, Russell 2000 reconstitution creates predictable buy/sell flow for added/deleted names. Front-run additions: +4-7% average gain with ~60-70% win rate. Post-inclusion mean reversion: -1 to -2% over 20 trading days. *[Source: SP500_Index_Inclusion_Backtest.docx]*

- **Leveraged ETF rebalancing:** Leveraged ETFs (2x, 3x) must rebalance at end of day to maintain their leverage ratio. This creates predictable flow in the final 30 minutes of trading:
  - After an up day: leveraged long ETFs must BUY more (amplifying the up move at close)
  - After a down day: leveraged long ETFs must SELL (amplifying the down move at close)
  - The larger the daily move, the larger the rebalancing flow
  *[Source: Price_Insensitive_Flows_Guide.docx]*

- **Pension/insurance rebalancing:** Monthly and quarterly rebalancing between equity and fixed income allocations. After a strong equity month, pensions sell equities to rebalance. After a weak month, they buy. This creates contrarian end-of-month flows. *[Source: Price_Insensitive_Flows_Guide.docx]*

- **OPEX pinning:** As options approach expiration, dealer hedging forces price toward the strike with the highest open interest (max pain). This creates a "pinning" effect on OPEX day. *[Source: Price_Insensitive_Flows_Guide.docx, Window of Weakness PNGs]*

- **Post-OPEX volatility expansion:** After OPEX, the gamma pinning effect disappears. This releases price from the pin and allows volatility to expand. The 1-5 days after monthly OPEX are the "Window of Weakness" — the market loses its normal hedging support. *[Source: Window of Weakness PNGs, Price_Insensitive_Flows_Guide.docx]*

### Window of Weakness Rules

- **Timing:** Monday through Wednesday after monthly OPEX (third Friday of the month). This is when the hedging support from expiring options fully dissipates. *[Source: Window of Weakness PNGs]*

- **Vanna effect:** As implied volatility changes post-OPEX, dealers adjust delta hedges. The buying pressure from vanna hedging that supported the market during the OPEX cycle drops away. *[Source: Window of Weakness PNGs]*

- **Charm effect:** As options approach and pass expiration, time-decay-driven hedging (charm) creates support that suddenly disappears. *[Source: Window of Weakness PNGs]*

- **Seasonal pattern:** OPEX week itself tends to skew stronger (hedging support present). The week AFTER OPEX tends to underperform (hedging support removed). *[Source: Window of Weakness PNGs]*

- **Window of Weakness checklist:**
  1. Monitor dealer positioning (net gamma exposure)
  2. Watch implied volatility changes post-OPEX
  3. Check calendar for monthly vs. quarterly OPEX (quarterly = larger effect)
  4. Reduce risk into Tuesday/Wednesday post-OPEX
  5. Expect wider ranges and potential sell-offs during the window
  *[Source: Window of Weakness PNGs]*

### Crude Oil Systematic Signals

- **Term structure signal:** A flip of the prompt spread from contango (front < back) to backwardation (front > back) leads flat price rallies approximately 75% of the time. This is because backwardation signals physical tightness (demand > supply). *[Source: comprehensive_crude_oil_guide.html]*

- **Crack spread signal:** Widening crack spreads (refining margins) are bullish for crude as they signal strong product demand. Narrowing crack spreads are bearish. *[Source: comprehensive_crude_oil_guide.html]*

- **Seasonal patterns (crude oil):** Summer driving season (May-August) bullish; refinery maintenance (October-November) can create short-term bearish pressure; winter heating demand (December-February) can be bullish. *[Source: comprehensive_crude_oil_guide.html]*

---

## 12. Bottom/Top Signal Checklists

### BTC Derivative Bottom-Signals Checklist (8 Signals)

A cyclical bottom in Bitcoin is identified when multiple (not single) derivative signals fire simultaneously. No single metric is a "silver bullet" — the "cluster effect" of multiple signals is required:

1. **25-Delta Skew → Extreme Negative:**
   - Put implied volatility significantly exceeds call implied volatility.
   - Interpretation: Market is extremely fearful; paying up for downside protection.
   - Bottom signal when skew reaches historical extremes (puts >> calls).
   *[Source: BTC Derivative Bottom-Signals PNGs]*

2. **Quarterly Basis → Compression to Parity (~0%):**
   - Futures premium over spot compresses to near zero.
   - Interpretation: No one is willing to pay for leveraged long exposure (maximum apathy/fear).
   - Bottom signal when basis compresses to ~0% annualized.
   *[Source: BTC Derivative Bottom-Signals PNGs]*

3. **Perpetual Funding → Flips Negative:**
   - Shorts are paying longs to maintain positions.
   - Interpretation: Market is net short; bears are paying for their positioning.
   - Bottom signal when funding is persistently negative.
   *[Source: BTC Derivative Bottom-Signals PNGs]*

4. **Stablecoin APRs → Collapse to Base Rate:**
   - Lending yields for stablecoins drop to near-zero.
   - Interpretation: No demand for leverage (apathy/capitulation).
   - Bottom signal when stablecoin yields collapse.
   *[Source: BTC Derivative Bottom-Signals PNGs]*

5. **Term Structure → Inversion (Near > Far):**
   - Near-term futures trade at a premium to longer-dated futures.
   - Interpretation: Short-term hedging demand is extreme.
   - Bottom signal when the curve inverts.
   *[Source: BTC Derivative Bottom-Signals PNGs]*

6. **Open Interest Divergence → Large OI Build into Bearish Candles:**
   - OI increases while price falls (new shorts being established at lows).
   - Interpretation: Participants are getting aggressively short at what may be the bottom.
   - Bottom signal when OI builds significantly during the decline.
   *[Source: BTC Derivative Bottom-Signals PNGs]*

7. **Liquidation Composition → >80% Longs:**
   - The vast majority of liquidations are long positions being stopped out.
   - Interpretation: Long holders have been flushed; the weak hands are out.
   - Bottom signal when long liquidation dominance reaches 80%+.
   *[Source: BTC Derivative Bottom-Signals PNGs]*

8. **Spot Orderbook Skew → Wall of Bids (Absorption):**
   - Spot order books show significantly more bid-side depth than ask-side.
   - Interpretation: Buyers are accumulating at these levels; sellers are being absorbed.
   - Bottom signal when bid-side depth significantly outweighs ask-side.
   *[Source: BTC Derivative Bottom-Signals PNGs]*

**Bonus Signal — VIX Spike (30+):** A VIX spike above 30 as macro confirmation of extreme fear. This is a cross-asset confirmation that risk-off sentiment is at extremes. *[Source: BTC Derivative Bottom-Signals PNGs]*

**Cluster Rule:** Require a MINIMUM of 4-5 of the 8 signals firing simultaneously before declaring a bottom signal. No single metric in isolation is sufficient. *[Source: BTC Derivative Bottom-Signals PNGs]*

### Positioning-Based Top Signals (Inverse of Bottom Signals)

The inverse of each bottom signal provides a top/overheating framework:

1. **25-Delta Skew → Extreme Positive:** Calls >> puts. Extreme euphoria; everyone wants upside exposure. *[Source: Derived from BTC Derivative Bottom-Signals PNGs]*
2. **Quarterly Basis → Extreme Premium:** Double-digit annualized futures premium. Leverage demand is maximal. *[Source: Derived from BTC Derivative Bottom-Signals PNGs]*
3. **Perpetual Funding → Persistently Positive (Elevated):** Longs paying extreme rates to hold positions. *[Source: Derived from BTC Derivative Bottom-Signals PNGs]*
4. **Stablecoin APRs → Spiking:** High demand for leverage (borrowing stablecoins to buy). *[Source: Derived from BTC Derivative Bottom-Signals PNGs]*
5. **Liquidation Composition → >80% Shorts:** Short sellers being flushed (capitulation of bears). *[Source: Derived from BTC Derivative Bottom-Signals PNGs]*

### Gold-Specific Reversal Framework

- **Gold driver #1: Real Yields.** The single most important driver of gold prices. Rising real yields = bearish gold; falling real yields = bullish gold. This overrides all other technical signals. *[Source: gold-trading-guide.html]*

- **Event-driven gold reversals:** After CPI, NFP, or FOMC releases, gold often makes a violent initial move that partially reverses within 1-2 hours. The fade-the-initial-move strategy works best when the initial move is on thin liquidity (pre-market or post-market). *[Source: gold-trading-guide.html]*

### Equity Positioning Extreme Signals

- **Short squeeze conditions:**
  1. High short interest (>15% of float)
  2. Rising borrow cost
  3. Positive catalyst (earnings beat, analyst upgrade)
  4. Volume surge with price rising (shorts covering)
  - Trade: Buy breakouts with volume confirmation. Target the squeeze toward the next resistance.
  *[Source: market_positioning_guide.html]*

- **Long puke conditions:**
  1. Extended long positioning (consensus bullish)
  2. Unexpected negative catalyst
  3. Gap down on heavy volume
  4. CVD heavily negative with price accelerating down
  - Trade: Do not catch the falling knife. Wait for stabilization (volume declining, delta shifting). Enter on the first constructive reaction after the liquidation cascade ends.
  *[Source: market_positioning_guide.html]*

- **Gamma pin → release:**
  1. Pre-OPEX: price pinned near max-pain strike (gamma compression)
  2. OPEX occurs: gamma evaporates
  3. Post-OPEX: sudden volatility expansion as the pin releases
  - Trade: Position for vol expansion (straddles/strangles or directional with wider stops) in the 1-3 days after OPEX.
  *[Source: market_positioning_guide.html, Window of Weakness PNGs, Price_Insensitive_Flows_Guide.docx]*

---

## Appendix: Universal Trading Principles (Cross-Cutting Rules)

These principles apply across all 12 categories above:

1. **"The market is always right. You are wrong if you are losing money for any reason at all."** — Michael Platt. Accept losses quickly; do not argue with price. *[Source: Finding an Edge.txt]*

2. **Universe management:** Cap your watchlist at 20 symbols maximum. Rank by ATR (top 30%) and proximity to a higher-timeframe level. *[Source: daily_trading_plan_card.html]*

3. **Retail edge is speed and selectivity.** Institutions are constrained by size, mandate, and bureaucracy. Retail traders can sit out, be in 100% cash, and pounce only on the highest-conviction setups. This optionality IS the edge. *[Source: retail_trading_Edge.html]*

4. **Identify who is forced to act.** Before analyzing a chart, ask: "Who is positioned here? Who is offside? What are they forced to do?" The forced flow will dominate price action. *[Source: market_positioning_guide.html, Finding an Edge.txt, Price_Insensitive_Flows_Guide.docx]*

5. **Regime identification precedes strategy selection.** Determine whether the market is in a trending, mean-reverting, or volatile regime BEFORE applying any technical setup. Wrong-regime application of a correct setup will lose money. *[Source: daily_trading_plan_card.html, How Price Moves.html]*

6. **Risk management is non-negotiable:** Max risk per trade 0.1-0.4% of capital (scalps) or up to 2% (swing). Daily loss limit of 3%. Hit the limit = stop. No exceptions. *[Source: Crypto Scalping Considerations PNGs, daily_trading_plan_card.html]*

7. **Master one tape before expanding.** Choose one instrument (ES, BTC, crude) and one session. Become expert in its microstructure. Do not spread attention across multiple instruments until you are consistently profitable on one. *[Source: Flow Trading Crypto PNGs, ES Scalping Reference Guide PNGs]*

---

*Generated from education documents in `docs/the-stable/`. Two PDF files (Flow Playbook Intraday.pdf, CTA Strategy Replication Cheat Sheet.pdf) were not readable and are excluded from this extraction.*
