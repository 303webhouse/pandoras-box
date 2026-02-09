"""
Watchlist API
Manages user's personal watchlist for priority scanning

Features:
- Organize tickers by sector
- Track sector strength for Trade Ideas prioritization
- Add/remove tickers from watchlist
- Watchlist scanned FIRST before S&P 500
- Persist watchlist to file (simple JSON storage)
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter()

try:
    from utils.pivot_auth import verify_pivot_key
except ModuleNotFoundError:
    from backend.utils.pivot_auth import verify_pivot_key

# Watchlist storage path
WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "watchlist.json")

# Default sector-organized watchlist
DEFAULT_WATCHLIST = {
    "sectors": {
        "Technology": {
            "tickers": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMD", "META"],
            "etf": "XLK"
        },
        "Consumer Discretionary": {
            "tickers": ["AMZN", "TSLA", "NFLX"],
            "etf": "XLY"
        },
        "Financials": {
            "tickers": ["JPM", "BAC", "GS"],
            "etf": "XLF"
        },
        "Healthcare": {
            "tickers": ["UNH", "JNJ", "PFE"],
            "etf": "XLV"
        },
        "Energy": {
            "tickers": ["XOM", "CVX"],
            "etf": "XLE"
        },
        "Industrials": {
            "tickers": ["CAT", "BA", "UPS"],
            "etf": "XLI"
        },
        "Index ETFs": {
            "tickers": ["SPY", "QQQ", "IWM"],
            "etf": None
        }
    },
    "sector_strength": {},
    "updated_at": None
}


class WatchlistUpdate(BaseModel):
    """Request model for updating watchlist"""
    tickers: List[str]


class TickerAction(BaseModel):
    """Request model for adding/removing a single ticker"""
    ticker: str
    sector: Optional[str] = "Uncategorized"


class SectorStrengthUpdate(BaseModel):
    """Request model for updating sector strength"""
    sector_strength: Dict[str, Any]


class WatchlistTickerAdd(BaseModel):
    """Add a ticker via the single ticker analyzer"""
    symbol: str
    sector: Optional[str] = None
    notes: Optional[str] = None


class WatchlistTickerMute(BaseModel):
    """Mute/unmute a single ticker"""
    muted: bool


class BulkMuteRequest(BaseModel):
    """Bulk mute/unmute tickers by symbol list or sector"""
    symbols: Optional[List[str]] = None
    sector: Optional[str] = None
    muted: bool


def ensure_data_dir():
    """Ensure the data directory exists"""
    data_dir = os.path.dirname(WATCHLIST_FILE)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)


def _copy_default_watchlist() -> Dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_WATCHLIST))


def _load_from_json() -> Dict[str, Any]:
    """Load watchlist from JSON file (fallback)."""
    try:
        ensure_data_dir()
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
                if "tickers" in data and "sectors" not in data:
                    return migrate_watchlist(data.get("tickers", []))
                return data
    except Exception as e:
        logger.error(f"Error loading watchlist JSON: {e}")
    return _copy_default_watchlist()


def _save_to_json(data: Dict[str, Any]) -> bool:
    """Save watchlist data to JSON file (backup)."""
    try:
        ensure_data_dir()
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving watchlist JSON: {e}")
        return False


def migrate_watchlist(tickers: List[str]) -> Dict[str, Any]:
    """Migrate old flat watchlist to sector-organized format"""
    new_data = _copy_default_watchlist()
    new_data["sectors"]["Uncategorized"] = {
        "tickers": tickers,
        "etf": None
    }
    _save_to_json(new_data)
    logger.info(f"Migrated {len(tickers)} tickers to sector format")
    return new_data


async def init_watchlist_table() -> None:
    """Create watchlist_config table and seed from JSON/defaults if empty."""
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_config (
                    id SERIAL PRIMARY KEY,
                    sector_name VARCHAR(100) NOT NULL,
                    tickers JSONB NOT NULL DEFAULT '[]',
                    etf VARCHAR(10),
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_watchlist_sector_name
                ON watchlist_config(sector_name)
            """)

            count = await conn.fetchval("SELECT COUNT(*) FROM watchlist_config")
            if count == 0:
                seed_data = _load_from_json()
                sectors = seed_data.get("sectors", {})
                for idx, (sector_name, sector_data) in enumerate(sectors.items()):
                    await conn.execute("""
                        INSERT INTO watchlist_config (sector_name, tickers, etf, sort_order)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (sector_name) DO NOTHING
                    """,
                        sector_name,
                        json.dumps(sector_data.get("tickers", [])),
                        sector_data.get("etf"),
                        idx,
                    )
                logger.info(f"Seeded {len(sectors)} sectors into watchlist_config")
        await migrate_watchlist_tickers()
    except Exception as e:
        logger.warning(f"Could not init watchlist table (using JSON fallback): {e}")


async def migrate_watchlist_tickers() -> None:
    """Seed watchlist_tickers from watchlist_config and scanner universe if empty."""
    try:
        from database.postgres_client import get_postgres_client
        from config.sectors import detect_sector
        from scanners.universe import SP500_EXPANDED, RUSSELL_HIGH_VOLUME

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM watchlist_tickers")
            if count and count > 0:
                return

            manual_symbols: set[str] = set()
            manual_attempts = 0

            rows = await conn.fetch(
                "SELECT sector_name, tickers FROM watchlist_config ORDER BY sort_order"
            )
            for row in rows:
                tickers = row["tickers"]
                if isinstance(tickers, str):
                    tickers = json.loads(tickers)
                for symbol in tickers or []:
                    symbol = str(symbol).upper().strip()
                    if not symbol:
                        continue
                    manual_symbols.add(symbol)
                    manual_attempts += 1
                    await conn.execute(
                        """
                        INSERT INTO watchlist_tickers (symbol, sector, source, priority)
                        VALUES ($1, $2, 'manual', 'normal')
                        ON CONFLICT (symbol) DO NOTHING
                        """,
                        symbol,
                        row["sector_name"],
                    )

            scanner_symbols: List[str] = []
            seen = set()
            for symbol in SP500_EXPANDED + RUSSELL_HIGH_VOLUME:
                symbol = str(symbol).upper().strip()
                if not symbol or symbol in seen or symbol in manual_symbols:
                    continue
                seen.add(symbol)
                scanner_symbols.append(symbol)

            scanner_attempts = 0
            for symbol in scanner_symbols:
                scanner_attempts += 1
                await conn.execute(
                    """
                    INSERT INTO watchlist_tickers (symbol, sector, source, priority)
                    VALUES ($1, $2, 'scanner', 'low')
                    ON CONFLICT (symbol) DO NOTHING
                    """,
                    symbol,
                    detect_sector(symbol),
                )

            logger.info(
                "Seeded watchlist_tickers: %s manual, %s scanner",
                manual_attempts,
                scanner_attempts,
            )
    except Exception as e:
        logger.warning(f"Could not migrate watchlist_tickers: {e}")


async def _load_from_postgres() -> Optional[Dict[str, Any]]:
    """Load watchlist config from PostgreSQL."""
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            sector_rows = await conn.fetch(
                "SELECT sector_name, etf, sort_order FROM watchlist_config ORDER BY sort_order"
            )
            ticker_rows = await conn.fetch(
                """
                SELECT symbol, sector, source, muted, priority, added_at
                FROM watchlist_tickers
                WHERE source IN ('manual', 'position') AND muted = false
                ORDER BY priority DESC, added_at
                """
            )

            if not sector_rows and not ticker_rows:
                return None

            sectors: Dict[str, Dict[str, Any]] = {}
            ordered_sector_names: List[str] = []
            for row in sector_rows:
                sector_name = row["sector_name"]
                ordered_sector_names.append(sector_name)
                sectors[sector_name] = {
                    "tickers": [],
                    "etf": row["etf"],
                }

            for row in ticker_rows:
                symbol = row["symbol"]
                sector_name = row["sector"] or "Uncategorized"
                if sector_name not in sectors:
                    sectors[sector_name] = {"tickers": [], "etf": None}
                    ordered_sector_names.append(sector_name)
                sectors[sector_name]["tickers"].append(symbol)

            sector_strength = {}
            try:
                sector_strength = _load_from_json().get("sector_strength", {})
            except Exception:
                sector_strength = {}

            return {
                "sectors": {name: sectors[name] for name in ordered_sector_names},
                "sector_strength": sector_strength,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        logger.warning(f"PostgreSQL unavailable, using JSON fallback: {e}")
        return None


async def _sync_watchlist_tickers_from_sectors(sectors: Dict[str, Any]) -> None:
    """Sync manual watchlist tickers from sector payloads."""
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            manual_symbols: Dict[str, str] = {}
            for sector_name, sector_data in sectors.items():
                for symbol in sector_data.get("tickers", []) or []:
                    symbol = str(symbol).upper().strip()
                    if not symbol:
                        continue
                    manual_symbols[symbol] = sector_name

            symbols = list(manual_symbols.keys())

            if not symbols:
                await conn.execute(
                    "DELETE FROM watchlist_tickers WHERE source = 'manual' AND priority != 'high'"
                )
                return

            for symbol, sector in manual_symbols.items():
                await conn.execute(
                    """
                    INSERT INTO watchlist_tickers (symbol, sector, source, priority, muted)
                    VALUES ($1, $2, 'manual', 'normal', false)
                    ON CONFLICT (symbol) DO UPDATE SET
                        sector = EXCLUDED.sector,
                        source = 'manual',
                        muted = false,
                        priority = CASE
                            WHEN watchlist_tickers.priority = 'high' THEN 'high'
                            ELSE 'normal'
                        END
                    """,
                    symbol,
                    sector,
                )

            await conn.execute(
                """
                DELETE FROM watchlist_tickers
                WHERE source = 'manual'
                  AND priority != 'high'
                  AND symbol <> ALL($1::text[])
                """,
                symbols,
            )
    except Exception as e:
        logger.warning(f"Failed to sync watchlist_tickers: {e}")


async def load_watchlist_data_async() -> Dict[str, Any]:
    """Load watchlist config from PostgreSQL (primary) or JSON file (fallback)."""
    data = await _load_from_postgres()
    if data:
        return data
    return _load_from_json()


def load_watchlist_data() -> Dict[str, Any]:
    """Sync fallback for watchlist config (JSON only)."""
    return _load_from_json()


async def save_watchlist_data_async(data: Dict[str, Any]) -> bool:
    """Save watchlist config to PostgreSQL (primary) and JSON file (backup)."""
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    saved_pg = False

    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            async with conn.transaction():
                sectors = data.get("sectors", {})
                for idx, (sector_name, sector_data) in enumerate(sectors.items()):
                    await conn.execute("""
                        INSERT INTO watchlist_config (sector_name, tickers, etf, sort_order, updated_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        ON CONFLICT (sector_name) DO UPDATE SET
                            tickers = $2, etf = $3, sort_order = $4, updated_at = NOW()
                    """,
                        sector_name,
                        json.dumps(sector_data.get("tickers", [])),
                        sector_data.get("etf"),
                        idx,
                    )

                current_sectors = list(sectors.keys())
                if current_sectors:
                    await conn.execute(
                        "DELETE FROM watchlist_config WHERE sector_name != ALL($1::text[])",
                        current_sectors,
                    )
                else:
                    await conn.execute("DELETE FROM watchlist_config")
        saved_pg = True
        await _sync_watchlist_tickers_from_sectors(sectors)
    except Exception as e:
        logger.warning(f"PostgreSQL save failed, using JSON only: {e}")

    saved_json = _save_to_json(data)
    await _invalidate_watchlist_cache()

    return saved_pg or saved_json


def save_watchlist_data(data: Dict[str, Any]) -> bool:
    """Sync JSON backup for watchlist config."""
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    return _save_to_json(data)


def _flatten_tickers(sectors: Dict[str, Any]) -> List[str]:
    all_tickers: List[str] = []
    for sector_data in sectors.values():
        all_tickers.extend(sector_data.get("tickers", []))
    return list(set(all_tickers))


async def load_watchlist() -> List[str]:
    """Load flat list of all tickers (async)."""
    data = await load_watchlist_data_async()
    return _flatten_tickers(data.get("sectors", {}))


async def save_watchlist(tickers: List[str]) -> bool:
    """Save flat list of tickers (backwards compatibility)."""
    data = await load_watchlist_data_async()
    data["sectors"]["Uncategorized"] = {
        "tickers": tickers,
        "etf": None
    }
    return await save_watchlist_data_async(data)


async def _invalidate_watchlist_cache() -> None:
    try:
        from database.redis_client import get_redis_client
        from watchlist.enrichment import ENRICHMENT_CACHE_KEY

        client = await get_redis_client()
        if client:
            await client.delete(ENRICHMENT_CACHE_KEY)
    except Exception:
        pass


@router.get("/watchlist")
async def get_watchlist():
    """Get the current watchlist organized by sector"""
    data = await load_watchlist_data_async()
    all_tickers = _flatten_tickers(data.get("sectors", {}))
    
    return {
        "status": "success",
        "sectors": data.get("sectors", {}),
        "sector_strength": data.get("sector_strength", {}),
        "tickers": all_tickers,  # Flat list for backwards compatibility
        "count": len(all_tickers),
        "updated_at": data.get("updated_at")
    }


@router.get("/watchlist/sectors")
async def get_watchlist_sectors():
    """Get watchlist organized by sector with strength data"""
    data = await load_watchlist_data_async()
    
    # Sort sectors by strength if available
    sectors = data.get("sectors", {})
    sector_strength = data.get("sector_strength", {})
    
    # Build response with strength ranking
    sectors_with_strength = []
    for sector_name, sector_data in sectors.items():
        strength_data = sector_strength.get(sector_name, {})
        sectors_with_strength.append({
            "name": sector_name,
            "tickers": sector_data.get("tickers", []),
            "etf": sector_data.get("etf"),
            "strength": strength_data.get("strength", 0),
            "trend": strength_data.get("trend", "neutral"),
            "rank": strength_data.get("rank", 999)
        })
    
    # Sort by strength rank
    sectors_with_strength.sort(key=lambda x: x.get("rank", 999))
    
    return {
        "status": "success",
        "sectors": sectors_with_strength,
        "total_tickers": sum(len(s["tickers"]) for s in sectors_with_strength)
    }


@router.put("/watchlist")
async def update_watchlist(update: WatchlistUpdate):
    """Replace the entire watchlist"""
    # Normalize tickers to uppercase
    tickers = [t.upper().strip() for t in update.tickers if t.strip()]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique_tickers.append(t)
    
    if await save_watchlist(unique_tickers):
        logger.info(f"Watchlist updated: {len(unique_tickers)} tickers")
        return {
            "status": "success",
            "tickers": unique_tickers,
            "count": len(unique_tickers)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save watchlist")


@router.post("/watchlist/add")
async def add_to_watchlist(action: TickerAction):
    """Add a single ticker to the watchlist (in specified sector)"""
    ticker = action.ticker.upper().strip()
    sector = action.sector or "Uncategorized"
    
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty")
    
    data = await load_watchlist_data_async()
    all_tickers = _flatten_tickers(data.get("sectors", {}))
    
    if ticker in all_tickers:
        return {
            "status": "already_exists",
            "message": f"{ticker} is already in your watchlist",
            "tickers": all_tickers
        }
    
    # Add to specified sector
    if sector not in data["sectors"]:
        data["sectors"][sector] = {"tickers": [], "etf": None}
    
    data["sectors"][sector]["tickers"].insert(0, ticker)
    
    if await save_watchlist_data_async(data):
        all_tickers = _flatten_tickers(data.get("sectors", {}))
        logger.info(f"Added {ticker} to watchlist ({sector})")
        return {
            "status": "success",
            "message": f"Added {ticker} to watchlist ({sector})",
            "tickers": all_tickers,
            "count": len(all_tickers)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save watchlist")


@router.post("/watchlist/remove")
async def remove_from_watchlist(action: TickerAction):
    """Remove a single ticker from the watchlist"""
    ticker = action.ticker.upper().strip()
    
    data = await load_watchlist_data_async()
    found = False
    
    # Search all sectors for the ticker
    for sector_name, sector_data in data["sectors"].items():
        if ticker in sector_data.get("tickers", []):
            sector_data["tickers"].remove(ticker)
            found = True
            break
    
    if not found:
        all_tickers = _flatten_tickers(data.get("sectors", {}))
        return {
            "status": "not_found",
            "message": f"{ticker} is not in your watchlist",
            "tickers": all_tickers
        }
    
    if await save_watchlist_data_async(data):
        all_tickers = _flatten_tickers(data.get("sectors", {}))
        logger.info(f"Removed {ticker} from watchlist")
        return {
            "status": "success",
            "message": f"Removed {ticker} from watchlist",
            "tickers": all_tickers,
            "count": len(all_tickers)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save watchlist")


@router.delete("/watchlist/clear")
async def clear_watchlist():
    """Clear the entire watchlist"""
    if await save_watchlist([]):
        logger.info("Watchlist cleared")
        return {
            "status": "success",
            "message": "Watchlist cleared",
            "tickers": [],
            "count": 0
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to clear watchlist")


@router.post("/watchlist/reset")
async def reset_watchlist():
    """Reset watchlist to defaults"""
    if await save_watchlist_data_async(_copy_default_watchlist()):
        all_tickers = _flatten_tickers(DEFAULT_WATCHLIST.get("sectors", {}))
        logger.info("Watchlist reset to defaults")
        return {
            "status": "success",
            "message": "Watchlist reset to defaults",
            "sectors": DEFAULT_WATCHLIST["sectors"],
            "tickers": all_tickers,
            "count": len(all_tickers)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to reset watchlist")


@router.post("/watchlist/sector-strength")
async def update_sector_strength(update: SectorStrengthUpdate, _: str = Depends(verify_pivot_key)):
    """Update sector strength rankings (called by bias scheduler)"""
    data = await load_watchlist_data_async()
    data["sector_strength"] = update.sector_strength
    
    if await save_watchlist_data_async(data):
        try:
            from database.redis_client import get_redis_client
            from watchlist.enrichment import SECTOR_STRENGTH_CACHE_KEY, SECTOR_STRENGTH_CACHE_TTL

            client = await get_redis_client()
            if client:
                await client.setex(
                    SECTOR_STRENGTH_CACHE_KEY,
                    SECTOR_STRENGTH_CACHE_TTL,
                    json.dumps(update.sector_strength),
                )
        except Exception as e:
            logger.warning(f"Failed to cache sector strength: {e}")

        logger.info(f"Sector strength updated: {len(update.sector_strength)} sectors")
        return {
            "status": "success",
            "sector_strength": update.sector_strength
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save sector strength")


# ====================
# WATCHLIST V3 (TICKERS)
# ====================

@router.get("/watchlist/tickers")
async def get_watchlist_tickers(
    source: str = Query("all", description="manual|position|scanner|all"),
    muted: Optional[bool] = Query(None, description="Filter by muted state"),
    sector: Optional[str] = Query(None, description="Filter by sector name"),
    sort_by: str = Query("sector", description="Sort field"),
    sort_dir: str = Query("asc", description="Sort direction"),
    include_enrichment: bool = Query(True, description="Include price/zone enrichment"),
):
    """
    Return watchlist tickers from watchlist_tickers with optional enrichment.
    """
    try:
        from database.postgres_client import get_postgres_client
        from watchlist.enrichment import fetch_price_data_async, get_cta_zones, get_active_signals
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Missing dependencies: {e}")

    redis_client = None
    try:
        from database.redis_client import get_redis_client
        redis_client = await get_redis_client()
    except Exception:
        redis_client = None

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Counts (unfiltered)
        count_rows = await conn.fetch(
            "SELECT source, muted, COUNT(*) AS count FROM watchlist_tickers GROUP BY source, muted"
        )

        counts = {"total": 0, "manual": 0, "position": 0, "scanner": 0, "muted": 0}
        for row in count_rows:
            row_count = int(row["count"])
            counts["total"] += row_count
            src = row["source"]
            if src in counts:
                counts[src] += row_count
            if row["muted"]:
                counts["muted"] += row_count

        clauses: List[str] = []
        params: List[Any] = []
        param_idx = 1

        if source and source != "all":
            clauses.append(f"source = ${param_idx}")
            params.append(source)
            param_idx += 1

        if muted is not None:
            clauses.append(f"muted = ${param_idx}")
            params.append(muted)
            param_idx += 1

        if sector:
            clauses.append(f"sector = ${param_idx}")
            params.append(sector)
            param_idx += 1

        query = """
            SELECT symbol, sector, source, muted, priority, position_id, notes, added_at, muted_at
            FROM watchlist_tickers
        """
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY added_at"

        rows = await conn.fetch(query, *params)

    tickers = []
    symbols = []
    for row in rows:
        symbol = row["symbol"]
        symbols.append(symbol)
        tickers.append({
            "symbol": symbol,
            "sector": row["sector"],
            "source": row["source"],
            "muted": row["muted"],
            "priority": row["priority"],
            "position_id": row["position_id"],
            "notes": row["notes"],
            "added_at": row["added_at"].isoformat() if row["added_at"] else None,
            "muted_at": row["muted_at"].isoformat() if row["muted_at"] else None,
            "price": None,
            "change_1d": None,
            "change_1w": None,
            "volume": None,
            "volume_avg": None,
            "relative_volume": None,
            "cta_zone": None,
            "active_signals": 0,
        })

    price_data: Dict[str, dict] = {}
    if include_enrichment:
        enrich_symbols = [t["symbol"] for t in tickers if t["source"] in ("manual", "position")]
        price_data = await fetch_price_data_async(enrich_symbols)

    cta_zones = await get_cta_zones(symbols, redis_client)
    signal_counts = await get_active_signals(symbols, redis_client)

    for ticker in tickers:
        symbol = ticker["symbol"]
        pd_data = price_data.get(symbol, {})
        ticker["price"] = pd_data.get("price")
        ticker["change_1d"] = pd_data.get("change_1d")
        ticker["change_1w"] = pd_data.get("change_1w")
        ticker["volume"] = pd_data.get("volume")
        ticker["volume_avg"] = pd_data.get("volume_avg")
        if pd_data.get("volume") and pd_data.get("volume_avg"):
            ticker["relative_volume"] = round(pd_data["volume"] / pd_data["volume_avg"], 2)
        ticker["cta_zone"] = cta_zones.get(symbol)
        ticker["active_signals"] = signal_counts.get(symbol, 0)

    sort_by = (sort_by or "sector").lower()
    reverse = (sort_dir or "asc").lower() == "desc"

    def sort_key(item: Dict[str, Any]):
        if sort_by == "change_1d":
            return item.get("change_1d") or 0
        if sort_by == "change_1w":
            return item.get("change_1w") or 0
        if sort_by == "relative_volume":
            return item.get("relative_volume") or 0
        if sort_by == "cta_zone":
            return item.get("cta_zone") or ""
        return (item.get("sector") or "", item.get("symbol") or "")

    tickers.sort(key=sort_key, reverse=reverse)

    return {
        "status": "success",
        "tickers": tickers,
        "counts": counts,
    }


@router.patch("/watchlist/tickers/{symbol}/mute")
async def mute_watchlist_ticker(symbol: str, request: WatchlistTickerMute):
    symbol = symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty")

    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT symbol, muted FROM watchlist_tickers WHERE symbol = $1",
            symbol,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Ticker not found")

        if request.muted:
            await conn.execute(
                "UPDATE watchlist_tickers SET muted = true, muted_at = NOW() WHERE symbol = $1",
                symbol,
            )
        else:
            await conn.execute(
                "UPDATE watchlist_tickers SET muted = false, muted_at = NULL WHERE symbol = $1",
                symbol,
            )

    await _invalidate_watchlist_cache()
    return {"status": "success", "symbol": symbol, "muted": request.muted}


@router.patch("/watchlist/tickers/bulk-mute")
async def bulk_mute_watchlist_tickers(request: BulkMuteRequest):
    if request.symbols and request.sector:
        raise HTTPException(status_code=400, detail="Provide symbols OR sector, not both")
    if not request.symbols and not request.sector:
        raise HTTPException(status_code=400, detail="Provide symbols or sector")

    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if request.symbols:
            symbols = [s.upper().strip() for s in request.symbols if s and s.strip()]
            if not symbols:
                raise HTTPException(status_code=400, detail="Symbols cannot be empty")
            if request.muted:
                await conn.execute(
                    "UPDATE watchlist_tickers SET muted = true, muted_at = NOW() WHERE symbol = ANY($1::text[])",
                    symbols,
                )
            else:
                await conn.execute(
                    "UPDATE watchlist_tickers SET muted = false, muted_at = NULL WHERE symbol = ANY($1::text[])",
                    symbols,
                )
        else:
            sector = request.sector
            if request.muted:
                await conn.execute(
                    "UPDATE watchlist_tickers SET muted = true, muted_at = NOW() WHERE sector = $1",
                    sector,
                )
            else:
                await conn.execute(
                    "UPDATE watchlist_tickers SET muted = false, muted_at = NULL WHERE sector = $1",
                    sector,
                )

    await _invalidate_watchlist_cache()
    return {"status": "success", "muted": request.muted}


@router.delete("/watchlist/tickers/{symbol}")
async def delete_watchlist_ticker(symbol: str):
    symbol = symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty")

    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT symbol, source FROM watchlist_tickers WHERE symbol = $1",
            symbol,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Ticker not found")

        source = row["source"]
        if source == "scanner":
            raise HTTPException(status_code=400, detail="Scanner tickers cannot be deleted. Mute instead.")

        if source == "position":
            open_count = await conn.fetchval(
                "SELECT COUNT(*) FROM positions WHERE ticker = $1 AND status = 'OPEN'",
                symbol,
            )
            if open_count and open_count > 0:
                raise HTTPException(status_code=400, detail="Ticker has open positions. Close position first.")

        await conn.execute("DELETE FROM watchlist_tickers WHERE symbol = $1", symbol)

    await _invalidate_watchlist_cache()
    return {"status": "success", "symbol": symbol}


@router.post("/watchlist/tickers/add")
async def add_watchlist_ticker(request: WatchlistTickerAdd):
    symbol = request.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty")

    from database.postgres_client import get_postgres_client
    from config.sectors import detect_sector

    sector = (request.sector or detect_sector(symbol)).strip()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Ensure sector exists in watchlist_config
        existing_sector = await conn.fetchval(
            "SELECT 1 FROM watchlist_config WHERE sector_name = $1",
            sector,
        )
        if not existing_sector:
            max_sort = await conn.fetchval(
                "SELECT COALESCE(MAX(sort_order), 0) FROM watchlist_config"
            )
            await conn.execute(
                """
                INSERT INTO watchlist_config (sector_name, tickers, etf, sort_order)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (sector_name) DO NOTHING
                """,
                sector,
                json.dumps([]),
                None,
                int(max_sort or 0) + 1,
            )

        existing = await conn.fetchrow(
            "SELECT source, priority FROM watchlist_tickers WHERE symbol = $1",
            symbol,
        )

        if existing:
            if existing["source"] == "manual":
                return {"status": "already_exists", "symbol": symbol}

            await conn.execute(
                """
                UPDATE watchlist_tickers
                SET source = 'manual',
                    sector = $2,
                    muted = false,
                    notes = COALESCE($3, notes),
                    priority = CASE
                        WHEN priority = 'high' THEN 'high'
                        ELSE 'normal'
                    END
                WHERE symbol = $1
                """,
                symbol,
                sector,
                request.notes,
            )
        else:
            await conn.execute(
                """
                INSERT INTO watchlist_tickers (symbol, sector, source, priority, notes)
                VALUES ($1, $2, 'manual', 'normal', $3)
                """,
                symbol,
                sector,
                request.notes,
            )

    await _invalidate_watchlist_cache()
    return {"status": "success", "symbol": symbol, "sector": sector}

# ====================
# WATCHLIST V2 (ENRICHED)
# ====================

@router.get("/watchlist/enriched")
async def get_enriched_watchlist(
    sort_by: str = Query("strength_rank", description="Sort field"),
    sort_dir: str = Query("asc", description="Sort direction"),
):
    """
    Get enriched watchlist with prices, sector strength, CTA zones, and bias alignment.
    """
    try:
        from watchlist.enrichment import enrich_watchlist
    except ImportError:
        raise HTTPException(status_code=503, detail="Enrichment engine not available")

    redis_client = None
    try:
        from database.redis_client import get_redis_client
        redis_client = await get_redis_client()
    except Exception:
        redis_client = None

    watchlist_data = await load_watchlist_data_async()
    result = await enrich_watchlist(watchlist_data, redis_client)

    reverse = (sort_dir.lower() == "desc")
    sort_by = (sort_by or "strength_rank").lower()

    if sort_by == "change_1d":
        for sector in result.get("sectors", []):
            sector["tickers"].sort(
                key=lambda t: t.get("change_1d") or 0,
                reverse=reverse,
            )
    elif sort_by == "change_1w":
        for sector in result.get("sectors", []):
            sector["tickers"].sort(
                key=lambda t: t.get("change_1w") or 0,
                reverse=reverse,
            )
    elif sort_by == "signals":
        for sector in result.get("sectors", []):
            sector["tickers"].sort(
                key=lambda t: t.get("active_signals", 0),
                reverse=True,
            )
    elif sort_by == "name":
        for sector in result.get("sectors", []):
            sector["tickers"].sort(key=lambda t: t.get("symbol", ""))

    return result


@router.get("/watchlist/flat")
async def get_flat_enriched(
    sort_by: str = Query("change_1d", description="Sort field"),
    sort_dir: str = Query("desc", description="Sort direction"),
    limit: int = Query(50, description="Max tickers to return"),
):
    """Get all watchlist tickers in a flat list with sector context."""
    try:
        from watchlist.enrichment import enrich_watchlist
    except ImportError:
        raise HTTPException(status_code=503, detail="Enrichment engine not available")

    redis_client = None
    try:
        from database.redis_client import get_redis_client
        redis_client = await get_redis_client()
    except Exception:
        redis_client = None

    watchlist_data = await load_watchlist_data_async()
    result = await enrich_watchlist(watchlist_data, redis_client)

    flat = []
    for sector in result.get("sectors", []):
        for ticker in sector.get("tickers", []):
            enriched = dict(ticker)
            enriched["sector"] = sector.get("name")
            enriched["sector_etf"] = sector.get("etf")
            enriched["sector_vs_spy_1w"] = sector.get("vs_spy_1w")
            enriched["sector_strength_rank"] = sector.get("strength_rank")
            enriched["sector_bias_alignment"] = sector.get("bias_alignment")
            flat.append(enriched)

    sort_key = (sort_by or "change_1d").lower()
    if sort_key == "signals":
        sort_key = "active_signals"

    valid_sorts = {"change_1d", "change_1w", "active_signals", "price", "symbol"}
    if sort_key not in valid_sorts:
        sort_key = "change_1d"

    reverse = (sort_dir.lower() == "desc")
    if sort_key == "symbol":
        flat.sort(key=lambda t: t.get("symbol", ""), reverse=reverse)
    else:
        flat.sort(key=lambda t: t.get(sort_key) or 0, reverse=reverse)

    return {
        "status": "success",
        "tickers": flat[:limit],
        "benchmark": result.get("benchmark"),
        "total": len(flat),
        "enriched_at": result.get("enriched_at"),
    }
