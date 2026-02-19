# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pandora's Box (codename **Pivot**): A real-time trading signal dashboard and AI-powered Discord trading assistant. The system processes TradingView alerts through automated strategies and bias filters, broadcasts trade recommendations via WebSocket, and provides interactive market analysis through a Discord bot.

## Deployment Architecture

### Production Infrastructure
| Component | Platform | Details |
|-----------|----------|---------|
| **Backend API** | Railway (fabulous-essence) | FastAPI + WebSocket, auto-deploys from GitHub `main` |
| **PostgreSQL** | Railway (fabulous-essence) | Same project as backend, linked via `${{Postgres.*}}` references |
| **Discord Bot** | VPS (PIVOT-EU, 188.245.250.2) | Hetzner, runs as `pivot-bot.service` systemd unit |
| **GitHub Repo** | 303webhouse/pandoras-box | Single `main` branch, pushes trigger Railway deploy |

### Railway Service (pandoras-box)
- **URL**: `pandoras-box-production.up.railway.app`
- **Health**: `GET /health` → returns postgres/redis/websocket status
- **Procfile**: `web: sh -c "cd backend && python -m uvicorn main:app --host 0.0.0.0 --port $PORT"`
- **Runtime**: Python 3.12.8
- **Region**: us-west2

### VPS Discord Bot (PIVOT-EU)
- **Host**: root@188.245.250.2
- **Code location**: `/opt/pandoras-box/`
- **Service**: `systemctl status pivot-bot` / `journalctl -u pivot-bot -f`
- **Deploy**: `cd /opt/pandoras-box && git pull && systemctl restart pivot-bot`
- **Intents**: Full (members + message_content + presences enabled in Discord Developer Portal)

### Environment Variables

Railway variables (pandoras-box service → Variables tab):
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` → linked via `${{Postgres.*}}` references
- `DISCORD_BOT_TOKEN`, `DISCORD_TOKEN`, `DISCORD_FLOW_CHANNEL_ID`, `DISCORD_WEBHOOK_SIGNALS`
- `COINALYZE_API_KEY`, `CRYPTO_BINANCE_PERP_HTTP_PROXY`
- `FRED_API_KEY`, `GEMINI_API_KEY`, `PIVOT_API_KEY`

**Important pattern for env vars** — always use `or` instead of default parameter to handle empty strings:
```python
# CORRECT — handles empty string from Railway references
DB_HOST = os.getenv("DB_HOST") or "localhost"
DB_PORT = int(os.getenv("DB_PORT") or 5432)

# WRONG — os.getenv returns '' (not None) when var exists but is empty
DB_HOST = os.getenv("DB_HOST", "localhost")  # returns '' not 'localhost'
DB_PORT = int(os.getenv("DB_PORT", 5432))    # int('') crashes
```

## Commands

### Deploy Backend (Railway — automatic)
```bash
# Push to main triggers auto-deploy
git add . && git commit -m "feat: description" && git push origin main
```

### Deploy Discord Bot (VPS — manual)
```bash
ssh root@188.245.250.2
cd /opt/pandoras-box && git pull origin main
systemctl restart pivot-bot
journalctl -u pivot-bot -f  # verify startup
```

### Local Development
```bash
# Start backend
cd backend && python main.py

# Start frontend (separate terminal)
cd frontend && python -m http.server 3000

# Run Discord bot locally
python run_discord_bot.py

# Windows quick start (backend + frontend + browser)
start.bat
```

### Database
```python
# Initialize schema
from backend.database.postgres_client import init_database
import asyncio
asyncio.run(init_database())
```

## Architecture

### Signal Flow
```
TradingView Alert → POST /webhook/tradingview → Strategy Validator →
Bias Filter → Signal Scorer → Redis Cache + PostgreSQL (async) →
WebSocket Broadcast → All Devices + Discord
```

### Two Applications
- **Main Trading Hub** (`backend/`, `frontend/`): Equity signals, bias filters, TradingView webhooks, REST API
- **Pivot Discord Bot** (`pivot/`, `run_discord_bot.py`): AI-powered trading assistant with market analysis

### Backend Structure (`backend/`)
| Directory | Purpose |
|-----------|---------|
| `webhooks/` | TradingView receivers, circuit breaker |
| `strategies/` | Signal validators (triple_line, exhaustion, ursa_taurus) |
| `bias_filters/` | Macro alignment (tick_breadth, macro_confluence, btc_bottom_signals, dollar_smile) |
| `scoring/` | Signal classification (APIS/KODIAK/BULLISH/BEAR) |
| `database/` | Redis (real-time cache) + PostgreSQL (permanent logs) |
| `websocket/` | Multi-device broadcaster |
| `api/` | REST routers (positions, scanner, bias, btc_signals, options, flow) |
| `scanners/` | Market scanners (hunter, hybrid, cta) |
| `alerts/` | Black swan detection, earnings calendar |
| `discord_bridge/` | Unusual Whales data bridge |

### Pivot Discord Bot (`pivot/`)
| Directory | Purpose |
|-----------|---------|
| `bot.py` | Bot entry point, Discord gateway connection |
| `llm/` | LLM integration (Gemini) for market analysis chat |
| `collectors/` | Market data collectors |
| `monitors/` | Market condition monitors |
| `notifications/` | Discord notification handlers |
| `scheduler/` | Scheduled tasks (market hours, data refresh) |

### Dual Database Pattern
- **Redis**: Real-time state (<2ms), signals expire in 3600s, bias in 86400s
- **PostgreSQL**: Permanent logging for backtesting; tables: signals, positions, options_positions, alerts, btc_sessions

### WebSocket Messages
```python
{"type": "NEW_SIGNAL", ...}
{"type": "BIAS_UPDATE", ...}
{"type": "POSITION_UPDATE", ...}
{"type": "SIGNAL_PRIORITY_UPDATE", ...}
```

## Adding New Components

### New Strategy
1. Create `backend/strategies/[name].py`
2. Import and register in `backend/webhooks/tradingview.py`
3. Document in `docs/approved-strategies/`
4. Add knowledgebase entry

### New Bias Filter
1. Create `backend/bias_filters/[name].py`
2. Add to signal processor pipeline
3. Document in `docs/approved-bias-indicators/`
4. Add knowledgebase entry

### New Knowledgebase Entry
Every indicator, signal, strategy, filter, or scanner **must** have a corresponding entry in `data/knowledgebase.json`:
```json
{
  "id": "term-slug-lowercase",
  "term": "Display Term Name",
  "category": "Bias Indicators|Signals|Strategies|Scanners|...",
  "shortDescription": "Max 500 words for popup",
  "fullDescription": "Full markdown documentation",
  "relatedTerms": ["related-term-id"]
}
```
Reload cache: `POST /api/knowledgebase/reload`

## Key API Endpoints

- `GET /health` — Service health check (postgres, redis, websocket status)
- `POST /webhook/tradingview` — Receive TradingView alerts
- `GET /api/bias/{timeframe}` — Get bias level (DAILY/WEEKLY/MONTHLY)
- `GET /api/positions` — Open positions
- `GET /api/scanner` — Market scanner
- `GET /api/btc-signals` — BTC macro signals
- `WS /ws` — WebSocket connection for real-time updates
