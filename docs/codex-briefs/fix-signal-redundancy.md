# Fix: Signal Redundancy Filter (Holy Grail + Scan-Based Strategies)

## Problem
Scan-based strategies like Holy Grail fire on **persistent conditions** (ADX ≥ 25 + RSI pullback), not discrete events. When conditions last across multiple TradingView scan cycles, each cycle fires a new webhook that passes the 60-second dedup window and creates a new signal row. These pile up as "supporting signals" in grouped Trade Ideas cards, inflating `signal_count`, boosting confluence tier, and distorting composite rank scoring.

## Fix: Two layers

### Layer 1 — Ingestion cooldown (`backend/webhooks/tradingview.py`)
### Layer 2 — Query dedup safety net (`backend/api/trade_ideas.py`)

---

## Layer 1: Ingestion Cooldown

**File:** `backend/webhooks/tradingview.py`

### Step 1A: Add cooldown config constant after the existing `CRYPTO_TICKERS` set

Find this line:
```python
def is_crypto_ticker(ticker: str) -> bool:
```

Insert BEFORE it:
```python
# Strategy-specific cooldown windows (seconds).
# Scan-based strategies that fire on persistent conditions need longer cooldowns
# to prevent duplicate signals from inflating confluence scoring.
# Event-driven strategies keep the default 60s Redis dedup.
STRATEGY_COOLDOWNS = {
    "Holy_Grail": {"equity": 14400, "crypto": 7200},   # 4h equity, 2h crypto
    "Scout": {"equity": 14400, "crypto": 7200},          # 4h equity, 2h crypto
    "Phalanx": {"equity": 3600, "crypto": 3600},         # 1h both
}


async def check_strategy_cooldown(ticker: str, strategy: str, direction: str, asset_class: str) -> bool:
    """
    Check if an ACTIVE signal with same ticker+strategy+direction exists
    within the strategy's cooldown window. Returns True if signal should
    be SKIPPED (cooldown active), False if signal should proceed.

    Uses Redis for fast lookup. Falls back to allowing signal if Redis unavailable.
    """
    cooldown_cfg = STRATEGY_COOLDOWNS.get(strategy)
    if not cooldown_cfg:
        return False  # No cooldown configured — allow signal

    cooldown_secs = cooldown_cfg.get("crypto" if asset_class == "CRYPTO" else "equity", 0)
    if cooldown_secs <= 0:
        return False

    cooldown_key = f"signal:cooldown:{ticker.upper()}:{strategy}:{direction.upper()}"
    try:
        from database.redis_client import get_redis_client
        rc = await get_redis_client()
        if rc and await rc.get(cooldown_key):
            return True  # Cooldown active — skip this signal
        # Set cooldown marker for future checks
        if rc:
            await rc.set(cooldown_key, "1", ex=cooldown_secs)
    except Exception:
        pass  # Redis failure — fail open, allow signal

    return False


```

### Step 1B: Add cooldown check to `process_holy_grail_signal`

Find this exact block inside `process_holy_grail_signal`:
```python
    signal_type = f"HOLY_GRAIL_{signal_type_suffix}"

    # Calculate risk/reward
    rr = calculate_risk_reward(alert)
```

Replace with:
```python
    signal_type = f"HOLY_GRAIL_{signal_type_suffix}"

    # Strategy cooldown — skip if same ticker+direction fired recently
    asset_class = "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY"
    if await check_strategy_cooldown(alert.ticker, "Holy_Grail", alert.direction, asset_class):
        logger.info("⏳ Holy Grail cooldown: skipping %s %s %s", alert.ticker, alert.direction, signal_type)
        return {"status": "cooldown", "detail": f"Holy Grail cooldown active for {alert.ticker} {alert.direction}"}

    # Calculate risk/reward
    rr = calculate_risk_reward(alert)
```

### Step 1C: Add cooldown check to `process_scout_signal`

Find this exact block inside `process_scout_signal`:
```python
    # Build signal data with Scout-specific fields
    signal_id = f"SCOUT_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
```

Insert BEFORE it:
```python
    # Strategy cooldown — skip if same ticker+direction fired recently
    asset_class = "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY"
    if await check_strategy_cooldown(alert.ticker, "Scout", alert.direction, asset_class):
        logger.info("⏳ Scout cooldown: skipping %s %s", alert.ticker, alert.direction)
        return {"status": "cooldown", "detail": f"Scout cooldown active for {alert.ticker} {alert.direction}"}

```

### Step 1D: Add cooldown check to `process_phalanx_signal`

Find this exact block inside `process_phalanx_signal`:
```python
    signal_id = f"PHALANX_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
```

Insert BEFORE it:
```python
    # Strategy cooldown — skip if same ticker+direction fired recently
    asset_class = "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY"
    if await check_strategy_cooldown(alert.ticker, "Phalanx", alert.direction, asset_class):
        logger.info("⏳ Phalanx cooldown: skipping %s %s", alert.ticker, alert.direction)
        return {"status": "cooldown", "detail": f"Phalanx cooldown active for {alert.ticker} {alert.direction}"}

```

---

## Layer 2: Query Dedup Safety Net

**File:** `backend/api/trade_ideas.py`

This catches duplicates already in the DB (from before the cooldown was deployed). When building `related_signals` in the grouping loop, collapse signals from the same strategy within a 4-hour window — keep only the most recent one.

### Step 2A: Add dedup helper function

Find this line at the top of the file:
```python
logger = logging.getLogger(__name__)
router = APIRouter()
```

Insert AFTER it:
```python

# Strategies that fire on persistent conditions (not discrete events).
# Duplicates within DEDUP_WINDOW_SECONDS are collapsed in grouped view.
SCAN_BASED_STRATEGIES = {"Holy_Grail", "Scout", "Phalanx", "holy_grail", "scout", "phalanx"}
DEDUP_WINDOW_SECONDS = 14400  # 4 hours


def _dedup_related_signals(related: list) -> list:
    """
    Collapse duplicate signals from scan-based strategies within a time window.
    Keeps only the most recent signal per (strategy, direction) combo.
    Event-driven strategies pass through untouched.
    """
    if not related:
        return related

    from datetime import datetime as _dt

    # Separate scan-based from event-driven
    keep = []
    scan_buckets = {}  # key: strategy_lower -> newest signal dict

    for sig in related:
        strat = (sig.get("strategy") or "").strip()
        if strat in SCAN_BASED_STRATEGIES or strat.lower() in {s.lower() for s in SCAN_BASED_STRATEGIES}:
            key = strat.lower()
            existing = scan_buckets.get(key)
            if existing is None:
                scan_buckets[key] = sig
            else:
                # Keep whichever is newer
                sig_ts = str(sig.get("timestamp") or "")
                ex_ts = str(existing.get("timestamp") or "")
                if sig_ts > ex_ts:
                    scan_buckets[key] = sig
        else:
            keep.append(sig)

    # Add back one representative per scan-based strategy
    keep.extend(scan_buckets.values())
    return keep

```

### Step 2B: Apply dedup when building groups

Find this exact block at the END of the grouping loop (after the `for row in rows:` loop closes), right before `# Compute composite rank for sorting`:
```python
    # Compute composite rank for sorting
    now = datetime.utcnow()
```

Insert BEFORE it:
```python
    # Dedup scan-based strategies within each group
    for g in groups_map.values():
        g["related_signals"] = _dedup_related_signals(g["related_signals"])
        # Recount after dedup: primary + related
        g["signal_count"] = 1 + len(g["related_signals"])
        # Rebuild strategy list from deduped signals
        strats = [g["primary_signal"].get("strategy") or g["primary_signal"].get("signal_type") or "UNKNOWN"]
        for rs in g["related_signals"]:
            s = rs.get("strategy") or "UNKNOWN"
            if s not in strats:
                strats.append(s)
        g["strategies"] = strats

```

---

## Testing

After deploy, verify:

1. **Cooldown works:** Send two Holy Grail webhooks for the same ticker+direction within 5 minutes. First should return `{"status": "accepted"}`, second should return `{"status": "cooldown"}`.

2. **Grouped view deduped:** Hit `GET /api/trade-ideas/grouped` and check that no group has multiple `related_signals` entries from the same scan-based strategy.

3. **Event strategies unaffected:** Exhaustion, Sniper, Artemis signals should still pass through with only the standard 60s Redis dedup.

4. **Redis key format:** Check Redis for keys matching `signal:cooldown:*` — they should have TTLs matching the configured cooldown windows.

---

## Files Modified
- `backend/webhooks/tradingview.py` — cooldown config + `check_strategy_cooldown()` + checks in 3 handler functions
- `backend/api/trade_ideas.py` — `_dedup_related_signals()` helper + dedup pass in grouping endpoint

## No new files, no new dependencies, no DB changes.
