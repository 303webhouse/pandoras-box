# Watchlist v2 — Enriched, Sortable, Bias-Aware

**Spec for:** `backend/api/watchlist.py`, `backend/watchlist/enrichment.py` (new), `frontend/app.js`
**Depends on:** Composite Bias Engine (see `docs/specs/composite-bias-engine.md`), CTA Scanner, Redis, PostgreSQL
**Priority:** Build AFTER composite bias engine (needs sector rotation factor data)

---

## Problem Statement

The current watchlist (`backend/api/watchlist.py`) is a CRUD service for ticker name strings stored in a JSON file. It returns data like `{"Technology": {"tickers": ["AAPL","MSFT"], "etf": "XLK"}}` with **zero market data** — no prices, no daily changes, no volume, no CTA zones, no signal counts. The `sector_strength` field is permanently `{}` because nothing ever calls the POST endpoint that populates it. Storage uses `data/watchlist.json` on disk, which gets wiped on every Railway deploy.

The frontend gets a bag of strings and has nothing to render → blank watchlist section.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    WATCHLIST v2                          │
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐ │
│  │PostgreSQL│◄───│ Watchlist     │───►│ Redis Cache   │ │
│  │(config)  │    │ Enrichment   │    │ (prices, ETFs)│ │
│  └──────────┘    │ Engine       │    └───────────────┘ │
│                  └──────┬───────┘                       │
│                         │                               │
│           ┌─────────────┼──────────────┐                │
│           │             │              │                │
│    ┌──────▼──┐   ┌──────▼──┐   ┌──────▼──────┐        │
│    │yfinance │   │CTA      │   │Composite    │        │
│    │(prices) │   │Scanner  │   │Bias Engine  │        │
│    └─────────┘   │(zones)  │   │(sector rot.)│        │
│                  └─────────┘   └─────────────┘        │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ GET /watchlist/      │
              │     enriched        │
              │                     │
              │ Frontend renders    │
              │ enriched grid with  │
              │ sector cards,       │
              │ ticker rows,        │
              │ sort controls       │
              └─────────────────────┘
```

---

## 1. Backend: Enrichment Engine

### File: `backend/watchlist/enrichment.py` (NEW)

This is the core new module. It takes the watchlist config (tickers + sectors) and enriches every ticker and sector ETF with live market data, CTA zones, and bias alignment.

```python
"""
Watchlist Enrichment Engine
Pulls live market data for all watchlist tickers and sector ETFs,
attaches CTA zones and bias alignment, caches in Redis.
"""

import yfinance as yf
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────

ENRICHMENT_CACHE_KEY = "watchlist:enriched"
ENRICHMENT_CACHE_TTL = 300  # 5 minutes
SECTOR_STRENGTH_CACHE_KEY = "watchlist:sector_strength"
SECTOR_STRENGTH_CACHE_TTL = 900  # 15 minutes

# Sector ETF → SPY relative strength benchmark
BENCHMARK_TICKER = "SPY"


# ─── Data Models ─────────────────────────────────────────

class EnrichedTicker:
    """Enriched data for a single ticker."""
    def __init__(self):
        self.symbol: str = ""
        self.price: Optional[float] = None
        self.change_1d: Optional[float] = None      # daily % change
        self.change_1w: Optional[float] = None      # weekly % change
        self.volume: Optional[int] = None
        self.volume_avg: Optional[int] = None       # 20-day avg volume
        self.cta_zone: Optional[str] = None         # from CTA scanner: MAX_LONG, DE_LEVERAGING, WATERFALL, CAPITULATION, etc.
        self.active_signals: int = 0                 # count of active signals from Redis
        self.last_updated: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "change_1d": self.change_1d,
            "change_1w": self.change_1w,
            "volume": self.volume,
            "volume_avg": self.volume_avg,
            "cta_zone": self.cta_zone,
            "active_signals": self.active_signals,
            "last_updated": self.last_updated,
        }


class EnrichedSector:
    """Enriched data for a sector grouping."""
    def __init__(self):
        self.name: str = ""
        self.etf: Optional[str] = None
        self.etf_price: Optional[float] = None
        self.etf_change_1d: Optional[float] = None
        self.etf_change_1w: Optional[float] = None
        self.vs_spy_1d: Optional[float] = None      # sector ETF daily change minus SPY daily change
        self.vs_spy_1w: Optional[float] = None      # sector ETF weekly change minus SPY weekly change
        self.strength_rank: Optional[int] = None     # 1 = strongest sector, ascending
        self.trend: str = "neutral"                  # "strengthening", "weakening", "neutral"
        self.bias_alignment: Optional[str] = None    # from composite bias sector rotation factor
        self.tickers: List[dict] = []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "etf": self.etf,
            "etf_price": self.etf_price,
            "etf_change_1d": self.etf_change_1d,
            "etf_change_1w": self.etf_change_1w,
            "vs_spy_1d": self.vs_spy_1d,
            "vs_spy_1w": self.vs_spy_1w,
            "strength_rank": self.strength_rank,
            "trend": self.trend,
            "bias_alignment": self.bias_alignment,
            "tickers": self.tickers,
        }


# ─── Price Fetching ──────────────────────────────────────

def fetch_price_data(symbols: List[str]) -> Dict[str, dict]:
    """
    Bulk-fetch current price, daily change, weekly change for a list of symbols.
    Uses yfinance bulk download for efficiency.
    
    Returns: {
        "AAPL": {"price": 228.15, "change_1d": -1.8, "change_1w": -3.2, "volume": 45000000, "volume_avg": 52000000},
        ...
    }
    """
    result = {}
    try:
        # Get 10 trading days of history (covers 1 week + buffer for holidays)
        data = yf.download(
            tickers=symbols,
            period="10d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
        )
        
        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    ticker_data = data
                else:
                    ticker_data = data[symbol]
                
                if ticker_data.empty or len(ticker_data) < 2:
                    result[symbol] = {"price": None, "change_1d": None, "change_1w": None, "volume": None, "volume_avg": None}
                    continue
                
                current_price = float(ticker_data["Close"].iloc[-1])
                prev_close = float(ticker_data["Close"].iloc[-2])
                
                # Daily change %
                change_1d = round(((current_price - prev_close) / prev_close) * 100, 2)
                
                # Weekly change % (5 trading days ago, or earliest available)
                week_idx = min(5, len(ticker_data) - 1)
                week_ago_close = float(ticker_data["Close"].iloc[-week_idx - 1]) if len(ticker_data) > week_idx else float(ticker_data["Close"].iloc[0])
                change_1w = round(((current_price - week_ago_close) / week_ago_close) * 100, 2)
                
                # Volume
                current_volume = int(ticker_data["Volume"].iloc[-1]) if "Volume" in ticker_data.columns else None
                avg_volume = int(ticker_data["Volume"].mean()) if "Volume" in ticker_data.columns else None
                
                result[symbol] = {
                    "price": round(current_price, 2),
                    "change_1d": change_1d,
                    "change_1w": change_1w,
                    "volume": current_volume,
                    "volume_avg": avg_volume,
                }
            except Exception as e:
                logger.warning(f"Error processing {symbol}: {e}")
                result[symbol] = {"price": None, "change_1d": None, "change_1w": None, "volume": None, "volume_avg": None}
    
    except Exception as e:
        logger.error(f"Bulk price fetch failed: {e}")
        for s in symbols:
            result[s] = {"price": None, "change_1d": None, "change_1w": None, "volume": None, "volume_avg": None}
    
    return result


# ─── CTA Zone Lookup ─────────────────────────────────────

def get_cta_zones(symbols: List[str], redis_client) -> Dict[str, Optional[str]]:
    """
    Look up CTA zone for each ticker from Redis.
    CTA scanner stores zones at key: cta:zone:{SYMBOL}
    
    Possible zones: MAX_LONG, LEVERAGED_LONG, DE_LEVERAGING, 
                    WATERFALL, CAPITULATION, RECOVERY, NEUTRAL
    
    If CTA scanner hasn't run for a ticker, returns None.
    """
    zones = {}
    for symbol in symbols:
        try:
            zone = redis_client.get(f"cta:zone:{symbol}")
            zones[symbol] = zone.decode() if zone else None
        except Exception:
            zones[symbol] = None
    return zones


# ─── Active Signal Lookup ────────────────────────────────

def get_active_signals(symbols: List[str], redis_client) -> Dict[str, int]:
    """
    Count active (non-dismissed) signals per ticker from Redis.
    Signal keys: signal:active:{SYMBOL}
    
    Returns: {"AAPL": 2, "NVDA": 0, ...}
    """
    counts = {}
    for symbol in symbols:
        try:
            count = redis_client.get(f"signal:active:{symbol}")
            counts[symbol] = int(count) if count else 0
        except Exception:
            counts[symbol] = 0
    return counts


# ─── Sector Strength Computation ─────────────────────────

def compute_sector_strength(sectors: Dict[str, dict], price_data: Dict[str, dict]) -> Dict[str, dict]:
    """
    Compute relative strength of each sector vs SPY.
    
    Returns sector_strength dict suitable for POST /watchlist/sector-strength
    and for caching in Redis.
    
    Logic:
    - For each sector with an ETF, compute: etf_change_1w - spy_change_1w
    - Rank sectors by this relative performance (1 = best)
    - Determine trend: if vs_spy_1d and vs_spy_1w same sign = "strengthening" or "weakening"
                        otherwise "neutral"
    """
    spy_data = price_data.get(BENCHMARK_TICKER, {})
    spy_1d = spy_data.get("change_1d", 0) or 0
    spy_1w = spy_data.get("change_1w", 0) or 0
    
    sector_scores = []
    
    for sector_name, sector_config in sectors.items():
        etf = sector_config.get("etf")
        if not etf or etf not in price_data:
            sector_scores.append({
                "name": sector_name,
                "vs_spy_1d": None,
                "vs_spy_1w": None,
                "trend": "neutral",
            })
            continue
        
        etf_data = price_data.get(etf, {})
        etf_1d = etf_data.get("change_1d", 0) or 0
        etf_1w = etf_data.get("change_1w", 0) or 0
        
        vs_spy_1d = round(etf_1d - spy_1d, 2)
        vs_spy_1w = round(etf_1w - spy_1w, 2)
        
        # Determine trend
        if vs_spy_1d > 0.3 and vs_spy_1w > 0.5:
            trend = "strengthening"
        elif vs_spy_1d < -0.3 and vs_spy_1w < -0.5:
            trend = "weakening"
        else:
            trend = "neutral"
        
        sector_scores.append({
            "name": sector_name,
            "vs_spy_1d": vs_spy_1d,
            "vs_spy_1w": vs_spy_1w,
            "trend": trend,
        })
    
    # Rank by vs_spy_1w (highest = strongest = rank 1)
    ranked = sorted(
        [s for s in sector_scores if s["vs_spy_1w"] is not None],
        key=lambda x: x["vs_spy_1w"],
        reverse=True,
    )
    
    strength_map = {}
    for rank, s in enumerate(ranked, 1):
        strength_map[s["name"]] = {
            "strength": s["vs_spy_1w"],
            "vs_spy_1d": s["vs_spy_1d"],
            "trend": s["trend"],
            "rank": rank,
        }
    
    # Add unranked sectors
    for s in sector_scores:
        if s["name"] not in strength_map:
            strength_map[s["name"]] = {
                "strength": None,
                "vs_spy_1d": None,
                "trend": "neutral",
                "rank": 999,
            }
    
    return strength_map


# ─── Bias Alignment Lookup ───────────────────────────────

def get_sector_bias_alignment(redis_client) -> Dict[str, str]:
    """
    Read the composite bias engine's sector rotation factor to determine
    which sectors align with the current macro bias.
    
    Reads from Redis key: bias:factor:sector_rotation:latest
    
    Returns: {"Technology": "URSA", "Energy": "TORO", ...}
    
    If composite bias engine hasn't computed yet, returns empty dict.
    Falls back gracefully.
    """
    alignment = {}
    try:
        rotation_data = redis_client.get("bias:factor:sector_rotation:latest")
        if rotation_data:
            data = json.loads(rotation_data)
            # Sector rotation factor tells us offensive vs defensive
            # If offensive sectors outperforming → TORO alignment for offensive sectors
            # If defensive outperforming → URSA alignment for offensive sectors
            score = data.get("score", 0)
            
            offensive_sectors = ["Technology", "Consumer Discretionary", "Financials", "Industrials"]
            defensive_sectors = ["Healthcare", "Energy"]  # Energy often acts as inflation hedge
            
            if score > 0.2:
                for s in offensive_sectors:
                    alignment[s] = "TORO"
                for s in defensive_sectors:
                    alignment[s] = "NEUTRAL"
            elif score < -0.2:
                for s in offensive_sectors:
                    alignment[s] = "URSA"
                for s in defensive_sectors:
                    alignment[s] = "TORO"
            else:
                for s in offensive_sectors + defensive_sectors:
                    alignment[s] = "NEUTRAL"
    except Exception as e:
        logger.warning(f"Could not read sector bias alignment: {e}")
    
    return alignment


# ─── Main Enrichment Function ────────────────────────────

async def enrich_watchlist(watchlist_data: dict, redis_client) -> dict:
    """
    Main entry point. Takes raw watchlist config, returns fully enriched response.
    
    1. Collect all unique tickers + sector ETFs + SPY
    2. Bulk fetch prices from yfinance (or Redis cache)
    3. Look up CTA zones from Redis
    4. Look up active signal counts from Redis
    5. Compute sector strength vs SPY
    6. Look up bias alignment from composite engine
    7. Assemble enriched response
    8. Cache in Redis for 5 minutes
    
    Args:
        watchlist_data: Raw watchlist from load_watchlist_data()
        redis_client: Redis connection
    
    Returns: Enriched response dict (see API Response section below)
    """
    
    # Step 0: Check cache first
    cached = redis_client.get(ENRICHMENT_CACHE_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass  # Cache corrupted, recompute
    
    sectors = watchlist_data.get("sectors", {})
    
    # Step 1: Collect all symbols we need prices for
    all_tickers = []
    all_etfs = []
    for sector_name, sector_config in sectors.items():
        tickers = sector_config.get("tickers", [])
        all_tickers.extend(tickers)
        etf = sector_config.get("etf")
        if etf:
            all_etfs.append(etf)
    
    all_tickers = list(set(all_tickers))
    all_etfs = list(set(all_etfs))
    all_symbols = list(set(all_tickers + all_etfs + [BENCHMARK_TICKER]))
    
    # Step 2: Bulk fetch prices
    price_data = fetch_price_data(all_symbols)
    
    # Step 3: CTA zones for tickers
    cta_zones = get_cta_zones(all_tickers, redis_client)
    
    # Step 4: Active signal counts
    signal_counts = get_active_signals(all_tickers, redis_client)
    
    # Step 5: Sector strength
    sector_strength = compute_sector_strength(sectors, price_data)
    
    # Step 6: Bias alignment
    bias_alignment = get_sector_bias_alignment(redis_client)
    
    # Step 7: Assemble enriched sectors
    enriched_sectors = []
    spy_data = price_data.get(BENCHMARK_TICKER, {})
    spy_1d = spy_data.get("change_1d", 0) or 0
    spy_1w = spy_data.get("change_1w", 0) or 0
    
    for sector_name, sector_config in sectors.items():
        etf = sector_config.get("etf")
        etf_data = price_data.get(etf, {}) if etf else {}
        strength = sector_strength.get(sector_name, {})
        
        enriched_tickers = []
        for ticker in sector_config.get("tickers", []):
            td = price_data.get(ticker, {})
            enriched_tickers.append({
                "symbol": ticker,
                "price": td.get("price"),
                "change_1d": td.get("change_1d"),
                "change_1w": td.get("change_1w"),
                "volume": td.get("volume"),
                "volume_avg": td.get("volume_avg"),
                "cta_zone": cta_zones.get(ticker),
                "active_signals": signal_counts.get(ticker, 0),
            })
        
        enriched_sectors.append({
            "name": sector_name,
            "etf": etf,
            "etf_price": etf_data.get("price"),
            "etf_change_1d": etf_data.get("change_1d"),
            "etf_change_1w": etf_data.get("change_1w"),
            "vs_spy_1d": strength.get("vs_spy_1d"),
            "vs_spy_1w": strength.get("strength"),
            "strength_rank": strength.get("rank", 999),
            "trend": strength.get("trend", "neutral"),
            "bias_alignment": bias_alignment.get(sector_name),
            "tickers": enriched_tickers,
        })
    
    # Sort sectors by strength rank (strongest first)
    enriched_sectors.sort(key=lambda x: x.get("strength_rank", 999))
    
    result = {
        "status": "success",
        "sectors": enriched_sectors,
        "benchmark": {
            "symbol": BENCHMARK_TICKER,
            "price": spy_data.get("price"),
            "change_1d": spy_data.get("change_1d"),
            "change_1w": spy_data.get("change_1w"),
        },
        "total_tickers": len(all_tickers),
        "enriched_at": datetime.now().isoformat(),
        "cache_ttl_seconds": ENRICHMENT_CACHE_TTL,
    }
    
    # Step 8: Cache
    try:
        redis_client.setex(
            ENRICHMENT_CACHE_KEY,
            ENRICHMENT_CACHE_TTL,
            json.dumps(result),
        )
    except Exception as e:
        logger.warning(f"Failed to cache enriched watchlist: {e}")
    
    return result
```

---

## 2. Backend: Updated API Endpoints

### File: `backend/api/watchlist.py` (MODIFY)

Keep ALL existing endpoints working. Add new enriched endpoint. Migrate storage.

### New Endpoint: `GET /watchlist/enriched`

```python
@router.get("/watchlist/enriched")
async def get_enriched_watchlist(sort_by: str = "strength_rank", sort_dir: str = "asc"):
    """
    Get the full enriched watchlist with live prices, sector strength,
    CTA zones, and signal counts.
    
    Query params:
        sort_by: "strength_rank" (default), "change_1d", "change_1w", "name", "signals"
        sort_dir: "asc" (default), "desc"
    
    Response: see EnrichedResponse model below
    """
    from watchlist.enrichment import enrich_watchlist
    from database.redis_client import get_redis
    
    redis = get_redis()
    watchlist_data = load_watchlist_data()
    
    result = await enrich_watchlist(watchlist_data, redis)
    
    # Apply sort
    if sort_by == "change_1d":
        for sector in result["sectors"]:
            sector["tickers"].sort(
                key=lambda t: t.get("change_1d") or 0,
                reverse=(sort_dir == "desc"),
            )
    elif sort_by == "change_1w":
        for sector in result["sectors"]:
            sector["tickers"].sort(
                key=lambda t: t.get("change_1w") or 0,
                reverse=(sort_dir == "desc"),
            )
    elif sort_by == "signals":
        for sector in result["sectors"]:
            sector["tickers"].sort(
                key=lambda t: t.get("active_signals", 0),
                reverse=True,
            )
    # Default: sectors already sorted by strength_rank from enrich_watchlist()
    
    return result
```

### New Endpoint: `GET /watchlist/flat`

```python
@router.get("/watchlist/flat")
async def get_flat_enriched(sort_by: str = "change_1d", sort_dir: str = "desc", limit: int = 50):
    """
    Get ALL watchlist tickers in a single flat list (not grouped by sector).
    Useful for "show me everything sorted by daily losers" view.
    
    Returns: {
        "status": "success",
        "tickers": [ ... all enriched tickers with sector field added ... ],
        "benchmark": { ... SPY data ... },
        "total": 28
    }
    """
    from watchlist.enrichment import enrich_watchlist
    from database.redis_client import get_redis
    
    redis = get_redis()
    watchlist_data = load_watchlist_data()
    result = await enrich_watchlist(watchlist_data, redis)
    
    # Flatten all tickers, adding sector name to each
    flat = []
    for sector in result["sectors"]:
        for ticker in sector["tickers"]:
            ticker["sector"] = sector["name"]
            ticker["sector_etf"] = sector["etf"]
            ticker["sector_vs_spy_1w"] = sector["vs_spy_1w"]
            flat.append(ticker)
    
    # Sort
    sort_key = sort_by if sort_by in ("change_1d", "change_1w", "active_signals", "price") else "change_1d"
    flat.sort(
        key=lambda t: t.get(sort_key) or 0,
        reverse=(sort_dir == "desc"),
    )
    
    return {
        "status": "success",
        "tickers": flat[:limit],
        "benchmark": result["benchmark"],
        "total": len(flat),
    }
```

### Modified: Keep existing endpoints

**DO NOT REMOVE** any of these existing endpoints. They must continue to work:

| Endpoint | Method | Keep as-is? | Notes |
|----------|--------|-------------|-------|
| `/watchlist` | GET | YES | Backwards compat — returns config only |
| `/watchlist` | PUT | YES | Replace entire watchlist |
| `/watchlist/sectors` | GET | YES | Returns config with strength data |
| `/watchlist/add` | POST | YES | Add single ticker |
| `/watchlist/remove` | POST | YES | Remove single ticker |
| `/watchlist/clear` | DELETE | YES | Clear all |
| `/watchlist/reset` | POST | YES | Reset to defaults |
| `/watchlist/sector-strength` | POST | YES | Receives strength updates |
| `/watchlist/enriched` | GET | **NEW** | Full enriched data |
| `/watchlist/flat` | GET | **NEW** | Flat sorted list |

---

## 3. Storage Migration: JSON → PostgreSQL

### Why

`data/watchlist.json` is wiped on every Railway deploy. PostgreSQL is already available in the stack.

### PostgreSQL Table: `watchlist_config`

```sql
CREATE TABLE IF NOT EXISTS watchlist_config (
    id SERIAL PRIMARY KEY,
    sector_name VARCHAR(100) NOT NULL,
    tickers JSONB NOT NULL DEFAULT '[]',    -- ["AAPL", "MSFT", "NVDA"]
    etf VARCHAR(10),                         -- "XLK"
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Unique constraint on sector name
CREATE UNIQUE INDEX IF NOT EXISTS idx_watchlist_sector_name ON watchlist_config(sector_name);

-- Seed with defaults (run once on first deploy)
INSERT INTO watchlist_config (sector_name, tickers, etf, sort_order) VALUES
    ('Technology', '["AAPL","MSFT","NVDA","GOOGL","AMD","META"]', 'XLK', 1),
    ('Consumer Discretionary', '["AMZN","TSLA","NFLX"]', 'XLY', 2),
    ('Financials', '["JPM","BAC","GS"]', 'XLF', 3),
    ('Healthcare', '["UNH","JNJ","PFE"]', 'XLV', 4),
    ('Energy', '["XOM","CVX"]', 'XLE', 5),
    ('Industrials', '["CAT","BA","UPS"]', 'XLI', 6),
    ('Index ETFs', '["SPY","QQQ","IWM"]', NULL, 7)
ON CONFLICT (sector_name) DO NOTHING;
```

### Migration approach

1. On startup, check if `watchlist_config` table exists
2. If not, create it and seed with DEFAULT_WATCHLIST
3. If `data/watchlist.json` exists and table is empty, migrate JSON → Postgres
4. Update `load_watchlist_data()` to read from Postgres
5. Update `save_watchlist_data()` to write to Postgres
6. Keep JSON as fallback ONLY if Postgres is unavailable (graceful degradation)

### Updated `load_watchlist_data()`

```python
async def load_watchlist_data() -> Dict[str, Any]:
    """Load watchlist config from PostgreSQL (primary) or JSON file (fallback)."""
    try:
        from database.postgres_client import get_pool
        pool = get_pool()
        if pool:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT sector_name, tickers, etf FROM watchlist_config ORDER BY sort_order"
                )
                if rows:
                    sectors = {}
                    for row in rows:
                        sectors[row["sector_name"]] = {
                            "tickers": json.loads(row["tickers"]) if isinstance(row["tickers"], str) else row["tickers"],
                            "etf": row["etf"],
                        }
                    return {"sectors": sectors, "sector_strength": {}, "updated_at": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"PostgreSQL unavailable, falling back to JSON: {e}")
    
    # Fallback to existing JSON logic
    return _load_from_json()
```

### Updated `save_watchlist_data()`

```python
async def save_watchlist_data(data: Dict[str, Any]) -> bool:
    """Save watchlist config to PostgreSQL (primary) and JSON file (backup)."""
    try:
        from database.postgres_client import get_pool
        pool = get_pool()
        if pool:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # Upsert each sector
                    for idx, (sector_name, sector_data) in enumerate(data.get("sectors", {}).items()):
                        await conn.execute("""
                            INSERT INTO watchlist_config (sector_name, tickers, etf, sort_order, updated_at)
                            VALUES ($1, $2, $3, $4, NOW())
                            ON CONFLICT (sector_name) DO UPDATE SET
                                tickers = $2, etf = $3, sort_order = $4, updated_at = NOW()
                        """, sector_name, json.dumps(sector_data.get("tickers", [])),
                            sector_data.get("etf"), idx)
                    
                    # Remove sectors that no longer exist
                    current_sectors = list(data.get("sectors", {}).keys())
                    if current_sectors:
                        await conn.execute(
                            "DELETE FROM watchlist_config WHERE sector_name != ALL($1)",
                            current_sectors,
                        )
            
            # Also save JSON as backup
            _save_to_json(data)
            return True
    except Exception as e:
        logger.warning(f"PostgreSQL save failed, using JSON only: {e}")
    
    return _save_to_json(data)
```

---

## 4. Frontend: Watchlist Section Rebuild

### File: `frontend/app.js` (MODIFY watchlist section)

### Data Flow

```
Page load / tab switch to Watchlist
    → fetch GET /api/watchlist/enriched
    → renderEnrichedWatchlist(data)
    → attach sort event listeners
    → start 60-second auto-refresh interval
```

### HTML Structure (add to existing `index.html`)

```html
<!-- Replace existing watchlist section contents -->
<div id="watchlist-section" class="dashboard-section">
    <div class="watchlist-header">
        <h2>Watchlist</h2>
        <div class="watchlist-controls">
            <div class="watchlist-benchmark" id="watchlist-benchmark">
                <!-- SPY: $585.20 +0.3% -->
            </div>
            <select id="watchlist-sort" class="watchlist-sort-select">
                <option value="strength_rank">By Sector Strength</option>
                <option value="change_1d">By Daily Change</option>
                <option value="change_1w">By Weekly Change</option>
                <option value="signals">By Active Signals</option>
            </select>
            <button id="watchlist-view-toggle" class="view-toggle-btn" title="Toggle flat/sector view">
                ☰
            </button>
        </div>
    </div>
    <div id="watchlist-grid" class="watchlist-grid">
        <!-- Populated by JS -->
    </div>
    <div class="watchlist-footer">
        <span id="watchlist-enriched-at" class="text-muted"></span>
        <button id="watchlist-refresh" class="btn-subtle">↻ Refresh</button>
    </div>
</div>
```

### JavaScript Functions

```javascript
// ─── Watchlist State ────────────────────────────────────
let watchlistViewMode = 'sectors';  // 'sectors' or 'flat'
let watchlistSortBy = 'strength_rank';
let watchlistRefreshInterval = null;

// ─── Zone color mapping (matches CTA zones) ────────────
const ZONE_COLORS = {
    'MAX_LONG':        { bg: '#0a2e1a', text: '#00e676' },
    'LEVERAGED_LONG':  { bg: '#0a2e2a', text: '#4caf50' },
    'DE_LEVERAGING':   { bg: '#2e2e0a', text: '#ffeb3b' },
    'WATERFALL':       { bg: '#2e1a0a', text: '#ff9800' },
    'CAPITULATION':    { bg: '#2e0a0a', text: '#f44336' },
    'RECOVERY':        { bg: '#0a1a2e', text: '#42a5f5' },
    'NEUTRAL':         { bg: '#1a2228', text: '#78909c' },
};

// ─── Fetch enriched data ────────────────────────────────
async function fetchEnrichedWatchlist() {
    try {
        const sort = document.getElementById('watchlist-sort')?.value || 'strength_rank';
        const url = watchlistViewMode === 'flat' 
            ? `${API_BASE}/watchlist/flat?sort_by=${sort}&sort_dir=desc`
            : `${API_BASE}/watchlist/enriched?sort_by=${sort}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'success') {
            if (watchlistViewMode === 'flat') {
                renderFlatWatchlist(data);
            } else {
                renderSectorWatchlist(data);
            }
            renderBenchmark(data.benchmark);
            updateEnrichedTimestamp(data.enriched_at);
        }
    } catch (error) {
        console.error('Watchlist fetch failed:', error);
        document.getElementById('watchlist-grid').innerHTML = 
            '<div class="watchlist-error">Failed to load watchlist data</div>';
    }
}

// ─── Render sector-grouped view ─────────────────────────
function renderSectorWatchlist(data) {
    const grid = document.getElementById('watchlist-grid');
    grid.innerHTML = '';
    
    data.sectors.forEach(sector => {
        const card = document.createElement('div');
        card.className = 'sector-card';
        
        // Sector header with ETF performance
        const vsSpyColor = (sector.vs_spy_1w || 0) >= 0 ? '#00e676' : '#f44336';
        const vsSpyBg = (sector.vs_spy_1w || 0) >= 0 ? '#0a2e1a' : '#2e0a0a';
        const biasColor = sector.bias_alignment === 'TORO' ? '#00e676' 
                        : sector.bias_alignment === 'URSA' ? '#f44336' 
                        : '#78909c';
        
        let headerHTML = `
            <div class="sector-header" style="background: ${vsSpyBg}">
                <div class="sector-title-row">
                    <span class="sector-name">${sector.name}</span>
                    ${sector.etf ? `<span class="sector-etf" style="color: ${vsSpyColor}">
                        ${sector.etf} ${formatChange(sector.etf_change_1w)}/1w
                    </span>` : ''}
                    ${sector.vs_spy_1w !== null ? `<span class="sector-vs-spy" style="color: ${vsSpyColor}">
                        vs SPY: ${formatChange(sector.vs_spy_1w)}
                    </span>` : ''}
                </div>
                <div class="sector-meta">
                    <span class="sector-bias" style="color: ${biasColor}">${sector.bias_alignment || '—'}</span>
                    <span class="sector-rank">#${sector.strength_rank}</span>
                </div>
            </div>
        `;
        
        // Column headers
        let tableHTML = `
            <div class="ticker-header-row">
                <span class="col-ticker">Ticker</span>
                <span class="col-price">Price</span>
                <span class="col-1d">1D</span>
                <span class="col-1w">1W</span>
                <span class="col-zone">Zone</span>
                <span class="col-signals">Sigs</span>
            </div>
        `;
        
        // Ticker rows
        sector.tickers.forEach(t => {
            const zoneStyle = ZONE_COLORS[t.cta_zone] || ZONE_COLORS['NEUTRAL'];
            const zoneLabel = t.cta_zone ? t.cta_zone.replace(/_/g, ' ').substring(0, 9) : '—';
            const signalDisplay = t.active_signals > 0 
                ? `<span class="signal-active">⚡${t.active_signals}</span>` 
                : '<span class="signal-none">—</span>';
            
            tableHTML += `
                <div class="ticker-row" data-symbol="${t.symbol}" onclick="openTradingView('${t.symbol}')">
                    <span class="col-ticker ticker-symbol">${t.symbol}</span>
                    <span class="col-price">${t.price !== null ? '$' + t.price.toFixed(2) : '—'}</span>
                    <span class="col-1d" style="color: ${changeColor(t.change_1d)}">${formatChange(t.change_1d)}</span>
                    <span class="col-1w" style="color: ${changeColor(t.change_1w)}">${formatChange(t.change_1w)}</span>
                    <span class="col-zone">
                        <span class="zone-badge" style="background: ${zoneStyle.bg}; color: ${zoneStyle.text}">${zoneLabel}</span>
                    </span>
                    <span class="col-signals">${signalDisplay}</span>
                </div>
            `;
        });
        
        card.innerHTML = headerHTML + tableHTML;
        grid.appendChild(card);
    });
}

// ─── Render flat view ───────────────────────────────────
function renderFlatWatchlist(data) {
    const grid = document.getElementById('watchlist-grid');
    grid.innerHTML = '';
    
    const table = document.createElement('div');
    table.className = 'flat-watchlist';
    
    // Header row
    table.innerHTML = `
        <div class="ticker-header-row flat-header">
            <span class="col-ticker">Ticker</span>
            <span class="col-sector">Sector</span>
            <span class="col-price">Price</span>
            <span class="col-1d">1D</span>
            <span class="col-1w">1W</span>
            <span class="col-zone">Zone</span>
            <span class="col-signals">Sigs</span>
        </div>
    `;
    
    data.tickers.forEach(t => {
        const zoneStyle = ZONE_COLORS[t.cta_zone] || ZONE_COLORS['NEUTRAL'];
        const zoneLabel = t.cta_zone ? t.cta_zone.replace(/_/g, ' ').substring(0, 9) : '—';
        const signalDisplay = t.active_signals > 0 
            ? `<span class="signal-active">⚡${t.active_signals}</span>` 
            : '<span class="signal-none">—</span>';
        
        const row = document.createElement('div');
        row.className = 'ticker-row';
        row.setAttribute('data-symbol', t.symbol);
        row.onclick = () => openTradingView(t.symbol);
        row.innerHTML = `
            <span class="col-ticker ticker-symbol">${t.symbol}</span>
            <span class="col-sector">${t.sector || '—'}</span>
            <span class="col-price">${t.price !== null ? '$' + t.price.toFixed(2) : '—'}</span>
            <span class="col-1d" style="color: ${changeColor(t.change_1d)}">${formatChange(t.change_1d)}</span>
            <span class="col-1w" style="color: ${changeColor(t.change_1w)}">${formatChange(t.change_1w)}</span>
            <span class="col-zone">
                <span class="zone-badge" style="background: ${zoneStyle.bg}; color: ${zoneStyle.text}">${zoneLabel}</span>
            </span>
            <span class="col-signals">${signalDisplay}</span>
        `;
        table.appendChild(row);
    });
    
    grid.appendChild(table);
}

// ─── Helpers ────────────────────────────────────────────
function formatChange(val) {
    if (val === null || val === undefined) return '—';
    const sign = val > 0 ? '+' : '';
    return `${sign}${val.toFixed(1)}%`;
}

function changeColor(val) {
    if (val === null || val === undefined) return '#78909c';
    return val >= 0 ? '#00e676' : '#f44336';
}

function renderBenchmark(benchmark) {
    const el = document.getElementById('watchlist-benchmark');
    if (!el || !benchmark) return;
    el.innerHTML = `
        <span class="benchmark-label">SPY</span>
        <span class="benchmark-price">$${benchmark.price?.toFixed(2) || '—'}</span>
        <span style="color: ${changeColor(benchmark.change_1d)}">${formatChange(benchmark.change_1d)}</span>
    `;
}

function updateEnrichedTimestamp(isoString) {
    const el = document.getElementById('watchlist-enriched-at');
    if (!el || !isoString) return;
    const date = new Date(isoString);
    el.textContent = `Updated: ${date.toLocaleTimeString()}`;
}

function openTradingView(symbol) {
    // If TradingView widget is embedded, load this symbol
    // Otherwise open in new tab
    if (typeof tvWidget !== 'undefined' && tvWidget.setSymbol) {
        tvWidget.setSymbol(symbol, '1D');
    } else {
        window.open(`https://www.tradingview.com/chart/?symbol=${symbol}`, '_blank');
    }
}

// ─── Event Listeners ────────────────────────────────────
document.getElementById('watchlist-sort')?.addEventListener('change', () => {
    fetchEnrichedWatchlist();
});

document.getElementById('watchlist-view-toggle')?.addEventListener('click', () => {
    watchlistViewMode = watchlistViewMode === 'sectors' ? 'flat' : 'sectors';
    const btn = document.getElementById('watchlist-view-toggle');
    btn.textContent = watchlistViewMode === 'sectors' ? '☰' : '⊞';
    btn.title = watchlistViewMode === 'sectors' ? 'Switch to flat view' : 'Switch to sector view';
    fetchEnrichedWatchlist();
});

document.getElementById('watchlist-refresh')?.addEventListener('click', () => {
    fetchEnrichedWatchlist();
});

// Auto-refresh every 60 seconds when watchlist tab is visible
function startWatchlistRefresh() {
    if (watchlistRefreshInterval) clearInterval(watchlistRefreshInterval);
    watchlistRefreshInterval = setInterval(fetchEnrichedWatchlist, 60000);
}

function stopWatchlistRefresh() {
    if (watchlistRefreshInterval) {
        clearInterval(watchlistRefreshInterval);
        watchlistRefreshInterval = null;
    }
}
```

### CSS Additions

```css
/* ─── Watchlist Section ──────────────────────────────── */
.watchlist-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.watchlist-controls {
    display: flex;
    align-items: center;
    gap: 10px;
}

.watchlist-benchmark {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-family: monospace;
    color: #90a4ae;
}

.benchmark-label {
    font-weight: 700;
    color: #c8d6e0;
}

.watchlist-sort-select {
    background: #111e2e;
    color: #c8d6e0;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
}

.view-toggle-btn {
    background: #111e2e;
    color: #78909c;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 4px 8px;
    cursor: pointer;
    font-size: 14px;
}

/* ─── Sector Cards ───────────────────────────────────── */
.watchlist-grid {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.sector-card {
    background: #111e2e;
    border: 1px solid #1e3a5f;
    border-radius: 6px;
    overflow: hidden;
}

.sector-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 14px;
    border-bottom: 1px solid #1e3a5f;
}

.sector-title-row {
    display: flex;
    align-items: center;
    gap: 10px;
}

.sector-name {
    font-size: 14px;
    font-weight: 700;
    color: #e0e8f0;
}

.sector-etf {
    font-size: 11px;
    font-family: monospace;
    padding: 2px 6px;
    border-radius: 3px;
}

.sector-vs-spy {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
}

.sector-meta {
    display: flex;
    align-items: center;
    gap: 8px;
}

.sector-bias {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

.sector-rank {
    font-size: 10px;
    color: #546e7a;
}

/* ─── Ticker Rows ────────────────────────────────────── */
.ticker-header-row {
    display: grid;
    grid-template-columns: 70px 80px 60px 60px 90px 50px;
    padding: 5px 14px;
    font-size: 10px;
    color: #546e7a;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #1a2a3a;
}

.ticker-header-row.flat-header {
    grid-template-columns: 70px 100px 80px 60px 60px 90px 50px;
}

.ticker-row {
    display: grid;
    grid-template-columns: 70px 80px 60px 60px 90px 50px;
    padding: 6px 14px;
    font-size: 12px;
    align-items: center;
    border-bottom: 1px solid #0d1b2a;
    cursor: pointer;
    transition: background 0.15s;
}

.ticker-row:hover {
    background: rgba(79, 195, 247, 0.06);
}

.flat-watchlist .ticker-row {
    grid-template-columns: 70px 100px 80px 60px 60px 90px 50px;
}

.ticker-symbol {
    font-weight: 700;
    color: #e0e8f0;
    font-family: monospace;
}

.col-price, .col-1d, .col-1w {
    text-align: right;
    font-family: monospace;
}

.col-zone {
    text-align: center;
}

.col-signals {
    text-align: center;
    font-family: monospace;
}

.col-sector {
    font-size: 10px;
    color: #78909c;
}

/* ─── Zone Badge ─────────────────────────────────────── */
.zone-badge {
    font-size: 9px;
    font-weight: 800;
    padding: 2px 6px;
    border-radius: 3px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}

/* ─── Signal Indicator ───────────────────────────────── */
.signal-active {
    color: #4fc3f7;
    font-weight: 700;
}

.signal-none {
    color: #37474f;
}

/* ─── Footer ─────────────────────────────────────────── */
.watchlist-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    font-size: 11px;
    color: #546e7a;
}

.btn-subtle {
    background: none;
    border: 1px solid #1e3a5f;
    color: #78909c;
    border-radius: 4px;
    padding: 3px 8px;
    cursor: pointer;
    font-size: 11px;
}

.btn-subtle:hover {
    background: #111e2e;
    color: #4fc3f7;
}

.watchlist-error {
    text-align: center;
    padding: 40px;
    color: #f44336;
    font-size: 13px;
}

/* ─── Mobile Responsive ──────────────────────────────── */
@media (max-width: 600px) {
    .ticker-header-row,
    .ticker-row {
        grid-template-columns: 55px 65px 50px 50px 70px 40px;
        font-size: 10px;
        padding: 5px 8px;
    }
    
    .flat-watchlist .ticker-header-row,
    .flat-watchlist .ticker-row {
        grid-template-columns: 55px 60px 65px 50px 50px 70px 40px;
    }
    
    .sector-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 4px;
    }
    
    .watchlist-controls {
        flex-wrap: wrap;
    }
}
```

---

## 5. Pivot Integration: Automated Sector Strength

### Add to Pivot's schedule (see `docs/specs/pivot-data-collector.md`)

Pivot already pulls sector ETF prices. Add a post-processing step:

```python
# In Pivot's market data pull (every 15 min during market hours)
# AFTER pulling all ticker data, compute and POST sector strength

async def compute_and_post_sector_strength():
    """
    After pulling market data, compute sector vs SPY relative strength
    and POST to the Pandora's Box backend.
    
    This populates the sector_strength field that was previously always empty.
    """
    import yfinance as yf
    
    sector_etfs = {
        "Technology": "XLK",
        "Consumer Discretionary": "XLY",
        "Financials": "XLF",
        "Healthcare": "XLV",
        "Energy": "XLE",
        "Industrials": "XLI",
    }
    
    # Pull 10 days of data for all ETFs + SPY
    symbols = list(sector_etfs.values()) + ["SPY"]
    data = yf.download(symbols, period="10d", interval="1d", auto_adjust=True, threads=True)
    
    spy_close = data["SPY"]["Close"]
    spy_1w_change = ((spy_close.iloc[-1] - spy_close.iloc[0]) / spy_close.iloc[0]) * 100
    spy_1d_change = ((spy_close.iloc[-1] - spy_close.iloc[-2]) / spy_close.iloc[-2]) * 100
    
    sector_strength = {}
    scores = []
    
    for sector_name, etf in sector_etfs.items():
        try:
            etf_close = data[etf]["Close"]
            etf_1w = ((etf_close.iloc[-1] - etf_close.iloc[0]) / etf_close.iloc[0]) * 100
            etf_1d = ((etf_close.iloc[-1] - etf_close.iloc[-2]) / etf_close.iloc[-2]) * 100
            
            vs_spy_1w = round(etf_1w - spy_1w_change, 2)
            vs_spy_1d = round(etf_1d - spy_1d_change, 2)
            
            trend = "strengthening" if vs_spy_1d > 0.3 and vs_spy_1w > 0.5 else \
                    "weakening" if vs_spy_1d < -0.3 and vs_spy_1w < -0.5 else "neutral"
            
            scores.append({"name": sector_name, "vs_spy_1w": vs_spy_1w})
            sector_strength[sector_name] = {
                "strength": vs_spy_1w,
                "vs_spy_1d": vs_spy_1d,
                "trend": trend,
            }
        except Exception as e:
            logger.warning(f"Could not compute strength for {sector_name}: {e}")
    
    # Assign ranks
    scores.sort(key=lambda x: x["vs_spy_1w"], reverse=True)
    for rank, s in enumerate(scores, 1):
        sector_strength[s["name"]]["rank"] = rank
    
    # POST to backend
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TRADING_HUB_URL}/api/watchlist/sector-strength",
                json={"sector_strength": sector_strength},
                headers={"Authorization": f"Bearer {PIVOT_API_KEY}"},
                timeout=10,
            )
            if response.status_code == 200:
                logger.info(f"Sector strength posted: {len(sector_strength)} sectors")
            else:
                logger.error(f"Sector strength POST failed: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to post sector strength: {e}")
```

---

## 6. Redis Key Schema

| Key | Type | TTL | Description |
|-----|------|-----|-------------|
| `watchlist:enriched` | JSON string | 300s (5 min) | Full enriched response cache |
| `watchlist:sector_strength` | JSON string | 900s (15 min) | Sector strength rankings |
| `cta:zone:{SYMBOL}` | String | None | CTA zone per ticker (set by CTA scanner) |
| `signal:active:{SYMBOL}` | Integer string | None | Active signal count per ticker |
| `bias:factor:sector_rotation:latest` | JSON string | None | From composite bias engine |

---

## 7. API Response: `GET /watchlist/enriched`

```json
{
    "status": "success",
    "sectors": [
        {
            "name": "Energy",
            "etf": "XLE",
            "etf_price": 92.45,
            "etf_change_1d": 0.8,
            "etf_change_1w": 2.1,
            "vs_spy_1d": 0.5,
            "vs_spy_1w": 5.2,
            "strength_rank": 1,
            "trend": "strengthening",
            "bias_alignment": "TORO",
            "tickers": [
                {
                    "symbol": "XOM",
                    "price": 112.80,
                    "change_1d": 1.1,
                    "change_1w": 3.2,
                    "volume": 15000000,
                    "volume_avg": 12000000,
                    "cta_zone": "MAX_LONG",
                    "active_signals": 2
                },
                {
                    "symbol": "CVX",
                    "price": 158.45,
                    "change_1d": 0.6,
                    "change_1w": 1.8,
                    "volume": 8000000,
                    "volume_avg": 7500000,
                    "cta_zone": "MAX_LONG",
                    "active_signals": 1
                }
            ]
        },
        {
            "name": "Technology",
            "etf": "XLK",
            "etf_price": 210.30,
            "etf_change_1d": -2.8,
            "etf_change_1w": -7.2,
            "vs_spy_1d": -3.1,
            "vs_spy_1w": -4.1,
            "strength_rank": 6,
            "trend": "weakening",
            "bias_alignment": "URSA",
            "tickers": [
                {
                    "symbol": "NVDA",
                    "price": 118.42,
                    "change_1d": -4.2,
                    "change_1w": -9.1,
                    "volume": 85000000,
                    "volume_avg": 60000000,
                    "cta_zone": "WATERFALL",
                    "active_signals": 0
                }
            ]
        }
    ],
    "benchmark": {
        "symbol": "SPY",
        "price": 585.20,
        "change_1d": 0.3,
        "change_1w": -3.1
    },
    "total_tickers": 28,
    "enriched_at": "2026-02-07T14:30:00",
    "cache_ttl_seconds": 300
}
```

---

## 8. Build Checklist

### Backend (build first)
- [ ] Create `backend/watchlist/__init__.py`
- [ ] Create `backend/watchlist/enrichment.py` with all functions from Section 1
- [ ] Add `GET /watchlist/enriched` endpoint to `backend/api/watchlist.py`
- [ ] Add `GET /watchlist/flat` endpoint to `backend/api/watchlist.py`
- [ ] Create `watchlist_config` PostgreSQL table (Section 3)
- [ ] Update `load_watchlist_data()` to read Postgres → JSON fallback
- [ ] Update `save_watchlist_data()` to write Postgres → JSON backup
- [ ] Add migration logic: on startup, check table exists, seed if needed
- [ ] Register new router if not already (check `backend/main.py`)
- [ ] Test: `GET /api/watchlist/enriched` returns enriched data
- [ ] Test: `GET /api/watchlist/flat?sort_by=change_1d&sort_dir=desc` works
- [ ] Test: Existing endpoints still work (backwards compat)
- [ ] Test: Redis cache populates on first call, serves on second

### Frontend (build second)
- [ ] Add watchlist HTML structure to `index.html`
- [ ] Add CSS from Section 4 to `styles.css`
- [ ] Add JavaScript functions to `app.js`
- [ ] Wire fetchEnrichedWatchlist() to tab activation or page load
- [ ] Test: Sector cards render with ETF performance
- [ ] Test: Ticker rows show price, daily/weekly change, zone badge
- [ ] Test: Sort dropdown changes sort order
- [ ] Test: Flat/sector view toggle works
- [ ] Test: Click ticker opens TradingView
- [ ] Test: Mobile responsive (check 375px width)
- [ ] Test: Auto-refresh fires every 60 seconds

### Pivot (build last, after composite bias engine is deployed)
- [ ] Add `compute_and_post_sector_strength()` to Pivot's 15-min schedule
- [ ] Test: POST to `/api/watchlist/sector-strength` succeeds
- [ ] Test: Sector strength data appears in enriched response
- [ ] Verify sector rotation bias alignment reads from composite engine

---

## 9. Dependencies & Import Notes

**New Python imports needed in `backend/watchlist/enrichment.py`:**
```
yfinance  (already in requirements.txt)
```

**New directory:**
```
backend/watchlist/
    __init__.py
    enrichment.py
```

**Existing code NOT to modify:**
- `backend/api/watchlist.py` existing endpoints — add new endpoints only
- `backend/scanners/cta_scanner.py` — read CTA zones from Redis, don't import the scanner
- `backend/bias_engine/composite.py` — read sector rotation from Redis, don't import directly

**Key architecture principle:** The enrichment engine READS from Redis keys that other systems WRITE to. It does not call CTA scanner or bias engine functions directly. This keeps modules decoupled.

---

## 10. Relationship to Other Specs

| Spec | Relationship |
|------|-------------|
| `composite-bias-engine.md` | Watchlist reads `bias:factor:sector_rotation:latest` from Redis |
| `factor-scoring.md` | Sector rotation factor score determines bias alignment per sector |
| `pivot-data-collector.md` | Pivot computes and POSTs sector strength on its 15-min schedule |
| `bias-frontend.md` | Watchlist section sits alongside bias display in dashboard |
