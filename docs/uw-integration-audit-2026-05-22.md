# UW Integration Audit — 2026-05-22

**Status:** Audit-only. No code changes. No new endpoints called from the audit itself beyond fetching `https://api.unusualwhales.com/api/openapi` once (cached at `docs/audit-artifacts/2026-05-22/uw-openapi.yaml`).

**Authoritative artifacts:**
- `docs/audit-artifacts/2026-05-22/uw-openapi.yaml` — Unusual Whales OpenAPI 3.0.0, 177 paths, fetched 2026-05-22.
- This document.

**Scope:** Inventory every UW touchpoint in `backend/`; diff against the OpenAPI surface; diagnose the Agora Sector Heatmap popup data-flow gap; propose build scope. Nothing more.

---

## 1. Summary

- **Coverage today:** Pandora's Box wraps **22 / 177 UW paths (12%)** through `backend/integrations/uw_api.py`. The remaining 155 are unused.
- **Canonical client status:** `uw_api.py` is the single client, with circuit breaker + token-bucket rate limiter (120 req/min). Polygon and FMP are deprecated dead code per `PROJECT_RULES.md`. `get_snapshot` was migrated off yfinance to UW `/stock-state` + `/info` on 2026-04-28. **`get_bars` still uses yfinance** — only outlier left in the hot path.
- **Sector Heatmap popup gap:** the popup table headers promise 11 columns (TICKER / PRICE / DAY% / REL% / WK% / MO% / RSI / VOL / Flow / IV / DP). The `/sectors/{etf}/leaders` route returns only 8 with real data; **`week_change_pct` and `month_change_pct` are hardcoded `None`** at `backend/api/sectors.py:728-729`. `rsi_14` depends on a Redis cache populated by other scanners and is silently `None` when those scanners haven't run. `flow_direction` is derived from the `flow_events` Postgres table (24h window), not a live UW call. No "ticker info" sub-card exists below the row — popup is row-only.
- **Top unwrapped value, ranked by frequency that the Olympus committee or Agora dashboard would benefit:**
  1. `stock/{ticker}/greeks` — committee + position MTM (BOTH).
  2. `stock/{ticker}/flow-alerts` — actionable single-trade alerts (BOTH).
  3. `market/{ticker}/etf-tide` — fast ETF-flavored flow tile (BOTH).
  4. `market/{sector}/sector-tide` — sector-rotation directional read (BOTH).
  5. `stock/{ticker}/technical-indicator/{function}` — replaces the Redis-scanner-dependent RSI in the heatmap popup (AGORA).
  6. `stock/{ticker}/oi-change` and `market/oi-change` — positioning shifts day-over-day (OLYMPUS).
  7. `stock/{ticker}/spot-exposures` — live GEX surface, complements `greek-exposure` (OLYMPUS).
  8. `option-trades/flow-alerts` — feeds Agora flow tile + committee enrichment (BOTH).
  9. `stock/{ticker}/expiry-breakdown` — option expiry concentration (OLYMPUS).
  10. `companies/{ticker}/profile` — replaces the missing "ticker info" card under the heatmap popup row (AGORA).
- **OLYMPUS / AGORA / BOTH / NEITHER split** across the 155 unwrapped: OLYMPUS = 56, AGORA = 30, BOTH = 27, NEITHER = 42 (crypto, forex, commodities, prediction markets, private markets, sockets, deprecated v1 variants — out of scope).
- **Hot fixes that should ride along with any new build:** delete the stale `# yfinance under the hood` comment at `backend/api/sectors.py:462` (no longer true since the 2026-04-28 hotfix); migrate `get_bars` off yfinance to `/api/stock/{ticker}/ohlc/{candle_size}` to honor the Data Source Hierarchy fully.

`UW_API_KEY` is set in Railway and `.env`. Not printed, not logged, not committed.

---

## 2. Current UW coverage

### 2.1 The 22 wrapped endpoints

| # | UW endpoint | Wrapper in `uw_api.py` | Consumed by (modules) | Surfaces (key fields) | Notes / dropped |
|---|---|---|---|---|---|
| 1 | `/api/stock/{ticker}/ohlc/{candle_size}` (1d) | `_get_regular_session_change` (helper for `get_snapshot`) | `get_snapshot` only | `c, h, l, o, v, t` | Only used to compute regular-session change inside `get_snapshot`. Not exposed as a standalone wrapper. |
| 2 | `/api/stock/{ticker}/info` | `_get_info_cached_long` → `get_snapshot` | sectors, macro_strip, market_data, ticker_profile, scanners, analysis, hub_mcp `quote` | `name, sector, marketcap, description, …` (limited subset) | UW info is broad; backend uses name + a few fundamentals. Most fields dropped. |
| 3 | `/api/stock/{ticker}/stock-state` | `get_snapshot` | sectors, macro_strip, market_data, ticker_profile, scanners, analysis, hub_mcp `quote` | `price, day_change_pct, volume, prev_volume` | UW state returns full intraday OHLCV. Backend only surfaces 4 fields. |
| 4 | `/api/stock/{ticker}/option-contracts` | `get_options_snapshot` | market_data, bias_filters/gex, bias_filters/iv_skew | Full chain passthrough through `/market/options-chain` | Chain is used for spread valuation + GEX/IV; downstream consumers cherry-pick contracts. |
| 5 | `/api/stock/{ticker}/flow-recent` | `get_flow_recent` | scanners/wh_accumulation, scheduler/bias_scheduler | Used internally for accumulation scoring; not directly exposed | Aggregated into Redis + Postgres flow_events. |
| 6 | `/api/stock/{ticker}/flow-per-expiry` | `get_flow_per_expiry` | jobs/uw_flow_poller | Persisted to `flow_events` table | Backend cron persists; UI reads aggregates, not raw rows. |
| 7 | `/api/stock/{ticker}/greek-exposure` | `get_greek_exposure` | bias_filters/gex, scanners/wh_accumulation | GEX series → daily aggregate value | Drops per-strike, per-expiry detail (those endpoints are unwrapped). |
| 8 | `/api/stock/{ticker}/max-pain` | `get_max_pain` | committee_bridge `/committee/enrichment/{ticker}` | Only entries `<5 DTE` surfaced | Full series dropped. |
| 9 | `/api/stock/{ticker}/iv-rank` | `get_iv_rank` | sectors `_get_iv_rank_for_ticker`, committee_bridge | `iv_rank` (0-100), `tier` low/mid/high | Drops `current_iv`, time-series, history. |
| 10 | `/api/market/market-tide` | `get_market_tide` | committee_bridge | `net_call_premium, net_put_premium, net_volume` | Drops full time-series. |
| 11 | `/api/market/sector-etfs` | `get_sector_etfs` | committee_bridge `_get_sector_flow` | Top 5 bullish + top 5 bearish | Drops middle sectors + non-summary fields. |
| 12 | `/api/market/economic-calendar` | `get_economic_calendar` | api/insider.py `/market/economic-calendar` | Passthrough | None obviously dropped. |
| 13 | `/api/darkpool/recent` | `get_darkpool_recent` | (no live consumer — used as helper) | n/a | Imported but no caller found in current code. |
| 14 | `/api/darkpool/{ticker}` | `get_darkpool_ticker` | sectors `_get_dp_activity_for_ticker`, committee_bridge, scanners/wh_accumulation | `active, prints_30m, total_size, total_value` | Drops per-print price/size detail; surfaces top-5 in committee enrichment. |
| 15 | `/api/earnings/premarket` | `get_earnings_premarket` | jobs/chronos_ingest | Persisted to earnings table | Field subset depends on chronos schema. |
| 16 | `/api/earnings/afterhours` | `get_earnings_afterhours` | jobs/chronos_ingest | Persisted | Same as above. |
| 17 | `/api/earnings/{ticker}` | `get_earnings_dates`, `get_next_earnings_date` | (ticker_profile + chronos) | `next_earnings_date` only | Drops full earnings calendar history. |
| 18 | `/api/shorts/{ticker}/interest-float/v2` | `get_short_interest` | scanners/hydra_squeeze, data/short_interest | `short_interest_pct, days_to_cover, …` | Drops historical series, exchange breakdown. |
| 19 | `/api/news/headlines` | `get_news_headlines` | api/uw.py `/uw/news`, api/market_data `/market/news`, committee_bridge | `title, url, source, published, tickers, sentiment, is_major` | Drops author, full_text, image_url often. |
| 20 | `/api/insider/{ticker}` | `get_insider_transactions(ticker=…)` | api/insider.py `/insider/transactions` | Passthrough | Returns raw UW array. |
| 21 | `/api/insider/transactions` | `get_insider_transactions(ticker=None)` | api/insider.py `/insider/transactions` | Passthrough | Same. |
| 22 | `/api/congress/recent-trades` | `get_congressional_trades` | api/insider.py `/congress/recent-trades` | Passthrough | Same. |

### 2.2 Consumer map (which backend module touches which wrapper)

| Module | UW wrappers used |
|---|---|
| `backend/api/sectors.py` | `get_snapshot`, `get_bars` (yfinance), `get_darkpool_ticker`, `get_iv_rank` |
| `backend/api/market_data.py` | `get_snapshot`, `get_bars` (yfinance), `get_previous_close`, `get_options_snapshot`, `get_news_headlines`, `get_spread_value`, `get_single_option_value` |
| `backend/api/committee_bridge.py` | `get_market_tide`, `get_darkpool_ticker`, `get_max_pain`, `get_sector_etfs`, `get_iv_rank`, `get_news_headlines` |
| `backend/api/unified_positions.py` | `get_spread_value`, `get_single_option_value`, `get_multi_leg_value`, `get_ticker_greeks_summary` |
| `backend/api/insider.py` | `get_economic_calendar`, `get_insider_transactions`, `get_congressional_trades` |
| `backend/api/uw.py` | `get_news_headlines` (plus webhook-fed Redis caches: `uw:flow:*`, `uw:discovery`, `uw:ticker:*`, `uw:market_flow:latest`) |
| `backend/api/uw_integration.py` | none direct — accepts Pandora-Bridge webhooks (`market_tide`, `sectorflow`, `economic_calendar`, `highest_volume`, `flow_alerts`, generic) into in-memory cache |
| `backend/api/uw_health.py` | `get_health` |
| `backend/api/macro_strip.py` | `get_snapshot` × 16 tickers |
| `backend/api/ticker_profile.py` | `get_snapshot` (also reads `flow_events` + Redis RSI) |
| `backend/api/flow.py` | none direct — webhook + Redis-cache reads |
| `backend/bias_filters/gex.py` | `get_options_snapshot`, `get_greek_exposure` |
| `backend/bias_filters/iv_skew.py` | `get_options_snapshot` |
| `backend/scanners/wh_accumulation.py` | `get_flow_recent`, `get_greek_exposure`, `get_darkpool_ticker` |
| `backend/scanners/hydra_squeeze.py` | `get_short_interest` |
| `backend/scheduler/bias_scheduler.py` | `get_flow_recent` |
| `backend/jobs/uw_flow_poller.py` | `get_flow_per_expiry` |
| `backend/jobs/chronos_ingest.py` | `get_earnings_premarket`, `get_earnings_afterhours` |
| `backend/circuit_breakers/strc_monitor.py` | `get_previous_close` |
| `backend/data/short_interest.py` | `get_short_interest` |
| `backend/analysis/correlation_monitor.py`, `trip_wire_monitor.py` | `get_snapshot`, `get_bars` |
| `backend/services/read_only/quote.py` (hub_mcp) | `uw_api` direct — only `read_only` module that bypasses caches |

### 2.3 Notable derived-data wrappers (not raw UW endpoints)

| Wrapper | Composition | Used by |
|---|---|---|
| `get_spread_value`, `get_single_option_value`, `get_multi_leg_value` | Built on top of `get_options_snapshot` — picks contracts, computes mid + greeks | market_data, unified_positions (mark-to-market) |
| `get_ticker_greeks_summary` | Built on top of `get_options_snapshot` — aggregates net greeks across a list of legs | unified_positions `/positions/greeks` |
| `get_bars` | **yfinance**, not UW. Schema mimics Polygon. | sectors heatmap fallback, market_data `/market/bars`, scanners, analysis |

### 2.4 Routers exposing UW-backed routes

| Router | Prefix | Routes | UW-backed routes |
|---|---|---|---|
| `sectors.py` | `/sectors` | 3 | 3 (heatmap, leaders, seed-constituents) |
| `market_data.py` | (none) | 6 | 6 |
| `macro_strip.py` | `/macro` | 1 | 1 |
| `committee_bridge.py` | (none) | 4 | 1 (`/committee/enrichment/{ticker}` is the only UW-heavy one) |
| `uw.py` | `/uw` | 7 | 1 direct (`/uw/news`); rest read webhook-fed Redis caches |
| `uw_integration.py` | `/bias/uw` | 9 | 0 direct — all webhook-fed |
| `uw_health.py` | `/uw` | 1 | 1 |
| `ticker_profile.py` | (none) | 2 | 1 |
| `insider.py` | (none) | 3 | 3 |
| `unified_positions.py` | `/v2` | 14 | 2 (`/positions/greeks`, `/positions/mark-to-market`) |
| `flow.py` | `/flow` | 10 | 0 direct |

---

## 3. Endpoint gaps

177 total UW paths − 22 wrapped = **155 unwrapped**.

The four buckets:

- **OLYMPUS** = committee analytics value (positioning, flow microstructure, smart-money, vol surface, regime).
- **AGORA** = dashboard / heatmap / scanner UI value (display tiles, popup enrichment, ticker drilldown).
- **BOTH** = clear value for committee analysts **and** at least one Agora surface.
- **NEITHER** = out of scope (crypto/forex/commodities/predictions/private markets/sockets/deprecated v1).

### 3.1 OLYMPUS (56 paths)

| Path | What it gives the committee |
|---|---|
| `/api/stock/{ticker}/greek-exposure/expiry` | GEX by expiry — pin-risk, gamma cliff identification |
| `/api/stock/{ticker}/greek-exposure/strike` | GEX by strike — magnet levels |
| `/api/stock/{ticker}/greek-exposure/strike-expiry` | Combined — full GEX surface |
| `/api/stock/{ticker}/spot-exposures` | Live 1-min spot GEX |
| `/api/stock/{ticker}/spot-exposures/expiry-strike` | Spot GEX surface — PYTHAGORAS/DAEDALUS |
| `/api/stock/{ticker}/spot-exposures/strike` | Spot GEX by strike |
| `/api/stock/{ticker}/greek-flow` | Net delta/gamma flow |
| `/api/stock/{ticker}/greek-flow/{expiry}` | Greek flow per expiry |
| `/api/stock/{ticker}/atm-chains` | ATM chain — ATM IV / OI snapshot |
| `/api/stock/{ticker}/interpolated-iv` | Interpolated IV surface — DAEDALUS pricing |
| `/api/stock/{ticker}/nope` | Net Options Pricing Effect — directional pressure |
| `/api/stock/{ticker}/expiry-breakdown` | Option expiry concentration |
| `/api/stock/{ticker}/oi-change` | OI shift — position building/unwinding |
| `/api/stock/{ticker}/oi-per-expiry` | OI distribution by expiry |
| `/api/stock/{ticker}/oi-per-strike` | OI distribution by strike |
| `/api/stock/{ticker}/option/stock-price-levels` | Option-implied price levels |
| `/api/stock/{ticker}/flow-per-strike` | Strike-level flow heatmap |
| `/api/stock/{ticker}/flow-per-strike-intraday` | Same, intraday cadence |
| `/api/stock/{ticker}/historical-risk-reversal-skew` | Skew time-series — sentiment |
| `/api/stock/{ticker}/volatility/realized` | RV vs IV gap |
| `/api/stock/{ticker}/volatility/stats` | Vol stats |
| `/api/stock/{ticker}/volatility/term-structure` | Term structure — DAEDALUS |
| `/api/stock/{ticker}/net-prem-ticks` | Net call vs put premium ticks |
| `/api/stock/{ticker}/option/volume-oi-expiry` | Volume × OI by expiry |
| `/api/stock/{ticker}/options-volume` | Aggregate options volume |
| `/api/stock/{ticker}/stock-volume-price-levels` | Off/lit price levels |
| `/api/stock/{ticker}/ownership` | Institutional ownership tape |
| `/api/market/correlations` | Cross-ticker correlation matrix |
| `/api/market/oi-change` | Market-wide OI shift |
| `/api/market/{sector}/sector-tide` | Sector-level tide (per-sector market_tide) |
| `/api/market/{ticker}/etf-tide` | ETF-flavored tide for any ticker |
| `/api/market/total-options-volume` | Vol vs avg |
| `/api/market/top-net-impact` | Top net-premium impact tickers |
| `/api/market/insider-buy-sells` | Aggregate insider activity |
| `/api/group-flow/{flow_group}/greek-flow` | Flow groups (e.g. tech, mag7) |
| `/api/group-flow/{flow_group}/greek-flow/{expiry}` | Per-expiry within a group |
| `/api/net-flow/expiry` | Net flow segregated by expiry |
| `/api/option-trades/flow-alerts` | Live actionable flow alerts |
| `/api/option-trades/flow-alerts/{id}` | Drill a specific alert |
| `/api/option-trades/full-tape/{date}` | Full option tape (heavy) |
| `/api/option-contract/{id}/flow` | Per-contract flow |
| `/api/option-contract/{id}/historic` | Per-contract OHLCV |
| `/api/option-contract/{id}/intraday` | Per-contract intraday |
| `/api/option-contract/{id}/volume-profile` | Per-contract volume profile |
| `/api/screener/option-contracts` | Hottest chains screener |
| `/api/institution/{ticker}/ownership` | Holders of a ticker |
| `/api/institution/{name}/activity/v2` | Smart-money institutional activity |
| `/api/institution/{name}/holdings` | Institutional holdings |
| `/api/institution/{name}/sectors` | Institutional sector tilt |
| `/api/institutions` | Institutions index |
| `/api/congress/unusual-trades` | Politically unusual buys/sells |
| `/api/congress/unusual-trades/by-tickers` | Same, ticker-keyed |
| `/api/congress/unusual-trades/stats` | Aggregate stats |
| `/api/seasonality/market` | Market seasonal patterns |
| `/api/seasonality/{ticker}/monthly` | Per-ticker seasonality (avg) |
| `/api/seasonality/{ticker}/year-month` | Per-ticker year-month grid |
| `/api/short_screener` | Squeeze candidates |

### 3.2 AGORA (30 paths)

| Path | UI surface it would feed |
|---|---|
| `/api/companies/{ticker}/profile` | Ticker info card under heatmap popup row — Section 4 gap |
| `/api/companies/{ticker}/dividends` | Ticker drilldown |
| `/api/companies/{ticker}/splits` | Ticker drilldown |
| `/api/companies/{ticker}/earnings-estimates` | Ticker drilldown — forward EPS |
| `/api/companies/{ticker}/transcripts/{quarter}` | Earnings transcript pull |
| `/api/companies/listings` | Symbol universe / autocomplete |
| `/api/stock-directory/ticker-exchanges` | Symbol → exchange mapping |
| `/api/stock/{sector}/tickers` | **Replaces hardcoded `SECTOR_SEEDS`** in `sectors.py` |
| `/api/stock/{ticker}/technical-indicator/{function}` | RSI / MACD direct from UW → fixes heatmap-popup RSI gap |
| `/api/stock/{ticker}/earnings` | Earnings history card |
| `/api/stock/{ticker}/insider-buy-sells` | Insider activity tile |
| `/api/stock/{ticker}/balance-sheets` | Fundamentals drawer |
| `/api/stock/{ticker}/income-statements` | Fundamentals drawer |
| `/api/stock/{ticker}/cash-flows` | Fundamentals drawer |
| `/api/stock/{ticker}/financials` | Fundamentals overview |
| `/api/stock/{ticker}/fundamental-breakdown` | Fundamentals overview |
| `/api/etfs/{ticker}/holdings` | ETF drilldown |
| `/api/etfs/{ticker}/weights` | ETF drilldown |
| `/api/etfs/{ticker}/exposure` | ETF drilldown |
| `/api/etfs/{ticker}/in-outflow` | ETF flow tile |
| `/api/etfs/{ticker}/info` | ETF metadata |
| `/api/calendar/ipo` | Calendar tile |
| `/api/market/fda-calendar` | Calendar tile |
| `/api/market/movers` | Top-movers tile |
| `/api/screener/stocks` | Stock screener page |
| `/api/screener/analysts` | Analyst ratings |
| `/api/shorts/{ticker}/data` | Short data card |
| `/api/shorts/{ticker}/volume-and-ratio` | Short volume card |
| `/api/shorts/{ticker}/volumes-by-exchange` | Short by exchange |
| `/api/shorts/{ticker}/ftds` | Failures to deliver |

### 3.3 BOTH (27 paths)

| Path | Used by |
|---|---|
| `/api/stock/{ticker}/greeks` | Position MTM accuracy (Agora) + DAEDALUS pricing |
| `/api/stock/{ticker}/flow-alerts` | Agora ticker tile + committee enrichment |
| `/api/stock/{ticker}/option-chains` | Strategy builder UI + committee structure picking |
| `/api/companies/{ticker}/profile` *(also in AGORA)* | Heatmap popup ticker card + committee context |
| `/api/insider/{ticker}/ticker-flow` | Dashboard insider tile + committee bias-alignment cross-check |
| `/api/insider/{sector}/sector-flow` | Heatmap sector tile + URSA macro read |
| `/api/seasonality/{month}/performers` | Calendar tile + TORO seasonal context |
| `/api/lit-flow/recent` | Live tape + committee microstructure |
| `/api/lit-flow/{ticker}` | Ticker drilldown + committee enrichment |
| `/api/predictions/insiders` *(if ever surfaced)* | Sentiment tile + committee context |
| `/api/congress/politicians` | Filter UI + URSA-bias context |
| `/api/congress/late-reports` | Late-disclosure tile + bias context |
| `/api/congress/congress-trader` | Per-trader card + committee context |
| `/api/politician-portfolios/recent_trades` | Politician feed tile + bias context |
| `/api/politician-portfolios/holders/{ticker}` | Ticker drilldown + bias context |
| `/api/politician-portfolios/disclosures` | Annual disclosures feed |
| `/api/politician-portfolios/people` | Politician picker |
| `/api/politician-portfolios/{politician_id}` | Portfolio drill |
| `/api/alerts` | UW-side alert pipeline → committee notifications |
| `/api/alerts/configuration` | Manage UW alerts from Pandora |
| `/api/analytics/sliding` | Both: sliding-window analytics |
| `/api/analytics/window` | Both: fixed-window analytics |
| `/api/economy/{indicator}` | Macro tile + URSA context (note: FRED is primary today) |
| `/api/institutions/latest_filings` | 13F feed + URSA context |
| `/api/institution/{name}/activity` (v1 deprecated) | Skip — use v2 |
| `/api/institution/{name}/holdings` *(also in OLYMPUS)* | Smart-money drilldown — Agora + committee |
| `/api/institution/{ticker}/ownership` *(also in OLYMPUS)* | Holders-of-ticker — both |

### 3.4 NEITHER — out of scope (42 paths)

- `/api/crypto/*` (4 paths) — superseded by Binance/Coinalyze per `PROJECT_RULES.md` Data Source Hierarchy.
- `/api/digital-currencies/*` (2) — same.
- `/api/forex/*` (3) — not in current asset universe.
- `/api/commodities/{name}` (1) — not in current asset universe.
- `/api/private-markets/*` (9) — out of scope (Nick trades listed equities + crypto only).
- `/api/predictions/*` (9) — prediction-market product, separate use case.
- `/api/socket/*` (14) — WebSocket transport; separate build entirely, not REST-shaped. Note these are listed in the OpenAPI but are not REST endpoints.

---

## 4. Sector Heatmap diagnosis

### 4.1 What the popup promises

The Sector Heatmap popup (`frontend/app.js:5872-5887`) renders a constituent table with **11 columns**:

```
TICKER | PRICE | DAY% | REL% | WK% | MO% | RSI | VOL | Flow | IV | DP
```

It calls `GET /sectors/{etf}/leaders` for the data (`frontend/app.js:5936`).

### 4.2 What `/sectors/{etf}/leaders` actually returns

From `backend/api/sectors.py:645-749`, each constituent entry has:

| Column | Field | Source | Status |
|---|---|---|---|
| TICKER | `ticker` | Postgres `sector_constituents` | OK |
| PRICE | `price` | `_fetch_sector_snapshot` → `uw_api.get_snapshot` (UW `/stock-state`) | OK |
| DAY% | `day_change_pct` | `_fetch_sector_snapshot` (calculated price vs prev close) | OK |
| REL% | `sector_relative_pct` | calculated (`day_change_pct` − sector ETF `day_change_pct`) | OK |
| **WK%** | `week_change_pct` | **`None`, hardcoded at sectors.py:728** | **GAP** |
| **MO%** | `month_change_pct` | **`None`, hardcoded at sectors.py:729** | **GAP** |
| RSI | `rsi_14` | `_get_rsi_for_ticker` reads Redis keys `rsi:{ticker}` / `indicator:rsi:{ticker}` / `scanner:rsi:{ticker}` | **Silently `None` whenever the upstream scanner has not populated the key** |
| VOL | `volume_ratio` | calculated from snapshot `volume / avg_volume_20d` (Postgres) | OK |
| Flow | `flow_direction` + `flow_call_pct` + `flow_premium` | Postgres `flow_events` table, 24h sum from `_get_flow_metrics` | OK functionally, but is a derived 24h aggregate — not a live UW flow read |
| IV | `iv_rank` + `iv_tier` | `_get_iv_rank_for_ticker` → live UW `/iv-rank` | OK |
| DP | `dp_active` + `dp_prints_30m` | `_get_dp_activity_for_ticker` → live UW `/darkpool/{ticker}` | OK |

The popup renderer (`_renderSectorPopupTable` at `frontend/app.js:6022+`) handles `null` by showing `-`. The dashes in WK% / MO% / RSI are the visible symptom of the gap.

### 4.3 Why WK% and MO% are blank

`_fetch_sector_snapshot` only calls `uw_api.get_snapshot` — which is a single-point quote, not a bars endpoint. To compute week / month change, the route would need to call `get_bars` (or UW `/api/stock/{ticker}/ohlc/{candle_size}` directly) for the prior 30 sessions and pull the close from 5 sessions ago + 21 sessions ago. The leaders route never does this — fields are set literal `None` at sectors.py:728-729 with no comment explaining the omission.

The same `week_change_pct` / `month_change_pct` fields are also expected by the **ticker profile popup** at `frontend/app.js:6330-6331` (`_tpRow('Week', pa.week_change_pct, …)`), so the gap shows up in two places.

### 4.4 Why RSI is intermittently blank

`_get_rsi_for_ticker` reads Redis only (`sectors.py:509-520`). It never computes RSI directly and never calls UW. The upstream populator is a separate scanner job whose population pattern is partial — many constituent tickers will have no key. Direct fix: call `/api/stock/{ticker}/technical-indicator/RSI` from UW for any ticker the cache lacks, with a short Redis TTL. **This is one of the 30 unwrapped AGORA endpoints listed in Section 3.2.**

### 4.5 Why "Flow" is a 24h Postgres aggregate, not live UW

`_get_flow_metrics` queries `flow_events WHERE created_at > NOW() - INTERVAL '24 hours'`. `flow_events` is populated by `jobs/uw_flow_poller.py` which calls `get_flow_per_expiry`. So the column is **two hops removed** from UW: poller cadence × Postgres staleness. Live alternative: `/api/option-trades/flow-alerts` or `/api/stock/{ticker}/flow-alerts` (BOTH bucket in Section 3.3).

### 4.6 The "ticker info" sub-card

The popup as currently built has no sub-card / drawer beneath the row — it is a flat table. Nick's note in the brief asks about an "individual ticker info section." That UI element **does not exist in `app.js`**: there is no `tickerInfoPanel`, no expand-row handler, no detail-view click target inside `openSectorPopup`. The only ticker drill-down lives in a separate `closeTickerPopup`/ticker profile popup invoked elsewhere (line 5931 closes it when sector popup closes). If the desired UX is "click a row → ticker info opens below," that needs to be built — the data plumbing (company name, market cap, sector, description) would come from `/api/companies/{ticker}/profile` (currently unwrapped, AGORA bucket).

### 4.7 Heatmap itself (vs the popup)

The heatmap grid (`/sectors/heatmap` at `sectors.py:122`) is a separate route, uses `get_sector_etfs` (UW `/api/market/sector-etfs`) and is not in the same code path as the popup. The brief asks specifically about the popup; the grid is healthy as far as this audit can see.

---

## 5. Recommended build scope

**Approach.** Do the work in three small phases, each independently deployable. No single mega-PR. Every phase passes through the Titans review process before merge per `PROJECT_RULES.md`.

### Phase A — Heatmap popup completeness (AGORA)

Smallest, most user-visible. Closes the WK% / MO% / RSI gaps in the popup that Nick has been looking at.

- Add `get_technical_indicator(ticker, function)` to `uw_api.py` → `/api/stock/{ticker}/technical-indicator/{function}`.
- In `_fetch_sector_snapshot` (or a new helper) batch a 30-day OHLC pull per constituent and derive `week_change_pct` (5-session) + `month_change_pct` (21-session). Cache per ticker for 60s.
- In `_get_rsi_for_ticker`, fall back to UW `technical-indicator/RSI` when Redis cache miss; same 60s TTL.
- (Optional, Phase A.5) Add ticker-info sub-card under the popup row backed by `/api/companies/{ticker}/profile` + already-wrapped `get_snapshot`. Build the UI element + a thin `/ticker/{symbol}/info-card` endpoint, or extend the existing `/ticker/{symbol}/profile`.

### Phase B — Bars on UW, not yfinance (foundational)

Closes the last yfinance dependency in the hot path, honors the Data Source Hierarchy fully.

- Replace the yfinance body of `get_bars` with `/api/stock/{ticker}/ohlc/{candle_size}` (already used internally by `_get_regular_session_change`). Keep the same Polygon-shaped schema downstream so no callers change.
- Validate against existing consumers: sectors fallback, market_data, scanners, analysis modules.
- Remove the now-stale comment in `sectors.py:462` ("UW API wraps yfinance for real-time quotes").
- Keep yfinance imports only as the documented fallback for indices/breadth (`^VIX`, `^GSPC`, etc.) which UW does not cover.

### Phase C — Olympus committee tactical upgrades (OLYMPUS / BOTH)

Pull the highest-leverage analytical endpoints into the committee enrichment pipeline.

- Add wrappers for: `stock/{ticker}/greeks`, `stock/{ticker}/flow-alerts`, `stock/{ticker}/oi-change`, `stock/{ticker}/expiry-breakdown`, `stock/{ticker}/spot-exposures`, `stock/{ticker}/volatility/term-structure`, `market/{ticker}/etf-tide`, `market/{sector}/sector-tide`, `option-trades/flow-alerts`, `institution/{ticker}/ownership`, `companies/{ticker}/profile`, `companies/{ticker}/earnings-estimates`.
- Extend `/committee/enrichment/{ticker}` to surface these alongside the existing six enrichment blocks. Keep additions optional behind feature flags so the committee skills can opt in lane-by-lane.
- Surface the new tiles (etf-tide, sector-tide, oi-change, flow-alerts) on Agora where the same data benefits the dashboard view.

**Sequencing rationale.** Phase A is the visible fix Nick keeps seeing. Phase B is foundational hygiene that everything else benefits from. Phase C is the high-leverage committee build that should not start until Phase A + B are stable.

**Out of scope for this build.** Sockets, prediction markets, private markets, crypto/forex/commodities — see Section 3.4.

---

## 6. Open questions for Nick + Titans

1. **Popup UX direction.** Is the heatmap popup intended to grow a ticker-info sub-card beneath the row, or should the existing ticker-profile popup (already separate) be the destination of a row click? Either is fine — the first is more UX-fluid, the second is less work.
2. **Bars migration risk tolerance.** `get_bars` is touched by sectors heatmap fallback, scanners, correlation/trip-wire monitors. Swapping yfinance → UW changes data lineage. Comfortable with a single PR that flips it, or want a feature-flagged dual-read for a week first?
3. **`get_bars` cadence cost.** UW rate limit is 120 req/min. Backfilling WK% / MO% for ~140 constituent tickers across 11 sector ETFs is up to 140 bar pulls per popup open. Want to (a) pre-warm in a scheduled job, (b) compute lazily on popup open with a 5-min TTL, or (c) only compute on the row currently visible?
4. **Bias warning about UW flow.** `_get_flow_metrics` reads a 24h Postgres aggregate. If we switch the popup "Flow" column to live `/api/option-trades/flow-alerts`, the column meaning changes (live-tick sentiment vs cumulative-day sentiment). Worth keeping both, or replacing?
5. **OLYMPUS scope cap.** Section 3.1 lists 56 OLYMPUS-bucket endpoints. Phase C only proposes 12. Are there others you want pulled forward (e.g. `interpolated-iv`, `nope`, `historical-risk-reversal-skew`)?
6. **Cost / rate-limit envelope.** UW Basic plan is 120 req/min today. Phase C adds ~10 new helper calls per `committee/enrichment` pass. With 6-agent committee passes happening on demand + Agora dashboard live tiles, will we breach 120/min? Should the recommendation include a plan upgrade evaluation, or is the existing token-bucket + circuit-breaker sufficient?
7. **`market/oi-change` vs `stock/{ticker}/oi-change`.** Market-wide and per-ticker variants both have value. Do we wrap both, or start with per-ticker?
8. **Politician / congress endpoints.** Eight congress paths + five politician-portfolio paths sit in OLYMPUS/BOTH. URSA is bias-driven and benefits from these. AGORA could surface them as a tile. Build all 13, or only the two highest-signal (`congress/unusual-trades`, `politician-portfolios/holders/{ticker}`)?
9. **Sockets.** 14 WebSocket channels are listed in the OpenAPI but require a separate transport. Out of scope for this REST audit, but worth filing as a follow-up?
10. **Companies/{ticker}/profile redundancy.** This endpoint partially overlaps with `stock/{ticker}/info` which is already wrapped via `get_snapshot`. Want both, or prefer to extend `_get_info_cached_long` to surface the same fields?

---

**End of audit. No code changes were made.** All UW endpoint reads beyond the OpenAPI fetch are based on existing code paths in `c:/trading-hub/backend/` and the cached spec at `docs/audit-artifacts/2026-05-22/uw-openapi.yaml`. `UW_API_KEY` was not printed, logged, or committed.
