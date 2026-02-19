# CODEX.md

This file provides guidance to OpenAI Codex and other AI coding assistants working with this repository.

For the full project context, see [CLAUDE.md](./CLAUDE.md) — it is the canonical reference and this file mirrors its key information.

## Quick Reference

**Project**: Pandora's Box (codename Pivot) — real-time trading signal dashboard + AI Discord trading assistant.

**Repo**: `303webhouse/pandoras-box` (single `main` branch)

## Deployment

| Component | Platform | URL/Host |
|-----------|----------|----------|
| Backend API | Railway (fabulous-essence) | pandoras-box-production.up.railway.app |
| PostgreSQL | Railway (fabulous-essence) | Same project, linked via `${{Postgres.*}}` |
| Discord Bot | VPS (Hetzner) | 188.245.250.2, systemd `pivot-bot.service` |

**Deploy backend**: Push to `main` → Railway auto-deploys.
**Deploy bot**: SSH to VPS → `cd /opt/pandoras-box && git pull && systemctl restart pivot-bot`

## Tech Stack

- **Backend**: Python 3.12, FastAPI, uvicorn
- **Database**: PostgreSQL (Railway) + Redis
- **Frontend**: Vanilla JS PWA
- **Discord Bot**: discord.py with Gemini LLM integration
- **Infra**: Railway (API + DB), Hetzner VPS (bot), GitHub

## Key Directories

```
backend/          → FastAPI backend (webhooks, strategies, bias filters, scoring, API, database)
pivot/            → Discord bot (bot.py, llm/, collectors/, monitors/, scheduler/)
frontend/         → PWA dashboard (HTML/CSS/JS)
config/           → Environment config templates
docs/             → Strategy and architecture documentation
data/             → Knowledgebase JSON, runtime data
migrations/       → Database migration scripts
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

## Commands

```bash
# Local dev
cd backend && python main.py          # API on port 8000
cd frontend && python -m http.server 3000  # UI on port 3000
python run_discord_bot.py             # Discord bot

# Health check
curl https://pandoras-box-production.up.railway.app/health
```

## Rules

- Read `PROJECT_RULES.md` before making architectural suggestions
- Every new strategy/filter needs a knowledgebase entry in `data/knowledgebase.json`
- Classify indicators as **execution** (entry/exit triggers) vs **bias** (directional filters) before building
- UI changes need explicit approval — suggest layout but don't assume placement
