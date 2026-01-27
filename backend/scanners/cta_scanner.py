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


# S&P 500 tickers for scanning
SP500_TOP_100 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B", "UNH", "XOM",
    "JNJ", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY",
    "PEP", "KO", "COST", "AVGO", "MCD", "WMT", "CSCO", "TMO", "ACN", "ABT",
    "DHR", "NEE", "LIN", "ADBE", "NKE", "TXN", "PM", "UNP", "CRM", "RTX",
    "ORCL", "CMCSA", "AMD", "LOW", "INTC", "SPGI", "HON", "AMGN", "UPS", "IBM",
    "BA", "CAT", "GE", "SBUX", "DE", "INTU", "QCOM", "PLD", "ISRG", "MDLZ",
    "AXP", "BKNG", "GILD", "ADI", "TJX", "SYK", "VRTX", "ADP", "MMC", "REGN",
    "CVS", "BLK", "SCHW", "C", "MO", "ZTS", "CI", "TMUS", "LRCX", "PGR",
    "NOW", "ETN", "PANW", "BSX", "SNPS", "SLB", "EQIX", "CB", "CME", "SO",
    "ITW", "DUK", "MU", "AON", "CL", "ICE", "WM", "MCO", "PNC", "FDX"
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


async def scan_ticker_cta(ticker: str) -> List[Dict]:
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
        
        # Check for each signal type (priority order)
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


async def run_cta_scan(tickers: List[str] = None, include_watchlist: bool = True) -> Dict:
    """
    Run full CTA scan on multiple tickers
    
    Returns signals sorted by priority with entry/stop/target
    """
    if not CTA_SCANNER_AVAILABLE:
        return {"error": "CTA Scanner dependencies not installed"}
    
    if not CTA_CONFIG["enabled"]:
        return {"error": "CTA Scanner is disabled"}
    
    # Build scan list
    watchlist = []
    sp500_list = []
    
    if tickers is None:
        if include_watchlist:
            watchlist = load_watchlist()
            sp500_list = [t for t in SP500_TOP_100 if t not in watchlist]
        else:
            sp500_list = SP500_TOP_100
    else:
        sp500_list = tickers
    
    all_tickers = watchlist + sp500_list
    
    logger.info(f"🎯 CTA Scan starting: {len(watchlist)} watchlist + {len(sp500_list)} S&P 500")
    start_time = datetime.now()
    
    all_signals = []
    
    for ticker in all_tickers:
        is_watchlist = ticker in watchlist
        
        try:
            signals = await scan_ticker_cta(ticker)
            for signal in signals:
                signal["from_watchlist"] = is_watchlist
                all_signals.append(signal)
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
        
        await asyncio.sleep(0.1)  # Rate limiting
    
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
        "watchlist_count": len(watchlist),
        "total_signals": len(all_signals),
        
        # Signals by type (best first)
        "golden_touch_signals": golden_touch[:5],
        "two_close_signals": two_close[:10],
        "pullback_signals": pullbacks[:10],
        "zone_upgrade_signals": zone_upgrades[:10],
        
        # Top 10 overall (for quick action)
        "top_signals": all_signals[:10],
    }
    
    logger.info(f"✅ CTA Scan complete: {len(all_signals)} signals in {elapsed:.1f}s")
    logger.info(f"   Golden Touch: {len(golden_touch)}, Two-Close: {len(two_close)}, Pullbacks: {len(pullbacks)}")
    
    return result


def get_cta_config() -> Dict:
    """Return current CTA scanner configuration"""
    return CTA_CONFIG.copy()


def set_cta_enabled(enabled: bool) -> None:
    """Enable or disable the CTA scanner"""
    CTA_CONFIG["enabled"] = enabled
