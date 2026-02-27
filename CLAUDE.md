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

**Pivot** is an AI-powered trading assistant built around a Discord bot that provides real-time market analysis, signal evaluation, and trade recommendations for options swing trading. The system combines automated data collection (22 macro/technical/flow factors), TradingView webhook integration, Unusual Whales flow data, dark pool detection, Polygon.io market data, and LLM-powered analysis to deliver actionable trading intelligence.

The project was originally called "Pandora's Box" — the name persists in some URLs, database names, and older code. **Pivot** is the current name for the overall system and the Discord bot personality.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     THREE DEPLOYMENT TARGETS                        │
├──────────────────────┬──────────────────────┬───────────────────────┤
│   Railway (Backend)  │   VPS (Pivot II)     │  Frontend (Static)    │
│   FastAPI + Postgres │   OpenClaw + crons   │  Dashboard + Charts   │
│   Auto-deploys from  │   /opt/openclaw on   │  analytics.js         │
│   main branch push   │   VPS (systemd)      │  Served from VPS      │
└──────────┬───────────┴──────────┬───────────┴───────────┬───────────┘
           │                      │                       │
           ▼                      ▼                       ▼
   pandoras-box-               188.245.250.2           Browser UI
   production.up.             (Hetzner, EU)            (port 3000)
   railway.app
```

### Backend (Railway — `backend/`)
- **FastAPI** app in `main.py` — all API routers, webhooks, WebSocket
- **PostgreSQL** (Railway, same project `fabulous-essence`) — signals, trades, factor_history, unified_positions, closed_positions, analytics tables. Linked via `${{Postgres.*}}` references.
- **Redis** (Upstash) — real-time cache for bias state, factor scores, signals. Requires SSL (`rediss://`). Per-factor TTLs (24h default, up to 1080h for Savita).
- Auto-deploys on push to `main` branch
- Key endpoints: `/webhook/tradingview`, `/webhook/breadth`, `/webhook/circuit-breaker/*`, `/api/bias/*`, `/api/analytics/*`, `/v2/positions/*`, `/health`
- Health check: `curl https://pandoras-box-production.up.railway.app/health`

### Pivot II (VPS — OpenClaw)
- **VPS**: Hetzner PIVOT-EU at `188.245.250.2`, code at `/opt/openclaw/workspace/`
- **Three systemd services**: `openclaw` (Pivot chat/briefs/pollers), `pivot-collector` (data collectors), `pivot2-interactions` (committee button handler)
- **LLM provider**: Direct Anthropic API (NOT OpenRouter). Haiku 4.5 (`claude-haiku-4-5-20251001`) for chat and analysis, Sonnet 4.6 for briefs and committee synthesis. Env var: `ANTHROPIC_API_KEY`.
- **OpenClaw config**: `/home/openclaw/.openclaw/openclaw.json`
- **Cron jobs**: `/home/openclaw/.openclaw/cron/jobs.json` — trade poller (*/15), twitter sentiment (*/30), morning/EOD briefs, prep pings, outcome matcher, weekly review, session cleanup
- Deploy: SSH → edit files at `/opt/openclaw/workspace/scripts/` → restart relevant service

### Frontend (`frontend/`)
- `index.html` + `app.js` — Main dashboard (bias cards with timeframe sub-scores, signals, circuit breaker banner, position summary widget, portfolio greeks)
- `analytics.js` — Analytics UI (6 tabs: Dashboard, Trade Journal, Signal Explorer, Factor Lab, Backtest, Risk)
- Position modals: add/edit/close/dismiss with structure support (debit_spread, credit_spread, iron_butterfly, straddle, strangle, custom)
- PWA-installable, dark teal theme with dynamic accent colors based on bias level
- **Cache busting**: CSS uses `?v=39`, app.js uses `?v=54`. Increment on UI changes.

## Key Subsystems

### Bias Engine (`backend/bias_engine/`)
22 factors across INTRADAY (5), SWING (9), and MACRO (8) categories. Each factor scores -1.0 to +1.0. Composite weighted average maps to 5-level system:
- **URSA MAJOR** (strongly bearish, ≤ -0.60) → **URSA MINOR** → **NEUTRAL** → **TORO MINOR** → **TORO MAJOR** (strongly bullish)

Weights sum to exactly 1.00 (enforced by assertion at import time): intraday 0.28, swing 0.41, macro 0.31.

**Data sources:** Polygon.io Options Starter ($29/mo — chains, greeks, OI, volume), Polygon.io Stocks Starter ($29/mo — ETF/equity prices), yfinance (VIX, indices, fallback), FRED (credit spreads, yield curve, claims, ISM/MANEMP), TradingView webhooks (TICK breadth, $UVOL/$DVOL breadth_intraday, circuit breaker), Twitter sentiment (30+ accounts via `pivot2_twitter.py`).

**Important patterns:**
- Factors return `None` (not `0.0`) when data is unavailable — prevents neutral dilution
- Redis keys are deleted when `compute_score()` returns None — prevents ghost 0.0 readings
- Per-factor Redis TTLs (ISM: 720h, Savita: 1080h, most others: 24h)
- Polygon uses NTM-filtered queries (±10% SPY price) to fetch 5-10 contracts instead of 2,500+
- VIX is used as SPY 30-day IV proxy (Polygon Starter plan doesn't populate `implied_volatility`)

### Circuit Breaker (`backend/webhooks/circuit_breaker.py`)
TradingView alerts trigger automatic bias overrides during extreme events. **Condition-verified decay** (NOT pure time-based) — both timer AND market condition must clear. State machine: active → pending_reset → Nick accepts/rejects via dashboard → inactive. No-downgrade guard (spy_down_1pct can't overwrite spy_down_2pct). Discord webhook notifications via `DISCORD_WEBHOOK_CB`. Integrated into `compute_composite()` as scoring modifier + bias cap/floor.

Triggers: `spy_down_1pct`, `spy_down_2pct`, `spy_up_2pct`, `vix_spike`, `vix_extreme`.

### Position Ledger (`backend/api/v2_positions.py` + `backend/positions/`)
Unified position tracking across all accounts (RH, IBKR, 401k). Options-aware with structure detection. Mark-to-market via Polygon options API (actual bid/ask mid-prices for both spread legs) with yfinance fallback for equities. Portfolio greeks endpoint. Committee context integration.

**v2 API (10 endpoints):** POST create, GET list (filtered), GET single, PUT update, POST close, DELETE soft-delete, POST sync (partial flag), GET summary, GET greeks, POST bulk-import.

**Important:** FastAPI matches routes in declaration order. `/v2/positions/summary` and `/v2/positions/greeks` must be declared BEFORE `/{position_id}` to prevent capture.

### Signal Pipeline
```
TradingView Alert / UW Flow / Whale Hunter → POST /webhook/* →
Strategy Validation → Bias Filter → Signal Scorer → PostgreSQL + Redis →
WebSocket Broadcast + Discord Alert
```

### Trading Team (Committee)
Multi-analyst AI committee evaluating signals. Pipeline: Gatekeeper → Context Builder → 4 parallel agents (TORO bull / URSA bear / Risk assessor / Pivot synthesizer) → Discord embed with Take/Pass/Watching buttons → Decision logging → Nightly outcome matching → Saturday weekly review.

Runs on VPS at `/opt/openclaw/workspace/scripts/`. Uses Anthropic API directly (Haiku for TORO/URSA/Risk, Sonnet for Pivot). ~$0.02/committee run.

See `docs/TRADING_TEAM_LOG.md` for build status and `TRADING_TEAM_STATUS.md` (project file) for architecture.

### Whale Hunter (Dark Pool Detection)
PineScript indicator on TradingView detects institutional absorption patterns via volume footprint analysis. Sends webhooks to Railway → evaluated by committee → posted to Discord.

### UW Flow Parser (`backend/discord_bridge/uw/`)
Monitors Unusual Whales Premium Bot Discord channels, parses flow alerts into structured signals. Filters: min DTE 7, max DTE 180, min premium $50K, min score 80.

### Collectors (`pivot/collectors/`)
Scheduled data fetchers: VIX term structure, credit spreads, sector rotation, TICK breadth, market breadth, CAPE yield, Savita indicator. Run on cron via `scheduler/cron_runner.py`.

### Monitors (`pivot/monitors/`)
Alert monitors: bias shift, CTA zones, factor velocity, volume anomaly, earnings calendar, economic calendar, DEFCON behavioral layer.

## Commands

```bash
# Backend (Railway — automatic on push)
git push origin main

# Verify backend
curl https://pandoras-box-production.up.railway.app/health

# Deploy Pivot II scripts (VPS — manual)
ssh root@188.245.250.2
# edit files at /opt/openclaw/workspace/scripts/
systemctl restart openclaw              # chat, briefs, pollers
systemctl restart pivot2-interactions   # committee button handler
systemctl restart pivot-collector       # data collectors
journalctl -u openclaw -f               # verify startup

# Check all services
systemctl status openclaw pivot-collector pivot2-interactions

# Local development
cd backend && python main.py          # API on port 8000
cd frontend && python -m http.server 3000  # UI on port 3000
```

## Environment Variables

### Railway (pandoras-box service)
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` → linked via `${{Postgres.*}}`
- `DISCORD_BOT_TOKEN`, `DISCORD_TOKEN`, `DISCORD_FLOW_CHANNEL_ID`, `DISCORD_WEBHOOK_SIGNALS`, `DISCORD_WEBHOOK_CB`
- `COINALYZE_API_KEY`, `CRYPTO_BINANCE_PERP_HTTP_PROXY`
- `FRED_API_KEY`, `PIVOT_API_KEY`
- `POLYGON_API_KEY` — Polygon.io API key (Options + Stocks Starter plans)

### VPS (OpenClaw env)
Set in `/home/openclaw/.openclaw/openclaw.json` under `env`. Key vars:
- `ANTHROPIC_API_KEY` — Direct Anthropic API (NOT OpenRouter)
- `DISCORD_BOT_TOKEN`, `PANDORA_API_URL`, `PIVOT_API_KEY`
- `FRED_API_KEY`
- UW channel IDs, Discord webhook URLs

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
1. Create factor file in `backend/bias_engine/factors/factor_[name].py` with `compute_score() → float | None`
2. Register in `backend/bias_engine/composite.py` with weight and timeframe category
3. **Weight sum must remain 1.00** — adjust existing weights to accommodate. Assertion will fail on import if sum ≠ 1.00.
4. Factor returns `None` when data unavailable (NOT 0.0)
5. Add collector/cron if factor needs periodic data refresh
6. Add to frontend factor display if user-visible

### New Signal Source
1. Create webhook handler in `backend/webhooks/[name].py`
2. Register route in `backend/main.py`
3. Add signal type to scoring pipeline
4. Wire into Trading Team committee (ask Nick if this signal type should go through committee review)
5. Update Discord alert formatting

### New v2 Position Endpoint
1. Add to `backend/api/v2_positions.py`
2. **Route ordering matters** — fixed paths (`/summary`, `/greeks`) BEFORE parameterized (`/{position_id}`)
3. Add models to `backend/positions/models.py` if new request/response shapes needed
4. Update committee context in `committee_context.py` if position data affects agent analysis

### New Analytics Feature
1. Add database tables/queries in `backend/analytics/db.py`
2. Add computation logic in `backend/analytics/computations.py`
3. Add API endpoint in `backend/api/analytics.py`
4. Add UI tab/component in `frontend/analytics.js`

## Key Files for Context

| File | Purpose |
|------|---------|
| `backend/bias_engine/composite.py` | Factor registration, weights (must sum to 1.00), composite bias calculation |
| `backend/bias_engine/factor_scorer.py` | Score computation, Redis caching, None handling, stale key cleanup |
| `backend/bias_engine/polygon_options.py` | Polygon.io options client (chains, greeks, spread valuation, NTM filtering) |
| `backend/webhooks/circuit_breaker.py` | Circuit breaker logic (condition-verified decay, state machine, no-downgrade) |
| `backend/webhooks/tradingview.py` | TradingView webhook receiver + /webhook/breadth endpoint |
| `backend/api/v2_positions.py` | Unified position ledger API (10 endpoints, route ordering matters) |
| `backend/positions/risk_calculator.py` | Options structure risk calculation (max loss, breakeven) |
| `frontend/app.js` | Main dashboard JS (bias cards, signals, positions, circuit breaker banner) |
| `frontend/analytics.js` | Analytics UI (6 tabs) |
| `DEVELOPMENT_STATUS.md` | Phase roadmap, what's built, what's planned |
| `docs/TRADING_TEAM_LOG.md` | Trading Team build status log |

### VPS / Trading Team Files

| File | Purpose |
|------|---------|
| `scripts/pivot2_committee.py` | Committee orchestrator + gatekeeper |
| `scripts/committee_context.py` | Market data enrichment + bias challenge + lessons + Twitter injection |
| `scripts/committee_prompts.py` | 4 agent system prompts (dpg/GEX trained — convexity-first, debit default) |
| `scripts/committee_parsers.py` | `call_agent()` + response parsers (Anthropic API direct, NOT OpenRouter) |
| `scripts/committee_decisions.py` | Decision logging, disk-backed pending store, button components |
| `scripts/committee_interaction_handler.py` | Persistent Discord bot for button clicks, modal, reminders |
| `scripts/committee_outcomes.py` | Nightly outcome matcher + Railway API fetcher |
| `scripts/committee_analytics.py` | Pattern analytics computation |
| `scripts/committee_review.py` | Weekly self-review LLM + Discord posting + lessons bank |
| `scripts/committee_autopsy.py` | Post-trade narrative generation (Haiku) |
| `scripts/pivot2_brief.py` | Morning/EOD brief generation (Sonnet, Anthropic API direct) |
| `scripts/pivot2_twitter.py` | Twitter sentiment collection (30+ accounts, Haiku scoring) |

## Nick's Working Style

- Has ADHD — prefers step-by-step guidance broken into manageable chunks
- Non-engineer background — explain technical decisions simply
- Uses **Claude.ai** for architecture planning, strategic discussions, and writing briefs
- Uses **Claude Code** for implementation — receives briefs as markdown files
- Workflow: discuss in Claude.ai → write brief → hand to Claude Code → deploy → verify
- Strongly opinionated trader — bearish on macro/Trump admin, bullish on AI disruption. Pivot should challenge these biases.
- **Local repo: `C:\trading-hub`** — the ONLY local clone. Never create a second clone.
- **Timezone: America/Denver** (Colorado, observes DST)
