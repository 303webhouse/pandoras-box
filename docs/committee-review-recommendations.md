# Committee Expert Review — Implementation Roadmap

**Date:** 2026-02-25
**Reviewers:** TA Expert, Buy-Side Analyst, Sell-Side Derivatives Strategist
**Overall Assessment:** Architecture and knowledge base are institutional-quality. The gap is options-specific data flowing into agents that already know what to do with it.

---

## Tier 1 — Critical (all 3 experts agree, implement first) ✅ COMPLETED 2026-02-26

### 1. IV Rank / IV Percentile Data
**Gap:** Agents are told to evaluate IV but never receive it. The system can't determine buy vs sell premium — the most consequential options decision.
**Fix:** Extend `fetch_technical_snapshot()` to compute IV rank/percentile from yfinance options chain. Inject as `## OPTIONS DATA` section alongside `## TECHNICAL DATA`.
**Files:** `committee_context.py`
**Effort:** 4-6 hours

### 2. Economic Calendar Integration
**Gap:** FOMC/CPI/NFP/PCE dates are not injected. Swing trades spanning these events have materially different risk profiles. No automated economic calendar check exists.
**Fix:** Create `data/econ_calendar.json` with FOMC, CPI, NFP, PCE, GDP dates. Check against signal's DTE window. Inject `## ECONOMIC CALENDAR WARNING` into agent context.
**Files:** `committee_context.py`, new `data/econ_calendar.json`
**Effort:** 2-3 hours

### 3. DTE-Aware Earnings Check
**Gap:** Current `check_earnings_proximity()` uses fixed 14-day window. A signal with 30 DTE where earnings are in 20 days won't be flagged.
**Fix:** Accept signal's DTE, check if earnings fall within that window instead of arbitrary 14 days.
**Files:** `pivot2_committee.py`
**Effort:** 30 minutes

### 4. Strike/Structure Recommendation in PIVOT Output
**Gap:** Committee says TAKE/PASS but never recommends a specific options structure. The hardest 40% of the decision is left to Nick.
**Fix:** Add `STRUCTURE:` and `LEVELS:` fields to PIVOT output format. Force Pivot to recommend options structure type based on IV rank and DTE. Add rule-based guidance: IV rank > 50 = credit structure, IV rank < 30 = debit structure, earnings within DTE = defined-risk only.
**Files:** `committee_prompts.py` (PIVOT prompt)
**Effort:** 1-2 hours

---

## Tier 2 — High Impact (2-3 experts agree) ✅ COMPLETED 2026-02-26

### 5. RSI/MACD Divergence Detection
**Gap:** Highest-probability reversal signals missing from data pipeline. Prompts tell agents to check divergences but data doesn't compute them.
**Fix:** After computing RSI and MACD, scan last 20-30 bars for swing highs/lows. Compare price vs indicator values. Flag divergences: `"rsi_divergence": "bearish (price higher high, RSI lower high)"`.
**Files:** `committee_context.py` (`fetch_technical_snapshot`)
**Effort:** 3-4 hours

### 6. SMAs Alongside EMAs
**Gap:** CTA Three-Speed System uses SMAs (20/50/120), but only EMAs (20/50/200) are computed. These are different calculations. CTA zone classification depends on SMAs.
**Fix:** Add `sma20`, `sma50`, `sma120`, `sma200` to snapshot. Add CTA zone classification (Green/Yellow/Red/Grey).
**Files:** `committee_context.py`
**Effort:** 1 hour

### 7. Portfolio-Level Risk Context
**Gap:** Committee evaluates each signal independently. Can't prevent concentration blowups or flag correlation with existing positions.
**Fix:** Inject anonymized portfolio summary: "Current portfolio: net short delta, 3 open positions, 2 bearish/1 neutral, total capital at risk: $450/$4,700 (9.6%)."
**Files:** `committee_context.py`, `pivot2_committee.py`
**Effort:** 3-4 hours (depends on position data availability)

### 8. Position Sizing in PIVOT Output
**Gap:** Conviction (HIGH/MEDIUM/LOW) should map to specific dollar risk. No position sizing recommendation.
**Fix:** Add `SIZE:` field to PIVOT output. Map: HIGH = 3-5% account risk, MEDIUM = 1.5-2.5%, LOW = watching only.
**Files:** `committee_prompts.py` (PIVOT prompt)
**Effort:** 30 minutes

### 9. Increase Token Limits
**Gap:** TECHNICALS at 500 tokens can't cover 7-item TA checklist. PIVOT at 1000 is tight for synthesis + decision + levels.
**Fix:** TECHNICALS → 750, PIVOT → 1500.
**Files:** `pivot2_committee.py`
**Effort:** 2 minutes

### 10. Realized Vol vs Implied Vol Spread
**Gap:** Core signal for premium buying vs selling. Without RV baseline, IV rank means different things for low-vol utilities vs high-vol biotechs.
**Fix:** Compute 20-day historical volatility from daily returns. Present alongside IV data: "HV(20): 28%, IV: 42%, IV/HV spread: +50%".
**Files:** `committee_context.py`
**Effort:** 1 hour

---

## Tier 3 — Important Enhancements ✅ COMPLETED 2026-02-26 (feasible items)

### 11. Bollinger Bands + Squeeze Detection ✅
**Gap:** Pre-breakout signal missing. The Stable docs cover BB extensively. BB squeeze is one of the most reliable volatility breakout predictors.
**Fix:** Add BB(20,2): `bb_upper`, `bb_lower`, `bb_width`, `bb_squeeze` (bandwidth < 20th percentile of 90-day history).
**Files:** `committee_context.py`
**Effort:** 1 hour

### 12. Volume Trend Analysis (Up-Volume vs Down-Volume) ✅
**Gap:** Agents can't assess accumulation vs distribution. Only current volume ratio provided.
**Fix:** Add `volume_up_days_avg` vs `volume_down_days_avg` (10-day window). Ratio indicates accumulation/distribution.
**Files:** `committee_context.py`
**Effort:** 1 hour

### 13. VWAP Computation ✅
**Gap:** Core institutional reference price missing. TECHNICALS prompt has entire VWAP section but no data.
**Fix:** At minimum, compute prior session VWAP using intraday data. Even daily approximation `(H+L+C)/3 * volume` is better than nothing.
**Files:** `committee_context.py`
**Effort:** 2-3 hours

### 14. Dynamic DEFCON (Replace Static Markdown) ⏭️ SKIPPED
**Gap:** DEFCON parsed from `SESSION-STATE.md` string matching. If file is stale, committee runs at wrong risk level.
**Fix:** Compute DEFCON dynamically from VIX level, VIX vs 20-day MA, SPY vs 50/200 EMAs, recent circuit breaker events.
**Files:** `pivot2_committee.py`
**Effort:** 3-4 hours
**Skip reason:** SESSION-STATE.md doesn't exist in repo. Manual DEFCON via existing mechanisms is adequate for now.

### 15. Recent P&L State Injection ✅
**Gap:** Committee can't enforce the "after 2 consecutive losses, half position size" playbook rule.
**Fix:** Inject recent trade P&L history: "Last 3 trades: WIN, LOSS, LOSS. Per playbook rules, reduce to 50% size."
**Files:** `committee_context.py`, `pivot2_committee.py`
**Effort:** 2-3 hours

### 16. GEX / Dealer Gamma Data ⏭️ SKIPPED
**Gap:** System references dealer gamma extensively but doesn't fetch GEX data. Gamma flip level determines mean-reversion vs trend-amplification regime.
**Fix:** Source daily GEX estimates (SpotGamma API or manual). Inject gamma flip level and regime.
**Files:** `committee_context.py`
**Effort:** 4-6 hours (API sourcing dependent)
**Skip reason:** Requires paid SpotGamma API or similar. yfinance options chain too slow/unreliable for production use.

### 17. Expected Move Calculation for Earnings ⏭️ SKIPPED
**Gap:** System warns about earnings but never computes expected move from ATM straddle vs historical average move.
**Fix:** When earnings within DTE, compute ATM straddle implied move vs stock's historical average move over last 4 quarters.
**Files:** `committee_context.py`, `pivot2_committee.py`
**Effort:** 3-4 hours
**Skip reason:** Requires reliable ATM straddle data. yfinance options chain is fragile and slow for production use.

### 18. Pin Risk / Early Assignment Warnings ✅
**Gap:** American-style options on Robinhood have early assignment risk. System doesn't mention pin risk near expiration.
**Fix:** Flag any TAKE recommendation on credit structure within 5 DTE of expiration. Add pin risk awareness to URSA prompt.
**Files:** `committee_prompts.py` (URSA prompt)
**Effort:** 30 minutes

### 19. 0DTE Gamma Awareness for SPY Trades ✅
**Gap:** 0DTE options now >40% of SPX volume, fundamentally altering intraday microstructure. Not addressed.
**Fix:** For SPY/SPX signals, inject note about 0DTE gamma effects on entry timing (mean-reversion early, trend acceleration near close).
**Files:** `committee_prompts.py` (TECHNICALS prompt)
**Effort:** 15 minutes

### 20. Relative Strength vs SPY ✅
**Gap:** For individual stock signals, relative strength vs benchmark is a core screening tool. Not computed.
**Fix:** Add `ticker_return_20d / spy_return_20d` as relative strength ratio.
**Files:** `committee_context.py`
**Effort:** 1-2 hours

---

## Bug Fixes / Corrections

### A. ATR Uses SMA Instead of Wilder Smoothing
**Issue:** `tr.rolling(14).mean()` doesn't match TradingView's ATR calculation.
**Fix:** Change to `tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()`.
**Files:** `committee_context.py` line 356
**Effort:** 1 minute

### B. MEDIUM Conviction Accuracy Inflation ✅ FIXED
**Issue:** `compute_agent_accuracy()` counts MEDIUM as "correct", inflating metrics.
**Fix:** Exclude MEDIUM from accuracy calculations or track separately as "uninformative".
**Files:** `committee_analytics.py`
**Effort:** 30 minutes

### C. OI Threshold Too Low
**Issue:** Playbook says 500 OI is comfortable. Sell-side says 500 is thin; 2,000+ is comfortable.
**Fix:** Update playbook reference and TECHNICALS prompt OI thresholds.
**Files:** `committee_prompts.py`
**Effort:** 5 minutes

### D. Bid-Ask Rule Should Be % of Mid-Price
**Issue:** "$0.15 spread" rule is absolute. Should be relative: < 3% of mid ideal, 3-5% acceptable, > 5% flag.
**Fix:** Update TECHNICALS and PIVOT prompt bid-ask guidance.
**Files:** `committee_prompts.py`
**Effort:** 5 minutes

### E. SMA vs EMA Confusion in Prompts
**Issue:** Prompts mix SMA and EMA references without distinguishing which system each belongs to.
**Fix:** Explicitly separate: "For CTA flow analysis, use SMAs. For momentum indicators, use EMAs."
**Files:** `committee_prompts.py`
**Effort:** 10 minutes

### F. MACD Crossover Window Too Narrow for Swing Trading
**Issue:** 4-bar lookback is tight for swing context (21+ DTE). A crossover 5-7 days ago is still relevant.
**Fix:** Expand lookback to 7-10 bars, or add `days_since_crossover` field.
**Files:** `committee_context.py`
**Effort:** 5 minutes
