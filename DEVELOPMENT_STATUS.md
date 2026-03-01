# Pivot — Development Status & Roadmap

**Last Updated:** March 1, 2026

This is the single source of truth for what has been built, what's in progress, and what's planned. Agents should read this before starting any work to avoid rebuilding existing features or building on assumptions about unbuilt ones.

---

## ⚡ Pivot Migration (COMPLETED Feb 20, 2026)

The original Pivot Discord bot (`pivot-bot`) has been **stopped and disabled**. All chat, briefs, and trade alerts now run through **Pivot (OpenClaw)**.

### Current VPS Services

| Service | Status | Purpose |
|---------|--------|---------|
| `openclaw` | **active** | Pivot — Discord chat, briefs, trade poller, twitter sentiment |
| `pivot-collector` | **active** | Data collection crons (factors, VIX, CAPE, sector strength). No LLM. |
| `pivot2-interactions` | **active** | Committee button handler (Take/Pass/Watching clicks, re-eval modal) |
| `pivot-bot` | **inactive, disabled** | OLD bot. Do not restart. |

### What Pivot Handles

- **Discord chat** in #pivot-chat (Haiku 4.5 default, Sonnet 4.6 for heavy analysis)
- **Morning brief** (9:45 ET) via `pivot2_brief.py` — Sonnet 4.6
- **EOD brief** (16:30 ET) via `pivot2_brief.py` — Sonnet 4.6
- **Morning/EOD prep pings** (9:15/16:15 ET) via `pivot2_prep_ping.py`
- **Trade idea poller** (every 15 min market hours) via `pivot2_trade_poller.py` — no LLM, polls Railway API
- **Twitter sentiment** (every 30 min market hours) via `pivot2_twitter.py` — Haiku 4.5
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
| `pivot2-trade-poller` | */15 9-16 M-F | `pivot2_trade_poller.py` |
| `pivot2-twitter-sentiment` | */30 9-16 M-F | `pivot2_twitter.py` |
| `nightly-outcome-matcher` | 4:00 UTC daily | `committee_outcomes.py` |
| `saturday-weekly-review` | 16:00 UTC Sat | `committee_review.py` |
| `session-image-cleanup` | hourly | `session_image_cleanup.py` |
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
|-------|----|-----------:|
| 1: Scorer Integrity | #8 | Removed RECOVERY references, added missing base scores, fixed RSI/zone bonus contamination |
| 2: Selection Pipeline | #9 | Added DB persistence before selection, fixed top-N bias, added per-ticker dedup |
| 3: Outcome Tracking | #10 | Fixed signal_id matching, added price_at_signal capture, wired outcome tracking to webhooks |
| 4: Backtest Fidelity | #11 | Native stop/target mode using signal's own levels instead of synthetic percentages |
| 5: Structural Cleanup | #12 | Zone downgrade detector, short signal gating, confluence scoring moved to scorer, 20 unit tests |

Key result: DEATH_CROSS, BEARISH_BREAKDOWN, RESISTANCE_REJECTION signals now run in production for first time.

---

## Brief 10: Unified Position Ledger (COMPLETED Feb 26, 2026)

Replaced 3 fragmented position tables (`positions`, `open_positions`, `options_positions`) with a single `unified_positions` table. Full v2 positions API (10 endpoints), options-aware frontend, and committee context integration.

### What's Built

- **Unified positions table** — Single table with fields for equities AND options (structure, strikes, expiration, greeks)
- **v2 Positions API (10 endpoints):**
  - `POST /v2/positions` — Create with duplicate check + committee linkage
  - `GET /v2/positions` — List with account/status/ticker filters
  - `GET /v2/positions/{id}` — Single position detail
  - `PUT /v2/positions/{id}` — Update position
  - `POST /v2/positions/{id}/close` — Close with P&L classification
  - `DELETE /v2/positions/{id}` — Soft delete
  - `POST /v2/positions/sync` — Bulk sync (partial flag for RH screenshots vs IBKR full sync)
  - `GET /v2/positions/summary` — Portfolio summary (balance, at-risk %, lean, nearest DTE)
  - `GET /v2/positions/greeks` — Per-ticker and aggregate portfolio greeks via Polygon
  - `POST /v2/positions/bulk-import` — Bulk import from screenshots
- **Position risk calculator** — Common options structures (debit/credit spreads, single legs, covered calls)
- **Options-aware frontend** — Structure badges, strikes+DTE display, max loss progress bars
- **Portfolio summary widget** — Balance, at-risk %, directional lean, nearest DTE in bias row
- **Committee context integration** — v2 summary injected into TORO/URSA/Risk/Pivot context (fallback to v1)
- **Pivot position manager skill** — VPS CLI for position CRUD
- **Data migration script** — Migrates from old tables to unified schema
- **Mark-to-market** — Polygon.io for options spreads (actual bid/ask mid-prices), yfinance fallback for equities
- **IBKR cron activation** — `ibkr-position-poller` (*/5 min), `ibkr-quotes-poller` (*/1 min)

### Position Tracking Details

- `signal_id` + `account` columns on positions for committee linkage and multi-account tracking
- Partial sync flag: `partial=true` reports `possibly_closed` without auto-closing (RH screenshots), `partial=false` auto-closes missing positions (IBKR full sync)
- `closed_positions` table with full P&L schema (pnl_dollars, pnl_percent, hold_days)
- Committee TAKE button saves `last_take.json`, prompts Nick for fill screenshot

---

## Polygon.io Integration (COMPLETED Feb 27, 2026)

Two Polygon.io Starter plans ($29/mo each) provide real market data for options and equities.

### Options ($29/mo — Options Starter)
- **`polygon_options.py` client** — Chain snapshots, contract matching, spread valuation, greeks extraction
- **Mark-to-market** — Actual bid/ask mid-prices for spread legs (replaces broken stock-price-only math)
- **Spread support** — Debit spreads, credit spreads, single-leg options
- **Portfolio greeks** — Delta, gamma, theta/day, vega per-ticker and aggregate
- **5-min in-memory cache** — Minimizes API calls within rate limits
- **NTM-filtered queries** — Fetches only near-the-money contracts (±10% SPY price) instead of full chains (5-10 contracts vs 2,500+)
- **Starter plan workarounds** — `day.close` + `day.vwap` fallback when `last_quote` missing; `implied_volatility` not populated so VIX used for iv_regime factor

### Stocks ($29/mo — Stocks Starter)
- **Primary data source** for ETF/equity tickers (SPY, QQQ, sector ETFs)
- **yfinance kept as fallback** for when Polygon is down or rate-limited
- **VIX/index tickers stay on yfinance** (not available on Polygon Stocks Starter)
- **Polygon-first routing** in data layer with transparent fallback

### New Bias Factors Using Polygon
- `polygon_oi_ratio` — SPY put/call open interest ratio from Polygon snapshots
- `polygon_pcr` — Automated SPY put/call volume ratio (contrarian scoring, 15-min delayed)
- `iv_regime` — Uses VIX as SPY 30-day IV proxy, computes IV rank vs 20-day history via Redis sorted set

---

## Bias System Overhaul (COMPLETED Feb 27, 2026)

Two-tier overhaul driven by Opus committee review (TORO/URSA/TECHNICALS agents).

### Tier 1 — Bug Fixes & Scoring Corrections
- `options_sentiment` + `put_call_ratio`: return `None` instead of `0.0` neutral fallback when no data (prevents dilution during selloffs)
- ISM Manufacturing: swap FRED series order to MANEMP (NAPM removed from FRED in 2016)
- TICK breadth: fix `elif→if` for extreme modifier (volatile wide-range days were netting out)
- Circuit breaker integrated into `compute_composite()`: scoring modifier, bias cap/floor, metadata
- VIX regime: VIX 18-20 scores -0.1 (was 0.0), VIX 20+ scores -0.3 (was -0.2)
- `score_to_bias()` asymmetry fixed: URSA_MAJOR threshold -0.60 (was -0.59)
- Factor weights normalized to exactly 1.00
- Redis TTL bug: long-lived factors (Savita 1080h, ISM 720h) get per-factor TTL instead of hardcoded 24h
- Redis stale key cleanup: delete Redis key when `compute_score()` returns None (prevents ghost 0.0 readings)

### Tier 2 — Factor Restructure
- **22 factors total** across INTRADAY (5), SWING (9), MACRO (8)
- **Removed 4 dead/unreliable:** iv_skew, breadth_momentum, options_sentiment, dollar_smile
- **Added 3 new:** breadth_intraday (TradingView $UVOL/$DVOL webhook), polygon_oi_ratio, iv_regime
- **Merged:** dollar_smile VIX logic into dxy_trend (8 DXY+VIX combinations)
- **Self-heal:** put_call_ratio via Polygon PCR fallback when primary source fails
- **Rebalanced weights:** intraday 0.28, swing 0.41, macro 0.31 = 1.00 (was 1.12)
- **Working flow weight:** 0.10 (up from 0.04)
- **Weight sum assertion** guardrail at import time
- `/webhook/breadth` endpoint for $UVOL/$DVOL TradingView alerts

### RVOL Conviction Modifier
- Asymmetric amplification: bearish signals 1.20x, bullish 1.10x, low-vol dampening 0.85x
- Hysteresis (activate at 1.5, deactivate at 1.2), 60-min cache
- Confidence gate + dead zone guardrails

### Circuit Breaker Overhaul
- **Condition-verified decay** (NOT pure time-based) — timer AND condition must clear
- **State machine:** active → pending_reset → Nick accepts/rejects via dashboard → inactive
- **No-downgrade guard:** spy_down_1pct can't overwrite spy_down_2pct
- **Discord webhook notifications** (DISCORD_WEBHOOK_CB env var)
- **Dashboard:** accept/reject buttons with amber pending-reset banner
- **Fix:** spy_up_2pct modifier direction (additive, not multiplicative)

---

## Committee Training Bible + v2 Prompts (COMPLETED Mar 1, 2026)

Two-part upgrade to the Trading Team committee system:

### Training Bible (`docs/committee-training-parameters.md`)
Comprehensive 89-rule reference document organized into 12 sections: Market Structure (M), Flow Analysis (F), Chart/Technical (C), Volume Profile (V), Execution (E), Risk Management (R), Bias System (B), dpg Convexity Philosophy (P), Approved Strategies (S), Playbook Risk Rules (K), Levels/Tools (L), Decision Framework (D). Consolidates all trading knowledge into a single citable reference that agents use by rule number.

### v2 Agent Prompts (`committee_prompts.py`)
All four committee agents rewritten to cite Bible rules by section/rule number instead of inlining education:
- **TORO:** -28% lines (85→61). Bull case analysis with rule citations (M.04, F.01-02, C.01-04, B.01-02)
- **URSA:** -9% lines (75→68). Bear case + explicit B.06 bias challenge duty (flag AI-bull, macro-bear tendencies)
- **TECHNICALS:** +11% lines (90→100). Scope expanded to hybrid technical+risk role — now owns entry/stop/target/R:R/structure/size calculations (previously split with PIVOT). References Nick's charting setup (L.06: EMA 9/20/55, SMA 50/120/200, Rolling VWAPs)
- **PIVOT:** -35% lines (130→84). No longer calculates levels/sizing from scratch — validates or adjusts TECHNICALS' output. Still owns final TAKE/PASS/WATCHING decision with conviction level

Net result: 384→325 lines (-15%). Agents now produce analysis grounded in specific, citable rules rather than vague heuristics.

### Previous: dpg/GEX Convexity Training (Feb 27, 2026)
All four agents previously retrained with dpg's convexity-first options philosophy (debit > credit default, fractional Kelly sizing, asymmetric payoff focus). The Training Bible codifies these principles as persistent rules rather than prompt-inlined education.

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

---

### ✅ Phase 2C: DEFCON Behavioral Layer
**What:** Behavioral monitoring system that evaluates market conditions and tells Nick what ACTION to take (vs circuit breaker which adjusts scoring algorithmically).

**Levels:**
- 🟢 GREEN — Normal operations
- 🟡 YELLOW — Pause 15-30 min (1 signal fires)
- 🟠 ORANGE — No new trades, tighten stops (2+ signals or 1 orange-level event)
- 🔴 RED — Flatten everything (3+ signals or 1 red-level event)

---

### ✅ Phase 2D: On-Demand Market Data Tools
**What:** Market data context injection. Sources: Polygon.io for equities/options, yfinance fallback, bias composite from Railway API, factor states.

---

### ✅ Phase 2E: Interactive Discord Chat
**What:** Full conversational interface in #pivot-chat via Pivot (OpenClaw).

---

### 🔨 Phase 2F: UW Dashboard Scraping (NOT STARTED)
**What:** Structured data extraction from Unusual Whales web dashboard API.
**Status:** Brief not yet written. Depends on UW API access investigation.

---

### 🔨 Phase 2G: Auto-Scout (NOT STARTED)
**What:** Automated screening of UW flow + Alpha Feed ideas to generate options picks.
**Status:** Brief not yet written. Depends on Phase 2F.

---

## Analytics System (Separate Track)

### ✅ Analytics Phase 1: Data Collection Schema
**Tables:** `signals`, `trades`, `signal_outcomes`, `factor_history`, `price_history`, `strategy_health`, `health_alerts`, `convergence_events`, `trade_legs`, `benchmarks`, `portfolio_snapshots`, `unified_positions`, `closed_positions`

### ✅ Analytics Phase 2: API Endpoints
**Endpoints:** `/api/analytics/signal-stats`, `/api/analytics/trade-stats`, `/api/analytics/factor-performance`, `/api/analytics/strategy-comparison`, `/api/analytics/convergence-stats`, `/api/analytics/portfolio-risk`, `/POST /api/analytics/backtest`, `/api/analytics/schema-status`

### ✅ Analytics Phase 3: UI
**Tabs:** Dashboard, Trade Journal, Signal Explorer, Factor Lab, Backtest, Risk

---

## Key System Components Already Built

### Bias Engine (`backend/bias_engine/`)
22 factors across INTRADAY (5), SWING (9), and MACRO (8) categories. Each scores -1.0 to +1.0. Composite weighted average maps to 5-level system: URSA MAJOR → URSA MINOR → NEUTRAL → TORO MINOR → TORO MAJOR. Weights sum to 1.00 (enforced by assertion at import time). **Polygon.io is primary data source** for equities/ETFs/options; yfinance is fallback. VIX/index tickers use yfinance directly.

**Data sources:** Polygon.io Options Starter (options chains, greeks, OI, volume), Polygon.io Stocks Starter (ETF/equity prices), yfinance (VIX, indices, fallback), FRED (credit spreads, yield curve, claims, ISM), TradingView webhooks (TICK breadth, $UVOL/$DVOL, circuit breaker), Twitter sentiment (30+ accounts via `pivot2_twitter.py`).

**Tier 2 Overhaul (Feb 27, 2026):** Opus committee review (TORO/URSA/TECHNICALS agents) drove a full factor cleanup. Removed 4 dead/unreliable factors (iv_skew, breadth_momentum, options_sentiment, dollar_smile). Added 3 new factors (breadth_intraday, polygon_oi_ratio, iv_regime). Merged dollar_smile VIX logic into dxy_trend. Added RVOL conviction modifier with asymmetric amplification, hysteresis, confidence gate, dead zone. Self-healing put_call_ratio via Polygon fallback. Working flow weight increased from 4% to 10%.

### Circuit Breaker (`backend/webhooks/circuit_breaker.py`)
TradingView alerts trigger automatic bias overrides during extreme market events (SPY -1%/-2%, VIX spikes). Condition-verified decay with state machine (active → pending_reset → accepted/rejected). No-downgrade guard. Discord webhook notifications. Dashboard accept/reject buttons with amber pending-reset banner. Integrated into `compute_composite()` as scoring modifier + bias cap/floor.

### Position Ledger (`backend/api/v2_positions.py` + `backend/positions/`)
Unified position tracking for all accounts (RH, IBKR, 401k). Options-aware with structure detection (debit/credit spreads, single legs). Mark-to-market via Polygon options API (bid/ask mid-prices for spreads) with yfinance fallback for equities. Portfolio greeks (delta, gamma, theta, vega). Committee context integration.

### Committee Training Bible (`docs/committee-training-parameters.md`)
89-rule reference document across 12 sections. All committee agents cite rules by number (e.g., "Per M.04, this sweep-and-reclaim..."). Consolidates trading knowledge from playbook, approved strategies, dpg philosophy, and bias system into a single citable source. TECHNICALS agent owns risk parameter calculations; PIVOT validates/adjusts.

### Scout Early Warning
15-minute timeframe TradingView alerts with automatic expiration. Posts early warnings to Discord before confirming on higher timeframes.

### Whale Hunter (Dark Pool Detection)
PineScript indicator on TradingView detects institutional absorption patterns via volume footprint analysis. Sends webhooks to Railway → evaluated by LLM → posted to Discord.

### UW Flow Parser (`backend/discord_bridge/uw/`)
Monitors Unusual Whales Premium Bot Discord channels. Parses flow alerts into structured signals with filtering (min DTE 7, max DTE 180, min premium $50K, min score 80 for alerts).

### Collectors (`pivot/collectors/`)
Scheduled data fetchers: VIX term structure, credit spreads, sector rotation, TICK breadth, market breadth, CAPE yield, Savita indicator. Run on cron via `scheduler/cron_runner.py`.

### Monitors (`pivot/monitors/`)
Alert monitors: bias shift detection, CTA zone proximity, factor velocity (rapid changes), volume anomalies, earnings calendar, economic calendar.

---

## Frontend Fixes (Feb 27, 2026)

Batch of UI bug fixes deployed:

- **Position modal overlay** — Root cause: `.signal-modal-overlay` had `display:flex` by default with no hidden state, creating an invisible overlay that blocked the page after first close. Fixed: `display:none` default + `.active` class toggle.
- **Signal card HTML corruption** — Root cause: `data-signal` attribute used single-quote delimiters; signal data with `<`, `>`, `&` broke HTML parser (zero computed height). Fixed: `encodeURIComponent`/`decodeURIComponent` for data attributes.
- **Signal card height** — Removed `overflow:hidden` from KODIAK_CALL and APIS_CALL cards that was clipping content.
- **P&L display** — Consistent +$X.XX (green) / -$X.XX (red) formatting across all 3 position rendering locations.
- **Custom structure support** — iron_butterfly, straddle, strangle, plus free-text "Custom" in position modals.
- **Edit modal falsy zero bug** — Values of `0` were silently dropped (`if(0)` is falsy); now checks string emptiness.
- **Timeframe labels** — Frontend uses API-computed `bias_level` directly instead of vote-based conversion (too-wide NEUTRAL range). Score display shows `sub_score` value.
- **Momentum delta threshold** — Lowered from 0.05 to 0.03 (weighted sub_scores range ~-0.3 to +0.3).
- **CSS cache busting** — v38→v39 (Polygon factors), app.js v53→v54 (timeframe labels).

---

## Codex Briefs Status

| # | Brief | Priority | Status |
|---|-------|----------|--------|
| 1 | SPY price feed fix | URGENT | ✅ Deployed |
| 2 | Factor freshness in EOD brief | HIGH | Deployed to Codex |
| 3 | Convergence summary in EOD brief | HIGH | Deployed to Codex |
| 4 | UW screenshot request scheduler | MEDIUM | Deployed to Codex |
| 5 | DXY macro factor | MEDIUM | ✅ Merged into dxy_trend (Tier 2 overhaul) |
| 6 | RVOL conviction modifier | MEDIUM | ✅ Deployed (Tier 2 overhaul) |
| 7 | TICK-Whale cross-reference | LOW | Deployed to Codex |
| 8 | Robinhood trade import | MEDIUM | Deployed to Codex |

---

## Not Yet Built

- **UW watcher bot:** Lightweight service to monitor UW/whale Discord channels and forward parsed data to Pandora API (no LLM needed)
- **Phase 2F:** UW dashboard API scraping
- **Phase 2G:** Auto-scout (screen UW flow → generate options picks)
- **Crypto sandbox:** Autonomous trading on Coinbase (~$150 account)
- **Broker API integration:** Automated execution (Robinhood API). IBKR currently read-only monitoring.
- **Complex multi-leg tracking:** Iron condors, butterflies (`trade_legs` table exists but not wired)
- **Learning Protocol:** Self-correcting system where Pivot tracks recommendation accuracy and adjusts confidence/weighting
- **Brief 05B:** Adaptive Calibration — dynamic thresholds + agent trust weighting (needs ~3 weeks outcome data)
- **Brief 07:** Watchlist Re-Scorer
- **Brief 08-09:** Librarian Phase 1+2 (Knowledge Base + Agent Training Loop)

---

## Known Issues (as of Feb 27, 2026)

- ⚠️ **`/api/signals/active` timeout from VPS**: Endpoint times out intermittently. Trade poller includes fallback to `/signals/queue`.
- ⚠️ **Analytics tables mostly empty**: System deployed but needs signal accumulation time and trade imports to populate meaningful data.
- ⚠️ **Trade journal has no historical data**: Robinhood import system designed but not built yet.
- ⚠️ **UW channel monitoring paused**: Old bot handled UW/whale channel parsing. Needs lightweight watcher replacement.
- ⚠️ **IBKR account not funded**: Position poller crons are active but IBKR gateway won't authenticate until account is funded. Read-only API user setup pending.
- ⚠️ **Polygon Starter plan limitations**: `last_quote` not always populated (use `day.close`/`day.vwap` fallback), `implied_volatility` field empty (use VIX as SPY IV proxy).
- ✅ **Stale factors resolved (Feb 27)**: options_sentiment removed. put_call_ratio self-heals via Polygon fallback. savita_indicator staleness window extended. Redis TTL per-factor.
- ✅ **SPY price feed fixed**: Guardrails + Polygon-first routing deployed.
- ✅ **Signal persistence hardened**: DB-first persistence enforced across webhooks + schedulers.
- ✅ **Savita persistence fixed (Feb 25)**: PUT endpoint now writes to composite engine via `record_factor_reading()`, recomputes composite bias.

---

## Nick's Trading Context

**Accounts:**
| Account | Balance | Max Risk/Trade | Notes |
|---------|---------|----------------|-------|
| Robinhood | ~$4,698 | $235 (5%) | Primary options trading |
| 401k BrokerageLink | ~$8,100 | Conservative | Long-term positions |
| Breakout Prop | $25K eval | $1,250/day (5%) | Step 1 active, HWM $25,158, floor $23,158 |
| Coinbase | ~$150 | Sandbox only | Pivot autonomous crypto learning |
| IBKR | Not funded | N/A | Pending setup — read-only monitoring planned |

**Biases (Pivot must challenge these):**
- Extremely bearish on Trump administration and US macro stability
- Bullish on AI disruption as a trade thesis
- Pivot's job is to present objective data that may contradict these views

**Working style:**
- Has ADHD — prefers step-by-step guidance broken into manageable chunks
- Non-engineer background — explain technical decisions simply
- Uses Claude.ai (Opus) for architecture/planning → writes markdown briefs → hands to Claude Code (Codex/Sonnet) for implementation
- Strongly opinionated trader who wants his system to push back on him
