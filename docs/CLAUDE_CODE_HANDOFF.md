# Pivot — Strategy & Trading Education Reference

**Last Updated:** February 19, 2026

> **⚠️ NOTE:** This file was originally a handoff document from early development (Jan 2026). The implementation specs are outdated — see `CLAUDE.md` and `DEVELOPMENT_STATUS.md` for current architecture. The strategy and trading education content below remains a useful reference.

---

## Current Architecture Reference

For up-to-date information, read these instead:
- `CLAUDE.md` — Architecture, key files, commands
- `DEVELOPMENT_STATUS.md` — Phase roadmap, what's built, what's planned
- `PROJECT_RULES.md` — Trading rules, agent maintenance protocol
- `pivot/llm/playbook_v2.1.md` — Current trading rules and risk parameters

---

# EQUITY SWING TRADING STRATEGY: CTA Replication

### Core Indicators: 20/50/120 Day SMAs

| Zone | Condition | Bias | Action |
|------|-----------|------|--------|
| **MAX_LONG** | Price > 20/50/120 SMAs | BULLISH | Buy pullbacks to 20 SMA |
| **DE_LEVERAGING** | Price < 20, above 50 | NEUTRAL | Watch 50 SMA, reduce size |
| **WATERFALL** | Price < 50 SMA | BEARISH | Short bias, fade rallies |
| **CAPITULATION** | 20 SMA < 120 SMA | BEARISH | Sell rallies only, no longs |

### Signal Types (Priority Order)

1. **GOLDEN_TOUCH** (Score: 100) — First touch of 120 SMA after 50+ days above, 5-8% correction, 20 SMA still above 120. Rare but highest probability.
2. **TWO_CLOSE_VOLUME** (Score: 80) — 2 consecutive closes above 50 SMA with volume >10% above 30-day average. Primary entry signal.
3. **VOLUME_BREAKOUT** (Score: 60) — Price crosses above 50 SMA with volume confirmation.
4. **PULLBACK_ENTRY** (Score: 50) — In MAX_LONG zone, price pulls back to within 1.5% of 20 SMA, bounce confirmed.
5. **ZONE_UPGRADE** (Score: 40) — Transition to more bullish zone. Watchlist alert, wait for confirmation.

### Filters (Reject Signals When)

1. **VIX Divergence:** VIX rising + Price rising = FAKE RALLY
2. **Window of Weakness:** Monday-Wednesday after monthly OPEX
3. **Low Volume:** Volume < 30-day average on breakout
4. **Poor R:R:** Calculated R:R < 1.5:1

### Risk Management

- **Stop Calculation:** Key SMA - (ATR × 1.5)
- **Target Calculation:** Entry + (Risk × 2.0) for 2:1 R:R
- **Max risk per trade:** 5% of account
- **Max correlated positions:** 2

---

# BTC/CRYPTO INTRADAY FRAMEWORK

## Key Horizontal Levels

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

## Volume Profile Levels
- **POC (Point of Control):** Price with most volume — acts as magnet
- **VAH (Value Area High):** Upper 70% volume boundary
- **VAL (Value Area Low):** Lower 70% volume boundary
- **Poor Highs/Lows:** Single prints — unfinished auctions

## BTC Trading Sessions (All Times ET)

| NY Time (EDT) | UTC | What Happens | Why It Matters |
|---------------|-----|--------------|----------------|
| **8pm-9pm Sun-Thu** | 00 UTC | Highest-vol hours; Garman-Klass σ spike | Asia session hand-off + perp funding reset |
| **4am-6am** | 08-10 UTC | London cash FX open → depth builds | Good for passive fills / iceberg execution |
| **11am-1pm** | 15-17 UTC | Peak global volume, vol & illiquidity | Best window for breakout scalps |
| **3pm-4pm** | 19-20 UTC | ETF fixing window — 6.7% of all spot BTC volume | Creation/redemption hedging |
| **Fri 3:55pm-4pm** | 19:55-20:00 UTC | CME BRRNY reference-rate calculation; futures expire | Micro-spikes in spot and CME basis |

### Session Bias Rules
- **Fade mean-reversion ideas** until after 15-17 UTC volume crest
- **Treat 00 UTC Asia open as "reset"** — European flow often unwinds Asia extremes by 08-10 UTC

## Three-Player Dynamic at Levels
1. **Reversal Traders:** Expect bounce/rejection
2. **Breakout Traders:** Enter on level breaks
3. **Smart Money:** Traps both groups before real move

---

# BTC DERIVATIVE BOTTOM-SIGNALS CHECKLIST

*"We are not guessing price; we are identifying the structural exhaustion of sellers and the reset of leverage."*

### Signal 1: 25-Delta Skew — Extreme Negativity
Options Skew drops significantly below zero (puts much more expensive than calls). Market is panic-bidding puts; dealers must short futures to hedge. When skew hits extreme lows, market is fully hedged; dealers buy back hedges creating vanna/charm tailwind.

### Signal 2: Quarterly Basis — Compression to Parity
Annualized futures premium collapses to near 0% (or flips negative). Compression toward ~0% confirms speculative longs are washed out, leverage reset.

### Signal 3: Perp Funding — The Negative Flip
Funding rates flip from positive to negative across major venues. Shorts are now paying longs; crowd is chasing downside. Creates fuel for short squeeze.

### Signal 4: Stablecoin APRs — The Apathy Floor
Borrow rates for USDT/USDC collapse to base rate (near 0%). DeFi stablecoin borrowing is primarily for levering into risk assets. Low APRs = apathy, speculative froth gone.

### Signal 5: Term Structure — Inversion
Near-dated futures trade HIGHER than far-dated futures. Market willing to pay premium to hedge RIGHT NOW. Urgency = forced selling/capitulation; unsustainable, marks end of trend.

### Signal 6: Open Interest — The Divergence Trap
Large OI build-up into bearish price candles (Price Down + OI Up). Aggressive shorts opening late OR longs averaging down. Price tick up = late shorts immediately underwater.

### Signal 7: Liquidation Composition — The "80/20" Rule
Total liquidation volume dominated by Longs (>80%). Bottom cannot form if shorts getting squeezed. >80% Long liquidations = over-leveraged bulls forcibly ejected.

### Signal 8: Spot Orderbook Skew — The Wall of Bids
Bid-side liquidity heavily outweighs ask-side at 1-10% depth. Derivatives noisy; spot is truth. Thicker bid side = smart money deploying passive capital.

### BONUS: VIX Spike — Macro Confirmation
VIX spikes vertically (30+). BTC acts as high-beta liquidity sponge. If signals 1-8 firing while VIX crushing equities = generational opportunity.

### The Cluster Effect (Execution Logic)

**No single metric is a silver bullet. The signal is the CLUSTER.**

Bottom Checklist:
- Skew: Extreme negative (fear peaked)
- Funding: Flips negative (shorts crowded)
- OI: Rising into the lows (trap set)
- Spot Book: Bid-side dominance (absorption)
- Basis: Compressing near 0% (leverage reset)
- Stable APRs: Collapse to base rate (apathy)
- Liqs: >80% longs (bulls washed out)
- Macro: VIX spiking (global capitulation)

**THE VERDICT:** When forced sellers (Long Liqs) dump into passive buyers (Spot Book), while dealers hedge (Skew) and funding flips negative... that's a bottom.

---

# ETF FLOW STRUCTURE

## Two Markets — Critical Understanding

**Secondary Market (What you see on screen):** Where retail trades ETF shares on exchange. Just trading existing shares. Does NOT automatically mean new BTC was bought.

**Primary Market (The "Flows"):** Between ETF and authorized participants/market makers. Where new ETF shares get created/redeemed. This is what people mean by "flows."

### Creation Process (Positive Flow)
Heavy buying → ETF price trades rich to NAV → MM sells ETF shares (goes short) → MM creates units in primary market → MM delivers BTC to get newly created shares → MM uses shares to flatten short. Result: ETF now holds more BTC.

### Redemption Process (Negative Flow)
Heavy selling → MM buys ETF shares (goes long) → MM redeems with ETF → MM gives shares, gets back BTC. Result: ETF shrinks.

### Critical Insight: Volume ≠ Flows
- 2B traded does NOT mean 2B of BTC was bought
- If Alice buys 100 shares and Bob sells 100 shares = 100 volume, ZERO creation
- ETF only moves when MM inventory gets offside enough
- **Timing quirk:** Creations settle T+1, trades settle T+2

---

*Strategy content derived from Ryan's Market Profile + Order Flow educational materials.*
