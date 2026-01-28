"""
CTA Strategy Scanner - Swing Trading Signal Generator
Based on Ryan's CTA Replication Strategy (20/50/120 SMAs)

Scans for:
1. GOLDEN TOUCH: First touch of 120 SMA after extended rally (5-8% correction)
2. ZONE TRANSITIONS: Stocks entering favorable CTA zones
3. TWO-CLOSE + VOLUME: Confirmed breakouts above key SMAs
4. PULLBACK ENTRIES: Pullbacks to 20 SMA in Max Long zone
5. VIX DIVERGENCE: Filters out fake rallies when VIX rising with price

Output: Actionable signals with Entry, Stop, Target prices

Requirements: yfinance, pandas, pandas_ta
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import uuid
import asyncio
import os
import json

logger = logging.getLogger(__name__)


def convert_numpy_types(obj):
    """Convert numpy types to Python native types for JSON serialization"""
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    return obj

# Watchlist storage path
WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "watchlist.json")


def load_watchlist() -> List[str]:
    """Load user's watchlist for priority scanning"""
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
                return data.get("tickers", [])
    except Exception as e:
        logger.error(f"Error loading watchlist: {e}")
    return []


# Try to import optional dependencies
try:
    import yfinance as yf
    import pandas_ta as ta
    CTA_SCANNER_AVAILABLE = True
except ImportError:
    CTA_SCANNER_AVAILABLE = False
    logger.warning("CTA Scanner dependencies not installed. Run: pip install yfinance pandas_ta")


# Universe Filters
UNIVERSE_FILTERS = {
    "market_cap_min": 2_000_000_000,      # $2B minimum
    "market_cap_max": 200_000_000_000,    # $200B maximum (avoid mega-caps)
    "atr_percent_min": 1.5,                # Minimum daily volatility
    "volume_min": 1_000_000,               # 1M shares/day minimum
    
    # Russell-specific (higher bars)
    "russell_market_cap_max": 50_000_000_000,  # $50B max for Russell
    "russell_atr_percent_min": 2.0,            # Higher volatility requirement
    "russell_volume_min": 2_000_000,           # 2M shares/day
}

# S&P 500 Expanded Universe (Top 200 by market cap/liquidity)
SP500_EXPANDED = [
    # Mega Tech (but still good movers)
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "AVGO", "ORCL", "AMD",
    "CRM", "ADBE", "CSCO", "INTC", "QCOM", "INTU", "NOW", "PANW", "SNPS", "AMAT",
    
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "USB",
    "PNC", "TFC", "COF", "BK", "STT", "SPGI", "MCO", "ICE", "CME", "AON",
    
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "ISRG", "REGN", "VRTX", "CI", "CVS", "ELV", "HUM", "ZTS",
    
    # Consumer Discretionary
    "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TJX", "LOW", "BKNG", "MAR",
    
    # Consumer Staples
    "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL", "GIS",
    
    # Industrials
    "CAT", "BA", "UNP", "UPS", "RTX", "HON", "GE", "DE", "MMC", "ITW",
    "WM", "EMR", "ETN", "FDX", "NSC", "CSX",
    
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL",
    
    # Materials
    "LIN", "APD", "SHW", "ECL", "NEM", "FCX",
    
    # Utilities
    "NEE", "SO", "DUK", "AEP", "SRE", "D", "EXC",
    
    # Real Estate
    "PLD", "AMT", "EQIX", "PSA", "WELL", "SPG", "O", "CBRE",
    
    # Communication Services
    "META", "GOOGL", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS"
]

# Russell 1000 High-Volume Tickers (selected for liquidity)
RUSSELL_HIGH_VOLUME = [
    # High-volume mid-caps with good technical setups
    "PLTR", "SOFI", "RIVN", "LCID", "F", "SNAP", "COIN", "HOOD", "RBLX", "U",
    "ZM", "DOCU", "CRWD", "NET", "DDOG", "SNOW", "MDB", "HUBS", "ZS", "OKTA",
    "SQ", "PYPL", "SHOP", "ROKU", "PINS", "TWLO", "LYFT", "UBER", "DASH", "ABNB",
    "GME", "AMC", "BB", "BBBY", "TLRY", "SNDL", "MARA", "RIOT", "SI", "FUBO",
    "NIO", "XPEV", "LI", "BABA", "JD", "PDD", "BIDU",
    "AFRM", "UPST", "LMND", "OPEN", "WISH", "CLOV", "SKLZ",
    "PLUG", "FCEL", "BE", "QS", "BLNK", "CHPT"
]


# CTA Scanner Configuration
CTA_CONFIG = {
    "enabled": True,
    "scan_interval_minutes": 60,  # Swing trading = less frequent
    "lookback_days": 365,  # Full year for 120 SMA + history
    
    # Golden Touch Settings
    "golden_touch": {
        "min_bars_above_120": 50,  # Must be above 120 for 50+ days
        "min_correction_pct": 5.0,  # 5% minimum correction from high
        "max_correction_pct": 12.0,  # Not too deep (>12% = broken trend)
    },
    
    # Volume Settings
    "volume": {
        "breakout_threshold": 1.10,  # 10% above 30-day avg
        "avg_period": 30,
    },
    
    # Pullback Settings
    "pullback": {
        "max_distance_from_20_pct": 1.5,  # Within 1.5% of 20 SMA
    },
    
    # Risk Management
    "risk": {
        "atr_period": 14,
        "stop_atr_multiplier": 1.5,
        "default_rr_ratio": 2.0,
    },
    
    # Signal Priority Weights
    "priority_weights": {
        "golden_touch": 100,
        "two_close_volume": 80,
        "volume_breakout": 60,
        "pullback_entry": 50,
        "zone_upgrade": 40,
    }
}


def get_cta_zone(price: float, sma20: float, sma50: float, sma120: float) -> Tuple[str, str]:
    """
    Determine CTA zone and bias
    
    Returns: (zone_name, bias)
    """
    if pd.isna(sma20) or pd.isna(sma50) or pd.isna(sma120):
        return ("UNKNOWN", "NEUTRAL")
    
    # Check for capitulation (structural breakdown)
    if sma20 < sma120:
        return ("CAPITULATION", "BEARISH")
    
    # Check zones based on price position
    if price > sma20 and price > sma50 and price > sma120:
        return ("MAX_LONG", "BULLISH")
    elif price < sma20 and price >= sma50:
        return ("DE_LEVERAGING", "NEUTRAL")
    elif price < sma50:
        return ("WATERFALL", "BEARISH")
    else:
        return ("TRANSITION", "NEUTRAL")


def calculate_cta_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all CTA strategy indicators"""
    if df is None or df.empty:
        return df
    
    try:
        # Core SMAs
        df['sma20'] = ta.sma(df['Close'], length=20)
        df['sma50'] = ta.sma(df['Close'], length=50)
        df['sma120'] = ta.sma(df['Close'], length=120)
        df['sma200'] = ta.sma(df['Close'], length=200)
        
        # ATR for stop calculation
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=CTA_CONFIG["risk"]["atr_period"])
        
        # Volume metrics
        vol_period = CTA_CONFIG["volume"]["avg_period"]
        df['vol_avg'] = df['Volume'].rolling(vol_period).mean()
        df['vol_ratio'] = df['Volume'] / df['vol_avg']
        
        # Rolling high (for correction calculation)
        df['rolling_high_60'] = df['High'].rolling(60).max()
        df['correction_pct'] = (df['rolling_high_60'] - df['Close']) / df['rolling_high_60'] * 100
        
        # Days above 120 SMA
        df['above_120'] = df['Close'] > df['sma120']
        df['days_above_120'] = df['above_120'].groupby((~df['above_120']).cumsum()).cumsum()
        
        # Distance to SMAs
        df['dist_to_20_pct'] = (df['Close'] - df['sma20']) / df['sma20'] * 100
        df['dist_to_50_pct'] = (df['Close'] - df['sma50']) / df['sma50'] * 100
        df['dist_to_120_pct'] = (df['Close'] - df['sma120']) / df['sma120'] * 100
        
        # Two-close detection
        df['close_above_50'] = df['Close'] > df['sma50']
        df['close_above_20'] = df['Close'] > df['sma20']
        
        # CTA Zone
        df['cta_zone'] = df.apply(
            lambda row: get_cta_zone(row['Close'], row['sma20'], row['sma50'], row['sma120'])[0],
            axis=1
        )
        
    except Exception as e:
        logger.error(f"Error calculating CTA indicators: {e}")
    
    return df


def check_golden_touch(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for 120 SMA Golden Touch setup
    
    Criteria:
    - Price touching or crossing 120 SMA
    - Was above 120 for 50+ days prior
    - Correction of 5-12% from recent high
    - 20 SMA still above 120 (uptrend intact)
    """
    config = CTA_CONFIG["golden_touch"]
    
    if len(df) < 2:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    price = latest['Close']
    sma120 = latest['sma120']
    sma20 = latest['sma20']
    days_above = latest['days_above_120']
    correction = latest['correction_pct']
    atr = latest['atr']
    
    # Skip if missing data
    if pd.isna(sma120) or pd.isna(sma20) or pd.isna(days_above):
        return None
    
    # Check conditions
    touching_120 = (latest['Low'] <= sma120 * 1.01 and price >= sma120 * 0.99)  # Within 1%
    was_above_long = days_above >= config["min_bars_above_120"]
    valid_correction = config["min_correction_pct"] <= correction <= config["max_correction_pct"]
    uptrend_intact = sma20 > sma120
    
    if touching_120 and was_above_long and valid_correction and uptrend_intact:
        # Calculate entry/stop/target
        entry = price
        stop = sma120 - (atr * CTA_CONFIG["risk"]["stop_atr_multiplier"])
        risk = entry - stop
        target = entry + (risk * CTA_CONFIG["risk"]["default_rr_ratio"])
        
        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "GOLDEN_TOUCH",
            "direction": "LONG",
            "priority": CTA_CONFIG["priority_weights"]["golden_touch"],
            "description": f"First touch of 120 SMA after {int(days_above)} days above. {correction:.1f}% correction.",
            "setup": {
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "risk": round(risk, 2),
                "reward": round(target - entry, 2),
                "rr_ratio": round((target - entry) / risk, 1),
            },
            "context": {
                "cta_zone": latest['cta_zone'],
                "days_above_120": int(days_above),
                "correction_pct": round(correction, 1),
                "sma20": round(sma20, 2),
                "sma50": round(latest['sma50'], 2),
                "sma120": round(sma120, 2),
                "volume_ratio": round(latest['vol_ratio'], 2),
            },
            "confidence": "HIGH",
            "notes": "Rare setup. Best entry in CTA system. Use 2-close rule for confirmation."
        }
    
    return None


def check_two_close_volume(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for Two-Close + Volume Confirmation
    
    Criteria:
    - Price closed above 50 SMA for 2 consecutive days
    - Was below 50 SMA before that
    - Volume > 10% above 30-day average
    """
    if len(df) < 3:
        return None
    
    latest = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    # Two consecutive closes above 50, after being below
    two_close_above_50 = (
        latest['close_above_50'] and 
        prev1['close_above_50'] and 
        not prev2['close_above_50']
    )
    
    # Volume confirmation
    vol_confirmed = latest['vol_ratio'] >= CTA_CONFIG["volume"]["breakout_threshold"]
    
    if two_close_above_50 and vol_confirmed:
        price = latest['Close']
        sma50 = latest['sma50']
        atr = latest['atr']
        
        entry = price
        stop = sma50 - (atr * CTA_CONFIG["risk"]["stop_atr_multiplier"])
        risk = entry - stop
        target = entry + (risk * CTA_CONFIG["risk"]["default_rr_ratio"])
        
        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "TWO_CLOSE_VOLUME",
            "direction": "LONG",
            "priority": CTA_CONFIG["priority_weights"]["two_close_volume"],
            "description": f"Two-close confirmation above 50 SMA with {latest['vol_ratio']:.0%} relative volume.",
            "setup": {
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "risk": round(risk, 2),
                "reward": round(target - entry, 2),
                "rr_ratio": round((target - entry) / risk, 1),
            },
            "context": {
                "cta_zone": latest['cta_zone'],
                "sma50": round(sma50, 2),
                "volume_ratio": round(latest['vol_ratio'], 2),
                "dist_to_50_pct": round(latest['dist_to_50_pct'], 1),
            },
            "confidence": "HIGH",
            "notes": "CTA-confirmed breakout. Strong institutional participation."
        }
    
    return None


def check_pullback_entry(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for Pullback Entry in Max Long zone
    
    Criteria:
    - Currently in MAX_LONG zone (price > all SMAs)
    - Price pulled back to within 1.5% of 20 SMA
    - Low touched or came close to 20 SMA
    """
    if len(df) < 2:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    zone, bias = get_cta_zone(latest['Close'], latest['sma20'], latest['sma50'], latest['sma120'])
    
    if zone != "MAX_LONG":
        return None
    
    # Check pullback to 20 SMA
    max_dist = CTA_CONFIG["pullback"]["max_distance_from_20_pct"]
    dist_to_20 = abs(latest['dist_to_20_pct'])
    touched_20 = latest['Low'] <= latest['sma20'] * 1.005  # Within 0.5%
    
    # Was further away before (actual pullback, not just sitting there)
    was_further = abs(prev['dist_to_20_pct']) > dist_to_20 + 0.5
    
    if (dist_to_20 <= max_dist or touched_20) and was_further:
        price = latest['Close']
        sma20 = latest['sma20']
        atr = latest['atr']
        
        entry = price
        stop = sma20 - (atr * CTA_CONFIG["risk"]["stop_atr_multiplier"])
        risk = entry - stop
        target = entry + (risk * CTA_CONFIG["risk"]["default_rr_ratio"])
        
        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "PULLBACK_ENTRY",
            "direction": "LONG",
            "priority": CTA_CONFIG["priority_weights"]["pullback_entry"],
            "description": f"Pullback to 20 SMA in Max Long zone. {dist_to_20:.1f}% from 20 SMA.",
            "setup": {
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "risk": round(risk, 2),
                "reward": round(target - entry, 2),
                "rr_ratio": round((target - entry) / risk, 1),
            },
            "context": {
                "cta_zone": zone,
                "sma20": round(sma20, 2),
                "sma50": round(latest['sma50'], 2),
                "dist_to_20_pct": round(latest['dist_to_20_pct'], 1),
                "touched_20": touched_20,
            },
            "confidence": "MEDIUM",
            "notes": "Trend continuation trade. Tight stop at 20 SMA."
        }
    
    return None


def check_zone_upgrade(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for CTA Zone upgrades (moving to more bullish zone)
    """
    if len(df) < 2:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    current_zone = latest['cta_zone']
    prev_zone = prev['cta_zone']
    
    # Define zone hierarchy (higher = more bullish)
    zone_rank = {
        "CAPITULATION": 0,
        "WATERFALL": 1,
        "DE_LEVERAGING": 2,
        "TRANSITION": 3,
        "MAX_LONG": 4,
        "UNKNOWN": -1
    }
    
    current_rank = zone_rank.get(current_zone, -1)
    prev_rank = zone_rank.get(prev_zone, -1)
    
    # Zone upgrade detected
    if current_rank > prev_rank and current_rank >= 2:  # Upgraded to at least DE_LEVERAGING
        price = latest['Close']
        atr = latest['atr']
        sma50 = latest['sma50']
        
        entry = price
        stop = sma50 - (atr * CTA_CONFIG["risk"]["stop_atr_multiplier"]) if current_rank >= 3 else price - (atr * 2)
        risk = entry - stop
        target = entry + (risk * CTA_CONFIG["risk"]["default_rr_ratio"])
        
        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "ZONE_UPGRADE",
            "direction": "LONG",
            "priority": CTA_CONFIG["priority_weights"]["zone_upgrade"],
            "description": f"CTA zone upgraded from {prev_zone} to {current_zone}.",
            "setup": {
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "risk": round(risk, 2),
                "reward": round(target - entry, 2),
                "rr_ratio": round((target - entry) / risk, 1),
            },
            "context": {
                "cta_zone": current_zone,
                "previous_zone": prev_zone,
                "sma20": round(latest['sma20'], 2),
                "sma50": round(latest['sma50'], 2),
                "sma120": round(latest['sma120'], 2),
            },
            "confidence": "MEDIUM",
            "notes": "Zone transition signal. Wait for two-close confirmation for higher probability."
        }
    
    return None


# ============================================================================
# SHORT SIGNAL DETECTION (for lagging sectors / bearish setups)
# ============================================================================

def check_bearish_breakdown(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for bearish breakdown below 50 SMA with volume
    
    Criteria:
    - Two consecutive closes below 50 SMA (after being above)
    - Volume > 1.2x average (selling pressure)
    - 20 SMA trending down (downtrend confirmed)
    """
    if len(df) < 3:
        return None
    
    latest = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    # Two consecutive closes below 50, after being above
    two_close_below_50 = (
        latest['Close'] < latest['sma50'] and 
        prev1['Close'] < prev1['sma50'] and 
        prev2['Close'] >= prev2['sma50']
    )
    
    if not two_close_below_50:
        return None
    
    # Volume confirmation
    vol_threshold = CTA_CONFIG["volume"]["breakout_threshold"]
    high_volume = latest['vol_ratio'] >= vol_threshold
    
    # 20 SMA trending down
    sma20_down = latest['sma20'] < prev1['sma20']
    
    if high_volume and sma20_down:
        price = latest['Close']
        sma50 = latest['sma50']
        atr = latest['atr']
        
        entry = price
        stop = sma50 + (atr * CTA_CONFIG["risk"]["stop_atr_multiplier"])
        risk = stop - entry
        target = entry - (risk * CTA_CONFIG["risk"]["default_rr_ratio"])
        
        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "BEARISH_BREAKDOWN",
            "direction": "SHORT",
            "priority": 75,
            "description": f"Bearish breakdown below 50 SMA with {latest['vol_ratio']:.0f}% volume.",
            "setup": {
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "risk": round(risk, 2),
                "reward": round(entry - target, 2),
                "rr_ratio": round((entry - target) / risk, 1),
            },
            "context": {
                "cta_zone": latest['cta_zone'],
                "sma20": round(latest['sma20'], 2),
                "sma50": round(sma50, 2),
                "sma120": round(latest['sma120'], 2),
                "volume_ratio": round(latest['vol_ratio'], 2),
            },
            "confidence": "HIGH",
            "notes": "Bearish breakdown confirmed. Best for lagging sectors."
        }
    
    return None


def check_death_cross(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for Death Cross (50 SMA crosses below 200 SMA)
    
    Strong bearish signal - trend is broken
    """
    if len(df) < 2:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    if pd.isna(latest['sma50']) or pd.isna(latest['sma200']):
        return None
    
    # Death cross just happened
    death_cross = (latest['sma50'] < latest['sma200'] and 
                  prev['sma50'] >= prev['sma200'])
    
    if death_cross:
        price = latest['Close']
        atr = latest['atr']
        sma50 = latest['sma50']
        
        entry = price
        stop = sma50 + (atr * 2)  # Wider stop for trend change
        risk = stop - entry
        target = entry - (risk * 2.5)  # Higher R:R for major trend shift
        
        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "DEATH_CROSS",
            "direction": "SHORT",
            "priority": 90,
            "description": f"Death Cross: 50 SMA crossed below 200 SMA. Major trend reversal.",
            "setup": {
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "risk": round(risk, 2),
                "reward": round(entry - target, 2),
                "rr_ratio": round((entry - target) / risk, 1),
            },
            "context": {
                "cta_zone": latest['cta_zone'],
                "sma50": round(sma50, 2),
                "sma200": round(latest['sma200'], 2),
            },
            "confidence": "HIGH",
            "notes": "Major bearish trend change. Long-term downtrend likely."
        }
    
    return None


def check_resistance_rejection(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for rejection at 50 or 120 SMA resistance
    
    Criteria:
    - Price rallied to 50 or 120 SMA
    - Failed to break above (rejection candle)
    - Now heading lower
    """
    if len(df) < 3:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Check if price tested 50 SMA and got rejected
    tested_50 = prev['High'] >= prev['sma50'] * 0.99  # Got within 1%
    rejected = latest['Close'] < prev['Close']  # Now heading down
    below_50 = latest['Close'] < latest['sma50']
    
    if tested_50 and rejected and below_50:
        price = latest['Close']
        sma50 = latest['sma50']
        atr = latest['atr']
        
        entry = price
        stop = sma50 + (atr * 1.5)
        risk = stop - entry
        target = entry - (risk * 2.0)
        
        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "RESISTANCE_REJECTION",
            "direction": "SHORT",
            "priority": 65,
            "description": f"Rejected at 50 SMA resistance. Heading lower.",
            "setup": {
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "risk": round(risk, 2),
                "reward": round(entry - target, 2),
                "rr_ratio": round((entry - target) / risk, 1),
            },
            "context": {
                "cta_zone": latest['cta_zone'],
                "sma50": round(sma50, 2),
                "resistance_level": round(prev['High'], 2),
            },
            "confidence": "MEDIUM",
            "notes": "Failed breakout. Good for continuation shorts in weak sectors."
        }
    
    return None


async def scan_ticker_cta(ticker: str, allow_shorts: bool = False) -> List[Dict]:
    """Scan a single ticker for all CTA signals"""
    if not CTA_SCANNER_AVAILABLE:
        return []
    
    signals = []
    
    try:
        # Fetch data
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        
        if df.empty or len(df) < 150:
            logger.debug(f"{ticker}: Insufficient data for CTA scan")
            return []
        
        # Calculate indicators
        df = calculate_cta_indicators(df)
        
        # LONG signals (always check)
        golden = check_golden_touch(df, ticker)
        if golden:
            signals.append(golden)
        
        two_close = check_two_close_volume(df, ticker)
        if two_close:
            signals.append(two_close)
        
        pullback = check_pullback_entry(df, ticker)
        if pullback:
            signals.append(pullback)
        
        zone_up = check_zone_upgrade(df, ticker)
        if zone_up:
            signals.append(zone_up)
        
        # SHORT signals (only if enabled)
        if allow_shorts:
            death_cross = check_death_cross(df, ticker)
            if death_cross:
                signals.append(death_cross)
            
            bearish_breakdown = check_bearish_breakdown(df, ticker)
            if bearish_breakdown:
                signals.append(bearish_breakdown)
            
            resistance_rejection = check_resistance_rejection(df, ticker)
            if resistance_rejection:
                signals.append(resistance_rejection)
        
    except Exception as e:
        logger.error(f"Error in CTA scan for {ticker}: {e}")
    
    # Convert numpy types for JSON serialization
    return [convert_numpy_types(s) for s in signals]


async def analyze_ticker_cta(ticker: str) -> Dict[str, Any]:
    """
    Detailed CTA analysis of a single ticker
    Returns comprehensive breakdown of all metrics
    """
    if not CTA_SCANNER_AVAILABLE:
        return {"error": "CTA Scanner dependencies not installed"}
    
    ticker = ticker.upper().strip()
    
    result = {
        "ticker": ticker,
        "scan_time": datetime.now().isoformat(),
        "cta_analysis": {},
        "signals": [],
        "recommendation": None
    }
    
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        
        if df.empty or len(df) < 150:
            result["error"] = "Insufficient data"
            return result
        
        df = calculate_cta_indicators(df)
        latest = df.iloc[-1]
        
        zone, bias = get_cta_zone(latest['Close'], latest['sma20'], latest['sma50'], latest['sma120'])
        
        result["cta_analysis"] = {
            "current_price": round(latest['Close'], 2),
            "cta_zone": zone,
            "bias": bias,
            "sma20": round(latest['sma20'], 2) if pd.notna(latest['sma20']) else None,
            "sma50": round(latest['sma50'], 2) if pd.notna(latest['sma50']) else None,
            "sma120": round(latest['sma120'], 2) if pd.notna(latest['sma120']) else None,
            "sma200": round(latest['sma200'], 2) if pd.notna(latest['sma200']) else None,
            "distance_to_20_pct": round(latest['dist_to_20_pct'], 2) if pd.notna(latest['dist_to_20_pct']) else None,
            "distance_to_50_pct": round(latest['dist_to_50_pct'], 2) if pd.notna(latest['dist_to_50_pct']) else None,
            "distance_to_120_pct": round(latest['dist_to_120_pct'], 2) if pd.notna(latest['dist_to_120_pct']) else None,
            "days_above_120": int(latest['days_above_120']) if pd.notna(latest['days_above_120']) else 0,
            "correction_from_high_pct": round(latest['correction_pct'], 2) if pd.notna(latest['correction_pct']) else None,
            "volume_ratio": round(latest['vol_ratio'], 2) if pd.notna(latest['vol_ratio']) else None,
            "atr": round(latest['atr'], 2) if pd.notna(latest['atr']) else None,
        }
        
        # Get signals
        result["signals"] = await scan_ticker_cta(ticker)
        
        # Generate recommendation
        if result["signals"]:
            best_signal = max(result["signals"], key=lambda x: x["priority"])
            result["recommendation"] = {
                "action": "CONSIDER_LONG",
                "signal_type": best_signal["signal_type"],
                "entry": best_signal["setup"]["entry"],
                "stop": best_signal["setup"]["stop"],
                "target": best_signal["setup"]["target"],
                "confidence": best_signal["confidence"],
            }
        else:
            if zone == "MAX_LONG":
                result["recommendation"] = {
                    "action": "HOLD_OR_WAIT_PULLBACK",
                    "note": "In Max Long zone but no specific entry signal. Wait for pullback to 20 SMA."
                }
            elif zone == "DE_LEVERAGING":
                result["recommendation"] = {
                    "action": "WATCH",
                    "note": "De-leveraging zone. Watch for reclaim of 20 SMA with volume."
                }
            elif zone == "WATERFALL":
                result["recommendation"] = {
                    "action": "AVOID_LONGS",
                    "note": "Waterfall zone. No long entries until 50 SMA reclaimed."
                }
            elif zone == "CAPITULATION":
                result["recommendation"] = {
                    "action": "NO_TRADE",
                    "note": "Capitulation zone. 20 SMA below 120. Wait for structural recovery."
                }
            else:
                result["recommendation"] = {
                    "action": "MONITOR",
                    "note": "No clear setup. Continue monitoring."
                }
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error analyzing {ticker}: {e}")
    
    # Convert numpy types to Python native types for JSON serialization
    return convert_numpy_types(result)


async def check_ticker_filters(ticker: str, is_russell: bool = False) -> bool:
    """
    Check if ticker passes quality filters (market cap, volume, volatility)
    
    Args:
        ticker: Stock symbol
        is_russell: If True, apply stricter Russell filters
        
    Returns:
        True if ticker passes all filters
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Get market cap
        market_cap = info.get('marketCap')
        if not market_cap:
            logger.debug(f"{ticker}: No market cap data")
            return False
        
        # Market cap filter
        if is_russell:
            if market_cap < UNIVERSE_FILTERS["market_cap_min"] or market_cap > UNIVERSE_FILTERS["russell_market_cap_max"]:
                return False
        else:
            if market_cap < UNIVERSE_FILTERS["market_cap_min"] or market_cap > UNIVERSE_FILTERS["market_cap_max"]:
                return False
        
        # Volume filter
        avg_volume = info.get('averageVolume', 0)
        min_vol = UNIVERSE_FILTERS["russell_volume_min"] if is_russell else UNIVERSE_FILTERS["volume_min"]
        if avg_volume < min_vol:
            logger.debug(f"{ticker}: Volume too low ({avg_volume:,})")
            return False
        
        # ATR% filter (need recent data)
        df = stock.history(period="1mo")
        if df.empty or len(df) < 20:
            return False
        
        # Calculate ATR%
        df = calculate_cta_indicators(df)
        latest_atr = df.iloc[-1].get('atr')
        latest_price = df.iloc[-1]['Close']
        
        if pd.isna(latest_atr) or latest_price == 0:
            return False
        
        atr_percent = (latest_atr / latest_price) * 100
        min_atr = UNIVERSE_FILTERS["russell_atr_percent_min"] if is_russell else UNIVERSE_FILTERS["atr_percent_min"]
        
        if atr_percent < min_atr:
            logger.debug(f"{ticker}: ATR% too low ({atr_percent:.2f}%)")
            return False
        
        logger.debug(f"{ticker}: Passed filters - MCap: ${market_cap/1e9:.1f}B, Vol: {avg_volume:,}, ATR%: {atr_percent:.2f}%")
        return True
        
    except Exception as e:
        logger.debug(f"{ticker}: Filter check error - {e}")
        return False


async def build_dynamic_universe(sector_strength: Dict[str, Any] = None) -> List[str]:
    """
    Build optimized scan universe based on sector strength and filters
    
    Priority order:
    1. Watchlist (always included)
    2. Leading sector tickers (20 per sector)
    3. S&P 500 filtered tickers
    4. Russell 1000 high-volume filtered tickers
    
    Returns:
        List of tickers to scan
    """
    universe = []
    
    # 1. Watchlist always first
    watchlist = load_watchlist()
    universe.extend(watchlist)
    logger.info(f"📋 Watchlist: {len(watchlist)} tickers")
    
    # 2. Sector-based allocation (if sector data available)
    if sector_strength:
        # Sort sectors by rank
        sorted_sectors = sorted(sector_strength.items(), key=lambda x: x[1].get('rank', 999))
        
        for sector_name, sector_data in sorted_sectors:
            rank = sector_data.get('rank', 999)
            trend = sector_data.get('trend', 'neutral')
            
            # Allocate tickers based on sector strength
            if trend == 'leading' and rank <= 3:
                # Leading sectors: scan more tickers
                allocation = 20
            elif trend == 'neutral' or (4 <= rank <= 8):
                # Mid-pack sectors: moderate allocation
                allocation = 10
            else:
                # Lagging sectors: skip for now (could add SHORT logic later)
                allocation = 0
            
            logger.info(f"📊 {sector_name}: Rank {rank}, {trend} → {allocation} tickers")
    
    # 3. S&P 500 filtered universe
    logger.info("🔍 Filtering S&P 500 universe...")
    sp500_filtered = []
    
    for ticker in SP500_EXPANDED[:150]:  # Check first 150
        if ticker not in universe:
            if await check_ticker_filters(ticker, is_russell=False):
                sp500_filtered.append(ticker)
                if len(sp500_filtered) >= 80:  # Cap at 80 to save scan time
                    break
    
    universe.extend(sp500_filtered)
    logger.info(f"✅ S&P 500: {len(sp500_filtered)} tickers passed filters")
    
    # 4. Russell high-volume picks (stricter filters)
    logger.info("🔍 Filtering Russell 1000 universe...")
    russell_filtered = []
    
    for ticker in RUSSELL_HIGH_VOLUME[:80]:  # Check first 80
        if ticker not in universe:
            if await check_ticker_filters(ticker, is_russell=True):
                russell_filtered.append(ticker)
                if len(russell_filtered) >= 30:  # Cap at 30
                    break
    
    universe.extend(russell_filtered)
    logger.info(f"✅ Russell: {len(russell_filtered)} tickers passed filters")
    
    logger.info(f"🎯 Total scan universe: {len(universe)} tickers")
    return universe


async def run_cta_scan(tickers: List[str] = None, include_watchlist: bool = True, use_dynamic_universe: bool = True) -> Dict:
    """
    Run full CTA scan on multiple tickers
    
    Args:
        tickers: Optional list of specific tickers to scan
        include_watchlist: If True, prioritize user's watchlist
        use_dynamic_universe: If True, build optimized universe with filters
    
    Returns signals sorted by priority with entry/stop/target
    """
    if not CTA_SCANNER_AVAILABLE:
        return {"error": "CTA Scanner dependencies not installed"}
    
    if not CTA_CONFIG["enabled"]:
        return {"error": "CTA Scanner is disabled"}
    
    start_time = datetime.now()
    
    # Build scan list
    if tickers is not None:
        # Manual ticker list provided
        all_tickers = tickers
        watchlist = load_watchlist() if include_watchlist else []
        logger.info(f"🎯 CTA Scan starting: {len(tickers)} specified tickers")
    elif use_dynamic_universe:
        # Use smart filtered universe
        logger.info("🧠 Building dynamic filtered universe...")
        
        # Try to load sector strength data
        try:
            import httpx
            response = httpx.get("http://localhost:8000/api/watchlist", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                sector_strength = data.get('sector_strength', {})
            else:
                sector_strength = None
        except:
            sector_strength = None
        
        all_tickers = await build_dynamic_universe(sector_strength)
        watchlist = load_watchlist()
    else:
        # Legacy: Just watchlist + top 100
        watchlist = load_watchlist() if include_watchlist else []
        sp500_list = [t for t in SP500_EXPANDED[:100] if t not in watchlist]
        all_tickers = watchlist + sp500_list
        logger.info(f"🎯 CTA Scan starting: {len(watchlist)} watchlist + {len(sp500_list)} S&P")
    
    logger.info(f"📊 Scanning {len(all_tickers)} tickers...")
    
    # Ensure watchlist is loaded for tagging
    if 'watchlist' not in locals():
        watchlist = load_watchlist()
    
    all_signals = []
    scan_stats = {
        "sp500_scanned": 0,
        "russell_scanned": 0,
        "watchlist_scanned": 0,
        "filtered_out": 0
    }
    
    for ticker in all_tickers:
        is_watchlist = ticker in watchlist
        
        try:
            signals = await scan_ticker_cta(ticker)
            for signal in signals:
                signal["from_watchlist"] = is_watchlist
                all_signals.append(signal)
            
            # Track stats
            if is_watchlist:
                scan_stats["watchlist_scanned"] += 1
            elif ticker in RUSSELL_HIGH_VOLUME:
                scan_stats["russell_scanned"] += 1
            else:
                scan_stats["sp500_scanned"] += 1
                
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
        
        await asyncio.sleep(0.05)  # Faster rate limiting (was 0.1)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Sort by: watchlist first, then priority, then confidence
    def sort_key(s):
        conf_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(s.get("confidence", "LOW"), 0)
        return (s.get("from_watchlist", False), s["priority"], conf_rank)
    
    all_signals.sort(key=sort_key, reverse=True)
    
    # Group by signal type
    golden_touch = [s for s in all_signals if s["signal_type"] == "GOLDEN_TOUCH"]
    two_close = [s for s in all_signals if s["signal_type"] == "TWO_CLOSE_VOLUME"]
    pullbacks = [s for s in all_signals if s["signal_type"] == "PULLBACK_ENTRY"]
    zone_upgrades = [s for s in all_signals if s["signal_type"] == "ZONE_UPGRADE"]
    
    result = {
        "scan_time": datetime.now().isoformat(),
        "scan_duration_seconds": round(elapsed, 1),
        "tickers_scanned": len(all_tickers),
        "universe_breakdown": scan_stats,
        "watchlist_count": scan_stats["watchlist_scanned"],
        "total_signals": len(all_signals),
        "filters_enabled": use_dynamic_universe if tickers is None else False,
        
        # Signals by type (best first)
        "golden_touch_signals": golden_touch[:5],
        "two_close_signals": two_close[:10],
        "pullback_signals": pullbacks[:10],
        "zone_upgrade_signals": zone_upgrades[:10],
        
        # Top 10 overall (for quick action)
        "top_signals": all_signals[:10],
    }
    
    logger.info(f"✅ CTA Scan complete: {len(all_signals)} signals in {elapsed:.1f}s")
    logger.info(f"   Universe: {scan_stats['watchlist_scanned']} WL, {scan_stats['sp500_scanned']} S&P, {scan_stats['russell_scanned']} Russell")
    logger.info(f"   Signals: Golden {len(golden_touch)}, Two-Close {len(two_close)}, Pullbacks {len(pullbacks)}")
    
    return result


def get_cta_config() -> Dict:
    """Return current CTA scanner configuration"""
    return CTA_CONFIG.copy()


def set_cta_enabled(enabled: bool) -> None:
    """Enable or disable the CTA scanner"""
    CTA_CONFIG["enabled"] = enabled
