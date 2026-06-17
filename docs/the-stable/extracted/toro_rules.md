# TORO Rules -- Bull Case Analyst

> Extracted from The Stable education library. Each rule includes its source document.
> TORO's mandate: Build the strongest possible bull case. Identify momentum, trend continuation,
> catalysts, supportive flows, favorable positioning, and asymmetric risk/reward setups.
> Challenge bearish assumptions with structural evidence.

---

## 1. Momentum & Trend Rules

### 1.1 CTA/Systematic Trend Signals
- **RULE: Price above all three CTA speeds (20/50/120 SMA) = "Max Long" regime.** Systematic funds are fully allocated. Trend is your friend -- do not fight it. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: The 120 SMA is the "golden trade."** When price pulls back to the 120 SMA in a broader uptrend, CTAs at the slower speed are still long. This is the highest-conviction dip-buy level for trend followers. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: Two-close rule for confirmation.** Require two consecutive closes above a SMA level before confirming a bullish signal. One close can be noise; two closes confirm CTA trigger. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: Rising price + falling VIX = real rally.** When VIX declines as price advances, institutional positioning is genuinely rotating into risk. This is the volatility filter that separates sustainable rallies from fake ones. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: Volume confirms trend.** Use volume as a "lie detector" -- a breakout above a SMA on above-average volume is genuine; on low volume, suspect. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: Green Line (20 SMA) is the "gas pedal."** If price is above the 20 SMA, CTAs are pressing longs. Momentum is accelerating. _[Source: CTA Flow Replicator Indicator]_
- **RULE: EMA 9 > EMA 20 = short-term bullish momentum.** When fast EMA crosses above slow EMA, near-term trend is up. _[Source: Ryans AIO MAs + Rolling VWAPs Indicator]_

### 1.2 Trend Day Recognition
- **RULE: Trend days exhibit one-way moves with multiple failed breakdowns in both directions.** On a bull trend day, buyers absorb every dip. Cumulative delta rises all day. Trade with the trend, not against it. _[Source: ES Scalping Reference Guide]_
- **RULE: Strong opens that never look back signal institutional conviction.** When the open drives through overnight highs with volume, this is a trend day signal. Size up and ride it. _[Source: How Price Moves]_
- **RULE: "Strength" in order flow = large aggressive buyers lifting offers, price makes new highs on rising cumulative delta.** This is the most basic bullish signal -- genuine buying pressure confirmed by delta. _[Source: Flow Playbook Intraday]_
- **RULE: On trend days, auction-marker lows (price swing mark-downs) feel "cheap" to bigger players.** What looks like a dip to retail is a discount to institutions. _[Source: ES Scalping Reference Guide]_

### 1.3 Session & Time-of-Day Momentum
- **RULE: 11am-1pm EDT (15-17 UTC) is peak global volume.** Direction tends to persist during this volume cluster. If the move is bullish here, it is likely the real move of the day. _[Source: Bitcoin Intraday Cheat Sheet]_
- **RULE: Fade mean-reversion ideas until after the 15-17 UTC volume crest.** Direction during peak volume is signal; trying to fade it is fighting the tape. _[Source: Bitcoin Intraday Cheat Sheet]_
- **RULE: The US Market Open (9:30-10:30 ET) captures 25% of daily volume.** Breakouts with volume in this window carry institutional weight. _[Source: Market Microstructure and Time of Day Analysis]_
- **RULE: Mid-Day session (10:30-14:30 ET) is range-bound, lower volume -- ideal for scalping ranges.** But when mid-day breaks range, it signals a real trend. _[Source: Market Microstructure and Time of Day Analysis]_
- **RULE: The Closing Period (14:30-16:00 ET) sees 30-35% of daily volume.** Market depth clears sharply at close. Momentum into close confirms the day's direction. _[Source: Market Microstructure and Time of Day Analysis]_

---

## 2. Flow & Positioning Signals (Bullish)

### 2.1 Order Flow Confirmation
- **RULE: Persistent one-sided taker flow that sustains and pulls price = real flow.** Look for CVD persistence, not just spikes. 2-3 consecutive high-imbalance windows matter more than one outlier. _[Source: Flow Trading Crypto]_
- **RULE: Rising price + rising OI = fresh longs entering.** This is genuine new bullish positioning, not just short covering. Watch for later squeezes as these longs need to be challenged. _[Source: Flow Trading Crypto]_
- **RULE: Large delta-OI + basis jump = speculative long build.** When basis (futures premium) jumps alongside OI increase, leveraged longs are building -- bullish if sustained. _[Source: Flow Trading Crypto]_
- **RULE: Aggressive spot orders lifting offers create cross-venue arbitrage.** When spot leads and futures follow, this is organic demand. HFTs chase the signal, amplifying the move. _[Source: Spot Flows & Futures Impact]_
- **RULE: When spot leads the move, it is organic demand.** Spot buying that forces futures higher through basis arbitrage is the most reliable bullish signal. Futures-led moves can be leverage-driven and fragile. _[Source: Spot Flows & Futures Impact]_

### 2.2 Institutional & Structural Flows
- **RULE: ETF net creation (primary market) = new capital entering.** Volume alone does not tell you direction. Creation units (authorized participants creating new shares) mean genuine new demand. Track via T+1 settlement data. _[Source: Crypto ETF Flow Structure]_
- **RULE: Price-insensitive buying creates predictable demand.** Index additions, pension rebalancing after drawdowns, and corporate buybacks are flows that MUST occur regardless of price. These are structural tailwinds. _[Source: Price-Insensitive Flows Guide]_
- **RULE: S&P 500 index additions create front-running opportunity.** The announcement-to-effective window (5-15 trading days) historically shows bullish drift as $16T in benchmarked assets must rebalance. Direct additions (non-MidCap migrations) offer the best edge. _[Source: SP500 Index Inclusion Backtest]_
- **RULE: Pension rebalancing after equity selloffs = forced buying.** After stocks fall, 60/40 pensions must BUY equities to restore target allocation. JP Morgan estimates $250B+ in rebalancing after major selloffs. _[Source: Price-Insensitive Flows Guide]_
- **RULE: Leveraged ETF rebalancing on up days = forced buying into close.** On large up days, 2x/3x leveraged ETFs must buy more exposure at end of day to maintain target leverage. This amplifies late-day moves. _[Source: Price-Insensitive Flows Guide]_
- **RULE: Corporate buybacks provide persistent bid support.** S&P 500 buybacks exceed $900B annually. Companies buy steadily, providing a structural floor. _[Source: Price-Insensitive Flows Guide]_
- **RULE: Russell reconstitution additions create predictable demand.** Purely rules-based (unlike S&P), making it highly predictable. $10.6T tracks Russell indices. _[Source: Price-Insensitive Flows Guide]_

### 2.3 Positioning-Based Bullish Signals
- **RULE: Short squeeze mechanics -- when shorts are trapped, covering creates buying pressure.** Rising price + declining OI after a period of rising OI on falling price = short covering rally. _[Source: Market Positioning Guide]_
- **RULE: Dealer long gamma pins price but creates explosive moves when gamma rolls off.** Post-OPEX, when dealer gamma hedging dissipates, suppressed volatility can release into a directional move. If bias is bullish, the move will be to the upside. _[Source: Market Positioning Guide]_
- **RULE: Negative funding rate in crypto = shorts are crowded.** When shorts are paying longs, there is no incentive for shorts to hold through a grind higher. This creates fuel for a short squeeze or mean-reversion bounce. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: "Ask who is trapped before asking is it cheap."** The best bull setups occur when bears are trapped, not just when price looks cheap. Trapped shorts with rising OI = coiled spring. _[Source: Market Positioning Guide]_

---

## 3. Catalyst Frameworks

### 3.1 News & Event Catalysts
- **RULE: When scheduled macro/news releases are imminent, the crypto order book goes thin -- and that disruption creates opportunity.** The initial price action during news events is often characterized by violent moves in both directions before settling into a trend. The directional move comes AFTER the whipsaw. _[Source: Trading the News]_
- **RULE: Use the 7-12 minute post-news window.** After news releases, the sequence is: 1-3 min initial order book thinning, 3-7 min significant liquidity withdrawal, 7-12 min news triggers immediate price movement, 12-30 sec initial vacuum movement. The tradeable trend establishes by 7-12 min. _[Source: Trading the News]_
- **RULE: Unscheduled news response framework -- 10-30 sec for algorithmic reaction, 30-60 sec for real traders to assess, 1-2 min for broader retail, 5+ min for price discovery and new equilibrium.** Position in the 1-5 min window after the initial algo noise. _[Source: Trading the News]_
- **RULE: Day type transformation is the ultimate bull catalyst.** Major events (CPI, ETF approval, enforcement action) can completely flip the day type from range-bound to trending. When this happens, immediately adopt trend strategy. _[Source: Trading the News]_
- **RULE: If early in position and flat, hold before the event -- the risk is worth the potential reward.** If already positioned ahead of a catalyst, maintain the position. The asymmetry favors holding. _[Source: Trading the News]_

### 3.2 Structural & Macro Catalysts
- **RULE: Gold rallies when real yields fall.** Real yields (TIPS yields) are the #1 driver of gold. Falling real yields = rising gold. This is the most reliable macro relationship. _[Source: Gold Trading Guide]_
- **RULE: Crude oil in backwardation = supply tight, bullish.** When near-month futures trade above far-month (backwardation), physical demand exceeds supply. This is bullish for commodities. _[Source: Comprehensive Crude Oil Guide]_
- **RULE: BTC ETF creation units = structural demand floor.** ETF creation/redemption mechanics provide a structural demand channel for BTC. When creation exceeds redemption, there is net new capital entering the ecosystem. _[Source: Crypto ETF Flow Structure]_
- **RULE: Risk premia harvesting -- crypto offers outsized risk premia for technology adoption, regulatory evolution, liquidity provision, and volatility.** These are not alpha (skill) but premia (compensation for bearing risk). The bull case is that these premia persist and reward patient holders. _[Source: Risk Premia Alpha Guide]_

---

## 4. VWAP & Level-Based Bull Setups

### 4.1 VWAP Setups
- **RULE: Price reclaiming VWAP from below on volume = bullish.** If price traded below VWAP and then reclaims it with confirming volume/delta, this is a high-probability long entry. Sellers who entered below VWAP are now trapped. _[Source: VWAP Trading Guide]_
- **RULE: Trade at VWAP deviation band edges, not in the middle.** The +/- 0.3 SD zone around VWAP is a no-trade zone (balance). Wait for price to reach the -1 SD or -2 SD band for long entries. Position size inversely proportional to VWAP proximity. _[Source: VWAP Trading Guide]_
- **RULE: Rolling VWAP confluence creates support.** When multiple rolling VWAPs (2-day, 3-day, 7-day) cluster at a similar level, that level acts as strong dynamic support. _[Source: Ryans AIO MAs + Rolling VWAPs Indicator]_

### 4.2 Horizontal Level Setups
- **RULE: Reclaim setups are high-probability longs.** When price breaks below a key level but then reclaims it from below with strong delta, shorts are trapped. Enter long on the reclaim with a stop below the level. _[Source: Flow Playbook Intraday]_
- **RULE: Rebid setups at prior support.** When price pulls back to a previously defended level and finds buyers again (bid-side absorption), this is a rebid -- high probability long. _[Source: Flow Playbook Intraday]_
- **RULE: Session-level hierarchy for support.** Use overnight low, yesterday close, weekly open, and monthly open as support levels. The more session levels that cluster, the stronger the support. _[Source: Comprehensive BTC Levels Guide]_
- **RULE: Volume Profile POC (Point of Control) acts as fair value.** When price pulls back to POC with absorption, it is returning to fair value. Longs here have statistical edge. _[Source: Comprehensive BTC Levels Guide]_
- **RULE: Wait for resolution at levels.** Do not trade the first test. Wait for the three-player dynamic (reversal trader enters, breakout trader enters, smart money takes the other side) to resolve. The resolution tells you the real direction. _[Source: Comprehensive BTC Levels Guide]_

### 4.3 Support from Moving Averages
- **RULE: SMA 50 acts as first institutional support in uptrend.** Institutional buyers often have standing orders at the 50 SMA. First touch in an uptrend is high-probability bounce. _[Source: Ryans AIO MAs + Rolling VWAPs Indicator]_
- **RULE: SMA 200 is the macro bull/bear line.** Price above 200 SMA = bullish regime. The 200 SMA is the most-watched institutional level globally. _[Source: CTA Strategy Replication Cheat Sheet]_

---

## 5. Risk/Reward Assessment

### 5.1 Position Sizing for Bull Cases
- **RULE: Size inversely proportional to distance from key level.** The closer to a well-defined support level, the larger the position (tighter stop, better R:R). At VWAP -2 SD, size up. At VWAP +1 SD, size down. _[Source: VWAP Trading Guide]_
- **RULE: Pre-event maximum 25% of normal position; during event trading, maximum 50%.** Manage size around catalysts. Post-event recovery gradually increase to 50% then full size only after clear price structure emerges. _[Source: Trading the News]_
- **RULE: Volatility-adjusted stops.** Wider stops in high-volatility environments to account for noise. Time-based stops: exit after a predetermined time if no clear direction emerges. Structure-based stops: based on key technical levels rather than percentage moves. _[Source: Trading the News]_
- **RULE: Scalping win rate target >60% with risk:reward of at least 1:1.** Track win rate, average win vs. average loss, and profit factor. Ensure positive expectancy. _[Source: Crypto Scalping Considerations]_

### 5.2 Retail Edge Advantages (Bull)
- **RULE: Retail traders have mandate freedom -- no benchmark constraints.** Unlike institutions, you can go 100% cash or 100% long. Use this freedom to size aggressively when conditions align. _[Source: Retail Trading Edge]_
- **RULE: Exploit liquidity voids.** Event-driven price dislocations (flash crashes, circuit breakers) where institutions are constrained by mandate or risk limits create the best asymmetric opportunities. Retail can step in where institutions cannot. _[Source: Retail Trading Edge]_
- **RULE: Speed of thesis adoption is your edge.** A retail trader can rotate from bearish to bullish in minutes. Institutions with committees, risk managers, and mandates take days or weeks. When the data shifts, shift immediately. _[Source: Retail Trading Edge]_

---

## 6. Market Microstructure (Bullish Patterns)

### 6.1 Absorption & Accumulation
- **RULE: "Absorption" = price stops falling despite aggressive selling.** Large passive buyers are absorbing sell orders. The bid wall holds, delta diverges from price. This is the hallmark of institutional accumulation. _[Source: How Price Moves]_
- **RULE: Iceberg orders on the bid = hidden institutional buying.** When the DOM shows thin bids but price does not fall (bid keeps refreshing), an iceberg algorithm is accumulating. _[Source: How Price Moves]_
- **RULE: Vacuum pullback into support = buying opportunity.** When price falls quickly through a "vacant floor" (no resting limits) into a zone of resting bids, the fast move creates panic selling that is absorbed by patient buyers. The bounce from vacuum lows is sharp and tradeable. _[Source: How Price Moves]_
- **RULE: Spot orderbook skew (wall of bids) = smart money accumulation.** When bid-side liquidity heavily outweighs ask-side across key depths while price is falling, smart money is deploying passive capital to absorb forced selling. _[Source: BTC Derivative Bottom-Signals Checklist]_

### 6.2 Trapped Trader Mechanics (Bullish)
- **RULE: Trapped shorts create fuel for rallies.** When price breaks below a level, shorts enter, then price quickly reclaims the level -- shorts are trapped. Their stop-loss buying adds fuel to the rally. _[Source: Flow Playbook Intraday]_
- **RULE: False breakdown + reclaim = high-conviction long.** A failed breakdown that reclaims on strong delta is the single highest-probability mean-reversion setup. The false move traps shorts and confirms strong demand below. _[Source: Flow Playbook Intraday]_
- **RULE: Monday range sweep -- if Monday sweeps below Friday's low early, watch for reclaim.** The Monday sweep traps weekend shorts. If price reclaims Friday's range, it signals strong buying and sets up a trend continuation for the week. _[Source: Flow Playbook Intraday]_
- **RULE: Asian session trap into London.** Asian session sets a range in thin liquidity. London open sweeps one side, then reverses. If London sweeps the Asian low and reverses up, it is a high-probability long. _[Source: Flow Playbook Intraday]_
- **RULE: Wick fill reversal -- long wicks into support that close back inside range = absorption.** The wick represents tested selling that was absorbed. Price returning inside range confirms demand. _[Source: Flow Playbook Intraday]_

### 6.3 Bottom-Signal Identification (Crypto-Specific)
- **RULE: The "Cluster Effect" -- multiple derivative bottom signals firing together = high-conviction bottom.** No single metric is a silver bullet. Look for clustering of: extreme negative skew (fear peaked), negative funding (shorts crowded), OI rising into lows (trap set), spot book bid dominance (absorption), basis compressing near 0% (leverage reset), stablecoin APRs collapsing (apathy), liquidations >80% longs (bulls washed out). _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: 25-delta skew extreme negative = fear peaked.** When puts become much more expensive than calls, the market is panic-bidding protection. Once selling pressure exhausts, dealers begin buying back hedges, creating a "vanna/charm" tailwind that stabilizes and lifts price. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: Quarterly basis compression to parity (~0%) = leverage washed out.** In bull markets, futures trade at a premium (contango) due to demand for leverage. When this premium compresses to near 0%, speculative longs have been purged and the system is reset to neutral baseline. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: Liquidation composition >80% longs = capitulation complete.** A genuine bottom requires the removal of supply. When >80% of liquidated capital is long positions, over-leveraged bulls have been forcibly ejected. The market is clean for a new rally. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: Stablecoin borrow APRs collapsing to base rate = apathy floor.** A bottom is not marked by a spike in rates but by apathy. Low APRs confirm speculative froth is gone and no one is rushing to leverage up. Clean slate for new trend. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: VIX spike (30+) while crypto derivative bottom signals fire = generational opportunity.** When correlations go to 1 and assets are sold for cash (global margin call), crypto signals 1-8 firing simultaneously while VIX crushes equities = liquidity flows back to fastest horses first when VIX rolls over. _[Source: BTC Derivative Bottom-Signals Checklist]_

### 6.4 Intraday Bullish Setups
- **RULE: Small Initial Balance (IB) breakout long.** When the first 30-60 min range (IB) is narrow, a breakout above the IB high on volume signals a trend day. Enter long on the breakout with stop below IB low. _[Source: Flow Playbook Intraday]_
- **RULE: Inside day breakout.** When today's range is inside yesterday's range and price breaks above yesterday's high, it signals coiled energy releasing upward. _[Source: Flow Playbook Intraday]_
- **RULE: Engulfing reversal from support.** A bullish engulfing candle at a key support level with volume confirmation = strong reversal signal. _[Source: Flow Playbook Intraday]_
- **RULE: Consolidation breakout.** Extended tight range consolidation followed by an upside breakout on expanding volume = new trend leg beginning. _[Source: Flow Playbook Intraday]_
- **RULE: Round number reversal.** At major round numbers (psychological levels), trapped shorts who sold the breakdown of the round number become fuel for the recovery when price reclaims it. _[Source: Flow Playbook Intraday]_

### 6.5 Crypto-Specific Flow Mechanics
- **RULE: CME + Coinbase spot is the primary truth feed during US hours for BTC/ETH.** CME sets basis and defines USD appetite. Coinbase confirms real USD spot demand. If both are bullish, the move is real. _[Source: Flow Trading Crypto]_
- **RULE: Binance perps are the primary truth feed during Asia/off-hours.** They carry the deepest liquidity, most leverage, and lead price discovery globally. If Binance perps are bid, the market is bid. _[Source: Flow Trading Crypto]_
- **RULE: OI shifts are your confirmation that real positioning is changing.** For BTC on a single venue: $250-400M delta-OI in 1h = worth tracking; $600-800M in 3h = meaningful; $1B+ in-session = dominant flow day. _[Source: Flow Trading Crypto]_
- **RULE: Favor persistence over spikes.** 2-3 consecutive high-imbalance windows matter more than one outlier. Persistent one-sided flow = real conviction. _[Source: Flow Trading Crypto]_

---

## 7. Window of Weakness (Bullish Angle)

- **RULE: The Window of Weakness is a 1-3 day period following monthly OPEX (typically Monday-Wednesday after 3rd Friday).** During this window, gamma support from options hedging activity disappears. For the BULL, this means: if the market survives the Window without breaking down, it confirms underlying demand strength independent of options mechanics. _[Source: Window of Weakness]_
- **RULE: If key support holds positively during the Window, it may clear the way for the next leg higher.** The absence of gamma support is a stress test. Passing it is bullish confirmation. _[Source: Window of Weakness]_
- **RULE: The Window is a flow-based phenomenon, not a fundamental one.** It exists because modern market structure (options, hedging flows) creates temporary vulnerability. Understanding this means you can buy dips during the Window knowing the weakness is mechanical, not fundamental. _[Source: Window of Weakness]_
- **RULE: After VIX expiration (Wednesday following OPEX), additional volatility from VIX options settling can create the final flush.** If price holds after Wednesday, the bull case strengthens into the rest of the week. _[Source: Window of Weakness]_
- **RULE: September-specific: "The September OPEX (third Friday) last week provides a nearly five-week period before October OPEX on the 17th of each month."** This extended window without options support is when dip-buying opportunities are largest if fundamentals support. _[Source: Window of Weakness]_

---

## 8. Commodity-Specific Bull Rules

### 8.1 Gold
- **RULE: Gold + falling real yields + weakening USD = maximum bullish alignment.** This triple confluence creates the strongest gold bull setup. _[Source: Gold Trading Guide]_
- **RULE: Central bank buying provides structural floor for gold.** Post-2022, central bank gold purchases have created a persistent demand driver independent of traditional macro factors. _[Source: Gold Trading Guide]_
- **RULE: Gold is a macro-financial asset, not a commodity.** Trade it based on rates, FX, and central bank policy -- not supply/demand like oil or copper. _[Source: Gold Trading Guide]_

### 8.2 Crude Oil
- **RULE: Supply factors drive 40% of crude, demand 35%, market structure 25%.** Bull case prioritizes: OPEC+ discipline, inventory draws, seasonal demand patterns. _[Source: Comprehensive Crude Oil Guide]_
- **RULE: Backwardation deepening = supply tightening.** When the front-month premium over back-months increases, physical demand is exceeding supply more urgently. _[Source: Comprehensive Crude Oil Guide]_
- **RULE: Crack spread widening = refinery demand strong.** When the 3-2-1 crack spread widens, refiners are profitably converting crude to products, supporting crude demand. _[Source: Comprehensive Crude Oil Guide]_

---

## 9. Execution & Discipline Rules

- **RULE: Master one tape.** Know its quirks: iceberg cadence, queueing behavior, fake depth, and fill quality. Depth of knowledge on one venue beats shallow knowledge of many. _[Source: Flow Trading Crypto]_
- **RULE: Scale by liquidity.** Adjust position size to depth and short-term realized vol. Do not use the same size in thin Asia hours as during US peak volume. _[Source: Flow Trading Crypto]_
- **RULE: Flip your "truth set" by session.** CME/spot during US hours, Binance perps during off-hours. Use the venue with the most flow as your signal source. _[Source: Flow Trading Crypto]_
- **RULE: Tight stops increase your odds of getting stopped out, especially in volatile environments.** Better to be right about direction with a wider stop than wrong with a tight one. Use structure-based stops at logical levels. _[Source: ES Scalping Reference Guide]_
- **RULE: Identify real inflection points -- support, resistance, volume nodes.** Execute to the next logical level with clear reasoning. Accept that some trades will lose -- part of the probability game. _[Source: ES Scalping Reference Guide]_
- **RULE: Post-Only entry on exchanges to save fees.** Use maker orders where possible. In high-frequency strategies, taker fees eat into edge rapidly. _[Source: Crypto Scalping Considerations]_
- **RULE: Your fixed cost of doing business matters more than any single trade.** Calculate your total cost per trade (exchange fees, spread cost, slippage). Your minimum profit target must exceed your total trading costs. _[Source: Crypto Scalping Considerations]_

---

## 10. Daily Trading Plan (Bull Bias)

- **RULE: Pre-market analysis must include: regime identification, market context, scheduled events, key levels, risk parameters, and circuit breaker levels.** Never trade without a plan. _[Source: Daily Trading Plan Card]_
- **RULE: For each setup, define: context (why), trigger (when), entry, stop, target, and invalidation BEFORE entering.** If you cannot articulate all six, do not trade. _[Source: Daily Trading Plan Card]_
- **RULE: Screening SOP: start with macro regime, then sector rotation, then individual setups.** Top-down analysis ensures your bull case aligns with the broader environment. _[Source: Daily Trading Plan Card]_
- **RULE: Circuit breaker awareness.** Know your personal daily loss limit and market-level circuit breakers. Even in a bull case, protect capital when the market regime shifts against you. _[Source: Daily Trading Plan Card]_
