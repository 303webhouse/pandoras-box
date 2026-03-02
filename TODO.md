# Pivot — Current Priorities

**Last Updated:** March 2, 2026

Prioritized list of what needs building, fixing, or improving. For full phase details, see `DEVELOPMENT_STATUS.md`.

---

## 🔴 Critical Fixes

- [ ] **IBKR Account Setup (Nick manual task)** — Sequence: fund account → create read-only API user → give credentials to Pivot. Steps:
  1. Fund the IBKR account (gateway won't authenticate until funded)
  2. Client Portal → Profile icon → Settings → Users & Access Rights → click + to add user
  3. Username: `pivot-api`, strong password, your email
  4. Permissions: **Disable** all Trading Access and Funding Access. **Enable** Reporting Access (Activity Statements, Flex Queries, PortfolioAnalyst, Margin Reports) and Account Settings (Account Details, Financial Information)
  5. Complete email verification immediately (code expires fast)
  6. E-sign Proof of Trader Authority if prompted
  7. IBKR approves next business day
  8. Give username + password to Pivot → update ibeam credentials → flip the switch

---

## 🟠 High Priority (Next Up)

- [ ] **Phase 3: New Scanner Builds** — 9 new scanners for the Trade Ideas system. Specs not yet written.
- [ ] **Phase 2F: UW Dashboard API scraping** — Replace manual screenshot analysis with structured API calls to Unusual Whales dashboard. Investigate UW API access. Brief not yet written.
- [ ] **Phase 2G: Auto-Scout** — Screen incoming UW flow + Alpha Feed ideas automatically, identify setups matching Playbook criteria, post formatted picks to Discord. Depends on Phase 2F.
- [ ] **Factor freshness in EOD brief** — Show which factors are fresh vs stale in daily summaries. Codex brief deployed.
- [ ] **Convergence summary in EOD brief** — Highlight when multiple independent sources agree. Codex brief deployed.
- [ ] **Brief 05B: Adaptive Calibration** — Dynamic thresholds + agent trust weighting for Trading Team. Needs ~3 weeks of accumulated outcome data.

---

## 🟡 Medium Priority

- [ ] **Position close flow (Brief 10 Phase 2)** — Screenshot-based close detection OR typed exit data, CSV import dedup, frontend open positions panel with IBKR live P&L, closed_positions → performance metrics
- [ ] **Robinhood trade import** — CSV parser + signal matching to backfill historical trades into analytics. Codex brief deployed.
- [ ] **UW screenshot scheduler** — Auto-request screenshots at 10AM, 3PM, 4:05PM ET. Codex brief deployed.
- [ ] **Brief 07: Watchlist Re-Scorer** — Re-evaluate WATCHING decisions on timer. Spec not yet written.
- [ ] **Brief 08-09: Librarian** — Knowledge base + agent training loop. Specs not yet written.
- [ ] **TICK-Whale cross-reference** — Cross-reference TICK breadth with Whale Hunter timing. Codex brief deployed.
- [ ] **Remaining Whale Hunter per-chart alerts** — Add Dark Pool Whale Hunter v2 alerts to remaining tickers from options list (17 total, partial done).

---

## 🟢 Lower Priority

- [ ] **Crypto sandbox** — Autonomous trading on Coinbase (~$150 account). Architecture not started.
- [ ] **Complex multi-leg tracking** — Iron condors, butterflies. `trade_legs` table exists but not wired.
- [ ] **Learning Protocol** — Self-correcting system where Pivot tracks recommendation accuracy and adjusts weighting. Designed but not implemented.
- [ ] **UW watcher bot** — Lightweight service to monitor UW/whale Discord channels and forward parsed data to Pandora API (no LLM needed).

---

## 🎨 UI/UX (When Time Permits)

- [ ] Custom signal icons (APIS CALL, BULLISH TRADE, KODIAK CALL, BEAR CALL)
- [ ] Pivot logo design (dark teal + accent colors)
- [ ] Loading skeletons for signal cards
- [ ] Mobile optimization (bottom nav, pull-to-refresh)
- [ ] WebSocket connection quality indicator

---

## ✅ Recently Completed (Mar 1-2)

- [x] **Trade Ideas 4-Phase Overhaul** — Complete rebuild of signal intake → scoring → committee pipeline. Phase 1: unified signal intake. Phase 2: scoring v2 engine. Phase 3: CTA scanner refactor. Phase 4: VPS bridge + committee integration. All deployed to Railway + VPS.
- [x] **Phase 2 Master Fix List (45 fixes)** — Brief 2A: TICK breadth (5 fixes). Brief 2B: CTA scanner (8 fixes). Brief 2C: PineScript indicators (16 fixes across 3 scripts). Brief 2D: cross-cutting (13 fixes). 2 deferred (L6/L7 Dark Pool rename), 1 killed (Exhaustion Levels).
- [x] **PineScript v2 Indicators** — Hub Sniper v2.1 (confirmation candles, wider stops, time filter, ADX regime, fixed R targets). Scout Sniper v3.1 (time filter, SMA regime, structural awareness, quality score, R-multiple targets). Dark Pool Whale Hunter v2 (RVOL floor, lunch filter, 3-bar match, structural context, trade framework, regime overlay).
- [x] **TradingView Alerts Configured** — Hub Sniper watchlist alert #1 (15m), Scout Sniper watchlist alert #2 (15m), Whale Hunter per-chart alerts (5m, partial).
- [x] **Whale Hunter Confluence Pipeline** — Whale webhook caches in Redis (30 min TTL), committee context builder fetches recent whale hits for ticker under review, renders "WHALE VOLUME DETECTED" section in committee prompt. Full end-to-end verified.
- [x] **Committee Training Bible + v2 Prompts** — 89-rule reference doc across 12 sections. All 4 agents rewritten to cite Bible rules by number. Net -15% prompt lines.

## ✅ Previously Completed (Feb 23-27)

- [x] **Brief 10: Unified Position Ledger** — Replaced 3 fragmented tables with unified_positions, 10-endpoint v2 API, options-aware frontend, portfolio summary widget, Polygon mark-to-market, committee context integration
- [x] **Polygon.io Integration** — Options Starter + Stocks Starter ($58/mo total). Real spread P&L, portfolio greeks, NTM-filtered chains, 3 new bias factors (polygon_pcr, polygon_oi_ratio, iv_regime)
- [x] **Bias System Overhaul (Tier 1+2)** — 22 factors (removed 4 dead, added 3 new), weights normalized to 1.00, None-not-zero pattern, Redis TTL per-factor, stale key cleanup, self-healing PCR
- [x] **Circuit Breaker Overhaul** — Condition-verified decay, state machine, no-downgrade guard, Discord notifications, dashboard accept/reject, spy_up_2pct direction fix
- [x] **RVOL Conviction Modifier** — Asymmetric amplification (bearish 1.20x, bullish 1.10x), hysteresis, confidence gate
- [x] **Committee dpg/GEX Training** — All 4 agents retrained with convexity-first philosophy, debit default, fractional Kelly sizing
- [x] **Cost Reduction** — OpenRouter → Direct Anthropic API, trade poller */2→*/15, session cleanup, ~$1/day
- [x] **Brief 06A: Twitter Sentiment** — Committee context + chatbot skill + Citrini7 account
- [x] **Position Tracking Gap Fixes** — signal_id/account columns, partial sync, closed_positions table, IBKR cron activation
- [x] **Savita Persistence Fix** — PUT endpoint writes to composite engine + recomputes bias
- [x] **Frontend Fixes** — Position modal overlay, signal card HTML corruption, P&L display, timeframe labels, momentum delta threshold, custom structures, edit modal falsy zero
- [x] **DXY macro factor** — Merged into dxy_trend (8 DXY+VIX combinations) during Tier 2 overhaul
- [x] **RVOL conviction modifier** — Deployed as part of Tier 2 overhaul
- [x] **Stale factor reliability** — options_sentiment removed, put_call_ratio self-heals via Polygon, savita TTL extended
