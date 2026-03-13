# Fix: Signal Redundancy Filter for Scan-Based Strategies

## Problem

The "supporting signals" section on grouped Trade Ideas cards shows every trigger from scan-based strategies like Holy Grail — even if the same condition fires every scan cycle all day in choppy markets. This inflates `signal_count`, distorts confluence scoring, and clutters the UI with noise.

**Root cause**: Holy Grail is a *condition-based* indicator (ADX > 25 + RSI pullback to EMA). When conditions persist across multiple scan cycles, each cycle creates a new `signals` DB row. The grouped endpoint collects ALL of them as separate "supporting signals" for the same ticker+direction.

## Fix Location

**One file**: `backend/api/trade_ideas.py`
**One function**: `get_trade_ideas_grouped()`

No ingestion changes, no DB schema changes, no frontend changes.

## Strategy

Dedup at the **grouping query level**, not at ingestion. This:
- Preserves all raw signal data in DB (no data loss for backtesting)
- Fixes the UI display and scoring without touching the webhook pipeline
- Is safe and reversible

## Implementation

### Step 1: Add strategy cooldown config at module level

**FIND** (near top of file, after the imports):
```python
logger = logging.getLogger(__name__)
router = APIRouter()
```

**REPLACE WITH**:
```python
logger = logging.getLogger(__name__)
router = APIRouter()

# ── Scan-based strategy dedup ─────────────────────────────────────────
# Strategies that fire on every scan cycle when conditions persist.
# For these, only the NEWEST signal per ticker+direction within the
# cooldown window counts toward grouping. Others are collapsed.
# Key: strategy name (lowercase), Value: cooldown in minutes.
SCAN_STRATEGY_COOLDOWNS = {
    "holy_grail": 240,       # 4 hours — condition-based, fires every scan in chop
    "holygrail": 240,
    "holy_grail_15m": 240,
    "holy_grail_1h": 240,
    "cta_scanner": 120,      # 2 hours
    "exhaustion": 180,       # 3 hours — can re-fire in extended moves
    "exhaustion_bull": 180,
    "exhaustion_bear": 180,
}
```

### Step 2: Add dedup helper function

**FIND** (the `get_trade_ideas_grouped` function definition):
```python
@router.get("/trade-ideas/grouped")
async def get_trade_ideas_grouped(
```

**INSERT BEFORE** that decorator (new function):
```python
def _dedup_key(strategy: str) -> str:
    """Normalize strategy name for cooldown lookup."""
    return (strategy or "").lower().replace("-", "_").replace(" ", "_")


def _is_redundant(signal_row: dict, existing_signals: list, cooldowns: dict) -> bool:
    """
    Check if a signal is redundant given existing signals in the group.
    Returns True if same strategy already has a signal within the cooldown window.
    """
    strategy = _dedup_key(signal_row.get("strategy") or signal_row.get("signal_type") or "")
    cooldown_minutes = cooldowns.get(strategy)
    if cooldown_minutes is None:
        return False  # Not a scan-based strategy — always keep

    sig_ts = signal_row.get("timestamp") or signal_row.get("created_at")
    if not sig_ts:
        return False

    from datetime import timedelta
    try:
        sig_time = datetime.fromisoformat(str(sig_ts).replace("Z", "+00:00").replace("+00:00", ""))
    except (ValueError, TypeError):
        return False

    for existing in existing_signals:
        existing_strategy = _dedup_key(existing.get("strategy") or "")
        if existing_strategy != strategy:
            continue
        # Same strategy found — check time gap
        ex_ts = existing.get("timestamp")
        if not ex_ts:
            continue
        try:
            ex_time = datetime.fromisoformat(str(ex_ts).replace("Z", "+00:00").replace("+00:00", ""))
        except (ValueError, TypeError):
            continue
        gap_minutes = abs((sig_time - ex_time).total_seconds()) / 60
        if gap_minutes < cooldown_minutes:
            return True  # Within cooldown — this is a redundant fire

    return False


```


### Step 3: Add dedup check in the grouping loop

Inside `get_trade_ideas_grouped()`, the grouping loop has an `else` branch that adds signals to `related_signals`. We need to add a redundancy check there.

**FIND** (the `else` branch in the grouping loop — this is the exact code):
```python
        else:
            g = groups_map[key]
            g["signal_count"] += 1
            g["related_signals"].append({
                "signal_id": r.get("signal_id"),
                "strategy": r.get("strategy") or r.get("signal_type"),
                "signal_category": r.get("signal_category"),
                "score": float(r.get("score_v2") or r.get("score") or 0),
                "timestamp": r.get("timestamp") or r.get("created_at"),
                "confluence_tier": r.get("confluence_tier"),
            })
```

**REPLACE WITH**:
```python
        else:
            g = groups_map[key]

            # ── Scan-based strategy dedup ──
            # Check if this is a redundant fire from a scan-based strategy.
            # If so, skip it entirely — don't count it, don't add to related.
            if _is_redundant(r, g["related_signals"] + [{
                "strategy": g["primary_signal"].get("strategy") or g["primary_signal"].get("signal_type"),
                "timestamp": g["primary_signal"].get("timestamp") or g["primary_signal"].get("created_at"),
            }], SCAN_STRATEGY_COOLDOWNS):
                continue

            g["signal_count"] += 1
            g["related_signals"].append({
                "signal_id": r.get("signal_id"),
                "strategy": r.get("strategy") or r.get("signal_type"),
                "signal_category": r.get("signal_category"),
                "score": float(r.get("score_v2") or r.get("score") or 0),
                "timestamp": r.get("timestamp") or r.get("created_at"),
                "confluence_tier": r.get("confluence_tier"),
            })
```

**KEY DETAIL**: The `_is_redundant()` check compares against BOTH existing `related_signals` AND the `primary_signal` (since the primary was never added to related_signals). This prevents a second Holy Grail from sneaking through when the first one became the primary.

The `continue` statement skips the rest of the loop body for this signal — so it won't increment `signal_count`, won't be added to `related_signals`, won't affect `strategies` list, and won't update time tracking.

### Step 4: Also dedup the primary signal selection

There's also a subtle issue: if the FIRST signal for a ticker+direction is a Holy Grail, and then a DIFFERENT strategy (e.g., Scout Sniper) fires, we want Scout to become primary (higher score typically). This is already handled because signals are sorted by score DESC — the highest-scoring signal becomes primary regardless of strategy. No change needed here.

## What This Does NOT Change

- **Signal ingestion**: TradingView webhooks still create signals normally. No data is lost.
- **DB schema**: No migrations.
- **Frontend**: No JS changes. The frontend already renders `group.related_signals` — it will just have fewer redundant entries.
- **Non-scan strategies**: Webhook-triggered strategies (Scout, Whale Hunter, UW Flow) have no entry in `SCAN_STRATEGY_COOLDOWNS` and are never filtered.
- **Confluence tier**: Still promoted correctly for non-redundant signals.
- **Composite rank**: Will be more accurate since `signal_count` reflects real diversity, not scan-cycle noise.

## Testing

1. Check the current state: `GET /api/trade-ideas/grouped` — count Holy Grail entries in any group's `related_signals`
2. After deploy: same call should show at most 1 Holy Grail per 4-hour window per ticker+direction
3. Signal count badge should drop from inflated numbers to real confluence counts
4. Verify non-scan strategies (Scout, Whale, UW Flow) still appear normally

## Tuning

The cooldown values in `SCAN_STRATEGY_COOLDOWNS` can be adjusted. Current settings:
- Holy Grail: 4 hours (conservative — it's a slow indicator)
- CTA Scanner: 2 hours
- Exhaustion: 3 hours

If a strategy should NOT be deduped, just remove it from the dict. If a new scan-based strategy is added later, add it with an appropriate cooldown.
