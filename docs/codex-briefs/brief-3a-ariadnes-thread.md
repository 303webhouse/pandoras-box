# Brief 3A: Ariadne's Thread — Canonical Signal-to-Outcome Model + Live Risk

## Summary

Define and implement the complete signal-to-outcome chain: Signal → Committee → Decision → Position → Outcome → Lesson → Risk Budget. This is the foundational data pipeline that all analytics depend on. Also unify live risk exposure onto `unified_positions` so the Strategos command view shows real-time account risk, not historical snapshots.

## The Canonical Model (Ariadne's Thread)

Every trade in the system should be traceable through this chain:

```
Signal (signals table)
  → Committee Review (committee_data on signal, optional)
  → Nick's Decision (TAKE / PASS / WATCHING via trade_ideas status)
  → Position (unified_positions, tagged with signal_id)
  → Outcome (WIN / LOSS / BREAKEVEN, computed on close)
  → Lesson (pattern extracted by weekly Hermes Dispatch)
  → Risk Budget (how much capacity consumed / remaining)
```

### Step 1: Signal-to-Position Linking

When Nick accepts a signal (clicks Take/Accept on Agora or Stater Swap), the resulting position in `unified_positions` must be tagged with `signal_id`.

**Check:** Does the accept flow already do this? Inspect:
- `frontend/app.js` — the accept/take handler. What data does it send when creating a position?
- `backend/api/trade_ideas.py` — the status update endpoint. Does it propagate `signal_id` to position creation?
- `backend/api/unified_positions.py` — the create position endpoint. Does it accept and store `signal_id`?

The `unified_positions` table already has a `signal_id` column (check `postgres_client.py` table creation). If the accept flow doesn't pass it through, wire it:

```python
# In the accept flow (wherever position is created from a signal)
position_data = {
    "ticker": signal["ticker"],
    "signal_id": signal["signal_id"],  # THIS IS THE LINK
    # ... other fields
}
```

For manual positions (entered without a signal), `signal_id` stays NULL. That's fine.

### Step 2: Auto-Resolve Outcomes on Position Close

When a position closes in `unified_positions` (status → CLOSED), automatically compute and store the outcome.

Add a post-close hook in `backend/api/unified_positions.py` in the `close_position` endpoint:

```python
async def _resolve_signal_outcome(position: dict):
    """
    When a position closes, resolve the outcome back to its originating signal.
    Part of Ariadne's Thread — the signal-to-outcome canonical chain.
    """
    signal_id = position.get("signal_id")
    if not signal_id:
        return  # Manual position, no signal to resolve

    entry = position.get("entry_price", 0)
    exit_price = position.get("exit_price", 0)
    direction = position.get("direction", "LONG")

    # Compute P&L
    if direction == "LONG":
        pnl_pct = ((exit_price - entry) / entry * 100) if entry else 0
    else:
        pnl_pct = ((entry - exit_price) / entry * 100) if entry else 0

    pnl_dollars = position.get("realized_pnl") or 0

    # Classify outcome
    if pnl_pct > 1.0:
        outcome = "WIN"
    elif pnl_pct < -1.0:
        outcome = "LOSS"
    else:
        outcome = "BREAKEVEN"

    # Compute MFE/MAE if price history available (optional enhancement)
    # For now, just store basic outcome

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE signals SET
                outcome = $2,
                outcome_pnl_pct = $3,
                outcome_pnl_dollars = $4,
                outcome_resolved_at = NOW()
            WHERE signal_id = $1
        """, signal_id, outcome, round(pnl_pct, 2), round(pnl_dollars, 2))

    logger.info(f"Ariadne: resolved {signal_id} → {outcome} ({pnl_pct:+.1f}%)") 
```

Call this at the end of the close_position endpoint, after the position status is updated.

### Step 3: Add Outcome Columns to Signals Table

If not already present, add these columns to the `signals` table via the auto-migration in `postgres_client.py`:

```sql
ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome TEXT;  -- WIN, LOSS, BREAKEVEN, EXPIRED
ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_pnl_pct FLOAT;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_pnl_dollars FLOAT;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome_resolved_at TIMESTAMPTZ;
```

### Step 4: Track Counterfactuals (Passed Signals)

For signals Nick PASSED on, track "what would have happened." This is simpler than it sounds:

Add a scheduled job (or extend the existing nightly outcome matcher) that checks PASSED/DISMISSED signals:

```python
async def resolve_counterfactuals():
    """
    For signals Nick passed on, check if price hit the target.
    Ariadne's Thread counterfactual: "what if I'd taken it?"
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Get dismissed signals with no outcome, from the last 14 days
        rows = await conn.fetch("""
            SELECT signal_id, ticker, direction, entry_price, target_1, stop_loss, created_at
            FROM signals
            WHERE status IN ('DISMISSED', 'EXPIRED')
            AND outcome IS NULL
            AND created_at > NOW() - INTERVAL '14 days'
            AND entry_price IS NOT NULL
            AND target_1 IS NOT NULL
        """)

    for row in rows:
        # Fetch price history since signal creation
        # Check if price hit target_1 or stop_loss first
        # Store as outcome = 'COUNTERFACTUAL_WIN' or 'COUNTERFACTUAL_LOSS'
        # This tells Nick: "you passed on this, and it would have won/lost"
        pass  # Implementation uses yfinance or cached price data
```

The counterfactual outcome goes in the same `outcome` column with distinct values (`COUNTERFACTUAL_WIN`, `COUNTERFACTUAL_LOSS`) so the Chronicle can display "signals you missed."

### Step 5: Live Risk Budget from Unified Positions

New endpoint: `GET /api/analytics/risk-budget`

Reads OPEN positions from `unified_positions` and computes real-time risk exposure:

```python
@router.get("/risk-budget")
async def get_risk_budget(account: Optional[str] = None):
    """
    Ariadne's Thread: live risk budget from the real book.
    Shows remaining capacity before hitting drawdown limits.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM unified_positions WHERE status = 'OPEN'
        """)

    positions = [dict(r) for r in rows]

    # Separate equity and crypto
    equity_positions = [p for p in positions if p.get("asset_type") != "CRYPTO"]
    crypto_positions = [p for p in positions if p.get("asset_type") == "CRYPTO"]

    # Equity risk
    equity_max_loss = sum(abs(p.get("max_loss") or 0) for p in equity_positions)
    equity_count = len(equity_positions)

    # Crypto risk (Breakout account specifics)
    breakout_balance = 25000  # TODO: make configurable or fetch from account
    breakout_static_dd = breakout_balance * 0.06  # $1,500
    breakout_daily_limit = breakout_balance * 0.04  # $1,000
    crypto_max_loss = sum(abs(p.get("max_loss") or 0) for p in crypto_positions)
    crypto_count = len(crypto_positions)
    breakout_remaining_dd = breakout_static_dd - crypto_max_loss
    breakout_remaining_daily = breakout_daily_limit  # TODO: track daily P&L

    return {
        "equity": {
            "open_positions": equity_count,
            "total_max_loss": round(equity_max_loss, 2),
            "capital_at_risk_pct": None,  # Need account balance context
        },
        "crypto": {
            "open_positions": crypto_count,
            "max_concurrent": 2,  # Breakout rule
            "total_max_loss": round(crypto_max_loss, 2),
            "breakout_static_dd_remaining": round(breakout_remaining_dd, 2),
            "breakout_daily_remaining": round(breakout_remaining_daily, 2),
            "can_open_new": crypto_count < 2 and breakout_remaining_dd > 250,
        },
        "combined": {
            "total_positions": equity_count + crypto_count,
            "total_max_loss": round(equity_max_loss + crypto_max_loss, 2),
        }
    }
```

### Step 6: Options-Specific Outcome Fields

When resolving outcomes for options positions, compute additional metrics:

```python
if position.get("asset_type") == "OPTION":
    outcome_data["options_metrics"] = {
        "structure": position.get("structure"),
        "dte_at_entry": position.get("dte_at_open"),  # if tracked
        "dte_at_exit": compute_dte(position.get("expiry"), position.get("closed_at")),
        "premium_at_risk": position.get("options_net_premium"),
        "max_loss_utilization": (pnl_dollars / position.get("max_loss", 1)) * 100 if position.get("max_loss") else None,
        "max_profit_utilization": (pnl_dollars / position.get("max_profit", 1)) * 100 if position.get("max_profit") else None,
        "exit_quality": "EARLY_PROFIT" if pnl_pct > 0 and compute_dte(position.get("expiry"), position.get("closed_at")) > 7 else
                        "HELD_TO_EXPIRY" if compute_dte(position.get("expiry"), position.get("closed_at")) <= 1 else
                        "STOPPED_OUT" if pnl_pct < -50 else "NORMAL",
    }
```

Store in a JSON column or as separate fields on the signal outcome.

## Files Modified

| File | Change |
|------|--------|
| `backend/api/unified_positions.py` | Add `_resolve_signal_outcome()` hook on close, add signal_id propagation |
| `backend/api/trade_ideas.py` | Verify signal_id passes through accept flow |
| `backend/analytics/api.py` | Add `/risk-budget` endpoint |
| `backend/database/postgres_client.py` | Add outcome columns to signals table migration |
| `frontend/app.js` | Verify accept handlers pass signal_id to position creation |

## Testing

1. Accept a signal in Agora → verify position has signal_id
2. Close that position → verify signal's outcome fields update
3. Dismiss a signal → verify counterfactual resolver can process it
4. Call `/api/analytics/risk-budget` → verify live position data
5. Close an options position → verify options-specific metrics
6. All existing tests pass (168+)

## Definition of Done

- [ ] Positions created from signals tagged with signal_id
- [ ] Position close triggers `_resolve_signal_outcome()` → updates signals table
- [ ] Outcome columns added to signals table (outcome, pnl_pct, pnl_dollars, resolved_at)
- [ ] Counterfactual resolver for passed/dismissed signals
- [ ] `/api/analytics/risk-budget` endpoint with live position data
- [ ] Breakout account risk budget (static DD remaining, daily remaining, can_open_new)
- [ ] Options outcome metrics (DTE tracking, premium utilization, exit quality)
- [ ] All existing tests pass
