# Pivot — Priorities & TODO

**Last Updated:** March 5, 2026

---

## 🔴 Immediate (This Week)

- [ ] **Verify breadth_intraday fires tomorrow** — TradingView $UVOL/$DVOL alert set. Confirm first webhook hits Railway at 9:30 AM ET. Factor should move from STALE → active.
- [ ] **tick_breadth tuning** — Late session TICK close bounces still overpower bearish avg (-110 avg, +455 close → +0.58 bullish). Consider weighting avg 2:1 over close, or using a time-decay that discounts close in first 30 min of data.
- [ ] **Scout signal levels verification** — Fix deployed. Wait for next scout alert and confirm entry/stop/target/R:R appear on Trade Idea cards.

---

## 🟠 Phase 1: Trading Strategies Review (Weeks 1-2)

**Goal:** Audit what signals are actually getting through the bias system, whether they're reliable, and what's missing.

- [ ] **Signal flow audit** — Pull last 30 days of signals from `signal_outcomes` table. Which strategies generated signals? What % passed gatekeeper? What % were TAKE vs PASS? Win rate by strategy?
- [ ] **Strategy-signal type mapping** — Current signals come in as SCOUT_ALERT, BULLISH_TRADE, BEAR_CALL, HOLY_GRAIL_1H. Map these back to the actual TradingView indicators that generated them. Are any strategies silent (no signals in 30 days)?
- [ ] **UW flow integration depth** — UW Watcher captures flow to Redis (1h TTL). Committee sees it as context. But flow isn't generating trade ideas independently. Evaluate: should high-conviction UW flow (e.g., $1M+ sweep on a ticker in our watchlist) trigger committee review directly?
- [ ] **Neglected strategies** — Review `docs/approved-strategies/` and `docs/strategy-backlog.md`. Which approved strategies have no TradingView alert configured? Which backlog strategies should be promoted?
- [ ] **PineScript indicator health** — Are Hub Sniper, Scout Sniper, and Whale Hunter alerts still firing? Check TradingView alert log for last 7 days of activity per indicator.
- [ ] **Gatekeeper threshold review** — Current thresholds: MAJOR=85, MINOR=70, NEUTRAL=60. Are these too tight/loose based on actual signal volumes?

---

## 🟠 Phase 2: Crypto Scalper Review/Overhaul (Weeks 2-3)

**Goal:** Assess the crypto shell, determine what's working, what's orphaned, and build a real LTF scalping system.

- [ ] **Current state audit** — The crypto scalper UI exists (`/crypto` route) with BTC key levels, order flow, and strategy filters. What backend endpoints are active vs dead? What data is actually flowing?
- [ ] **Signal reliability** — What crypto signals are coming in? From where? Are they hitting the same webhook pipeline or a separate path?
- [ ] **LTF strategy implementation** — What strategies do we need for 1m-15m crypto/forex scalping? Evaluate: VWAP bounce, order flow imbalance, funding rate divergence, liquidation cascade detection.
- [ ] **Architecture decision** — "Single app, two shells" was approved. `/hub` (equities) and `/crypto` (scalping) sharing Railway backend. What's the cleanest path to make the crypto shell functional without disrupting the equity pipeline?
- [ ] **BTC session/bottom signal components** — Orphaned components from earlier builds. Reconnect or remove.
- [ ] **Exchange integration** — Coinbase sandbox (~$150). What API access do we have? Can we paper trade on Binance testnet for faster iteration?

---

## 🟠 Phase 3: Analytics Review/Overhaul (Weeks 3-4)

**Goal:** Make analytics accurate, visual, and self-improving.

- [ ] **Scoring accuracy audit** — Compare signal scores at time of generation vs actual outcomes. Is the 75+ threshold meaningful? Are HIGH confidence signals actually winning more than LOW?
- [ ] **Data visualization overhaul** — Current analytics tabs (Dashboard, Trade Journal, Signal Explorer, Factor Lab, Backtest, Risk) exist but are data-sparse and not visually engaging. Design a dashboard that shows: win rate trend, factor contribution heatmap, strategy P&L curve, committee accuracy over time.
- [ ] **Missing tracking** — What isn't being tracked? Candidates: time-to-fill after TAKE, slippage (signal entry vs actual fill), partial fills, position sizing compliance, DTE at entry vs exit.
- [ ] **Unified performance view** — Single page that answers "is this system making money?" Combine: position P&L, signal accuracy, factor reliability, committee agreement rate, override outcomes.
- [ ] **Self-improvement loop** — Pivot + Trading Committee already have weekly review (Saturday 9 AM MT) that generates lessons → `lessons_bank.jsonl` → injected into future committee context. Is this loop actually improving decisions? Audit lesson quality and committee behavior changes over time.
- [ ] **Outcome matcher reliability** — Nightly cron at 11 PM ET matches decisions to outcomes. Is it running? Are matches accurate? Check `outcome_log.jsonl` for completeness.
- [ ] **Robinhood trade import** — CSV parser exists but historical trades haven't been imported. Need this data for any meaningful backtesting.

---

## 🟠 Phase 4: Knowledge Base Cleanup (Week 4)

**Goal:** Complete overhaul after the massive changes in Feb-Mar 2026.

- [ ] **Audit existing KB entries** — Knowledge base was built before the bias system overhaul, committee training bible, position ledger, and signal pipeline rebuild. Most entries are stale or wrong.
- [ ] **Rebuild from current architecture** — Generate KB entries from: CLAUDE.md, DEVELOPMENT_STATUS.md, committee-training-parameters.md, factor-scoring.md, TRADING_HUB_API.md.
- [ ] **Agent training integration** — KB should be queryable by Pivot during chat. Currently it's a static frontend feature. Wire it into the OpenClaw knowledge system.
- [ ] **Strategy documentation** — Each approved strategy should have a KB entry with: entry criteria, exit rules, bias alignment requirements, historical win rate, and links to the PineScript indicator.

---

## 🟡 Ongoing / Lower Priority

- [ ] **IBKR account setup** — Fund account → create read-only API user → enable position polling
- [ ] **Brief 05B: Adaptive Calibration** — Dynamic thresholds + agent trust weighting. Needs 3+ weeks of outcome data.
- [ ] **Complex multi-leg tracking** — Iron condors, butterflies. `trade_legs` table exists but not wired.
- [ ] **Mobile optimization** — Bottom nav, pull-to-refresh, responsive position cards
- [ ] **Whale Hunter remaining alerts** — Add per-chart alerts for full options watchlist (17 tickers, partial done)
- [ ] **DST fix deployment** — Convert hardcoded UTC offsets to IANA timezones. Brief written, not deployed.

---

## ✅ Completed (Mar 5, 2026 Session)

- [x] Scout signal levels (entry/stop/target passthrough from PineScript)
- [x] tick_breadth directional scoring (range-only → 60% direction / 40% range blend)
- [x] Circuit breaker scoring modifier fix (was dampening bearish, now amplifies)
- [x] Circuit breaker bias floor fix (inverted comparison, never enforced)
- [x] Main bias display uses composite bias_level (not old daily system)
- [x] Unblocked credit_spreads, market_breadth, sector_rotation from PIVOT_OWNED
- [x] Unblocked vix_term from PIVOT_OWNED
- [x] GEX recalibrated for Polygon Starter ($5B→$2B scale, tighter bands)
- [x] IV regime uses 52-week VIX range (was broken 20-day rolling)
- [x] spy_50sma_distance added as swing factor (intermediate trend)
- [x] spy_200sma_distance moved to macro (structural trend)
- [x] McClellan webhook endpoint (`/webhook/mcclellan`)
- [x] Breadth + McClellan TradingView alerts configured
- [x] Brief 08: RH/Fidelity account tabs (All/RH/Fidelity toggle)
- [x] Brief 09: Hub feature cleanup (killed Strategy Filters + Hybrid Scanner, redesigned Options Flow → Headlines tabs)
- [x] Factor weight rebalance (20 factors, 1.00 sum: intraday 0.26, swing 0.34, macro 0.40)
