# Key Files Reference

Quick lookup for file purposes. Read when you need to find where something lives.

---

## Backend Core

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app — all routers, webhooks, WebSocket, background loops |
| `backend/bias_engine/composite.py` | Factor registration, weights (sum=1.00), composite bias calculation |
| `backend/bias_engine/factor_scorer.py` | Score computation, Redis caching, None handling, stale key cleanup |
| `backend/bias_engine/polygon_options.py` | Polygon.io options client (chains, greeks, spreads, NTM filtering) |
| `backend/webhooks/circuit_breaker.py` | Circuit breaker (condition-verified decay, state machine, no-downgrade) |
| `backend/webhooks/tradingview.py` | TradingView webhook receiver + /webhook/breadth |
| `backend/webhooks/whale.py` | Whale Hunter webhook + Redis caching + GET /whale/recent/{ticker} |
| `backend/api/unified_positions.py` | Position ledger API (10 endpoints, route ordering matters) |
| `backend/positions/risk_calculator.py` | Options structure risk calculation (max loss, breakeven) |
| `backend/api/analytics.py` | Analytics API endpoints |
| `backend/analytics/computations.py` | Analytics computation logic |
| `backend/analytics/db.py` | Analytics database queries |
| `backend/strategies/crypto_setups.py` | BTC setup engine (3 strategies) |
| `backend/strategies/btc_market_structure.py` | Crypto market structure filter |

## Frontend

| File | Purpose |
|------|---------|
| `frontend/app.js` | Main dashboard (bias cards, signals, positions, circuit breaker banner) |
| `frontend/analytics.js` | Analytics UI (6 tabs: Dashboard, Journal, Signal Explorer, Factor Lab, Backtest, Risk) |
| `frontend/index.html` | Dashboard HTML shell |

## VPS / Trading Team

| File | Purpose |
|------|---------|
| `scripts/pivot2_committee.py` | Committee orchestrator + gatekeeper + whale context fetch |
| `scripts/committee_context.py` | Market data enrichment + bias challenge + lessons + twitter + whale |
| `scripts/committee_prompts.py` | 4 agent system prompts (Bible-referenced) |
| `scripts/committee_parsers.py` | call_agent() + response parsers (Anthropic API direct) |
| `scripts/committee_decisions.py` | Decision logging, disk-backed pending store, buttons |
| `scripts/committee_interaction_handler.py` | Discord bot for button clicks, modal, reminders |
| `scripts/committee_outcomes.py` | Nightly outcome matcher |
| `scripts/committee_analytics.py` | Pattern analytics computation |
| `scripts/committee_review.py` | Weekly self-review + lessons bank |
| `scripts/committee_autopsy.py` | Post-trade narrative generation |
| `scripts/pivot2_brief.py` | Morning/EOD briefs (Sonnet) |
| `scripts/pivot2_twitter.py` | Twitter sentiment (30+ accounts, Haiku scoring) |

## Docs

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Agent guidance — architecture, patterns, deployment |
| `PROJECT_RULES.md` | Prime directive, review teams, workflow rules |
| `DEVELOPMENT_STATUS.md` | Factor table, signal pipeline, known issues |
| `docs/TRADING_TEAM_LOG.md` | Trading Team build status log |
| `docs/committee-training-parameters.md` | 89-rule Training Bible for committee agents |
| `pivot/llm/playbook_v2.1.md` | Risk rules, account details, strategy specs |
| `docs/approved-strategies/` | All approved LTF execution strategies |
| `docs/approved-bias-indicators/` | All approved bias indicator models |
