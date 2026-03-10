# Pivot — Current State Summary

**Last Updated:** February 19, 2026

This document is a snapshot of what's deployed, what's working, and what's in progress. For the full development roadmap, see `DEVELOPMENT_STATUS.md`.

---

## What's Live and Working

### Discord Bot (VPS — 188.245.250.2)
- ✅ Interactive chat in #pivot-chat — responds to market questions, evaluates trade ideas
- ✅ Screenshot analysis — Claude Vision parses UW dashboards and charts
- ✅ Whale Hunter alerts — TradingView webhook → LLM evaluation → Discord alert
- ✅ UW Premium Bot monitoring — watches flow alert channels, parses into signals
- ✅ Circuit Breaker — TradingView alerts override bias during extreme market events
- ✅ Scout early warning — 15-minute timeframe alerts with auto-expiration
- ✅ EOD daily brief — scheduled market summary with bias and factor analysis
- ✅ Trade journaling — log trades via Discord with confirmation flow
- ✅ DEFCON behavioral monitoring — confluence-based alerting system
- ✅ Playbook v2.1 integrated into system prompts
- ✅ Market data context injection (prices, VIX, bias state)

### Backend API (Railway — fabulous-essence)
- ✅ TradingView webhook receiver (`POST /webhook/tradingview`)
- ✅ Bias calculation endpoints (`GET /api/bias/*`)
- ✅ Analytics API — signals, strategy health, factor performance, price data, risk
- ✅ Signal logging pipeline — all signals stored with metadata
- ✅ Factor history snapshots — time-series storage for 20+ factors
- ✅ Health endpoint (`GET /health`) — postgres, redis, websocket status
- ✅ PostgreSQL — same project as backend, linked via `${{Postgres.*}}`

### Frontend
- ✅ Main dashboard — bias cards, signal display, TradingView chart embed
- ✅ Analytics UI (6 tabs) — Dashboard, Trade Journal, Signal Explorer, Factor Lab, Backtest, Risk
- ✅ PWA installable

---

## Infrastructure

| Component | Platform | Status | Cost |
|-----------|----------|--------|------|
| Backend API | Railway (fabulous-essence) | ✅ Online | Free tier ($5/mo credit) |
| PostgreSQL | Railway (same project) | ✅ Connected | Included |
| Discord Bot | Hetzner VPS (PIVOT-EU) | ✅ Running | ~€4/month |
| Data Collector | Hetzner VPS (same box) | ✅ Running | Included |
| Frontend | Served from VPS | ✅ Available | Included |
| **Total** | | | **~$5/month** |

---

## Factor Inventory (20+ factors)

**MACRO:** yield_curve, high_yield_oas, credit_spreads, excess_cape_yield, initial_claims, sahm_rule, ism_manufacturing, dollar_smile, savita_indicator

**TECHNICAL:** spy_200sma_distance, spy_9ema_distance (⚠️ corrupted by price feed), vix_term_structure, vix_regime, sector_rotation, copper_gold_ratio

**FLOW:** options_sentiment, put_call_ratio, unusual_whales

**BREADTH:** tick_breadth, market_breadth, spy_trend_intraday

**Pending:** dxy_trend (in Codex brief)

---

## Known Issues

- ⚠️ **SPY price feed**: yfinance may return split-unadjusted data (~$228 vs ~$686). Corrupts EMA/SMA factors. Fix in progress.
- ⚠️ **Stale factors**: options_sentiment, put_call_ratio, savita_indicator have reliability issues.
- ⚠️ **Analytics tables mostly empty**: Needs signal accumulation time and trade imports.
- ⚠️ **No historical trade data**: Robinhood import system designed but not built yet.

---

## Development Phase

| Phase | Description | Status |
|-------|-------------|--------|
| 2A | Playbook → prompts.py | ✅ Complete |
| 2B | Trade Journal (SQLite + Postgres) | ✅ Complete |
| 2C | DEFCON behavioral layer | ✅ Complete |
| 2D | On-demand market data tools | ✅ Complete |
| 2E | Interactive Discord chat | ✅ Complete |
| 2F | UW dashboard API scraping | 📋 Not started |
| 2G | Auto-scout (flow screening → picks) | 📋 Not started |
| Analytics 1 | Data collection schema | ✅ Complete |
| Analytics 2 | API endpoints | ✅ Complete |
| Analytics 3 | 6-tab UI | ✅ Complete |
| Codex briefs | 8 analytical upgrades | 🔨 Deployed to Codex |

See `DEVELOPMENT_STATUS.md` for full details on each phase.
