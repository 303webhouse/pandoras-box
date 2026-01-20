"""
Strategy Management API
Allows enabling/disabling trading strategies through the dashboard

Strategies:
- Hunter (Ursa/Taurus trapped traders scanner)
- Sniper (Kill zone execution)
- Exhaustion (Reversal signals)
- Triple Line Trend Retracement
- BTC Macro Confluence

Each strategy can be toggled on/off independently.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional, List, Any
import json
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Strategy configuration storage
STRATEGIES_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategies.json")

# Default strategy configuration
DEFAULT_STRATEGIES = {
    "hunter": {
        "name": "Hunter Scanner",
        "description": "Scans for trapped traders (Ursa/Taurus) on S&P 500",
        "enabled": True,
        "category": "scanner",
        "timeframes": ["DAILY", "WEEKLY"],
        "settings": {
            "adx_min": 20,
            "rsi_range": [40, 60],
            "rvol_min": 1.25
        }
    },
    "sniper": {
        "name": "Sniper Execution",
        "description": "Kill zone entry signals on TradingView",
        "enabled": True,
        "category": "execution",
        "timeframes": ["5MIN", "15MIN"],
        "settings": {}
    },
    "exhaustion": {
        "name": "Exhaustion Reversal",
        "description": "Momentum exhaustion reversal signals",
        "enabled": True,
        "category": "reversal",
        "timeframes": ["DAILY", "WEEKLY"],
        "settings": {}
    },
    "triple_line": {
        "name": "Triple Line Trend",
        "description": "Trend retracement entry strategy",
        "enabled": True,
        "category": "trend",
        "timeframes": ["DAILY"],
        "settings": {}
    },
    "btc_confluence": {
        "name": "BTC Macro Confluence",
        "description": "BTC 50 SMA + DXY + QQQ 200 SMA filter for crypto",
        "enabled": True,
        "category": "macro",
        "timeframes": ["DAILY", "WEEKLY"],
        "settings": {}
    },
    "savita_filter": {
        "name": "Savita Sentiment Filter",
        "description": "BofA Sell Side Indicator for macro bias",
        "enabled": True,
        "category": "macro",
        "timeframes": ["MONTHLY"],
        "settings": {}
    }
}


class StrategyToggle(BaseModel):
    """Request model for toggling a strategy"""
    enabled: bool


class StrategySettings(BaseModel):
    """Request model for updating strategy settings"""
    settings: Dict[str, Any]


def ensure_data_dir():
    """Ensure the data directory exists"""
    data_dir = os.path.dirname(STRATEGIES_FILE)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)


def load_strategies() -> Dict[str, Any]:
    """Load strategy configuration from file"""
    try:
        ensure_data_dir()
        if os.path.exists(STRATEGIES_FILE):
            with open(STRATEGIES_FILE, 'r') as f:
                saved = json.load(f)
                # Merge with defaults (in case new strategies were added)
                merged = DEFAULT_STRATEGIES.copy()
                for key, value in saved.items():
                    if key in merged:
                        merged[key].update(value)
                    else:
                        merged[key] = value
                return merged
        else:
            save_strategies(DEFAULT_STRATEGIES)
            return DEFAULT_STRATEGIES
    except Exception as e:
        logger.error(f"Error loading strategies: {e}")
        return DEFAULT_STRATEGIES


def save_strategies(strategies: Dict[str, Any]) -> bool:
    """Save strategy configuration to file"""
    try:
        ensure_data_dir()
        with open(STRATEGIES_FILE, 'w') as f:
            json.dump(strategies, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving strategies: {e}")
        return False


@router.get("/strategies")
async def get_all_strategies():
    """Get all strategy configurations"""
    strategies = load_strategies()
    
    # Count enabled/disabled
    enabled_count = sum(1 for s in strategies.values() if s.get("enabled", True))
    disabled_count = len(strategies) - enabled_count
    
    return {
        "status": "success",
        "strategies": strategies,
        "summary": {
            "total": len(strategies),
            "enabled": enabled_count,
            "disabled": disabled_count
        }
    }


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get a specific strategy configuration"""
    strategies = load_strategies()
    
    if strategy_id not in strategies:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
    
    return {
        "status": "success",
        "strategy_id": strategy_id,
        **strategies[strategy_id]
    }


@router.post("/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: str, toggle: StrategyToggle):
    """Enable or disable a specific strategy"""
    strategies = load_strategies()
    
    if strategy_id not in strategies:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
    
    strategies[strategy_id]["enabled"] = toggle.enabled
    
    if save_strategies(strategies):
        status = "enabled" if toggle.enabled else "disabled"
        logger.info(f"Strategy '{strategy_id}' {status}")
        return {
            "status": "success",
            "message": f"Strategy '{strategies[strategy_id]['name']}' {status}",
            "strategy_id": strategy_id,
            "enabled": toggle.enabled
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save strategy configuration")


@router.put("/strategies/{strategy_id}/settings")
async def update_strategy_settings(strategy_id: str, update: StrategySettings):
    """Update settings for a specific strategy"""
    strategies = load_strategies()
    
    if strategy_id not in strategies:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
    
    strategies[strategy_id]["settings"].update(update.settings)
    
    if save_strategies(strategies):
        logger.info(f"Strategy '{strategy_id}' settings updated")
        return {
            "status": "success",
            "message": f"Strategy '{strategies[strategy_id]['name']}' settings updated",
            "strategy_id": strategy_id,
            "settings": strategies[strategy_id]["settings"]
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save strategy configuration")


@router.post("/strategies/enable-all")
async def enable_all_strategies():
    """Enable all strategies"""
    strategies = load_strategies()
    
    for key in strategies:
        strategies[key]["enabled"] = True
    
    if save_strategies(strategies):
        logger.info("All strategies enabled")
        return {
            "status": "success",
            "message": "All strategies enabled",
            "count": len(strategies)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save")


@router.post("/strategies/disable-all")
async def disable_all_strategies():
    """Disable all strategies (emergency kill switch)"""
    strategies = load_strategies()
    
    for key in strategies:
        strategies[key]["enabled"] = False
    
    if save_strategies(strategies):
        logger.info("All strategies DISABLED (kill switch)")
        return {
            "status": "success",
            "message": "All strategies DISABLED",
            "count": len(strategies)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save")


@router.post("/strategies/reset")
async def reset_strategies():
    """Reset all strategies to default configuration"""
    if save_strategies(DEFAULT_STRATEGIES):
        logger.info("Strategies reset to defaults")
        return {
            "status": "success",
            "message": "All strategies reset to defaults",
            "strategies": DEFAULT_STRATEGIES
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save")


def is_strategy_enabled(strategy_id: str) -> bool:
    """
    Check if a strategy is enabled (for use by other modules)
    
    Returns True if strategy is enabled or not found (fail-open)
    """
    strategies = load_strategies()
    return strategies.get(strategy_id, {}).get("enabled", True)


def get_strategy_settings(strategy_id: str) -> Dict[str, Any]:
    """
    Get settings for a strategy (for use by other modules)
    
    Returns empty dict if not found
    """
    strategies = load_strategies()
    return strategies.get(strategy_id, {}).get("settings", {})
