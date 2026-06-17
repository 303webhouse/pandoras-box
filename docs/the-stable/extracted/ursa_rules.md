# URSA Rules -- Bear Case Analyst

> Extracted from The Stable education library. Each rule includes its source document.
> URSA's mandate: Build the strongest possible bear case. Identify headwinds, resistance,
> regime conflicts, timing risks, exhaustion signals, flow deterioration, and reasons NOT
> to take a trade. Challenge bullish assumptions with structural evidence.

---

## 1. Risk Identification Taxonomy

### 1.1 Regime & Macro Risks
- **RULE: Rising price + rising VIX = fake rally.** When VIX rises alongside price, institutional hedging is increasing even as price advances. This is the volatility filter that exposes unsustainable moves. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: Price below the 50 SMA ("the Brake") = CTA de-leveraging has begun.** When the 50 SMA breaks, systematic funds start reducing exposure. This is not a dip to buy -- it is the start of trend degradation. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: "Waterfall" zone -- price below 50 SMA.** CTAs are actively selling. The trend is broken at the medium speed. Do not catch falling knives here without extreme caution. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: "Capitulation" -- 20 SMA crosses below 120 SMA.** This is the death cross for CTA flows. Fast momentum has been negative long enough to cross below the slow trend. Maximum bearish systematic positioning. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: Interconnected market relationships create contagion risk.** ES is linked to: 500 underlying SPX stocks (direct), stock options (gamma), VIX and volatility surface (fear/hedging), U.S. dollar strength (currency), income correlations with EU/treasury futures (risk-on/off), and international markets (European and Asian session influence). One breaking can cascade. _[Source: ES Scalping Reference Guide]_
- **RULE: Bitcoin acts as a high-beta liquidity sponge.** When VIX explodes, correlations go to 1 and all assets are sold for cash. Crypto is the most vulnerable asset in a global margin call. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: Value is irrelevant in times of market stress -- it is all about positions.** When leverage unwinds, fundamental value provides no support. Markets trade against the largest positions, not toward fair value. _[Source: Finding an Edge / Market Positioning Guide]_

### 1.2 Structural Deterioration
- **RULE: The index inclusion effect has collapsed from +7.4% (1990s) to ~1-2% (2010s-present).** Crowded trades, front-running, and offsetting migration flows mean this "free edge" is largely arbitraged away. Beware of assuming historical patterns still hold. _[Source: SP500 Index Inclusion Backtest]_
- **RULE: Post-inclusion mean reversion.** After S&P 500 effective date, stocks often experience mean reversion as front-runners exit and temporary demand shock dissipates. Most pronounced in first 20 trading days. _[Source: SP500 Index Inclusion Backtest]_
- **RULE: Alpha decays rapidly.** Any edge that becomes known gets crowded. Risk premia that appear stable can evaporate when regime changes remove the risk being compensated. _[Source: Risk Premia Alpha Guide]_
- **RULE: Data-snooping bias.** Patterns found in backtests may not persist in live trading. The more parameters optimized, the less likely the edge is real. _[Source: Retail Trading Edge]_

---

## 2. Flow & Positioning Signals (Bearish)

### 2.1 Bearish Order Flow
- **RULE: "Exhaustion" in order flow = large buying effort with no new highs.** Price stalls at resistance despite aggressive buying (delta positive but price flat). This means supply is overwhelming demand. The move is running out of fuel. _[Source: Flow Playbook Intraday]_
- **RULE: Falling price + rising OI = new shorts entering (potential trap if CVD diverges).** Fresh shorts building is bearish momentum confirmation. But watch for CVD divergence -- if cumulative delta is actually positive while price falls and OI rises, the shorts may be walking into a trap. _[Source: Flow Trading Crypto]_
- **RULE: Large delta-OI + basis compress/funding red = short build.** When basis compresses and funding turns negative alongside OI increase, leveraged shorts are building aggressively. _[Source: Flow Trading Crypto]_
- **RULE: Big delta-OI with small price range = trapped inventory.** When OI changes significantly but price barely moves, one side is accumulating positions that will be forced to exit. If this happens at highs, longs are trapped. _[Source: Flow Trading Crypto]_
- **RULE: Big move + flat OI = liquidation event, less sticky positioning.** When price drops sharply but OI does not decline, the move was driven by liquidations rather than new shorts. The positioning aftermath is unstable. _[Source: Flow Trading Crypto]_

### 2.2 Institutional & Structural Headwinds
- **RULE: ETF net redemption = capital leaving.** When authorized participants redeem ETF shares (primary market outflows), real capital is exiting the ecosystem. This is a structural headwind regardless of price action. _[Source: Crypto ETF Flow Structure]_
- **RULE: Pension rebalancing after equity rallies = forced selling.** After stocks rise, 60/40 pensions must SELL equities to restore target allocation. Goldman estimated $32B in pension equity selling at Q1 2024 quarter-end (89th percentile). _[Source: Price-Insensitive Flows Guide]_
- **RULE: Leveraged ETF rebalancing on down days = forced selling into close.** On large down days, 2x/3x leveraged ETFs must SELL exposure at end of day. September 3, 2024: $15B in ETF selling contributed to 3% Nasdaq drop. This creates a negative feedback loop. _[Source: Price-Insensitive Flows Guide]_
- **RULE: VIX contango roll creates constant selling pressure on VIX, but when contango flips to backwardation, the reverse occurs.** VIX backwardation = market stress. Volatility-targeting funds sell equities when realized vol rises, creating positive feedback: selling --> higher vol --> more selling. _[Source: Price-Insensitive Flows Guide]_
- **RULE: Tax-loss harvesting creates selling pressure in November-December.** Losing positions are sold for tax purposes, creating predictable downward pressure on YTD losers. _[Source: Price-Insensitive Flows Guide]_
- **RULE: MSTR policy shift removed ~6,300 BTC weekly absorption.** When MSTR changed from opportunistic to disciplined buying (>2.5x mNAV threshold), it broke the reflexive loop of continuous buying. One structural demand pillar removed. _[Source: MicroStrategy Policy Analysis]_

### 2.3 Positioning-Based Bearish Signals
- **RULE: "Long puke" = forced long liquidation cascade.** When highly leveraged longs are forced to exit, their selling triggers further liquidations. This cascade creates the sharpest downside moves. _[Source: Market Positioning Guide]_
- **RULE: Dealer short gamma on downside = mechanical selling.** When dealers are short gamma (from selling puts), they must sell futures as price drops to hedge. This mechanically exacerbates the sell-off. _[Source: Market Positioning Guide / BTC Derivative Bottom-Signals Checklist]_
- **RULE: Crowded long positioning = vulnerability.** When COT shows extreme long positioning, or when OI is at extremes with positive funding rates, the market is vulnerable to a long squeeze. _[Source: Market Positioning Guide]_
- **RULE: Gamma squeeze in reverse.** When heavy put buying forces dealers short gamma, they must sell stock as price falls. This creates a negative feedback loop -- the reverse gamma squeeze. _[Source: Price-Insensitive Flows Guide]_
- **RULE: Options skew turning negative rapidly = protective panic.** When 25-delta skew drops significantly below zero (puts becoming much more expensive than calls), the market is panic-bidding downside protection. This confirms bearish sentiment has teeth. _[Source: BTC Derivative Bottom-Signals Checklist]_

---

## 3. Counter-Trend Warning Signs

### 3.1 Exhaustion & Distribution
- **RULE: Absorption at highs = distribution.** When price stops rising despite aggressive buying (delta positive, price flat or declining), large passive sellers are distributing into buying pressure. This is the mirror image of accumulation at lows. _[Source: How Price Moves]_
- **RULE: Iceberg orders on the ask = hidden institutional selling.** When the DOM shows thin offers but price cannot advance (ask keeps refreshing), an iceberg algorithm is distributing. _[Source: How Price Moves]_
- **RULE: Divergence between price and cumulative delta = exhaustion.** If price makes new highs but cumulative delta diverges (making lower highs), the buying is losing conviction. The trend is exhausting. _[Source: How Price Moves / Flow Playbook Intraday]_
- **RULE: "Controlled demolition" via stop-runs.** Large players identify where stops are clustered (below obvious support), then engineer moves to trigger those stops. The stop-run creates a cascade of selling that allows the large player to accumulate at lower prices -- or signals a genuine breakdown if no absorption follows. _[Source: How Price Moves]_
- **RULE: Liquidity vacuum above resistance.** When there are no resting sell limits above a resistance level ("vacant floor" above), price can spike through resistance but then immediately reverse when the vacuum is filled. The spike is a trap, not a breakout. _[Source: How Price Moves]_

### 3.2 Failed Breakout Patterns
- **RULE: Failed breakout + rejection = trapped longs.** When price breaks above resistance but immediately fails and falls back below, breakout buyers are trapped. Their stop-loss selling adds fuel to the decline. _[Source: Flow Playbook Intraday]_
- **RULE: Fast spike trap.** A rapid spike to new highs that immediately reverses indicates a liquidity grab, not genuine demand. The spike trapped aggressive buyers at the top. _[Source: Flow Playbook Intraday]_
- **RULE: Level deception warning.** Horizontal levels attract three players: reversal traders (fade the level), breakout traders (trade through it), and smart money (exploit both groups). The first move at a level is often a fake -- the smart money traps one side before going the other direction. _[Source: Comprehensive BTC Levels Guide]_

---

## 4. VWAP & Level-Based Bear Setups

### 4.1 VWAP Rejection Setups
- **RULE: Price failing to reclaim VWAP from below = bearish continuation.** If price is below VWAP and tests it from below but gets rejected (sell-side absorption at VWAP), the market is confirming sellers are in control. _[Source: VWAP Trading Guide]_
- **RULE: VWAP deviation band +1 SD and +2 SD as resistance.** When price extends to the upper deviation bands, it is stretched and vulnerable to mean reversion back toward VWAP. Short entries at +1 SD / +2 SD with stops above. _[Source: VWAP Trading Guide]_
- **RULE: +/- 0.3 SD zone around VWAP is the no-trade zone.** This is the balance zone where neither side has edge. Trading here is noise. Wait for price to reach extreme deviation bands for setups. _[Source: VWAP Trading Guide]_

### 4.2 Resistance & Breakdown Levels
- **RULE: Session-level hierarchy for resistance.** Use overnight high, yesterday close, weekly open, and monthly open as resistance levels. When multiple session levels cluster overhead, selling pressure intensifies. _[Source: Comprehensive BTC Levels Guide]_
- **RULE: Volume Profile Value Area High (VAH) as resistance.** VAH represents the upper boundary of the accepted value range. Rejection from VAH signals the market is refusing to accept higher prices. _[Source: Comprehensive BTC Levels Guide]_
- **RULE: Loss of POC (Point of Control) is bearish.** When price breaks below the highest-volume node, the "fair value" anchor has shifted lower. This signals a regime change in the volume profile. _[Source: Comprehensive BTC Levels Guide]_
- **RULE: Trapped longs above resistance that failed.** When price breaks above a level, attracts buyers, then fails -- those trapped longs become overhead supply. Every bounce toward that level will be sold by trapped participants trying to exit at breakeven. _[Source: Flow Playbook Intraday]_

### 4.3 Moving Average Breakdowns
- **RULE: Loss of SMA 50 = first institutional support broken.** When the 50 SMA fails, the first layer of institutional support is gone. This often triggers CTA de-leveraging (sell signals on the medium speed). _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: Loss of SMA 200 = macro trend has turned.** Price below 200 SMA = bearish regime. The most-watched institutional level globally has been lost. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: Red Line (120 SMA) is the "Floor" -- watch for bounces but respect breakdowns.** If the 120 SMA breaks, CTAs at the slow speed flip to sell/short. This is the last line of defense for systematic trend followers. _[Source: CTA Flow Replicator Indicator]_
- **RULE: Orange Line (50 SMA) is "the Brake."** If this breaks, CTA selling starts at the medium speed. The trend is degrading. _[Source: CTA Flow Replicator Indicator]_
- **RULE: Background color turns grey = high volatility (VIX > 20).** Even if trend is up, "risk is high" and position sizing should be smaller. Volatility expansion is a headwind for conviction. _[Source: CTA Flow Replicator Indicator]_

---

## 5. Timing & Regime Risk Rules

### 5.1 Window of Weakness Framework
- **RULE: The "Window of Weakness" is a 1-3 day period following monthly OPEX (typically Monday-Wednesday after 3rd Friday).** During this window, normal gamma support from options hedging disappears. Market can experience larger moves and increased volatility as the stabilizing effect of dealer hedging is removed. _[Source: Window of Weakness]_
- **RULE: Key timing -- the Window is open Monday-Wednesday after monthly OPEX.** Market "appears" to bottom on big strike levels but the options support vanishes. What looked like support can gap through. _[Source: Window of Weakness]_
- **RULE: Vanna effect.** When volatility changes, dealers must adjust their hedges. Typically, when volatility spikes (which happens more on down moves), this creates buying pressure that supports the market. After OPEX, this options support disappears. _[Source: Window of Weakness]_
- **RULE: Charm effect.** As options approach expiration, their hedging requirements change each day. The typical daily buying that props up the market becomes unreliable after OPEX. _[Source: Window of Weakness]_
- **RULE: Bottom line -- "There are no guarantees stocks must go down during each period."** But the window creates added ability for "much larger moves in one direction or another." The absence of hedging flows = larger downside potential when sellers emerge. _[Source: Window of Weakness]_
- **RULE: If dealers are long or short gamma post-expiry = expect wider ranges.** Large gamma values at open OI strikes vanish. Price is freed from the gravitational pull of options positioning. _[Source: Window of Weakness]_
- **RULE: Specific checklist for trading the Window:** (1) If options are far into the money, call-weighted put-equity = expect wider ranges; (2) If they rebound positively, the window may clear safely; (3) If volatility stays after Tuesday/Wednesday = weakness likely continues; (4) If volatility ebbs after VIX expiration Wednesday = window closing. _[Source: Window of Weakness]_
- **RULE: Friday before close -- consider reducing risk or buying protection.** Monday PM: window typically closes, but be cautious. Tuesday/Wednesday: Monitor. If bullish reversal signs, reduce protective positions. _[Source: Window of Weakness]_
- **RULE: "Do not assume it means markets will go down. Stability can go away too."** The Window makes markets fragile, not necessarily bearish. But fragility + bearish catalyst = amplified downside. _[Source: Window of Weakness]_

### 5.2 OPEX and Options Cycle Timing
- **RULE: Post-OPEX volatility expansion.** As gamma rolls off at monthly OPEX, suppressed volatility is released. The first 1-3 days after OPEX historically show higher realized volatility. _[Source: Window of Weakness / Price-Insensitive Flows Guide]_
- **RULE: Price "pinning" near high OI strikes pre-OPEX.** Before expiration, dealer hedging pins price near strikes with high open interest. This suppresses volatility but creates potential for explosive moves once the pin is released. _[Source: Price-Insensitive Flows Guide]_
- **RULE: Options delta-hedging flows dominate intraday in the final days before OPEX.** 0DTE and weekly options create significant gamma effects. These flows are mechanical, not directional -- and they vanish instantly at expiration. _[Source: Price-Insensitive Flows Guide]_

### 5.3 Session & Time-of-Day Risks
- **RULE: Pre-Market Session (4:00-9:30 ET) = 4% of daily volume.** Spreads are typically 2-4x wider than regular trading hours. Low liquidity means increased price manipulation risk. _[Source: Market Microstructure and Time of Day Analysis]_
- **RULE: 8pm-9pm EDT (00 UTC) = Asia session handoff + perp funding reset.** One of the five highest-vol hours. Perp funding resets can cause sharp moves in thin liquidity. _[Source: Bitcoin Intraday Cheat Sheet]_
- **RULE: Treat 00 UTC Asia open as "reset."** European flow often unwinds Asia extremes by 08-10 UTC. Positions taken in Asia session are vulnerable to London reversal. _[Source: Bitcoin Intraday Cheat Sheet]_
- **RULE: 3pm-4pm EDT (19-20 UTC) = ETF fixing window.** 6.7% of all spot BTC volume now prints here. Watch for late-day "basis snap" from creation/redemption hedging. _[Source: Bitcoin Intraday Cheat Sheet]_
- **RULE: Friday 3:55-4pm EDT = CME BRRNY reference rate calculation.** BTC Friday futures expire and ETF NAV is set. Micro-spikes in spot and CME basis -- beware of getting caught in the print. _[Source: Bitcoin Intraday Cheat Sheet]_
- **RULE: After-hours session (16:00-20:00 ET) = 3-5% of daily volume (spikes during earnings).** Spreads widen significantly. Liquidity concentrated in the first 30 minutes post-close. _[Source: Market Microstructure and Time of Day Analysis]_
- **RULE: European open window (02:00-04:00 ET) is the primary venue for global equity exposure during Asian hours.** Futures open trades here can set false direction that reverses at US open. _[Source: Market Microstructure and Time of Day Analysis]_

### 5.4 Calendar & Seasonal Risks
- **RULE: Quarter-end rebalancing creates headwinds after strong quarters.** Pensions and target-date funds sell winners. This is predictable, mechanical selling in the last week of March, June, September, December. _[Source: Price-Insensitive Flows Guide]_
- **RULE: Triple/quadruple witching adds options-related flows.** The convergence of multiple derivative expirations creates mechanical flows that can distort price. Do not trust moves on witching days as genuine directional signals. _[Source: Price-Insensitive Flows Guide]_
- **RULE: September OPEX creates an extended 5-week gap to October OPEX.** This creates the longest window without options support. Historical underperformance in September may partly be explained by this extended vulnerability. _[Source: Window of Weakness]_

---

## 6. Market Microstructure (Bearish Patterns)

### 6.1 Distribution & Selling Mechanics
- **RULE: "Controlled demolition" = institutional selling.** When price descends methodically through support levels with low volatility and consistent selling (not panic), this is institutional distribution. It looks orderly but is deeply bearish. _[Source: How Price Moves]_
- **RULE: "Building demolition" analogy -- when the support structure is removed.** If bid limits (the "floors" in the high-rise analogy) are pulled, price falls through a vacuum until it hits the next resting bid. The speed of the fall depends on the size of the vacuum. _[Source: How Price Moves]_
- **RULE: Institutional rebalancing day type.** On these days, large portfolio rebalances dominate price action. The moves are against the prevailing trend (forced selling in rallies, forced buying in selloffs). Do not trade these as trend days. _[Source: How Price Moves]_
- **RULE: News-driven day type = regime uncertainty.** News events create genuine uncertainty. The first move is usually wrong (news algo reaction). The second move is usually wrong too (retail reaction). The third move is often the real direction. _[Source: How Price Moves]_

### 6.2 Liquidity Dynamics (Bearish)
- **RULE: Liquidity vacuum below support = crash risk.** When there are no resting bid limits below a support level ("vacant floors" below), a break of support leads to a rapid freefall until the next zone of resting bids. These vacuums cause the sharpest drops. _[Source: How Price Moves]_
- **RULE: Vacuum-driven decline analysis -- check for the absence of counterparties.** During vacuums, there is no "selling pressure" -- there is simply no buying. The absence of bids, not the presence of aggressive selling, causes the sharpest drops. _[Source: How Price Moves]_
- **RULE: Support level interaction -- liquidation proximity.** When price approaches a support level in the context of high OI and leveraged positions, the support may hold initially but if breached, the liquidation cascade creates a vacuum below. _[Source: Market Microstructure and Time of Day Analysis]_
- **RULE: Spread costs vary by 3-10x across time periods.** Trading during low-liquidity periods (pre-market, overnight) exposes you to wider spreads and worse execution. This is a hidden cost that erodes edge. _[Source: Market Microstructure and Time of Day Analysis]_

### 6.3 Trapped Trader Mechanics (Bearish)
- **RULE: Trapped longs create fuel for declines.** When price breaks above a level, longs enter, then price quickly falls back below -- longs are trapped. Their stop-loss selling adds fuel to the decline. _[Source: Flow Playbook Intraday]_
- **RULE: London range trap (bearish).** London sets a range, then sweeps the Asian high before reversing down. The sweep traps Asian session longs. _[Source: Flow Playbook Intraday]_
- **RULE: Premarket sweep.** Premarket establishes false highs that trap early buyers, then NY open reverses. _[Source: Flow Playbook Intraday]_
- **RULE: Trapped trader reversal with delta + OI confirmation.** When OI builds at highs (longs entering) but delta diverges (sellers absorbing), the trapped long setup is confirmed. The reversal will be violent when the longs are forced to exit. _[Source: Flow Playbook Intraday]_
- **RULE: Wick fill targeting (bearish).** Long upper wicks at resistance that are not filled represent rejection. Target the opposite end of the wick for profit taking on shorts. _[Source: Flow Playbook Intraday]_

### 6.4 Intraday Bearish Setups
- **RULE: Failed IB (Initial Balance) breakout.** When the first 30-60 min range is broken to the upside but immediately fails, this signals a trap and potential trend day to the downside. _[Source: Flow Playbook Intraday]_
- **RULE: Engulfing reversal from resistance.** A bearish engulfing candle at a key resistance level with volume confirmation = strong reversal signal to the downside. _[Source: Flow Playbook Intraday]_
- **RULE: Monday range sweep (bearish).** If Monday sweeps above Friday's high early and then fails, weekend longs are trapped. The failure signals weakness for the week. _[Source: Flow Playbook Intraday]_
- **RULE: Round number rejection.** At major round numbers, failed breakouts create trapped breakout buyers whose stops add selling fuel on the reversal. _[Source: Flow Playbook Intraday]_
- **RULE: Grind day characteristics are bearish for momentum traders.** Multiple failed breakouts in both directions, high chop and noise within established ranges, mean-reversion tendencies at day levels, lower volume on moves. These days chew up directional traders. _[Source: ES Scalping Reference Guide]_

---

## 7. Crypto-Specific Bear Rules

### 7.1 Derivatives Warning Signs
- **RULE: Futures term structure inversion (near-dated > far-dated) = panic premium.** The market is willing to pay a premium to hedge RIGHT NOW. This urgency is almost exclusively associated with forced selling and capitulation events. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: OI divergence trap -- large OI buildup into bearish price candles (price down + OI up).** If price bleeds but OI rises, aggressive shorts are opening late OR longs are averaging down. Either way, stored energy for further violent moves. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: Liquidation cascade -- when >80% of liquidated capital is long positions.** This confirms forced selling is still in progress. Until the long liquidation cascade is complete, do not attempt to catch the bottom. _[Source: BTC Derivative Bottom-Signals Checklist]_
- **RULE: High positive funding = longs are paying to stay long.** Extreme positive funding means the long side is crowded and paying a premium. Any downside trigger creates cascading liquidations as overleveraged longs are ejected. _[Source: Flow Trading Crypto]_
- **RULE: USD vs stablecoin rails -- anchored markets (CME/Coinbase) and stablecoin perps move in different directions.** When this happens, a dislocation is forming. One side is wrong, and the resolution will be violent. _[Source: Flow Trading Crypto]_

### 7.2 Crypto Structural Risks
- **RULE: Crypto has no NBBO or consolidated quote.** Price discovery rotates between Coinbase (USD spot), Binance perps, and CME futures depending on hour and regime. Venue quirks (tick sizes, maker/taker fees, liquidation logic) differ across venues. This fragmentation creates execution risk. _[Source: Flow Trading Crypto]_
- **RULE: Binance perps stop leading microstructure moves by more than ~1-2 seconds = temporary leadership loss.** When the primary venue loses leadership, something unusual is happening. Check secondary venues for extreme one-sided flow, funding divergence, or liquidation data. _[Source: Flow Trading Crypto]_
- **RULE: More screens = more noise, not more truth.** Only zoom out to secondary venues when OI/liquidation data shows extreme one-sided flow, funding diverges sharply between venues, or the primary venue loses leadership. Otherwise, additional data sources add confusion. _[Source: Flow Trading Crypto]_

---

## 8. Commodity-Specific Bear Rules

### 8.1 Gold
- **RULE: Gold + rising real yields + strengthening USD = maximum bearish alignment.** This triple headwind is the strongest gold bear signal. _[Source: Gold Trading Guide]_
- **RULE: Gold ETF outflows = institutional selling.** When gold ETF holdings decline, institutions are actively reducing gold exposure. _[Source: Gold Trading Guide]_
- **RULE: Hawkish central bank surprise = immediate gold headwind.** Gold is inversely correlated with real rates. Unexpected tightening signals compress the bullion case. _[Source: Gold Trading Guide]_

### 8.2 Crude Oil
- **RULE: Contango deepening = oversupply.** When far-month futures trade at an increasing premium over near-month, the market is signaling excess supply and storage buildup. _[Source: Comprehensive Crude Oil Guide]_
- **RULE: Crack spread narrowing = demand destruction.** When the refinery spread narrows, refiners are losing profitability converting crude to products, reducing crude demand. _[Source: Comprehensive Crude Oil Guide]_
- **RULE: OPEC+ discipline breaking = supply flood risk.** When OPEC+ members cheat on quotas, the supply overhang can crash prices quickly. _[Source: Comprehensive Crude Oil Guide]_

---

## 9. Execution & Discipline Rules (Bearish Bias)

### 9.1 Stop-Loss & Risk Management
- **RULE: Maximum risk per trade -- never risk more than 1-1.5% of capital per trade.** For high-frequency scalping strategies, this is even more critical. Consistency of small losses beats occasional large ones. _[Source: Crypto Scalping Considerations]_
- **RULE: Consecutive daily loss limit -- set daily max loss at 3% of total capital.** After hitting the daily limit, stop trading. Emotional decisions after losses compound the damage. _[Source: Crypto Scalping Considerations]_
- **RULE: Concentration limit -- never commit more than 5% of capital to scaling positions simultaneously.** Concentration risk kills -- even in high-conviction setups. _[Source: Crypto Scalping Considerations]_
- **RULE: Leverage considerations -- use leverage cautiously. High frequency amplifies both gains and losses.** In volatile markets, leverage can turn a manageable loss into a catastrophic one. _[Source: Crypto Scalping Considerations]_
- **RULE: If short starts trading, close all positions 30 minutes before major scheduled events.** Event risk is binary and unhedgeable in size. _[Source: Trading the News]_

### 9.2 When NOT to Trade
- **RULE: If you cannot clearly articulate the context, trigger, entry, stop, target, and invalidation -- do not trade.** The absence of a clear plan is itself a reason not to trade. _[Source: Daily Trading Plan Card]_
- **RULE: VWAP balance zone (+/- 0.3 SD) = no-trade zone.** Price in the balance zone means neither side has edge. Taking positions here is gambling, not trading. _[Source: VWAP Trading Guide]_
- **RULE: Mixed CTA signals (some speeds long, some short) = regime uncertainty.** When the three CTA speeds disagree, systematic funds are conflicted. Wait for alignment before taking directional positions. _[Source: CTA Strategy Replication Cheat Sheet]_
- **RULE: "The tight stop fallacy."** Tight stops increase your odds of getting stopped out in volatile environments. Arbitrary stop distances (like "3 ticks") ignore market structure. Proper stops are structure-based, not distance-based. _[Source: ES Scalping Reference Guide]_
- **RULE: Style confusion leads to the worst of both approaches.** Do not turn a scalp into a swing trade when losing (hope), or a swing trade into a scalp when winning (fear). Define your timeframe before entry and stick to it. _[Source: ES Scalping Reference Guide]_
- **RULE: Must avoid FOMO and its content (keep losing prices moving -- 15-25 ticks).** Chasing missed moves leads to entering at the worst possible time. If you missed it, you missed it. _[Source: ES Scalping Reference Guide]_

### 9.3 Psychological Traps (Bear Side)
- **RULE: "Analysts don't think about anything else other than how smart they are."** Avoid the analyst trap of being married to your thesis. If the market is going up, you are wrong regardless of your analysis. The market is always right. _[Source: Finding an Edge]_
- **RULE: Revenge trading after a string of losses in either direction.** After consecutive losses, the urge to "make it back" leads to oversizing, ignoring stops, and emotional trading. The bear analyst must be as disciplined about taking bullish evidence seriously as spotting risks. _[Source: ES Scalping Reference Guide]_
- **RULE: Cannot accept losing full amount -- if that outcome is unacceptable, the position is too large.** Size every position so that the maximum loss is emotionally tolerable. If it is not, cut the size. _[Source: ES Scalping Reference Guide]_

---

## 10. Pre-Trade Bear Checklist

Before dismissing a bull case, URSA must verify these bearish conditions:

1. **Regime check:** Is price below any CTA speed (20/50/120 SMA)? Which ones? _[CTA Strategy Replication Cheat Sheet]_
2. **Volatility check:** Is VIX rising with price? Is VIX > 20? _[CTA Strategy Replication Cheat Sheet]_
3. **Flow check:** Is OI declining (longs exiting) or rising on down moves (shorts building)? _[Flow Trading Crypto]_
4. **Positioning check:** Who is trapped? Are there crowded longs? Extreme positive funding? _[Market Positioning Guide]_
5. **Level check:** Is price rejecting resistance? Has key support (50/200 SMA, VWAP, POC) been lost? _[Comprehensive BTC Levels Guide]_
6. **Structural flow check:** Are there price-insensitive sellers (pension rebalancing, ETF redemptions, leveraged ETF rebalancing)? _[Price-Insensitive Flows Guide]_
7. **Calendar check:** Are we in the Window of Weakness? Near quarter-end? Near OPEX? _[Window of Weakness]_
8. **Microstructure check:** Is there absorption at highs (distribution)? Icebergs on the ask? Delta divergence from price? _[How Price Moves]_
9. **Session check:** What time is it? Is liquidity thin? Are we in a session transition that historically reverses? _[Market Microstructure and Time of Day Analysis / Bitcoin Intraday Cheat Sheet]_
10. **Exhaustion check:** Is the selling itself exhausting? (If yes, the bear case may be played out -- shift to neutral.) _[Flow Playbook Intraday]_
