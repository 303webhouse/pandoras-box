# Pivot — Current Priorities

**Last Updated:** February 25, 2026

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

- [ ] **Phase 2F: UW Dashboard API scraping** — Replace manual screenshot analysis with structured API calls to Unusual Whales dashboard. Investigate UW API access. Brief not yet written.
- [ ] **Phase 2G: Auto-Scout** — Screen incoming UW flow + Alpha Feed ideas automatically, identify setups matching Playbook criteria, post formatted picks to Discord. Depends on Phase 2F.
- [ ] **Factor freshness in EOD brief** — Show which factors are fresh vs stale in daily summaries. Codex brief deployed.
- [ ] **Convergence summary in EOD brief** — Highlight when multiple independent sources agree. Codex brief deployed.

---

## 🟡 Medium Priority

- [ ] **Position close flow (Brief 10 Phase 2)** — Screenshot-based close detection OR typed exit data, CSV import dedup, frontend open positions panel with IBKR live P&L, closed_positions → performance metrics
- [ ] **Robinhood trade import** — CSV parser + signal matching to backfill historical trades into analytics. Codex brief deployed.
- [ ] **UW screenshot scheduler** — Auto-request screenshots at 10AM, 3PM, 4:05PM ET. Codex brief deployed.
- [ ] **DXY macro factor** — Dollar index as secondary confirmation signal (low weight). Codex brief deployed.
- [ ] **RVOL conviction modifier** — Add relative volume to Whale Hunter signal scoring. Codex brief deployed.
- [ ] **Stale factor reliability** — options_sentiment, put_call_ratio, savita_indicator have ongoing reliability issues.

---

## 🟢 Lower Priority

- [ ] **TICK-Whale cross-reference** — Cross-reference TICK breadth with Whale Hunter timing. Codex brief deployed.
- [ ] **Crypto sandbox** — Autonomous trading on Coinbase (~$150 account). Architecture not started.
- [ ] **Complex multi-leg tracking** — Iron condors, butterflies. `trade_legs` table exists but not wired.
- [ ] **Learning Protocol** — Self-correcting system where Pivot tracks recommendation accuracy and adjusts weighting. Designed but not implemented.

---

## 🎨 UI/UX (When Time Permits)

- [ ] Custom signal icons (APIS CALL, BULLISH TRADE, KODIAK CALL, BEAR CALL)
- [ ] Pivot logo design (dark teal + accent colors)
- [ ] Loading skeletons for signal cards
- [ ] Mobile optimization (bottom nav, pull-to-refresh)
- [ ] WebSocket connection quality indicator

---

## ✅ Recently Completed

- [x] **Brief 10: Position tracking gap fixes** — DB schema (signal_id, account columns, closed_positions table), partial sync flag, single position create endpoint, committee TAKE → screenshot prompt, IBKR cron activation, yfinance fallback pricer
- [x] **Signal persistence hardening** - Enforced DB-first signal persistence (webhooks and schedulers), skipped Redis/broadcast on DB write failure for scheduled signals, and fixed CTA `signal_outcomes.symbol` fallback to ticker
- [x] **SPY price feed fix** - Added SPY quote validation and fallback handling in `backend/bias_engine/factor_utils.py` to prevent split-scale mismatches from corrupting 9 EMA / 200 SMA factors (deploy verification pending)
- [x] Railway Postgres fix — moved to same project (fabulous-essence), linked via `${{Postgres.*}}`
- [x] Documentation overhaul — CLAUDE.md, CODEX.md, PROJECT_SUMMARY.md, PROJECT_RULES.md rewritten
- [x] DEVELOPMENT_STATUS.md — Full phase roadmap with system component inventory
- [x] Phase 2A-2E — Playbook, trade journal, DEFCON, market data, interactive chat all live
- [x] Analytics Phases 1-3 — Schema, API endpoints, 6-tab UI all deployed
- [x] Empty env var pattern — Documented and applied across codebase
