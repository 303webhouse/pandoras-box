"""
BTC Integration Module
Bridges the existing BTC bottom signals from the main trading hub
with the crypto scalper signal engine

This allows the crypto scalper to benefit from the sophisticated
derivative signals already built:
- 25-Delta Skew
- Quarterly Basis
- Perp Funding
- Stablecoin APRs
- Term Structure
- Open Interest Divergence
- Liquidation Composition
- Spot Orderbook Skew
- VIX Spike (macro)
"""

import sys
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Add parent trading-hub to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

logger = logging.getLogger(__name__)

# Try to import from main trading hub
try:
    from backend.bias_filters.btc_bottom_signals import (
        get_all_signals,
        get_signal,
        update_signal_manual,
        get_btc_sessions,
        get_current_session,
        SignalStatus
    )
    BTC_SIGNALS_AVAILABLE = True
    logger.info("✅ BTC bottom signals integration available")
except ImportError as e:
    BTC_SIGNALS_AVAILABLE = False
    logger.warning(f"⚠️ BTC bottom signals not available: {e}")


async def get_btc_bottom_confluence() -> Dict[str, Any]:
    """
    Get BTC bottom signal confluence from main trading hub
    
    Returns confluence score and all signal states for the crypto scalper
    to incorporate into its decision making.
    """
    if not BTC_SIGNALS_AVAILABLE:
        return {
            "available": False,
            "message": "BTC bottom signals not integrated"
        }
    
    try:
        signals_data = await get_all_signals()
        
        return {
            "available": True,
            "signals": signals_data["signals"],
            "summary": signals_data["summary"],
            "firing_count": signals_data["summary"]["firing_count"],
            "confluence_pct": signals_data["summary"]["confluence_pct"],
            "verdict": signals_data["summary"]["verdict"],
            "is_bottom_signal": signals_data["summary"]["firing_count"] >= 6
        }
    except Exception as e:
        logger.error(f"Error getting BTC signals: {e}")
        return {
            "available": False,
            "error": str(e)
        }


async def get_current_btc_session() -> Dict[str, Any]:
    """Get current BTC trading session from main trading hub"""
    if not BTC_SIGNALS_AVAILABLE:
        return {"active": False}
    
    try:
        session = get_current_session()
        if session:
            return {
                "active": True,
                **session
            }
        return {"active": False}
    except Exception as e:
        logger.error(f"Error getting BTC session: {e}")
        return {"active": False, "error": str(e)}


async def get_btc_session_schedule() -> Dict[str, Any]:
    """Get all BTC trading sessions schedule"""
    if not BTC_SIGNALS_AVAILABLE:
        return {"available": False}
    
    try:
        sessions = get_btc_sessions()
        current = get_current_session()
        
        return {
            "available": True,
            "sessions": sessions,
            "current_session": current
        }
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return {"available": False, "error": str(e)}


async def update_btc_signal(signal_id: str, status: str, value: Any = None) -> Dict[str, Any]:
    """
    Update a BTC bottom signal manually
    
    This allows the crypto scalper to update signals based on
    data it receives from Bybit that the main hub doesn't have.
    """
    if not BTC_SIGNALS_AVAILABLE:
        return {"success": False, "message": "BTC signals not available"}
    
    try:
        result = await update_signal_manual(signal_id, status, value)
        return {
            "success": True,
            "signal": result
        }
    except Exception as e:
        logger.error(f"Error updating signal: {e}")
        return {"success": False, "error": str(e)}


def calculate_bias_from_btc_signals(confluence_data: Dict) -> str:
    """
    Calculate directional bias from BTC bottom signals
    
    Returns: "BULLISH", "BEARISH", or "NEUTRAL"
    """
    if not confluence_data.get("available"):
        return "NEUTRAL"
    
    firing_count = confluence_data.get("firing_count", 0)
    
    # 6+ signals firing = strong bottom signal = BULLISH
    if firing_count >= 6:
        return "BULLISH"
    
    # 4-5 signals = moderate bottom forming
    if firing_count >= 4:
        return "NEUTRAL"  # Wait for more confluence
    
    # 0-3 signals = no bottom yet
    return "NEUTRAL"


class BTCIntegrationManager:
    """
    Manager class for BTC bottom signals integration
    
    Provides a unified interface for the signal engine to
    query macro-level BTC signals.
    """
    
    def __init__(self):
        self.available = BTC_SIGNALS_AVAILABLE
        self.last_confluence_check = None
        self.cached_confluence = None
        self.cache_duration_seconds = 60  # Cache for 1 minute
    
    async def get_confluence(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get cached or fresh confluence data"""
        now = datetime.now(timezone.utc)
        
        # Return cached if fresh
        if (not force_refresh and 
            self.cached_confluence and 
            self.last_confluence_check and
            (now - self.last_confluence_check).total_seconds() < self.cache_duration_seconds):
            return self.cached_confluence
        
        # Fetch fresh
        self.cached_confluence = await get_btc_bottom_confluence()
        self.last_confluence_check = now
        return self.cached_confluence
    
    async def should_favor_longs(self) -> bool:
        """Quick check if BTC bottom signals favor long positions"""
        confluence = await self.get_confluence()
        return confluence.get("is_bottom_signal", False)
    
    async def get_session_context(self) -> Dict[str, Any]:
        """Get current session context for trade timing"""
        return await get_current_btc_session()
    
    async def get_full_context(self) -> Dict[str, Any]:
        """Get full BTC context for signal engine"""
        confluence = await self.get_confluence()
        session = await get_current_btc_session()
        bias = calculate_bias_from_btc_signals(confluence)
        
        return {
            "confluence": confluence,
            "session": session,
            "bias": bias,
            "favor_longs": confluence.get("is_bottom_signal", False),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Global instance
_btc_manager: Optional[BTCIntegrationManager] = None


def get_btc_manager() -> BTCIntegrationManager:
    """Get or create BTC integration manager"""
    global _btc_manager
    if _btc_manager is None:
        _btc_manager = BTCIntegrationManager()
    return _btc_manager
