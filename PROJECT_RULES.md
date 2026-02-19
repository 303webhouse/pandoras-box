# Pivot — Project Rules

**Last Updated:** February 19, 2026

---

## Prime Directive

**Automate everything possible so Nick can focus on trade execution only.**

No manual data entry, no mental math, no context-switching. If a human has to remember it or look it up repeatedly, it should be automated.

---

## Primary Goal

**Real-time, actionable trade intelligence delivered via Discord with objective market analysis.**

The system must deliver:
1. **Automated data collection** — 20+ macro/technical/flow factors fetched on schedule
2. **Clear trade evaluations** — Every signal evaluated with entry, exit, stop, and conviction level
3. **Bias challenge** — Pivot actively challenges Nick's directional biases with data
4. **Multi-source convergence** — Flag when independent signals agree (whale + UW flow + sector rotation)
5. **Performance tracking** — Analytics system measures what's working and what isn't

---

## Development Principles

1. **Single source of truth** — Data lives in PostgreSQL, displayed in many places (Discord, UI, briefs)
2. **Fail visible** — If data is stale or missing, say so explicitly. Never silently use bad data.
3. **Bias toward action** — Ship incremental improvements over perfect plans
4. **Modular architecture** — New factors, signals, and strategies plug in without rewriting core
5. **Brief-driven development** — Architecture decisions happen in Claude.ai conversations. Implementation specs are written as markdown briefs and handed to Codex for building.
6. **Empty-safe env vars** — Always use `os.getenv("VAR") or default` pattern, never `os.getenv("VAR", default)` to handle Railway's empty string references.

---

## Trading System Rules

### Bias Hierarchy (5 Levels)
| Level | Name | Meaning |
|-------|------|---------|
| 5 | TORO MAJOR | Strongly bullish — full size longs |
| 4 | TORO MINOR | Lean bullish — reduced size longs |
| 3 | NEUTRAL | No directional bias — scalps only or sit out |
| 2 | URSA MINOR | Lean bearish — reduced size shorts |
| 1 | URSA MAJOR | Strongly bearish — full size shorts |

### Factor Categories (Keep Separate)
- **MACRO** — Economic/credit indicators (yield curve, HY OAS, CAPE, claims, ISM, DXY)
- **TECHNICAL** — Price-based indicators (SPY SMA/EMA distance, VIX regime, sector rotation)
- **FLOW** — Order flow and sentiment (options sentiment, put/call ratio, UW flow, dark pool)
- **BREADTH** — Market internals (TICK breadth, market breadth, advance/decline)

### Signal Sources
- **TradingView webhooks** — Strategy alerts, Whale Hunter, Circuit Breaker, Scout
- **Unusual Whales** — Options flow alerts (via Discord Premium Bot monitoring)
- **UW Screenshots** — Manual screenshots analyzed by Pivot via Claude Vision
- **Trade Ideas** — Manual trade concepts evaluated by Pivot

### Risk Rules (from Playbook v2.1)
- Max 5% account risk per trade
- Max 2 correlated positions simultaneously
- Circuit Breaker overrides bias during extreme market events
- DEFCON system monitors behavioral patterns and market confluence

---

## Technical Stack

| Component | Tool | Details |
|-----------|------|---------|
| Backend | FastAPI (Python 3.12) | REST + WebSocket, deployed on Railway |
| Database | PostgreSQL | Railway-hosted (fabulous-essence project) |
| Cache | Redis (Upstash) | Real-time state, requires SSL (`rediss://`) |
| Frontend | Vanilla JS PWA | No framework, dark teal UI, 6-tab analytics |
| Discord Bot | discord.py | VPS: 188.245.250.2 (`/opt/pivot`) |
| LLM | Claude Sonnet 4.6 via OpenRouter | `anthropic/claude-sonnet-4.6` — analysis, evaluation, briefs |
| Charts | TradingView embed | Webhook alerts for automation |
| Version Control | GitHub | `303webhouse/pandoras-box`, push to `main` auto-deploys Railway |
| VPS | Hetzner (PIVOT-EU) | 188.245.250.2, Debian, hosts bot + collector |

---

## Deployment Rules

- **Railway backend**: Auto-deploys on push to `main`. Postgres must be in the SAME Railway project — never use `${{Postgres.*}}` references across different projects.
- **VPS Discord bot**: Manual deploy via SSH → `git pull` → `systemctl restart pivot-bot`. Always check `journalctl -u pivot-bot -f` after restart.
- **One bot instance only**: The Discord bot runs on VPS only. Never run a second instance on Railway (causes duplicate gateway connections).
- **VPS has TWO services**: `pivot-bot.service` (Discord bot) and `pivot-collector.service` (data collector). Both managed via systemd.
- **bot.py source of truth**: Edit `backend/discord_bridge/bot.py` in the repo. The VPS copy at `/opt/pivot/discord_bridge/bot.py` is synced from git.

---

## Workflow Rules

- **Architecture decisions**: Discuss in Claude.ai with Nick → document rationale
- **Implementation**: Write detailed markdown brief → hand to Codex → deploy → verify
- **New indicators**: Classify as MACRO/TECHNICAL/FLOW/BREADTH before building
- **New signals**: Must include evaluation template in `pivot/llm/prompts.py`
- **UI changes**: Ask Nick how it should look — suggest options but get approval
- **Prompt changes**: `prompts.py` is Pivot's brain — edit carefully, test in Discord after deploy
- **Step-by-step guidance**: Nick has ADHD — break complex tasks into small, manageable chunks
- **Use Claude Code for implementation, Claude.ai for architecture/planning**

---

## Agent Maintenance Protocol

**All Claude.ai (Opus) and Claude Code (Codex/Sonnet) agents must follow these rules to maintain project continuity.**

### 1. Update Documentation After Significant Changes

| Change Type | Update These Files |
|-------------|-------------------|
| New module, subsystem, or major feature | `DEVELOPMENT_STATUS.md`, `CLAUDE.md` |
| New API endpoint | `CLAUDE.md` (key files section) |
| New database table | `DEVELOPMENT_STATUS.md` |
| New factor or signal source | `CLAUDE.md` (subsystems), `PROJECT_RULES.md` (if new category) |
| Strategy or risk rule change | `PROJECT_RULES.md`, update Playbook reference |
| Bug fix for a known issue | `DEVELOPMENT_STATUS.md` (remove from known issues) |
| Architecture decision with rationale | `DEVELOPMENT_STATUS.md` |

### 2. Track What's Real vs Planned

**Never describe planned/unbuilt features as if they exist.** If unsure whether something has been implemented, check:
- `DEVELOPMENT_STATUS.md` for build status
- The actual codebase (grep for the function/endpoint/table)
- Railway health endpoint or VPS service status

### 3. Maintain the Known State

These values change and should be verified, not assumed:
- Account balances (Robinhood, 401k, Breakout prop, Coinbase)
- Number of active factors and which ones are stale
- Current bias composite level
- What's deployed on Railway vs what's deployed on VPS (they can drift)

### 4. Flag Contradictions

If documentation contradicts the actual code, **fix the documentation** and note it. The code is the source of truth.

### 5. Preserve Decision Context

When making architecture decisions, document **why** not just **what**. Future agents need to understand the reasoning.
- ❌ "Added DXY factor with weight 0.05"
- ✅ "Added DXY factor with weight 0.05 — kept low because dollar strength is a secondary confirmation signal, not a primary equity rotation driver."

---

## Pending Automation Targets

- [ ] UW Dashboard API scraping (Phase 2F)
- [ ] Auto-scout: screen UW flow + Alpha Feed ideas → Discord picks (Phase 2G)
- [ ] Crypto autonomous trading sandbox (Coinbase)
- [ ] Robinhood trade import (CSV parser, signal matching)
- [ ] DXY macro factor (in Codex brief)
- [ ] Dark Pool Whale Hunter RVOL conviction modifier
