# Pivot — Priorities & TODO

**Last Updated:** April 22, 2026

---

## ✅ Phase 0: Code Hygiene Cleanup — COMPLETE

**Context:** External audit by GPT-5.4 (March 9) identified critical issues. All 7 phases completed March 10-11.

### ✅ Phase 0A — Repo Source of Truth (COMPLETE — March 10)
- [x] 9 missing VPS scripts pulled, 8 untracked added, duplicates resolved, stale docs fixed, `config/.env` untracked, `committee_autopsy.py` fixed, `committee_outcomes.py` updated from VPS
- **⚠️ Nick:** Rotate credentials from `config/.env` + Discord bot token (repo is private, not urgent)

### ✅ Phase 0B — Auth Lockdown (COMPLETE — March 10)
- [x] Unified `require_api_key()`, auth on 9 position + committee + trade ideas routes, TradingView webhook secret, CORS env var, frontend `authHeaders()` on 30 calls, removed duplicate auth functions
- [x] `PIVOT_KEY_PLACEHOLDER` replaced with real API key in `app.js` ✅

### ✅ Phase 0C — Finish Positions Migration (COMPLETE — March 10)
- [x] 1,268 lines removed across 7 files. In-memory state killed, `accept_signal()` writes to unified_positions, 13 legacy routes deleted, sync functions deleted, frontend unified on v2.

### ✅ Phase 0D — Frontend Hygiene (COMPLETE — March 10)
- [x] 233 lines removed. Dead endpoints eliminated, polling consolidated, hybrid scanner documented as active.

### ✅ Phase 0E — Data Durability (COMPLETE — March 10)
- [x] `safe_jsonl.py` utility (atomic writes via temp+rename, fsync on appends). 7 committee scripts converted. Deployed to VPS.

### ✅ Phase 0F — Resilience & Monitoring (COMPLETE — March 10)
- [x] Committee heartbeat, factor staleness monitor, webhook dedup, Polygon health tracking

### ✅ Phase 0G — Test Coverage (COMPLETE — March 11)
- [x] **93 tests, all passing** — auth enforcement, webhook validation, position CRUD, frontend route smoke, grouped endpoint

---

## ✅ Immediate (Trading) — COMPLETE

- [x] tick_breadth late bounce fix, VWAP validation harness, confluence validation gate

---

## ✅ Phase 1: Trading Strategies Review — COMPLETE (all actionable items)

### ✅ Done (March 5-6-9-10-11 Sessions)

- [x] Signal flow audit, strategy-signal mapping, PineScript health, 5 strategy docs written
- [x] Triple Line scrapped (345 lines), strategy backlog created
- [x] Confluence Engine live, Holy Grail scanner live, Scout Sniper scanner live
- [x] Absorption Wall wired, committee strategy review, all selloff tweaks (CTA/HG/Scout/Exhaustion)
- [x] Golden Touch fix, ETF yfinance fix, outcome tracking fix, committee data access + prompts
- [x] Pivot Chat data access + system prompt overhaul, auto-committee disabled, dead code cleanup
- [x] Twitter scraper refreshed, trade logging pipeline, macro narrative context
- [x] Close position P&L tracking, portfolio positions deprecated, Sell the Rip scanner v1
- [x] **UW Watcher fix** — dead 7 days, Discord bold markdown broke regex
- [x] **breadth_intraday fix** — DVOL→USI:DVOL (was resolving to ETF)
- [x] **Whale Hunter TV alerts** — 32 tickers active (original 18 + SPY, QQQ, XLF, XLE, NEM, IGV, NVDA, MSFT, JPM, AMD, GLD, USO/XOP, TLT, LMT)
- [x] **Positions UI refresh** — auto-refresh on create/close/manual, type grouping (Options Long/Short, Stocks)
- [x] **Whale Hunter pipeline integration** — Whale signals now persist in `signals` table via `process_signal_unified()`. CONTESTED signals Discord-only. Webhook secret validation added. `signal_category=DARK_POOL`. Base score 50.
- [x] **UW Flow as independent signal source** — $500K+ premium, 3+ unusual trades, bias-aligned → auto-creates trade idea signals. 1-hour per-ticker cooldown. Redis-tunable thresholds. `signal_category=FLOW_INTEL`. Base score 40.
- [x] **Grouped Trade Ideas** — `GET /api/trade-ideas/grouped` groups by ticker+direction. Composite ranking (score 50%, confluence 20%, recency 15%, urgency 15%). Three card templates (TRADE_SETUP, DARK_POOL, FLOW_INTEL). Confluence badges, position overlap indicators, stale markers, expandable related signals.

### ⏳ Blocked on Data (monitoring passively)

- [ ] **Artemis server-side port (Phase A.3)** — Blocked on VWAP validation (5 trading days). `vwap_validator.py` collecting data.
- [ ] **Gatekeeper threshold review** — Needs 4+ weeks outcome data. Confluence validation endpoint collecting.
- [ ] **Shadow mode validation** — `/api/analytics/shadow-validation` collecting. Target ≥80% overlap.
- [ ] **Confluence Phase C (combine PineScripts)** — Deferred. HIGH risk, not needed yet.

---

## ✅ Phase 2: Crypto Scalper Review/Overhaul — COMPLETE

### ✅ Phase 2A — Plumbing & Auth (COMPLETE)
- [x] Ticker normalization (.P suffix handling)
- [x] Auth on BTC signal mutation routes
- [x] Legacy route coupling killed
- [x] Symbol propagation (selected coin → API)
- [x] Dead code cleanup, smoke tests

### ✅ Phase 2B — BTC Setup Engine (COMPLETE)
- [x] Crypto bias bypass (NEUTRAL alignment for crypto signals)
- [x] Holy Grail + Exhaustion PineScript alerts on BTCUSDT.P
- [x] 3 crypto-native strategies: Funding Rate Fade, Session Sweep, Liquidation Flush
- [x] Breakout position sizing (1% max risk, $25K account)
- [x] 5-minute scheduler, 24/7

### ✅ Phase 2B.5 — Market Structure Filter (COMPLETE)
- [x] Volume Profile (POC/VAH/VAL from klines)
- [x] CVD gate (flow confirmation/divergence)
- [x] Orderbook imbalance (bid/ask ratio + wall detection)
- [x] Score modifier: -45 to +35 per signal

### ✅ Phase 2C — Discord Delivery (COMPLETE)
- [x] Crypto-specific Discord embeds
- [x] 24/7 notifier cron
- [x] Take/Pass/Watching buttons (no committee)

### ✅ Phase 2D — Cleanup (COMPLETE)
- [x] Standalone crypto-scalper/ deleted
- [x] Orphaned references removed
- [x] crypto_market.py symbol derivation (no more hardcoded BTC)
- [x] Docs updated

---

## 🟢 Raschke Strategy Build (Olympus 2026-04-22)

**Context:** Olympus committee deep review completed 2026-04-22 ratified 7 framework amendments (now in PROJECT_RULES.md) and classified 5 Raschke strategies under REPLACE-ELEVATE-ADD-REJECT. Holy Grail audit (same day) surfaced `iv_regime` factor exists in `composite.py:87-92` but NOT wired to Holy Grail, and `hunter.py` self-deprecated in header but still live. 15m HG variant confirmed as TV webhook at `tradingview.py:365-371` (not a separate Python file).

**Key docs:**
- `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` — committee output
- `docs/strategy-reviews/raschke/titans-brief-3-10-oscillator.md` — Titans Pass 1 input
- `docs/audits/holy-grail-audit-2026-04-22.md` — CC audit delta report
- `docs/codex-briefs/brief-holy-grail-audit-olympus-expanded.md` — original audit brief
- `docs/codex-briefs/brief-project-rules-framework-amendments.md` — framework brief
- `docs/codex-briefs/brief-hunter-py-removal.md` — next CC task

### ⏳ Phase 1: Foundation (in progress)

- [x] **Remove `hunter.py`** — self-deprecated, banked +1 anti-bloat slot. Commit `80b4aca` (619 lines). See `docs/codex-briefs/brief-hunter-py-removal.md`.
- [x] **Strip hunter UI + `api/scanner.py` wrapper** — completes the deprecation end-to-end. Commit `07858cb` (461 lines across frontend/app.js, api/scanner.py, main.py, test_auth.py). See `docs/codex-briefs/brief-hunter-ui-strip.md`.
- [ ] **Titans Pass 1 on 3-10 Oscillator** — ✅ completed via separate chat, committed to `docs/strategy-reviews/raschke/titans-brief-3-10-oscillator.md` at commit `123d66b`. Architecture locked in §11.
- [ ] **3-10 Oscillator CC build** — 4-phase build brief at `docs/codex-briefs/brief-3-10-oscillator-core.md` (commit `49c91fb`). Phase 0 pre-flight check first, then phased execution with checkpoints. **NEXT CC TASK.**
- [ ] **Holy Grail Tier 1 fixes** — covered within 3-10 build brief Phase 2 (dual-gate tagging) and Phase 3 (sector-rotation tag). iv_regime wiring is NOT yet covered and remains a separate Tier 1 fix — scope a follow-up brief after 3-10 build lands.

### ⏳ Phase 2: Scanners (gated on Phase 1 validation + backtest module live)

- [ ] **80-20 Reversals scanner** — B3 equity with PYTHIA VAL/VAH gate mandatory in trigger definition. Then B2 daily variant.
- [ ] **Turtle Soup as ELEVATE lane on `sell_the_rip_scanner`** — not a parallel scanner per audit finding. Vanilla daily first, then flow-augmented (UW net-sell + put sweep on failure bar), then B3 intraday parameterization.
- [ ] **Holy Grail Tier 2 fixes** — session filter (config-gated, on for 15m webhook), EMA slope confirmation, HH/HL structure check, `asset_class` parameterization for crypto variant, PYTHIA VA-relative context tag, PYTHAGORAS ATR-alternative stop.

### ⏳ Phase 3: Anti variant (gated on Phase 1+2 positive expectancy)

- [ ] **The Anti as Holy Grail config branch** — shallow-pullback variant. Requires 3-10 live + backtest showing <50% overlap with standard HG fires. Dedupes at signal layer.
- [ ] **Holy Grail Tier 3 fixes** — scale exit (50% at 1R + trail remainder), pullback sequence tracking (1st vs Nth after ADX ignition), URSA ticker-level circuit breaker (skip next fire after 2 consecutive losses in 10d).

### ⏳ Phase 4: News Reversal + closeout

- [ ] **News Reversal (moved from Phase 3 per Nick decision 2026-04-22)** — DAEDALUS + THALES joint design. Requires UW news classification upstream (may warrant own Titans brief). URSA's three pre-build gates: (1) fade direction aligned with broader trend, (2) IV crush pattern required, (3) mandatory DAEDALUS structure selection — no naked puts/calls on earnings plays. Crypto variant deferred pending DVOL integration trigger.
- [ ] **Crypto variant reviews** — Turtle Soup/80-20/Holy Grail on BTC/ETH once HV-30 regime gate is in place. DVOL integration gated on first IV-sensitive crypto strategy (likely News Reversal crypto variant).
- [ ] **`wh_reversal` compliance re-check** — auto-surface at Q3 2026 Olympus cadence to verify VAL-proximity absorption into location multiplier holds in production (not behaving as hidden factor).
- [ ] **Backtest-driven deprecation sweep** — run backtest against any strategies flagged for possible REPLACE; close the anti-bloat loop.

---

## 🟠 Phase 3: Analytics Review/Overhaul

**Goal:** Make analytics accurate, visual, and self-improving.

**Progress:** Outcome tracking operational. Confluence validation endpoint live. Grouped trade ideas with composite ranking deployed.

- [ ] **Scoring accuracy audit** — Compare signal scores at generation vs outcomes. Is 75+ threshold meaningful?
- [ ] **Data visualization overhaul** — Dashboard showing: win rate trend, factor contribution heatmap, strategy P&L curve, committee accuracy over time.
- [ ] **Missing tracking** — Time-to-fill after TAKE, slippage, partial fills, position sizing compliance, DTE at entry vs exit.
- [ ] **Unified performance view** — Single page: "Is this system making money?" Position P&L + signal accuracy + factor reliability + committee agreement rate + override outcomes.
- [ ] **Self-improvement loop audit** — Weekly review → lessons_bank → committee context injection. Verify loop quality after 4 weeks of data.
- [ ] **Robinhood trade import** — CSV parser exists, historical trades not imported. Needed for backtesting.

---

## 🟠 Phase 4: Knowledge Base Cleanup

**Goal:** Complete overhaul after massive Feb-Mar 2026 changes.

- [ ] **Audit existing KB entries** — Most are stale/wrong (pre-bias overhaul, pre-committee training).
- [ ] **Rebuild from current architecture** — Generate KB from: CLAUDE.md, DEVELOPMENT_STATUS.md, committee prompts, factor-scoring.md, API docs.
- [ ] **Agent training integration** — KB queryable by Pivot during chat. Currently static frontend feature.
- [ ] **Bias factor documentation** — 19 of 20 factors exist only in code. Document each factor's logic, data source, and scoring bands.

---

## 🟡 Ongoing / Lower Priority

- [ ] **Polygon-Powered Dynamic Scan Universe** — CONFIRMED: Polygon Stocks Starter ($29/mo) returns 12,367 tickers in a single snapshot API call with current price, volume, and daily change. Plan supports daily bars (delayed 15 min) and full-market snapshots but NOT intraday bars (15m/1H — needs Developer plan $79/mo). **Proposed architecture:** Stage 1 = Polygon snapshot pre-filter (1 API call, ~2s) filters to liquid, moving names by volume/price/change thresholds. Stage 2 = yfinance 15m bars only on the filtered set. Gets wider coverage (catching movers not in hardcoded lists) while being faster (skips dead tickers). For daily-bar strategies (CTA Scanner), can replace yfinance with Polygon entirely. Existing integration: `backend/integrations/polygon_equities.py` has `get_bars()`, `get_bars_as_dataframe()`, `get_snapshot()`, `get_previous_close()` all working. **Impact:** Scale server-side scanners from hardcoded 200 tickers to dynamic 500-1000+ without yfinance rate limit issues.
- [ ] **Phalanx confluence enrichment** — Phalanx plumbing is live and wall levels caching in Redis. Next step: when scoring other signals (CTA, Artemis, etc.), check Redis for nearby Phalanx wall levels. If signal entry_price within 0.5 ATR of cached wall AND direction matches: +10 confluence bonus. Separate brief.
- [ ] **Artemis parameter loosening** — After 1 week of baseline data with webhook fix: widen proximity zone (0.25→0.4 ATR), convert AVWAP gate to score modifier (-15 pts), remove stacked confirmation candle RVOL, lower Flush mode RVOL (2.0→1.5x). Per Olympus review.
- [ ] **IBKR account setup** — Fund account → create read-only API user → enable position polling
- [ ] **Brief 05B: Adaptive Calibration** — Dynamic thresholds + agent trust weighting. Needs 3+ weeks outcome data.
- [ ] **Complex multi-leg tracking** — Iron condors, butterflies. `trade_legs` table exists but not wired.
- [ ] **Mobile optimization** — Bottom nav, pull-to-refresh, responsive position cards
- [ ] **DST fix deployment** — Convert hardcoded UTC offsets to IANA timezones. Brief written, not deployed.
- [ ] **Drop `positions` and `open_positions` tables** — Fully deprecated. Can drop after confirming zero callers.
- [ ] **Credential rotation** — `config/.env` had live creds in git history. Repo is private, not urgent.
- [ ] **Repo hygiene — mangled directory** — `ctrading-hubbackendintegrations_deprecated/` at repo root looks like a path typo that became a directory name (missed backslash somewhere). If empty/unused, delete via a dead-code-cleanup CC brief.
- [ ] **Repo hygiene — stale backup zip** — `trading-hub-complete-20260128_113640.zip` at repo root. Git is the backup system; delete unless there's a specific reason to keep.
- [ ] **Repo hygiene — consolidate agent config files** — `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `PROJECT_RULES.md`, `PROJECT_SUMMARY.md`, `QUICK_START.md`, `DEVELOPMENT_STATUS.md` overlap in "source of truth" role. A consolidation pass would reduce drift risk. Parked as a later cleanup, not urgent.
- [ ] **Auth coverage gap on new routes** — `test_no_unprotected_mutations` now flags 16 routes without webhook-secret protection (was 2 when first noted, grew as new routes were added: trade-watchlist, hermes, hydra, etc.). Surfaced again during hunter UI strip (commit `07858cb`). Not a hunter-removal regression. Needs a targeted audit brief: identify which of the 16 routes SHOULD be secret-protected vs. which are legitimately public, then either (a) add auth to the ones that need it, or (b) update the test's allow-list with a comment explaining why each exempted route is safe. Don't bury this — it's growing.

---

## ✅ Completed (March 11, 2026) — Webhook Fix + McClellan + Artemis + Phalanx

- [x] **Webhook dedup bug fix** — `alert.interval` → `alert.timeframe`. Was 500'ing ALL TradingView webhooks (Scout, Artemis, Exhaustion, Holy Grail, Phalanx). Deployed immediately.
- [x] **McClellan Oscillator NYSE proxy** — CC added ^NYA daily returns as breadth proxy fallback. Factor no longer MISSING.
- [x] **Artemis (formerly Hub Sniper) — DEPLOYED** — Olympus review → CC brief → deployed. Dedicated `process_artemis_signal()` handler, Pydantic fields (mode, avwap_ctx, prox_atr, adx_rising), scorer entries (ARTEMIS_LONG/SHORT: 45), strategy doc renamed. PineScript updated, TV watchlist alert active.
- [x] **Phalanx (formerly Absorption Wall) — DEPLOYED** — Olympus review → CC brief → deployed. Dedicated `process_phalanx_signal()` handler with `signal_category=ORDER_FLOW`, Redis wall level caching (4h TTL), scorer entries (PHALANX_BULL/BEAR: 40), strategy doc created. PineScript updated, TV watchlist alert active.
- [x] **Polygon scan universe discovery** — Confirmed Starter plan returns 12K tickers in single snapshot call. Architecture for dynamic scan universe documented.
- [x] UI rename: Greek mythology theme (Agora, Stater Swap, Abacus, Great Library, Insights, Ledger)

## ✅ Completed (March 10-11, 2026) — Phase 0 + Phase 1 + Immediate Trading + Signal Pipeline

- [x] Phase 0A-0G: All 7 code hygiene phases complete (93 tests)
- [x] API key deployed, Redis fix, Sell the Rip scanner v1
- [x] tick_breadth late bounce fix, VWAP validator, confluence validation + shadow mode
- [x] Positions UI: auto-refresh + type grouping with dividers
- [x] UW Watcher fix (bold markdown), breadth_intraday fix (DVOL symbol)
- [x] Whale Hunter: 32 TV alerts active, pipeline integration (signals table + scoring + confluence)
- [x] UW Flow: independent signal source ($500K+, 3+ unusual, bias-aligned, 1hr cooldown)
- [x] Grouped Trade Ideas: composite ranking, 3 card templates, confluence badges, position overlap, stale markers

## ✅ Completed (March 9, 2026 Session) — 9 builds shipped

- [x] Exhaustion BULL suppression, macro briefing (crisis), PLTR DST fix
- [x] Pivot Chat overhaul, close position P&L, portfolio deprecated, balances corrected
- [x] All positions synced, closed trades backfilled (+$329, 3W/1L)

## ✅ Completed (March 6, 2026 Session) — 19 builds shipped

- [x] Signal audit, PineScripts, strategy docs, Triple Line scrapped, strategy backlog
- [x] Confluence Engine, Holy Grail + Scout scanners, Absorption Wall, selloff tweaks
- [x] Committee access + prompts, Pivot Chat data, trade logging, macro context

## ✅ Completed (March 5, 2026 Session)

- [x] Bias engine overhaul: 20 factors, tick_breadth scoring, GEX recal, IV regime
- [x] McClellan endpoint, breadth alerts, factor weights, Brief 08 + 09
