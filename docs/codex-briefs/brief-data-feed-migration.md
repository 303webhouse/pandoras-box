# CODEX BRIEF: Data Feed Migration — The Great Consolidation
## UW API Basic + yfinance + FRED → Replace Polygon, UW Discord Scraper, OpenClaw Committee

**Date:** April 13, 2026
**Status:** PROPOSED — Requires PhD-level architecture review
**Scope:** MAJOR — Touches 90+ backend files, 3 systemd services, 20 bias factors

---

## EXECUTIVE SUMMARY

This brief maps every external data dependency in Pandora's Box, determines which can be replaced by UW API Basic ($150/mo), which fall back to yfinance (free), which stay on FRED (free), and which require no replacement because the committee auto-run is being eliminated in favor of manual Claude reviews.

The result is a consolidated data stack that costs less, delivers more, and eliminates the fragile multi-service architecture that currently requires Polygon (limited by Starter tier), UW Discord scraping (fragile embed parsing), and OpenRouter API calls (low-quality committee output).

---

## PART 1: CURRENT DATA SOURCE AUDIT

### Source Map — What feeds what

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT ARCHITECTURE                          │
│                                                                  │
│  POLYGON STOCKS ($29/mo)                                        │
│  ├── get_snapshot() → ticker tape, real-time prices             │
│  ├── get_bars() → historical OHLCV for SMA calculations         │
│  └── Used by: 34 files (bias factors, scanners, enrichment)     │
│                                                                  │
│  POLYGON OPTIONS ($29/mo)                                       │
│  ├── Options chains, greeks, OI                                 │
│  ├── Spread valuation (bid/ask mid-prices)                      │
│  ├── GEX calculation (CRIPPLED: 150 contract limit)             │
│  └── Used by: polygon_options.py, gex.py, unified_positions.py  │
│                                                                  │
│  UW DISCORD SCRAPER ($68/mo dashboard + free bot)               │
│  ├── uw_watcher.py on VPS → parses Discord embeds              │
│  ├── Pushes to Redis: uw:flow:{SYM}, uw:discovery              │
│  ├── FRAGILE: breaks when UW changes embed format               │
│  └── Used by: cta_scanner, flow_ingestion, hydra_squeeze        │
│                                                                  │
│  YFINANCE (free)                                                │
│  ├── Fallback for everything Polygon can't do                   │
│  ├── VIX, indices, sector ETFs, historical bars                 │
│  ├── 63 files depend on it (largest single dependency)          │
│  └── Rate-limited, occasionally unreliable, no SLA              │
│                                                                  │
│  FRED (free)                                                    │
│  ├── Yield curve, initial claims, Sahm rule, CAPE, ISM         │
│  ├── fred_cache.py handles caching                              │
│  └── 8 files depend on it — macro factors only                  │
│                                                                  │
│  FMP — Financial Modeling Prep (free tier)                       │
│  ├── Earnings calendar (Chronos)                                │
│  └── 3 files depend on it                                       │
│                                                                  │
│  TRADINGVIEW WEBHOOKS (existing TV sub)                          │
│  ├── Signal generation (Hub Sniper, Scout, Holy Grail, CTA)    │
│  ├── Bias factors (TICK breadth, McClellan, breadth intraday)  │
│  ├── PYTHIA Market Profile levels                               │
│  └── Circuit breaker triggers                                   │
│                                                                  │
│  COINALYZE ($0 — free tier)                                    │
│  ├── BTC funding rates, OI for crypto signals                  │
│  └── 2 files depend on it                                       │
│                                                                  │
│  VPS OPENCLAW/PIVOT SERVICES                                    │
│  ├── openclaw.service: Discord chat, morning/EOD briefs        │
│  ├── pivot-collector.service: 11 bias factor collectors         │
│  │   ├── tick_breadth, vix_term, credit_spreads                │
│  │   ├── market_breadth, sector_rotation, excess_cape          │
│  │   ├── dollar_smile, savita, ad_breadth                      │
│  │   └── sector_strength                                        │
│  ├── pivot2-interactions.service: committee button handler      │
│  ├── uw-watcher.service: UW Discord embed parser               │
│  └── LLM calls via Anthropic API (Haiku/Sonnet)               │
│                                                                  │
│  OPENROUTER (eliminated)                                        │
│  └── Was: committee auto-run LLM calls                          │
│      Now: manual Claude reviews (better quality, zero cost)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## PART 2: UW API ENDPOINT MAPPING

### What UW API Basic replaces

| Current Source | Current Use | UW API Replacement Endpoint | Status |
|---------------|------------|---------------------------|--------|
| **Polygon Options** | Options chains | `/api/stock/{ticker}/option-contracts` | FULL REPLACE |
| Polygon Options | Greeks per strike | `/api/stock/{ticker}/greeks` | FULL REPLACE |
| Polygon Options | OI data | `/api/stock/{ticker}/open-interest` via flow endpoints | FULL REPLACE |
| Polygon Options | GEX calculation | `/api/stock/{ticker}/greek-exposure` + `/greek-exposure/strike` + `/greek-exposure/expiry` | FULL REPLACE (UPGRADE — no 150 contract limit) |
| Polygon Options | Spread valuation | `/api/stock/{ticker}/atm-chains` + option contract endpoints | FULL REPLACE |
| Polygon Options | IV data | `/api/stock/{ticker}/iv-rank` + `/interpolated-iv` + `/historical-risk-reversal-skew` | FULL REPLACE (UPGRADE — IV rank was missing on Polygon Starter) |
| **Polygon Stocks** | Real-time snapshot | `/api/stock/{ticker}/info` | PARTIAL — may lack intraday granularity |
| Polygon Stocks | Historical bars (OHLCV) | **NOT AVAILABLE on UW** | KEEP yfinance fallback |
| Polygon Stocks | Sector ETF prices | `/api/market/sector-etfs` | FULL REPLACE |
| **UW Discord scraper** | Flow data | `/api/stock/{ticker}/flow-recent` + `/flow-alerts` | FULL REPLACE (UPGRADE — structured JSON, not embed parsing) |
| UW Discord scraper | Discovery tickers | `/api/option-trades/flow-alerts` | FULL REPLACE |
| UW Discord scraper | Dark pool | `/api/darkpool/{ticker}` + `/darkpool/recent` | FULL REPLACE |
| UW Discord scraper | Market Tide | `/api/market/market-tide` | FULL REPLACE |
| **Manual screenshots** | GEX charts | `/api/stock/{ticker}/greek-exposure/strike-expiry` | FULL REPLACE |
| Manual screenshots | OI analysis | `/api/market/oi-change` | FULL REPLACE |
| Manual screenshots | Flow snapshots for briefs | `/api/stock/{ticker}/flow-recent` + `/api/market/top-net-impact` | FULL REPLACE |
| **FMP** | Earnings calendar | `/api/earnings/premarket` + `/afterhours` + `/{ticker}` | FULL REPLACE |
| FMP | Fundamentals | `/api/stock/{ticker}/financials` + `/balance-sheets` + `/cash-flows` + `/income-statements` | FULL REPLACE |

### What UW API adds (NEW capabilities)

| UW API Endpoint | What It Enables | Current Status |
|----------------|----------------|----------------|
| `/api/market/economic-calendar` | Automated economic event awareness | Currently manual or via FRED |
| `/api/news/headlines` | Live news feed for committee context | Currently I.18 gap ("no live news feed") |
| `/api/market/correlations` | Cross-asset correlation monitoring | Not available |
| `/api/shorts/{ticker}/interest-float/v2` | Short interest + float data | Currently manual OpenInsider checks |
| `/api/insider/{ticker}` | Insider transactions | Currently I.25 gap |
| `/api/congress/recent-trades` | Congressional trading | Not available |
| `/api/screener/stocks` | Stock screening | Not available via API |
| `/api/screener/analysts` | Analyst ratings | Currently I.21 gap ("via web search") |
| `/api/seasonality/{ticker}/monthly` | Seasonal patterns | Not available |
| `/api/market/fda-calendar` | FDA event calendar (biotech) | Not available |
| `/api/stock/{ticker}/fundamental-breakdown` | Fundamental health data | Partial via FMP |
| `/api/stock/{ticker}/max-pain` | Max pain levels | Not available |
| `/api/stock/{ticker}/flow-per-strike-intraday` | Intraday flow heatmap | Not available |
| `/api/etfs/{ticker}/in-outflow` | ETF creation/redemption flows | Not available (F.04/F.05 gap) |
| `/api/net-flow/expiry` | Net flow by expiration | Not available |
| `/api/institution/{name}/activity/v2` | Institutional positioning | Not available |
| `/api/predictions/*` | Prediction market data | Not available (Polymarket/Kalshi integration) |
| `/api/lit-flow/*` | Lit (on-exchange) flow | Not available |
| `/api/crypto/*` | Crypto whale transactions | Partial via Coinalyze |

### What stays unchanged

| Source | Why It Stays | Files Affected |
|--------|-------------|---------------|
| **yfinance** | Free fallback for historical price bars (OHLCV), SMA calculations. UW API doesn't provide historical bar data. | ~63 files |
| **FRED** | Free. Macro economic data (yield curve, claims, Sahm, CAPE, ISM). UW has economic calendar but not the underlying data series. | 8 files |
| **TradingView webhooks** | Signal generation engine. This is the core signal pipeline — scanners fire via TV Pine Script → webhook → Railway. Cannot be replaced. | ~15 files |
| **Coinalyze** | Free tier. BTC-specific derivatives data. UW has crypto whale transactions but not funding rates/OI in the same format. | 2 files |

### What gets eliminated

| Service/Source | Why It Dies | Impact |
|---------------|------------|--------|
| **Polygon Options Starter** ($29/mo) | Every function replaced by UW API with better data quality | Drop subscription |
| **Polygon Stocks Starter** ($29/mo) | Snapshot/sector data replaced by UW API. Historical bars handled by yfinance. Test thoroughly before canceling. | Drop subscription (after validation) |
| **UW Discord uw-watcher** | Replaced by direct API calls. No more fragile embed parsing. | Kill `uw-watcher.service` on VPS |
| **UW Basic dashboard** ($68/mo) | API provides all the same data programmatically | Drop subscription |
| **pivot2-interactions.service** | Committee auto-run eliminated. Manual Claude reviews via chat. | Kill service on VPS |
| **OpenRouter API calls** | Committee LLM calls eliminated | Remove from codebase |
| **FMP client** | Earnings + fundamentals replaced by UW API | Remove `fmp_client.py` |
| **Claude Pro** ($100→$20) | Hub mostly built. Basic tier sufficient for manual reviews. | Downgrade |

---

## PART 3: MIGRATION PLAN — FILE-BY-FILE IMPACT

### Tier 1: Direct Polygon Replacement (Must change)

These files import from `integrations/polygon_equities.py` or `integrations/polygon_options.py` and must be refactored to use the new `integrations/uw_api.py` client:

**integrations/ (core clients)**
- `polygon_equities.py` → Replace with `uw_api.py` stock endpoints + yfinance fallback
- `polygon_options.py` → Replace with `uw_api.py` options endpoints
- `sector_snapshot.py` → Replace with `/api/market/sector-etfs`
- `fmp_client.py` → Replace with UW earnings/fundamentals endpoints

**bias_filters/ (GEX is the critical one)**
- `gex.py` → Replace with `/api/stock/SPY/greek-exposure` (MAJOR UPGRADE)
- `iv_skew.py` → Replace with `/api/stock/{ticker}/historical-risk-reversal-skew`
- `iv_regime.py` → Can stay on yfinance (VIX-based)

**scanners/**
- `polygon_prefilter.py` → Replace with UW screener or yfinance
- `hydra_squeeze.py` → Replace short interest source with `/api/shorts/{ticker}/interest-float/v2`
- `universe.py` → Replace snapshot with yfinance or UW info endpoint

**enrichment/**
- `signal_enricher.py` → Add UW flow/GEX/OI enrichment
- `price_enrichment.py` → Replace Polygon snapshot with yfinance
- `universe_cache.py` → Replace Polygon universe with UW or yfinance

**api/**
- `market_data.py` → Replace Polygon calls
- `ticker_profile.py` → Replace with UW `/api/stock/{ticker}/info`
- `unified_positions.py` → Replace Polygon options valuation with UW
- `scanner.py` → Replace Polygon price checks
- `sectors.py` → Replace with UW sector endpoints
- `macro_strip.py` → Replace Polygon with UW market endpoints
- `hydra.py` → Replace short interest source

**data/**
- `short_interest.py` → Replace with UW `/api/shorts/{ticker}/data`

**monitoring/**
- `polygon_health.py` → Replace with UW API health check

### Tier 2: UW Discord Scraper Replacement

These files read from Redis keys set by the UW Discord scraper (`uw:flow:{SYM}`, `uw:discovery`). The Redis key schema stays the same — we just change who writes to it (API poller instead of Discord parser):

- `backend/api/uw.py` → Refactor to read from UW API instead of Redis scraper cache
- `backend/api/uw_integration.py` → Major refactor
- `backend/api/flow_ingestion.py` → Refactor ingestion from API
- `backend/discord_bridge/uw/parser.py` → ELIMINATE
- `backend/discord_bridge/uw/filter.py` → ELIMINATE (filtering moves to API query params)
- `backend/discord_bridge/uw/aggregator.py` → ELIMINATE (aggregation moves to API)
- `scripts/uw_watcher.py` → ELIMINATE
- `backend/scanners/cta_scanner.py` → Update flow confirmation to use API data
- `backend/scanners/hydra_squeeze.py` → Update UW data source

### Tier 3: VPS Service Changes

| Service | Action | Reason |
|---------|--------|--------|
| `openclaw.service` | KEEP but modify | Still handles Discord chat, morning briefs. Morning brief no longer needs manual UW screenshots — pull from API. |
| `pivot-collector.service` | KEEP | Still collects bias factors. Most use yfinance/FRED, not Polygon. |
| `pivot2-interactions.service` | ELIMINATE | Committee auto-run replaced by manual Claude reviews |
| `uw-watcher.service` | ELIMINATE | Replaced by UW API polling on Railway |

### Tier 4: New Files to Create

| File | Purpose |
|------|---------|
| `backend/integrations/uw_api.py` | Async UW API client with rate limiting, caching, error handling |
| `backend/integrations/uw_api_cache.py` | Redis caching layer for UW API responses |
| `backend/scanners/auto_scout.py` | Phase 2G flow screening pipeline |
| `backend/bias_filters/net_premium_tide.py` | New bias factor from `/api/market/market-tide` |
| `backend/bias_filters/darkpool_sentiment.py` | New bias factor from `/api/darkpool/recent` |

---

## PART 4: POLYGON STOCKS — DROP OR KEEP?

This requires careful analysis. Polygon Stocks ($29/mo) provides two things:

**1. Real-time snapshots (`get_snapshot`)** — Used for the ticker tape, real-time position valuation, and sector rotation calculations.

UW API has `/api/stock/{ticker}/info` which returns current price data. However, the response latency and update frequency need testing. If UW's stock info endpoint provides near-real-time quotes, Polygon Stocks can be dropped entirely.

yfinance also provides real-time-ish quotes (15-min delay on some endpoints, real-time on others). The hub's ticker tape currently refreshes every 15 seconds via Polygon snapshot. If it can tolerate 30-60 second latency from yfinance, that works.

**2. Historical bars (`get_bars`)** — Used for SMA calculations (20/50/120/200 SMAs), ATR, RSI, Bollinger Bands across all bias factors and scanners.

UW API does NOT provide historical OHLCV bars. This is the one gap. yfinance handles this today as a fallback, and it works — but it's rate-limited and occasionally returns stale data.

**Recommendation:** Drop Polygon Stocks but add a validation sprint. Run yfinance as the sole price bar source for 1 week on a staging branch. If bias factor calculations remain accurate and the ticker tape latency is acceptable, ship it. If yfinance proves unreliable under full load, keep Polygon Stocks as a $29/mo insurance policy.

---

## PART 5: VPS MORNING BRIEF UPGRADE

Currently the morning brief flow is:

```
1. Pivot posts "drop your UW screenshots" to Discord
2. Nick manually screenshots Market Tide, GEX, etc.
3. Nick posts to Discord
4. Pivot reads screenshots, generates brief
5. If Nick doesn't respond, brief fires without UW data
```

With UW API:

```
1. Brief cron fires at 9:30 AM ET
2. Backend pulls from UW API:
   - /api/market/market-tide → net premium flow
   - /api/market/sector-etfs → sector rotation
   - /api/market/oi-change → OI shifts
   - /api/market/top-net-impact → top flow tickers
   - /api/stock/SPY/greek-exposure → GEX levels
   - /api/darkpool/recent → dark pool activity
   - /api/market/economic-calendar → today's events
   - /api/news/headlines → market-moving news
   - /api/earnings/premarket → pre-market earnings
3. Pivot generates brief with FULL data context
4. No manual screenshots needed — ever
```

This alone justifies the API subscription. The morning brief becomes fully autonomous and data-complete.

---

## PART 6: TRAINING BIBLE UPDATES (Section I)

With UW API, the following data gaps in Section I are resolved:

| Bible Ref | Current Status | New Status |
|-----------|---------------|------------|
| I.06 (UW flow data) | Via Discord scraper, fragile | **RESOLVED** — Direct API, structured JSON |
| I.07 (UW market flow) | Via Discord scraper | **RESOLVED** — `/api/market/market-tide` + `/top-net-impact` |
| I.13 (Market Profile) | Manual TV checks | **UNCHANGED** — UW doesn't provide MP data. TV webhooks + MCP cover this. |
| I.14 (Level 2 / orderbook) | Not available | **PARTIALLY RESOLVED** — Dark pool bid/ask sentiment via API |
| I.17 (Live options chain) | Not available (Polygon Starter too limited) | **RESOLVED** — Full chains, IV rank, greeks, all strikes |
| I.18 (News headlines) | Not available | **RESOLVED** — `/api/news/headlines` |
| I.21 (Analyst consensus) | Manual web search | **RESOLVED** — `/api/screener/analysts` |
| I.25 (Insider transactions) | Manual OpenInsider checks | **RESOLVED** — `/api/insider/{ticker}` |
| I.26 (Short interest) | Manual / limited Polygon | **RESOLVED** — `/api/shorts/{ticker}/interest-float/v2` |

**6 of 8 data gaps in the Training Bible are fully resolved by UW API.**

---

## PART 7: BUILD ORDER (Chunked)

### Sprint 0: Validation (Before ANY subscription changes)
- [ ] Sign up for UW API Basic ($150/mo)
- [ ] Test 10 critical endpoints manually (curl or Postman)
- [ ] Verify: `/api/stock/SPY/greek-exposure` returns full GEX data
- [ ] Verify: `/api/stock/SPY/flow-recent` returns structured flow
- [ ] Verify: `/api/market/market-tide` returns tide data
- [ ] Verify: `/api/stock/SPY/info` returns usable price data
- [ ] Verify: rate limits (120/min) work for planned polling pattern
- [ ] Compare: yfinance SPY bars vs Polygon bars — any material differences?
- [ ] **DO NOT cancel any existing subscriptions until Sprint 0 passes**

### Sprint 1: Core API Client (Weekend 1)
- [ ] Create `backend/integrations/uw_api.py`
- [ ] Async httpx client with:
  - Bearer token auth
  - Rate limiter (120/min)
  - Retry logic with exponential backoff
  - Response caching in Redis (configurable TTL per endpoint)
  - Request counting for daily budget monitoring
- [ ] Create `backend/integrations/uw_api_cache.py`
- [ ] Health check: `/api/uw/health`
- [ ] Test: full request cycle for 5 endpoints

### Sprint 2: GEX + Flow Migration (Weekend 2)
- [ ] Refactor `bias_filters/gex.py` to use UW API
- [ ] Refactor `backend/api/uw.py` to use UW API instead of Redis scraper
- [ ] Refactor `backend/api/flow_ingestion.py`
- [ ] Update Redis key schema if needed (prefer keeping same keys for backward compat)
- [ ] Add flow polling loop (every 30s during market hours)
- [ ] Kill `uw-watcher.service` on VPS
- [ ] Test: verify flow data appears in hub exactly as before

### Sprint 3: Polygon Replacement (Weekend 3)
- [ ] Refactor `integrations/polygon_options.py` → route to UW API
- [ ] Refactor `integrations/polygon_equities.py` → route to yfinance + UW info
- [ ] Update `signal_enricher.py` with UW enrichment data
- [ ] Update `unified_positions.py` spread valuation
- [ ] Update `hydra_squeeze.py` short interest source
- [ ] Update `short_interest.py`
- [ ] Run full bias engine cycle and compare scores: old sources vs new sources
- [ ] **If scores match within 5%: cancel Polygon Options**
- [ ] **If yfinance validation passed in Sprint 0: cancel Polygon Stocks**

### Sprint 4: Morning Brief + Earnings (Weekend 4)
- [ ] Update VPS morning brief to pull UW API data instead of requiring screenshots
- [ ] Replace FMP earnings calendar with UW earnings endpoints
- [ ] Add economic calendar from `/api/market/economic-calendar`
- [ ] Add news headlines from `/api/news/headlines` to committee context
- [ ] Add insider/congressional data to enrichment pipeline
- [ ] Kill `pivot2-interactions.service` on VPS
- [ ] Cancel UW Basic dashboard subscription ($68/mo)
- [ ] Downgrade Claude Pro to Basic ($20/mo)

### Sprint 5: Phase 2G Auto-Scout (see separate brief)
- [ ] Per brief-phase-2g-auto-scout.md

### Sprint 6: New Indicators (Weeks 5-8)
- [ ] Implement Net Premium Tide bias factor
- [ ] Implement Dark Pool Sentiment bias factor
- [ ] Upgrade GEX regime classifier
- [ ] Implement Options-Equity Divergence detector
- [ ] Implement Whale Flow Momentum scanner
- [ ] Implement GEX Flip Breakout strategy
- [ ] Update Training Bible Section I
- [ ] Performance review: are new factors improving bias accuracy?

---

## PART 8: RISK MATRIX

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| UW API downtime | Medium | High — no flow data | Keep yfinance as price fallback; cache aggressively (5-min TTL on flow, 15-min on GEX) |
| UW API data quality differs from dashboard | Low | Medium | Sprint 0 validation catches this before migration |
| yfinance can't handle full load without Polygon | Medium | Medium | Keep Polygon Stocks as $29/mo insurance if Sprint 0 fails |
| Rate limits hit during high-activity market days | Low | Medium | Request budget is 3,058/day of 20,000 — 85% headroom |
| Breaking changes to UW API | Low | High | Pin to current API version; monitor UW changelog |
| Bias factor scores diverge after migration | Medium | High | Sprint 3 comparison test catches this; don't cancel until validated |
| Morning brief quality degrades | Low | Low | API data is strictly better than manual screenshots |

---

## PART 9: COST SUMMARY (FINAL)

### Before
| Service | Monthly |
|---------|---------|
| UW Basic Dashboard | $68 |
| Polygon Options Starter | $29 |
| Polygon Stocks Starter | $29 |
| Claude Pro | $100 |
| FMP | $0 (free tier) |
| TradingView Premium | ~$57 |
| Railway | ~$10 |
| Hetzner VPS | ~$5 |
| Anthropic API (OpenRouter) | ~$8 |
| FRED / yfinance / Coinalyze | $0 |
| **Total** | **~$306/mo** |

### After
| Service | Monthly |
|---------|---------|
| UW API Basic | $150 |
| Claude Basic | $20 |
| TradingView Premium | ~$57 |
| Railway | ~$10 |
| Hetzner VPS | ~$5 |
| Anthropic API (Pivot chat only) | ~$5 |
| yfinance / FRED / Coinalyze | $0 |
| TV MCP Server | $0 |
| **Total** | **~$247/mo** |

### Net savings: ~$59/mo ($708/yr)
### Services eliminated: 5 (Polygon ×2, UW Basic, FMP, OpenRouter)
### Services added: 1 (UW API Basic)
### VPS services killed: 2 (uw-watcher, pivot2-interactions)
### Training Bible gaps resolved: 6 of 8
### New capabilities: 17 new API endpoint categories
