# BRIEF: Single Ticker Analyzer v2 (Phase 3)

**Priority:** P0
**Depends on:** Phase 1 (Polygon snapshot cache), Phase 2 (sector_constituents table)
**Touches:** Backend (main.py / routes, new profile aggregator), Frontend (app.js — new modal component), Supabase (new table for baselines)

---

## Summary

Rebuild the Single Ticker Analyzer as a card-grid modal popup with comprehensive company/trading data. This replaces the current minimal ticker analysis with a rich, skimmable profile that answers: "What does this company do, how is it positioned right now, and should I trade it?" Includes a one-click Olympus Committee quick review powered by a single Sonnet API call. All fast-moving data refreshes every 5 seconds during market hours.

---

## Architecture Overview

### Data sources per field

| Field | Source | Refresh Rate |
|-------|--------|-------------|
| Price, day change% | Polygon snapshot cache (Redis) | 5 sec |
| Week/month change% | Polygon aggregates or calculate | 5 min |
| 52-week high/low | Polygon or yfinance | Daily cache |
| RSI (14-period) | Redis RSI cache (scanner infra) | 5 min |
| Volume ratio (today vs 20d avg) | Snapshot volume vs sector_constituents.avg_volume_20d | 5 min |
| Market cap | Polygon reference data | Daily cache |
| Sector, industry | sector_constituents table + Polygon reference | Static |
| Company description | Polygon ticker details (/v3/reference/tickers/{ticker}) | Static (cache in Supabase) |
| Beta to SPY | Calculated from 60-day returns | Nightly batch |
| Beta to sector ETF | Calculated from 60-day returns | Nightly batch |
| Sector-relative rank | Calculated from sector popup data | 5 min |
| Options flow (last 5 events) | flow_events table (Supabase) | 5 min |
| Net flow direction | Derived from flow_events | 5 min |
| Next earnings date | yfinance or Polygon | Daily cache |
| Dividend yield | Polygon reference or yfinance | Daily cache |
| P/E ratio | yfinance (if available) | Daily cache |
| Analyst consensus | yfinance (if available) | Daily cache — best effort, don't block on this |

### Two-tier refresh (same pattern as Phase 2)

| Tier | Fields | Refresh |
|------|--------|---------|
| Fast (5 sec) | price, day_change_pct | Polygon snapshot cache |
| Slow (5 min) | rsi, volume_ratio, week/month change, flow events, sector rank | Redis + Supabase |
| Static (on open) | description, market_cap, beta, earnings, dividend, P/E, analyst | Supabase ticker_profiles cache |

---

## Backend Changes

### 1. New Supabase table: `ticker_profiles`

Cache for slow-changing reference data so we don't re-fetch from Polygon/yfinance on every popup open.

```sql
CREATE TABLE IF NOT EXISTS ticker_profiles (
    ticker VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(200),
    description TEXT,
    sector VARCHAR(50),
    industry VARCHAR(100),
    market_cap BIGINT,
    high_52w NUMERIC(12,2),
    low_52w NUMERIC(12,2),
    pe_ratio NUMERIC(8,2),
    dividend_yield NUMERIC(6,4),
    next_earnings_date DATE,
    analyst_consensus VARCHAR(20),  -- 'Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell', or NULL
    analyst_count INTEGER,
    beta_spy NUMERIC(6,3),          -- beta vs SPY
    beta_sector NUMERIC(6,3),       -- beta vs sector ETF
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Population:** Nightly batch job that refreshes all tickers in `sector_constituents`. Also refreshes on-demand when a ticker popup opens and the profile is >24h stale or missing.

### 2. New endpoint: `GET /api/ticker/{symbol}/profile`

**Response shape (full load):**

```json
{
    "ticker": "AAPL",
    "company_name": "Apple Inc",
    "description": "Apple Inc designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories. The company also sells digital content, apps, and services.",
    
    "price_action": {
        "price": 187.43,
        "day_change_pct": -0.31,
        "week_change_pct": -2.1,
        "month_change_pct": -5.4,
        "high_52w": 199.62,
        "low_52w": 143.28,
        "rsi_14": 42,
        "volume_ratio": 2.3,
        "volume_ratio_label": "heavy"
    },
    
    "fundamentals": {
        "market_cap": 2890000000000,
        "market_cap_label": "$2.89T",
        "pe_ratio": 28.5,
        "dividend_yield": 0.0055,
        "next_earnings_date": "2026-04-24",
        "analyst_consensus": "Buy",
        "analyst_count": 38
    },
    
    "positioning": {
        "sector": "Technology",
        "sector_etf": "XLK",
        "industry": "Consumer Electronics",
        "beta_spy": 1.21,
        "beta_sector": 0.87,
        "sector_relative_pct": 1.21,
        "sector_rank": 5,
        "sector_rank_total": 20,
        "sector_rank_label": "5th of 20 in XLK"
    },
    
    "flow": {
        "net_direction": "bearish",
        "recent_events": [
            {
                "timestamp": "2026-03-27T14:22:00Z",
                "type": "PUT",
                "premium": 1250000,
                "premium_label": "$1.25M",
                "strike": 180,
                "expiry": "2026-04-17",
                "sentiment": "bearish"
            }
        ]
    },
    
    "updated_at": "2026-03-27T14:30:05Z",
    "is_market_hours": true
}
```

**Response shape (fast=true):**

```json
{
    "ticker": "AAPL",
    "price": 187.43,
    "day_change_pct": -0.31,
    "updated_at": "2026-03-27T14:30:05Z"
}
```

**Implementation notes:**

1. Read price data from shared Polygon snapshot cache
2. Read RSI from Redis scanner cache (lazy-calculate if missing, same as Phase 2)
3. Read static profile from `ticker_profiles` table. If missing or >24h stale, trigger an async refresh:
   - Polygon `/v3/reference/tickers/{ticker}` for description, market cap, sector, industry
   - yfinance as fallback for P/E, dividend, earnings date, analyst ratings
   - Calculate beta from 60 daily returns (Polygon daily bars) vs SPY and vs sector ETF
   - Write results to `ticker_profiles`
4. Read flow events from `flow_events` WHERE ticker = X ORDER BY created_at DESC LIMIT 5
5. Calculate sector_relative_pct and rank from sector_constituents + snapshot cache
6. Format market_cap as human-readable ("$2.89T", "$45.2B", "$890M")

### 3. Nightly profile refresh job

Create a scheduled task that runs once daily (e.g., 6:00 AM ET, before market open) and refreshes `ticker_profiles` for all tickers in `sector_constituents`. This ensures profiles are warm when Nick opens them during the day.

**Implementation:** Loop through all unique tickers in `sector_constituents`, call Polygon reference + yfinance for each, update the `ticker_profiles` table. Rate-limit to avoid hammering APIs — 1 ticker per second is fine for 220 tickers (~4 minutes total).

Also recalculate beta values during this job:
- For each ticker, fetch 60 daily bars from Polygon
- Fetch 60 daily bars for SPY and the ticker's sector ETF
- Calculate beta = covariance(ticker_returns, benchmark_returns) / variance(benchmark_returns)
- Store in `ticker_profiles.beta_spy` and `ticker_profiles.beta_sector`

Also refresh `sector_constituents.avg_volume_20d` during this job:
- For each ticker, average the volume from the last 20 daily bars

### 4. Olympus Quick Review endpoint: `POST /api/committee/quick-review`

**Request body:**

```json
{
    "ticker": "AAPL",
    "direction": "bearish",
    "timeframe": "swing"
}
```

`direction` is optional — if omitted, the committee evaluates both directions. `timeframe` defaults to "swing" (2-10 day hold).

**What happens internally:**

1. Fetch the full profile data (same as GET /api/ticker/{symbol}/profile)
2. Fetch current macro briefing context (from existing committee_context.py)
3. Fetch last 24h of flow data for this ticker
4. Bundle everything into a structured prompt using the Olympus committee framework
5. Make ONE Anthropic API call to Claude Sonnet with the combined prompt
6. Return the response

**Prompt structure (store as a template on Railway, not hardcoded in frontend):**

```
You are the Olympus Trading Committee evaluating {TICKER} for a potential {DIRECTION} {TIMEFRAME} trade.

CURRENT MARKET CONTEXT:
{macro_briefing}

TICKER PROFILE:
{full_profile_json}

RECENT OPTIONS FLOW:
{flow_events}

CURRENT POSITIONS:
{any existing positions in this ticker from unified_positions}

Provide a condensed committee review with three sections:

## Bull Case
What supports a long/bullish position? Include specific price levels, catalysts, and flow signals.

## Bear Case  
What supports a short/bearish position? Include specific risks, resistance levels, and negative signals.

## Verdict
- Direction: BULLISH / BEARISH / NEUTRAL
- Conviction: HIGH / MEDIUM / LOW
- Suggested structure: (e.g., "Apr 17 $180/$170 put spread" or "avoid — conflicting signals")
- Key risk: The single biggest thing that could make this trade wrong
- Trip wire: Specific price/event that invalidates the thesis
```

**Response shape:**

```json
{
    "ticker": "AAPL",
    "review": "## Bull Case\n...\n\n## Bear Case\n...\n\n## Verdict\n...",
    "direction": "bearish",
    "conviction": "medium",
    "model": "claude-sonnet-4-6",
    "cost_estimate": "$0.02",
    "generated_at": "2026-03-27T14:35:00Z"
}
```

**Cost guardrails:**
- Max input tokens: ~3000 (profile + macro + flow context)
- Max output tokens: 1000
- Estimated cost per review: $0.01-0.03
- No automatic retries — if the API call fails, return an error to the frontend

---

## Frontend Changes

### 1. Single Ticker Analyzer Modal

**Trigger:** Clicking any ticker row in the sector popup, OR clicking a ticker anywhere else in the UI where `analyzeTicker()` is currently called.

**Size:** 750px wide × 580px tall. Centered modal with semi-transparent backdrop. Z-index ABOVE the sector popup (so both can be open — sector popup underneath, ticker popup on top).

**Layout — card grid format:**

```
┌─────────────────────────────────────────────────────────┐
│  AAPL — Apple Inc                    $187.43 ▼0.31% [×] │
│  Consumer Electronics | Technology (XLK)                 │
├──────────────────┬──────────────────┬────────────────────┤
│  PRICE ACTION    │  FUNDAMENTALS    │  FLOW & SENTIMENT  │
│                  │                  │                     │
│  Day:  -0.31%    │  Mkt Cap: $2.89T │  Flow: 🔴 Bearish  │
│  Week: -2.1%     │  P/E: 28.5       │                     │
│  Month: -5.4%    │  Div: 0.55%      │  $1.25M PUT 180 4/17│
│                  │  Earnings: 4/24  │  $890K PUT 175 4/17 │
│  RSI: 42         │  Analyst: Buy    │  $650K CALL 195 4/17│
│  Vol: 🔥 2.3x    │   (38 analysts)  │                     │
│                  │                  │                     │
│  52w: ████░░ 78% │                  │                     │
├──────────────────┴─────────────┬────┴────────────────────┤
│  POSITIONING                   │  ABOUT                   │
│                                │                          │
│  Beta (SPY): 1.21              │  Apple designs and       │
│  Beta (XLK): 0.87              │  manufactures smart-     │
│  Sector rank: 5th of 20        │  phones, computers,      │
│  Rel. perf: +1.21% vs XLK     │  tablets, wearables...   │
│                                │                          │
├────────────────────────────────┴──────────────────────────┤
│  [🏛️ Run Olympus Review]              [+ Add to Watchlist]│
└───────────────────────────────────────────────────────────┘
```

### Card Details

**PRICE ACTION card (top-left):**
- Day/Week/Month change percentages, color-coded green/red (absolute, not relative)
- RSI with color hint: <30 green ("oversold"), 30-70 gray ("neutral"), >70 red ("overbought")
- Volume ratio with emoji indicator (same as sector popup: 🔥📈😴)
- 52-week range as a mini progress bar showing where current price sits between low and high

**FUNDAMENTALS card (top-center):**
- Market cap formatted human-readable ($2.89T, $45.2B, etc.)
- P/E ratio (show "N/A" if unavailable)
- Dividend yield as percentage (show "—" if none)
- Next earnings date (highlight in yellow if within 14 days — affects options pricing)
- Analyst consensus + count (show "N/A" if unavailable — this field is best-effort)

**FLOW & SENTIMENT card (top-right):**
- Net flow direction indicator at top (🟢 Bullish / 🔴 Bearish / ⚪ Neutral)
- List of last 3-5 flow events from flow_events table, each showing:
  - Premium (formatted: $1.25M, $890K)
  - Type (PUT/CALL)
  - Strike price
  - Expiry date
  - Color-coded: puts in red text, calls in green text
- If no flow events exist for this ticker, show "No recent flow data"

**POSITIONING card (bottom-left):**
- Beta to SPY with interpretation hint:
  - β > 1.5: "(volatile — consider smaller size)"
  - β < 0.7: "(slow mover — needs wider strikes)"
  - β 0.7-1.5: no hint needed
- Beta to sector ETF
- Sector rank: "5th of 20 in XLK" — pulled from sector leaders data
- Sector-relative performance: "+1.21% vs XLK" with green/red coloring

**ABOUT card (bottom-right):**
- Company description from ticker_profiles.description
- Truncate to ~200 characters with "..." if longer
- Sector and industry labels (if not already shown in header)

### 2. Bottom action bar

**[🏛️ Run Olympus Review] button:**
- On click: show a loading spinner in the button ("Analyzing...")
- POST to `/api/committee/quick-review` with `{ ticker, direction: null, timeframe: "swing" }`
- On response: expand the modal downward (or open a new panel/tab within the modal) to show the review text
- Render the review markdown as formatted HTML (the response contains markdown headers and bullets)
- Show the conviction badge (HIGH/MEDIUM/LOW) and direction (BULLISH/BEARISH/NEUTRAL) prominently
- Show the cost estimate subtly at the bottom ("~$0.02")
- If API call fails: show error message in the review panel, don't crash the popup

**[+ Add to Watchlist] button:**
- On click: call the existing watchlist add function (search app.js for watchlist add/management)
- If no watchlist function exists yet, wire it to a stub that shows "Coming soon" toast
- Button should toggle to "✓ On Watchlist" if the ticker is already watched

### 3. TradingView integration

When the ticker popup opens, also change the TradingView widget symbol to the selected ticker. Search app.js for the existing TV widget symbol change function — likely `tvWidget.setSymbol()` or `chart.setSymbol()` or similar.

### 4. Polling logic

Same pattern as Phase 2:

```javascript
let tickerPopupInterval = null;
let tickerFullRefreshInterval = null;

function openTickerPopup(symbol) {
    // Initial full load
    fetchTickerProfile(symbol, false);
    showTickerModal();
    changeTVSymbol(symbol);

    // Fast refresh every 5 seconds (price only)
    tickerPopupInterval = setInterval(() => {
        fetchTickerProfile(symbol, true);  // fast=true
    }, 5000);

    // Full refresh every 5 minutes
    tickerFullRefreshInterval = setInterval(() => {
        fetchTickerProfile(symbol, false);
    }, 300000);
}

function closeTickerPopup() {
    // CRITICAL: Clear intervals
    if (tickerPopupInterval) {
        clearInterval(tickerPopupInterval);
        tickerPopupInterval = null;
    }
    if (tickerFullRefreshInterval) {
        clearInterval(tickerFullRefreshInterval);
        tickerFullRefreshInterval = null;
    }
    hideTickerModal();
}
```

### 5. Popup stacking rules

- Sector popup and ticker popup can BOTH be open simultaneously
- Ticker popup renders ON TOP of sector popup (higher z-index)
- Closing ticker popup returns focus to sector popup (if still open)
- Only ONE ticker popup open at a time — clicking a different ticker closes the current one and opens the new one
- Closing sector popup also closes any open ticker popup (and clears its intervals)
- The Olympus review panel is part of the ticker popup, not a separate popup

### 6. Opening from non-sector contexts

The ticker popup should also be openable from:
- Trade idea cards on the Agora dashboard (clicking the ticker name)
- Any other place in the UI where a ticker is clickable
- Wire this by making `openTickerPopup(symbol)` a global function callable from anywhere

Currently `analyzeTicker()` or similar function handles this — find it in app.js and either rename it to `openTickerPopup()` or have it call `openTickerPopup()`.

---

## Supabase Migration

```sql
-- Migration: create ticker_profiles table
CREATE TABLE IF NOT EXISTS ticker_profiles (
    ticker VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(200),
    description TEXT,
    sector VARCHAR(50),
    industry VARCHAR(100),
    market_cap BIGINT,
    high_52w NUMERIC(12,2),
    low_52w NUMERIC(12,2),
    pe_ratio NUMERIC(8,2),
    dividend_yield NUMERIC(6,4),
    next_earnings_date DATE,
    analyst_consensus VARCHAR(20),
    analyst_count INTEGER,
    beta_spy NUMERIC(6,3),
    beta_sector NUMERIC(6,3),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Committee Review Prompt Template

Store this as a constant in a new file (e.g., `backend/committee/quick_review_prompts.py`) or alongside the existing committee prompt templates.

```python
QUICK_REVIEW_PROMPT = """You are the Olympus Trading Committee providing a rapid assessment of {ticker} ({company_name}).

CURRENT MACRO CONTEXT:
{macro_context}

TICKER PROFILE:
- Price: ${price} ({day_change_pct:+.2f}% today, {week_change_pct:+.2f}% this week, {month_change_pct:+.2f}% this month)
- RSI(14): {rsi_14}
- Volume: {volume_ratio:.1f}x average ({volume_label})
- Market Cap: {market_cap_label}
- P/E: {pe_ratio}
- Sector: {sector} ({sector_etf}) | Rank: {sector_rank_label}
- Sector-relative: {sector_relative_pct:+.2f}%
- Beta (SPY): {beta_spy:.2f} | Beta ({sector_etf}): {beta_sector:.2f}
- 52-week range: ${low_52w} — ${high_52w}
- Next earnings: {next_earnings_date}
- Analyst consensus: {analyst_consensus} ({analyst_count} analysts)

RECENT OPTIONS FLOW (last 24h):
{flow_summary}

EXISTING POSITIONS IN THIS NAME:
{existing_positions}

{direction_instruction}

Provide a condensed committee review:

## Bull Case
2-3 specific reasons to go long. Include price levels and catalysts.

## Bear Case
2-3 specific reasons to go short. Include price levels and risks.

## Verdict
- **Direction:** BULLISH / BEARISH / NEUTRAL
- **Conviction:** HIGH / MEDIUM / LOW  
- **Suggested structure:** A specific options spread or "avoid" with reasoning
- **Key risk:** The single biggest thing that could make this wrong
- **Trip wire:** Specific price level or event that invalidates the thesis

Keep the entire response under 400 words. Be specific about price levels and strike prices. Reference the flow data and sector positioning in your reasoning.
"""

DIRECTION_INSTRUCTION_NEUTRAL = "Evaluate both bullish and bearish cases equally."
DIRECTION_INSTRUCTION_BIASED = "The trader is leaning {direction}. Evaluate both sides but focus the Verdict on the {direction} thesis — confirm or challenge it."
```

---

## Testing Checklist

1. **Profile endpoint:** `GET /api/ticker/AAPL/profile` returns all cards' data correctly
2. **Fast mode:** `GET /api/ticker/AAPL/profile?fast=true` returns only price
3. **Missing profile:** First open of an uncached ticker triggers async profile fetch and returns partial data, then fills in on next poll
4. **Modal renders:** All 5 cards display with correct data and layout
5. **Flow events:** Flow card shows actual data from flow_events table (or "No recent flow data")
6. **52-week bar:** Progress bar correctly positions current price between high and low
7. **Earnings highlight:** Earnings within 14 days shows yellow highlight
8. **Beta hints:** Beta > 1.5 shows "volatile" hint, < 0.7 shows "slow mover" hint
9. **Committee review:** Clicking Run Olympus Review → loading state → review renders in expanded panel
10. **Committee error handling:** If Anthropic API fails, shows error message (doesn't crash popup)
11. **Polling works:** Price updates every 5 seconds, full data every 5 minutes
12. **Polling cleanup:** Closing popup clears all intervals
13. **TV integration:** Opening popup changes TradingView symbol
14. **Stacking:** Sector popup stays open underneath ticker popup
15. **Global access:** `openTickerPopup('AAPL')` works from trade idea cards and other UI locations

---

## What This Brief Does NOT Cover

- Contextual Modifier / trade idea enrichment (Phase 4 — separate brief)
- Watchlist management system (future build — button is wired to stub for now)
- Full 4-persona committee review (this brief implements the condensed 3-section format only)
- Nightly batch job infrastructure/scheduler (this brief defines what the job does; if no scheduler exists yet, CC should add it to the existing startup/cron pattern)

---

## Notes for Claude Code

- The frontend is vanilla JS in a single large `app.js` (~420KB). Use Desktop Commander with `start_search` and `literalSearch: True` to find anchors.
- Search for the existing ticker analysis function (`analyzeTicker`, `analyzeStock`, or similar) — this is being replaced/upgraded.
- Search for TradingView widget integration to find the symbol change function.
- The committee prompt template should live alongside existing committee prompts — search for `committee_prompts` or `PIVOT` prompt constants.
- The ANTHROPIC_API_KEY env var should already exist on Railway for the committee pipeline. Use the same key for quick reviews.
- Modal CSS should match the existing dark theme. Use the same color palette as the sector popup modal from Phase 2.
- The `ticker_profiles` table is a cache — stale data is acceptable. Never block the popup on a profile refresh. Show what you have, update async.
- Market cap formatting helper: write a utility function that converts raw numbers to $XXX.XXT/B/M format. This will be reused across the UI.
