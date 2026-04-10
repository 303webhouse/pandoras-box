# ARGUS Phase 2 — Pythia Scoring + Flow Pipeline + Regime Penalty + Sort

**Priority:** HIGH — deploy before Monday open  
**Builder:** Claude Code (VSCode)  
**Branch:** `main`  
**Pre-req:** `git pull origin main` — P1-P4 + hotfixes already deployed  

---

## Context

BMY scored 92.5 (Pullback Entry LONG) while every other signal said bearish:
- Pythia: VA migrating DOWN, POOR LOW active, price below IB
- UW Flow: put/call 1.17, net premium -$93K (puts 2x calls)
- Prior BMY signal (March 17): same setup, ACCEPTED → CLOSED AS LOSS

The score was inflated because the scoring engine only sees the CTA pattern, not the
context. This brief adds three new scoring layers + one UX feature.

---

## P1: Pythia Scoring v2 — Three-Tier Model

**File:** `backend/webhooks/pythia_events.py` → modify `get_pythia_profile_position()`

### Current behavior
Returns `{profile_bonus: +8/+3/0/-10, zone: ...}` based only on entry vs VAH/VAL/POC.

### New behavior
Returns three tiers that stack:

**Tier 1 — Static position (keep existing):**
- Entry at/below VAL on LONG: +8
- Entry between VAL and POC: +3
- Entry between POC and VAH: 0
- Entry above VAH on LONG: -10
- (Inverted for SHORT)

**Tier 2 — Dynamic session data (NEW):**
Query `pythia_events` table for most recent event for this ticker where
`timestamp > NOW() - INTERVAL '4 hours'`. If no recent event, skip Tier 2 and 3.

```
va_migration aligns with signal direction: +3
va_migration opposes signal direction: -8
va_migration overlapping or unknown: 0

poor_low active + signal is LONG: -10
poor_high active + signal is SHORT: -10
poor_low active + signal is SHORT: +5
poor_high active + signal is LONG: +5

volume_quality = "high": multiply Tier 1 bonus by 1.5 (round to int)
volume_quality = "thin": multiply Tier 1 bonus by 0.5 (round to int)
volume_quality = "normal": no change
```

**Tier 3 — IB context (NEW):**
Only if `ib_high` and `ib_low` are present in the event:
```
entry > ib_high AND signal is LONG AND volume_quality == "high": +5
entry < ib_low AND signal is LONG: -5
entry < ib_low AND signal is SHORT AND volume_quality == "high": +5
entry > ib_high AND signal is SHORT: -5
```

### Return format
```python
return {
    "profile_bonus": tier1_bonus,       # existing field, keep for backward compat
    "migration_bonus": migration_adj,
    "poor_extreme_bonus": poor_adj,
    "ib_bonus": ib_adj,
    "volume_quality": vol_quality,
    "total_pythia_adjustment": tier1 + tier2 + tier3,
    "zone": zone_label,
    "vah": vah, "val": val, "poc": poc,
    "data_age": "current" or "stale",
}
```

### Pipeline integration
**File:** `backend/signals/pipeline.py` → in `apply_scoring()`, find the P4B Pythia block.

Replace:
```python
pp_bonus = pp.get("profile_bonus", 0)
if pp_bonus != 0:
    score = min(100, max(0, score + pp_bonus))
```

With:
```python
pp_total = pp.get("total_pythia_adjustment", pp.get("profile_bonus", 0))
if pp_total != 0:
    score = min(100, max(0, score + pp_total))
```

Store the full dict in `triggering_factors["profile_position"]`.

### BMY validation
With Tier 2 (VA down = -8, poor low = -10) + Tier 3 (below IB on LONG = -5):
92.5 - 23 = 69.5. Below threshold. Correctly filtered.

---

## P2: Options Flow Pipeline — yfinance On-Demand

**New file:** `backend/signals/flow_enrichment.py`

### Architecture
Same pattern as `price_enrichment.py`:
```
Signal fires → pipeline.py calls enrich_flow_data(signal_data)
  → check Redis cache "flow_data:{TICKER}" (30min TTL)
  → if miss: yfinance option_chain() in executor thread
  → compute put/call ratio + net premium direction
  → cache in Redis + inject into signal metadata
  → scorer applies flow adjustment
```

### Implementation

```python
"""
Flow Enrichment — fetches options chain data via yfinance and computes
put/call volume ratio and net premium direction for scoring.
Uses Redis cache (30min TTL) to avoid rate limits.
"""

import asyncio
import json as _json
import logging
from datetime import datetime

logger = logging.getLogger("pipeline")
FLOW_CACHE_TTL = 1800  # 30 minutes


async def enrich_flow_data(signal_data: dict) -> dict:
    ticker = (signal_data.get("ticker") or "").upper()
    if not ticker:
        return signal_data

    metadata = signal_data.get("metadata") or {}
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    if "flow_pc_ratio" in metadata:
        return signal_data

    flow_data = None
    cache_key = f"flow_data:{ticker}"

    # Check Redis cache
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                flow_data = _json.loads(cached)
                logger.debug("Flow cache hit for %s", ticker)
    except Exception:
        pass

    # Fetch from yfinance if not cached
    if flow_data is None:
        try:
            loop = asyncio.get_event_loop()
            flow_data = await loop.run_in_executor(
                None, _fetch_flow_yfinance, ticker
            )
        except Exception as e:
            logger.debug("Flow fetch failed for %s: %s", ticker, e)
            return signal_data

    if flow_data is None:
        return signal_data

    # Cache successful result
    try:
        redis = await get_redis_client()
        if redis:
            await redis.set(cache_key, _json.dumps(flow_data), ex=FLOW_CACHE_TTL)
    except Exception:
        pass

    # Inject into metadata
    metadata["flow_pc_ratio"] = flow_data.get("pc_ratio")
    metadata["flow_net_premium_direction"] = flow_data.get("net_premium_direction")
    metadata["flow_call_volume"] = flow_data.get("call_volume")
    metadata["flow_put_volume"] = flow_data.get("put_volume")
    signal_data["metadata"] = metadata

    logger.info("Flow enriched for %s: P/C=%.2f net_prem=%s",
                ticker,
                flow_data.get("pc_ratio", 0),
                flow_data.get("net_premium_direction", "?"))
    return signal_data


def _fetch_flow_yfinance(ticker: str) -> dict:
    """Synchronous yfinance options fetch. Runs in executor."""
    import yfinance as yf

    tk = yf.Ticker(ticker)
    expirations = tk.options
    if not expirations:
        return None

    # Use nearest monthly expiration (skip weeklies if possible)
    # Pick first expiration that is 14+ days out, else use the nearest
    from datetime import datetime, timedelta
    target_date = datetime.now() + timedelta(days=14)
    chosen_exp = expirations[0]
    for exp in expirations:
        exp_dt = datetime.strptime(exp, "%Y-%m-%d")
        if exp_dt >= target_date:
            chosen_exp = exp
            break

    chain = tk.option_chain(chosen_exp)
    calls = chain.calls
    puts = chain.puts

    if calls.empty and puts.empty:
        return None

    # Filter strikes within 20% of current price
    current_price = tk.fast_info.get("lastPrice", 0)
    if current_price and current_price > 0:
        low_bound = current_price * 0.8
        high_bound = current_price * 1.2
        calls = calls[(calls["strike"] >= low_bound) & (calls["strike"] <= high_bound)]
        puts = puts[(puts["strike"] >= low_bound) & (puts["strike"] <= high_bound)]

    call_volume = int(calls["volume"].sum()) if "volume" in calls.columns else 0
    put_volume = int(puts["volume"].sum()) if "volume" in puts.columns else 0

    pc_ratio = put_volume / call_volume if call_volume > 0 else 999.0

    # Net premium direction estimate
    # yfinance gives lastPrice * volume as rough premium proxy
    call_premium = 0
    put_premium = 0
    if "lastPrice" in calls.columns and "volume" in calls.columns:
        call_premium = float((calls["lastPrice"] * calls["volume"]).sum())
    if "lastPrice" in puts.columns and "volume" in puts.columns:
        put_premium = float((puts["lastPrice"] * puts["volume"]).sum())

    net_premium = call_premium - put_premium
    net_direction = "bullish" if net_premium > 0 else "bearish"

    return {
        "pc_ratio": round(pc_ratio, 3),
        "call_volume": call_volume,
        "put_volume": put_volume,
        "call_premium": round(call_premium, 2),
        "put_premium": round(put_premium, 2),
        "net_premium": round(net_premium, 2),
        "net_premium_direction": net_direction,
        "expiration_used": chosen_exp,
    }
```

### Scoring integration

**File:** `backend/scoring/trade_ideas_scorer.py`

Add after the freshness penalty calculation (section 9), before time horizon:

```python
# 10. Options flow adjustment
flow_bonus = 0
flow_meta = metadata.get("flow_pc_ratio")
flow_dir = metadata.get("flow_net_premium_direction")
if flow_meta is not None:
    pc = float(flow_meta)
    is_long = direction in ("LONG", "BUY", "BULLISH")

    # Put/call ratio scoring
    if is_long:
        if pc < 0.5:
            flow_bonus += 5
        elif pc < 0.8:
            flow_bonus += 3
        elif pc > 1.8:
            flow_bonus -= 8
        elif pc > 1.2:
            flow_bonus -= 5
    else:  # SHORT
        if pc > 1.8:
            flow_bonus += 5
        elif pc > 1.2:
            flow_bonus += 3
        elif pc < 0.5:
            flow_bonus -= 5
        elif pc < 0.8:
            flow_bonus -= 3

    # Net premium direction scoring
    if flow_dir:
        signal_bullish = is_long
        prem_bullish = flow_dir == "bullish"
        if signal_bullish == prem_bullish:
            flow_bonus += 3  # premium aligns with signal
        else:
            flow_bonus -= 5  # premium opposes signal

        # TORO guardrail: if P/C > 1.2 but net premium is bullish,
        # reduce the P/C penalty by half (protective hedging scenario)
        if is_long and pc > 1.2 and prem_bullish and flow_bonus < 0:
            flow_bonus = flow_bonus // 2

    triggering_factors["flow_data"] = {
        "pc_ratio": pc,
        "net_premium_direction": flow_dir,
        "bonus": flow_bonus,
    }
```

Apply `flow_bonus` to the score the same way freshness penalty is applied (pre-alignment).

### Pipeline wiring

**File:** `backend/signals/pipeline.py`

Import and call after price enrichment, before scoring:
```python
from signals.flow_enrichment import enrich_flow_data
signal_data = await enrich_flow_data(signal_data)
```

### BMY validation
P/C 1.17 → -5 for LONG. Net premium bearish → -5. Total flow: -10.
Combined with Pythia -23: BMY drops from 92.5 to 59.5.

---

## P3: Regime/Chop Penalty — SPY ADX-Based

### Concept
When the market is choppy (not trending), trend-following signals (Pullback Entry)
are less reliable. The system should detect this and adjust scores.

### Data source
SPY 14-period ADX. Compute from Polygon daily bars (already used for bias system).

**File:** `backend/scoring/trade_ideas_scorer.py` — add near the top constants

```python
# Regime penalty based on SPY ADX
REGIME_THRESHOLDS = {
    "trending": {"adx_min": 25, "penalty": 0, "max_alignment": 1.25},
    "transitional": {"adx_min": 20, "penalty": -5, "max_alignment": 1.15},
    "choppy": {"adx_min": 0, "penalty": -10, "max_alignment": 1.10},
}

# Strategy-specific adjustments in choppy regime (ADX < 20)
CHOP_STRATEGY_ADJUSTMENTS = {
    "PULLBACK_ENTRY": -8,
    "GOLDEN_TOUCH": -8,
    "RESISTANCE_REJECTION": +5,
    "TRAPPED_SHORTS": +3,
    "TRAPPED_LONGS": +3,
    "SELL_RIP_EMA": +3,
    "SELL_RIP_VWAP": +3,
    "DEATH_CROSS": -5,
    "BEARISH_BREAKDOWN": -5,
}
```

### ADX computation

**New function** in `trade_ideas_scorer.py` or a utility file:

```python
def compute_adx(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Compute ADX from daily bars. Returns current ADX value."""
    if len(closes) < period * 2:
        return 25.0  # default to "trending" if not enough data
    import pandas as pd
    import pandas_ta as ta
    df = pd.DataFrame({"high": highs, "low": lows, "close": closes})
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=period)
    if adx_df is None or adx_df.empty:
        return 25.0
    col = f"ADX_{period}"
    if col in adx_df.columns:
        val = adx_df[col].iloc[-1]
        return float(val) if pd.notna(val) else 25.0
    return 25.0
```

### Cache ADX in Redis

**File:** `backend/signals/pipeline.py` or bias refresh cycle

Fetch SPY daily bars from Polygon (30 days), compute ADX, cache in Redis:
```
Key: regime:spy_adx
Value: {"adx": 18.5, "regime": "choppy", "timestamp": "..."}
TTL: 14400 (4 hours)
```

The scorer reads this value at score time. If cache miss, default to "trending"
(no penalty — fail open, not fail restrictive).

### Scoring integration

In `calculate_signal_score()`, after all other factors are computed but BEFORE
the alignment multiplier is applied:

```python
# Regime/chop penalty
regime_penalty = 0
chop_strategy_adj = 0
try:
    from database.redis_client import get_redis_client
    import asyncio
    # Note: this is sync code, need Redis sync or cached value passed in
    # PREFERRED: pass regime_data as parameter to calculate_signal_score()
    regime_data = kwargs.get("regime_data", {})
    spy_adx = regime_data.get("adx", 25)

    if spy_adx >= 25:
        regime_label = "trending"
        regime_penalty = 0
        max_align = 1.25
    elif spy_adx >= 20:
        regime_label = "transitional"
        regime_penalty = -5
        max_align = 1.15
    else:
        regime_label = "choppy"
        regime_penalty = -10
        max_align = 1.10
        # Strategy-specific chop adjustments
        chop_strategy_adj = CHOP_STRATEGY_ADJUSTMENTS.get(signal_type, 0)

    # Cap alignment multiplier
    alignment_multiplier = min(alignment_multiplier, max_align)

    triggering_factors["regime"] = {
        "spy_adx": round(spy_adx, 1),
        "label": regime_label,
        "penalty": regime_penalty,
        "strategy_adj": chop_strategy_adj,
    }
except Exception:
    regime_penalty = 0
    chop_strategy_adj = 0
```

Apply `regime_penalty + chop_strategy_adj` to the pre-alignment score.

### Score threshold adjustments

**File:** `frontend/app.js` — in the signal rendering logic

Add regime awareness to the score display. If `triggering_factors.regime.label`
is "choppy", the high-conviction threshold rises from 80 to 90. Signals between
80-90 in a choppy regime should render with a yellow "CHOP" badge instead of the
normal green high-conviction styling.

The `regime` label should also appear in the Agora bias panel:
- Trending: green text
- Transitional: yellow text
- Choppy: red text

Place it next to the existing regime bar / bias score display.

---

## P4: Insights Sort Control

**File:** `frontend/app.js`

### Behavior
Add two sort buttons (or a toggle) above the Insights signal list:
- **Time** (default): Most recent signals first (current behavior)
- **Score**: Highest score first

When the page loads, default to Time sort. User can tap Score to re-sort.
The selected sort should persist for the session (simple JS variable, no localStorage).

### Implementation

Add sort controls in the Insights panel header area:

```html
<div class="insights-sort-controls">
    <button class="sort-btn active" data-sort="time">Time</button>
    <button class="sort-btn" data-sort="score">Score</button>
</div>
```

CSS for sort buttons:
```css
.insights-sort-controls {
    display: flex;
    gap: 6px;
    margin-bottom: 8px;
}
.sort-btn {
    padding: 4px 12px;
    border-radius: 4px;
    border: 1px solid var(--border-color, #333);
    background: transparent;
    color: var(--text-secondary, #888);
    font-size: 12px;
    cursor: pointer;
}
.sort-btn.active {
    background: var(--accent-color, #2196F3);
    color: white;
    border-color: var(--accent-color, #2196F3);
}
```

In the signal rendering function, before rendering the signal list, apply sort:

```javascript
let insightsSortMode = 'time'; // default

function sortSignals(signals, mode) {
    if (mode === 'score') {
        return [...signals].sort((a, b) => (b.score || 0) - (a.score || 0));
    }
    // Default: time (most recent first)
    return [...signals].sort((a, b) => {
        const tA = new Date(a.timestamp || 0).getTime();
        const tB = new Date(b.timestamp || 0).getTime();
        return tB - tA;
    });
}
```

Wire click handlers to toggle `insightsSortMode` and re-render the signal list.

---

## Wiring Summary

### Pipeline order (backend/signals/pipeline.py)

```
1. enrich_price_range(signal_data)     ← P1 (existing)
2. enrich_flow_data(signal_data)       ← P2 (NEW)
3. apply_scoring(signal_data)          ← includes:
   a. Base score
   b. Technical bonus
   c. R:R bonus
   d. Recency bonus
   e. Sector momentum (P2A from Phase 1)
   f. Catalyst alignment
   g. Time of day
   h. Freshness penalty (P1A from Phase 1)
   i. Flow adjustment (P2 NEW)
   j. Regime/chop penalty (P3 NEW)
   k. Time horizon (P3A from Phase 1)
   l. Alignment multiplier (CAPPED by regime)
   m. Squeeze cross-ref (post-alignment)
   n. Pythia profile v2 (P1 NEW — 3-tier, post-alignment)
```

### Files to create
- `backend/signals/flow_enrichment.py` (P2 — ~100 lines)

### Files to modify
- `backend/webhooks/pythia_events.py` → `get_pythia_profile_position()` (P1)
- `backend/signals/pipeline.py` → add flow enrichment call, pass regime data (P2, P3)
- `backend/scoring/trade_ideas_scorer.py` → add flow scoring, regime penalty, chop adj (P2, P3)
- `frontend/app.js` → sort controls, regime label, flow/profile badges (P4 + display)
- `frontend/styles.css` → sort button styles, regime label, chop badge (P4 + display)

### Estimated total: ~350-400 new lines across 6 files

---

## Validation Checklist

After deploy, verify with these test cases:

1. **BMY retroactive:** If BMY signal re-fires, score should be ~60-70 (not 92.5)
   - Pythia: VA down (-8) + poor low (-10) + below IB (-5) = -23
   - Flow: P/C 1.17 (-5) + net prem bearish (-5) = -10
   - Total penalty: -33 → 92.5 - 33 = 59.5

2. **NEXT validation:** NEXT signal should score HIGHER with these additions
   - Pythia: IB breakout with HiVol = +5
   - Flow: P/C 0.33 on UW data = bullish flow = +5 to +8
   - Net effect: +10 to +13 bonus

3. **Regime check:** Query `regime:spy_adx` in Redis after deploy.
   Should show current SPY ADX value and regime label.

4. **Sort feature:** Open Agora, verify default sort is by time.
   Tap Score, verify reorder. Tap Time, verify return to time order.

5. **Flow cache:** Check Redis for `flow_data:{ticker}` keys after
   signals fire. Should show P/C ratio and premium data.
