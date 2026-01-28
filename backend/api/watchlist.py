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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

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


def ensure_data_dir():
    """Ensure the data directory exists"""
    data_dir = os.path.dirname(WATCHLIST_FILE)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)


def load_watchlist_data() -> Dict[str, Any]:
    """Load full watchlist data including sectors"""
    try:
        ensure_data_dir()
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
                # Handle old format (flat list)
                if "tickers" in data and "sectors" not in data:
                    # Migrate to new format
                    return migrate_watchlist(data.get("tickers", []))
                return data
        else:
            save_watchlist_data(DEFAULT_WATCHLIST)
            return DEFAULT_WATCHLIST
    except Exception as e:
        logger.error(f"Error loading watchlist: {e}")
        return DEFAULT_WATCHLIST


def migrate_watchlist(tickers: List[str]) -> Dict[str, Any]:
    """Migrate old flat watchlist to sector-organized format"""
    # Put all existing tickers in Uncategorized
    new_data = DEFAULT_WATCHLIST.copy()
    new_data["sectors"]["Uncategorized"] = {
        "tickers": tickers,
        "etf": None
    }
    save_watchlist_data(new_data)
    logger.info(f"Migrated {len(tickers)} tickers to sector format")
    return new_data


def load_watchlist() -> List[str]:
    """Load flat list of all tickers (for backwards compatibility)"""
    data = load_watchlist_data()
    all_tickers = []
    for sector_data in data.get("sectors", {}).values():
        all_tickers.extend(sector_data.get("tickers", []))
    return list(set(all_tickers))  # Remove duplicates


def save_watchlist_data(data: Dict[str, Any]) -> bool:
    """Save full watchlist data to file"""
    try:
        ensure_data_dir()
        data["updated_at"] = datetime.now().isoformat()
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving watchlist: {e}")
        return False


def save_watchlist(tickers: List[str]) -> bool:
    """Save flat list of tickers (backwards compatibility)"""
    data = load_watchlist_data()
    # Put all tickers in Uncategorized
    data["sectors"]["Uncategorized"] = {
        "tickers": tickers,
        "etf": None
    }
    return save_watchlist_data(data)


@router.get("/watchlist")
async def get_watchlist():
    """Get the current watchlist organized by sector"""
    data = load_watchlist_data()
    all_tickers = load_watchlist()
    
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
    data = load_watchlist_data()
    
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
    
    if save_watchlist(unique_tickers):
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
    
    data = load_watchlist_data()
    all_tickers = load_watchlist()
    
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
    
    if save_watchlist_data(data):
        all_tickers = load_watchlist()
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
    
    data = load_watchlist_data()
    found = False
    
    # Search all sectors for the ticker
    for sector_name, sector_data in data["sectors"].items():
        if ticker in sector_data.get("tickers", []):
            sector_data["tickers"].remove(ticker)
            found = True
            break
    
    if not found:
        all_tickers = load_watchlist()
        return {
            "status": "not_found",
            "message": f"{ticker} is not in your watchlist",
            "tickers": all_tickers
        }
    
    if save_watchlist_data(data):
        all_tickers = load_watchlist()
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
    if save_watchlist([]):
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
    if save_watchlist_data(DEFAULT_WATCHLIST):
        all_tickers = load_watchlist()
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
async def update_sector_strength(update: SectorStrengthUpdate):
    """Update sector strength rankings (called by bias scheduler)"""
    data = load_watchlist_data()
    data["sector_strength"] = update.sector_strength
    
    if save_watchlist_data(data):
        logger.info(f"Sector strength updated: {len(update.sector_strength)} sectors")
        return {
            "status": "success",
            "sector_strength": update.sector_strength
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save sector strength")
