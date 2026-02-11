"""
BTC Derivative Bottom-Signals Checklist
Based on Ryan's Market Profile + Order Flow Framework

"We are not guessing price; we are identifying the structural 
exhaustion of sellers and the reset of leverage."

ALL 9 SIGNALS NOW AUTOMATED:
1. 25-Delta Skew - Extreme Negativity (Deribit API)
2. Quarterly Basis - Compression to Parity (Binance API)
3. Perp Funding - Negative Flip (Coinalyze API)
4. Stablecoin APRs - Apathy Floor (DeFiLlama API)
5. Term Structure - Inversion (Coinalyze API)
6. Open Interest - Divergence Trap (Coinalyze API)
7. Liquidation Composition - 80/20 Rule (Coinalyze API)
8. Spot Orderbook Skew - Wall of Bids (Binance API)
9. VIX Spike - Macro Confirmation (yfinance)
"""

import logging
import asyncio
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import data fetching libraries
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# Import Redis client for persistence
try:
    from database.redis_client import get_redis_client
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis client not available - signals will not persist")

# Import API clients
try:
    from bias_filters.coinalyze_client import (
        get_funding_rate, get_open_interest, get_liquidations, get_term_structure
    )
    COINALYZE_AVAILABLE = True
except ImportError:
    COINALYZE_AVAILABLE = False
    logger.warning("Coinalyze client not available")

try:
    from bias_filters.deribit_client import get_25_delta_skew
    DERIBIT_AVAILABLE = True
except ImportError:
    DERIBIT_AVAILABLE = False
    logger.warning("Deribit client not available")

try:
    from bias_filters.defillama_client import get_stablecoin_aprs
    DEFILLAMA_AVAILABLE = True
except ImportError:
    DEFILLAMA_AVAILABLE = False
    logger.warning("DeFiLlama client not available")

try:
    from bias_filters.binance_client import get_spot_orderbook_skew, get_quarterly_basis
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    logger.warning("Binance client not available")


class SignalStatus(str, Enum):
    """Status of each bottom signal"""
    FIRING = "FIRING"       # Signal is active (bullish for bottom)
    NEUTRAL = "NEUTRAL"     # Signal not triggered
    UNKNOWN = "UNKNOWN"     # Data unavailable
    MANUAL = "MANUAL"       # Manually overridden by user


# Redis keys
REDIS_KEY_SIGNALS = "btc:bottom_signals"
REDIS_KEY_RAW_DATA = "btc:bottom_signals:raw"
REDIS_TTL_SECONDS = 86400  # 24 hours


# Signal definitions with thresholds
SIGNAL_DEFINITIONS = {
    "skew_25delta": {
        "name": "25-Delta Skew",
        "description": "Options skew extremely negative (Puts expensive)",
        "threshold": "< -5% or > +5%",
        "source": "deribit",
        "notes": "When skew hits extreme lows, market is fully hedged; dealers buy back hedges creating vanna/charm tailwind"
    },
    "quarterly_basis": {
        "name": "Quarterly Basis",
        "description": "Futures premium compressed to near 0% (or negative)",
        "threshold": "< 5% or > 15% annualized",
        "source": "binance",
        "notes": "Compression confirms speculative longs are washed out, leverage reset"
    },
    "perp_funding": {
        "name": "Perp Funding",
        "description": "Funding rates flip negative (Shorts paying Longs)",
        "threshold": "< -0.03% or > 0.05%",
        "source": "coinalyze",
        "notes": "Creates fuel for short squeeze; no incentive for shorts to hold through grind higher"
    },
    "stablecoin_aprs": {
        "name": "Stablecoin APRs",
        "description": "DeFi lending rates collapsed to base rate",
        "threshold": "< 2% or > 8%",
        "source": "defillama",
        "notes": "Low APRs = apathy, speculative froth gone, no one rushing to leverage up"
    },
    "term_structure": {
        "name": "Term Structure",
        "description": "Near-dated futures > Far-dated (Inversion)",
        "threshold": "Contango + rising funding = FIRING",
        "source": "coinalyze",
        "notes": "Market willing to pay premium to hedge RIGHT NOW; urgency = forced selling/capitulation"
    },
    "open_interest": {
        "name": "Open Interest Divergence",
        "description": "OI rising while price falling (Trap set)",
        "threshold": "OI/Price divergence > 2%",
        "source": "coinalyze",
        "notes": "Aggressive shorts opening late OR longs averaging down; price tick up = late shorts underwater"
    },
    "liquidations": {
        "name": "Liquidation Composition",
        "description": "Total liquidations >75% Longs (Bulls washed)",
        "threshold": "> 75% Long liqs with $5M+ volume",
        "source": "coinalyze",
        "notes": "Bottom cannot form if shorts getting squeezed; high Long liqs = over-leveraged bulls ejected"
    },
    "spot_orderbook": {
        "name": "Spot Orderbook Skew",
        "description": "Bid-side liquidity heavily outweighs Ask-side",
        "threshold": "> 15% imbalance",
        "source": "binance",
        "notes": "Derivatives noisy; Spot is truth. Thick Bid = smart money deploying passive capital"
    },
    "vix_spike": {
        "name": "VIX Spike (Macro)",
        "description": "VIX spikes above 25 (Global capitulation)",
        "threshold": "> 25 or > 20% spike",
        "source": "yfinance",
        "notes": "BTC acts as high-beta liquidity sponge; VIX explosion = global margin call = generational opportunity if other signals firing"
    }
}


# In-memory state (Redis-backed)
_bottom_signals: Dict[str, Dict[str, Any]] = {}
_raw_data: Dict[str, Any] = {}
_initialized = False


def _to_float(value: Any) -> Optional[float]:
    """Convert unknown numeric payloads to float safely."""
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def _load_from_redis() -> None:
    """Load signal states from Redis on startup"""
    global _bottom_signals, _raw_data, _initialized
    
    if not REDIS_AVAILABLE:
        _initialized = True
        return
    
    try:
        redis = await get_redis_client()
        if redis:
            # Load signals
            signals_data = await redis.get(REDIS_KEY_SIGNALS)
            if signals_data:
                _bottom_signals = json.loads(signals_data)
                logger.info(f"Loaded {len(_bottom_signals)} BTC signals from Redis")
            
            # Load raw data
            raw_data = await redis.get(REDIS_KEY_RAW_DATA)
            if raw_data:
                _raw_data = json.loads(raw_data)
        
        _initialized = True
    except Exception as e:
        logger.error(f"Error loading from Redis: {e}")
        _initialized = True


async def _save_to_redis() -> None:
    """Persist signal states to Redis"""
    if not REDIS_AVAILABLE:
        return
    
    try:
        redis = await get_redis_client()
        if redis:
            await redis.setex(
                REDIS_KEY_SIGNALS,
                REDIS_TTL_SECONDS,
                json.dumps(_bottom_signals, default=str)
            )
            await redis.setex(
                REDIS_KEY_RAW_DATA,
                REDIS_TTL_SECONDS,
                json.dumps(_raw_data, default=str)
            )
    except Exception as e:
        logger.error(f"Error saving to Redis: {e}")


def _init_signal(signal_id: str) -> Dict[str, Any]:
    """Initialize a signal with default values"""
    defn = SIGNAL_DEFINITIONS.get(signal_id, {})
    return {
        "name": defn.get("name", signal_id),
        "description": defn.get("description", ""),
        "status": SignalStatus.UNKNOWN.value,
        "value": None,
        "threshold": defn.get("threshold", ""),
        "source": defn.get("source", "unknown"),
        "auto": defn.get("source") != "manual",
        "updated_at": None,
        "notes": defn.get("notes", "")
    }


async def _ensure_initialized():
    """Ensure signals are initialized"""
    global _bottom_signals, _initialized
    
    if not _initialized:
        await _load_from_redis()
    
    # Initialize any missing signals
    for signal_id in SIGNAL_DEFINITIONS:
        if signal_id not in _bottom_signals:
            _bottom_signals[signal_id] = _init_signal(signal_id)


# ============================================================================
# AUTO-FETCH FUNCTIONS
# ============================================================================

async def _fetch_vix_signal() -> Dict[str, Any]:
    """Fetch VIX data and determine signal"""
    if not YFINANCE_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "yfinance not available"}
    
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="5d")
        if hist.empty:
            return {"status": SignalStatus.UNKNOWN.value, "error": "No VIX data"}
        
        current_vix = float(hist['Close'].iloc[-1])
        prev_vix = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_vix
        vix_change = ((current_vix - prev_vix) / prev_vix * 100) if prev_vix > 0 else 0
        
        # Determine signal
        if current_vix > 25 or vix_change > 20:
            status = SignalStatus.FIRING.value
        else:
            status = SignalStatus.NEUTRAL.value
        
        return {
            "status": status,
            "value": round(current_vix, 2),
            "change_pct": round(vix_change, 2),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching VIX: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


async def _fetch_funding_signal() -> Dict[str, Any]:
    """Fetch funding rate from Coinalyze"""
    if not COINALYZE_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "Coinalyze not available"}
    
    try:
        data = await get_funding_rate()
        return {
            "status": data.get("signal", SignalStatus.UNKNOWN.value),
            "value": data.get("funding_rate"),
            "predicted_rate": data.get("predicted_rate"),
            "sentiment": data.get("sentiment"),
            "updated_at": data.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching funding: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


async def _fetch_oi_signal() -> Dict[str, Any]:
    """Fetch open interest from Coinalyze"""
    if not COINALYZE_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "Coinalyze not available"}
    
    try:
        data = await get_open_interest()
        oi_change = _to_float(data.get("oi_change_4h"))
        price_change = _to_float(data.get("price_change_4h"))
        oi_text = f"{oi_change:+.2f}%" if oi_change is not None else "--"
        price_text = f"{price_change:+.2f}%" if price_change is not None else "--"

        return {
            "status": data.get("signal", SignalStatus.UNKNOWN.value),
            "value": f"OI: {oi_text} | Price: {price_text}",
            "oi_change": oi_change,
            "price_change": price_change,
            "divergence": data.get("divergence"),
            "updated_at": data.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching OI: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


async def _fetch_liquidations_signal() -> Dict[str, Any]:
    """Fetch liquidation data from Coinalyze"""
    if not COINALYZE_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "Coinalyze not available"}
    
    try:
        data = await get_liquidations()
        long_pct = _to_float(data.get("long_pct"))
        total_liq = _to_float(data.get("total_liquidations"))
        long_text = f"{long_pct:.0f}%" if long_pct is not None else "--"
        total_text = f"${total_liq/1e6:.1f}M" if total_liq is not None else "--"

        return {
            "status": data.get("signal", SignalStatus.UNKNOWN.value),
            "value": f"{long_text} Long | {total_text}",
            "long_pct": long_pct,
            "total_usd": total_liq,
            "composition": data.get("composition"),
            "updated_at": data.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching liquidations: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


async def _fetch_term_structure_signal() -> Dict[str, Any]:
    """Fetch term structure from Coinalyze"""
    if not COINALYZE_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "Coinalyze not available"}
    
    try:
        data = await get_term_structure()
        return {
            "status": data.get("signal", SignalStatus.UNKNOWN.value),
            "value": f"{data.get('structure', 'unknown')} ({data.get('funding_trend', 'stable')})",
            "structure": data.get("structure"),
            "trend": data.get("funding_trend"),
            "current_funding": data.get("current_funding"),
            "updated_at": data.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching term structure: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


async def _fetch_skew_signal() -> Dict[str, Any]:
    """Fetch 25-delta skew from Deribit"""
    if not DERIBIT_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "Deribit not available"}
    
    try:
        data = await get_25_delta_skew()
        return {
            "status": data.get("signal", SignalStatus.UNKNOWN.value),
            "value": f"{data.get('skew_25d', 0):+.2f}%",
            "skew": data.get("skew_25d"),
            "put_iv": data.get("put_iv_25d"),
            "call_iv": data.get("call_iv_25d"),
            "sentiment": data.get("sentiment"),
            "updated_at": data.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching skew: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


async def _fetch_stablecoin_signal() -> Dict[str, Any]:
    """Fetch stablecoin APRs from DeFiLlama"""
    if not DEFILLAMA_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "DeFiLlama not available"}
    
    try:
        data = await get_stablecoin_aprs()
        return {
            "status": data.get("signal", SignalStatus.UNKNOWN.value),
            "value": f"{data.get('average_apy', 0):.2f}% avg",
            "average_apy": data.get("average_apy"),
            "median_apy": data.get("median_apy"),
            "pools_analyzed": data.get("pools_analyzed"),
            "sentiment": data.get("sentiment"),
            "updated_at": data.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching stablecoin APRs: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


async def _fetch_orderbook_signal() -> Dict[str, Any]:
    """Fetch orderbook skew from Binance"""
    if not BINANCE_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "Binance not available"}
    
    try:
        data = await get_spot_orderbook_skew()
        imbalance = _to_float(data.get("imbalance_pct"))
        imbalance_text = f"{imbalance:+.1f}%" if imbalance is not None else "--"

        return {
            "status": data.get("signal", SignalStatus.UNKNOWN.value),
            "value": f"{imbalance_text} imbalance",
            "imbalance": imbalance,
            "bid_depth": data.get("bid_depth"),
            "ask_depth": data.get("ask_depth"),
            "sentiment": data.get("sentiment"),
            "updated_at": data.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching orderbook: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


async def _fetch_basis_signal() -> Dict[str, Any]:
    """Fetch quarterly basis from Binance"""
    if not BINANCE_AVAILABLE:
        return {"status": SignalStatus.UNKNOWN.value, "error": "Binance not available"}
    
    try:
        data = await get_quarterly_basis()
        basis_ann = _to_float(data.get("basis_annualized"))
        basis_text = f"{basis_ann:.2f}% ann." if basis_ann is not None else "unknown"

        return {
            "status": data.get("signal", SignalStatus.UNKNOWN.value),
            "value": basis_text,
            "basis_annualized": basis_ann,
            "basis_pct": _to_float(data.get("basis_pct")),
            "spot_price": _to_float(data.get("spot_price")),
            "futures_price": _to_float(data.get("futures_price")),
            "sentiment": data.get("sentiment"),
            "updated_at": data.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching basis: {e}")
        return {"status": SignalStatus.UNKNOWN.value, "error": str(e)}


# ============================================================================
# PUBLIC API
# ============================================================================

async def update_all_signals() -> Dict[str, Any]:
    """Fetch and update ALL signals from their respective APIs"""
    global _bottom_signals, _raw_data
    
    await _ensure_initialized()
    
    logger.info("🔄 Updating all BTC bottom signals...")
    
    # Fetch all signals in parallel
    results = await asyncio.gather(
        _fetch_vix_signal(),
        _fetch_funding_signal(),
        _fetch_oi_signal(),
        _fetch_liquidations_signal(),
        _fetch_term_structure_signal(),
        _fetch_skew_signal(),
        _fetch_stablecoin_signal(),
        _fetch_orderbook_signal(),
        _fetch_basis_signal(),
        return_exceptions=True
    )
    
    signal_mapping = [
        ("vix_spike", results[0]),
        ("perp_funding", results[1]),
        ("open_interest", results[2]),
        ("liquidations", results[3]),
        ("term_structure", results[4]),
        ("skew_25delta", results[5]),
        ("stablecoin_aprs", results[6]),
        ("spot_orderbook", results[7]),
        ("quarterly_basis", results[8]),
    ]
    
    # Update signals
    for signal_id, result in signal_mapping:
        if isinstance(result, Exception):
            logger.error(f"Error updating {signal_id}: {result}")
            continue
        
        if signal_id not in _bottom_signals:
            _bottom_signals[signal_id] = _init_signal(signal_id)
        
        # Only update if not manually overridden
        if _bottom_signals[signal_id].get("manual_override"):
            continue
        
        _bottom_signals[signal_id]["status"] = result.get("status", SignalStatus.UNKNOWN.value)
        _bottom_signals[signal_id]["value"] = result.get("value")
        _bottom_signals[signal_id]["updated_at"] = result.get("updated_at", datetime.now(timezone.utc).isoformat())
        _bottom_signals[signal_id]["auto"] = True
        
        # Store raw data for debugging
        _raw_data[signal_id] = result
    
    # Save to Redis
    await _save_to_redis()
    
    # Count firing signals
    firing_count = sum(1 for s in _bottom_signals.values() 
                       if s.get("status") == SignalStatus.FIRING.value)
    
    logger.info(f"✅ BTC signals updated: {firing_count}/{len(_bottom_signals)} firing")
    
    return await get_all_signals()


async def get_all_signals() -> Dict[str, Any]:
    """Get current state of all bottom signals"""
    await _ensure_initialized()
    
    # Count firing signals
    firing_count = sum(1 for s in _bottom_signals.values() 
                       if s.get("status") == SignalStatus.FIRING.value)
    total_signals = len(_bottom_signals)
    
    # Determine overall verdict
    if firing_count >= 7:
        verdict = "STRONG BOTTOM SIGNAL - Consider scaling into longs"
        verdict_level = "strong"
    elif firing_count >= 5:
        verdict = "MODERATE CONFLUENCE - Watch closely for more signals"
        verdict_level = "moderate"
    elif firing_count >= 3:
        verdict = "EARLY SIGNS - Not enough confluence yet"
        verdict_level = "early"
    else:
        verdict = "NO BOTTOM SIGNAL - Conditions not met"
        verdict_level = "none"
    
    return {
        "signals": _bottom_signals,
        "raw_data": _raw_data,
        "confluence": {
            "firing": firing_count,
            "total": total_signals,
            "pct": round(firing_count / total_signals * 100, 1) if total_signals > 0 else 0,
            "verdict": verdict,
            "verdict_level": verdict_level
        },
        "last_update": datetime.now(timezone.utc).isoformat(),
        "api_status": {
            "coinalyze": COINALYZE_AVAILABLE,
            "deribit": DERIBIT_AVAILABLE,
            "defillama": DEFILLAMA_AVAILABLE,
            "binance": BINANCE_AVAILABLE,
            "yfinance": YFINANCE_AVAILABLE,
            "redis": REDIS_AVAILABLE
        },
        "api_keys": {
            "coinalyze": bool(os.getenv("COINALYZE_API_KEY"))
        },
        "api_errors": {
            signal_id: raw.get("error")
            for signal_id, raw in _raw_data.items()
            if isinstance(raw, dict) and raw.get("error")
        }
    }


async def get_signal(signal_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific signal by ID"""
    await _ensure_initialized()
    return _bottom_signals.get(signal_id)


async def update_signal_manual(
    signal_id: str, 
    status: str,
    value: Optional[Any] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Manually override a signal's status
    """
    global _bottom_signals
    await _ensure_initialized()
    
    if signal_id not in SIGNAL_DEFINITIONS:
        raise ValueError(f"Unknown signal: {signal_id}")
    
    # Validate status
    try:
        status_enum = SignalStatus(status.upper())
    except ValueError:
        raise ValueError(f"Invalid status: {status}. Use: FIRING, NEUTRAL, UNKNOWN")
    
    if signal_id not in _bottom_signals:
        _bottom_signals[signal_id] = _init_signal(signal_id)
    
    _bottom_signals[signal_id]["status"] = status_enum.value
    _bottom_signals[signal_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    _bottom_signals[signal_id]["manual_override"] = True
    _bottom_signals[signal_id]["auto"] = False
    
    if value is not None:
        _bottom_signals[signal_id]["value"] = value
    
    if notes is not None:
        _bottom_signals[signal_id]["notes"] = notes
    
    await _save_to_redis()
    
    logger.info(f"📊 BTC Signal '{signal_id}' manually set to {status_enum.value}")
    
    return _bottom_signals[signal_id]


async def clear_manual_override(signal_id: str) -> Dict[str, Any]:
    """Clear manual override for a signal (return to auto-fetch)"""
    global _bottom_signals
    await _ensure_initialized()
    
    if signal_id in _bottom_signals:
        _bottom_signals[signal_id]["manual_override"] = False
        _bottom_signals[signal_id]["auto"] = True
        await _save_to_redis()
    
    # Re-fetch the signal
    return await update_all_signals()


async def reset_all_signals() -> None:
    """Reset all signals to UNKNOWN status"""
    global _bottom_signals, _raw_data
    
    for signal_id in SIGNAL_DEFINITIONS:
        _bottom_signals[signal_id] = _init_signal(signal_id)
    
    _raw_data = {}
    await _save_to_redis()
    
    logger.info("🔄 All BTC bottom signals reset")


def get_signal_ids() -> List[str]:
    """Get list of all signal IDs"""
    return list(SIGNAL_DEFINITIONS.keys())


# ============================================================================
# BTC TRADING SESSIONS
# ============================================================================

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
    """Determine if we're currently in a key BTC trading session"""
    try:
        try:
            from zoneinfo import ZoneInfo
            ny_tz = ZoneInfo("America/New_York")
        except Exception:
            import pytz
            ny_tz = pytz.timezone("America/New_York")

        now_ny = datetime.now(ny_tz)
        hour = now_ny.hour
        minute = now_ny.minute
        weekday = now_ny.weekday()
        
        if 20 <= hour < 21:
            return {**BTC_SESSIONS["asia_handoff"], "active": True}
        elif 4 <= hour < 6:
            return {**BTC_SESSIONS["london_open"], "active": True}
        elif 11 <= hour < 13:
            return {**BTC_SESSIONS["peak_volume"], "active": True}
        elif 15 <= hour < 16:
            return {**BTC_SESSIONS["etf_fixing"], "active": True}
        elif weekday == 4 and hour == 15 and minute >= 55:
            return {**BTC_SESSIONS["friday_close"], "active": True}
        
    except Exception as e:
        logger.error(f"Error checking BTC session: {e}")
    
    return None
