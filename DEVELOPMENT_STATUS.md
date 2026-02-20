# Pivot — Development Status & Roadmap

**Last Updated:** February 20, 2026

This is the single source of truth for what has been built, what's in progress, and what's planned. Agents should read this before starting any work to avoid rebuilding existing features or building on assumptions about unbuilt ones.

---

## ⚡ Pivot II Migration (COMPLETED Feb 20, 2026)

The original Pivot Discord bot (`pivot-bot`) has been **stopped and disabled**. All chat, briefs, and trade alerts now run through **Pivot II (OpenClaw)**.

### Current VPS Services

| Service | Status | Purpose |
|---------|--------|---------|
| `openclaw` | **active** | Pivot II — Discord chat, briefs, trade poller, twitter sentiment |
| `pivot-collector` | **active** | Data collection crons (factors, VIX, CAPE, sector strength). No LLM. |
| `pivot-bot` | **inactive, disabled** | OLD bot. Do not restart. |

### What Pivot II Handles

- **Discord chat** in #pivot-chat (Haiku 3.5 default, Sonnet 4.6 for heavy analysis)
- **Morning brief** (9:45 ET) via `pivot2_brief.py` — Sonnet 4.6
- **EOD brief** (16:30 ET) via `pivot2_brief.py` — Sonnet 4.6
- **Morning/EOD prep pings** (9:15/16:15 ET) via `pivot2_prep_ping.py`
- **Trade idea poller** (every 2 min market hours) via `pivot2_trade_poller.py` — no LLM, polls Railway API
- **Twitter sentiment** (every 30 min market hours) via `pivot2_twitter.py` — Haiku 3.5
- **Weekly data audit** (Saturday 16:00 UTC)
- **Memory + knowledge base** system with session state
- **Screenshot extraction** → SESSION-STATE.md (context window optimization)

### OpenClaw Cron Jobs

| Job | Schedule (ET) | Script |
|-----|--------------|--------|
| `pivot2-morning-prep-ping` | 9:15 M-F | `pivot2_prep_ping.py --mode morning` |
| `pivot2-morning-brief` | 9:45 M-F | `pivot2_brief.py --mode morning` |
| `pivot2-eod-prep-ping` | 16:15 M-F | `pivot2_prep_ping.py --mode eod` |
| `pivot2-eod-brief` | 16:30 M-F | `pivot2_brief.py --mode eod` |
| `pivot2-trade-poller` | */2 9-16 M-F | `pivot2_trade_poller.py` |
| `pivot2-twitter-sentiment` | */30 9-16 M-F | `pivot2_twitter.py` |
| `weekly-data-audit` | Sat 16:00 UTC | Agent-driven |

### Key Files (VPS)

- OpenClaw config: `/home/openclaw/.openclaw/openclaw.json`
- OpenClaw cron: `/home/openclaw/.openclaw/cron/jobs.json`
- Scripts: `/opt/openclaw/workspace/scripts/`
- Agent docs: `/opt/openclaw/workspace/AGENTS.md`, `IDENTITY.md`, `SOUL.md`, etc.
- Trade poller state: `/opt/openclaw/workspace/data/seen_signal_ids.json`
- Zone shift state: `/opt/openclaw/workspace/data/last_zone_shift.json`

### Not Yet Migrated

- **UW channel monitoring/parsing** — Old bot watched UW Premium Bot channels, parsed embeds, forwarded to Pandora API. Needs lightweight watcher bot (no LLM).
- **Whale alerts forwarding** — Old bot watched #whale-alerts. Bundle with UW watcher.
- **UW scheduled commands** — `/market_tide`, `/sectorflow`, etc. sent to UW bot at set times. Low priority.

### Runtime Note

`GET /api/signals/active` times out intermittently from VPS. Trade poller includes fallback to `/signals/queue`.

---

## CTA Scanner Audit (COMPLETED Feb 20, 2026)

18 critical bugs fixed across 5 phases (PRs #8–#12). All merged and deployed.

| Phase | PR | What Fixed |
|-------|----|-----------|
| 1: Scorer Integrity | #8 | Removed RECOVERY references, added missing base scores, fixed RSI/zone bonus contamination |
| 2: Selection Pipeline | #9 | Added DB persistence before selection, fixed top-N bias, added per-ticker dedup |
| 3: Outcome Tracking | #10 | Fixed signal_id matching, added price_at_signal capture, wired outcome tracking to webhooks |
| 4: Backtest Fidelity | #11 | Native stop/target mode using signal's own levels instead of synthetic percentages |
| 5: Structural Cleanup | #12 | Zone downgrade detector, short signal gating, confluence scoring moved to scorer, 20 unit tests |

Key result: DEATH_CROSS, BEARISH_BREAKDOWN, RESISTANCE_REJECTION signals now run in production for first time.

---

## Phase 2: Pivot Discord Bot (Core Features)

### ✅ Phase 2A: Playbook Integration
**What:** Integrated Playbook v2.1 into `pivot/llm/prompts.py` so the LLM has full trading rules, risk parameters, account details, and strategy specs in its system prompt.

**Key files:** `pivot/llm/prompts.py`, `pivot/llm/playbook_v2.1.md`

**What Playbook v2.1 contains:**
- Three-tier account structure (Robinhood ~$4,698, 401k BrokerageLink ~$8,100, Breakout prop $25K eval)
- Tiered Circuit Breaker system (SPY %, VIX levels)
- Risk rules: 5% max per trade, 2 correlated positions max
- Options strategies: credit spreads, debit spreads, shares
- Flow analysis rules for UW and dark pool signals
- Macro worldview context (bearish Trump admin, bullish AI disruption)
- Autonomous trading sandbox rules (Coinbase ~$150)

---

### ✅ Phase 2B: Trade Journal
**What:** SQLite trade journal on VPS + PostgreSQL on Railway for logging trades, tracking P&L, and Breakout prop account monitoring.

**Key files:** Journal DB at `/opt/pivot/data/journal.db` (VPS)

**Tables:** `trades`, `trade_notes`, `defcon_events`, `breakout_snapshots`

**Features:**
- Log trades via Discord with confirmation flow
- Track open/closed status, P&L, entry/exit prices
- Breakout prop HWM and drawdown floor tracking
- Origin tracking (manual, UW flow, whale signal, etc.)

---

### ✅ Phase 2C: DEFCON Behavioral Layer
**What:** Behavioral monitoring system that evaluates market conditions and tells Nick what ACTION to take (vs circuit breaker which adjusts scoring algorithmically).

**Key files:** `pivot/monitors/defcon.py` (designed), wired into `pivot/scheduler/cron_runner.py`

**Levels:**
- 🟢 GREEN — Normal operations
- 🟡 YELLOW — Pause 15-30 min (1 signal fires)
- 🟠 ORANGE — No new trades, tighten stops (2+ signals or 1 orange-level event)
- 🔴 RED — Flatten everything (3+ signals or 1 red-level event)

**Signal sources:** Circuit breaker state, VIX level/term structure, TICK breadth, Breakout proximity, SPY decline %

---

### ✅ Phase 2D: On-Demand Market Data Tools
**What:** Market data context injection so Pivot can answer questions about current prices, VIX, sector performance, etc.

**Sources:** yfinance for equities/VIX, bias composite from Railway API, factor states

---

### ✅ Phase 2E: Interactive Discord Chat
**What:** Full conversational interface in #pivot-chat via Pivot II (OpenClaw).

**Capabilities:**
- Natural language market analysis (Haiku 3.5 default, Sonnet 4.6 for deep analysis)
- Screenshot parsing and extraction to SESSION-STATE.md
- Trade idea evaluation with 9-point check
- Signal type differentiation (Whale Hunter vs UW flow vs manual)
- Market context injection (current bias, recent signals, factor states)
- Memory system with knowledge base
- Morning and EOD brief generation (Sonnet 4.6)

---

### 🔨 Phase 2F: UW Dashboard Scraping (NOT STARTED)
**What:** Structured data extraction from Unusual Whales web dashboard API.

**Goal:** Replace manual screenshot analysis with automated API calls for options flow data, dark pool prints, and sector flow heat maps.

**Status:** Brief not yet written. Depends on UW API access investigation.

---

### 🔨 Phase 2G: Auto-Scout (NOT STARTED)
**What:** Automated screening of UW flow + Alpha Feed ideas to generate options picks delivered to Discord.

**Goal:** Pivot independently screens incoming flow data, identifies high-conviction setups matching the Playbook criteria, and posts formatted trade ideas with full evaluation.

**Status:** Brief not yet written. Depends on Phase 2F for structured UW data.

---

## Analytics System (Separate Track)

### ✅ Analytics Phase 1: Data Collection Schema
**What:** PostgreSQL tables for signal tracking, trade logging, factor history, and price data.

**Tables:** `signals`, `trades`, `signal_outcomes`, `factor_history`, `price_history`, `strategy_health`, `health_alerts`, `convergence_events`

**Additional schema (from Phase 1 Addendum):**
- `trade_legs` — multi-leg and scaling support
- `benchmarks` — SPY buy-and-hold, bias-follow strategy comparison
- `portfolio_snapshots` — correlated risk tracking
- Calendar fields on signals: `day_of_week`, `hour_of_day`, `is_opex_week`, `days_to_earnings`

### ✅ Analytics Phase 2: API Endpoints
**What:** REST API layer powering the analytics UI and Pivot's database queries.

**Endpoints:**
- `GET /api/analytics/signal-stats` — accuracy, MFE/MAE, breakdowns by regime/day/hour
- `GET /api/analytics/trade-stats` — win rate, P&L, Sharpe, Sortino, drawdown, by account/structure
- `GET /api/analytics/factor-performance` — factor accuracy, correlation matrix, staleness
- `GET /api/analytics/strategy-comparison` — grade strategies, convergence pairs
- `GET /api/analytics/convergence-stats` — when multiple sources agree
- `GET /api/analytics/portfolio-risk` — exposure, correlated positions, net delta
- `POST /api/analytics/backtest` — simulated equity curve from historical signals + price data
- `GET /api/analytics/schema-status` — table row counts and job statuses

### ✅ Analytics Phase 3: UI
**What:** 6-tab analytics interface in `frontend/analytics.js`.

**Tabs:**
1. **Dashboard** — strategy health cards, equity curve, key metrics, active alerts
2. **Trade Journal** — filterable table, trade logging form, P&L summary, origin tags
3. **Signal Explorer** — signal table with filters, dynamic stats panel, MFE/MAE histograms
4. **Factor Lab** — dual-axis factor timeline, correlation matrix heatmap, factor stats
5. **Backtest** — parameter form, simulated equity curve, trade-by-trade results
6. **Risk** — account cards, exposure charts, correlation risk

---

## Codex Briefs In Progress

These upgrades have been specified as markdown briefs and handed to Codex for implementation:

| # | Brief | Priority | Status |
|---|-------|----------|--------|
| 1 | SPY price feed fix (yfinance split-unadjusted data) | URGENT | Implemented in code (deploy verification pending) |
| 2 | Factor freshness indicator in EOD brief | HIGH | Deployed to Codex |
| 3 | Convergence summary in EOD brief | HIGH | Deployed to Codex |
| 4 | UW screenshot request scheduler (10AM, 3PM, 4:05PM ET) | MEDIUM | Deployed to Codex |
| 5 | DXY macro factor (low weight) | MEDIUM | Deployed to Codex |
| 6 | RVOL conviction modifier for Whale Hunter | MEDIUM | Deployed to Codex |
| 7 | TICK-Whale cross-reference | LOW | Deployed to Codex |
| 8 | Robinhood trade import (CSV parser, signal matching) | MEDIUM | Deployed to Codex |

---

## Not Yet Built

- **UW watcher bot:** Lightweight service to monitor UW/whale Discord channels and forward parsed data to Pandora API (no LLM needed, replaces old bot's channel monitoring)
- **Phase 2F:** UW dashboard API scraping
- **Phase 2G:** Auto-scout (screen UW flow → generate options picks)
- **Crypto sandbox:** Autonomous trading on Coinbase (~$150 account)
- **Broker API integration:** Automated execution (Robinhood API)
- **Complex multi-leg tracking:** Iron condors, butterflies (trade_legs table exists but not wired)
- **Learning Protocol:** Self-correcting system where Pivot tracks its own recommendation accuracy and adjusts confidence/weighting (designed but not implemented)

---

## Key System Components Already Built

### Bias Engine (`backend/bias_engine/`)
20+ factors across MACRO, TECHNICAL, FLOW, and BREADTH categories. Each scores -2 to +2. Composite weighted average maps to 5-level system: URSA MAJOR → URSA MINOR → NEUTRAL → TORO MINOR → TORO MAJOR.

### Circuit Breaker (`backend/webhooks/circuit_breaker.py`)
TradingView alerts trigger automatic bias overrides during extreme market events (SPY -1%/-2%, VIX spikes). Adjusts scoring modifiers and bias caps/floors algorithmically.

### Scout Early Warning
15-minute timeframe TradingView alerts with automatic expiration. Posts early warnings to Discord before confirming on higher timeframes.

### Whale Hunter (Dark Pool Detection)
PineScript indicator on TradingView detects institutional absorption patterns via volume footprint analysis — consecutive bars with matched total volume and Point of Control (POC) levels. Sends webhooks to Railway → evaluated by LLM → posted to Discord.

### UW Flow Parser (`backend/discord_bridge/uw/`)
Monitors Unusual Whales Premium Bot Discord channels. Parses flow alerts into structured signals with filtering (min DTE 7, max DTE 180, min premium $50K, min score 80 for alerts).

### Collectors (`pivot/collectors/`)
Scheduled data fetchers: VIX term structure, credit spreads, sector rotation, TICK breadth, market breadth, dollar smile, CAPE yield, Savita indicator. Run on cron via `scheduler/cron_runner.py`. Morning/EOD briefs disabled (Pivot II handles these now).

### Monitors (`pivot/monitors/`)
Alert monitors: bias shift detection, CTA zone proximity, factor velocity (rapid changes), volume anomalies, earnings calendar, economic calendar.

---

## Known Issues (as of Feb 20, 2026)

- ⚠️ **`/api/signals/active` timeout from VPS**: Endpoint times out intermittently. Trade poller includes fallback to `/signals/queue`.
- ⚠️ **SPY price feed verification pending**: Guardrails were added in `backend/bias_engine/factor_utils.py` (live quote validation + fallback), but production deployment/runtime verification is still required.
- ⚠️ **Stale factors**: options_sentiment, put_call_ratio, and savita_indicator have reliability issues. EOD brief doesn't indicate which are fresh vs stale yet.
- ⚠️ **Analytics tables mostly empty**: System deployed but needs signal accumulation time and trade imports to populate meaningful data.
- ⚠️ **Trade journal has no historical data**: Robinhood import system designed but not built yet.
- ⚠️ **Signal persistence verification pending**: DB-first persistence guardrails were added (webhooks + schedulers) to prevent Redis-only signals, but production runtime verification is still required.
- ⚠️ **UW channel monitoring paused**: Old bot handled UW/whale channel parsing. Needs lightweight watcher replacement.

---

## Nick's Trading Context

**Accounts:**
| Account | Balance | Max Risk/Trade | Notes |
|---------|---------|----------------|-------|
| Robinhood | ~$4,698 | $235 (5%) | Primary options trading |
| 401k BrokerageLink | ~$8,100 | Conservative | Long-term positions |
| Breakout Prop | $25K eval | $1,250/day (5%) | Step 1 active, HWM $25,158, floor $23,158 |
| Coinbase | ~$150 | Sandbox only | Pivot autonomous crypto learning |

**Biases (Pivot must challenge these):**
- Extremely bearish on Trump administration and US macro stability
- Bullish on AI disruption as a trade thesis
- Pivot's job is to present objective data that may contradict these views

**Working style:**
- Has ADHD — prefers step-by-step guidance broken into manageable chunks
- Non-engineer background — explain technical decisions simply
- Uses Claude.ai (Opus) for architecture/planning → writes markdown briefs → hands to Claude Code (Codex/Sonnet) for implementation
- Strongly opinionated trader who wants his system to push back on him
