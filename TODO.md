# Pivot — Priorities & TODO

**Last Updated:** March 6, 2026

---

## 🔴 Immediate (This Week)

- [ ] **Confluence validation gate** — After 20 CONFIRMED/CONVICTION events fire during market hours, compare 24-hour outcomes vs 20 random STANDALONE signals. Success: confluence beats standalone by ≥12% win rate or ≥0.3R average. If not, reassess architecture.
- [ ] **PLTR trade management** — Monday 9:30 AM ET alert scheduled. Watch open below $158 = hold, above $160 past 10 AM = exit. Position: 152.5p/147p spread, 3/13 expiry.
- [ ] **Verify Twitter scraper Monday AM** — Tokens refreshed March 6. Confirm tweets are flowing into `twitter_signals.jsonl` during market hours. Health check cron runs daily 10 AM ET.
- [ ] **Hub Sniper VWAP validation harness** — Run parallel TV + server-side VWAP on SPY for 5 trading days. Acceptance: mean error < 0.1%, max error < 0.5%. If fails, Hub Sniper stays on TV with 1 watchlist alert.
- [ ] **tick_breadth tuning** — Late session TICK close bounces still overpower bearish avg. Consider weighting avg 2:1 over close.

---

## 🟠 Phase 1: Trading Strategies Review — ~85% Complete

### ✅ Done (March 5-6 Sessions)

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
- [x] Golden Touch fix — thresholds relaxed (50→30 days, 2.0→1.3x volume, 3-bar window)
- [x] ETF yfinance fix — skip earnings check for ETFs, prevents committee crash on QQQ/SMH/IWM
- [x] Outcome tracking fix — removed 48h window, reads ALL decisions, 5 outcomes matched
- [x] Committee data access fix — bias URL corrected, portfolio verified, enhanced factor context
- [x] Committee prompts update — 4-agent TORO/URSA/TECHNICALS/PIVOT deployed to VPS
- [x] Pivot Chat data access — 11 data sources (positions, balances, CB, sectors, trade ideas)
- [x] Auto-committee disabled — cron commented out until confluence system dialed in
- [x] Dead code cleanup — Triple Line handler, deprecated functions, old PineScript archived
- [x] Twitter scraper tokens refreshed + daily health check cron added

### 🔧 Building Now

- [ ] **Trade logging pipeline** — Auto-detect when Nick takes a trade in Discord, prompt to confirm, write to decision_log.jsonl + Railway outcomes. `/log-trade` slash command backup. CC building.
- [ ] **Macro narrative context** — Raw headlines block, macro prices (oil, gold, 10Y, DXY), persistent regime briefing file. CC building.

### 📋 Remaining

- [ ] **Hub Sniper server-side port (Phase A.3)** — Blocked on VWAP validation harness. Highest-risk port due to VWAP band sensitivity. If validation fails, Hub Sniper stays on TV.
- [ ] **Whale Hunter TV alert configuration** — Wire TV watchlist alert on top 50 tickers to `/webhook/whale`. Handler exists, needs TV setup.
- [ ] **UW Flow as independent signal source** — Currently context-only. High-conviction sweeps ($1M+) should trigger committee review directly. Needs threshold definition.
- [ ] **Gatekeeper threshold review** — Current: MAJOR=85, MINOR=70, NEUTRAL=60. Needs 4+ weeks outcome data to evaluate.
- [ ] **Confluence Phase C (combine PineScripts)** — Deferred. Merge Whale Hunter + Absorption Wall into 1 TV script. HIGH engineering risk, not needed yet.
- [ ] **breadth_intraday verification** — Confirm webhook fires and factor moves from STALE to active.
- [ ] **Shadow mode validation** — After 5 trading days, compare Holy Grail + Scout server-side vs TV signal overlap. Target ≥80%.
- [ ] **Exhaustion BULL suppression** — Same pattern as Scout LONG suppression. Apply bias-aware IGNORE when composite < -0.3.

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

**Progress:** Outcome tracking now operational (5 matched outcomes). Weekly review runs Saturday 9 AM MT.

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
- [ ] **DST fix deployment** — Convert hardcoded UTC offsets to IANA timezones. Brief written, not deployed.

---

## ✅ Completed (March 6, 2026 Session)

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
