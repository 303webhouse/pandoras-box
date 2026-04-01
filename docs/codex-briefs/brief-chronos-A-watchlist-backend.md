# BRIEF: Chronos Phase A — Trade Idea Watchlist Backend
## Priority: P0 | System: Railway Postgres + FastAPI
## Date: 2026-04-01
## Related: Chronos Phase B (Earnings Calendar), Phase C (Frontend)

---

## CONTEXT FOR CLAUDE CODE

This is a **new trade idea staging system** — NOT the existing RADAR/watchlist ticker screener in `api/watchlist.py`. That existing system manages sector-organized tickers for scanner prioritization. This new system is a separate **Long/Short ideas pipeline** where Nick stages potential trades before committing capital.

**The pipeline:** Idea → Watchlist → Olympus Committee Review → Position (in `unified_positions`)

Each watchlist entry tracks: ticker, direction (LONG/SHORT), entry target price, thesis note, committee grade, source, and current price. When a ticker hits its entry target, a Hermes-style alert fires so Nick can act.

**Database is Railway Postgres** (NOT Supabase). Use `get_postgres_client()` from `backend/database/postgres_client.py` for all DB operations.

**Data sources:**
- Polygon.io for price snapshots (already integrated, env: `POLYGON_API_KEY`)
- Earnings dates will come from Chronos Phase B (leave `next_earnings_date` nullable for now)

---

## STEP 1: Database — `trade_watchlist` Table

Create the table in `database/postgres_client.py` inside `init_database()`, following the existing pattern for table creation.

```sql
CREATE TABLE IF NOT EXISTS trade_watchlist (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_target NUMERIC(10,2),
    current_price NUMERIC(10,2),
    distance_to_target_pct NUMERIC(6,2),
    thesis_note TEXT,
    committee_grade TEXT CHECK (committee_grade IN ('A', 'A-', 'B+', 'B', 'B-', 'C', NULL)),
    source TEXT DEFAULT 'MANUAL' CHECK (source IN ('MANUAL', 'UW_FLOW', 'SCANNER', 'COMMITTEE')),
    bucket TEXT CHECK (bucket IN ('THESIS', 'TACTICAL', NULL)),
    next_earnings_date DATE,
    earnings_timing TEXT CHECK (earnings_timing IN ('BMO', 'AMC', 'TNS', NULL)),
    alert_fired BOOLEAN DEFAULT FALSE,
    alert_fired_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_watchlist_ticker UNIQUE (ticker)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_active ON trade_watchlist (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_watchlist_direction ON trade_watchlist (direction);
```

**Important:** The `UNIQUE (ticker)` constraint means one entry per ticker. If Nick wants to re-add a previously removed ticker, the old row gets reactivated (not duplicated).

---

## STEP 2: API Routes — `api/trade_watchlist.py`

Create a NEW file `backend/api/trade_watchlist.py`. Do NOT modify the existing `api/watchlist.py` (that's the RADAR system).

```python
"""
Trade Watchlist API — Long/Short idea staging area
Separate from the RADAR ticker screener (api/watchlist.py)

Endpoints:
- GET    /trade-watchlist              — List all active watchlist entries
- POST   /trade-watchlist              — Add a new ticker
- PATCH  /trade-watchlist/{id}         — Update entry (grade, target, thesis, etc.)
- DELETE /trade-watchlist/{id}         — Soft-delete (set is_active = FALSE)
- POST   /trade-watchlist/{id}/reactivate — Reactivate a soft-deleted entry
- GET    /trade-watchlist/alerts       — Get entries where alert has fired
"""
```

### Route Details:

**GET `/trade-watchlist`**
- Query params: `direction` (optional, LONG/SHORT), `active_only` (default True)
- Returns all active entries, sorted by `distance_to_target_pct ASC` (closest to entry target first) within each direction group
- Response shape:
```json
{
  "long_ideas": [ ... ],
  "short_ideas": [ ... ],
  "total": 5,
  "alerts_pending": 1
}
```

**POST `/trade-watchlist`**
- Body (Pydantic model `WatchlistEntry`):
```python
class WatchlistEntry(BaseModel):
    ticker: str                    # Required, uppercase
    direction: str                 # Required: LONG or SHORT
    entry_target: Optional[float]  # Target entry price
    thesis_note: Optional[str]     # One-line thesis
    committee_grade: Optional[str] # A, A-, B+, B, B-, C
    source: str = "MANUAL"         # MANUAL, UW_FLOW, SCANNER, COMMITTEE
    bucket: Optional[str]          # THESIS or TACTICAL
```
- On insert: immediately fetch current price from Polygon snapshot (`/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}`)
- Compute `distance_to_target_pct`:
  - For LONG: `((current_price - entry_target) / entry_target) * 100` (positive = above target, negative = below)
  - For SHORT: `((entry_target - current_price) / current_price) * 100` (positive = above target, negative = below)
- If ticker already exists but `is_active = FALSE`, reactivate it with new values instead of inserting
- Return the created/reactivated entry

**PATCH `/trade-watchlist/{id}`**
- Accepts partial updates to any field except `ticker` and `id`
- Updates `updated_at` timestamp
- If `entry_target` changes, recalculate `distance_to_target_pct`

**DELETE `/trade-watchlist/{id}`**
- Soft delete: sets `is_active = FALSE`
- Does NOT remove the row (preserves history)

---

## STEP 3: Price Alert Background Loop — in `main.py` lifespan

Add a new background task in the `lifespan()` function following the existing pattern (e.g., `mark_to_market_loop`, `universe_cache_loop`).

```python
# Watchlist price alert: check every 30 min during market hours
async def watchlist_price_alert_loop():
    """Check watchlist tickers for entry target crossings."""
    import pytz
    from datetime import datetime as dt_cls
    
    await asyncio.sleep(120)  # 2 min startup delay
    
    while True:
        try:
            et = dt_cls.now(pytz.timezone("America/New_York"))
            # Market hours: 9:30 AM - 4:00 PM ET, weekdays
            if et.weekday() < 5 and 9 <= et.hour < 16:
                from api.trade_watchlist import check_watchlist_price_alerts
                await check_watchlist_price_alerts()
            else:
                logger.debug("Watchlist alerts: outside market hours, skipping")
        except Exception as e:
            logger.warning("Watchlist price alert error: %s", e)
        await asyncio.sleep(1800)  # 30 minutes

watchlist_alert_task = asyncio.create_task(watchlist_price_alert_loop())
```

Don't forget to add `watchlist_alert_task.cancel()` in the shutdown section of `lifespan()`.

### The `check_watchlist_price_alerts()` function (in `api/trade_watchlist.py`):

```python
async def check_watchlist_price_alerts():
    """
    For each active watchlist entry where alert_fired = FALSE:
    1. Fetch current price from Polygon snapshot
    2. Update current_price and distance_to_target_pct in DB
    3. If price has crossed the entry target:
       - LONG: current_price <= entry_target (price dropped to target)
       - SHORT: current_price >= entry_target (price rose to target)
       → Set alert_fired = TRUE, alert_fired_at = NOW()
       → Fire Hermes-style webhook (see Step 4)
    """
```

**Polygon price fetch:** Use the existing Polygon snapshot pattern from the codebase. The endpoint is:
```
GET https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}?apiKey={key}
```
Batch multiple tickers efficiently. The watchlist will have 5-15 tickers max, so individual snapshot calls are fine (not worth batching).

---

## STEP 4: Alert Delivery — WebSocket Push

When an entry target is hit, push a WebSocket message so the Agora UI can display it immediately (same pattern as Hermes Flash alerts).

```python
from websocket.broadcaster import manager

async def fire_watchlist_alert(entry: dict):
    """Push watchlist target hit to all connected clients."""
    alert_payload = {
        "type": "watchlist_alert",
        "ticker": entry["ticker"],
        "direction": entry["direction"],
        "entry_target": float(entry["entry_target"]),
        "current_price": float(entry["current_price"]),
        "thesis_note": entry.get("thesis_note", ""),
        "committee_grade": entry.get("committee_grade"),
        "bucket": entry.get("bucket"),
        "fired_at": entry["alert_fired_at"].isoformat() if entry.get("alert_fired_at") else None
    }
    await manager.broadcast(alert_payload)
    logger.info(f"🎯 WATCHLIST ALERT: {entry['ticker']} hit target ${entry['entry_target']} (direction: {entry['direction']})")
```

The frontend will handle this in Phase C. For now, just make sure the broadcast fires.

---

## STEP 5: Wire Into `main.py`

Add the import and router registration following the existing pattern:

**Import block** (around line 640-660 in main.py, with the other router imports):
```python
from api.trade_watchlist import router as trade_watchlist_router
```

**Router registration** (around line 670-710, with the other `app.include_router` calls):
```python
app.include_router(trade_watchlist_router, prefix="/api", tags=["trade-watchlist"])
```

**Init call** in `lifespan()` startup section (after the existing watchlist init):
```python
# Initialize trade watchlist table
try:
    from api.trade_watchlist import init_trade_watchlist_table
    await init_trade_watchlist_table()
    logger.info("✅ Trade watchlist table ready")
except Exception as e:
    logger.warning(f"⚠️ Could not initialize trade watchlist table: {e}")
```

The `init_trade_watchlist_table()` function runs the CREATE TABLE IF NOT EXISTS from Step 1.

---

## STEP 6: Position Overlap Utility — `utils/position_overlap.py`

Create a shared utility that answers: "does this ticker appear in any of Nick's positions, either directly or as a top holding of an ETF he holds?"

This utility will be used by Watchlist (this brief), Hydra (already deployed), and Chronos (Phase B).

```python
"""
Position Overlap Utility
Checks if a ticker overlaps with any position in unified_positions,
either directly or as a top-10 ETF component.
"""

# Hardcoded ETF top-10 holdings (updated quarterly)
# Source: FMP ETF holdings API or iShares/Vanguard factsheets
ETF_COMPONENTS = {
    "XLF": ["JPM", "BRK.B", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "AXP"],
    "SMH": ["NVDA", "TSM", "AVGO", "ASML", "TXN", "QCOM", "AMD", "AMAT", "LRCX", "MU"],
    "HYG": [],  # Bond ETF — no single-stock components to track
    "IYR": ["PLD", "AMT", "EQIX", "WELL", "SPG", "DLR", "PSA", "O", "CCI", "VICI"],
    "IWM": [],  # 2000 stocks — too broad, skip component matching
    "IBIT": [],  # Bitcoin ETF — no equity components
}

async def check_position_overlap(ticker: str) -> dict:
    """
    Returns:
    {
        "overlaps": True/False,
        "positions": ["XLF", "SMH"],  # which positions this ticker touches
        "relationship": "component"    # "direct" or "component"
    }
    """
    from database.postgres_client import get_postgres_client
    
    client = await get_postgres_client()
    
    # Get all active position tickers
    rows = await client.fetch(
        "SELECT ticker FROM unified_positions WHERE status = 'OPEN'"
    )
    position_tickers = [r["ticker"] for r in rows]
    
    # Direct match
    if ticker in position_tickers:
        return {"overlaps": True, "positions": [ticker], "relationship": "direct"}
    
    # Component match: is this ticker in any ETF that Nick holds?
    overlapping_positions = []
    for pos_ticker in position_tickers:
        components = ETF_COMPONENTS.get(pos_ticker, [])
        if ticker in components:
            overlapping_positions.append(pos_ticker)
    
    if overlapping_positions:
        return {"overlaps": True, "positions": overlapping_positions, "relationship": "component"}
    
    return {"overlaps": False, "positions": [], "relationship": None}
```

**Note:** The `ETF_COMPONENTS` dict is hardcoded for now. Chronos Phase B will add FMP-powered auto-refresh of these holdings. For V1, hardcoded is fine — these top 10 lists don't change often.

---

## VERIFICATION CHECKLIST

After deploying, verify these endpoints work:

1. `POST /api/trade-watchlist` with body `{"ticker": "URA", "direction": "LONG", "entry_target": 42.00, "thesis_note": "Nuclear + AI baseload demand", "committee_grade": "A", "source": "MANUAL"}` → should return created entry with current_price populated
2. `GET /api/trade-watchlist` → should return `{"long_ideas": [...], "short_ideas": [...], "total": 1, "alerts_pending": 0}`
3. `PATCH /api/trade-watchlist/{id}` with `{"entry_target": 40.00}` → should recalculate distance
4. `DELETE /api/trade-watchlist/{id}` → should soft-delete
5. Check logs during market hours for `watchlist_price_alert_loop` running every 30 min
6. `GET /api/trade-watchlist/alerts` → returns entries where alert_fired = TRUE

---

## FILES CREATED/MODIFIED

| File | Action |
|------|--------|
| `backend/api/trade_watchlist.py` | **CREATE** — Full CRUD + price alert logic |
| `backend/utils/position_overlap.py` | **CREATE** — Shared overlap utility |
| `backend/main.py` | **MODIFY** — Add router import, include_router, init call, background task |
| `backend/database/postgres_client.py` | **MODIFY** — Add CREATE TABLE in init_database() |

**Do NOT touch:** `backend/api/watchlist.py` (that's the existing RADAR system — completely separate)
