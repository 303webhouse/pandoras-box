"""
Watchlist API
Manages user's personal watchlist for priority scanning

Features:
- Add/remove tickers from watchlist
- Watchlist scanned FIRST before S&P 500
- Persist watchlist to file (simple JSON storage)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Watchlist storage path
WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "watchlist.json")

# Default watchlist if none exists
DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", 
    "META", "TSLA", "AMD", "NFLX", "SPY"
]


class WatchlistUpdate(BaseModel):
    """Request model for updating watchlist"""
    tickers: List[str]


class TickerAction(BaseModel):
    """Request model for adding/removing a single ticker"""
    ticker: str


def ensure_data_dir():
    """Ensure the data directory exists"""
    data_dir = os.path.dirname(WATCHLIST_FILE)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)


def load_watchlist() -> List[str]:
    """Load watchlist from file"""
    try:
        ensure_data_dir()
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
                return data.get("tickers", DEFAULT_WATCHLIST)
        else:
            # Create default watchlist
            save_watchlist(DEFAULT_WATCHLIST)
            return DEFAULT_WATCHLIST
    except Exception as e:
        logger.error(f"Error loading watchlist: {e}")
        return DEFAULT_WATCHLIST


def save_watchlist(tickers: List[str]) -> bool:
    """Save watchlist to file"""
    try:
        ensure_data_dir()
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump({"tickers": tickers}, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving watchlist: {e}")
        return False


@router.get("/watchlist")
async def get_watchlist():
    """Get the current watchlist"""
    tickers = load_watchlist()
    return {
        "status": "success",
        "tickers": tickers,
        "count": len(tickers)
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
    """Add a single ticker to the watchlist"""
    ticker = action.ticker.upper().strip()
    
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty")
    
    tickers = load_watchlist()
    
    if ticker in tickers:
        return {
            "status": "already_exists",
            "message": f"{ticker} is already in your watchlist",
            "tickers": tickers
        }
    
    tickers.insert(0, ticker)  # Add to front of list
    
    if save_watchlist(tickers):
        logger.info(f"Added {ticker} to watchlist")
        return {
            "status": "success",
            "message": f"Added {ticker} to watchlist",
            "tickers": tickers,
            "count": len(tickers)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save watchlist")


@router.post("/watchlist/remove")
async def remove_from_watchlist(action: TickerAction):
    """Remove a single ticker from the watchlist"""
    ticker = action.ticker.upper().strip()
    
    tickers = load_watchlist()
    
    if ticker not in tickers:
        return {
            "status": "not_found",
            "message": f"{ticker} is not in your watchlist",
            "tickers": tickers
        }
    
    tickers.remove(ticker)
    
    if save_watchlist(tickers):
        logger.info(f"Removed {ticker} from watchlist")
        return {
            "status": "success",
            "message": f"Removed {ticker} from watchlist",
            "tickers": tickers,
            "count": len(tickers)
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
    if save_watchlist(DEFAULT_WATCHLIST):
        logger.info("Watchlist reset to defaults")
        return {
            "status": "success",
            "message": "Watchlist reset to defaults",
            "tickers": DEFAULT_WATCHLIST,
            "count": len(DEFAULT_WATCHLIST)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to reset watchlist")
