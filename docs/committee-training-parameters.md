# Committee Training Parameters
## The Trading Committee's Reference Bible

> **Purpose:** Discrete, numbered principles distilled from Nick's education library, approved strategies, bias indicators, and playbook. Each rule is machine-referenceable — agents can cite, confirm, or challenge by number.
>
> **Source materials:** 27 Stable education docs, playbook_v2.1.md, approved-strategies/, approved-bias-indicators/
>
> **How agents use this:** When evaluating a signal, cite relevant rule numbers in your analysis. When a rule supports or contradicts the trade, say so explicitly. Example: "Per M.04, this move looks like a stop-run sequence into thin liquidity — wait for resolution before entry."

---

## Section M: Market Mechanics

**M.01** — Price moves through liquidity, not to targets. Large orders consume available liquidity at each level; when a level is cleared, price jumps to the next cluster. Thin liquidity zones between clusters create the "vacuum" effect where price moves fast with minimal volume.

**M.02** — The "high-rise demolition" model: price collapses fastest when support is removed from the base (stops triggered below), not when selling pressure comes from above. Selling INTO bids depletes them; when key bid clusters are gone, price free-falls to the next support.

**M.03** — Iceberg orders (large hidden orders) reveal institutional intent. They appear as a level that keeps getting hit but doesn't move. Detecting icebergs on the bid = absorption of selling = potential reversal. On the offer = absorption of buying = potential top.

**M.04** — Stop-run sequence: Price sweeps an obvious level (prior low/high, round number), triggers stops, then reverses. The sweep itself is the trap — the real move is the reversal. Professional approach: wait for the sweep to complete, then trade the reclaim/rejection.

**M.05** — Day types determine viable strategies. Trend days reward continuation plays. Range/rotational days reward mean-reversion and fades. Volatile expansion days require wider stops and faster decisions. Low-vol compression days precede expansion — reduce size and wait for the breakout.

**M.06** — Delta divergence: when price makes a new high/low but delta (net aggressive buying minus selling) does NOT confirm, the move is exhausted. Divergence at key levels is a high-probability reversal signal.

**M.07** — The market is just positions. Price responds to who's long, who's short, how big, how leveraged, and where they're forced to act. Understanding positioning > understanding fundamentals for short-term trading.

**M.08** — Positioning layers: directional (outright long/short), leverage (margin, futures), Greeks (option delta/gamma/vanna exposure), basis (spot vs derivative spread), structured products (risk reversal, collar overlays). Each layer can force flows independently.

**M.09** — Classic forced-flow events: short squeeze (shorts forced to cover), long puke (longs forced to sell into weakness), gamma pin (dealer hedging pins price at strike), vanna flow (volatility changes force dealer delta adjustments). These are predictable when you know the positioning.

**M.10** — Positioning tells (observable signals): Open Interest changes, COT reports, GEX (Gamma Exposure), skew (put/call IV differential), VVIX (volatility of volatility), funding rates (crypto). These reveal WHERE forced flows will occur before they happen.

**M.11** — Spot leads derivatives. Aggressive spot buying → lifts offers → new reference price → arb bots reprice perps → market makers adjust → HFT detects and chases → stop/liquidation cascades → broader repricing. One aggressive spot trade can shift millions across venues.

**M.12** — Execution method matters: a single aggressive market order has far more impact than the same dollar size executed via TWAP algorithm. Low-liquidity periods (weekends, holidays, lunch hour) amplify the impact of any given trade.

**M.13** — Feedback loops where spot moves trigger derivative flows that affect spot prices can be destabilizing. Recognize when you're in a reflexive cycle — these accelerate until the fuel (leverage, positioning) is exhausted.

---

## Section F: Flow Analysis

**F.01** — Three core order flow behaviors: (1) Strength — aggressive volume moving price efficiently, (2) Absorption — large passive orders absorbing aggressive flow without price moving, (3) Exhaustion — aggressive volume failing to move price, delta declining. Each signals a different market state.

**F.02** — Trapped traders are the highest-probability setup. Identify: aggressive orders into a level (trapped longs buying highs or trapped shorts selling lows), confirm they're offside via footprint/delta, enter when price closes back through the trap zone. The trapped side provides fuel for the move.

**F.03** — Reclaim/rebid pattern: price breaks a level, fails to follow through, then reclaims back above/below. The failed breakout traps breakout traders; the reclaim triggers their stops and provides acceleration fuel.

**F.04** — ETF volume ≠ ETF flows. ETF shares trade secondary market without touching the underlying. Only creation (new shares minted by APs) and redemption (shares destroyed) move the underlying asset. $2B in ETF volume does NOT mean $2B of underlying was bought.

**F.05** — T+1 settlement quirk for ETFs: heavy buying on Day 1 shows as creation on Day 2. Monitor creation/redemption data, not volume, for actual flow impact.

**F.06** — Price-insensitive flows are trades that MUST occur regardless of price (index rebalancing, dealer hedging, pension rebalancing, leveraged ETF daily rebalance, corporate actions, VIX product rolls). Predictable in timing, often in magnitude. The market's forced-flow calendar.

**F.07** — Index rebalancing: S&P 500 tracked by ~$16T. Addition = forced buying. Deletion = forced selling. Russell reconstitution (June) = single largest trading day of the year. MSCI rebalancing critical for international flows ($15.6T benchmarked).

**F.08** — Dealer gamma position determines market character. Long gamma = dealers buy dips/sell rallies (suppresses volatility, mean-reversion favored). Short gamma = dealers sell dips/buy rallies (amplifies volatility, momentum/breakouts). Know the gamma environment before choosing strategy.

**F.09** — Gamma squeeze mechanics: heavy call buying → dealers short gamma → must buy stock as price rises → positive feedback. Most powerful with high short interest (GameStop-type events). Reverse gamma squeeze on put-heavy downside works the same way.

**F.10** — Leveraged ETF daily rebalance concentrates in the final 30 minutes. Large down day = leveraged ETFs must SELL into close. Large up day = must BUY into close. Effect strongest in low liquidity. TQQQ/SQQQ, SOXL/SOXS are key products.

**F.11** — Volatility-targeting and risk-parity funds adjust equity exposure based on realized volatility. Vol rises → they sell equities. Vol falls → they buy. Creates "air pocket" declines: selling → higher vol → more selling → cascading liquidation.

**F.12** — Calendar flow patterns: first trading day = positive bias (new month flows), month-end = rebalancing pressure, turn-of-month = positive (401k inflows), mid-month = weakest, quarter-end = window dressing + pension rebalancing, year-end = tax-loss harvesting + January effect.

**F.13** — Well-documented flow edges decay over time as more participants discover and front-run them. The S&P 500 inclusion effect declined from +7.4% (1990s) to +1.0% (2010s). Edge persists only in specific conditions (direct additions from outside S&P 1500, high short interest names, unique catalysts).

**F.14** — Structural buyers/sellers matter as much as data. When a major structural buyer changes behavior (e.g., MicroStrategy pausing BTC purchases), it shifts the entire supply/demand equation. Monitor structural flow sources like you monitor economic data.

**F.15** — Reflexive loops (buying creates conditions for more buying) are powerful but fragile. When the fuel source is disrupted, the loop breaks and the asset loses a key support mechanism. Identify the fuel; monitor for disruption.

---

## Section V: VWAP & Value

**V.01** — VWAP is the volume-weighted average price — where the average dollar was transacted. It's the institutional benchmark for "fair value" on the session. Price above VWAP = buyers in control. Below = sellers in control.

**V.02** — VWAP danger zone: ±0.3-0.5 standard deviations around VWAP is the "chop zone." Price oscillates without clear direction. Multiple reversals and minimal delta confirm the danger zone. Reduce size or avoid trading entirely when price is in this range.

**V.03** — Protective protocols near VWAP: establish no-trade boundaries around VWAP, require higher conviction signals to enter, use volume profile confirmation, and inverse-size to VWAP proximity (smaller positions closer to VWAP, larger positions at extremes).

**V.04** — Rolling VWAPs (2d, 3d, 7d, 30d) provide dynamic value areas at different timeframes. Price interaction with these levels reveals whether a move is a genuine breakout or just noise within a larger value area.

---

## Section L: Levels & Structure

**L.01** — Levels are NOT predictive — they are context anchors for interpreting price behavior. A level doesn't "cause" a reversal; it's where you watch for evidence that a reversal is occurring.

**L.02** — Level hierarchy (weakest to strongest): Session-based (overnight high/low, prior session extremes) → Volume Profile (POC, VAH, VAL) → Structural (4H swing highs/lows, daily/weekly levels) → Event-driven (FOMC candle, earnings gap). Higher-hierarchy levels produce stronger reactions.

**L.03** — Three-player dynamic at every level: (1) reversal traders betting on rejection, (2) breakout traders betting on continuation, (3) smart money that traps both. The professional approach: wait for the level to resolve (break or hold), then trade the first pullback/reclaim rather than betting on the outcome at the level.

**L.04** — Position sizing should vary by level quality. High confluence (multiple level types converging) = larger position. Single or questionable level = reduced size.

**L.05** — Stop placement: avoid obvious levels where everyone else's stops cluster. Place stops slightly beyond the manipulation zone — the extra few ticks of adverse movement that market makers and algos use to sweep stops before the real move.

**L.06** — Nick's charting setup uses specific technical levels: EMA 9/20/55, SMA 50/120/200, Rolling VWAPs 2d/3d/7d/30d. When discussing technical structure, reference these specific levels. SMA 50/120/200 = CTA trigger levels.

---

## Section E: Execution & Timing

**E.01** — Position scaling model: 25-40% initial entry, 30-50% on confirmation, 10-25% on momentum. Never enter full size at once. Scaling in allows you to manage risk if the thesis is wrong at the first entry.

**E.02** — Entry triggers (in order of reliability): (1) sweep of a level + close back through it, (2) absorption at a key level (aggressive orders failing to move price), (3) delta divergence at a level, (4) volume climax (extreme volume followed by reversal candle).

**E.03** — Time restrictions: No trades in the first 15 minutes after open (too noisy). Avoid 12-1pm ET (lunch hour, low liquidity, false signals). Flat by 3:30pm ET (avoid end-of-day rebalancing noise unless specifically trading that flow). Time after 10:00 AM ET for the Triple Line strategy.

**E.04** — Circuit breakers (personal discipline): 2 consecutive losses = 30-minute mandatory break. 3 losses in a day = done for the day. Daily max loss hit = close all positions. These are NON-NEGOTIABLE.

**E.05** — Time stop: if a trade hasn't reached Target 1 within 60 minutes, close or tighten stop to breakeven. Good trades work relatively quickly; if it's just sitting there, the thesis is likely wrong or the timing is off.

**E.06** — Pre-market regime classification is mandatory before trading. Classify: Trend Up, Trend Down, Range Bound, Volatile Expansion, or Low Vol Compression. Each regime dictates viable strategies. Trading a range strategy in a trend day (or vice versa) is the #1 cause of avoidable losses.

**E.07** — Screening discipline: Universe capped at 20 names. ATR rank top 30% (only trade things that move enough to be worth the risk). Must be near an HTF level. Event calendar must be clear (no earnings/FOMC imminent unless specifically trading the event). Shortlist max 3 names. No trading outside the shortlist.

**E.08** — One position at a time (for intraday execution). Don't stack positions that share the same risk factor.

**E.09** — A-setups only. If it doesn't check every box on the setup template (context requirements, entry trigger, clear invalidation), it's not an A-setup and doesn't get traded. B-setups and "kinda close" setups are how accounts bleed to death.

**E.10** — Event-driven execution framework: around major releases (CPI, NFP, FOMC), treat the event like earnings — define your position BEFORE the event, size for the expected move, and accept that you'll be wrong some of the time. Don't react-trade the first candle.

**E.11** — Institutional dead zones are where retail has structural edge: liquidity voids during CPI/FOMC when algos widen or disable, panic wicks where institutions are forced sellers, euphoria spikes where momentum algos overshoot. These are opportunities, not threats.

**E.12** — 12 recognized intraday setups (from Flow Playbook): Small Initial Balance, Monday Range Sweep, Asian Liquidity Trap, Round Number Reversal, Fast Spike + Trapped Delta, Wick Fill Reversal/Targeting, Trapped Trader Reversal, London Range Trap, Premarket High/Low Sweep, Inside Day, Engulfing Reversal. Each has specific context requirements. Citing the setup name in committee analysis helps Nick pattern-match.

---

## Section R: Risk Management

**R.01** — Most retail blow-ups come from SIZING, not thesis. Over-leverage kills. Even correct theses lose money if position size is wrong. This is the single most important risk principle.

**R.02** — Account-specific risk limits:
- **401(k) BrokerageLink (~$8,100):** Max 1% per trade (~$81). High-conviction exception exists but requires explicit override acknowledgment.
- **Robinhood (~$4,698):** Max 5% per trade (~$235), ONLY for asymmetric setups with strong conviction and bias alignment. Defined-risk strategies preferred.
- **Breakout Prop (~$25,000):** Personal max daily loss 2.5% (~$620). Personal drawdown floor adds $500 cushion above the account's real trailing drawdown floor. Never use more than 50% of daily loss allowance.

**R.03** — DEFCON circuit breaker system:
- **YELLOW** (single signal fires): Pause, assess 15-30 minutes, check all positions, resume if resolved.
- **ORANGE** (2+ signals or high-severity single): No new trades, tighten all stops, cancel working orders, consider reducing exposure.
- **RED** (3+ signals or extreme severity): Flatten everything, capital preservation only, no re-entry until next session minimum.

**R.04** — Monitored DEFCON signals: VIX spike (level + speed), SPY below key MAs (50/200-day), TICK breadth extremes, SPY gap >1% at open, VIX term structure inversion, cross-asset correlation spike, Black Swan system trigger, daily loss limit approaching.

**R.05** — Undefined-risk options (naked calls/puts): Always flag theoretical max loss, whether a defined-risk alternative achieves similar exposure, current margin impact, and proximity to earnings/catalysts. Nick uses these selectively but they require extra scrutiny.

**R.06** — Options risk assessment checklist (in order): (1) Which account? (2) Bias alignment? (3) Max loss calculation. (4) Risk/reward ≥ 2:1 minimum, 3:1+ for homerun swings. (5) IV context (buying premium = want low IV, selling = want high IV). (6) DTE appropriateness (>21 DTE for swings, <7 DTE only for intentional scalps). (7) Catalyst proximity. (8) Liquidity (bid-ask <$0.05 ideal, OI >500, meaningful volume). (9) Current portfolio exposure and correlation.

**R.07** — IV environment decision framework: IV rank >50 = lean toward selling premium. IV rank <30 = lean toward buying premium. 30-50 = let bias and setup dictate. Extremely high IV (>80) = rich premium to sell, but respect why IV is elevated.

**R.08** — Post-trade logging is mandatory: P&L, win rate, average R, regime accuracy, setup quality, entry timing, exit efficiency, rules broken (Y/N), key lesson, tomorrow's focus.

---

## Section S: Approved Strategies & Indicators

### S.01 — Triple Line Trend Retracement (VWAP + Dual 200 EMA)

**Indicators:** VWAP (daily anchored), 200 EMA on 1-min chart, 200 EMA on 5-min chart, ADX (14-period).

**Long setup:** Price above all three lines, bullish stack order, lines separated by ≥10 points (no tangling), ADX > 25, 200 EMA 1-min sloping upward, time after 10:00 AM ET. Entry: pullback to EMA/VWAP zone + bullish engulfing/hammer, OR break above pullback high.

**Short setup:** Price below all three lines, bearish stack, ≥10 point separation, ADX > 25, 200 EMA 1-min sloping downward, time after 10:00 AM ET. Entry: pullback to EMA/VWAP zone + bearish engulfing/shooting star, OR break below pullback low.

**Stop:** 2-5 points beyond the furthest EMA/VWAP line in the zone, or beyond pullback swing point (whichever tighter).

**Targets:** T1 at 1:1 R:R (take 50%), trail remainder using 200 EMA 1-min or fixed 50+ point target.

**Time exit:** If T1 not reached within 60 minutes, close or tighten to breakeven.

**No-trade conditions:** Before 10:00 AM ET, ADX < 25, lines within 10 points (tangled/choppy), 200 EMA 1-min flat.

**Timeframe:** 5-minute chart. Instruments: NQ, ES, or similar liquid index futures.

### S.02 — CTA Flow Replication Strategy

**Core framework:** Three-speed SMA dashboard (20-day, 50-day, 120-day). Price position relative to these SMAs determines CTA positioning zones.

**Trigger zones:** Max Long (above all three), De-Leveraging (drops below 20-day), Waterfall (drops below 50-day), Capitulation (drops below 120-day). Reverse for short side.

**Volatility filter:** Rising price + falling VIX = real rally. Rising price + rising VIX = suspicious.

**Execution rules:** Two-Close Rule (need two consecutive closes above/below the SMA, not just one). Volume Lie Detector (breakout must be accompanied by above-average volume). 120 SMA = "Golden Trade" (the most significant CTA trigger level — breaks here cause the largest systematic flow).

### S.03 — TICK Range Breadth Model (Raschke Method)

**Indicator:** NYSE TICK ($TICK) daily high and low values.

**Daily bias:** TICK high >+1000 OR TICK low <-1000 (wide range) = Bullish. TICK high <+500 AND TICK low >-500 (narrow range) = Bearish. Mixed = Neutral.

**Weekly bias:** Count wide vs narrow range days over trailing 5 sessions. 3+ wide = Bullish weekly. 3+ narrow = Bearish weekly.

**Bias level mapping:**
- Toro Major: 4+ wide days + current day wide
- Toro Minor: 3 wide OR bullish daily but mixed weekly
- Neutral: Mixed signals or mid-range
- Ursa Minor: 3 narrow OR bearish daily but mixed weekly
- Ursa Major: 4+ narrow days + current day narrow

**Interpretation:** Wide TICK = strong breadth participation, institutions active across many stocks = favors long continuation. Narrow TICK = low conviction, weak participation, vulnerable to selling = favors short bias or caution.

---

## Section B: Bias System

**B.01** — Five-level bias framework: Ursa Major (-2), Ursa Minor (-1), Neutral (0), Toro Minor (+1), Toro Major (+2). This is the foundation of all trade selection.

**B.02** — Never trade against the higher-timeframe bias unless you have an explicit mean-reversion edge within a clear range. Higher timeframe bias governs direction; lower timeframe provides entry timing.

**B.03** — Neutral means CAUTION, not default. Reduce size, favor non-directional strategies (iron condors, strangles), or stay flat. Neutral is a genuine reading, not the absence of a signal.

**B.04** — Bias transitions are signals themselves. A shift from Toro Major to Toro Minor is a yellow flag even though it's still bullish. Deteriorating conviction matters even before the bias flips.

**B.05** — Nick's personal macro bias (currently bearish due to political/fiscal/geopolitical concerns) may differ from the system bias. When they conflict: system bias governs short-term trade direction; Nick's macro view governs portfolio-level positioning and theme selection.

**B.06** — Bias challenge protocol: Nick has documented tendencies toward AI-bullishness and macro-bearishness. Committee agents — especially URSA — should actively flag countersignals to these biases. Challenging bias with evidence is explicitly part of the job.

**B.07** — Three-tier signal hierarchy: (1) Macro Bias (weekly/monthly regime — what direction is the tide flowing?), (2) Daily Bias (today's TICK breadth, overnight positioning, gap context), (3) Execution signals (intraday triggers from approved strategies). Execution signals must align with at least one higher tier to be tradeable.


---

## Section P: Edge & Philosophy

**P.01** — Risk premia = compensation for bearing systematic risks others dislike. Structural, persists for decades, mechanically replicable. Alpha = exploiting market inefficiencies. Fragile, decays when discovered, limited capacity. Most skilled traders operate in the "edge-enhanced premia" zone — warehousing the same risks as everyone else but with superior timing, hedging, and sizing.

**P.02** — "If you cannot articulate exactly which risks you're being paid to warehouse, you're probably not generating alpha — you're simply calling your risk premia collection 'skill.'" Every committee analysis should implicitly identify what risk is being taken and whether the compensation is adequate.

**P.03** — During liquidity booms, all risk factors pay simultaneously, making everyone look like a genius. This is when discipline matters most — the easy gains mask deteriorating risk/reward. Committee should flag "everything working" as a warning sign, not confirmation of skill.

**P.04** — Any edge discussed publicly is already compromised. Documented anomalies (index inclusion effect, calendar effects, etc.) decay as more participants discover and front-run them. The committee should discount well-known patterns and focus on conditional edges (specific subsets where the pattern still holds).

**P.05** — Retail's structural advantages: zero mandate (can sit in cash for weeks), invisible at small size, no career risk (can flip thesis instantly), access to products institutions can't touch easily (0-DTE, micro futures, DeFi). The committee should actively consider whether a setup exploits institutional constraints.

**P.06** — Retail's structural weakness is SIZING. Over-leverage is the #1 killer. "Trade small, learn fast, and let their constraints be your opportunity." Committee sizing recommendations should always err conservative.

**P.07** — Michael Platt principle: seek edge-finders who exploit inefficiencies, avoid value calculators who don't stop out. The committee should prioritize setups with clear invalidation over "the stock is cheap" thesis.

**P.08** — Know what ACTUALLY drives the asset you're trading. Different assets respond to fundamentally different catalysts. Equities respond to earnings + macro. Gold responds to real yields + USD. Oil responds to physical supply/demand + OPEC. Crypto responds to liquidity + positioning + narrative reflexivity. Don't apply the wrong framework.

**P.09** — Reflexive loops (buying creates conditions for more buying) are powerful but require fuel (new money, leverage, narrative). When the fuel source is disrupted, the loop breaks. Committee should identify whether a trend is reflexive and whether the fuel source is intact.

---

## Section A: Asset-Specific Notes

**A.01** — Gold is a macro-financial asset disguised as a commodity. Core driver hierarchy: (1) Real yields (falling = bullish), (2) USD strength (inverse), (3) Monetary policy/Fed, (4) Central bank reserve buying, (5) ETF flows, (6) Geopolitics/safe-haven. Supply/demand is NOT a primary driver — gold has massive above-ground reserves and demand is anchored in financial perception.

**A.02** — Gold "safe haven" narrative only works if positioning isn't already overloaded. If everyone is already long gold for safety, the incremental bid from a new crisis is limited. Check positioning before assuming the safe-haven trade will work.

**A.03** — Crude oil driver hierarchy: (1) Physical supply disruptions (strongest), (2) OPEC decisions, (3) Inventory data, (4) Economic/demand data, (5) Technicals (weakest). Term structure matters: backwardation (near > far) = tight physical market. Contango (far > near) = oversupply.

**A.04** — BTC/Crypto driver hierarchy: (1) Liquidity conditions (macro liquidity = crypto liquidity), (2) ETF flows (creation/redemption, not volume), (3) Structural buyer behavior (MicroStrategy, sovereign buyers), (4) Derivatives positioning (funding rates, OI, liquidation levels), (5) Narrative/reflexivity. Crypto amplifies everything — same mechanics as equities but with 5-10x volatility.

**A.05** — Crypto "alpha" illusions to watch for: small-cap rotation (higher beta to same liquidity cycles), DeFi yields (payment for smart contract risk, not skill), perp funding capture (short-vol carry trade that reverses in stress), social media signals (usually late-stage reflexivity where you're exit liquidity).

**A.06** — MicroStrategy (MSTR) policy status as of mid-2025: Shifted from opportunistic BTC buying (any premium >1.0×) to disciplined NAV-based (only if mNAV >2.5×). This effectively pauses one of Bitcoin's top-three structural demand sources. Monitor mNAV premium as a leading indicator for when this structural bid returns. Current mNAV ~1.7× means ATM equity sales on hold.

**A.07** — Venue hierarchy matters: Binance dominates crypto price discovery for spot. In equities, NYSE/NASDAQ set reference prices. Trades on the dominant venue have outsized impact on prices across all other venues.

---

## Section D: Discipline & Psychology

**D.01** — Log every trade. No exceptions. Post-market review: P&L, win rate, average R, regime accuracy, setup quality, entry timing, exit efficiency, rules broken (Y/N), key lesson, tomorrow's focus.

**D.02** — Rules broken is a binary question in the post-trade review. If the answer is yes on multiple days in a row, the problem isn't the market — it's discipline. Committee should flag when recommendations are being overridden frequently as a pattern worth examining.

**D.03** — Bias check on losing streaks: if Nick is taking repeated losses on bearish trades (his default macro bias), the committee should raise: "Is the market telling you something about your macro thesis timing?"

**D.04** — When multiple committee agents agree with high conviction and Nick overrides → track the outcome. This builds the data set for calibrating when Nick's instincts add value vs. when the committee's systematic analysis is more reliable.

**D.05** — The committee exists to reduce cognitive load. Nick has ADHD. The system handles "keeping track of everything" so he can focus on the execution decision. Each recommendation should be concise, structured, and end with a single clear action.

**D.06** — Perfectionism and boredom are documented derailers. Boredom leads to B-setup trading (see E.09 — A-setups only). Perfectionism leads to missed entries while waiting for the "perfect" setup. Committee should flag both patterns when observed.

---

## Section C: CTA & Systematic Flow Context

**C.01** — CTA (Commodity Trading Advisor) strategies are systematic, rules-based trading programs that collectively manage hundreds of billions of dollars. Their signals are based on moving average crossovers and trend following. When CTA levels break, the flows are massive, predictable, and mechanical.

**C.02** — The three CTA speeds: 20-day SMA (fast — tactical), 50-day SMA (medium — primary trend), 120-day SMA (slow — structural). When all three align, CTA positioning is at maximum. When they diverge, CTAs are de-leveraging.

**C.03** — 120-day SMA is the "Golden Line" — the most significant CTA trigger. A break below the 120-day SMA triggers the largest systematic selling. A reclaim above the 120-day SMA triggers the largest systematic buying. These moves can persist for days as the flow works through the market.

**C.04** — Two-Close Rule: a single close above/below a CTA level is not enough. Wait for two consecutive closes to confirm the break/reclaim. First close = alert. Second close = confirmed signal.

**C.05** — Volume Lie Detector: a CTA level break must be accompanied by above-average volume to be genuine. Thin-volume breaks on holidays or low-liquidity sessions are more likely to reverse.

**C.06** — Volatility filter: rising price + falling VIX = real rally (genuine risk appetite). Rising price + rising VIX = suspicious (likely hedging flow or positioning adjustment, not conviction buying).

---

*Last updated: 2025-02-28*
*Source materials: 27 Stable education docs, playbook_v2.1.md, approved-strategies/, approved-bias-indicators/*
*Total rules: 89 discrete numbered principles across 10 sections*
