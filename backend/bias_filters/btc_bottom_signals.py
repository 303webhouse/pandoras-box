"""
BTC Derivative Bottom-Signals Checklist
Based on Ryan's Market Profile + Order Flow Framework

"We are not guessing price; we are identifying the structural 
exhaustion of sellers and the reset of leverage."

Signals:
1. 25-Delta Skew - Extreme Negativity (Puts expensive)
2. Quarterly Basis - Compression to Parity (~0%)
3. Perp Funding - Negative Flip (Shorts paying longs)
4. Stablecoin APRs - Apathy Floor (Near 0%)
5. Term Structure - Inversion (Near > Far dated)
6. Open Interest - Divergence Trap (OI up + Price down)
7. Liquidation Composition - 80/20 Rule (>80% Long liqs)
8. Spot Orderbook Skew - Wall of Bids (Bid > Ask depth)
BONUS: VIX Spike - Macro Confirmation (VIX > 30)
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import data fetching libraries
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class SignalStatus(str, Enum):
    """Status of each bottom signal"""
    FIRING = "FIRING"       # Signal is active (bullish for bottom)
    NEUTRAL = "NEUTRAL"     # Signal not triggered
    UNKNOWN = "UNKNOWN"     # Data unavailable
    MANUAL = "MANUAL"       # Manually set by user


# In-memory storage for signal states
# In production, this would be in Redis for persistence
_bottom_signals: Dict[str, Dict[str, Any]] = {
    "skew_25delta": {
        "name": "25-Delta Skew",
        "description": "Options skew extremely negative (Puts expensive)",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "< -10%",
        "source": "manual",  # manual | coinalyze | deribit | laevitas
        "updated_at": None,
        "notes": "When skew hits extreme lows, market is fully hedged; dealers buy back hedges creating vanna/charm tailwind"
    },
    "quarterly_basis": {
        "name": "Quarterly Basis",
        "description": "Futures premium compressed to near 0% (or negative)",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "< 2% annualized",
        "source": "manual",  # manual | coinalyze | coinglass
        "updated_at": None,
        "notes": "Compression confirms speculative longs are washed out, leverage reset"
    },
    "perp_funding": {
        "name": "Perp Funding",
        "description": "Funding rates flip negative (Shorts paying Longs)",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "< 0%",
        "source": "manual",  # manual | coinalyze | binance
        "updated_at": None,
        "notes": "Creates fuel for short squeeze; no incentive for shorts to hold through grind higher"
    },
    "stablecoin_aprs": {
        "name": "Stablecoin APRs",
        "description": "DeFi lending rates collapsed to base rate",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "< 3%",
        "source": "manual",  # manual | defillama
        "updated_at": None,
        "notes": "Low APRs = apathy, speculative froth gone, no one rushing to leverage up"
    },
    "term_structure": {
        "name": "Term Structure",
        "description": "Near-dated futures > Far-dated (Inversion)",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "Inverted",
        "source": "manual",  # manual | coinalyze
        "updated_at": None,
        "notes": "Market willing to pay premium to hedge RIGHT NOW; urgency = forced selling/capitulation"
    },
    "open_interest": {
        "name": "Open Interest Divergence",
        "description": "OI rising while price falling (Trap set)",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "OI ↑ + Price ↓",
        "source": "manual",  # manual | coinalyze | coinglass
        "updated_at": None,
        "notes": "Aggressive shorts opening late OR longs averaging down; price tick up = late shorts underwater"
    },
    "liquidations": {
        "name": "Liquidation Composition",
        "description": "Total liquidations >80% Longs (Bulls washed)",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "> 80% Long liqs",
        "source": "manual",  # manual | coinalyze | coinglass
        "updated_at": None,
        "notes": "Bottom cannot form if shorts getting squeezed; >80% Long liqs = over-leveraged bulls ejected"
    },
    "spot_orderbook": {
        "name": "Spot Orderbook Skew",
        "description": "Bid-side liquidity heavily outweighs Ask-side",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "Bid > Ask at 1-10% depth",
        "source": "manual",  # manual | binance | coinbase
        "updated_at": None,
        "notes": "Derivatives noisy; Spot is truth. Thick Bid = smart money deploying passive capital"
    },
    "vix_spike": {
        "name": "VIX Spike (Macro)",
        "description": "VIX spikes above 30 (Global capitulation)",
        "status": SignalStatus.UNKNOWN,
        "value": None,
        "threshold": "> 30",
        "source": "auto",  # We can get this from yfinance
        "updated_at": None,
        "notes": "BTC acts as high-beta liquidity sponge; VIX explosion = global margin call = generational opportunity if other signals firing"
    }
}

# Cache for auto-fetched data
_data_cache = {
    "last_update": None,
    "vix": None
}

CACHE_DURATION_MINUTES = 5


async def get_vix_data() -> Optional[float]:
    """Fetch current VIX value using yfinance"""
    global _data_cache
    
    if not YFINANCE_AVAILABLE:
        return None
    
    now = datetime.now()
    
    # Check cache
    if (_data_cache["last_update"] and 
        (now - _data_cache["last_update"]).total_seconds() < CACHE_DURATION_MINUTES * 60 and
        _data_cache["vix"] is not None):
        return _data_cache["vix"]
    
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="1d")
        if not hist.empty:
            vix_value = float(hist['Close'].iloc[-1])
            _data_cache["vix"] = vix_value
            _data_cache["last_update"] = now
            return vix_value
    except Exception as e:
        logger.error(f"Error fetching VIX: {e}")
    
    return None


async def update_auto_signals() -> None:
    """Update signals that can be fetched automatically"""
    global _bottom_signals
    
    # Update VIX
    vix_value = await get_vix_data()
    if vix_value is not None:
        _bottom_signals["vix_spike"]["value"] = round(vix_value, 2)
        _bottom_signals["vix_spike"]["updated_at"] = datetime.now().isoformat()
        
        if vix_value > 30:
            _bottom_signals["vix_spike"]["status"] = SignalStatus.FIRING
        else:
            _bottom_signals["vix_spike"]["status"] = SignalStatus.NEUTRAL
    
    # TODO: Add more auto-fetch sources as they're connected
    # - Coinalyze API for funding, OI, liquidations, basis
    # - DeFiLlama API for stablecoin APRs
    # - Binance API for orderbook depth


async def get_all_signals() -> Dict[str, Any]:
    """Get current state of all bottom signals"""
    
    # Update auto signals first
    await update_auto_signals()
    
    # Count firing signals
    firing_count = sum(1 for s in _bottom_signals.values() 
                       if s["status"] == SignalStatus.FIRING)
    total_signals = len(_bottom_signals)
    
    # Determine overall verdict
    if firing_count >= 6:
        verdict = "🟢 STRONG BOTTOM SIGNAL - Consider scaling into longs"
    elif firing_count >= 4:
        verdict = "🟡 MODERATE CONFLUENCE - Watch closely for more signals"
    elif firing_count >= 2:
        verdict = "🟠 EARLY SIGNS - Not enough confluence yet"
    else:
        verdict = "🔴 NO BOTTOM SIGNAL - Conditions not met"
    
    return {
        "signals": _bottom_signals,
        "summary": {
            "firing_count": firing_count,
            "total_signals": total_signals,
            "confluence_pct": round(firing_count / total_signals * 100, 1),
            "verdict": verdict,
            "updated_at": datetime.now().isoformat()
        }
    }


async def get_signal(signal_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific signal by ID"""
    return _bottom_signals.get(signal_id)


async def update_signal_manual(
    signal_id: str, 
    status: str,
    value: Optional[Any] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Manually update a signal's status
    Used for signals that require manual checking (no API available)
    """
    global _bottom_signals
    
    if signal_id not in _bottom_signals:
        raise ValueError(f"Unknown signal: {signal_id}")
    
    # Validate status
    try:
        status_enum = SignalStatus(status.upper())
    except ValueError:
        raise ValueError(f"Invalid status: {status}. Use: FIRING, NEUTRAL, UNKNOWN, MANUAL")
    
    _bottom_signals[signal_id]["status"] = status_enum
    _bottom_signals[signal_id]["updated_at"] = datetime.now().isoformat()
    _bottom_signals[signal_id]["source"] = "manual"
    
    if value is not None:
        _bottom_signals[signal_id]["value"] = value
    
    if notes is not None:
        _bottom_signals[signal_id]["notes"] = notes
    
    logger.info(f"📊 BTC Signal '{signal_id}' manually set to {status_enum}")
    
    return _bottom_signals[signal_id]


async def reset_all_signals() -> None:
    """Reset all signals to UNKNOWN status"""
    global _bottom_signals
    
    for signal_id in _bottom_signals:
        if _bottom_signals[signal_id]["source"] != "auto":
            _bottom_signals[signal_id]["status"] = SignalStatus.UNKNOWN
            _bottom_signals[signal_id]["value"] = None
            _bottom_signals[signal_id]["updated_at"] = None
    
    logger.info("🔄 All manual BTC bottom signals reset")


def get_signal_ids() -> List[str]:
    """Get list of all signal IDs"""
    return list(_bottom_signals.keys())


# BTC Trading Session Windows (NY/ET times)
BTC_SESSIONS = {
    "asia_handoff": {
        "name": "Asia Handoff + Funding Reset",
        "ny_time": "8pm-9pm",
        "utc_time": "00:00-01:00",
        "description": "One of the five highest-vol hours; Garman-Klass σ spike",
        "trading_note": "Watch for funding reset volatility"
    },
    "london_open": {
        "name": "London Cash FX Open",
        "ny_time": "4am-6am", 
        "utc_time": "08:00-10:00",
        "description": "Depth builds, spreads compress",
        "trading_note": "Good for passive fills / iceberg execution"
    },
    "peak_volume": {
        "name": "Peak Global Volume",
        "ny_time": "11am-1pm",
        "utc_time": "15:00-17:00",
        "description": "Peak global volume, volatility & illiquidity",
        "trading_note": "Best window for breakout scalps; slippage risk higher"
    },
    "etf_fixing": {
        "name": "ETF Fixing Window",
        "ny_time": "3pm-4pm",
        "utc_time": "19:00-20:00",
        "description": "6.7% of all spot BTC volume for ETF creation/redemption",
        "trading_note": "Watch for late-day basis snap from hedging"
    },
    "friday_close": {
        "name": "Friday CME Close",
        "ny_time": "Fri 3:55pm-4pm",
        "utc_time": "Fri 19:55-20:00",
        "description": "CME BRRNY reference-rate; BTC futures expire; ETF NAV set",
        "trading_note": "Micro-spikes in spot and CME basis; beware into the print"
    }
}


def get_btc_sessions() -> Dict[str, Any]:
    """Get BTC trading session windows"""
    return BTC_SESSIONS


def get_current_session() -> Optional[Dict[str, Any]]:
    """
    Determine if we're currently in a key BTC trading session
    Returns the session info if active, None otherwise
    """
    from datetime import datetime
    import pytz
    
    try:
        ny_tz = pytz.timezone('America/New_York')
        now_ny = datetime.now(ny_tz)
        hour = now_ny.hour
        minute = now_ny.minute
        weekday = now_ny.weekday()  # 0=Monday, 4=Friday
        
        # Check each session
        if 20 <= hour < 21:  # 8pm-9pm
            return {**BTC_SESSIONS["asia_handoff"], "active": True}
        elif 4 <= hour < 6:  # 4am-6am
            return {**BTC_SESSIONS["london_open"], "active": True}
        elif 11 <= hour < 13:  # 11am-1pm
            return {**BTC_SESSIONS["peak_volume"], "active": True}
        elif 15 <= hour < 16:  # 3pm-4pm
            return {**BTC_SESSIONS["etf_fixing"], "active": True}
        elif weekday == 4 and hour == 15 and minute >= 55:  # Friday 3:55pm-4pm
            return {**BTC_SESSIONS["friday_close"], "active": True}
        
    except Exception as e:
        logger.error(f"Error checking BTC session: {e}")
    
    return None
