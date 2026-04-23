# Backtest Module — Mini-Brief for Titans Review

**Type:** Pre-build scoping brief (Titans reviews before CC brief is written)
**Status:** Draft for Titans Pass 1

---

## 1. Why We Need This

Before adding any Raschke strategy (Turtle Soup, Anti, 80-20, etc.) to live signal generation, we need to prove the edge hasn't decayed since Raschke's original research (mostly pre-2015). We also need to validate our **flow-augmentation hypothesis** — that adding UW flow/dark pool confluence to vanilla Raschke setups improves expectancy.

Without a backtest module, we're guessing. With one, we have quantitative go/no-go gates for every strategy addition, forever.

---

## 2. Scope (Tight — Intentionally)

**IN SCOPE:**
- Retrospective testing of bar-pattern strategies (Turtle Soup, 80-20, Holy Grail, Anti) on historical OHLCV
- Incorporation of UW historical data where available (flow, dark pool, GEX) for confluence-augmented variants
- Output: win rate, avg R-multiple, max drawdown, expectancy, Sharpe, profit factor — per strategy per symbol per timeframe
- Walk-forward analysis to detect overfitting (split train/test chronologically, not randomly)
- Comparison mode: **vanilla strategy vs. flow-augmented strategy** — the core question we need answered
- Export results to a DB table `backtest_results` for dashboard display later

**OUT OF SCOPE (YAGNI — do not build now):**
- Live papertrading / real-time simulation
- Order fill modeling beyond mid-price with configurable slippage
- Monte Carlo / bootstrap confidence intervals (Phase 2 if needed)
- GUI for running backtests (CLI + DB write is enough)
- Generic strategy framework (build ONLY for the Raschke strategies; generalize later if warranted)
- Options strategy backtesting (equities/ETF first; options leg is Phase 2)

---

## 3. Data Requirements (Critical Path — Verify Before Build)

### 3.1 yfinance historical OHLCV
Daily: abundant. Intraday (1m/5m/15m): limited to last ~60 days for 1m, ~730 days for 5m+. **Constraint:** intraday backtests >2 years may be impossible without a paid data vendor. Mitigation: daily-timeframe backtest for all strategies first; intraday variants tested on whatever history yfinance provides.

### 3.2 UW historical data — THE CRITICAL UNKNOWN

**Titans must verify before approving build:**
- How far back does UW basic plan ($150/mo) provide historical flow alerts, dark pool prints, GEX snapshots?
- Is historical data queryable via the MCP / API, or live-only?
- If historical depth is <6 months: the "flow-augmented" backtest is impossible and we must either (a) start logging UW data now to build a proprietary history, or (b) scope the flow augmentation as forward-test only.

**This single question determines whether the flow-augmentation hypothesis can be retrospectively validated or must be tested forward.** AEGIS + ATLAS please resolve before Pass 2.

### 3.3 VIX historical
Available via yfinance (`^VIX`). Trivial.

### 3.4 Value area / market profile data
If Pythia's value area data is calculable from OHLCV alone (it is, via TPO reconstruction), we can backtest VAH/VAL confluence. If it requires historical tick data, it's harder. Pythia agent to confirm.

---

## 4. Proposed Architecture (Titans to Critique)

```
backend/
  backtest/
    __init__.py
    engine.py             # core backtest loop, walk-forward
    data_loader.py        # yfinance + UW historical pulls
    strategies/
      holy_grail.py       # signal logic, reusable with live code
      turtle_soup.py
      eighty_twenty.py
      anti.py
    confluence/
      flow_augment.py     # wraps strategy signals with UW flow filter
      pythia_augment.py   # wraps with VAH/VAL filter
      vix_regime.py       # regime gate
    reporting/
      metrics.py          # win rate, R-multiple, Sharpe, etc.
      export.py           # writes to backtest_results DB table
    cli.py                # `python -m backend.backtest --strategy turtle_soup --symbol SPY --start 2020-01-01`
```

**Key design question for ATLAS:** should strategy logic live in ONE place (shared between backtest and live signal gen), or duplicated? Strong preference for shared — otherwise backtest results won't match live behavior. But shared requires live strategy code to be refactored to be callable from backtest without side effects.

**Key design question for HELIOS:** what does the backtest results dashboard look like? (Phase 2, but think ahead.) Suggest: grid view of strategies × symbols with color-coded expectancy, drill-down to per-trade log.

**Key design question for AEGIS:** historical UW pulls — rate limits, caching, data retention, credentials. Don't want backtest runs burning our live API quota. Local cache required.

**Key question for ATHENA:** is this a VPS-run job (nightly backtest, results to DB) or on-demand (Nick runs it from hub UI)? I lean nightly + DB-backed with on-demand re-runs possible. Titans confirm.

---

## 5. Minimum Viable Output

A single backtest run produces:

```
Strategy: Turtle Soup (vanilla)
Symbol: SPY
Timeframe: Daily
Period: 2020-01-01 to 2026-04-01
Trades: 47
Win Rate: 58.3%
Avg Winner: +1.8R
Avg Loser: -1.0R
Expectancy: +0.64R per trade
Max Drawdown: -6.2R
Profit Factor: 2.5
Sharpe (annualized): 1.1
---
Strategy: Turtle Soup (+ UW flow confluence)
Symbol: SPY
Timeframe: Daily
Period: [same]
Trades: 19  [fewer fires because flow filter is strict]
Win Rate: 73.7%
Avg Winner: +2.1R
Avg Loser: -1.0R
Expectancy: +1.28R per trade
Max Drawdown: -3.1R
Profit Factor: 4.2
Sharpe (annualized): 1.8
```

Comparison rows make it obvious whether flow augmentation is additive edge or just noise.

---

## 6. Decision Gates (Built into the Module)

Per strategy, we need pre-defined thresholds for GO / NO-GO:

- **GO live:** expectancy > +0.5R per trade, win rate > 45%, profit factor > 1.5, max DD < 10R, trade count > 30 over test period
- **GO live with caveats:** expectancy +0.25 to +0.5R, other metrics OK — size small, watch closely
- **NO-GO:** expectancy < +0.25R OR win rate < 40% OR max DD > 15R

These are defaults. Olympus can tune per-strategy.

---

## 7. Phase Plan

**Phase 1 (MVP):** Engine + data loader + one strategy (Turtle Soup, vanilla) + reporting. Prove the architecture works. **Target: 1 week of CC time after Titans approval.**

**Phase 2:** Add Holy Grail, 80-20, Anti. Add flow-augmentation wrapper. **Target: 1 week.**

**Phase 3:** Walk-forward, Pythia confluence, VIX regime gate, dashboard. **Target: 1-2 weeks.**

**Phase 4:** Deprecation checker — run backtest on EXISTING system strategies that Raschke additions might replace. Quantitatively validate the REPLACE decisions from the strategy evaluation doc.

Phase 4 is the one that closes the loop on the anti-bloat goal. Don't skip it.

---

## 8. Titans — Questions to Answer in Pass 1

- **ATLAS:** is the shared strategy-code architecture workable, or do we accept a small amount of duplication between backtest and live?
- **AEGIS:** UW historical data access plan + credentials handling + rate-limit safety + local caching strategy.
- **HELIOS:** dashboard wireframe for Phase 3 (rough).
- **ATHENA:** VPS-scheduled vs on-demand vs both. Priority vs. other builds in the queue. Decision.

---

## 9. Out of Scope Reminder (Resist Scope Creep)

- No ML, no parameter optimization search (that's overfitting machine number one)
- No live trading connection
- No multi-asset portfolio backtest (single strategy, single symbol at a time for V1)
- No news-event backtesting (News Reversal strategy) until UW news data's historical depth is confirmed

---

## 10. Success Criteria

This build is done when Nick can type one command and get a statistically honest answer to: **"Does Turtle Soup with UW flow confluence have edge on SPY daily over the last 6 years, and by how much?"** Anything beyond that is Phase N+1.
