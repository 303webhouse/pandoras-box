# Pandora's Box — Project Rules
**Last Updated:** 2026-02-06

## Prime Directive
Automate everything possible so Nick can focus on trade execution only. No manual data entry, no mental math, no context-switching. If a human has to remember it or look it up repeatedly, it should be automated.

## Primary Goal
Real-time, actionable trade recommendations with minimal subjective interpretation.
The app must deliver:
- **Automated filtering** — Signals pass through customizable filters before surfacing
- **Clear trade recommendations** — Every signal includes Entry, Exit (target), and Stop/Loss prices
- **Multi-timeframe/multi-asset coverage** — Strategies for swing trades, intraday, equities, crypto, etc.
- **Future optionality** — Ability to add new strategies/filters from the UI without code changes
- **Full flexibility** — Every filter and strategy can be toggled on/off independently
- **Knowledgebase** — Every strategy and filter has an explanation linked to its trade suggestions, scanners, and UI components

## Development Principles
- **Single source of truth** — Data lives in one place (database), displayed in many.
- **Fail visible** — If something breaks, the dashboard should show it clearly (not silent failures).
- **Bias toward action** — Default to shipping incremental improvements over perfect plans.
- **Modular architecture** — New strategies/indicators plug in without rewriting core logic.

---

## AI Builder Workflow
Multiple AI tools are used to build this project. Here is how they should be utilized:

| Tool | Role | When to Use |
|------|------|-------------|
| **Opus (Claude.ai)** | Architect & Analyst | Diagnosing problems, designing systems, writing specs, reviewing results, post-mortems |
| **Claude Code / Codex** | Builder | Writing code from specs, Git commits, Railway deploys, refactoring |
| **Pivot (OpenClaw)** | Runtime Operator | Real-time data collection, scheduled pulls, Discord scraping, POSTing to backend APIs |

**Handoff convention:** Opus writes spec docs in `docs/specs/`. Builders read the relevant spec + this file before implementing. Every spec is self-contained — pick one up and build it without needing the others.

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

### Composite Bias Engine (v2 — Feb 2026 Rebuild)

> **WHY THIS EXISTS:** The original bias system only read from the Savita indicator (monthly, often unavailable). Six other weekly/daily factors existed in `/market-indicators/summary` but were NEVER wired into the main bias output. During the Feb 2–5, 2026 market breakdown (NASDAQ -4.5%, S&P Software -10%), the system failed to detect any risk-off conditions because Savita was stale and the other factors were disconnected. This rebuild creates a single unified composite score from ALL available factors.

#### Architecture Overview

```
DATA SOURCES                         COMPOSITE ENGINE                    OUTPUT
─────────────                        ────────────────                    ──────
Pivot (scheduled pulls) ──┐
TradingView webhooks ─────┤          ┌──────────────────────┐
yfinance (fallback) ──────┼────────► │ Score each factor    │
Discord/UW (Pivot) ───────┤          │ Apply weights        │──► Single composite score
Manual override (UI) ─────┘          │ Handle staleness     │──► 5-level bias mapping
                                     │ Rate-of-change boost │──► WebSocket broadcast
                                     │ Cross-asset confirm  │──► Frontend display
                                     └──────────────────────┘
```

#### Factor Weights & Staleness

| Factor | Weight | Staleness Threshold | Update Frequency | Data Source |
|--------|--------|-------------------|------------------|-------------|
| Credit Spreads (HYG/TLT) | 18% | 48 hours | Daily | Pivot → yfinance |
| Market Breadth (RSP/SPY) | 18% | 48 hours | Daily | Pivot → yfinance |
| VIX Term Structure (VIX/VIX3M) | 16% | 4 hours | Intraday | Pivot → CBOE/yfinance |
| TICK Breadth | 14% | 4 hours | Intraday | TradingView webhook |
| Sector Rotation | 14% | 48 hours | Daily | Pivot → yfinance |
| Dollar Smile (DXY) | 8% | 48 hours | Daily | Pivot → yfinance |
| Excess CAPE Yield | 8% | 7 days | Weekly | Pivot → web scrape |
| Savita (BofA) | 4% | 45 days | Monthly | Manual entry (proprietary) |

**Writer Ownership Rule (Feb 19, 2026 hotfix):** each factor key has one writer.
- Pivot-owned keys: `credit_spreads`, `market_breadth`, `vix_term`, `tick_breadth`, `sector_rotation`, `dollar_smile`, `excess_cape`, `savita`.
- Backend scorer-owned keys: all remaining factors in `bias_engine.factor_scorer`.
- Backend scorer must skip Pivot-owned keys to prevent Redis overwrite races.

**Macro/Volatility Price Sanity Bounds (Feb 19, 2026 hotfix):**
- `^VIX`: 9 to 90
- `^VIX3M`: 9 to 60
- `DX-Y.NYB` (DXY): 80 to 120
- Any out-of-range value is treated as anomalous, rejected, and never cached.

**Graceful Degradation Rule:** When a factor goes stale (exceeds its staleness threshold), its weight is redistributed proportionally to remaining active factors. The system MUST always produce a valid bias reading from whatever subset of factors is available.

#### Composite Score → Bias Level Mapping

| Score Range | Bias Level | Trading Action |
|-------------|-----------|----------------|
| +0.60 to +1.00 | TORO MAJOR | Full size longs |
| +0.20 to +0.59 | TORO MINOR | Reduced size longs |
| -0.19 to +0.19 | NEUTRAL | Scalps only or sit out |
| -0.59 to -0.20 | URSA MINOR | Reduced size shorts |
| -1.00 to -0.60 | URSA MAJOR | Full size shorts |

#### Rate-of-Change Escalation
When multiple factors deteriorate rapidly (3+ factors shift bearish within 24 hours), the composite score gets a **velocity multiplier** of 1.3x. This ensures multi-day breakdowns like Feb 2–5 trigger URSA MAJOR faster than static threshold-checking alone.

#### Manual Override
Nick can override the composite bias from the UI. Override persists until manually cleared OR until the composite crosses a full level boundary in the opposite direction (e.g., override to TORO MINOR auto-clears if composite hits URSA MINOR).

#### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/bias/composite` | Full composite bias with factor breakdown |
| `POST /api/bias/factor-update` | Pivot POSTs new factor data here |
| `POST /api/bias/override` | Manual bias override |
| `GET /api/bias/history` | Historical bias readings for backtesting |

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
| Data Collection | Pivot (OpenClaw on Hetzner VPS) | 24/7 scheduled pulls, Discord scraping |
| Deployment | Railway | Backend auto-deploys from `main` |

---

## Workflow Rules
1. **Strategy evaluation:** Viability check → optimal timeframe → concise summary → add to approved list
2. **New indicators:** Classify as execution vs. bias BEFORE building
3. **This file:** Read before making suggestions or building features
4. **UI for new features:** Before building a new module, scanner, or feature, ask Nick how it should appear on the UI — provide suggestions but get explicit approval on layout/placement
5. **Spec docs:** Implementation specs live in `docs/specs/`. Read the relevant spec before building a component.
6. **Pivot tasks:** Data collection tasks for Pivot are defined in `docs/specs/pivot-data-collector.md`

---

## Pending Automation Targets
- ~~Dollar Smile macro bias~~ (implemented)
- ~~TICK Range Breadth daily auto-pull~~ (implemented via TradingView)
- ~~TORO MAJOR/MINOR display fix~~ (fixed)
- **Composite Bias Engine** — See `docs/specs/composite-bias-engine.md`
- **Pivot data collection schedule** — See `docs/specs/pivot-data-collector.md`
- **Factor scoring formulas** — See `docs/specs/factor-scoring.md`
- **Bias frontend rebuild** — See `docs/specs/bias-frontend.md`
