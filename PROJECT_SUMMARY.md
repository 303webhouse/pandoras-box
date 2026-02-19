# Pandora's Box — Project Summary

**Last Updated:** 2026-02-19

## What This Is

A **real-time trading signal system** with two main components:

1. **Backend API** (Railway) — Processes TradingView alerts through automated strategies and bias filters, stores signals in PostgreSQL, broadcasts via WebSocket.
2. **Discord Bot "Pivot"** (VPS) — AI-powered trading assistant that provides market analysis, monitors unusual flow, and delivers trade recommendations in Discord.

---

## Current Deployment

| Component | Platform | Status |
|-----------|----------|--------|
| Backend API | Railway (fabulous-essence project) | ✅ Online |
| PostgreSQL | Railway (same project) | ✅ Connected |
| Discord Bot | Hetzner VPS (PIVOT-EU) | ✅ Running |
| Frontend PWA | Served via backend | PWA-installable |

**Backend URL**: `pandoras-box-production.up.railway.app`
**Health endpoint**: `GET /health` → returns postgres, redis, websocket status
**VPS**: `188.245.250.2` — bot runs as `pivot-bot.service` via systemd

### How Deploys Work
- **Backend**: Push to GitHub `main` → Railway auto-deploys in ~2 minutes
- **Discord Bot**: SSH to VPS → `git pull` → `systemctl restart pivot-bot`
- **Both services** run from the same repo (`303webhouse/pandoras-box`)

---

## Core Architecture

### Signal Flow
```
TradingView Alert → POST /webhook/tradingview → Strategy Validator →
Bias Filter → Signal Scorer → Redis + PostgreSQL → WebSocket Broadcast → All Devices + Discord
```

### Backend (`backend/`)
Python FastAPI application handling:
- TradingView webhook reception and validation
- Strategy validation (Triple Line, Exhaustion, Ursa Taurus)
- Bias filtering (TICK Breadth, Macro Confluence, BTC Bottom Signals, Dollar Smile)
- Signal scoring and classification (APIS CALL, KODIAK CALL, BULLISH TRADE, BEAR CALL)
- Dual database: Redis (real-time cache, <2ms) + PostgreSQL (permanent logging)
- WebSocket broadcasting to all connected clients
- REST API for positions, scanner, bias data, BTC signals, options flow
- Circuit Breaker system for major market events

### Discord Bot — Pivot (`pivot/`)
AI trading assistant running on discord.py with:
- Gemini LLM integration for interactive market analysis chat
- Market data collectors and condition monitors
- Unusual Whales flow bridge
- Scheduled tasks aligned to market hours
- Full Discord intents (members, message_content, presences)

### Frontend (`frontend/`)
PWA dashboard with dark teal UI:
- Real-time signal display via WebSocket
- 5-level bias system (Ursa Major → Toro Major)
- Position management (select/dismiss signals)
- Knowledgebase viewer for strategy documentation
- Mobile-installable (iOS/Android/desktop)

---

## File Structure

```
pandoras-box/
├── CLAUDE.md              ← AI coding assistant context
├── CODEX.md               ← OpenAI Codex context
├── PROJECT_RULES.md       ← Development rules and trading system specs
├── PROJECT_SUMMARY.md     ← This file
├── Procfile               ← Railway process definitions
├── requirements.txt       ← Python dependencies (backend)
├── runtime.txt            ← Python version for Railway
├── run_discord_bot.py     ← Discord bot entry point
├── start.bat              ← Windows local dev launcher
│
├── backend/               ← FastAPI application
│   ├── main.py            ← Entry point
│   ├── webhooks/          ← TradingView receivers, circuit breaker
│   ├── strategies/        ← Signal validators
│   ├── bias_filters/      ← Macro alignment filters
│   ├── scoring/           ← Signal classification
│   ├── database/          ← Redis + PostgreSQL clients
│   ├── websocket/         ← Multi-device broadcaster
│   ├── api/               ← REST routers
│   ├── scanners/          ← Market scanners
│   ├── alerts/            ← Black swan detection
│   └── discord_bridge/    ← Unusual Whales bridge
│
├── pivot/                 ← Discord bot
│   ├── bot.py             ← Bot entry point
│   ├── llm/               ← LLM integration (Gemini)
│   ├── collectors/        ← Market data collectors
│   ├── monitors/          ← Market condition monitors
│   ├── notifications/     ← Discord notification handlers
│   └── scheduler/         ← Scheduled market tasks
│
├── frontend/              ← PWA dashboard
│   ├── index.html         ← Dashboard
│   ├── styles.css         ← Dark teal styling
│   ├── app.js             ← WebSocket client
│   └── manifest.json      ← PWA config
│
├── config/                ← Environment templates
├── data/                  ← Knowledgebase JSON, runtime data
├── docs/                  ← Strategy and architecture docs
└── migrations/            ← Database migrations
```

---

## Environment Variables

Railway (pandoras-box service):
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — linked to Postgres via `${{Postgres.*}}`
- `DISCORD_BOT_TOKEN`, `DISCORD_TOKEN`, `DISCORD_FLOW_CHANNEL_ID`, `DISCORD_WEBHOOK_SIGNALS`
- `COINALYZE_API_KEY`, `CRYPTO_BINANCE_PERP_HTTP_PROXY`
- `FRED_API_KEY`, `GEMINI_API_KEY`, `PIVOT_API_KEY`

VPS (`/opt/pandoras-box/.env`):
- Discord bot token and API keys configured locally

---

## Trading System

### Bias Hierarchy (5 Levels)
| Level | Name | Meaning |
|-------|------|---------|
| 5 | TORO MAJOR | Strongly bullish — full size longs |
| 4 | TORO MINOR | Lean bullish — reduced size longs |
| 3 | NEUTRAL | No directional bias — scalps only |
| 2 | URSA MINOR | Lean bearish — reduced size shorts |
| 1 | URSA MAJOR | Strongly bearish — full size shorts |

### Signal Types
- **APIS CALL** — Strong bullish, macro-aligned
- **KODIAK CALL** — Strong bearish, macro-aligned
- **BULLISH TRADE** — Good long setup
- **BEAR CALL** — Good short setup

---

## Development Phase

Currently in **Phase 2** of Pivot development:
- ✅ Phase 2A-2C: Complete (trade journaling, behavioral monitoring, interactive chat)
- 🔨 Phase 2D-2F: In progress (UW dashboard scraping, advanced analysis)
- 📋 Phase 2G: Planned (auto-scout — screen UW flow + Alpha Feed for Discord picks)

---

## Cost

| Service | Cost |
|---------|------|
| Railway (API + Postgres) | Free tier ($5/month credit) |
| Hetzner VPS | ~€4/month |
| Discord Bot | Free (Discord API) |
| TradingView | Existing subscription |
| **Total** | ~$5/month |
