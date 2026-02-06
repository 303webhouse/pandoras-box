# Composite Bias Engine — Implementation Spec
**Status:** Ready to build
**Priority:** CRITICAL — This is the core fix for the Feb 2–5 failure
**Estimated effort:** ~300 lines of Python

## What This Does
Creates a single unified bias score from ALL available market factors, maps it to the 5-level bias system (URSA MAJOR → TORO MAJOR), and broadcasts changes via WebSocket.

## Why It's Needed
The old system at `/api/bias/summary` only read from Savita (monthly, often unavailable). Six weekly/daily factors existed in `/api/market-indicators/summary` but were NEVER wired into the bias output. During the Feb 2–5 NASDAQ crash (-4.5%), the system showed UNKNOWN/stale while it should have been screaming URSA MAJOR.

---

## File Location
**Create:** `backend/bias_engine/composite.py`
**Create:** `backend/bias_engine/__init__.py`
**Modify:** `backend/api/bias.py` — add new endpoints
**Modify:** `backend/main.py` — register new router

## Dependencies
- Existing: `redis`, `asyncpg`, `fastapi`, `pydantic`
- Existing bias_filters: All files in `backend/bias_filters/` (credit_spreads.py, market_breadth.py, vix_term_structure.py, tick_breadth.py, sector_rotation.py, dollar_smile.py, excess_cape_yield.py, savita_indicator.py)
- No new pip packages needed

---

## Data Model

### FactorReading (Pydantic model)
```python
class FactorReading(BaseModel):
    factor_id: str          # e.g., "credit_spreads", "vix_term"
    score: float            # -1.0 (max bearish) to +1.0 (max bullish)
    signal: str             # Human label: "URSA_MAJOR", "NEUTRAL", etc.
    detail: str             # Explanation: "HYG underperforming TLT by 2.3%"
    timestamp: datetime     # When this reading was taken
    source: str             # "pivot", "tradingview", "yfinance", "manual"
    raw_data: dict          # Raw values used to compute score (for debugging)
```

### CompositeResult (Pydantic model)
```python
class CompositeResult(BaseModel):
    composite_score: float          # -1.0 to +1.0
    bias_level: str                 # "URSA_MAJOR" | "URSA_MINOR" | "NEUTRAL" | "TORO_MINOR" | "TORO_MAJOR"
    bias_numeric: int               # 1-5 (matches existing frontend)
    factors: dict[str, FactorReading]  # All factor readings
    active_factors: list[str]       # Which factors contributed (not stale)
    stale_factors: list[str]        # Which factors were excluded
    velocity_multiplier: float      # 1.0 normal, 1.3 if rapid deterioration
    override: Optional[str]         # Manual override if active
    override_expires: Optional[datetime]
    timestamp: datetime
    confidence: str                 # "HIGH" (6+ active), "MEDIUM" (4-5), "LOW" (1-3)
```

---

## Factor Configuration

```python
FACTOR_CONFIG = {
    "credit_spreads": {
        "weight": 0.18,
        "staleness_hours": 48,
        "description": "HYG vs TLT ratio — measures credit market risk appetite",
    },
    "market_breadth": {
        "weight": 0.18,
        "staleness_hours": 48,
        "description": "RSP vs SPY ratio — equal-weight vs cap-weight divergence",
    },
    "vix_term": {
        "weight": 0.16,
        "staleness_hours": 4,
        "description": "VIX vs VIX3M — near-term fear vs longer-term expectations",
    },
    "tick_breadth": {
        "weight": 0.14,
        "staleness_hours": 4,
        "description": "Intraday TICK readings — buying/selling pressure",
    },
    "sector_rotation": {
        "weight": 0.14,
        "staleness_hours": 48,
        "description": "XLK/XLY vs XLP/XLU — offensive vs defensive flows",
    },
    "dollar_smile": {
        "weight": 0.08,
        "staleness_hours": 48,
        "description": "DXY trend — risk-on weakness vs risk-off strength",
    },
    "excess_cape": {
        "weight": 0.08,
        "staleness_hours": 168,  # 7 days
        "description": "Excess CAPE yield — valuation risk level",
    },
    "savita": {
        "weight": 0.04,
        "staleness_hours": 1080,  # 45 days
        "description": "BofA Sell Side Indicator — monthly contrarian sentiment",
    },
}
```

---

## Core Algorithm: `compute_composite()`

### Step 1: Gather Latest Readings
```python
async def compute_composite() -> CompositeResult:
    """Main entry point. Call on schedule or when new data arrives."""
    
    # Pull latest reading for each factor from Redis
    # Key pattern: bias:factor:{factor_id}:latest
    readings = {}
    for factor_id in FACTOR_CONFIG:
        reading = await get_latest_reading(factor_id)
        if reading:
            readings[factor_id] = reading
```

### Step 2: Classify Active vs Stale
```python
    now = datetime.utcnow()
    active = {}
    stale = []
    
    for factor_id, reading in readings.items():
        max_age = timedelta(hours=FACTOR_CONFIG[factor_id]["staleness_hours"])
        if (now - reading.timestamp) <= max_age:
            active[factor_id] = reading
        else:
            stale.append(factor_id)
    
    # Also mark factors with no reading at all as stale
    for factor_id in FACTOR_CONFIG:
        if factor_id not in readings:
            stale.append(factor_id)
```

### Step 3: Redistribute Weights (Graceful Degradation)
```python
    # Calculate total weight of active factors
    active_weight_sum = sum(FACTOR_CONFIG[f]["weight"] for f in active)
    
    if active_weight_sum == 0:
        # No active factors — return NEUTRAL with LOW confidence
        return CompositeResult(
            composite_score=0.0,
            bias_level="NEUTRAL",
            bias_numeric=3,
            factors=readings,
            active_factors=[],
            stale_factors=list(FACTOR_CONFIG.keys()),
            velocity_multiplier=1.0,
            override=None,
            override_expires=None,
            timestamp=now,
            confidence="LOW",
        )
    
    # Redistribute: each active factor's weight = base_weight / active_weight_sum
    # This ensures weights always sum to 1.0
    normalized_weights = {
        f: FACTOR_CONFIG[f]["weight"] / active_weight_sum
        for f in active
    }
```

### Step 4: Calculate Weighted Score
```python
    raw_score = sum(
        active[f].score * normalized_weights[f]
        for f in active
    )
    # Clamp to [-1.0, 1.0]
    raw_score = max(-1.0, min(1.0, raw_score))
```

### Step 5: Apply Rate-of-Change Velocity Multiplier
```python
    velocity_multiplier = 1.0
    
    # Check how many factors shifted bearish in last 24 hours
    bearish_shifts_24h = await count_bearish_shifts(hours=24)
    if bearish_shifts_24h >= 3:
        velocity_multiplier = 1.3
    
    # Apply multiplier (only amplifies, preserves sign, still clamps to [-1, 1])
    adjusted_score = max(-1.0, min(1.0, raw_score * velocity_multiplier))
```

### Step 6: Map to Bias Level
```python
    def score_to_bias(score: float) -> tuple[str, int]:
        if score >= 0.60:
            return "TORO_MAJOR", 5
        elif score >= 0.20:
            return "TORO_MINOR", 4
        elif score >= -0.19:
            return "NEUTRAL", 3
        elif score >= -0.59:
            return "URSA_MINOR", 2
        else:
            return "URSA_MAJOR", 1
    
    bias_level, bias_numeric = score_to_bias(adjusted_score)
```

### Step 7: Check Manual Override
```python
    override = await get_active_override()
    if override:
        # Override active — but check if composite has crossed a full level
        # in the opposite direction, which auto-clears the override
        override_level = bias_name_to_numeric(override["level"])
        if (override_level > 3 and bias_numeric <= 2) or \
           (override_level < 3 and bias_numeric >= 4):
            await clear_override(reason="composite_crossed_opposite")
            override = None
        else:
            bias_level = override["level"]
            bias_numeric = bias_name_to_numeric(override["level"])
```

### Step 8: Determine Confidence
```python
    active_count = len(active)
    if active_count >= 6:
        confidence = "HIGH"
    elif active_count >= 4:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
```

### Step 9: Build Result, Cache, Broadcast
```python
    result = CompositeResult(
        composite_score=adjusted_score,
        bias_level=bias_level,
        bias_numeric=bias_numeric,
        factors={f: readings.get(f) for f in FACTOR_CONFIG},
        active_factors=list(active.keys()),
        stale_factors=stale,
        velocity_multiplier=velocity_multiplier,
        override=override["level"] if override else None,
        override_expires=override.get("expires") if override else None,
        timestamp=now,
        confidence=confidence,
    )
    
    # Cache in Redis (key: bias:composite:latest, TTL: 86400)
    await cache_composite(result)
    
    # Log to PostgreSQL (table: bias_composite_history)
    await log_composite(result)
    
    # Broadcast via WebSocket
    await broadcast_bias_update(result)
    
    return result
```

---

## Helper Function: `count_bearish_shifts()`

```python
async def count_bearish_shifts(hours: int = 24) -> int:
    """
    Count how many factors shifted toward bearish in the given window.
    A 'shift' = factor score decreased by >= 0.3 from its previous reading.
    """
    count = 0
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    for factor_id in FACTOR_CONFIG:
        # Get current and previous readings from Redis sorted set
        # Key: bias:factor:{factor_id}:history (sorted by timestamp)
        current = await get_latest_reading(factor_id)
        previous = await get_reading_before(factor_id, cutoff)
        
        if current and previous:
            delta = current.score - previous.score
            if delta <= -0.3:  # Shifted 0.3+ toward bearish
                count += 1
    
    return count
```

---

## Redis Key Schema

| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `bias:factor:{factor_id}:latest` | JSON string | 86400s | Latest reading for each factor |
| `bias:factor:{factor_id}:history` | Sorted Set (score=timestamp) | 7 days | Rolling history for velocity calc |
| `bias:composite:latest` | JSON string | 86400s | Latest composite result |
| `bias:override` | JSON string | None (manual clear) | Active manual override |

---

## PostgreSQL Table

```sql
CREATE TABLE IF NOT EXISTS bias_composite_history (
    id SERIAL PRIMARY KEY,
    composite_score FLOAT NOT NULL,
    bias_level VARCHAR(20) NOT NULL,
    bias_numeric INTEGER NOT NULL,
    active_factors TEXT[] NOT NULL,
    stale_factors TEXT[] NOT NULL,
    velocity_multiplier FLOAT NOT NULL DEFAULT 1.0,
    override VARCHAR(20),
    confidence VARCHAR(10) NOT NULL,
    factor_scores JSONB NOT NULL,  -- {factor_id: score} snapshot
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_bias_history_created ON bias_composite_history(created_at);
```

---

## API Endpoints (add to `backend/api/bias.py`)

### GET /api/bias/composite
Returns the latest composite bias with full factor breakdown.

**Response:**
```json
{
    "composite_score": -0.68,
    "bias_level": "URSA_MAJOR",
    "bias_numeric": 1,
    "confidence": "HIGH",
    "velocity_multiplier": 1.3,
    "override": null,
    "active_factors": ["credit_spreads", "market_breadth", "vix_term", "tick_breadth", "sector_rotation", "dollar_smile", "excess_cape"],
    "stale_factors": ["savita"],
    "factors": {
        "credit_spreads": {
            "score": -0.5,
            "signal": "URSA_MINOR",
            "detail": "HYG underperforming TLT by 1.8%",
            "timestamp": "2026-02-05T15:30:00Z",
            "source": "pivot"
        }
    },
    "timestamp": "2026-02-05T15:35:00Z"
}
```

### POST /api/bias/factor-update
Pivot or TradingView POSTs new factor data here. This triggers a recomputation.

**Request:**
```json
{
    "factor_id": "credit_spreads",
    "score": -0.5,
    "signal": "URSA_MINOR",
    "detail": "HYG underperforming TLT by 1.8%",
    "source": "pivot",
    "raw_data": {
        "hyg_price": 72.45,
        "tlt_price": 88.20,
        "ratio": 0.821,
        "ratio_sma20": 0.835,
        "pct_below_sma": -1.67
    }
}
```

**Response:** Returns the new CompositeResult after recomputation.

### POST /api/bias/override
Manual bias override from the UI.

**Request:**
```json
{
    "level": "TORO_MINOR",
    "reason": "Expecting bounce after oversold conditions",
    "expires_hours": 24
}
```

### DELETE /api/bias/override
Clear manual override.

### GET /api/bias/history
Historical composite readings for backtesting/charts.

**Query params:** `?hours=72` (default 24)

---

## WebSocket Message Format

When composite changes, broadcast:
```json
{
    "type": "BIAS_UPDATE",
    "data": {
        "bias_level": "URSA_MAJOR",
        "bias_numeric": 1,
        "composite_score": -0.68,
        "confidence": "HIGH",
        "override": null,
        "changed_from": "URSA_MINOR",
        "timestamp": "2026-02-05T15:35:00Z"
    }
}
```

---

## Execution Schedule

The composite should recompute:
1. **On every factor update** — when `POST /api/bias/factor-update` receives data
2. **Every 15 minutes** — as a safety net to catch staleness transitions
3. **On manual override** — immediate recompute + broadcast

Use the existing scheduler in `backend/scheduler/` to add the 15-minute cron.

---

## Integration Checklist

- [ ] Create `backend/bias_engine/__init__.py`
- [ ] Create `backend/bias_engine/composite.py` with all logic above
- [ ] Add PostgreSQL table `bias_composite_history`
- [ ] Add new endpoints to `backend/api/bias.py`
- [ ] Register endpoints in `backend/main.py`
- [ ] Add 15-minute scheduler job
- [ ] Update WebSocket broadcast to use new composite format
- [ ] Test with mock factor data
- [ ] Verify graceful degradation (remove factors one by one)
- [ ] Verify velocity multiplier triggers correctly

## What NOT to Change
- Do NOT remove existing `/api/bias/{timeframe}` endpoints — they may still be used
- Do NOT modify existing bias_filters files — they will be called by the factor scoring layer (see `factor-scoring.md`)
- Do NOT touch the frontend yet — see `bias-frontend.md` for that
