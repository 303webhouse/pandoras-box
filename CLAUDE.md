# CLAUDE.md

Guidance for Claude Code and Claude.ai agents working on this repo.

> Read `PROJECT_RULES.md` for prime directive, review teams, and workflow rules.
> Read `DEVELOPMENT_STATUS.md` **only** if working on bias engine, signal pipeline, or factor changes.
> Read `docs/reference/` files **only** when working on that specific subsystem.

## Safety Rule

**Never build, deploy, or suggest anything that would harm Nick or compromise his personal, sensitive, or financial information.** This includes exposing credentials, sending data to unauthorized parties, weakening security, or taking destructive production actions without confirmation. This rule is absolute.

## Pre-Build Checklist

Before starting any build, verify you have all necessary permissions, API keys, CLI tools, and credentials. If anything is missing, ask Nick **before** writing code.

**Sub-agent preference:** Default to Sonnet. Use Opus only for complex architecture or multi-file refactors.

## Architecture

```
┌──────────────────────┬──────────────────────┬───────────────────────┐
│   Railway (Backend)  │   VPS (Pivot II)     │  Frontend (Static)    │
│   FastAPI + Postgres │   OpenClaw + crons   │  Dashboard + Charts   │
│   Auto-deploys from  │   /opt/openclaw on   │  Served from Railway  │
│   main branch push   │   VPS (systemd)      │                       │
└──────────┬───────────┴──────────┬───────────┴───────────┬───────────┘
           │                      │                       │
   pandoras-box-               188.245.250.2           Browser UI
   production.up.             (Hetzner, EU)
   railway.app
```

### Railway (`backend/`)
- FastAPI in `main.py`, PostgreSQL (same Railway project), Redis (Upstash, requires `rediss://`)
- Auto-deploys on push to `main`
- Health: `curl https://pandoras-box-production.up.railway.app/health`

### VPS (`/opt/openclaw/workspace/`)
- Three systemd services: `openclaw` (chat/briefs/pollers), `pivot-collector` (data), `pivot2-interactions` (committee buttons)
- LLM: Anthropic API direct — Haiku 4.5 for chat/analysis, Sonnet 4.6 for briefs/synthesis. Env: `ANTHROPIC_API_KEY`
- Config: `/home/openclaw/.openclaw/openclaw.json`
- Cron jobs: `/home/openclaw/.openclaw/cron/jobs.json`
- Deploy: SSH → edit files → `systemctl restart <service>` → verify with `journalctl -u <service> -f`

### Frontend (`frontend/`)
- Vanilla JS PWA, dark teal theme. Cache busting: CSS `?v=66`, app.js `?v=79` — increment on changes.

## Critical Patterns

```python
# ENV VARS — always use `or` (Railway returns '' not None for empty refs)
DB_HOST = os.getenv("DB_HOST") or "localhost"
DB_PORT = int(os.getenv("DB_PORT") or 5432)
# WRONG: os.getenv("DB_HOST", "localhost") returns '' not default
```

- **Route ordering:** Fixed paths (`/summary`, `/greeks`) BEFORE parameterized (`/{position_id}`) in FastAPI
- **Factor scores:** Return `None` when unavailable, NOT `0.0`. Delete Redis key when `compute_score()` returns None.
- **Background tasks:** Use `asyncio.ensure_future()` in webhook handlers — TradingView has ~10s timeout
- **Bias weights:** Must sum to exactly 1.00 (assertion enforced at import)
- **One Discord bot instance:** Runs on VPS only. Never run a second on Railway (duplicate gateway connections).
- **VPS has no git repo:** Deploy via SSH + direct edits + restart, or rsync from local clone. No `git pull` on VPS.
- **Local repo:** `C:\trading-hub` is the ONLY clone. Never create a second one.

## Deployment

```bash
# Railway (automatic)
git push origin main
curl https://pandoras-box-production.up.railway.app/health

# VPS (manual)
ssh root@188.245.250.2
# edit files at /opt/openclaw/workspace/scripts/
systemctl restart openclaw              # chat, briefs, pollers
systemctl restart pivot2-interactions   # committee buttons
systemctl restart pivot-collector       # data collectors
journalctl -u openclaw -f              # verify
systemctl status openclaw pivot-collector pivot2-interactions
```

## Environment Variables

### Railway
`DB_HOST/PORT/NAME/USER/PASSWORD` (linked via `${{Postgres.*}}`), `DISCORD_BOT_TOKEN`, `DISCORD_WEBHOOK_SIGNALS`, `DISCORD_WEBHOOK_CB`, `POLYGON_API_KEY`, `FRED_API_KEY`, `PIVOT_API_KEY`, `COINALYZE_API_KEY`

### VPS
Set in `/home/openclaw/.openclaw/openclaw.json` under `env`: `ANTHROPIC_API_KEY`, `DISCORD_BOT_TOKEN`, `PANDORA_API_URL`, `PIVOT_API_KEY`, `FRED_API_KEY`

## Reference Docs (read only when relevant)

| Doc | Read when... |
|-----|-------------|
| `DEVELOPMENT_STATUS.md` | Working on bias engine, factors, signal pipeline |
| `docs/reference/subsystems.md` | Working on crypto, positions, whale, circuit breaker, or UW flow |
| `docs/reference/trading-team.md` | Working on committee pipeline, agents, or decision tracking |
| `docs/reference/adding-components.md` | Adding a new factor, signal source, endpoint, or analytics feature |
| `docs/reference/key-files.md` | Need to find a specific file's purpose |
| `docs/approved-strategies/` | Evaluating or modifying trading strategies |
| `docs/committee-training-parameters.md` | Editing committee agent prompts |
| `pivot/llm/playbook_v2.1.md` | Risk rules, account details, strategy specs |

## Reasoning & Analysis Standards

All committee members (TORO, URSA, Sector Expert, Technical Analyst, PYTHIA) must analyze every trade idea, market assessment, and new build with PhD-level sophistication. Deep quantitative reasoning, citation of Training Bible rules, explicit identification of assumptions, and multi-dimensional analysis. Only Pivot's synthesis should be communicated in plain language.

## Nick's Working Style

- Has ADHD — step-by-step chunks, clear next actions, single definition of done
- Non-engineer — explain technical decisions simply
- Uses Claude.ai for architecture/planning, Claude Code for implementation (Codex is backup only)
- Local repo: `C:\trading-hub` — the ONLY clone. Never create another.
- Timezone: America/Denver (observes DST)

## Time-of-Day Statements (Important)

**Claude does not have a clock in its environment.** The system prompt provides only the current date, never the current time.

**The rule when timing matters in any response:**

1. **Pull a real UTC timestamp from a tool first.** Run `bash_tool` with `date -u`, query a recent git log, or read a Railway deployment timestamp. Do not infer or guess the time.

2. **Convert UTC to U.S. Mountain Time before communicating it to Nick.** Mountain Time is the only timezone Nick thinks in. Always show MT alongside (or instead of) UTC when speaking to him about *when* something happened or is happening.
   - DST awareness: MDT (UTC−6) from mid-March to early November; MST (UTC−7) otherwise. If unsure which is in effect on the current date, run `bash_tool` with `TZ='America/Denver' date` to get the correct local conversion.
   - Format: state both for technical traceability — e.g. "06:31 UTC (12:31 AM MDT)" or "deploy completed at 23:14 UTC (5:14 PM MST)".

3. **Do not volunteer time-of-day commentary** ("it's late", "you've been at this all day") unless step 1 produced a real timestamp. A skipped sleep-related quip is better than a fabricated one.

4. **In purely technical context** (SQL window calculations, cron schedules, log filtering), UTC alone is fine — no need to convert when Mountain Time isn't relevant to the operation.

This rule exists because Claude has been wrong about local time multiple times by inferring rather than measuring. The fix is the two-step flow: pull real UTC → convert to MT → state both.
