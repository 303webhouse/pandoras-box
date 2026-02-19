# CODEX.md

This file provides guidance to OpenAI Codex and other AI coding assistants working with this repository.

For the full project context, see [CLAUDE.md](./CLAUDE.md) — it is the canonical reference. For development status and roadmap, see [DEVELOPMENT_STATUS.md](./DEVELOPMENT_STATUS.md).

## Quick Reference

**Project**: Pivot — AI-powered Discord trading assistant for options swing trading.

**Repo**: `303webhouse/pandoras-box` (single `main` branch). "Pandora's Box" is the legacy name.

## Deployment

| Component | Platform | URL/Host |
|-----------|----------|----------|
| Backend API | Railway (fabulous-essence) | pandoras-box-production.up.railway.app |
| PostgreSQL | Railway (fabulous-essence) | Same project, linked via `${{Postgres.*}}` |
| Discord Bot | VPS (Hetzner) | 188.245.250.2, systemd `pivot-bot.service` |
| Data Collector | VPS (same box) | systemd `pivot-collector.service` |

**Deploy backend**: Push to `main` → Railway auto-deploys.
**Deploy bot**: `ssh root@188.245.250.2` → `cd /opt/pivot && git pull && systemctl restart pivot-bot`
**Health check**: `curl https://pandoras-box-production.up.railway.app/health`

## Tech Stack

- **Backend**: Python 3.12, FastAPI, uvicorn
- **Database**: PostgreSQL (Railway) + Redis (Upstash, SSL required)
- **Frontend**: Vanilla JS PWA (dashboard + 6-tab analytics)
- **Discord Bot**: discord.py + Gemini Pro via OpenRouter
- **Indicators**: PineScript on TradingView (Whale Hunter, CTA, Circuit Breaker)

## Key Directories

```
backend/          → FastAPI backend (webhooks, strategies, bias filters, scoring, analytics, API)
backend/discord_bridge/ → Discord bot source (bot.py is 3,466 lines — the live bot)
backend/discord_bridge/uw/ → UW flow parser, aggregator, filter
pivot/            → Bot core (bot.py entry, llm/, collectors/, monitors/, scheduler/)
pivot/llm/        → prompts.py (Pivot's brain), playbook_v2.1.md, pivot_agent.py
frontend/         → PWA dashboard (index.html, app.js, analytics.js, styles.css)
config/           → Environment config templates
docs/             → PineScript source, architecture docs
```

## Environment Variable Pattern

Always handle empty strings from Railway variable references:
```python
# CORRECT
DB_HOST = os.getenv("DB_HOST") or "localhost"
DB_PORT = int(os.getenv("DB_PORT") or 5432)

# WRONG — empty string '' is truthy for os.getenv default
DB_HOST = os.getenv("DB_HOST", "localhost")
```

## Key Files

| File | What It Does |
|------|--------------|
| `pivot/llm/prompts.py` | Pivot's personality, analysis rules, evaluation templates |
| `pivot/llm/playbook_v2.1.md` | Trading rules, risk params, account balances |
| `backend/discord_bridge/bot.py` | The running Discord bot (VPS copy is live) |
| `backend/bias_engine/composite.py` | Factor weighting and composite calculation |
| `backend/webhooks/tradingview.py` | TradingView webhook receiver |
| `backend/webhooks/circuit_breaker.py` | Circuit breaker bias override |
| `pivot/scheduler/cron_runner.py` | Heartbeat scheduler for monitors |
| `pivot/deploy.sh` | VPS deployment script |

## Rules

- Read `PROJECT_RULES.md` before making architectural suggestions
- Read `DEVELOPMENT_STATUS.md` to understand what's built vs planned
- Every new factor needs a collector, bias filter, composite registration, and scheduler entry
- Classify indicators as MACRO/TECHNICAL/FLOW/BREADTH before building
- `prompts.py` is Pivot's brain — edit carefully, test after deploy
- Always deploy both: push to git (Railway) + sync VPS (bot restart)
- Update `DEVELOPMENT_STATUS.md` after completing significant work
