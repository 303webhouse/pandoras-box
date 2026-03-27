# BRIEF: Contextual Modifier — Trade Idea Enrichment (Phase 4)

**Priority:** P0
**Depends on:** Phase 1 (Polygon snapshot cache), Phase 2 (sector_constituents table), Phase 3 (ticker_profiles, flow query patterns)
**Touches:** Backend (trade idea pipeline, new enrichment function), Frontend (app.js — trade idea cards)

---

## Summary

Every trade idea that enters the pipeline now gets a "second opinion" — a Contextual Confidence Modifier that checks four real-time factors about the ticker and nudges the score up or down. This automates the mental checklist Nick already runs when he sees a scanner alert: is the stock already moving in the trade's direction? Is there room left? Are big players participating? What are the options whales doing?

The modifier is bounded (max ±17 points on a 100-point scale), transparent (Nick can see which factors contributed), and runs asynchronously so it never slows down trade idea creation.

---

## How the Modifier Works (Plain English)

When a scanner fires and creates a trade idea (e.g., "COIN bearish signal, base score 70"), the enrichment function immediately checks four things:

1. **Sector-relative performance** — Is COIN already moving in the direction the trade expects? If COIN is lagging its sector (bad day for COIN specifically, not just the sector), that *confirms* a bearish signal → boost. If COIN is outperforming its sector despite a bearish signal → the signal is fighting momentum → degrade.

2. **RSI alignment** — Has the stock already moved too far (overbought/oversold) or does it have room to run? A bearish signal on a stock with RSI at 65 (still has room to fall) is better than one with RSI at 25 (already oversold, may bounce).

3. **Volume confirmation** — Are institutions participating in this move? High volume (>2x average) means the move has conviction. Low volume means it could reverse easily.

4. **Options flow alignment** — Are the options whales betting the same direction? If the scanner says "bearish" and UW flow is bearish, that's confirmation. If flow is bullish, the signal is fighting smart money.

Each factor adds or subtracts a small number of points. The total modifier (roughly -14 to +17) gets added to the base score. If 3+ factors *conflict* with the signal direction, the idea gets tagged as a "Contrarian Alert" — not buried, but flagged distinctly.

---

## Scoring Math

### Factor 1: Sector-Relative Performance

Measures: Is the ticker's move aligned with or against the trade direction, relative to its sector?

Calculate `sector_relative_pct` = ticker_day_change_pct - sector_etf_day_change_pct

**For BEARISH signals:**
| Condition | Points | Rationale |
|-----------|--------|-----------|
| Ticker lagging sector by > 2% | +5 | Strong confirmation — stock is already weak vs peers |
| Ticker lagging sector by 1-2% | +3 | Moderate confirmation |
| Within ±1% of sector | 0 | Moving with the group, no signal |
| Ticker outperforming sector by 1-2% | -3 | Fighting the signal — relative strength |
| Ticker outperforming sector by > 2% | -5 | Strongly fighting the signal |

**For BULLISH signals:** Reverse all signs (outperforming = positive, lagging = negative).

**Conflict flag:** Points are negative (signal fights relative performance).

### Factor 2: RSI Alignment

Measures: Does the stock have room to move in the trade direction, or is it already stretched?

**For BEARISH signals:**
| RSI Range | Points | Rationale |
|-----------|--------|-----------|
| > 70 | +5 | Overbought — plenty of room to fall, confirms short |
| 50-70 | +3 | Neutral-to-high — good entry zone for shorts |
| 35-50 | 0 | Neutral — no edge from RSI |
| 30-35 | -2 | Getting oversold — limited downside, risk of bounce |
| < 30 | -4 | Deeply oversold — high bounce risk, late to the party |

**For BULLISH signals:** Reverse (< 30 = +5 oversold bounce opportunity, > 70 = -4 overbought risk).

**Conflict flag:** Points are negative (RSI suggests limited room in trade direction).

### Factor 3: Volume Confirmation

Measures: Is there institutional participation in the current move?

| Volume Ratio | Points | Rationale |
|-------------|--------|-----------|
| > 2.0x avg | +4 | Heavy volume — institutions are participating, move has legs |
| 1.5-2.0x | +2 | Above average — decent participation |
| 1.0-1.5x | +1 | Slightly above average — marginal signal |
| 0.5-1.0x | 0 | Normal volume — no edge |
| < 0.5x | -3 | Thin volume — move is suspect, could reverse easily |

**Volume is direction-agnostic** — high volume confirms ANY move, low volume undermines ANY signal. No conflict flag from volume alone.

### Factor 4: Options Flow Alignment

Measures: Are the options whales betting the same direction as the signal?

Derive flow direction from `flow_events` table: last 24h of flow for this ticker. If net premium is >60% puts → "bearish flow". >60% calls → "bullish flow". Otherwise → "neutral".

**For BEARISH signals:**
| Flow Direction | Points | Rationale |
|---------------|--------|-----------|
| Bearish (matches) | +5 | Smart money agrees — strong confirmation |
| Neutral | 0 | No signal from flow |
| Bullish (contradicts) | -3 | Smart money disagrees — caution |

**For BULLISH signals:** Reverse (bullish flow = +5, bearish flow = -3).

**Conflict flag:** Points are negative (flow contradicts signal direction).

### Total Modifier

```
context_modifier = sector_points + rsi_points + volume_points + flow_points
```

**Range:** -14 to +17 (before any clamping)
**Clamp to:** -20 to +20 (safety bound in case scoring is extended later)

### Contrarian Detection

```
conflict_count = number of factors where points < 0
is_contrarian = conflict_count >= 3
```

If `is_contrarian` is true, the trade idea gets a distinct visual treatment. Maximum 3 active contrarian alerts at any time (oldest falls off when a new one arrives).

### Adjusted Score

```
adjusted_score = base_score + context_modifier
adjusted_score = max(5, min(100, adjusted_score))  # clamp to 5-100
```

---

## Backend Changes

### 1. New enrichment function

Create a new file: `backend/enrichment/context_modifier.py`

```python
"""
Contextual Confidence Modifier

Enriches trade ideas with a multi-factor context score that confirms
or challenges the scanner's signal using real-time market data.

Called asynchronously after trade idea creation. Reads from:
- Polygon snapshot cache (price, volume)
- Redis RSI cache
- sector_constituents table (sector membership, avg volume)
- flow_events table (options flow)

Never blocks trade idea creation. If any data source is unavailable,
that factor scores 0 and is flagged as "unavailable".
"""
```

**Core function signature:**

```python
async def enrich_trade_idea(trade_idea_id: int, ticker: str, direction: str, base_score: int) -> dict:
    """
    Calculate contextual modifier for a trade idea.
    
    Args:
        trade_idea_id: ID of the trade idea record to update
        ticker: Stock symbol
        direction: "bullish" or "bearish"
        base_score: Original scanner score (0-100)
    
    Returns:
        dict with modifier breakdown and adjusted score
    """
```

**Steps inside:**

1. Look up ticker's sector from `sector_constituents`
2. Get sector ETF's day change from Polygon snapshot cache
3. Get ticker's day change from Polygon snapshot cache
4. Calculate sector_relative_pct
5. Get RSI from Redis cache (if missing, score RSI factor as 0 with "unavailable" flag)
6. Get volume from snapshot, get avg_volume_20d from sector_constituents
7. Calculate volume_ratio
8. Query flow_events for last 24h, determine net flow direction
9. Calculate each factor's points using the tables above
10. Sum to context_modifier
11. Check contrarian flag
12. Calculate adjusted_score
13. Write results back to the trade idea record

### 2. Database changes — add columns to trade ideas table

Find the existing trade ideas table (likely `trade_ideas` or `signals` — search the codebase). Add these columns:

```sql
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS context_modifier INTEGER DEFAULT 0;
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS context_factors JSONB DEFAULT '{}';
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS adjusted_score INTEGER;
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS is_contrarian BOOLEAN DEFAULT FALSE;
ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS context_updated_at TIMESTAMPTZ;
```

**NOTE:** The actual table name may differ. Search the codebase for where trade ideas / signals are stored. The column names above are the target schema — adapt the ALTER statements to the actual table name.

The `context_factors` JSONB column stores the breakdown:

```json
{
    "sector_rel": {
        "points": 5,
        "value": -2.3,
        "label": "Lagging sector by 2.3%",
        "available": true
    },
    "rsi": {
        "points": 3,
        "value": 62,
        "label": "RSI at 62 — room to fall",
        "available": true
    },
    "volume": {
        "points": 4,
        "value": 2.3,
        "label": "Volume 2.3x average — heavy participation",
        "available": true
    },
    "flow": {
        "points": 5,
        "value": "bearish",
        "label": "Bearish flow — smart money agrees",
        "available": true
    }
}
```

If a factor's data source was unavailable, `available` is false and `points` is 0.

### 3. Hook into trade idea creation pipeline

Find where trade ideas are created/inserted in the codebase. After the INSERT (not before, not during — AFTER), fire the enrichment function asynchronously:

```python
# After trade idea is created and committed:
asyncio.create_task(enrich_trade_idea(
    trade_idea_id=new_idea.id,
    ticker=new_idea.ticker,
    direction=new_idea.direction,
    base_score=new_idea.score
))
```

**CRITICAL:** The enrichment MUST be async / fire-and-forget. The trade idea INSERT is on the critical path. The enrichment is housekeeping. If enrichment fails, the trade idea still exists with base_score — it just won't have a modifier until the next refresh.

### 4. Live modifier refresh

When the Agora dashboard polls for trade ideas (existing polling mechanism), the response should include the enrichment fields. The frontend uses these to display the modifier badges.

Additionally, for trade ideas that are still "active" (not expired/closed), the modifier should be recalculated periodically because prices change. Add a background task:

```python
async def refresh_active_modifiers():
    """
    Re-enrich trade ideas that are still active.
    Runs every 60 seconds during market hours.
    """
    active_ideas = get_active_trade_ideas()  # ideas from last 24h that aren't closed
    for idea in active_ideas:
        await enrich_trade_idea(idea.id, idea.ticker, idea.direction, idea.base_score)
        await asyncio.sleep(0.1)  # gentle rate limiting
```

This ensures that if Nick sees a trade idea card 2 hours after it was created, the modifier reflects CURRENT conditions, not stale ones from signal time.

### 5. Contrarian alert management

Maintain a simple counter/list of active contrarian alerts. When a new contrarian alert is created and there are already 3 active ones, mark the oldest one as `is_contrarian = False` (it keeps its modifier score, just loses the contrarian badge). This prevents contrarian alert fatigue.

Implementation: when setting `is_contrarian = True` on a new idea, query for existing contrarian ideas, and if count >= 3, set `is_contrarian = False` on the oldest one.

---

## Frontend Changes

### 1. Trade idea card modifications

Find the existing trade idea card rendering in app.js. Each card currently shows (at minimum) the ticker, strategy name, direction, and score. Add:

**Modifier badge:** Next to the existing score display, add a small colored badge:
- Green badge with "+" prefix for positive modifiers: `+12`
- Red badge with no prefix for negative modifiers: `-8`
- Gray badge with `0` for neutral modifiers

**Contrarian badge:** If `is_contrarian` is true, show a yellow `⚡ CONTRARIAN` badge. This replaces the normal modifier badge (don't show both).

**Adjusted score:** The main score display should show `adjusted_score` (not `base_score`). Show the base score in smaller text or on hover: "85 (base: 70 +15)"

### 2. Factor breakdown on click

Clicking the modifier badge (or the score area) expands a small detail panel below the card showing each factor in plain English:

```
✅ Lagging sector by 2.3% (aligns with short)        +5
✅ RSI at 62 — room to fall                           +3
✅ Volume 2.3x average — heavy participation          +4
✅ Bearish flow — smart money agrees                  +5
                                          Total: +17
```

Use checkmarks (✅) for confirming factors, warning signs (⚠️) for conflicting factors, and gray dashes (—) for neutral/unavailable factors. This is pulled directly from the `context_factors` JSONB — each factor has a pre-computed `label` and `points`.

### 3. Sorting and filtering

The Agora dashboard's trade ideas section should:
- **Default sort:** by `adjusted_score` descending (highest conviction first)
- **Filter option:** "Show Contrarian Only" toggle that filters to `is_contrarian = true`
- **Stale indicator:** If `context_updated_at` is more than 2 minutes old during market hours, show a subtle "⏳" icon indicating the modifier is being refreshed

### 4. Visual confidence bar (optional enhancement)

If space allows on the card, add a thin horizontal bar that visually represents the score:
- Bar background: dark gray
- Base score portion: blue fill
- Modifier portion: green extension (positive) or red reduction (negative)
- This makes it instantly visible whether the context is helping or hurting the signal

---

## Integration with Phase 3 (Single Ticker Analyzer)

When a trade idea card is clicked to open the Single Ticker Analyzer (Phase 3), the popup should:
1. Open the full ticker profile popup
2. Pre-populate the Olympus Review with the trade direction from the signal (so clicking "Run Olympus Review" sends the direction hint to the committee)
3. Scroll or highlight the relevant factor in the ticker profile that most strongly confirms or conflicts with the signal

This is a natural workflow: see high-conviction trade idea → click to investigate → see full profile → optionally run committee review → decide to trade.

---

## Testing Checklist

1. **Enrichment fires:** Create a trade idea (via scanner or manually) → verify `context_modifier`, `context_factors`, `adjusted_score` are populated within 1 second
2. **Factor math:** Manually verify the scoring for a known ticker:
   - Check sector_relative_pct calculation matches expected
   - Check RSI lookup returns correct cached value
   - Check volume_ratio calculation
   - Check flow direction derivation
3. **Async safety:** Kill the Redis connection mid-enrichment → trade idea still exists with base_score, modifier shows "unavailable" factors
4. **Bearish signal scoring:** Create a bearish signal on a stock lagging its sector with RSI 62, high volume, bearish flow → should get +15 to +17
5. **Bullish signal scoring:** Create a bullish signal on a stock outperforming sector with RSI 35, high volume, bullish flow → should get similar positive modifier
6. **Conflicting signal:** Create a bearish signal on a stock outperforming its sector with bullish flow → should get negative modifier and `is_contrarian = true` if 3+ factors conflict
7. **Contrarian cap:** Create 4+ contrarian alerts → only 3 should be active, oldest loses badge
8. **Frontend display:** Modifier badge shows correct value and color on trade idea cards
9. **Factor breakdown:** Clicking modifier shows plain-English breakdown
10. **Adjusted score sort:** Trade ideas sort by adjusted_score by default
11. **Live refresh:** A trade idea's modifier updates when the underlying data changes (e.g., RSI shifts, new flow event arrives)
12. **No blocking:** Time the trade idea creation path — enrichment should NOT add latency to the INSERT
13. **Market closed:** Outside market hours, modifier refresh runs every 5 minutes (not every 60 seconds)

---

## What This Brief Does NOT Cover

- Tuning the weight/points of each factor (start with the values above, adjust based on real-world observation)
- Daily digest / analytics of modifier performance (future build — log stats to Supabase for later analysis)
- Integration with position sizing (beta-aware sizing is flagged but not auto-calculated)
- Auto-trading based on adjusted score (all trade ideas remain manual-review)

---

## Notes for Claude Code

- Search the codebase for where trade ideas or signals are created/inserted to find the hook point for async enrichment
- The actual table name for trade ideas may be `trade_ideas`, `signals`, or something else — check the models/schema
- The enrichment function reads from multiple sources — handle each independently so partial data (e.g., RSI available but flow not) still produces a useful modifier
- The `context_factors` JSONB is pre-computed with human-readable labels — the frontend does NOT calculate or interpret the scores, it just displays what the backend provides
- Use the same Redis connection patterns as existing scanner code
- The contrarian cap (max 3) is a simple DB query, not an in-memory counter — it needs to survive restarts
- Factor labels should include the actual values (e.g., "RSI at 62" not just "RSI bullish") so Nick can evaluate the reasoning himself
