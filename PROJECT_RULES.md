# Pivot — Project Rules

**Last Updated:** April 27, 2026

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
7. **Data source priority** — See Data Source Hierarchy below. UW API is PRIMARY for all equities/ETFs/options.

## Data Source Hierarchy

When building any feature that needs market data, use these sources in this priority order. **Polygon.io and FMP are DEPRECATED — never add new dependencies on either.** UW API is the primary source for all market data.

| Data Type | Primary Source | Fallback | Notes |
|-----------|---------------|----------|-------|
| **Equity/ETF daily bars** | UW API `uw_api.get_bars()` | yfinance | Wraps yfinance for OHLCV; Bearer-token auth |
| **Equity/ETF snapshots** | UW API `uw_api.get_snapshot()` | yfinance | Real-time quotes, current price, prev close, volume |
| **Options chains/greeks** | UW API `uw_api.py` | — | `get_spread_value`, `get_single_option_value`, `get_multi_leg_value`, `get_ticker_greeks_summary` |
| **Options flow / unusual activity** | UW API `uw_api.get_flow_per_expiry()` | — | Real-time flow with $ premium, sweep detection |
| **IV rank / IV regime** | UW API `uw_api.get_iv_rank()` | — | Purpose-built percentile, prefer over computing from yfinance chain |
| **GEX / gamma exposure** | UW API `uw_api.get_greek_exposure()` | — | Already wired to bias engine |
| **Dark pool prints** | UW API `uw_api.get_darkpool_ticker()` | — | Real-time DP volume |
| **Max pain** | UW API `uw_api.get_max_pain()` | — | Per-expiry max pain levels |
| **VIX, indices (^VIX, ^GSPC)** | yfinance | — | UW doesn't cover index symbols with `^` prefix |
| **Breadth data (^ADVN, ^DECLN)** | yfinance / NYSE proxy | — | NYSE advance/decline, not on UW |
| **Crypto (BTC, ETH)** | Binance/Coinalyze | yfinance | Futures data via `binance_futures.py` |
| **Macro (FRED series)** | FRED API | — | Interest rates, claims, yield curve, ISM |
| **Sector ETF performance** | UW API `uw_api.get_snapshot()` | yfinance | All 11 SPDR sectors |
| **News headlines (per ticker)** | UW API `uw_api.get_news_headlines()` | — | Real-time news feed |
| **Insider transactions** | UW API `uw_api.get_insider_transactions()` | — | |
| **Congressional trades** | UW API `uw_api.get_congressional_trades()` | — | |
| **Economic calendar** | UW API `uw_api.get_economic_calendar()` | FRED | |

**Key rules:**
- `backend/integrations/uw_api.py` is the canonical client — use the helpers there, do not call UW endpoints directly elsewhere
- UW results are cached in Redis; respect existing TTLs and add new ones for new endpoints
- yfinance is acceptable ONLY for indices/breadth that UW doesn't cover, and as a fallback when UW fails
- **Never use the enrichment cache (`watchlist:enriched`) as the sole data source for a feature** — it only covers tickers in the watchlist
- TradingView webhooks are for alerts/signals, not data fetching
- **`backend/integrations/polygon_equities.py` and `backend/integrations/polygon_options.py` are DEAD CODE.** Polygon plan was canceled 2026-04-27. If your build references either file, that is a bug — use UW API instead.
- **FMP is DEPRECATED.** No new dependencies on Financial Modeling Prep.

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
| Data source change | `PROJECT_RULES.md` Data Source Hierarchy |

**Rules:**
- Never describe planned features as built. Verify in code if unsure.
- Code is source of truth over docs. Fix docs when they contradict code.
- Document **why** not just **what** for architecture decisions.
- **When deprecating a data source, update the Data Source Hierarchy in this file IMMEDIATELY.** Stale data-source guidance is a compounding foot-gun for every future build.

## Outcome Tracking Semantics

`signals.outcome` carries three distinct meanings depending on which writer
produced it. The `signals.outcome_source` column (added 2026-05-03 via
migration 013) records the producer.

| outcome_source | Meaning | Writer |
|---|---|---|
| `BAR_WALK` | Hypothetical: "if you'd held to target/stop, what happened?" | `outcome_resolver.py` (yfinance forward bar walk) |
| `ACTUAL_TRADE` | Realized: "what did the trade actually return when closed?" | `unified_positions.py` Ariadne path |
| `COUNTERFACTUAL` | What-if: "if this dismissed signal hadn't been dismissed, what would have happened?" | `analytics/api.py` `/resolve-counterfactuals` endpoint |
| `EXPIRED` | Signal time-window elapsed without target or stop touch (label only; outcome stays NULL) | Phase A backfill from `signal_outcomes` |
| `INVALIDATED` | Signal was contradicted before resolution (label only; outcome stays NULL) | Phase A backfill from `signal_outcomes` |
| `PROJECTED_FROM_BAR_WALK` | Reserved for Phase C — `signal_outcomes`-projected values | (not yet used) |
| `NULL` | Unresolved | — |

**Query rules:**

1. **Strategy-vs-strategy comparisons (win-rate calibration, score-band tuning)**
   must use `signal_outcomes` directly, OR filter `signals` to
   `outcome_source = 'BAR_WALK'`. Mixing semantics (especially Ariadne
   actual-trade outcomes) corrupts the comparison.
2. **P&L reporting (real money)** should use `signals.outcome` filtered to
   `outcome_source = 'ACTUAL_TRADE'`, joined to `unified_positions` /
   `closed_positions` for full context.
3. **Counterfactual analysis** (what-if dashboards, missed-opportunity audits)
   should use `outcome_source = 'COUNTERFACTUAL'` exclusively.
4. **Drift detection** uses `v_outcome_drift` view, which is scoped to
   bar-walk semantics only.

**Phase B (shipped 2026-05-08):** resolver `outcome_resolved_at` is now
wall-clock `NOW()` at write time (no longer derived from yfinance `bar_ts`),
and the bar-walk loop now skips bars stamped before `signal_ts`. All
existing BAR_WALK rows have been backfilled on corrected logic (see
`signal_outcome_diff_log` for the full diff, keyed by backfill_run_id).
Brief: `docs/codex-briefs/outcome-tracking-phase-b-resolver-fix-2026-05-08.md`.

### Phase C: Bar-walk projection rule

- `signal_outcomes` is canonical bar-walk truth.
- `signals.outcome*` is a denormalized projection of bar-walk truth, EXCEPT
  when overridden by `ACTUAL_TRADE` (Ariadne, on position close) or
  `COUNTERFACTUAL` (analytics).
- The `outcome_resolver.py` writes `signals.outcome*` directly with
  `outcome_source = 'BAR_WALK'`.
- The `score_signals.py` writes `signal_outcomes` and projects to
  `signals.outcome*` with `outcome_source = 'PROJECTED_FROM_BAR_WALK'`.
- `signal_outcomes.max_favorable` is a snapshot, not a living number. To use
  MFE for any decision more than 7 days post-resolution, run
  `scripts/rewalk_signal_outcomes.py --dry-run` first to detect drift.

### Canonical walker policy

- 15-minute resolver (`outcome_resolver.py`) is canonical for:
  intraday tactics (B3 scalps), MFE/MAE for entry/exit calibration,
  stop-tightness studies.
- Daily resolver (`score_signals.py`) is canonical for:
  B1/B2 swing strategies where intraday wiggle is noise, weekly/monthly
  aggregate studies, strategy promotion audits.
- When the two agree: use either.
- When they disagree on a signal: the canonical walker for the signal's
  strategy/timeframe wins. Log the disagreement in
  `signal_outcome_diff_log` with `reason='granularity_reconciliation'`.
  Never silently average.
- INVALIDATED carve-out: when `signal_outcomes.outcome = 'INVALIDATED'`
  but `signal_outcomes.MAE` crossed `stop_loss` or `MFE` crossed `target_1`,
  the BAR_WALK price-based verdict wins. Log with distinct
  `reason='granularity_reconciliation_invalidated_override'` so these
  cases are queryable as a quality signal on `score_signals`'s
  contradiction logic.

## Deployment Verification

"Committed and pushed" ≠ "deployed and running." Railway can silently fail a
build, time out a deploy, or serve a stale image while reporting healthy.
A May 2026 incident saw 4 days of "deployed" code that was never actually
running. Every brief that ships code MUST verify the deployed image matches
the committed code before declaring complete.

**Required verification step in every CC brief acceptance criteria:**

1. After `git push origin main`, confirm Railway deploy status:
   `railway deployment list -s <service>` — most recent deployment must
   show SUCCESS, not BUILDING / FAILED / CRASHED.
2. Verify deploy SHA matches commit SHA being shipped. Mismatch = stale
   container, retry deploy or trigger an empty commit to force rebuild.
3. Empirically confirm the patched code is live — query the running
   service for an observable side effect of the patch (new tag value,
   new column write, new endpoint response, log line, etc.). Do NOT
   accept `/health = OK` as proof; FastAPI health endpoints don't
   reflect job-scheduler or background-worker patches.
4. If deploy is silent for >5 min after `git push`, do not assume success.
   Pull `railway logs -s <service> --tail` and check for build failures.

A brief is not complete until step 3 is empirically confirmed.

## unified_positions Schema Limitation

The `unified_positions` table represents spreads via `long_strike` and
`short_strike` only. Structures with more than 2 legs (broken-wing spreads,
butterflies, condors) are stored under a 2-leg approximation; middle/extra
legs are structurally invisible to schema queries.

Active example: **HYG 6/18 put ratio** (`POS_HYG_20260325_185236`) is the
broken-wing `-4×$74P / +4×$75P / +4×$76P` recorded as `put_debit_spread`
with `long_strike=76, short_strike=74`. The `+4×$75P` middle leg is not
in the DB. Canonical full-structure reference: `docs/open-positions.md`.

### Naked single-leg option pricing gap

The price-updater builds option-chain keys from `long_strike` and
`short_strike` columns on `unified_positions`. Naked single-leg long
options (`structure IN ('long_call', 'long_put')`) leave both strike
columns NULL, so the updater has no key to query and `current_price`/
`current_value`/`unrealized_pnl` remain NULL.

Affected positions are correctly excluded from `position_value` totals
(via the `current_price IS NULL` skip in unified_positions.py — see
Cluster C fix 2026-05-13). User-visible impact: per-row PnL column
displays "—" for these positions.

Canonical PnL reference for naked positions: broker app directly, or
`docs/open-positions.md` if maintained.

Active examples (as of 2026-05-13):
- COUR 6/18 long_put × 3, $4 strike
- WEAT 6/18 long_call × 8, $30 strike

Future remediation candidate: extract strike from `notes` / `legs` jsonb
/ `signal_id` lookup chain. Not scheduled.
