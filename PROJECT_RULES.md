# Pandora's Box — Project Rules

**Last Updated:** 2026-01-22

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

---

## Development Principles

1. **Single source of truth** — Data lives in one place (database), displayed in many.
2. **Fail visible** — If something breaks, the dashboard should show it clearly (not silent failures).
3. **Bias toward action** — Default to shipping incremental improvements over perfect plans.
4. **Modular architecture** — New strategies/indicators plug in without rewriting core logic.

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

| Component | Tool | Notes |
|-----------|------|-------|
| Backend | FastAPI (Python) | REST + WebSocket |
| Database | PostgreSQL (Supabase) | Persistent storage |
| Cache/Realtime | Redis (Upstash) | Requires SSL, use `rediss://` |
| Frontend | Vanilla JS | No framework, keep simple |
| Charts | TradingView embed | Webhook alerts for automation |
| Version Control | GitHub | Sync from `C:\trading-hub` |

---

## Workflow Rules

- **Strategy evaluation:** Viability check → optimal timeframe → concise summary → add to approved list
- **New indicators:** Classify as execution vs. bias BEFORE building
- **This file:** Read before making suggestions or building features
- **UI for new features:** Before building a new module, scanner, or feature, ask Nick how it should appear on the UI — provide suggestions but get explicit approval on layout/placement

---

## Pending Automation Targets

- [ ] Dollar Smile macro bias (DXY + VIX via TradingView webhooks)
- [ ] TICK Range Breadth daily auto-pull
- [ ] TORO MAJOR/MINOR display fix (currently showing "Loading...")
