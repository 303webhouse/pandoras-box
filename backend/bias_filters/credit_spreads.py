"""
Credit Spreads Bias Filter
Weekly bias indicator based on high yield vs treasury performance

The Logic:
- HYG (High Yield/Junk Bonds) outperforming TLT (Treasuries) = RISK-ON (Bullish)
- TLT outperforming HYG = RISK-OFF (Bearish)
- Similar performance = NEUTRAL

When investors are confident, they buy riskier junk bonds (HYG up).
When investors are fearful, they flee to safe treasuries (TLT up).

Data Inputs:
- HYG (iShares High Yield Corporate Bond ETF) - 5-day performance
- TLT (iShares 20+ Year Treasury Bond ETF) - 5-day performance

Update Frequency: Weekly (every Monday)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

from bias_engine.composite import FactorReading
from bias_engine.factor_utils import score_to_signal, get_price_history

logger = logging.getLogger(__name__)


class CreditSpreadBias(str, Enum):
    """Credit spread bias levels"""
    URSA_MAJOR = "URSA_MAJOR"      # Strong flight to safety
    URSA_MINOR = "URSA_MINOR"      # Mild risk-off
    NEUTRAL = "NEUTRAL"            # No clear preference
    TORO_MINOR = "TORO_MINOR"      # Mild risk-on
    TORO_MAJOR = "TORO_MAJOR"      # Strong risk appetite


# Current state storage
_credit_spread_state: Dict[str, Any] = {
    "hyg_return": None,
    "tlt_return": None,
    "spread": None,  # HYG return - TLT return (positive = risk-on)
    "bias": CreditSpreadBias.NEUTRAL.value,
    "bias_level": 3,
    "last_updated": None,
    "description": "Awaiting data"
}

# Thresholds
CREDIT_SPREAD_CONFIG = {
    "strong_spread_pct": 2.0,    # >2% spread = strong signal
    "mild_spread_pct": 0.75,     # 0.75-2% spread = mild signal
    "lookback_days": 5,          # 5 trading days (1 week)
}


def calculate_credit_spread_bias(hyg_return: float, tlt_return: float) -> Dict[str, Any]:
    """
    Calculate credit spread bias from ETF performance.
    
    Args:
        hyg_return: 5-day return of HYG (high yield bonds) in percent
        tlt_return: 5-day return of TLT (treasuries) in percent
    
    Returns:
        Dict with bias, spread, and context
    """
    config = CREDIT_SPREAD_CONFIG
    
    # Spread: positive = HYG outperforming (risk-on), negative = TLT outperforming (risk-off)
    spread = hyg_return - tlt_return
    
    # Determine bias based on spread
    if spread >= config["strong_spread_pct"]:
        bias = CreditSpreadBias.TORO_MAJOR
        bias_level = 5
        description = f"🐂 RISK-ON: Junk bonds (HYG) crushing treasuries by {spread:.1f}%. Strong risk appetite."
    
    elif spread >= config["mild_spread_pct"]:
        bias = CreditSpreadBias.TORO_MINOR
        bias_level = 4
        description = f"📈 LEAN BULLISH: HYG outperforming TLT by {spread:+.1f}%. Mild risk appetite."
    
    elif spread <= -config["strong_spread_pct"]:
        bias = CreditSpreadBias.URSA_MAJOR
        bias_level = 1
        description = f"🐻 RISK-OFF: Flight to safety - treasuries beating junk by {abs(spread):.1f}%."
    
    elif spread <= -config["mild_spread_pct"]:
        bias = CreditSpreadBias.URSA_MINOR
        bias_level = 2
        description = f"⚠️ LEAN BEARISH: TLT outperforming HYG by {abs(spread):.1f}%. Caution."
    
    else:
        bias = CreditSpreadBias.NEUTRAL
        bias_level = 3
        description = f"➖ NEUTRAL: No clear credit preference (spread: {spread:+.1f}%)."
    
    return {
        "hyg_return": round(hyg_return, 2),
        "tlt_return": round(tlt_return, 2),
        "spread": round(spread, 2),
        "bias": bias.value,
        "bias_level": bias_level,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }


async def auto_fetch_and_update() -> Dict[str, Any]:
    """
    Auto-fetch credit spread data using yfinance and update bias.
    """
    global _credit_spread_state
    
    try:
        import yfinance as yf
        
        # Fetch HYG (High Yield Corporate Bonds)
        hyg = yf.Ticker("HYG")
        hyg_hist = hyg.history(period="10d")
        
        # Fetch TLT (Long-term Treasuries)
        tlt = yf.Ticker("TLT")
        tlt_hist = tlt.history(period="10d")
        
        if len(hyg_hist) < 6 or len(tlt_hist) < 6:
            logger.warning("Not enough data for credit spread calculation")
            return {"status": "error", "message": "Insufficient data"}
        
        # Calculate 5-day returns
        hyg_current = float(hyg_hist['Close'].iloc[-1])
        hyg_5d_ago = float(hyg_hist['Close'].iloc[-6])
        hyg_return = ((hyg_current - hyg_5d_ago) / hyg_5d_ago) * 100
        
        tlt_current = float(tlt_hist['Close'].iloc[-1])
        tlt_5d_ago = float(tlt_hist['Close'].iloc[-6])
        tlt_return = ((tlt_current - tlt_5d_ago) / tlt_5d_ago) * 100
        
        # Calculate bias
        result = calculate_credit_spread_bias(hyg_return, tlt_return)
        _credit_spread_state.update(result)
        _credit_spread_state["last_updated"] = datetime.now().isoformat()
        _credit_spread_state["data_source"] = "yfinance_auto"
        
        logger.info(f"💳 Credit Spreads updated: {result['bias']} (spread: {result['spread']:+.1f}%)")
        
        return {"status": "success", "data": _credit_spread_state}
        
    except Exception as e:
        logger.error(f"Error fetching credit spread data: {e}")
        return {"status": "error", "message": str(e)}


def get_credit_spread_status() -> Dict[str, Any]:
    """Get current credit spread bias status"""
    return {
        **_credit_spread_state,
        "config": CREDIT_SPREAD_CONFIG
    }


def get_bias_for_scoring() -> Dict[str, Any]:
    """Get simplified bias for signal scoring integration"""
    bias = _credit_spread_state.get("bias", CreditSpreadBias.NEUTRAL.value)
    level = _credit_spread_state.get("bias_level", 3)
    
    return {
        "bias": bias,
        "bias_level": level,
        "allows_longs": level >= 3,
        "allows_shorts": level <= 3,
        "last_updated": _credit_spread_state.get("last_updated")
    }


async def compute_credit_spread_score() -> Optional[FactorReading]:
    """
    Compute HYG/TLT ratio vs its 20-day SMA.
    Bearish when ratio is falling (HYG underperforming TLT).
    """
    hyg = await get_price_history("HYG", days=30)
    tlt = await get_price_history("TLT", days=30)

    if hyg is None or tlt is None or hyg.empty or tlt.empty:
        return None
    if "close" not in hyg.columns or "close" not in tlt.columns:
        return None

    ratio = (hyg["close"] / tlt["close"]).dropna()
    if len(ratio) < 20:
        return None

    current_ratio = float(ratio.iloc[-1])
    sma_20 = float(ratio.rolling(20).mean().iloc[-1])
    if sma_20 == 0:
        return None

    pct_dev = (current_ratio - sma_20) / sma_20 * 100

    if len(ratio) >= 5 and ratio.iloc[-5] != 0:
        roc_5d = (current_ratio - float(ratio.iloc[-5])) / float(ratio.iloc[-5]) * 100
    else:
        roc_5d = 0.0

    if pct_dev >= 2.0:
        base = 0.8
    elif pct_dev >= 1.0:
        base = 0.4
    elif pct_dev >= -1.0:
        base = 0.0
    elif pct_dev >= -2.0:
        base = -0.4
    else:
        base = -0.8

    roc_modifier = max(-0.2, min(0.2, roc_5d * 0.1))
    score = max(-1.0, min(1.0, base + roc_modifier))

    return FactorReading(
        factor_id="credit_spreads",
        score=score,
        signal=score_to_signal(score),
        detail=(
            f"HYG/TLT ratio {current_ratio:.3f} vs SMA20 {sma_20:.3f} "
            f"({pct_dev:+.1f}%), 5d ROC: {roc_5d:+.2f}%"
        ),
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "hyg": float(hyg["close"].iloc[-1]),
            "tlt": float(tlt["close"].iloc[-1]),
            "ratio": current_ratio,
            "sma20": sma_20,
            "pct_dev": float(pct_dev),
            "roc_5d": float(roc_5d),
        },
    )


async def compute_score() -> Optional[FactorReading]:
    return await compute_credit_spread_score()
