# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pandora's Box: Real-time trading signal dashboard with multi-device sync and sub-100ms latency. Includes a companion BTC crypto scalping system.

## Commands

### Main Trading Hub (port 8000)
```bash
# Start backend
cd backend && python main.py

# Start frontend (separate terminal)
cd frontend && python -m http.server 3000

# Windows quick start (runs both + opens browser)
start.bat
```

### Crypto Scalper (port 8001)
```bash
cd crypto-scalper
start.bat
# Or manually:
cd crypto-scalper/backend && uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Discord Bot
```bash
python run_discord_bot.py
```

### Database Initialization
```python
from backend.database.postgres_client import init_database
import asyncio
asyncio.run(init_database())
```

## Architecture

### Signal Flow (target <30ms total)
```
TradingView Alert → POST /webhook/tradingview → Strategy Validator (10ms) →
Bias Filter (5ms) → Signal Scorer (5ms) → Redis Cache (2ms) + PostgreSQL (async) →
WebSocket Broadcast (3ms) → All Devices
```

### Two Applications
- **Main Trading Hub** (`backend/`, `frontend/`): Equity signals, bias filters, TradingView webhooks
- **Crypto Scalper** (`crypto-scalper/`): BTC perpetual futures, Bybit WebSocket, 4 scalping strategies

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

### Dual Database Pattern
- **Redis**: Real-time state (<2ms), signals expire in 3600s, bias in 86400s
- **PostgreSQL**: Permanent logging for backtesting, tables: signals, positions, options_positions, alerts, btc_sessions

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

### New Bias Filter
1. Create `backend/bias_filters/[name].py`
2. Add to signal processor pipeline
3. Document in `docs/approved-bias-indicators/`

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

## Configuration

Environment variables in `config/.env`:
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `FRED_API_KEY`, `GEMINI_API_KEY`

## Key API Endpoints

### Main Hub
- `POST /webhook/tradingview` - Receive alerts
- `GET /api/bias/{timeframe}` - Get bias level (DAILY/WEEKLY/MONTHLY)
- `GET /api/positions` - Open positions
- `GET /api/scanner` - Market scanner
- `GET /api/btc-signals` - BTC macro signals
- `WS /ws` - WebSocket connection

### Crypto Scalper
- `GET /api/signals` - Active BTC signals
- `GET /api/strategies` - Strategy status
- `GET /api/risk/status` - Account status
- `GET /api/market` - Current market data
- `WS /ws` - Real-time updates

## Frontend

PWA dashboard at `frontend/`:
- `app.js`: WebSocket client + signal management
- `styles.css`: Dark teal UI with lime/orange accents
- `manifest.json`: PWA install config
- `knowledgebase.html/js`: Strategy documentation viewer
