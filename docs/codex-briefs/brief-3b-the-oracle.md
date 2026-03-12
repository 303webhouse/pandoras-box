# Brief 3B: The Oracle — Insights Engine + Options Analytics

## Summary

Build The Oracle: a pre-computed insights engine that generates plain-English performance summaries, strategy scorecards, decision quality analysis, and options-specific analytics. Runs on a schedule, caches results, and serves them via a single endpoint. This replaces manual dashboard interpretation with computed answers.

Depends on Brief 3A (Ariadne's Thread) for outcome data.

## Architecture

New module: `backend/analytics/oracle_engine.py`

Scheduled to run every hour during market hours, daily during off-hours. Results cached in Redis with 1-hour TTL.

Single endpoint: `GET /api/analytics/oracle?days=30&account=&asset_class=`

Returns the full pre-computed payload. Frontend just renders it.

## The Oracle Payload

```python
{
    "computed_at": "2026-03-12T15:00:00Z",
    "narrative": "Holy Grail is your best performer this month...",  # AI-generated

    "system_health": {
        "overall_grade": "B+",
        "pnl_total": 1240.50,
        "pnl_equity": 890.00,
        "pnl_crypto": 350.50,
        "win_rate": 0.548,
        "expectancy": 18.50,  # avg $ per trade
        "profit_factor": 1.65,
        "max_drawdown_pct": 3.2,
        "max_consecutive_losses": 3,
        "current_streak": {"type": "WIN", "count": 3},
        "trajectory": "IMPROVING",  # IMPROVING, STABLE, DECLINING
        "total_trades": 42,
        "total_signals": 380,
        "take_rate": 0.11,  # 11% of signals taken
    },

    "strategy_scorecards": [
        {
            "strategy": "Holy_Grail",
            "display_name": "Holy Grail",
            "signals": 85,
            "taken": 12,
            "wins": 8,
            "losses": 4,
            "win_rate": 0.667,
            "expectancy": 32.50,
            "total_pnl": 390.00,
            "best_trade": {"ticker": "NVDA", "pnl": 120.00},
            "worst_trade": {"ticker": "AAPL", "pnl": -85.00},
            "avg_rr_achieved": 1.8,
            "grade": "A",
        },
        # ... more strategies
    ],

    "decision_quality": {
        "total_decisions": 45,
        "overrides": 8,  # Nick took when committee said PASS, or passed when TAKE
        "override_win_rate": 0.625,
        "override_net_pnl": 35.00,
        "committee_agreement_rate": 0.72,
        "best_override": {"ticker": "NVDA", "pnl": 120.00, "committee_said": "PASS"},
        "worst_override": {"ticker": "AAPL", "pnl": -85.00, "committee_said": "TAKE"},
        "passed_would_have_won": 12,  # counterfactuals
        "passed_would_have_lost": 18,
    },

    "options_analytics": {
        "total_options_trades": 28,
        "by_structure": {
            "put_debit_spread": {"count": 12, "win_rate": 0.58, "avg_pnl": 45.00},
            "call_debit_spread": {"count": 8, "win_rate": 0.50, "avg_pnl": 22.00},
            # ...
        },
        "avg_dte_at_entry": 28,
        "avg_dte_at_exit": 14,
        "early_exits": 8,  # closed before 50% of DTE elapsed
        "held_to_expiry": 3,
        "avg_max_loss_utilization": 0.35,  # avg 35% of max loss realized on losers
        "avg_max_profit_utilization": 0.42,  # avg 42% of max profit captured on winners
        "best_structure": "put_debit_spread",
        "worst_structure": "call_debit_spread",
    },

    "factor_attribution": {
        "most_predictive_bullish": {"factor": "tick_breadth", "win_rate_when_bullish": 0.72},
        "most_predictive_bearish": {"factor": "spy_200sma", "win_rate_when_bearish": 0.68},
        "least_predictive": {"factor": "excess_cape", "correlation_with_outcome": 0.02},
        "regime_performance": {
            "TORO_MINOR": {"trades": 15, "win_rate": 0.60},
            "URSA_MINOR": {"trades": 8, "win_rate": 0.50},
            "NEUTRAL": {"trades": 19, "win_rate": 0.53},
        }
    }
}
```

## AI Narrative Generation

Use Claude Haiku to generate the `narrative` field. Pass the computed metrics as context:

```python
async def generate_oracle_narrative(metrics: dict) -> str:
    """
    Generate a plain-English performance summary using Haiku.
    The Oracle speaks — concise, actionable, honest.
    """
    prompt = f"""
    You are The Oracle, the AI performance analyst for a trading system.
    Generate a 3-4 sentence performance summary from these metrics.
    Be direct, specific, and actionable. Use exact numbers.
    If performance is declining, say so. If a strategy is failing, name it.
    If the trader is overriding the committee profitably, acknowledge it.

    Metrics (last {metrics.get('days', 30)} days):
    {json.dumps(metrics, indent=2, default=str)}

    Respond with ONLY the summary text, no JSON, no markdown.
    """
    # Call Haiku via Anthropic API
    # ~$0.001 per narrative
```

The narrative refreshes hourly. Cost: ~$0.024/day.

## Strategy Scorecard Computation

```python
async def compute_strategy_scorecards(days: int = 30) -> list:
    """Compute per-strategy performance from resolved signal outcomes."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT strategy, outcome, outcome_pnl_dollars, outcome_pnl_pct,
                   ticker, direction, score, bias_alignment
            FROM signals
            WHERE outcome IS NOT NULL
            AND outcome NOT LIKE 'COUNTERFACTUAL%'
            AND created_at > NOW() - INTERVAL '1 day' * $1
        """, days)

    # Group by strategy, compute win rate, expectancy, P&L, grade
    # Grade: A (>60% WR + positive expectancy), B (>50% WR), C (<50%), F (<40%)
```

## Options-Specific Analytics

Query `unified_positions` with `asset_type='OPTION'` and join with signal outcomes:

```python
async def compute_options_analytics(days: int = 30) -> dict:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.*, s.outcome, s.outcome_pnl_dollars, s.outcome_pnl_pct
            FROM unified_positions p
            LEFT JOIN signals s ON p.signal_id = s.signal_id
            WHERE p.asset_type = 'OPTION'
            AND p.created_at > NOW() - INTERVAL '1 day' * $1
        """, days)

    # Compute:
    # - Win rate by structure (put_debit_spread, call_debit_spread, etc.)
    # - Average DTE at entry and exit
    # - Max loss utilization (how much of max_loss was realized on losers)
    # - Max profit utilization (how much of max_profit was captured on winners)
    # - Exit quality distribution (EARLY_PROFIT, HELD_TO_EXPIRY, STOPPED_OUT)
    # - Best/worst structure by expectancy
```

## Factor Attribution (Outcome-Linked)

Reorient factor analytics from "factor vs SPY" to "factor vs trade quality":

```python
async def compute_factor_attribution(days: int = 30) -> dict:
    """
    For each bias factor value at signal creation time,
    what was the subsequent trade outcome?
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Get signals with outcomes that have factor snapshots
        rows = await conn.fetch("""
            SELECT s.signal_id, s.outcome, s.outcome_pnl_pct, s.strategy,
                   s.score_v2_factors, s.direction, s.bias_alignment
            FROM signals s
            WHERE s.outcome IS NOT NULL
            AND s.outcome NOT LIKE 'COUNTERFACTUAL%'
            AND s.score_v2_factors IS NOT NULL
            AND s.created_at > NOW() - INTERVAL '1 day' * $1
        """, days)

    # For each factor in score_v2_factors:
    #   - When factor was bullish and signal was LONG → win rate?
    #   - When factor was bearish and signal was SHORT → win rate?
    #   - Factor contribution correlation with outcome
    # Rank factors by predictive power
```

Keep SPY benchmark as context ("factor X moved, SPY moved similarly") but promote outcome correlation as the primary metric.

## Cache Strategy

Store computed Oracle payload in Redis:
```python
REDIS_KEY = "oracle:insights:{days}:{account}:{asset_class}"
TTL = 3600  # 1 hour
```

The scheduler recomputes every hour. The endpoint serves cached data.

## Scheduler

Add to Railway's scheduler (in `main.py` lifespan or `backend/scheduler/`):

```python
# Oracle refresh — hourly during market hours, every 4 hours otherwise
# Runs for all three asset_class variants: ALL, EQUITY, CRYPTO
async def refresh_oracle():
    for asset_class in [None, "EQUITY", "CRYPTO"]:
        for days in [7, 30, 90]:
            payload = await compute_oracle_payload(days=days, asset_class=asset_class)
            cache_key = f"oracle:insights:{days}:{asset_class or 'ALL'}"
            await redis.set(cache_key, json.dumps(payload, default=str), ex=3600)
```

## Files

| File | Change |
|------|--------|
| `backend/analytics/oracle_engine.py` | NEW — all computation + narrative generation |
| `backend/analytics/api.py` | Add `/oracle` endpoint |
| `backend/scheduler/` or `main.py` | Add hourly Oracle refresh job |

## Definition of Done

- [ ] `oracle_engine.py` computes full payload (health, scorecards, decisions, options, factors)
- [ ] AI narrative generated by Haiku (~$0.001/call)
- [ ] Strategy scorecards with grade (A/B/C/F), expectancy, best/worst trade
- [ ] Decision quality: override rate, override P&L, counterfactual analysis
- [ ] Options analytics: by structure, DTE tracking, exit quality, max loss/profit utilization
- [ ] Factor attribution linked to outcomes, not just SPY movement
- [ ] Cached in Redis, refreshed hourly
- [ ] `GET /api/analytics/oracle` serves pre-computed payload
- [ ] Equity/crypto split supported via query param
- [ ] All existing tests pass
