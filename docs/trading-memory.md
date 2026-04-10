# TRADING MEMORY — Pandora's Box / Olympus Committee
# Last updated: April 10, 2026
# Location: C:\trading-hub\docs\trading-memory.md
# Rule: Read this file before ANY trading discussion, committee review, or position analysis.
#       Update it whenever trades open/close or macro conditions change.

---

## ⏰ TIME AWARENESS (MANDATORY)

**Every Claude agent must note the exact current time at the start of any trading discussion.**
State: current time (ET and MT), market status, and days to next major catalyst.

Market session windows (all Eastern Time):
- Pre-market: 4:00-9:30 AM — analysis and planning only
- First 30 min: 9:30-10:00 AM — noise, do NOT react to moves here
- Prime time: 10:00 AM-11:30 AM — best execution window
- Midday: 11:30 AM-2:00 PM — low volume, chop
- Power hour: 3:00-4:00 PM — end-of-day flows, institutional activity
- After hours: 4:00-8:00 PM — analysis only, thin liquidity
- Weekend/holiday: Analysis, planning, briefs only

**Why this matters:** A signal at 9:35 AM is noise. The same signal at 10:15 AM is actionable.
Friday afternoon selloffs often continue Monday. Weekend ceasefire news can gap positions.
Always frame analysis in the context of WHEN it's happening.

---

## ⚠️ TRIP WIRE STATUS (check every session)

Close ALL shorts if ANY TWO hit simultaneously:
1. SPX reclaims 200 DMA ~6,600 for 2 consecutive closes — NOT FIRED
2. Brent below $95 — ✓ FIRED (Apr 8)
3. Ceasefire + Hormuz reopening — ✓ FIRED (fragile, Iran demands unlikely met)
4. VIX below 20 for 48 hours — NOT FIRED (VIX back above 20 as of Apr 10)

**STATUS: 2 of 4 fired. Nick has NOT acted. Ceasefire fragile.**
**RULE: If a 3rd trip wire fires during ANY conversation, FLAG IT IMMEDIATELY.**

---

## 🧠 NICK'S BEHAVIORAL PATTERNS (actively counter these)

1. **Right on direction, late on exits.** Enforced by the <21 DTE profit-taking rule.
2. **Holds winners too long hoping for perfection.** Counter: take 60-70% of max and redeploy.
3. **Generates too many new trade ideas when capital frees up.** Counter: evaluate existing positions FIRST. Ask "should you add to a current position instead?"
4. **Overthinks and gets off task.** If Nick is spiraling, ask a sharp grounding question.

---

## 🚫 DON'TS (hard rules for every discussion)

- Don't open new positions without checking existing book first
- Don't trade ADRs or illiquid names with wide bid-ask spreads (>20% of ask)
- Don't short into mechanical flow events (pension rebalance, OpEx, collar roll)
- Don't hold Bucket 2 losers past 3 trading days
- Don't buy watchlist names into gap-up rally days
- Don't chase — if entry is >2% past the signal price, the trade is gone
- Don't ignore trip wires — if 2+ fire, the thesis may be invalidating

---

## 📰 HEADLINE / POLITICAL RISK AWARENESS

**This market is extremely headline-driven.** Before any trade discussion, agents MUST search
for recent headlines — especially from the Trump administration — that could be moving markets.
Executive orders, tariff threats, ceasefire announcements, sanctions, energy policy shifts, and
social media posts from @realDonaldTrump can move indexes 2-3% in minutes.

### The "TACO" Trade (Talk And Capitulate Often)
The market consistently assumes Trump won't follow through on outlandish threats or claims.
He makes extreme statements constantly (tariffs, military strikes, policy reversals), and the
market's default reaction is to price in a walkback. **This creates a systematic edge for anyone
who takes the threats seriously when the market doesn't.** The stonXBT principle applies: watch
what physically happens (ships, sanctions enforcement, troop movements), not what's tweeted.

**Rule for agents:** When Trump makes a dramatic announcement, do NOT default to "the market
will shrug it off." Check whether physical actions are following the rhetoric. If ships stop
transiting or tariffs actually get implemented, the market reprices violently.

### AI Disruption Context
AI developments cause massive market reactions — both up and down. DeepSeek-style disruptions
can crater AI stocks 10-20% in a day. New model releases or capability demonstrations can
spike them similarly. **We are likely in a massive AI bubble that should NOT be longed
irresponsibly.** Nick's PLTR LEAPS put is a direct expression of this view.

**Rule for agents:** All trade discussions involving tech/AI names must acknowledge bubble risk.
Do not recommend LONG positions in high-multiple AI names without explicitly addressing the
valuation risk and the possibility of a DeepSeek-style disruption event.

---

## 📊 MACRO DATA FILE

**See:** `C:\trading-hub\docs\macro-economic-data.md` (also on GitHub)

That file contains current economic data points (CPI, unemployment, GDP, PCE, etc.),
hub data pipeline endpoints, and historical context. Reference it for any macro discussion.

**Monthly cleanup rule:** Macro data older than 2 months should be compressed or archived
during the first Battlefield Brief of each month. Keep only the most recent 2-3 prints
per indicator plus any historically significant data points. Agents should not rely on
data points older than 60 days without verifying they're still current.

---

## CURRENT POSITIONS (update whenever trades open/close)

### Robinhood — Bearish Book (~$1,123 deployed)
- HYG $76/$74 put x3 Jun18 — $195 risk / $7,510 max — HOME RUN. Thesis: private credit contagion (Quinn Step 2-3) cracks high-yield bonds. HYG broke $80 on Apr 10.
- PLTR $60/$50 put x1 Jan27 — $77 risk — LEAPS. Thesis: AI valuation reset as macro deteriorates. Fire-and-forget.
- XLY $100/$90 put x2 Jun18 — $300 risk — Thesis: consumer exhaustion (savings rate 4.0%, lowest since 2008). Discretionary spending contracts.
- GLD $425/$420 put x2 May1 — $282 risk — Thesis: gold overextended near ATH, pullback setup. Pairs with Fidelity GDX tranche (buy shares after gold pulls back).
- TSLA $240/$230 put x1 Jun18 — $59 risk — Thesis: broad market correction hits high-multiple names hardest.
- BX $95/$85 put x1 May15 — $110 risk — Thesis: Blackstone is ground zero for private credit stress. EARNINGS APR 17.
- JETS $24/$20 put x2 May15 — $100 risk — Thesis: elevated oil + consumer weakening + airlines overextended. Cut if no movement by late Apr.

### Robinhood — Bullish Book (~$435 deployed)
- IBIT $43/$47 call x3 Apr20 — $114 risk — Thesis: BTC showing relative strength vs equities in chop. HARD EXIT Wed Apr 15 if <$42.
- NEXT $8/$10 call x3 May15 — $105 risk — Thesis: US LNG exporter, direct Hormuz beneficiary. "Asia wants more US LNG." Committee approved. EARNINGS May 5.
- DBA $29/$34 call x3 Oct16 — $216 risk — Thesis: ag supply disruption from Hormuz (urea/fertilizer). 6 months runway. No management needed.

### Fidelity Roth IRA (~$8,500)
- Tranche 1 FILLED: JEPI + EFA
- Tranche 2 PENDING: GDX $500 (trigger: gold pullback to $4,400-4,500 holds 3 days)
- Tranche 3 PENDING: URA $500 (trigger: pullback to $40-42)
- Tranches 4-5 PENDING: JEPI + EFA ($750 each, triggers: SPX breaks 6,400 / recession confirmed)
- Cash reserve: $2,500

### Closed/Expired
- DAL $60/$56 put — expired Apr 10 worthless
- UNG $15/$20 call x6 — expired Apr 17 worthless

---

## WATCHLIST
- XLV: Healthcare sector ETF — defensive + AI exposure. Wait for clean pullback + hub signal with new scoring.
- GDX/NEM: Gold miners for Fidelity Roth Tranche 2. Trigger: gold $4,400-4,500 holds 3 days.
- URA: Uranium ETF for Fidelity Roth Tranche 3. Trigger: pullback to $40-42.

---

## GAME PLAN

### Week of Apr 13-17
- IBIT: Hard exit Wed Apr 15 if not above $42
- BX EARNINGS Apr 17 (Thu pre-market): Hold through. If BX disappoints on private credit, puts go ITM
- JETS: If not below $23 by Fri Apr 18, cut for salvage
- Monitor ARGUS Phase 2 signals — first week with Pythia + flow + regime scoring live

### Week of Apr 20-24
- IBIT expires Apr 20 — resolved
- GLD puts approaching May 1 expiry — if gold >$450, cut by Apr 25 for salvage value
- If gold pulling back: prepare Fidelity Roth Tranche 2 (GDX)

### Week of Apr 27-May 1
- GLD put expiry May 1
- BMY earnings Apr 30 — NOT in book, but watch as Phase 2 validation

### Week of May 5-9
- NEXT earnings May 5: Sell 2 of 3 spreads before report if profitable, hold 1 as lotto
- Begin evaluating May 15 cluster exit strategy

### Week of May 12-15
- BX, JETS, NEXT all expire May 15 — BIG DECISION WEEK
- Determine if credit thesis is accelerating (HYG) or stalling

### Ongoing
- HYG: Don't touch unless Tier 2 exit (~10-12% correction). This is the home run.
- PLTR: Fire-and-forget until Jan 2027
- DBA: No management needed for months
- Sunday evenings: Battlefield Brief with ARGUS Phase 2 data

---

## 🔮 PYTHIA READING GUIDE (for interpreting market profile data)

When Nick shares a Pythia chart or profile data, here's how to read it:
- **VAH/VAL/POC**: Value Area High, Low, and Point of Control. Where 70% of volume traded.
- **VA migration "higher"**: Today's value area is above yesterday's — bullish, institutions accepting higher prices
- **VA migration "lower"**: Value area shifting down — bearish, distribution
- **VA migration "overlapping"**: Neutral, consolidating
- **Poor Low (PL)**: >5% of session volume at the low — sellers leaning, bearish for longs. A healthy low has LITTLE volume (clean rejection).
- **Poor High (PH)**: >5% of volume at the high — buyers leaning, bearish for shorts
- **IB (Initial Balance)**: First hour range (9:30-10:30 ET). IB-BO = breakout above IB high (bullish). IB-BD = breakdown below IB low (bearish).
- **HiVol**: Above-average volume. Increases confidence in any profile signal.
- **Wide VA (>3% of price)**: No institutional consensus. Stock in discovery mode — signals less reliable.
- **Tight VA (<1% of price)**: Strong consensus. Signals more trustworthy.

---

## TRADING RULES

### Two-Bucket Strategy
- **Bucket 1** = Thesis positions (longer-dated, hold for correction/credit crisis)
- **Bucket 2** = Tactical momentum trades (3-5 day holds, 50-100%+ targets, max 2 open at a time, max $200-300 each, cut if not profitable in 3 days)

### Short-Dated Position Rule (<21 DTE)
Take profits at 60-70% of max value. Don't hold for perfection.

### Positioning Awareness
Check for mechanical flow events before opening short-dated positions: quarter-end pension rebalancing, JPM JHEQX collar roll (quarterly), monthly OpEx pin risk, VIX expiration.

### Core Principle (stonXBT)
"Trade the physical reality, not the tweets. Ships either transit or they don't." Focus on physical supply chain confirmation, not headlines.

---

## EXIT RULES
- <21 DTE: Take profits at 60-70% of max value
- Bucket 2 tactical: Cut if not profitable in 3 trading days
- Trip wires: See top of document

---

## MACRO THESIS DETAIL (update as conditions change)

### Quinn Thompson Roadmap
Step 1: Mag7 cash depletion (confirmed). Step 2: Private credit gating — Apollo/Ares/Blue Owl freezing redemptions (confirmed). Step 3: Failed Treasury auctions — 10Y "disaster" Apr 8, foreign private UST holders ($5.3T) with no Fed backstop (confirmed). Step 4: Semiconductor unwind — early signs (NVDA bearish flow, hyperscaler capex cuts).

### Treasury Vulnerability (Wallerstein/Clocktower)
Foreign PRIVATE holders of USTs doubled to $5.3T since 2019. No Fed backstop (FIMA = official only). Oil-exporter SWFs may fire-sell. Structural driver behind failed auctions.

### Physical vs Paper Oil
Dubai physical was $126 vs Brent paper $112 pre-ceasefire. Apr 8 ceasefire crashed oil to $94. Ceasefire fragile. US Gulf exports at record 4.9M b/d.

### Key Macro Data Points
- GDP: 4.4% → 0.5% (stagflation)
- Personal savings rate: 4.0% (2nd-lowest since 2008 crisis)
- HYG broke $80 on Apr 10
- VIX back above 20

### Fidelity Roth Tranche Plan ($8,500, ETFs only)
- Tranche 1 (FILLED): JEPI $750 + EFA $750
- Tranche 2 (gold trigger): GDX $500
- Tranche 3 (URA pullback $40-42): URA $500
- Tranche 4 (SPX breaks 6,400): JEPI $750 + EFA $750
- Tranche 5 (recession confirmed): JEPI $750 + EFA $750
- Cash reserve: $2,500. No tech/AI exposure.
