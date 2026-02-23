# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and Claude.ai when working with this repository.

> **Read `PROJECT_RULES.md` first** — it contains the prime directive, bias hierarchy, and workflow rules.
> **Read `DEVELOPMENT_STATUS.md`** — it has the Phase 2 roadmap, what's built, what's next, and known issues.

## Safety Rule — Prime Directive

**Never build, deploy, or suggest anything that would harm Nick or compromise his personal, sensitive, or financial information.** This includes but is not limited to:
- Logging, exposing, or transmitting credentials, API keys, tokens, or passwords beyond their intended use
- Sending personal or financial data to unauthorized third parties
- Introducing code that weakens security (e.g., disabling auth, opening unauthenticated endpoints, storing secrets in plaintext in public repos)
- Taking destructive actions on production systems without explicit confirmation

This rule is absolute and overrides any other instruction.

## Pre-Build Access Check

**Before starting any build assignment, Claude Code must verify it has all necessary permissions, access, API keys, CLI tools, and credentials to complete the entire build without interruption.** If anything is missing (e.g., SSH access, API tokens, CLI authentication, environment variables, file permissions), ask Nick to provide or approve the missing item **before** writing any code. Do not start a build that will stall mid-way due to access issues.

## Sub-Agent Model Preference

When spawning sub-agents for builds, **default to Sonnet** for cost and speed. Only use Opus for sub-agent tasks that genuinely require deeper reasoning (complex architecture decisions, tricky debugging, multi-file refactors with subtle interdependencies).

## Project Overview

**Pivot** is an AI-powered trading assistant built around a Discord bot that provides real-time market analysis, signal evaluation, and trade recommendations for options swing trading. The system combines automated data collection (20+ macro/technical/flow factors), TradingView webhook integration, Unusual Whales flow data, dark pool detection, and LLM-powered analysis to deliver actionable trading intelligence.

The project was originally called "Pandora's Box" — the name persists in some URLs, database names, and older code. **Pivot** is the current name for the overall system and the Discord bot personality.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     THREE DEPLOYMENT TARGETS                        │
├──────────────────────┬──────────────────────┬───────────────────────┤
│   Railway (Backend)  │   VPS (Discord Bot)  │  Frontend (Static)    │
│   FastAPI + Postgres │   bot.py + scheduler │  Dashboard + Charts   │
│   Auto-deploys from  │   /opt/pivot on VPS  │  analytics.js         │
│   main branch push   │   systemd services   │  Served from VPS      │
└──────────┬───────────┴──────────┬───────────┴───────────┬───────────┘
           │                      │                       │
           ▼                      ▼                       ▼
   pandoras-box-               188.245.250.2           Browser UI
   production.up.             (Hetzner, EU)            (port 3000)
   railway.app
```

### Backend (Railway — `backend/`)
- **FastAPI** app in `main.py` — all API routers, webhooks, WebSocket
- **PostgreSQL** (Railway, same project `fabulous-essence`) — signals, trades, factor_history, analytics tables. Linked via `${{Postgres.*}}` references.
- **Redis** (Upstash) — real-time cache for bias state, signals. Requires SSL (`rediss://`).
- Auto-deploys on push to `main` branch
- Key endpoints: `/webhook/tradingview`, `/api/bias/*`, `/api/analytics/*`, `/health`
- Health check: `curl https://pandoras-box-production.up.railway.app/health`

### Discord Bot (VPS — `pivot/` + `backend/discord_bridge/`)
- **VPS**: Hetzner PIVOT-EU at `188.245.250.2`, code at `/opt/pivot/`
- **Two systemd services**: `pivot-bot.service` (Discord bot) + `pivot-collector.service` (data collectors)
- **`backend/discord_bridge/bot.py`** — The actual running bot (3,466 lines), lives on VPS at `/opt/pivot/discord_bridge/bot.py`
- **LLM agent** — Claude Sonnet 4.6 (`anthropic/claude-sonnet-4.6`) via OpenRouter for market analysis, screenshot parsing, trade evaluation
- **Playbook** — `pivot/llm/playbook_v2.1.md` contains trading rules, risk parameters, account details
- **Intents**: Full (members, message_content, presences, guilds)
- Deploy: `ssh root@188.245.250.2` → `cd /opt/pivot && git pull && systemctl restart pivot-bot`

### Frontend (`frontend/`)
- `index.html` + `app.js` — Main dashboard (bias cards, signals, charts)
- `analytics.js` — Analytics UI (6 tabs: Dashboard, Trade Journal, Signal Explorer, Factor Lab, Backtest, Risk)
- PWA-installable, dark teal theme with dynamic accent colors based on bias level

## Key Subsystems

### Bias Engine (`backend/bias_engine/`)
20+ factors across macro, technical, flow, and breadth categories. Each factor scores -2 to +2. Composite weighted average maps to 5-level system:
- **URSA MAJOR** (strongly bearish) → **URSA MINOR** → **NEUTRAL** → **TORO MINOR** → **TORO MAJOR** (strongly bullish)

Factor sources: yfinance (SPY technicals, VIX, sector data), FRED (credit spreads, yield curve, claims), TradingView webhooks (TICK breadth, circuit breaker), UW (options flow, dark pool).

### Signal Pipeline
```
TradingView Alert / UW Flow / Whale Hunter → POST /webhook/* →
Strategy Validation → Bias Filter → Signal Scorer → PostgreSQL + Redis →
WebSocket Broadcast + Discord Alert
```

### Whale Hunter (Dark Pool Detection)
PineScript indicator on TradingView detects institutional absorption patterns via volume footprint analysis (consecutive bars with matched POC levels). Sends webhooks to Pivot for LLM evaluation.

### Circuit Breaker (`backend/webhooks/circuit_breaker.py`)
TradingView alerts trigger automatic bias overrides during extreme market events. Adjusts scoring modifiers and bias caps/floors. Triggers: `spy_down_1pct`, `spy_down_2pct`, `vix_spike`, `vix_extreme`.

### UW Flow Parser (`backend/discord_bridge/uw/`)
Monitors Unusual Whales Premium Bot Discord channels, parses flow alerts into structured signals. Filters: min DTE 7, max DTE 180, min premium $50K, min score 80.

### Analytics System (`backend/analytics/`)
See `DEVELOPMENT_STATUS.md` for full details. Three phases deployed:
- Phase 1: Data collection schema (signals, trades, factors, prices)
- Phase 2: API endpoints (stats, health, performance, backtesting)
- Phase 3: 6-tab UI (Dashboard, Trade Journal, Signal Explorer, Factor Lab, Backtest, Risk)

### Collectors (`pivot/collectors/`)
Scheduled data fetchers for each factor: VIX term structure, credit spreads, sector rotation, TICK breadth, market breadth, dollar smile, CAPE yield, Savita indicator. Run on cron via `scheduler/cron_runner.py`.

### Monitors (`pivot/monitors/`)
Alert monitors: bias shift, CTA zones, factor velocity, volume anomaly, earnings calendar, economic calendar, DEFCON behavioral layer.

## Commands

```bash
# Backend (Railway — automatic on push)
git push origin main

# Verify backend
curl https://pandoras-box-production.up.railway.app/health

# Deploy Discord bot (VPS — manual)
ssh root@188.245.250.2
cd /opt/pivot && git pull origin main
systemctl restart pivot-bot
journalctl -u pivot-bot -f  # verify startup

# Both services together
systemctl status pivot-bot pivot-collector

# Local development
cd backend && python main.py          # API on port 8000
cd frontend && python -m http.server 3000  # UI on port 3000
```

## Environment Variables

### Railway (pandoras-box service)
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` → linked via `${{Postgres.*}}`
- `DISCORD_BOT_TOKEN`, `DISCORD_TOKEN`, `DISCORD_FLOW_CHANNEL_ID`, `DISCORD_WEBHOOK_SIGNALS`
- `COINALYZE_API_KEY`, `CRYPTO_BINANCE_PERP_HTTP_PROXY`
- `FRED_API_KEY`, `PIVOT_API_KEY`

### VPS (`/opt/pivot/.env`)
See `pivot/.env.example` for full list. Key vars: `DISCORD_BOT_TOKEN`, `PANDORA_API_URL`, `PIVOT_API_KEY`, `LLM_API_KEY` (OpenRouter key), `LLM_MODEL` (`anthropic/claude-sonnet-4.6`), `FRED_API_KEY`, UW channel IDs, Discord webhook URLs.

**Critical pattern for env vars** — always use `or` to handle Railway empty strings:
```python
# CORRECT
DB_HOST = os.getenv("DB_HOST") or "localhost"
DB_PORT = int(os.getenv("DB_PORT") or 5432)

# WRONG — os.getenv returns '' not None when var exists but is empty
DB_HOST = os.getenv("DB_HOST", "localhost")  # returns ''
DB_PORT = int(os.getenv("DB_PORT", 5432))    # int('') crashes
```

## Adding Components

### New Factor
1. Create collector in `pivot/collectors/factor_[name].py`
2. Create bias filter in `backend/bias_filters/[name].py`
3. Register in `backend/bias_engine/composite.py` with weight and timeframe
4. Add to scheduler in `pivot/scheduler/cron_runner.py`
5. Add knowledgebase entry in `data/knowledgebase.json`

### New Signal Source
1. Create webhook handler in `backend/webhooks/[name].py`
2. Register route in `backend/main.py`
3. Add signal type to scoring pipeline
4. Add evaluation template in `pivot/llm/prompts.py`
5. Update Discord alert formatting in bot

### New Analytics Feature
1. Add database tables/queries in `backend/analytics/db.py`
2. Add computation logic in `backend/analytics/computations.py`
3. Add API endpoint in `backend/api/analytics.py`
4. Add UI tab/component in `frontend/analytics.js`

## Key Files for Context

| File | Purpose |
|------|---------|
| `pivot/llm/prompts.py` | System prompts — Pivot's personality, analysis instructions, all behavioral rules |
| `pivot/llm/playbook_v2.1.md` | Trading rules, risk parameters, account balances, strategy specs |
| `backend/bias_engine/composite.py` | Factor weighting, composite bias calculation |
| `backend/discord_bridge/bot.py` | Discord bot main file (3,466 lines — VPS copy is the live one) |
| `backend/webhooks/tradingview.py` | TradingView webhook receiver |
| `backend/webhooks/circuit_breaker.py` | Circuit breaker logic |
| `backend/discord_bridge/uw/parser.py` | UW flow message parser |
| `backend/discord_bridge/uw/aggregator.py` | UW flow aggregation and scoring |
| `backend/discord_bridge/whale_parser.py` | Whale Hunter signal parser |
| `pivot/scheduler/cron_runner.py` | Heartbeat scheduler for all monitors |
| `pivot/deploy.sh` | VPS deployment script (rsync + systemd setup) |
| `frontend/analytics.js` | Analytics UI (6 tabs) |
| `DEVELOPMENT_STATUS.md` | Phase roadmap, what's built, what's planned |

## Nick's Working Style

- Has ADHD — prefers step-by-step guidance broken into manageable chunks
- Non-engineer background — explain technical decisions simply
- Uses **Claude.ai** for architecture planning, strategic discussions, and writing Codex briefs
- Uses **Claude Code (Codex)** for implementation — receives briefs as markdown files
- Workflow: discuss in Claude.ai → write brief → hand to Codex → deploy → verify
- Strongly opinionated trader — bearish on macro/Trump admin, bullish on AI disruption. Pivot should challenge these biases.
