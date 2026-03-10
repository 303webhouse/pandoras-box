# Pivot

AI-powered trading assistant for options swing trading. Combines 20+ automated macro/technical/flow factors, TradingView webhook integration, Unusual Whales flow data, and dark pool detection into a Discord-based trading intelligence system.

## How It Works

Pivot lives in Discord. It monitors market data sources continuously, evaluates incoming signals (whale alerts, options flow, trade ideas), and delivers market analysis through:

- **Real-time signal evaluation** — TradingView webhooks trigger instant analysis with entry/stop/target
- **Daily EOD briefs** — End-of-day market summary with bias, factor breakdown, and convergence detection
- **Interactive chat** — Ask Pivot about any ticker, strategy, or market condition
- **Screenshot analysis** — Drop an Unusual Whales or chart screenshot and Pivot extracts actionable data
- **Trade journaling** — Log trades via Discord, track P&L, and measure signal performance
- **Dark pool detection** — Whale Hunter PineScript detects institutional absorption patterns

## Architecture

| Component | Technology | Location |
|-----------|-----------|----------|
| Backend API | FastAPI + PostgreSQL + Redis | Railway (auto-deploys from `main`) |
| Discord Bot (Pivot II) | discord.py + Claude (Anthropic API) | VPS at `188.245.250.2` |
| Frontend | Vanilla JS PWA (6-tab analytics) | `frontend/` |
| Indicators | PineScript | TradingView (Whale Hunter, CTA) |

## Repository Structure

```
pandoras-box/
├── CLAUDE.md                  # Agent instructions (read first)
├── DEVELOPMENT_STATUS.md      # Phase roadmap, what's built, what's planned
├── PROJECT_RULES.md           # Trading rules + agent maintenance protocol
├── PROJECT_SUMMARY.md         # Current state snapshot
├── backend/                   # FastAPI backend (Railway)
│   ├── main.py                # Entry point, all routers
│   ├── analytics/             # Analytics system (signal tracking, P&L, health)
│   ├── api/                   # REST endpoints
│   ├── bias_engine/           # 20+ factor composite bias calculation
│   ├── bias_filters/          # Individual factor implementations
│   ├── webhooks/              # TradingView + Whale Hunter receivers
│   ├── discord_bridge/        # Discord bot (VPS copy is live)
│   └── database/              # PostgreSQL + Redis clients
├── pivot/                     # Bot core (collectors, LLM, monitors)
│   ├── llm/                   # prompts.py (brain), playbook, agent
│   ├── collectors/            # Scheduled factor data fetchers
│   ├── monitors/              # Alert monitors (bias, volume, earnings)
│   └── scheduler/             # Cron job runner
├── frontend/                  # PWA dashboard
│   ├── index.html             # Main dashboard
│   ├── analytics.js           # Analytics UI (6 tabs)
│   └── styles.css             # Dark teal theme
└── docs/                      # Specs, PineScript, handoff docs
```

## Getting Started (for Agents)

1. Read `CLAUDE.md` for architecture and key files
2. Read `DEVELOPMENT_STATUS.md` for what's built vs planned
3. Read `PROJECT_RULES.md` for trading rules and agent maintenance protocol
4. Check `PROJECT_SUMMARY.md` for current state and known issues

## Deployment

```bash
# Backend: push to main → Railway auto-deploys
git push origin main

# VPS bot: manual file sync (VPS is NOT a git repo)
# Edit files locally, then SCP to /opt/openclaw/workspace/scripts/
scp scripts/my_script.py root@188.245.250.2:/opt/openclaw/workspace/scripts/
ssh root@188.245.250.2 "systemctl restart openclaw"

# Verify
curl https://pandoras-box-production.up.railway.app/health
```

## Key Documentation

- `CLAUDE.md` — Architecture, subsystems, commands, key files
- `DEVELOPMENT_STATUS.md` — Phase roadmap, analytics phases, known issues, Nick's context
- `PROJECT_RULES.md` — Prime directive, bias hierarchy, agent maintenance protocol
- `PROJECT_SUMMARY.md` — Current state snapshot
- `pivot/llm/playbook_v2.1.md` — Trading rules, risk parameters, account details
