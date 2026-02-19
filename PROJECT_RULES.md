# Pandora's Box — Project Rules

**Last Updated:** 2026-02-19

---

## Prime Directive

**Automate everything possible so Nick can focus on trade execution only.**

No manual data entry, no mental math, no context-switching. If a human has to remember it or look it up repeatedly, it should be automated.

---

## Primary Goal

**Real-time, actionable trade recommendations with minimal subjective interpretation.**

The app must deliver:
1. **Automated filtering** — Signals pass through customizable filters before surfacing
2. **Clear trade recommendations** — Every signal includes Entry, Exit (target), and Stop/Loss prices
3. **Multi-timeframe/multi-asset coverage** — Strategies for swing trades, intraday, equities, crypto, etc.
4. **Future optionality** — Ability to add new strategies/filters from the UI without code changes
5. **Full flexibility** — Every filter and strategy can be toggled on/off independently
6. **Knowledgebase** — Every strategy and filter has an explanation linked to its trade suggestions, scanners, and UI components
7. **Bias challenge** — Pivot must actively challenge Nick's directional biases with objective data

---

## Development Principles

1. **Single source of truth** — Data lives in one place (database), displayed in many.
2. **Fail visible** — If something breaks, the dashboard should show it clearly (not silent failures).
3. **Bias toward action** — Default to shipping incremental improvements over perfect plans.
4. **Modular architecture** — New strategies/indicators plug in without rewriting core logic.
5. **Empty-safe env vars** — Always use `os.getenv("VAR") or default` pattern, never `os.getenv("VAR", default)` to handle Railway's empty string references.

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

### Indicator Categories (Keep Separate)
- **Execution Strategies** — Entry/exit triggers (e.g., Triple Line Trend Retracement)
- **Bias Indicators** — Directional filters, no entry signals (e.g., TICK Range Breadth, Dollar Smile)
- **Black Swan Monitors** — Event-driven alerts (e.g., Truth Social scanner)

---

## Technical Stack

| Component | Tool | Details |
|-----------|------|--------|
| Backend | FastAPI (Python 3.12) | REST + WebSocket, deployed on Railway |
| Database | PostgreSQL | Railway-hosted, same project as backend |
| Cache | Redis | Real-time state, requires SSL (`rediss://`) |
| Frontend | Vanilla JS PWA | No framework, dark teal UI |
| Discord Bot | discord.py + Gemini | Runs on Hetzner VPS as systemd service |
| Charts | TradingView embed | Webhook alerts for automation |
| Version Control | GitHub | `303webhouse/pandoras-box`, push to `main` auto-deploys Railway |
| VPS | Hetzner (PIVOT-EU) | 188.245.250.2, Ubuntu, hosts Discord bot |

---

## Deployment Rules

- **Railway backend**: Auto-deploys on push to `main`. Never configure database variables with `${{Postgres.*}}` references across different Railway projects — they must be in the same project.
- **VPS Discord bot**: Manual deploy via SSH → `git pull` → `systemctl restart pivot-bot`. Always check `journalctl -u pivot-bot -f` after restart.
- **Environment variables**: Railway variables tab for backend, `.env` file on VPS for bot.
- **One bot instance only**: The Discord bot runs on VPS only. Do not run a second instance on Railway (causes duplicate gateway connections).

---

## Workflow Rules

- **Strategy evaluation:** Viability check → optimal timeframe → concise summary → add to approved list
- **New indicators:** Classify as execution vs. bias BEFORE building
- **This file:** Read before making suggestions or building features
- **UI for new features:** Before building a new module, scanner, or feature, ask Nick how it should appear on the UI — provide suggestions but get explicit approval on layout/placement
- **Step-by-step guidance:** Nick has ADHD — break complex tasks into small, manageable chunks
- **Use Claude Code for implementation, Claude.ai for architecture/planning**

---

## Pending Automation Targets

- [ ] Dollar Smile macro bias (DXY + VIX via TradingView webhooks)
- [ ] TICK Range Breadth daily auto-pull
- [ ] UW Dashboard API scraping (Phase 2D)
- [ ] Auto-scout: screen UW flow + Alpha Feed ideas → Discord picks (Phase 2G)
- [ ] Dark Pool Whale Hunter PineScript integration into Pivot ecosystem
