"""
VIX Term Structure Bias Filter (Sentiment Proxy)
Weekly bias indicator based on VIX vs VIX3M relationship

The Logic:
- CONTANGO (VIX < VIX3M): Normal state, market calm = BULLISH
- BACKWARDATION (VIX > VIX3M): Fear state, near-term panic = BEARISH
- The steeper the contango/backwardation, the stronger the signal

When VIX is below VIX3M (3-month VIX), traders expect calm to continue.
When VIX spikes above VIX3M, traders expect near-term turbulence.

Data Inputs:
- ^VIX (CBOE Volatility Index) - current level
- ^VIX3M (CBOE 3-Month Volatility Index) - current level

Update Frequency: Weekly (every Monday)

Note: If VIX3M is unavailable, we fall back to comparing VIX level alone.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

from bias_engine.composite import FactorReading
from bias_engine.factor_utils import score_to_signal, get_latest_price, neutral_reading

logger = logging.getLogger(__name__)


class VixTermBias(str, Enum):
    """VIX term structure bias levels"""
    URSA_MAJOR = "URSA_MAJOR"      # Severe backwardation (panic)
    URSA_MINOR = "URSA_MINOR"      # Mild backwardation (caution)
    NEUTRAL = "NEUTRAL"            # Flat term structure
    TORO_MINOR = "TORO_MINOR"      # Mild contango (normal)
    TORO_MAJOR = "TORO_MAJOR"      # Steep contango (complacent)


# Current state storage
_vix_term_state: Dict[str, Any] = {
    "vix_current": None,
    "vix3m_current": None,
    "ratio": None,  # VIX / VIX3M (< 1 = contango, > 1 = backwardation)
    "spread_pct": None,  # (VIX - VIX3M) / VIX3M * 100
    "term_structure": None,  # "CONTANGO" or "BACKWARDATION"
    "bias": VixTermBias.NEUTRAL.value,
    "bias_level": 3,
    "last_updated": None,
    "description": "Awaiting data"
}

# Thresholds
VIX_TERM_CONFIG = {
    "strong_contango_pct": -10,   # VIX 10%+ below VIX3M = strong bullish
    "mild_contango_pct": -5,      # VIX 5-10% below VIX3M = mild bullish
    "mild_backwardation_pct": 5,  # VIX 5-10% above VIX3M = mild bearish
    "strong_backwardation_pct": 10,  # VIX 10%+ above VIX3M = strong bearish
    "vix_fear_threshold": 25,     # Fallback: VIX alone > 25 = fear
    "vix_calm_threshold": 15,     # Fallback: VIX alone < 15 = calm
}


def calculate_vix_term_bias(vix: float, vix3m: float = None) -> Dict[str, Any]:
    """
    Calculate VIX term structure bias.
    
    Args:
        vix: Current VIX level
        vix3m: Current VIX3M level (optional - falls back to VIX-only if unavailable)
    
    Returns:
        Dict with bias, term structure, and context
    """
    config = VIX_TERM_CONFIG
    
    # If VIX3M available, use term structure
    if vix3m and vix3m > 0:
        ratio = vix / vix3m
        spread_pct = ((vix - vix3m) / vix3m) * 100
        
        if spread_pct <= config["strong_contango_pct"]:
            bias = VixTermBias.TORO_MAJOR
            bias_level = 5
            term_structure = "STEEP_CONTANGO"
            description = f"🐂 STEEP CONTANGO: VIX {spread_pct:.1f}% below VIX3M. Market very complacent."
        
        elif spread_pct <= config["mild_contango_pct"]:
            bias = VixTermBias.TORO_MINOR
            bias_level = 4
            term_structure = "CONTANGO"
            description = f"📈 CONTANGO: VIX {abs(spread_pct):.1f}% below VIX3M. Normal calm expectations."
        
        elif spread_pct >= config["strong_backwardation_pct"]:
            bias = VixTermBias.URSA_MAJOR
            bias_level = 1
            term_structure = "SEVERE_BACKWARDATION"
            description = f"🐻 SEVERE BACKWARDATION: VIX {spread_pct:.1f}% above VIX3M. Near-term panic!"
        
        elif spread_pct >= config["mild_backwardation_pct"]:
            bias = VixTermBias.URSA_MINOR
            bias_level = 2
            term_structure = "BACKWARDATION"
            description = f"⚠️ BACKWARDATION: VIX {spread_pct:.1f}% above VIX3M. Elevated near-term fear."
        
        else:
            bias = VixTermBias.NEUTRAL
            bias_level = 3
            term_structure = "FLAT"
            description = f"➖ NEUTRAL: VIX term structure flat (spread: {spread_pct:+.1f}%)."
        
        return {
            "vix_current": round(vix, 2),
            "vix3m_current": round(vix3m, 2),
            "ratio": round(ratio, 3),
            "spread_pct": round(spread_pct, 2),
            "term_structure": term_structure,
            "bias": bias.value,
            "bias_level": bias_level,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
    
    # Fallback: VIX level only
    else:
        if vix >= config["vix_fear_threshold"]:
            bias = VixTermBias.URSA_MAJOR
            bias_level = 1
            description = f"🐻 HIGH VIX: VIX at {vix:.1f} - elevated fear."
        elif vix >= 20:
            bias = VixTermBias.URSA_MINOR
            bias_level = 2
            description = f"⚠️ ELEVATED VIX: VIX at {vix:.1f} - caution warranted."
        elif vix <= config["vix_calm_threshold"]:
            bias = VixTermBias.TORO_MAJOR
            bias_level = 5
            description = f"🐂 LOW VIX: VIX at {vix:.1f} - very calm market."
        elif vix <= 18:
            bias = VixTermBias.TORO_MINOR
            bias_level = 4
            description = f"📈 CALM VIX: VIX at {vix:.1f} - low fear environment."
        else:
            bias = VixTermBias.NEUTRAL
            bias_level = 3
            description = f"➖ NEUTRAL VIX: VIX at {vix:.1f} - normal range."
        
        return {
            "vix_current": round(vix, 2),
            "vix3m_current": None,
            "ratio": None,
            "spread_pct": None,
            "term_structure": "VIX_ONLY_FALLBACK",
            "bias": bias.value,
            "bias_level": bias_level,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }


async def auto_fetch_and_update() -> Dict[str, Any]:
    """
    Auto-fetch VIX term structure data using yfinance and update bias.
    """
    global _vix_term_state
    
    try:
        import yfinance as yf
        
        # Fetch VIX
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="5d")
        
        if len(vix_hist) < 1:
            logger.warning("No VIX data available")
            return {"status": "error", "message": "No VIX data"}
        
        vix_current = float(vix_hist['Close'].iloc[-1])
        
        # Try to fetch VIX3M (may not be available)
        vix3m_current = None
        try:
            vix3m = yf.Ticker("^VIX3M")
            vix3m_hist = vix3m.history(period="5d")
            if len(vix3m_hist) >= 1:
                vix3m_current = float(vix3m_hist['Close'].iloc[-1])
        except Exception as e:
            logger.warning(f"VIX3M not available, using VIX-only fallback: {e}")
        
        # Calculate bias
        result = calculate_vix_term_bias(vix_current, vix3m_current)
        _vix_term_state.update(result)
        _vix_term_state["last_updated"] = datetime.now().isoformat()
        _vix_term_state["data_source"] = "yfinance_auto"
        
        logger.info(f"📉 VIX Term Structure updated: {result['bias']} (VIX: {vix_current:.1f})")
        
        return {"status": "success", "data": _vix_term_state}
        
    except Exception as e:
        logger.error(f"Error fetching VIX term structure data: {e}")
        return {"status": "error", "message": str(e)}


def get_vix_term_status() -> Dict[str, Any]:
    """Get current VIX term structure bias status"""
    return {
        **_vix_term_state,
        "config": VIX_TERM_CONFIG
    }


def get_bias_for_scoring() -> Dict[str, Any]:
    """Get simplified bias for signal scoring integration"""
    bias = _vix_term_state.get("bias", VixTermBias.NEUTRAL.value)
    level = _vix_term_state.get("bias_level", 3)
    
    return {
        "bias": bias,
        "bias_level": level,
        "allows_longs": level >= 3,
        "allows_shorts": level <= 3,
        "last_updated": _vix_term_state.get("last_updated")
    }


async def compute_vix_term_score() -> Optional[FactorReading]:
    """
    VIX / VIX3M ratio.
    Backwardation (ratio > 1.0) = bearish.
    Contango (ratio < 0.85) = bullish.
    Also factors in absolute VIX level.
    """
    vix = await get_latest_price("^VIX")
    vix3m = await get_latest_price("^VIX3M")

    if vix is None:
        return None
    if not vix3m:
        return neutral_reading("vix_term", "VIX3M data unavailable", source="yfinance")

    ratio = vix / vix3m

    if ratio >= 1.10:
        term_score = -1.0
    elif ratio >= 1.0:
        term_score = -0.6
    elif ratio >= 0.95:
        term_score = -0.2
    elif ratio >= 0.85:
        term_score = 0.2
    else:
        term_score = 0.6

    if vix >= 30:
        level_mod = -0.3
    elif vix >= 25:
        level_mod = -0.2
    elif vix >= 20:
        level_mod = -0.1
    elif vix <= 12:
        level_mod = 0.1
    else:
        level_mod = 0.0

    score = max(-1.0, min(1.0, term_score + level_mod))

    return FactorReading(
        factor_id="vix_term",
        score=score,
        signal=score_to_signal(score),
        detail=(
            f"VIX {vix:.1f} / VIX3M {vix3m:.1f} = {ratio:.3f} "
            f"({'backwardation' if ratio > 1 else 'contango'})"
        ),
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "vix": float(vix),
            "vix3m": float(vix3m),
            "ratio": float(ratio),
            "term_score": float(term_score),
            "level_mod": float(level_mod),
        },
    )


async def compute_score() -> Optional[FactorReading]:
    return await compute_vix_term_score()
