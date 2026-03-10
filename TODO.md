# Pivot — Priorities & TODO

**Last Updated:** March 10, 2026

---

## 🔴 Phase 0: Code Hygiene Cleanup (GPT-5.4 Audit Response)

**Context:** External audit by GPT-5.4 (March 9) identified critical issues: repo not matching production, unauthenticated endpoints, position migration incomplete, frontend/API drift, JSONL fragility. Full audit saved in project chat history.

### ✅ Phase 0A — Repo Source of Truth (COMPLETE — March 10)
- [x] **Pull all VPS-only scripts into repo** — 9 missing scripts pulled from VPS, 8 previously untracked added to git. 30 scripts on VPS, all now in `scripts/`.
- [x] **Resolve duplicate interaction handler** — `openclaw/scripts/` deleted, canonical copies in `scripts/`
- [x] **Fix stale docs** — Replaced `git pull` with SCP workflow in 5 files, updated Gemini→Claude, updated service names
- [x] **Remove committed secrets** — `config/.env` untracked, `twitter_health_check.py` sanitized (hardcoded token removed), `committee_autopsy.py` fixed (OpenRouter→Anthropic API)
- [x] **Updated VPS-diverged files** — `committee_outcomes.py` replaced with newer VPS version (Mar 6 vs Feb 25)
- **⚠️ Nick action items:** Rotate credentials from `config/.env` + Discord bot token from `twitter_health_check.py`/`pltr_alert.py` (still in git history). SCP fixed `committee_autopsy.py` to VPS.

### ✅ Phase 0B — Auth Lockdown (COMPLETE — March 10)
- [x] **Unified auth** — `require_api_key()` in `pivot_auth.py` accepts both `X-API-Key` and `Bearer` headers
- [x] **unified_positions.py** — Auth on 9 mutation routes (create, update, close, delete, bulk, reconcile, MTM, account-balance)
- [x] **committee_bridge.py** — Auth on POST `/committee/results`
- [x] **trade_ideas.py** — Auth on PATCH status + POST expire
- [x] **TradingView webhooks** — Optional `secret` field on all 4 handlers, validated against `TRADINGVIEW_WEBHOOK_SECRET` env var
- [x] **CORS** — Reads from `ALLOWED_ORIGINS` env var, defaults to `*`
- [x] **Frontend app.js** — `API_KEY` constant + `authHeaders()` helper, all 30 mutation fetch calls updated
- [x] **Cleanup** — Removed duplicate auth functions from `portfolio.py` and `macro.py`
- **⚠️ Nick action items:** Set `PIVOT_API_KEY` on Railway (if not already). Replace `PIVOT_KEY_PLACEHOLDER` in `app.js` with actual key. Optionally set `TRADINGVIEW_WEBHOOK_SECRET` + `ALLOWED_ORIGINS` on Railway.

### ✅ Phase 0C — Finish Positions Migration (COMPLETE — March 10)
- [x] **Killed in-memory state** — Removed `_open_positions`, `_closed_trades`, `_position_counter` from `positions.py`
- [x] **Rewrote `accept_signal()`** — Now writes directly to `unified_positions` table instead of old `positions` table
- [x] **Deleted 13 legacy position routes** — ~750 lines removed from `positions.py` (open, close, manual, history, debug, diagnose, force-sync, etc.)
- [x] **Removed startup sync** — `sync_positions_from_database()` deleted from `positions.py`, startup call removed from `main.py`
- [x] **Deleted v2↔legacy sync functions** — `sync_v2_to_legacy()` and `sync_legacy_to_v2()` removed from `unified_positions.py` + 3 calls removed from `portfolio.py`
- [x] **Frontend unified** — Removed `_open_positions_cache`, `renderPositions()`, legacy fetch/close/delete fallbacks. Manual position creation uses v2.
- [x] **Bonus fix** — `alerts.py` updated to read from `unified_positions` instead of deleted `_open_positions`
- **Total: 1,268 lines of dead code removed across 7 files**

### Phase 0D — Frontend Hygiene ← **NEXT**
- [ ] **Remove dead endpoint calls** — `/bias-auto/status`, `/bias-auto/shift-status`, `/bias-auto/CYCLICAL`, `/signals/ticker/{ticker}`
- [ ] **Audit hybrid scanner usage** — Identify which hybrid endpoints frontend still needs vs safe to delete
- [ ] **Consolidate polling intervals** — One interval per data type, remove duplicate refresh loops

### Phase 0E — Data Durability
- [ ] **Move decision_log to Postgres** (or SQLite on VPS) — JSONL kept as append-only audit
- [ ] **Move committee_log, outcome_log, lessons_bank** same way
- [ ] **Atomic write pattern** for any remaining JSONL appends (write temp → rename)

### Phase 0F — Resilience & Monitoring
- [ ] **Committee heartbeat** — Alert to Discord if no committee run in 2h during market hours
- [ ] **Factor staleness monitor** — Alert if any factor hasn't updated in 2× its expected TTL
- [ ] **Webhook dedup in tradingview.py** — Check signal_id before Postgres insert
- [ ] **Polygon degradation handling** — Return last-known value with stale flag instead of failing

### Phase 0G — Test Coverage (Sharp Edges Only)
- [ ] Auth enforcement tests (unauthenticated → 401)
- [ ] Webhook secret validation tests
- [ ] Position CRUD tests (create/close/reconcile via v2)
- [ ] Frontend route smoke test (every endpoint the UI calls returns non-404)

---

## 🟡 Immediate (Trading)

- [ ] **Confluence validation gate** — After 20 CONFIRMED/CONVICTION events fire during market hours, compare 24-hour outcomes vs 20 random STANDALONE signals. Success: confluence beats standalone by ≥12% win rate or ≥0.3R average. If not, reassess architecture.
- [ ] **Hub Sniper VWAP validation harness** — Run parallel TV + server-side VWAP on SPY for 5 trading days. Acceptance: mean error < 0.1%, max error < 0.5%. If fails, Hub Sniper stays on TV with 1 watchlist alert.
- [ ] **tick_breadth tuning** — Late session TICK close bounces still overpower bearish avg. Consider weighting avg 2:1 over close.

---

## 🟠 Phase 1: Trading Strategies Review — ~95% Complete

### ✅ Done (March 5-6-9 Sessions)

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
- [x] Portfolio positions table deprecated — GET /api/portfolio/positions now reads from unified_positions. Single source of truth. No more v2/portfolio sync bugs.

### 📋 Remaining

- [ ] **Hub Sniper server-side port (Phase A.3)** — Blocked on VWAP validation harness. Highest-risk port due to VWAP band sensitivity. If validation fails, Hub Sniper stays on TV.
- [ ] **Whale Hunter TV alert configuration** — Wire TV watchlist alert on top 50 tickers to `/webhook/whale`. Handler exists, needs TV setup.
- [ ] **UW Flow as independent signal source** — Currently context-only. High-conviction sweeps ($1M+) should trigger committee review directly. Needs threshold definition.
- [ ] **Gatekeeper threshold review** — Current: MAJOR=85, MINOR=70, NEUTRAL=60. Needs 4+ weeks outcome data to evaluate.
- [ ] **Confluence Phase C (combine PineScripts)** — Deferred. Merge Whale Hunter + Absorption Wall into 1 TV script. HIGH engineering risk, not needed yet.
- [ ] **breadth_intraday verification** — Confirm webhook fires and factor moves from STALE to active.
- [ ] **Shadow mode validation** — After 5 trading days, compare Holy Grail + Scout server-side vs TV signal overlap. Target ≥80%.

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

**Progress:** Outcome tracking operational. 9 outcomes now tracked (5 from nightly matcher + 4 manually backfilled March 9). Weekly review runs Saturday 9 AM MT. Close position P&L tracking now functional.

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
- [ ] **Whale Hunter remaining alerts** — Add per-chart alerts for full options watchlist
- [ ] **DST fix deployment** — Convert hardcoded UTC offsets to IANA timezones. Brief written, not deployed. IBKR not funded so pollers not active.
- [ ] **Drop `positions` and `open_positions` tables** — Now fully deprecated. All reads/writes go through `unified_positions`. Can drop after confirming zero callers.

---

## ✅ Completed (March 10, 2026) — Phase 0A + 0B + 0C

- [x] Phase 0A: Repo source of truth — 9 VPS scripts pulled, 8 untracked added, duplicates resolved, stale docs fixed in 5 files, `config/.env` untracked, `committee_autopsy.py` fixed (OpenRouter→Anthropic), `twitter_health_check.py` sanitized, `committee_outcomes.py` updated from VPS
- [x] Phase 0B: Auth lockdown — unified `require_api_key()`, auth on 9 position routes + committee results + trade ideas, TradingView webhook secret (optional), CORS env var, frontend `authHeaders()` on 30 calls, removed duplicate auth functions
- [x] Phase 0C: Positions migration complete — 1,268 lines removed. Killed in-memory `_open_positions`/`_closed_trades`, rewrote `accept_signal()` → unified_positions, deleted 13 legacy routes, removed startup sync, deleted `sync_v2_to_legacy()`/`sync_legacy_to_v2()`, frontend unified on v2, fixed `alerts.py` import

## ✅ Completed (March 9, 2026 Session) — 9 builds shipped

- [x] Exhaustion BULL suppression (bias-aware IGNORE when composite < -0.3)
- [x] Macro briefing updated for crisis (oil $108, Strait of Hormuz closed, stagflation regime)
- [x] PLTR alert DST-corrected (14:30→13:30 UTC for EDT)
- [x] Pivot Chat system prompt — data integrity rules, 4-agent committee format (TORO/URSA/TECHNICALS/PIVOT), signal pipeline awareness (Scout/CTA/Holy Grail/Absorption/Confluence), removed stale hardcoded balances, fixed 8→20 factors
- [x] Close position P&L tracking — frontend sends exit_value/trade_outcome/loss_reason/close_reason, v2 backend writes to closed_positions on full close, PATCH /api/portfolio/positions/closed/{id} backfill endpoint, trade exit detection on VPS (7 patterns)
- [x] Portfolio positions table deprecated — GET /api/portfolio/positions reads from unified_positions with _v2_to_legacy_dict() mapper, removed sync_v2_to_legacy() from MTM loop
- [x] RH balance corrected ($4,371.42 / $3,709.42 cash)
- [x] All positions synced — PLTR/TSLA/IWM/TOST closed, IBIT (2 positions) + NEM added, AMZN/XLF quantities corrected to 1
- [x] Closed trades P&L backfilled to outcome_log.jsonl — PLTR +$35, TSLA +$237, IWM +$94, TOST -$37 (total +$329, 3W/1L)

## ✅ Completed (March 6, 2026 Session) — 19 builds shipped

- [x] Full signal system health audit (389 trade ideas, 6 strategies, 9 CTA sub-types)
- [x] All 10 PineScripts backed up to repo + inventory doc
- [x] 5 missing strategy docs written (Holy Grail, Scout, Hub Sniper, Whale Hunter, Exhaustion)
- [x] Strategy backlog created (deferred/rejected/pending decisions/dead code)
- [x] Triple Line scrapped + dead code removed (345 lines)
- [x] Golden Touch fix deployed (50→30 days, 2.0→1.3x volume, 3-bar window)
- [x] ETF yfinance fix deployed (skip earnings for ETFs)
- [x] Signal Confluence Architecture designed + committee-reviewed
- [x] Confluence Engine live (Phase B) — 7 lens categories, 4-hour window, Discord alerts
- [x] Holy Grail server-side scanner live (Phase A.1) — 200+ tickers, shadow mode
- [x] Scout Sniper server-side scanner live (Phase A.2) — 200+ tickers, shadow mode
- [x] Absorption Wall wired (PineScript JSON + Railway handler + confluence lens)
- [x] Outcome tracking fix (removed 48h window, 5 decisions matched with P&L)
- [x] CTA selloff tweaks (VIX stops + zone-aware volume)
- [x] Holy Grail selloff tweaks (RSI bypass + VIX tolerance)
- [x] Scout selloff tweaks (bias-aware LONG suppression)
- [x] Committee data access fix (bias URL, portfolio, enhanced factors)
- [x] Committee prompts update (4-agent structure deployed to VPS)
- [x] Pivot Chat data access (11 sources: positions, balances, CB, sectors, trade ideas)
- [x] Auto-committee disabled (cron commented out)
- [x] Twitter scraper tokens refreshed + daily health check cron
- [x] PLTR trade analyzed (simulated committee), logged, position added to hub
- [x] PLTR Monday playbook alert scheduled (9:30 AM ET Discord)
- [x] Macro briefing file seeded on VPS (Iran war, oil, stagflation context)
- [x] Dead code cleanup (Triple Line, deprecated functions, old PineScript archived)
- [x] Trade logging pipeline (auto-detect trades, confirmation buttons, /log-trade, dual logging)
- [x] Macro narrative context (raw headlines, macro prices, regime briefing, /macro-update command)

## ✅ Completed (March 5, 2026 Session)

- [x] Scout signal levels (entry/stop/target passthrough from PineScript)
- [x] tick_breadth directional scoring (range-only → 60% direction / 40% range blend)
- [x] Circuit breaker scoring modifier fix + bias floor fix
- [x] Main bias display uses composite bias_level
- [x] Unblocked credit_spreads, market_breadth, sector_rotation, vix_term from PIVOT_OWNED
- [x] GEX recalibrated for Polygon Starter ($5B→$2B scale)
- [x] IV regime uses 52-week VIX range
- [x] spy_50sma_distance added as swing factor
- [x] spy_200sma_distance moved to macro
- [x] McClellan webhook endpoint
- [x] Breadth + McClellan TradingView alerts configured
- [x] Brief 08: RH/Fidelity account tabs
- [x] Brief 09: Hub feature cleanup (killed Strategy Filters + Hybrid Scanner UI)
- [x] Factor weight rebalance (20 factors, intraday 0.26, swing 0.34, macro 0.40)
