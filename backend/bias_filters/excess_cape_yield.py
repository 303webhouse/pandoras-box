"""
Excess CAPE Yield (ECY) - Rate-Adjusted Valuation Indicator

Developed by Robert Shiller to compare equity valuations against bond yields.
Better than raw CAPE because it accounts for interest rate environment.

Formula:
    ECY = (1/CAPE) - Real 10-Year Treasury Yield
    ECY = Earnings Yield - Real Risk-Free Rate

Interpretation:
    - High ECY (>4%): Stocks very attractive vs bonds (bullish)
    - Low ECY (<0%): Bonds more attractive than stocks (bearish)

Example:
    CAPE = 35 → Earnings Yield = 2.86%
    Real 10Y = 2.0%
    ECY = 0.86% (stocks barely beating bonds)

Data Sources:
    - CAPE: Manual input (changes slowly, monthly updates sufficient)
    - Real 10Y Yield: FRED API (DGS10 - T10YIE)
"""

import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime

from bias_engine.composite import FactorReading
from bias_engine.factor_utils import score_to_signal, get_latest_price
from bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot

logger = logging.getLogger(__name__)
REAL_YIELD_CACHE_KEY = "fred:REAL_10Y:latest"

# ECY Configuration
ECY_CONFIG = {
    # CAPE (Shiller P/E) - update monthly or when significant changes occur
    # Current value as of late 2024/early 2025 is around 35-38
    "cape": 36.5,
    "cape_last_updated": "2026-01-15",
    
    # Real yield cache (fetched from FRED)
    "real_yield": None,
    "real_yield_updated": None,
    
    # ECY result cache
    "ecy": None,
    "ecy_updated": None,
    
    # Thresholds for scoring
    "thresholds": {
        "very_attractive": 4.0,    # ECY > 4%: +2 (stocks very cheap vs bonds)
        "attractive": 2.0,          # ECY 2-4%: +1 (stocks attractive)
        "neutral_high": 0.0,        # ECY 0-2%: 0 (neutral)
        "neutral_low": -1.0,        # ECY -1 to 0%: -1 (bonds competitive)
        "unattractive": -1.0,       # ECY < -1%: -2 (bonds more attractive)
    },
    
    "enabled": True
}


async def fetch_real_yield_from_fred() -> Optional[float]:
    """
    Fetch real 10-year Treasury yield from FRED.
    Real Yield = Nominal 10Y (DGS10) - 10Y Breakeven Inflation (T10YIE)
    
    Returns:
        Real yield as percentage, or None if fetch fails
    """
    fred_api_key = os.environ.get("FRED_API_KEY")
    if not fred_api_key:
        logger.warning("FRED_API_KEY not configured for ECY")
        cached = await load_fred_snapshot(REAL_YIELD_CACHE_KEY)
        if cached and cached.get("value") is not None:
            return float(cached["value"])
        return None
    
    try:
        from fredapi import Fred
        fred = Fred(api_key=fred_api_key)
        
        # Fetch nominal 10Y yield
        dgs10 = fred.get_series('DGS10', observation_start='2024-01-01')
        nominal_10y = float(dgs10.dropna().iloc[-1])
        
        # Fetch 10Y breakeven inflation
        t10yie = fred.get_series('T10YIE', observation_start='2024-01-01')
        breakeven_10y = float(t10yie.dropna().iloc[-1])
        
        # Real yield = Nominal - Inflation expectations
        real_yield = nominal_10y - breakeven_10y
        
        logger.info(f"📊 Real 10Y Yield: {real_yield:.2f}% (Nominal: {nominal_10y:.2f}%, Breakeven: {breakeven_10y:.2f}%)")
        
        # Cache the result
        ECY_CONFIG["real_yield"] = real_yield
        ECY_CONFIG["real_yield_updated"] = datetime.now().isoformat()
        await cache_fred_snapshot(
            REAL_YIELD_CACHE_KEY,
            {
                "value": real_yield,
                "nominal_10y": nominal_10y,
                "breakeven_10y": breakeven_10y,
                "fetched_at": datetime.utcnow().isoformat(),
            },
        )
        
        return real_yield
        
    except Exception as e:
        logger.error(f"Error fetching real yield from FRED: {e}")
        cached = await load_fred_snapshot(REAL_YIELD_CACHE_KEY)
        if cached and cached.get("value") is not None:
            logger.info(
                "Using cached FRED real-yield snapshot for ECY (fetched: %s)",
                cached.get("fetched_at"),
            )
            return float(cached["value"])
        return ECY_CONFIG.get("real_yield")


def calculate_ecy(cape: float = None, real_yield: float = None) -> Dict[str, Any]:
    """
    Calculate Excess CAPE Yield.
    
    Args:
        cape: Override CAPE value (uses config if not provided)
        real_yield: Override real yield (uses config if not provided)
    
    Returns:
        ECY calculation result with bias interpretation
    """
    cape = cape or ECY_CONFIG["cape"]
    real_yield = real_yield if real_yield is not None else ECY_CONFIG.get("real_yield")
    
    if real_yield is None:
        return {
            "status": "error",
            "message": "Real yield not available - FRED data needed",
            "cape": cape,
            "real_yield": None,
            "ecy": None,
            "bias": "NEUTRAL",
            "enabled": False
        }
    
    # Calculate earnings yield from CAPE
    earnings_yield = (1 / cape) * 100  # Convert to percentage
    
    # Calculate ECY
    ecy = earnings_yield - real_yield
    
    # Determine bias based on ECY
    thresholds = ECY_CONFIG["thresholds"]
    
    if ecy >= thresholds["very_attractive"]:
        bias = "TORO_MAJOR"
        signal = "STRONG_BUY"
        interpretation = f"ECY {ecy:.2f}%: Stocks very attractive vs bonds"
        vote = 2
    elif ecy >= thresholds["attractive"]:
        bias = "TORO_MINOR"
        signal = "BUY"
        interpretation = f"ECY {ecy:.2f}%: Stocks attractive vs bonds"
        vote = 1
    elif ecy >= thresholds["neutral_high"]:
        bias = "NEUTRAL"
        signal = "NEUTRAL"
        interpretation = f"ECY {ecy:.2f}%: Fair valuation vs bonds"
        vote = 0
    elif ecy >= thresholds["neutral_low"]:
        bias = "URSA_MINOR"
        signal = "CAUTION"
        interpretation = f"ECY {ecy:.2f}%: Bonds becoming competitive"
        vote = -1
    else:
        bias = "URSA_MAJOR"
        signal = "BEARISH"
        interpretation = f"ECY {ecy:.2f}%: Bonds more attractive than stocks"
        vote = -2
    
    # Cache result
    ECY_CONFIG["ecy"] = ecy
    ECY_CONFIG["ecy_updated"] = datetime.now().isoformat()
    
    return {
        "status": "success",
        "cape": cape,
        "cape_last_updated": ECY_CONFIG["cape_last_updated"],
        "earnings_yield": round(earnings_yield, 2),
        "real_yield": round(real_yield, 2),
        "ecy": round(ecy, 2),
        "bias": bias,
        "signal": signal,
        "interpretation": interpretation,
        "vote": vote,
        "enabled": ECY_CONFIG["enabled"],
        "thresholds": thresholds
    }


async def get_ecy_reading() -> Dict[str, Any]:
    """
    Get current ECY reading, fetching fresh real yield data if needed.
    
    Returns:
        Full ECY analysis with bias signal
    """
    # Fetch fresh real yield from FRED
    await fetch_real_yield_from_fred()
    
    # Calculate and return ECY
    return calculate_ecy()


def update_cape(new_cape: float, update_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Update the CAPE ratio manually.
    CAPE changes slowly, so monthly updates are sufficient.
    
    Args:
        new_cape: New CAPE value (typically 15-45 range)
        update_date: Optional date string
    
    Returns:
        Updated ECY calculation
    """
    if new_cape < 5 or new_cape > 60:
        raise ValueError("CAPE should be between 5 and 60")
    
    old_cape = ECY_CONFIG["cape"]
    ECY_CONFIG["cape"] = new_cape
    ECY_CONFIG["cape_last_updated"] = update_date or datetime.now().strftime("%Y-%m-%d")
    
    logger.info(f"📈 CAPE updated: {old_cape} -> {new_cape}")
    
    # Recalculate ECY with new CAPE
    return calculate_ecy()


def get_ecy_config() -> Dict[str, Any]:
    """Get current ECY configuration and cached values"""
    return {
        **ECY_CONFIG.copy(),
        "current_calculation": calculate_ecy()
    }


def set_ecy_enabled(enabled: bool) -> None:
    """Enable or disable the ECY indicator"""
    ECY_CONFIG["enabled"] = enabled
    logger.info(f"ECY Indicator {'enabled' if enabled else 'disabled'}")


async def compute_excess_cape_score() -> Optional[FactorReading]:
    """
    Excess CAPE Yield = (1/CAPE) - 10Y nominal yield.
    Lower = more expensive = more risky.
    """
    cape = ECY_CONFIG.get("cape")
    if not cape or cape <= 0:
        return None

    ten_year_raw = await get_latest_price("^TNX")
    if ten_year_raw is None:
        return None

    ten_year = ten_year_raw / 100
    cape_ey = 1.0 / cape
    ecy = (cape_ey - ten_year) * 100

    if ecy >= 3.0:
        score = 0.6
    elif ecy >= 2.0:
        score = 0.3
    elif ecy >= 1.0:
        score = 0.0
    elif ecy >= 0.0:
        score = -0.4
    else:
        score = -0.8

    return FactorReading(
        factor_id="excess_cape",
        score=score,
        signal=score_to_signal(score),
        detail=(
            f"CAPE: {cape:.1f}, Earnings Yield: {cape_ey*100:.1f}%, "
            f"10Y: {ten_year*100:.1f}%, ECY: {ecy:.1f}%"
        ),
        timestamp=datetime.utcnow(),
        source="mixed",
        raw_data={
            "cape": float(cape),
            "earnings_yield": float(cape_ey),
            "ten_year": float(ten_year),
            "ecy": float(ecy),
        },
    )


async def compute_score() -> Optional[FactorReading]:
    return await compute_excess_cape_score()
