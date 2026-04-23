# Pivot — Project Rules

**Last Updated:** March 15, 2026

## Prime Directive

**Automate everything possible so Nick can focus on trade execution only.**

No manual data entry, no mental math, no context-switching. If a human has to remember it or look it up repeatedly, it should be automated.

## Primary Goal

Real-time, actionable trade intelligence via Discord: automated data collection (20+ factors), clear trade evaluations (entry/exit/stop/conviction), bias challenge, multi-source convergence, and performance tracking.

## Review Teams

### Olympus (Trading Committee)
4-agent double-pass for trade strategy, signal pipeline, and bias engine changes.

| Agent | Role |
|-------|------|
| TORO | Bull analyst — finds reasons to take the trade |
| URSA | Bear analyst — finds reasons to pass |
| TECHNICALS | Risk/structure — entry/stop/target/sizing |
| PIVOT | Synthesizer — final recommendation with conviction level |

Runs inside Claude.ai conversations (not VPS API) to avoid costs.

### The Titans (Software Design Team)
4-agent double-pass for significant builds before any Brief goes to Claude Code.

| Agent | Role |
|-------|------|
| ATLAS | Backend architect (finance/scalability) |
| HELIOS | Frontend UI/UX |
| AEGIS | Security |
| ATHENA | PM — final decision, presents plan to Nick |

Workflow: Pass 1 → Pass 2 → ATHENA overview → Nick approval → Brief → Titans final review → Claude Code.

## Strategy Anti-Bloat Framework (Olympus-Ratified 2026-04-22)

All proposed strategy additions, Olympus reviews, and Titans briefs must comply with these rules. Source: `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` Pass 1 consensus.

### Core Classification

Every candidate strategy must be classified as one of:

- **REPLACES** — deprecates an existing signal
- **ELEVATES** — becomes a filter/gate on top of an existing signal
- **ADDS** — genuinely orthogonal edge (requires backtest proof)
- **REJECTED** — no clean case for inclusion

### Confluence Caps

- **Cash factors:** maximum of 3 per setup (ADX, price level, structure, etc.)
- **Derivatives factors:** maximum of 2 per setup (IV rank, skew, GEX, max pain) — ADDITIVE to the cash cap, not subject to it
- **4+ factor override:** setups with 4+ factors in a single layer require written orthogonality justification AND must pass a higher backtest bar (Sharpe > 1.0 vs. standard > 0.7)

### Filter Rules

- Filters must SUBTRACT signals, not add them
- Measurable rule: a filter is subtractive ONLY if it reduces weekly signal count by ≥30% while holding or improving expectancy
- Filters that redistribute signals across buckets without reducing total count are additive disguised as subtractive — reject

### ADD Requirements

- Every ADD is PROVISIONAL until backtest module validates it; shadow-mode acceptable in the interim
- Every ADD requires a named deprecation target (one-in-one-out is MANDATORY, not soft)
- Deprecations can be "banked" against future ADDs if Olympus identifies them outside the context of a specific new strategy

### Location-Quality Multiplier (PYTHIA)

All signals are graded against their trigger location relative to the value area:

- **At VA edge (extension zone):** grade +0.5
- **Mid-VA (chop zone):** grade -0.5
- **Use PRIOR-SESSION developing VA** at signal time — cumulative VA introduces lookahead bias

This multiplier is applied to grades in Olympus reviews and to scoring in the live pipeline.

### Sector-Rotation Regime Specification (THALES)

- Every ADD must declare which sector-rotation regimes it targets (concentrated leadership, rotation, or regime-agnostic)
- Backtest segments results by rotation state
- Signals firing in the wrong regime for their profile receive a 0.75x position-size penalty automatically

### Signal Enrichment at Trigger Time

Every signal emitted by any scanner/strategy must include:

- Sector-rotation state tag (via lookup against `sector_rs` scanner output)
- Auction state tag (balanced / one-timeframing / trend day) via PYTHIA
- Prior-session VA-relative context (inside / at edge / outside)
- IV rank (for options-structure selection, payload-only — not used as a filter by default)

### Grandfather Clause

Existing strategies at the time of ratification are grandfathered against the confluence cap. Strategies flagged in the 2026-04-22 review with factor counts at or above the cap:

- **`wh_reversal`** (4 factors: WH-ACCUMULATION + 5-day return + VAL proximity + flow sentiment) — under the new location-quality multiplier, VAL proximity is reclassified as a grade modifier (not a factor). Effective count: 3. Compliant.

Grandfathered strategies auto-surface for review at each Olympus cadence (quarterly minimum) regardless of performance grade, to verify framework compliance holds.

### Grade Decay Auto-Flag

Any strategy scoring below B- for 3 consecutive Olympus reviews → mandatory deprecation review.

## Development Principles

1. **Single source of truth** — Data in PostgreSQL, displayed in many places
2. **Fail visible** — If data is stale or missing, say so. Never silently use bad data.
3. **Bias toward action** — Ship incremental improvements over perfect plans
4. **Modular architecture** — New factors/signals/strategies plug in without rewriting core
5. **Brief-driven development** — Architecture in Claude.ai → markdown brief → Claude Code builds
6. **Empty-safe env vars** — `os.getenv("VAR") or default`, never `os.getenv("VAR", default)`
7. **Data source priority** — See Data Source Hierarchy below. Default to Polygon for all equities/ETFs.

## Data Source Hierarchy

When building any feature that needs market data, use these sources in this priority order. Never default to yfinance for equities when Polygon is available.

| Data Type | Primary Source | Fallback | Notes |
|-----------|---------------|----------|-------|
| **Equity/ETF daily bars** | Polygon `get_bars()` | yfinance | Polygon Stocks Starter ($29/mo), unlimited calls, 15-min delayed |
| **Equity/ETF snapshots** | Polygon `get_snapshot()` | yfinance | Current price, prev close, volume |
| **Options chains/greeks** | Polygon `polygon_options.py` | — | Options snapshot endpoint |
| **VIX, indices (^VIX, ^GSPC)** | yfinance | — | Polygon doesn't cover index symbols with `^` prefix |
| **Breadth data (^ADVN, ^DECLN)** | yfinance | — | NYSE advance/decline, not on Polygon |
| **Crypto (BTC, ETH)** | Binance/Coinalyze | yfinance | Futures data via `binance_futures.py` |
| **Macro (FRED series)** | FRED API | — | Interest rates, claims, yield curve |
| **Sector ETF performance** | Polygon `get_bars()` | yfinance | All 11 SPDR sectors — never rely on enrichment cache alone |
| **Options flow / unusual activity** | Unusual Whales (VPS watcher) | — | Parsed from Discord, not API |

**Key rules:**
- `backend/integrations/polygon_equities.py` has `get_bars()` and `get_snapshot()` — use them
- Polygon results are cached 5 min in-memory (`_bars_cache`, `_snapshot_cache`)
- yfinance is acceptable for indices/breadth that Polygon doesn't cover, and as a fallback when Polygon fails
- Never use the enrichment cache (`watchlist:enriched`) as the sole data source for a feature — it only covers tickers in the watchlist
- TradingView webhooks are for alerts/signals, not data fetching

## Bias Hierarchy

| Level | Name | Meaning |
|-------|------|---------|
| 5 | TORO MAJOR | Strongly bullish — full size longs |
| 4 | TORO MINOR | Lean bullish — reduced size |
| 3 | NEUTRAL | No bias — scalps or sit out |
| 2 | URSA MINOR | Lean bearish — reduced size |
| 1 | URSA MAJOR | Strongly bearish — full size shorts |

## Deployment Rules

- **Railway:** Auto-deploys on push to `main`. Postgres must be in SAME Railway project.
- **VPS:** SSH → edit → restart. No git repo on VPS.
- **One Discord bot instance only** (VPS). Never run a second on Railway.
- **Three VPS services:** `openclaw`, `pivot-collector`, `pivot2-interactions`.

## Workflow Rules

- Architecture → Claude.ai. Implementation → Claude Code. Codex is backup only.
- Significant builds → Titans review. Strategy/trading changes → Olympus review.
- New indicators → classify as MACRO/TECHNICAL/FLOW/BREADTH first.
- UI changes → get Nick's approval before building.
- Prompt changes → test after deploy (committee prompts are the system's brain).

## Agent Maintenance Protocol

| Change Type | Update |
|-------------|--------|
| New module/feature | `DEVELOPMENT_STATUS.md`, `CLAUDE.md` |
| New endpoint | `CLAUDE.md` reference docs |
| New factor/signal | `CLAUDE.md`, `PROJECT_RULES.md` if new category |
| Bug fix for known issue | `DEVELOPMENT_STATUS.md` |

**Rules:**
- Never describe planned features as built. Verify in code if unsure.
- Code is source of truth over docs. Fix docs when they contradict code.
- Document **why** not just **what** for architecture decisions.
