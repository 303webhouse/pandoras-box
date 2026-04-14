# CODEX BRIEF: Phase 2G — Auto-Scout Pipeline
## UW API Basic + TV MCP Architecture

**Date:** April 13, 2026
**Status:** PROPOSED — Pending Nick's approval
**Dependencies:** UW API Basic subscription ($150/mo), TV MCP server (free)
**Replaces:** UW Basic dashboard ($68), Polygon Options ($29), Polygon Stocks ($29)
**Net cost change:** -$56/mo savings vs current stack

---

## EXECUTIVE SUMMARY

Phase 2G transforms Pandora's Box from a system that *presents* signals for manual review into one that *discovers* opportunities autonomously by screening the entire UW options flow firehose, enriching candidates with GEX/OI/dark pool data, running them through the Olympus committee, and posting scored picks to Discord — all without human intervention.

The architecture combines three data layers: TradingView webhooks (real-time signals, already built), UW API Basic polling (flow enrichment, new), and the TV MCP screener (technical screening, new/free). Total data cost drops from $126/mo to $150/mo while gaining programmatic API access that was previously impossible.

---

## PART 1: OLYMPUS COMMITTEE REVIEW — TRADING EDGE ANALYSIS

### TORO — Bull Case for Phase 2G

The edge case for this build is straightforward and quantifiable. Today, Nick manually screens UW flow data by taking screenshots, pasting them into chat, and waiting for committee analysis. This morning's session — where we reviewed ERAS, PATH, NVDA, and SMH — took approximately 4 hours of active work to identify and evaluate 4 candidates. Nick passed on ERAS, took PATH and NVDA, and deferred SMH.

An automated Phase 2G pipeline running the same logic would have:
- Flagged ERAS trapped-shorts at 9:31 AM (within 60 seconds of market open) instead of 52 minutes later
- Simultaneously identified PATH's P/C 0.21 + 7.6% gap + GEX flip at $10 as a high-priority candidate
- Screened the entire UW flow universe (~500-1000 unusual trades/day) instead of the ~20 tickers Nick manually checks
- Done all of this while Nick slept, commuted, or focused on other work

Per F.13, well-documented edges decay. The flow-following edge is real but time-sensitive — the alpha in a trapped-shorts setup at market open is materially different from the same setup identified 52 minutes later. Automation compresses the signal-to-action gap from minutes/hours to seconds.

The capital efficiency argument per R.01: Nick's RH account will be ~$7,858 after the $5K deposit. At $235 max risk per trade, he can hold roughly 30-33 positions at max allocation. Currently he's running 10 positions across bearish and bullish books. The constraint isn't capital — it's attention. He can only evaluate ~4-6 candidates per session manually. Phase 2G removes that bottleneck.

The coverage argument per P.04-P.05: Retail's structural edge is speed of decision-making on small positions in illiquid names that institutions can't efficiently trade. UiPath (PATH) today was a perfect example — a $10 stock with massive institutional call positioning that retail can front-run via cheap spreads. These setups exist every day across the 6,000+ optionable tickers. Nick currently sees ~20 of them. Phase 2G sees all of them.

CONVICTION THAT THIS BUILD GENERATES POSITIVE ROI: **HIGH**

### URSA — Risk Case and Failure Modes

Several material risks require mitigation:

**Signal overload (the primary risk).** The UW flow firehose produces 500-1000 unusual trades daily. If Phase 2G flags 50 candidates/day and posts them all to Discord, Nick drowns in noise. Per E.09, only A-setups should reach Nick. The filtering layer must be aggressive — score threshold of 80+, bias alignment required, risk parameters pre-checked. This is a filtering problem, not a data problem.

**False precision.** Automated scoring can create overconfidence. A committee review that takes 30 seconds via API will miss nuance that a 10-minute manual review catches. Per B.06, bias confirmation is a real risk — an automated bull-leaning system during a bull market will generate an endless stream of long signals that feel validated by recent performance but represent crowded trades per F.13 and P.04.

**Backtesting without the backtest.** The 30-day historical lookback on UW API Basic is short. Nick will be tempted to trust flow signals without statistical validation. Before deploying any auto-scout signal as tradeable, there should be a minimum 30-day paper-trade validation period where Phase 2G posts picks but Nick doesn't trade them, then evaluates hit rate.

**API reliability.** Polling every 30 seconds for 6.5 hours = 780 requests to a third-party API. If UW has downtime, rate limits, or data quality issues, the pipeline goes blind. Must have graceful degradation — fall back to the existing uw-watcher Discord scraper if API fails.

**Concentration risk.** If Phase 2G is optimized on flow signals, it will naturally bias toward high-flow, high-momentum names — tech, meme stocks, momentum plays. Nick's structural thesis trades (HYG, BX, DBA, NEXT) are not flow-driven. Phase 2G must be positioned as a supplement to thesis trading, not a replacement. Per R.01, the biggest blow-ups come from sizing, and an automated system that produces 5 "high conviction" signals in one sector is effectively a concentrated bet.

**The $150/mo cost creates commitment bias.** Once Nick is paying for the API, he'll feel pressure to trade on its signals to justify the cost. This is a psychological trap per D.01 (discipline section). The API's value should be measured by trades NOT taken (filtered out by committee) as much as trades taken.

CONVICTION THAT BUILD FAILS TO GENERATE ROI: **MEDIUM** — primarily from signal overload and concentration risk if filtering isn't rigorous.

### TECHNICAL ANALYST — Architecture & Risk Parameters

#### Data Flow Architecture

```
LAYER 1: REAL-TIME SIGNAL GENERATION (existing + new)
├── TradingView Webhooks (existing)
│   ├── Hub Sniper v2.1 (15m entries)
│   ├── Scout Sniper v3.1 (15m early warning)
│   ├── Holy Grail scanner (1H pullbacks)
│   ├── CTA Scanner (daily trend)
│   ├── PYTHIA Market Profile alerts
│   └── TICK/McClellan/Breadth bias webhooks
│
├── UW Discord uw-watcher (existing)
│   └── Parses UW bot embeds → Redis flow cache
│
└── TV MCP Screener (NEW — free)
    ├── fiale-plus/tradingview-mcp-server on VPS
    ├── 100+ screener fields
    ├── TA summaries for any symbol
    ├── Runs headless, no TV Desktop needed
    └── Cron: scan universe every 15 min

LAYER 2: FLOW ENRICHMENT (NEW — UW API Basic)
├── Poll /flow endpoint every 30s during market hours
│   └── Parse: ticker, premium, type, sentiment, sweep/block
├── Poll /darkpool/{ticker} every 5 min for watchlist
├── Poll /stock/{ticker}/options-volume every 5 min
├── Poll /etf/tide for market-wide flow direction
├── On-demand enrichment for any signal from Layer 1:
│   ├── GET /stock/{ticker}/options-flow → flow context
│   ├── GET /stock/{ticker}/greek-exposure → GEX
│   ├── GET /stock/{ticker}/open-interest → OI changes
│   └── GET /stock/{ticker}/darkpool → institutional activity
└── Request budget: ~1,600/day of 20,000 limit (8%)

LAYER 3: SIGNAL SCORING & FILTERING
├── Input: signals from Layer 1 + enrichment from Layer 2
├── Composite signal score (0-100):
│   ├── Base score from scanner (existing)
│   ├── Bias alignment multiplier (existing)
│   ├── CTA zone bonus (existing)
│   ├── NEW: Flow confirmation bonus (+5-15)
│   │   └── If UW flow sentiment aligns with signal direction
│   ├── NEW: GEX regime bonus (+5-10)
│   │   └── If gamma profile supports the move direction
│   ├── NEW: Dark pool confirmation (+5-10)
│   │   └── If institutional dark pool prints align
│   ├── NEW: OI change acceleration (+3-8)
│   │   └── If OI is building in the signal direction
│   └── R:R validation gate (existing)
├── Minimum score for committee: 80
├── Maximum candidates per day: 10
├── Sector concentration limit: max 3 from same sector
└── Dedup: no repeat signals on same ticker within 4 hours

LAYER 4: COMMITTEE EVALUATION
├── Candidates scoring 80+ enter committee pipeline
├── LLM committee run via Anthropic API (~$0.02/run)
│   ├── TORO, URSA, TA, PYTHIA evaluate with full context
│   ├── Context includes: all Layer 2 enrichment data
│   └── Pivot synthesizes → TAKE / PASS / WATCHING
├── TAKE signals → Discord #auto-scout channel
│   ├── Include: entry, stop, target, structure, size
│   ├── Include: committee reasoning summary
│   └── Include: one-click "Accept" button (existing)
└── PASS signals → logged to DB for backtest analysis

LAYER 5: PERFORMANCE TRACKING
├── Track every auto-scout signal outcome (30 days)
├── Win rate by signal type, sector, flow pattern
├── Compare: Phase 2G picks vs manual picks
├── Monthly review: is the automation adding alpha?
└── Kill switch: if win rate < 40% over 30 signals, pause
```

#### API Request Budget (UW API Basic: 20K/day, 120/min)

| Task | Frequency | Requests/Day |
|------|-----------|-------------|
| Flow polling (every 30s, market hours) | 780 calls | 780 |
| Watchlist enrichment (20 tickers × 4 endpoints × every 15 min) | 26 cycles × 80 | 2,080 |
| On-demand signal enrichment (~30 signals/day × 4 endpoints) | 30 × 4 | 120 |
| Market-wide endpoints (tide, sector flow, indices) | Every 5 min | 78 |
| **Total** | | **~3,058** |
| **Budget remaining** | | **~16,942 (85%)** |

Comfortable margin. Could increase polling frequency or add more tickers without hitting limits.

#### Risk Parameters for Auto-Scout Signals

Per R.01-R.07, every auto-scout pick must include:

- Max risk in dollars (capped at $235 for RH)
- Specific spread structure with strikes and expiry
- Defined stop level
- Minimum R:R of 2:1
- IV rank context (per R.07: >50 = sell premium, <30 = buy premium)
- DTE minimum of 14 days (no 0DTE or weekly lottery tickets)
- Earnings check: flag if earnings within DTE window
- Correlation check against existing open positions
- Account risk check: total open risk + new risk ≤ 20% of account

### PYTHIA — Structural Considerations

The auto-scout pipeline must respect auction theory principles. Flow signals represent *activity* — what people are doing. Market Profile represents *structure* — what the auction says about fair value. These can conflict.

A high-flow bullish signal on a ticker where price is at the Value Area High with a poor high overhead is a different trade than the same signal at the Value Area Low. The flow says "buy" but the structure says "you're buying at the top of the range."

**Recommendation:** For Phase 2G auto-scout, PYTHIA's structural read should be a gate, not just a score modifier. If the auction structure directly contradicts the flow signal (e.g., buying at VAH in a bracketing market, or selling at VAL during value migration higher), the signal should be downgraded regardless of flow strength.

This requires either:
1. PYTHIA's Pine Script indicator firing webhook levels that the pipeline can read (partially built — PYTHIA v2 is deployed on the 14-ticker watchlist), or
2. The TV MCP screener providing TA summaries that approximate structural reads (available via the fiale-plus server)

Option 1 is more accurate but limited to the watchlist. Option 2 is broader but less nuanced. Recommend starting with Option 2 for the auto-scout universe and using Option 1 for the core watchlist.

### PIVOT — Synthesis

Here's my take on the build.

Phase 2G is the single highest-ROI project on the backlog. Everything else — UI tweaks, new bias factors, Fidelity integration — is incremental improvement. This is a capability unlock. You go from a guy who's really good at reading flow data to a system that reads ALL the flow data, ALL the time, and only surfaces the best 2-5 plays per day.

The architecture is sound. Three free/existing layers (TV webhooks, uw-watcher, TV MCP) handle real-time signals. UW API Basic handles enrichment at 8% of its daily budget. The committee pipeline is already built and runs at $0.02/run. The Discord output channel is already built. This is a plumbing job, not a new build.

URSA's right about signal overload — that's the failure mode to design against. The filtering layer is where the edge lives or dies. A Phase 2G that posts 50 signals a day is worse than no Phase 2G. A Phase 2G that posts 2-3 A-setup signals a day, each with full committee analysis, is a game-changer.

Build it in this order:
1. UW API integration (polling + caching)
2. TV MCP server deployment on VPS
3. Signal enrichment pipeline (add flow/GEX/OI to existing signals)
4. Auto-scout scoring layer
5. Committee auto-run on high-score candidates
6. Discord output + Accept/Pass buttons
7. 30-day paper trade validation
8. Go live

Estimated build time: 3-4 weekends if chunked properly. Each step is independently testable and deployable.

ACTION: **BUILD**
PRIORITY: **HIGH — next major project after current positions stabilize**

---

## PART 2: NEW INDICATORS & STRATEGIES ENABLED

With UW API + TV MCP, the following become buildable for the first time:

### New Bias Engine Factors

#### 1. NET PREMIUM TIDE (Swing-tier factor)
**Source:** UW API `/etf/tide` endpoint
**What it measures:** Net call vs put premium across the market, tracked over time
**Current gap:** You manually screenshot the Market Tide chart from UW dashboard. This automates it.
**Bias signal:** Net premium consistently positive = TORO, consistently negative = URSA
**Weight suggestion:** 0.05 (swing tier)
**Bible rule:** Extends F.01 (flow strength identification)

#### 2. INSTITUTIONAL DARK POOL SENTIMENT (Swing-tier factor)
**Source:** UW API `/darkpool/recent` and `/stock/{ticker}/darkpool`
**What it measures:** Net dark pool sentiment across SPY/QQQ components
**Current gap:** I.14 explicitly notes "no bid/ask depth, orderbook imbalance" as missing data. Dark pool prints with bid/ask sentiment partially fills this gap.
**Bias signal:** Net dark pool buying = TORO, selling = URSA
**Weight suggestion:** 0.04 (swing tier)
**Bible rule:** Extends M.03 (iceberg orders / hidden liquidity)

#### 3. GEX REGIME CLASSIFIER (Intraday-tier factor)
**Source:** UW API `/stock/SPY/greek-exposure` or FlashAlpha free tier
**What it measures:** Whether dealers are long gamma (mean-reverting, sell rallies/buy dips) or short gamma (momentum, chase moves)
**Current gap:** The hub's GEX factor exists but is crippled by Polygon Starter's 150-contract limit. UW API provides full institutional-grade GEX data.
**Bias signal:** Positive GEX = NEUTRAL (dampened moves), Negative GEX = directional (amplified moves). Combined with direction to determine TORO/URSA.
**Weight suggestion:** Replace existing GEX factor (currently 0.04) with upgraded version
**Bible rule:** Directly implements F.08 (dealer gamma positioning)

#### 4. OPTIONS-EQUITY DIVERGENCE DETECTOR (Macro-tier factor)
**Source:** UW API flow data vs price data
**What it measures:** When options flow diverges from price action — e.g., price flat but massive put buying, or price dropping but call flow accelerating
**Current gap:** Entirely new capability. No existing factor captures this.
**Bias signal:** Divergence = regime change warning. Call flow diverging bullishly from price = early TORO signal. Put flow diverging bearishly = early URSA signal.
**Weight suggestion:** 0.03 (macro tier)
**Bible rule:** Extends M.06 (delta divergence) to options flow context

### New Scanner Strategies

#### 5. WHALE FLOW MOMENTUM SCANNER
**Trigger:** UW API detects >$5M in premium on a single ticker within 30 minutes, 80%+ directionally aligned, sweep/block execution
**Logic:** When institutional-scale capital enters a name aggressively, the move often has 2-5 days of follow-through. This scanner catches the initial wave.
**Output:** Signal card with flow details, committee auto-review
**Edge per P.05:** Exploits the information asymmetry window — institutions know something, retail follows, and the first-mover retail trader captures the gap between institutional entry and broad awareness.
**Risk per URSA:** Not all whale flow is directional — some is hedging existing positions (the AMZN 75% bearish premium today was likely a hedge, not a conviction short). The scanner must cross-reference with the ticker's existing options OI to distinguish new positioning from hedging.

#### 6. GEX FLIP BREAKOUT STRATEGY
**Trigger:** Price crosses the gamma flip level (where net GEX transitions from positive to negative or vice versa)
**Logic:** Per F.08, when price moves from positive gamma territory (dealers dampen moves) to negative gamma territory (dealers amplify moves), the resulting momentum acceleration creates high-probability trend continuation setups. The SPX gamma flip at 6846 from today's market maker chart is exactly this level.
**Output:** Alert when a tracked ticker crosses its gamma flip, with direction and magnitude
**Implementation:** Calculate gamma flip from UW GEX data, set as a dynamic level in the bias engine
**Edge:** This is a mechanical, non-discretionary signal based on dealer positioning — exactly the kind of structural edge per P.01 (risk premia vs alpha).

#### 7. SMART MONEY / DUMB MONEY FLOW DIVERGENCE
**Trigger:** UW API identifies institutional block/sweep flow diverging from retail options flow
**Logic:** When institutional sweeps are buying calls but overall retail P/C ratio is high (bearish retail sentiment), the smart/dumb money divergence signals a high-probability long entry. Vice versa for shorts.
**Output:** Divergence score from -100 (max bearish divergence) to +100 (max bullish divergence)
**Edge per F.02:** Trapped traders (retail on the wrong side) provide fuel for the institutional move
**Implementation:** Compare UW's sweep/block data (institutional proxy) against overall P/C and small-lot flow (retail proxy)

#### 8. DARK POOL ACCUMULATION DETECTOR
**Trigger:** UW API shows sustained dark pool buying on a ticker over 3+ days, with prints consistently above the bid midpoint
**Logic:** When institutions use dark pools to accumulate shares without moving the price, the eventual public market impact creates a predictable upward repricing. This was historically only visible to prop desks.
**Output:** Accumulation score and average dark pool price vs current price
**Edge per P.05:** This directly exploits an institutional constraint — institutions MUST use dark pools for large orders, creating a detectable footprint that retail can front-run.
**Bible rule:** Directly implements the concept behind the existing whale-hunter strategy (docs/approved-strategies/whale-hunter.md) but with real API data instead of the current Polygon-limited version.

#### 9. CONGRESSIONAL TRADE FOLLOWING (Experimental)
**Trigger:** UW API `/congressional/recent-trades` detects a new filing
**Logic:** Congressional trades have shown statistically significant alpha in certain studies, particularly on committee-relevant tickers (e.g., a defense committee member buying RTX). The 45-day reporting delay limits immediacy, but cluster analysis (multiple members buying the same sector) can identify thematic bets.
**Output:** Congressional flow alerts filtered by committee relevance and cluster detection
**Caution per URSA:** The 45-day delay means the informational edge is stale. This is a supplementary signal, not a primary one. Weight accordingly.

#### 10. TV MCP MULTI-TIMEFRAME REGIME SCANNER
**Trigger:** TV MCP screener runs every 15 minutes across the full universe
**Logic:** Using the fiale-plus/tradingview-mcp-server's built-in TA summary, classify every ticker in the watchlist + discovery list as: trending up, trending down, or ranging. Cross-reference with UW flow direction. When flow and trend align, signal strength increases.
**Output:** Universe-wide regime classification that feeds into the auto-scout scoring layer
**Implementation:** TV MCP provides `get_ta_summary` and `rank_by_ta` endpoints that return buy/sell/neutral ratings across multiple timeframes. Map these to the existing CTA zone framework.

### Updates to Training Bible (Section I)

With UW API + TV MCP, the following "Data You DO NOT Have" entries from Section I can be upgraded:

| Current Gap | Bible Ref | New Status |
|------------|-----------|------------|
| Live options chain data | I.17 | **RESOLVED** — UW API provides IV rank, OI, volume, greeks per strike |
| Market Profile / TPO data | I.13 | **PARTIALLY RESOLVED** — TV MCP provides TA summaries; PYTHIA webhooks provide key levels for watchlist |
| Intraday orderbook / Level 2 | I.14 | **PARTIALLY RESOLVED** — Dark pool bid/ask sentiment available via UW API |
| Insider transactions | I.25 | **RESOLVED** — UW API `/insider/recent-trades` endpoint |
| Short interest | I.26 | **RESOLVED** — UW API `/stock/{ticker}/short-interest` endpoint (already used in Hydra Squeeze Monitor) |

---

## PART 3: BUILD PLAN

### Phase 2G Build Order (Chunked for ADHD-friendly implementation)

#### Sprint 1: Foundation (Weekend 1)
**Goal:** UW API connected and caching data

- [ ] Sign up for UW API Basic ($150/mo)
- [ ] Cancel UW Basic dashboard ($68/mo)
- [ ] Cancel Polygon Options Starter ($29/mo)
- [ ] Test: can yfinance handle all bias factor data without Polygon Stocks?
  - If yes: cancel Polygon Stocks ($29/mo)
  - If no: keep Polygon Stocks for now
- [ ] Create `backend/integrations/uw_api.py` — async client with rate limiting
- [ ] Implement core endpoints: flow, GEX, OI, dark pool, tide
- [ ] Add Redis caching layer (same pattern as existing UW integration)
- [ ] Health check endpoint: `/api/uw/health`
- [ ] Test: pull SPY flow data and cache it
- [ ] Downgrade Claude Pro to Basic ($20/mo)

**Definition of done:** Can query UW API for any ticker's flow/GEX/OI and see cached results in Redis.

#### Sprint 2: TV MCP Deployment (Weekend 2)
**Goal:** TV MCP screener running on VPS

- [ ] Clone `fiale-plus/tradingview-mcp-server` to VPS
- [ ] `npm install`, configure
- [ ] Create systemd service: `tv-mcp.service`
- [ ] Test: run screener against SPY, QQQ, SMH
- [ ] Create wrapper: `backend/integrations/tv_mcp.py`
- [ ] Add TA summary endpoint: `/api/tv/ta-summary/{ticker}`
- [ ] Cron: scan universe every 15 minutes, cache to Redis

**Definition of done:** Can query any ticker's TA summary from the hub's API.

#### Sprint 3: Signal Enrichment (Weekend 3)
**Goal:** Existing signals get UW flow context automatically

- [ ] Modify signal pipeline (`backend/signals/pipeline.py`)
- [ ] When a signal fires, auto-fetch from UW API:
  - Flow data (premium, P/C, sentiment)
  - GEX levels (gamma flip, net gamma)
  - OI changes (new positions opening)
  - Dark pool prints (last 24h)
- [ ] Add enrichment data to signal context (injected into committee prompts)
- [ ] Add flow confirmation score modifier to composite signal score
- [ ] Upgrade existing GEX bias factor to use UW API instead of Polygon
- [ ] Add Net Premium Tide as new swing-tier bias factor
- [ ] Test: fire a test webhook and verify enrichment data appears

**Definition of done:** Signal cards in the hub show UW flow data alongside existing technical data. Committee reviews receive enrichment context automatically.

#### Sprint 4: Auto-Scout Pipeline (Weekend 4)
**Goal:** Autonomous flow screening → scored candidates → committee review

- [ ] Create `backend/scanners/auto_scout.py`
- [ ] Polling loop: query UW flow every 30s during market hours
- [ ] Filter: minimum premium threshold, DTE ≥ 14, not blacklisted
- [ ] Score: composite of flow strength + GEX alignment + bias alignment + TA summary
- [ ] Gate: score ≥ 80 → enter committee pipeline
- [ ] Gate: max 10 candidates/day, max 3 per sector
- [ ] Auto-run committee evaluation (existing pipeline)
- [ ] TAKE signals → Discord #auto-scout channel
- [ ] Include: structure, entry, stop, target, size, committee reasoning
- [ ] Add "Accept" / "Pass" buttons (existing interaction system)
- [ ] Performance tracking: log every signal with outcome

**Definition of done:** Phase 2G is live and posting 2-5 auto-scout picks per day to Discord with full committee analysis.

#### Sprint 5: Validation & New Strategies (Weeks 5-8)
**Goal:** Paper trade validation + new strategy deployment

- [ ] 30-day paper trade period — track picks but don't trade them
- [ ] Analyze: win rate, average R:R, sector distribution, timing
- [ ] Implement Whale Flow Momentum Scanner (Strategy #5)
- [ ] Implement GEX Flip Breakout Strategy (Strategy #6)
- [ ] Implement Dark Pool Accumulation Detector (Strategy #8)
- [ ] Update Training Bible Section I with new data availability
- [ ] Performance review: is auto-scout generating alpha?
- [ ] Go/no-go decision on live trading auto-scout signals

**Definition of done:** 30-day track record with measurable win rate. Kill switch: if win rate < 40% over 30 signals, pause and recalibrate.

---

## PART 4: COST SUMMARY

### Before (Current Monthly)
| Service | Cost |
|---------|------|
| UW Basic | $68 |
| Polygon Options | $29 |
| Polygon Stocks | $29 |
| Claude Pro | $100 |
| TradingView Premium | ~$57 |
| Railway | ~$10 |
| Hetzner VPS | ~$5 |
| Anthropic API | ~$8 |
| **Total** | **~$306/mo** |

### After (Consolidated Monthly)
| Service | Cost |
|---------|------|
| UW API Basic | $150 |
| Claude Basic | $20 |
| TradingView Premium | ~$57 |
| Railway | ~$10 |
| Hetzner VPS | ~$5 |
| Anthropic API | ~$10 (slightly more committee runs) |
| yfinance | Free |
| TV MCP | Free |
| **Total** | **~$252/mo** |

### Net savings: ~$54/mo ($648/yr)
### Capability gain: Programmatic API access, Phase 2G auto-scout, 5+ new indicators/strategies

---

## APPENDIX: UW API ENDPOINTS FOR PHASE 2G

Priority endpoints (used daily):
- `GET /flow` — real-time options flow firehose
- `GET /stock/{ticker}/options-flow` — ticker-specific flow
- `GET /stock/{ticker}/greek-exposure` — GEX by strike
- `GET /stock/{ticker}/open-interest` — OI with changes
- `GET /stock/{ticker}/darkpool` — dark pool prints
- `GET /etf/tide` — market-wide put/call premium flow
- `GET /stock/{ticker}/quote` — price data (Polygon replacement)

Secondary endpoints (used for enrichment):
- `GET /stock/{ticker}/short-interest` — short interest data
- `GET /insider/recent-trades` — insider transactions
- `GET /congressional/recent-trades` — congressional trades
- `GET /stock/{ticker}/net-prem-ticks` — granular premium flow
- `GET /stock/{ticker}/options-volume` — volume by expiry/strike

Documentation: https://api.unusualwhales.com/docs
OpenAPI spec: https://api.unusualwhales.com/api/openapi
MCP Server: https://unusualwhales.com/public-api/mcp
