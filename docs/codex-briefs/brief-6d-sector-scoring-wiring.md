# Brief 6D: Wire Sector Strength into Signal Scoring (Olympus-Approved)

**Target Agent:** Claude Code (VSCode)
**Priority:** HIGH — sector scoring is currently dead code
**Depends On:** Brief 6C (sector data now refreshing every 15s via Polygon)
**Olympus Approved:** March 17, 2026 — asymmetric model (+5/-8)

---

## What This Does

Three changes:
1. Feed live sector strength data from Redis into the scorer on every signal
2. Update `SECTOR_PRIORITY_BONUS` weights to Olympus-approved asymmetric model
3. Remove the redundant `sector_rotation_bonus.py` pipeline call to eliminate double-counting

---

## Context: Why This Is Needed

`calculate_signal_score()` in `trade_ideas_scorer.py` accepts an optional `sector_strength` parameter that drives the `SECTOR_PRIORITY_BONUS` logic (+8 leading / -5 misaligned). But **nobody passes it**:

- `apply_scoring()` in `pipeline.py` calls `calculate_signal_score(signal_data, current_bias)` — no sector_strength
- `run_cta_scan_scheduled()` in `bias_scheduler.py` calls `calculate_signal_score(trade_signal, current_bias)` — no sector_strength

Meanwhile, a separate `sector_rotation_bonus.py` IS wired into the pipeline but does its own independent calculation with different logic. This creates confusion and inconsistency.

**Olympus decision:** Single scoring path, asymmetric weights, rank-based tiers.

---

## Step 1: Update Sector Scoring Weights

**File:** `backend/scoring/trade_ideas_scorer.py`

**Find:**
```python
# Sector priority bonuses
SECTOR_PRIORITY_BONUS = {
    "leading_aligned": 8,       # Signal in leading sector, aligned with bullish bias
    "lagging_counter": 8,       # Signal in lagging sector, aligned with bearish bias (short)
    "neutral_sector": 0,        # Neutral sector, no bonus
    "misaligned_sector": -5     # Signal against sector trend (e.g., long in lagging during bull)
}
```

**Replace with:**
```python
# Sector priority bonuses (Olympus-approved asymmetric model)
# Penalty > bonus by design: avoiding bad trades matters more than boosting good ones
# Tiers based on sector rank: top 3 = leading, bottom 3 = lagging, middle 5 = neutral
SECTOR_PRIORITY_BONUS = {
    "leading_aligned": 5,       # Signal in top-3 sector, direction aligned
    "lagging_counter": 5,       # Signal shorting bottom-3 sector (aligned with weakness)
    "neutral_sector": 0,        # Sector ranked #4-8, no effect
    "misaligned_sector": -8     # Signal long in bottom-3 sector OR short in top-3 sector
}
```

### Step 1B: Update the sector scoring logic to use rank-based tiers

**Find** the sector priority bonus calculation block inside `calculate_signal_score()`. It starts with:
```python
    # 6. Sector priority bonus
    sector_bonus = 0
    ticker = signal.get('ticker', '').upper()
    sector = TICKER_SECTORS.get(ticker)
    
    if sector and sector_strength:
        sector_data = sector_strength.get(sector, {})
        sector_trend = sector_data.get("trend", "neutral")
        
        # Determine if sector alignment helps or hurts
        is_bullish_signal = direction in ["LONG", "BUY"]
        is_bearish_signal = direction in ["SHORT", "SELL"]
        
        if sector_trend == "leading":
            if is_bullish_signal:
                sector_bonus = SECTOR_PRIORITY_BONUS["leading_aligned"]
            else:
                sector_bonus = SECTOR_PRIORITY_BONUS["misaligned_sector"]
        elif sector_trend == "lagging":
            if is_bearish_signal:
                sector_bonus = SECTOR_PRIORITY_BONUS["lagging_counter"]
            else:
                sector_bonus = SECTOR_PRIORITY_BONUS["misaligned_sector"]
        
        triggering_factors["sector_priority"] = {
            "sector": sector,
            "trend": sector_trend,
            "bonus": sector_bonus,
            "rank": sector_data.get("rank")
        }
```

**Replace with:**
```python
    # 6. Sector priority bonus (Olympus-approved asymmetric: +5/-8, rank-based tiers)
    sector_bonus = 0
    ticker = signal.get('ticker', '').upper()
    sector = TICKER_SECTORS.get(ticker)
    
    if sector and sector_strength:
        sector_data = sector_strength.get(sector, {})
        sector_rank = sector_data.get("rank", 6)  # Default to middle
        sector_trend = sector_data.get("trend", "neutral")
        
        is_bullish_signal = direction in ["LONG", "BUY"]
        is_bearish_signal = direction in ["SHORT", "SELL"]
        
        # Rank-based tiers: top 3 = leading, bottom 3 = lagging, middle 5 = neutral
        is_leading = sector_rank <= 3
        is_lagging = sector_rank >= 9
        
        if is_leading:
            if is_bullish_signal:
                sector_bonus = SECTOR_PRIORITY_BONUS["leading_aligned"]   # +5
            elif is_bearish_signal:
                sector_bonus = SECTOR_PRIORITY_BONUS["misaligned_sector"]  # -8 (shorting a leader)
        elif is_lagging:
            if is_bearish_signal:
                sector_bonus = SECTOR_PRIORITY_BONUS["lagging_counter"]    # +5
            elif is_bullish_signal:
                sector_bonus = SECTOR_PRIORITY_BONUS["misaligned_sector"]  # -8 (buying a lagger)
        # Middle ranks (#4-8): no bonus or penalty
        
        triggering_factors["sector_priority"] = {
            "sector": sector,
            "rank": sector_rank,
            "trend": sector_trend,
            "tier": "leading" if is_leading else ("lagging" if is_lagging else "neutral"),
            "bonus": sector_bonus,
        }
```

---

## Step 2: Feed Sector Data into Scorer from Pipeline

**File:** `backend/signals/pipeline.py`

Inside `apply_scoring()`, sector strength needs to be fetched from Redis and passed to `calculate_signal_score()`.

**Find:**
```python
        # Calculate score
        score, bias_alignment, triggering_factors = calculate_signal_score(
            signal_data, current_bias
        )
```

**Replace with:**
```python
        # Fetch sector strength from Redis (refreshed every 15s by sector_refresh_loop)
        sector_strength = None
        try:
            from database.redis_client import get_redis_client
            import json as _json
            redis = await get_redis_client()
            if redis:
                raw = await redis.get("sector:strength")
                if raw:
                    sector_strength = _json.loads(raw)
        except Exception as sect_err:
            logger.debug(f"Sector strength unavailable for scoring: {sect_err}")

        # Calculate score (with sector strength if available)
        score, bias_alignment, triggering_factors = calculate_signal_score(
            signal_data, current_bias, sector_strength=sector_strength
        )
```

---

## Step 3: Remove Redundant `sector_rotation_bonus.py` Call

The pipeline currently has a SEPARATE sector bonus call that runs independently from the scorer. This causes double-counting now that the scorer receives sector data directly.

**File:** `backend/signals/pipeline.py`

**Find** this block inside `apply_scoring()` (it's after the contrarian qualification block):
```python
        # Sector rotation bonus
        try:
            from scoring.sector_rotation_bonus import get_sector_bonus
            sector_rot_bonus = await get_sector_bonus(signal_data)
            if sector_rot_bonus != 0:
                score = min(100, max(0, score + sector_rot_bonus))
                score = round(score, 2)
                triggering_factors["sector_rotation_bonus"] = sector_rot_bonus
        except ImportError:
            pass
        except Exception as sr_err:
            logger.debug(f"Sector rotation bonus failed: {sr_err}")
```

**Replace with:**
```python
        # Sector rotation bonus: REMOVED (Brief 6D)
        # Sector scoring is now handled inside calculate_signal_score() via the
        # sector_strength parameter. The old sector_rotation_bonus.py path was
        # a separate module that caused double-counting. All sector effects now
        # flow through SECTOR_PRIORITY_BONUS in trade_ideas_scorer.py.
```

---

## Step 4: Also Wire Sector into CTA Scanner Path

The CTA scanner in `bias_scheduler.py` also calls `calculate_signal_score()` without sector data.

**File:** `backend/scheduler/bias_scheduler.py`

**Find** in `run_cta_scan_scheduled()`:
```python
            # Calculate score using the new scoring algorithm
            score, bias_alignment, triggering_factors = calculate_signal_score(trade_signal, current_bias)
```

**Replace with:**
```python
            # Fetch sector strength from Redis for scoring
            sector_strength_data = None
            try:
                from database.redis_client import get_redis_client
                import json as _json
                redis = await get_redis_client()
                if redis:
                    raw = await redis.get("sector:strength")
                    if raw:
                        sector_strength_data = _json.loads(raw)
            except Exception:
                pass

            # Calculate score using the new scoring algorithm (with sector strength)
            score, bias_alignment, triggering_factors = calculate_signal_score(
                trade_signal, current_bias, sector_strength=sector_strength_data
            )
```

**Note:** This fetch will be fast (Redis read, <1ms) since sector data is refreshed every 15 seconds by the 6C loop. Don't refactor to fetch once outside the ticker loop — the data is cached and the overhead is negligible vs. the clarity of having it next to the scorer call.

---

## Step 5: Do NOT Delete `sector_rotation_bonus.py` Yet

The file `backend/scoring/sector_rotation_bonus.py` is no longer called, but keep it for reference until the next cleanup pass. It's now dead code but harmless. Add a comment at the top:

**File:** `backend/scoring/sector_rotation_bonus.py`

**Prepend** to the top of the file (before the existing docstring):
```python
# DEPRECATED (Brief 6D): This module is no longer called by the pipeline.
# Sector scoring is now handled via SECTOR_PRIORITY_BONUS in trade_ideas_scorer.py,
# which receives sector_strength data from Redis (refreshed every 15s by Brief 6C).
# Safe to delete in the next cleanup pass.
```

---

## How Scoring Now Works (Post-6D)

Example: Holy Grail LONG signal on NVDA (Technology sector)
- Sector strength ranks Technology as #1 (leading)
- Signal direction is LONG → aligned with leading sector
- Sector bonus: **+5**
- Total score: base(50) + technicals(15) + recency(8) + R:R(5) = 78 × bias(1.10) = 85.8 + sector(+5) = **90.8**

Same signal on NEE (Utilities, ranked #10, lagging):
- Signal direction is LONG → misaligned with lagging sector
- Sector bonus: **-8**
- Total score: 78 × 1.10 = 85.8 + sector(-8) = **77.8**

A 13-point swing between sectors. The NVDA signal shows in Insights as high-conviction. The NEE signal shows but is deprioritized. A weaker NEE signal (base 65 instead of 78) would score 71.5 + (-8) = **63.5** — below the 70 threshold, hidden from Insights entirely.

---

## Testing Checklist

1. **Sector bonus fires:** Score a signal for a ticker in a top-3 sector — `triggering_factors.sector_priority` should show `bonus: 5` and `tier: "leading"`
2. **Sector penalty fires:** Score a LONG signal for a ticker in a bottom-3 sector — should show `bonus: -8` and `tier: "lagging"`
3. **Middle sectors neutral:** Score a signal in rank #4-8 sector — should show `bonus: 0` and `tier: "neutral"`
4. **No double-counting:** `triggering_factors` should NOT contain both `sector_priority` and `sector_rotation_bonus`. Only `sector_priority` should appear.
5. **CTA scanner path:** CTA scanner signals should also have `sector_priority` in their triggering factors
6. **Redis unavailable:** If Redis is down, scoring still works (sector_strength=None, no sector bonus applied)
7. **All existing tests pass**

## Definition of Done
- [ ] `SECTOR_PRIORITY_BONUS` updated to +5/-8 asymmetric model
- [ ] Rank-based tiers: top 3 leading, bottom 3 lagging, middle 5 neutral
- [ ] `apply_scoring()` fetches sector strength from Redis and passes to scorer
- [ ] `run_cta_scan_scheduled()` also passes sector strength to scorer
- [ ] Old `sector_rotation_bonus` call removed from pipeline (no double-counting)
- [ ] `sector_rotation_bonus.py` marked as deprecated
- [ ] All existing tests pass
