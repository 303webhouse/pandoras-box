# Pivot — Priorities & TODO

**Last Updated:** March 11, 2026

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
- [x] **92 tests, all passing** — `conftest.py` with mocked Redis/Postgres (no live DB needed)
- [x] `test_auth.py` — 38 tests: 9 protected routes × 3 auth methods + public routes + wrong key
- [x] `test_webhooks.py` — 3 tests: webhook secret validation
- [x] `test_positions.py` — 16 tests: v2 CRUD + 10 legacy routes confirmed dead (404)
- [x] `test_frontend_routes.py` — 17 tests: frontend endpoint smoke + dead endpoint checks
- [x] Original 20 scorer tests still pass

---

## ✅ Immediate (Trading) — COMPLETE

- [x] **tick_breadth late bounce fix** — Conflict handler now replaces close signal with average-derived direction (was only dampening 0.25x). Agreement amplification (1.2x) when close and avg confirm.
- [x] **Hub Sniper VWAP validation harness** — `vwap_validator.py` logging SPY VWAP + ±2σ bands every 15 min. Endpoint: `GET /api/monitoring/vwap-validation`. Nick compares vs TV for 5 trading days.
- [x] **Confluence validation gate** — `confluence_validation.py` comparing CONFIRMED/CONVICTION vs STANDALONE outcomes. Endpoints: `GET /api/analytics/confluence-validation`, `GET /api/analytics/shadow-validation`. Auto-reports PASS/FAIL/WAITING verdict.

---

## ✅ Phase 1: Trading Strategies Review — COMPLETE (actionable items)

### ✅ Done (March 5-6-9-10-11 Sessions)

- [x] Signal flow audit — 389 trade ideas mapped, per-strategy breakdown, per-CTA-subtype counts
- [x] Strategy-signal type mapping — full webhook handler routing documented
- [x] PineScript indicator health — all 10 webhook scripts backed up to repo, inventory created
- [x] Neglected strategies — 5 missing strategy docs written (Holy Grail, Scout, Hub Sniper, Whale Hunter, Exhaustion)
- [x] Triple Line scrapped — doc replaced with tombstone, dead code removed (345 lines)
- [x] Strategy backlog created — deferred (WRR, Dollar Smile, HTF Divergences), pending decisions, dead code
- [x] Signal Confluence Architecture — designed, committee-reviewed (double-pass), validated sequencing
- [x] Confluence Engine (Phase B) — live on Railway, 15-min scan, 7 lens categories, Discord alerts
- [x] Holy Grail server-side scanner (Phase A.1) — live, 200+ tickers, 15-min scan, shadow mode
- [x] Scout Sniper server-side scanner (Phase A.2) — live, 200+ tickers, 15-min scan, shadow mode
- [x] Absorption Wall wired to pipeline — JSON PineScript alert + dedicated Railway handler + ORDER_FLOW_BALANCE lens
- [x] Committee strategy review (all 5 active strategies) — selloff-specific analysis with tweaks
- [x] CTA selloff tweaks — VIX-adjusted stops (0.5→0.75 ATR), zone-aware RESISTANCE_REJECTION volume (0.8x in bearish)
- [x] Holy Grail selloff tweaks — RSI floor bypass in strong downtrends, VIX touch tolerance widening
- [x] Scout Sniper selloff tweaks — bias-aware LONG suppression when composite < -0.3
- [x] Exhaustion BULL suppression — bias-aware IGNORE when composite < -0.3 (deployed March 9)
- [x] Golden Touch fix — thresholds relaxed (50→30 days, 2.0→1.3x volume, 3-bar window)
- [x] ETF yfinance fix — skip earnings check for ETFs, prevents committee crash on QQQ/SMH/IWM
- [x] Outcome tracking fix — removed 48h window, reads ALL decisions, 5 outcomes matched
- [x] Committee data access fix — bias URL corrected, portfolio verified, enhanced factor context
- [x] Committee prompts update — 4-agent TORO/URSA/TECHNICALS/PIVOT deployed to VPS
- [x] Pivot Chat data access — 11 data sources (positions, balances, CB, sectors, trade ideas)
- [x] Pivot Chat system prompt overhaul — data integrity rules, 4-agent committee format, signal pipeline awareness, removed stale hardcoded balances, 8→20 factors
- [x] Auto-committee disabled — cron commented out until confluence system dialed in
- [x] Dead code cleanup — Triple Line handler, deprecated functions, old PineScript archived
- [x] Twitter scraper tokens refreshed + daily health check cron added
- [x] Trade logging pipeline — auto-detect entries AND exits in Discord, confirmation buttons, `/log-trade` command, writes to decision_log.jsonl + Railway outcomes
- [x] Macro narrative context — raw headlines block, macro prices (oil, gold, 10Y, DXY, VIX), persistent regime briefing file, `/macro-update` Discord command, Railway endpoint
- [x] Close position P&L tracking — frontend sends exit values, v2 writes to closed_positions, PATCH backfill endpoint, trade exit detection patterns on VPS
- [x] Portfolio positions table deprecated — GET /api/portfolio/positions now reads from unified_positions. Single source of truth.
- [x] **Sell the Rip scanner v1** — Server-side negative momentum fade with sector rotation layer.
- [x] **UW Watcher fix** — Was dead for 7 days. Discord bold markdown (`**TICKER**`) broke regex parsing. Fix: strip `**` before parsing, skip `<t:` timestamp lines, bump "No parseable" log to INFO.
- [x] **breadth_intraday fix** — PineScript DVOL symbol resolving to ETF ($55) instead of NYSE Down Volume (~300M). Fix: `"DVOL"` → `"USI:DVOL"`, `"UVOL"` → `"USI:UVOL"`.
- [x] **Whale Hunter TV alerts verified** — 18 tickers active and working (LUV, XOM, CVX, FCX, META, GOOGL, CRCL, AVGO, TSM, PANW, CRWD, CVNA, AMZN, AAPL, UBER, PLTR, TSLA, GS). AVGO signal confirmed March 4.
- [x] **Positions UI refresh** — Auto-refresh prices on create/close/manual refresh. MTM endpoint works after hours. Positions grouped by type (Options Long/Short, Stocks) with subtle dividers.

### ⏳ Blocked on Data (monitoring passively)

- [ ] **Hub Sniper server-side port (Phase A.3)** — Blocked on VWAP validation (5 trading days of data collecting via `vwap_validator.py`). If validation fails, Hub Sniper stays on TV.
- [ ] **Gatekeeper threshold review** — Current: MAJOR=85, MINOR=70, NEUTRAL=60. Needs 4+ weeks outcome data. Confluence validation endpoint collecting data.
- [ ] **Shadow mode validation** — Endpoint live at `/api/analytics/shadow-validation`. Data collecting. Target ≥80% overlap.
- [ ] **Confluence Phase C (combine PineScripts)** — Deferred. HIGH engineering risk, not needed yet.

### 📋 Ready to Build Next

- [ ] **UW Flow as independent signal source** — UW watcher now working. High-conviction flow (premium ≥ $500K, unusual_count ≥ 3, bias-aligned) should trigger committee review directly. Needs brief.

---

## 🟠 Phase 2: Crypto Scalper Review/Overhaul

**Goal:** Assess the crypto shell, determine what's working, what's orphaned, and build a real LTF scalping system.

**Discovery (March 6):** Crypto Scanner is actively generating ~57 trade ideas. Source and configuration unknown — needs audit.

- [ ] **Current state audit** — The crypto scalper UI exists (`/crypto` route). What backend endpoints are active vs dead? What data is actually flowing? Where are the 57 trade ideas coming from?
- [ ] **Signal reliability** — What crypto signals are coming in? From where? Same webhook pipeline or separate path?
- [ ] **LTF strategy implementation** — Strategies for 1m-15m crypto/forex scalping. Evaluate: VWAP bounce, order flow imbalance, funding rate divergence, liquidation cascade detection.
- [ ] **Architecture decision** — "Single app, two shells" approved. `/hub` (equities) and `/crypto` (scalping) sharing Railway backend.
- [ ] **BTC session/bottom signal components** — Orphaned components from earlier builds. Reconnect or remove.
- [ ] **Exchange integration** — Coinbase sandbox (~$150). API access for paper trading.

---

## 🟠 Phase 3: Analytics Review/Overhaul

**Goal:** Make analytics accurate, visual, and self-improving.

**Progress:** Outcome tracking operational. 9 outcomes now tracked (5 from nightly matcher + 4 manually backfilled March 9). Weekly review runs Saturday 9 AM MT. Close position P&L tracking now functional. Confluence validation endpoint live.

- [ ] **Scoring accuracy audit** — Compare signal scores at generation vs outcomes. Is 75+ threshold meaningful?
- [ ] **Data visualization overhaul** — Dashboard showing: win rate trend, factor contribution heatmap, strategy P&L curve, committee accuracy over time.
- [ ] **Missing tracking** — Time-to-fill after TAKE, slippage, partial fills, position sizing compliance, DTE at entry vs exit.
- [ ] **Unified performance view** — Single page: "Is this system making money?" Position P&L + signal accuracy + factor reliability + committee agreement rate + override outcomes.
- [ ] **Self-improvement loop audit** — Weekly review → lessons_bank → committee context injection. Verify loop quality after 4 weeks of data.
- [ ] **Robinhood trade import** — CSV parser exists, historical trades not imported. Needed for backtesting.

---

## 🟠 Phase 4: Knowledge Base Cleanup

**Goal:** Complete overhaul after massive Feb-Mar 2026 changes.

**Head start:** 7 strategy docs now complete (was 2), PineScript inventory created, architecture docs current.

- [ ] **Audit existing KB entries** — Most are stale/wrong (pre-bias overhaul, pre-committee training).
- [ ] **Rebuild from current architecture** — Generate KB from: CLAUDE.md, DEVELOPMENT_STATUS.md, committee prompts, factor-scoring.md, API docs.
- [ ] **Agent training integration** — KB queryable by Pivot during chat. Currently static frontend feature.
- [ ] **Bias factor documentation** — 19 of 20 factors exist only in code. Document each factor's logic, data source, and scoring bands.

---

## 🟡 Ongoing / Lower Priority

- [ ] **IBKR account setup** — Fund account → create read-only API user → enable position polling
- [ ] **Brief 05B: Adaptive Calibration** — Dynamic thresholds + agent trust weighting. Needs 3+ weeks outcome data.
- [ ] **Complex multi-leg tracking** — Iron condors, butterflies. `trade_legs` table exists but not wired.
- [ ] **Mobile optimization** — Bottom nav, pull-to-refresh, responsive position cards
- [ ] **DST fix deployment** — Convert hardcoded UTC offsets to IANA timezones. Brief written, not deployed. IBKR not funded so pollers not active.
- [ ] **Drop `positions` and `open_positions` tables** — Now fully deprecated. All reads/writes go through `unified_positions`. Can drop after confirming zero callers.
- [ ] **Credential rotation** — `config/.env` had live creds in git history. Redis password exposed in chat. Generate new PIVOT_API_KEY, rotate DB password, Discord bot token. Repo is private so not urgent.

---

## ✅ Completed (March 10-11, 2026) — Phase 0 Complete + Phase 1 Complete + Immediate Trading

- [x] Phase 0A: Repo source of truth
- [x] Phase 0B: Auth lockdown + `PIVOT_KEY_PLACEHOLDER` replaced with real API key
- [x] Phase 0C: Positions migration (1,268 lines removed)
- [x] Phase 0D: Frontend hygiene (233 lines removed)
- [x] Phase 0E: Data durability (atomic JSONL writes)
- [x] Phase 0F: Resilience & monitoring (heartbeat, staleness, dedup, Polygon health)
- [x] Phase 0G: Test coverage (92 tests — auth, webhooks, positions, frontend routes)
- [x] Sell the Rip scanner v1
- [x] Redis fix (`REDIS_URL` env var pattern)
- [x] tick_breadth late bounce fix (avg overrides conflicting close)
- [x] VWAP validation harness (collecting data for Hub Sniper port)
- [x] Confluence validation gate + shadow mode endpoints
- [x] Positions UI: auto-refresh prices on create/close/refresh + type grouping with dividers
- [x] UW Watcher fix — dead 7 days due to Discord bold markdown breaking regex
- [x] breadth_intraday fix — DVOL resolving to ETF, changed to `USI:DVOL`
- [x] Whale Hunter TV alerts verified — 18 tickers active and confirmed working

## ✅ Completed (March 9, 2026 Session) — 9 builds shipped

- [x] Exhaustion BULL suppression (bias-aware IGNORE when composite < -0.3)
- [x] Macro briefing updated for crisis (oil $108, Strait of Hormuz closed, stagflation regime)
- [x] PLTR alert DST-corrected (14:30→13:30 UTC for EDT)
- [x] Pivot Chat system prompt — data integrity rules, 4-agent committee format, signal pipeline awareness
- [x] Close position P&L tracking — frontend sends exit values, v2 backend writes to closed_positions
- [x] Portfolio positions table deprecated — single source of truth via unified_positions
- [x] RH balance corrected ($4,371.42 / $3,709.42 cash)
- [x] All positions synced — PLTR/TSLA/IWM/TOST closed, IBIT + NEM added, AMZN/XLF corrected
- [x] Closed trades P&L backfilled (+$329, 3W/1L)

## ✅ Completed (March 6, 2026 Session) — 19 builds shipped

- [x] Full signal system health audit (389 trade ideas, 6 strategies, 9 CTA sub-types)
- [x] All 10 PineScripts backed up to repo + inventory doc
- [x] 5 missing strategy docs written (Holy Grail, Scout, Hub Sniper, Whale Hunter, Exhaustion)
- [x] Strategy backlog created (deferred/rejected/pending decisions/dead code)
- [x] Triple Line scrapped + dead code removed (345 lines)
- [x] Golden Touch fix, ETF yfinance fix, Confluence Engine, Holy Grail + Scout scanners
- [x] Absorption Wall wired, CTA/HG/Scout selloff tweaks, committee data access + prompts
- [x] Pivot Chat data access (11 sources), auto-committee disabled, Twitter scraper fixed
- [x] Trade logging pipeline, macro narrative context, dead code cleanup

## ✅ Completed (March 5, 2026 Session)

- [x] Scout signal levels, tick_breadth scoring, circuit breaker fix, bias floor fix
- [x] GEX recalibrated, IV regime, spy_50sma, spy_200sma moved to macro
- [x] McClellan endpoint, breadth + McClellan TV alerts, factor weight rebalance
- [x] Brief 08 (RH/Fidelity tabs), Brief 09 (Hub feature cleanup)
