# Pivot — Project Rules

**Last Updated:** March 11, 2026

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

## Review Teams

### Olympus (Trading Committee)

4-agent double-pass review for **trade strategy evaluations, signal pipeline changes, and bias engine modifications**.

| Agent | Role |
|-------|------|
| **TORO** | Bull analyst — finds reasons to take the trade |
| **URSA** | Bear analyst — finds reasons to pass |
| **TECHNICALS** | Risk/structure analyst — entry/stop/target/sizing |
| **PIVOT** | Synthesizer — final recommendation with conviction level |

**Use for:** Evaluating proposed strategies, reviewing signal pipeline changes, assessing bias engine modifications, trade-specific analysis.

**Runs inside:** Claude.ai conversations (not VPS API) to avoid API costs.

### The Titans (Software Design Team)

4-agent double-pass review for **all significant builds, revisions, and adjacent projects** before any Brief is sent to Claude Code.

| Agent | Role | Expertise |
|-------|------|-----------|
| **ATLAS** | Senior Backend Architect | Decades of experience at Wall Street and finance firms. Focuses on scalability, data integrity, API design, and system reliability. |
| **HELIOS** | Frontend UI/UX Specialist | Designs clean, responsive, reliable interfaces for fast-paced and high-stress environments. Obsessive about usability and information hierarchy. |
| **AEGIS** | Cybersecurity Expert | Obsessive about data security, privacy, authentication, and attack surface minimization. Reviews every external-facing change. |
| **ATHENA** | Project Manager (Final Decision) | Award-winning attention to detail, usability, and aesthetics without sacrificing security or reliability. Presents the final plan to Nick. |

**The Titans Workflow:**

1. **Pass 1 (Independent):** Each Titan reviews the proposed build independently and makes their recommendations.
2. **Pass 2 (Cross-Review):** Each Titan does a second pass incorporating all other Titans' suggestions, producing final recommendations.
3. **ATHENA Overview:** ATHENA presents a unified plan to Nick with an overview of all recommendations, trade-offs, and any clarifications needed.
4. **Nick Approval:** Nick reviews, asks questions, requests changes.
5. **Brief Written:** Claude.ai writes the implementation brief targeting Claude Code.
6. **Final Brief Review:** The Titans do a final double-pass review of the completed Brief before it's sent to Claude Code to build.

**Use for:** Every significant revision, new build, or adjacent project. Not needed for small bug fixes or one-line config changes.

**Runs inside:** Claude.ai conversations (this project).

---

## Development Principles

1. **Single source of truth** — Data lives in PostgreSQL, displayed in many places (Discord, UI, briefs)
2. **Fail visible** — If data is stale or missing, say so explicitly. Never silently use bad data.
3. **Bias toward action** — Ship incremental improvements over perfect plans
4. **Modular architecture** — New factors, signals, and strategies plug in without rewriting core
5. **Brief-driven development** — Architecture decisions happen in Claude.ai conversations. Implementation specs are written as markdown briefs and handed to Claude Code for building. Codex is a backup builder only.
6. **Empty-safe env vars** — Always use `os.getenv("VAR") or default` pattern, never `os.getenv("VAR", default)` to handle Railway's empty string references.
7. **Data source priority** — Polygon.io is the primary data source for all equity/ETF price data (OHLCV, volume, snapshots) and options data (chains, greeks, IV, OI). yfinance is the fallback source, used only when Polygon fails or for data types Polygon does not cover. VIX and index tickers (`^VIX`, `^VIX3M`, `^ADVN`, `^DECLN`, `DX-Y.NYB`) remain on yfinance — no Polygon Indices subscription.

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
- **Unusual Whales** — Options flow alerts (via Discord Premium Bot monitoring → UW Watcher on VPS)
- **Server-side scanners** — Holy Grail, Scout Sniper, Sell the Rip (Railway background loops)
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
| Pivot II | OpenClaw + discord.py | VPS: 188.245.250.2 (`/opt/openclaw`) |
| LLM (Pivot II) | Anthropic API direct | Haiku 4.5 for chat/analysis, Sonnet 4.5 for briefs/synthesis |
| LLM (Olympus) | Anthropic API direct | Haiku for TORO/URSA/TECHNICALS, Sonnet for Pivot synthesizer |
| Charts | TradingView embed | Webhook alerts for automation |
| Version Control | GitHub | `303webhouse/pandoras-box`, push to `main` auto-deploys Railway |
| VPS | Hetzner (PIVOT-EU) | 188.245.250.2, Debian, hosts Pivot II + collectors |

---

## Deployment Rules

- **Railway backend**: Auto-deploys on push to `main`. Postgres must be in the SAME Railway project — never use `${{Postgres.*}}` references across different projects.
- **VPS Pivot II**: Manual deploy via SSH → edit files at `/opt/openclaw/workspace/scripts/` → `systemctl restart openclaw`. Always check `journalctl -u openclaw -f` after restart.
- **VPS has no git repo**: Deployment uses direct file edits on VPS + service restart, OR `rsync` from local clone. There is no `git pull` on VPS.
- **One bot instance only**: The Discord bot runs on VPS only. Never run a second instance on Railway (causes duplicate gateway connections).
- **VPS has THREE services**: `openclaw` (Pivot chat/briefs/pollers), `pivot-collector.service` (data collectors), `pivot2-interactions.service` (committee button handler). All managed via systemd.

---

## Workflow Rules

- **Architecture decisions**: Discuss in Claude.ai with Nick → document rationale
- **Significant builds**: Run through **The Titans** review (Pass 1 → Pass 2 → ATHENA overview → Nick approval → Brief → Titans final review → Claude Code)
- **Strategy/trading changes**: Run through **Olympus** review (TORO/URSA/TECHNICALS/PIVOT double-pass)
- **Implementation**: Write detailed markdown brief → hand to Claude Code → deploy → verify. Codex is backup only.
- **New indicators**: Classify as MACRO/TECHNICAL/FLOW/BREADTH before building
- **New signals**: Must include evaluation template in committee prompts or Pivot system prompt
- **UI changes**: Ask Nick how it should look — suggest options but get approval
- **Prompt changes**: Committee prompts and Pivot system prompts are the system's brain — edit carefully, test after deploy
- **Step-by-step guidance**: Nick has ADHD — break complex tasks into small, manageable chunks
- **Use Claude Code for implementation, Claude.ai for architecture/planning**

---

## Agent Maintenance Protocol

**All Claude.ai (Opus) and Claude Code agents must follow these rules to maintain project continuity.**

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
