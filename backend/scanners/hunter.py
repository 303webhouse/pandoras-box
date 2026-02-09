"""
DEPRECATED: Trapped trader detection has been absorbed into cta_scanner.py.
This file is kept for reference only. Do not import from it.
See: check_trapped_longs() and check_trapped_shorts() in cta_scanner.py
"""

import pandas as pd
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import uuid
import asyncio
import os

logger = logging.getLogger(__name__)

async def _get_watchlist_symbols() -> List[str]:
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT symbol FROM watchlist_tickers "
                "WHERE source IN ('manual', 'position') AND muted = false "
                "ORDER BY added_at"
            )
        return [row["symbol"] for row in rows]
    except Exception as e:
        logger.warning(f"Failed to load watchlist symbols: {e}")
        return []

# Try to import optional dependencies
try:
    import yfinance as yf
    import pandas_ta as ta
    SCANNER_AVAILABLE = True
except ImportError:
    SCANNER_AVAILABLE = False
    logger.warning("Scanner dependencies not installed. Run: pip install yfinance pandas_ta")

# S&P 500 tickers (top 100 most liquid for faster scanning)
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

# Scanner configuration
SCANNER_CONFIG = {
    "enabled": True,
    "scan_interval_minutes": 15,
    "max_concurrent_requests": 10,
    "lookback_days": 100,  # For 200 SMA we need enough history
    "filters": {
        "adx_min": 20,
        "rsi_bull_max": 60,
        "rsi_bear_min": 40,
        "rvol_min": 1.25,  # Lowered from 1.5 for more results
    }
}


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all required indicators for the Hunter
    
    Adds columns:
    - sma_200: 200-day Simple Moving Average
    - vwap_20: 20-day VWAP approximation
    - adx: Average Directional Index (14-period)
    - rsi: Relative Strength Index (14-period)
    - rvol: Relative Volume (current vs 20-day average)
    """
    if df is None or df.empty:
        return df
    
    try:
        # 1. SMA 200
        df['sma_200'] = ta.sma(df['Close'], length=200)
        
        # 2. VWAP approximation (20-day typical price * volume weighted)
        # True VWAP resets daily, but for screening we use rolling VWAP
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        df['vwap_20'] = (typical_price * df['Volume']).rolling(20).sum() / df['Volume'].rolling(20).sum()
        
        # 3. ADX (14-period)
        adx_data = ta.adx(df['High'], df['Low'], df['Close'], length=14)
        if adx_data is not None and 'ADX_14' in adx_data.columns:
            df['adx'] = adx_data['ADX_14']
        else:
            df['adx'] = None
        
        # 4. RSI (14-period)
        df['rsi'] = ta.rsi(df['Close'], length=14)
        
        # 5. Relative Volume
        df['vol_avg_20'] = df['Volume'].rolling(20).mean()
        df['rvol'] = df['Volume'] / df['vol_avg_20']
        
        # 6. Percent distance from VWAP
        df['pct_from_vwap'] = ((df['Close'] - df['vwap_20']) / df['vwap_20']) * 100
        
    except Exception as e:
        logger.error(f"Error calculating indicators: {e}")
    
    return df


def check_ursa_signal(row: pd.Series, ticker: str) -> Optional[Dict]:
    """
    Check if current data meets URSA (Bearish) criteria
    
    URSA = Trapped Longs
    - Price < 200 SMA (macro bearish)
    - Price < VWAP (buyers underwater)
    - ADX > 20 (trending)
    - RSI > 40 (room to fall)
    - RVOL > 1.5 (institutional activity)
    """
    filters = SCANNER_CONFIG["filters"]
    
    price = row.get('Close')
    sma_200 = row.get('sma_200')
    vwap = row.get('vwap_20')
    adx = row.get('adx')
    rsi = row.get('rsi')
    rvol = row.get('rvol')
    
    # Check all conditions
    if pd.isna(sma_200) or pd.isna(vwap) or pd.isna(adx) or pd.isna(rsi) or pd.isna(rvol):
        return None
    
    # URSA conditions
    macro_bearish = price < sma_200
    trapped_longs = price < vwap
    trending = adx > filters["adx_min"]
    momentum_room = rsi > filters["rsi_bear_min"]
    institutional = rvol > filters["rvol_min"]
    
    if all([macro_bearish, trapped_longs, trending, momentum_room, institutional]):
        return {
            "scan_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "strategy_profile": {
                "name": "Ursa Hunter",
                "bias": "BEARISH",
                "setup_type": "TRAPPED_LONGS"
            },
            "market_data": {
                "current_price": round(price, 2),
                "vwap_20": round(vwap, 2),
                "sma_200": round(sma_200, 2),
                "pct_distance_from_vwap": round(row.get('pct_from_vwap', 0), 2)
            },
            "quality_metrics": {
                "adx_trend_strength": round(adx, 1),
                "rsi_momentum": round(rsi, 1),
                "rvol_institutional": round(rvol, 2)
            },
            "action_required": {
                "priority": "HIGH" if rvol > 2.0 and adx > 30 else "MEDIUM",
                "suggested_timeframe": "1H",
                "sniper_instruction": "Wait for rejection at Value Area High"
            }
        }
    
    return None


def check_taurus_signal(row: pd.Series, ticker: str) -> Optional[Dict]:
    """
    Check if current data meets TAURUS (Bullish) criteria
    
    TAURUS = Trapped Shorts
    - Price > 200 SMA (macro bullish)
    - Price > VWAP (shorts underwater)
    - ADX > 20 (trending)
    - RSI < 60 (room to rise)
    - RVOL > 1.5 (institutional activity)
    """
    filters = SCANNER_CONFIG["filters"]
    
    price = row.get('Close')
    sma_200 = row.get('sma_200')
    vwap = row.get('vwap_20')
    adx = row.get('adx')
    rsi = row.get('rsi')
    rvol = row.get('rvol')
    
    # Check all conditions
    if pd.isna(sma_200) or pd.isna(vwap) or pd.isna(adx) or pd.isna(rsi) or pd.isna(rvol):
        return None
    
    # TAURUS conditions
    macro_bullish = price > sma_200
    trapped_shorts = price > vwap
    trending = adx > filters["adx_min"]
    momentum_room = rsi < filters["rsi_bull_max"]
    institutional = rvol > filters["rvol_min"]
    
    if all([macro_bullish, trapped_shorts, trending, momentum_room, institutional]):
        return {
            "scan_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "strategy_profile": {
                "name": "Taurus Hunter",
                "bias": "BULLISH",
                "setup_type": "TRAPPED_SHORTS"
            },
            "market_data": {
                "current_price": round(price, 2),
                "vwap_20": round(vwap, 2),
                "sma_200": round(sma_200, 2),
                "pct_distance_from_vwap": round(row.get('pct_from_vwap', 0), 2)
            },
            "quality_metrics": {
                "adx_trend_strength": round(adx, 1),
                "rsi_momentum": round(rsi, 1),
                "rvol_institutional": round(rvol, 2)
            },
            "action_required": {
                "priority": "HIGH" if rvol > 2.0 and adx > 30 else "MEDIUM",
                "suggested_timeframe": "1H",
                "sniper_instruction": "Wait for rejection at Value Area Low"
            }
        }
    
    return None


async def scan_single_ticker(ticker: str) -> List[Dict]:
    """
    Scan a single ticker for Hunter signals
    Returns list of signals (can be 0, 1, or 2 if both URSA and TAURUS somehow match)
    """
    if not SCANNER_AVAILABLE:
        logger.warning("Scanner not available - missing dependencies")
        return []
    
    signals = []
    
    try:
        # Fetch data
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")  # 1 year for 200 SMA
        
        if df.empty or len(df) < 200:
            logger.debug(f"{ticker}: Insufficient data")
            return []
        
        # Calculate indicators
        df = calculate_indicators(df)
        
        # Get latest row
        latest = df.iloc[-1]
        
        # Check for URSA signal
        ursa = check_ursa_signal(latest, ticker)
        if ursa:
            signals.append(ursa)
        
        # Check for TAURUS signal
        taurus = check_taurus_signal(latest, ticker)
        if taurus:
            signals.append(taurus)
            
    except Exception as e:
        logger.error(f"Error scanning {ticker}: {e}")
    
    return signals


async def analyze_single_ticker(ticker: str) -> Dict[str, Any]:
    """
    Detailed analysis of a single ticker with pass/fail breakdown for each criteria.
    
    Returns comprehensive analysis showing:
    - What passed ✅
    - What failed ❌
    - Current values for all metrics
    - Overall verdict (URSA, TAURUS, or NO_SIGNAL)
    """
    if not SCANNER_AVAILABLE:
        return {
            "error": "Scanner dependencies not installed",
            "install": "pip install yfinance pandas_ta"
        }
    
    ticker = ticker.upper().strip()
    filters = SCANNER_CONFIG["filters"]
    
    result = {
        "ticker": ticker,
        "scan_time": datetime.now().isoformat(),
        "data_status": "pending",
        "current_price": None,
        "criteria_breakdown": {
            "ursa_bearish": {},
            "taurus_bullish": {}
        },
        "overall_verdict": "NO_SIGNAL",
        "signal_data": None
    }
    
    try:
        # Fetch data
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        
        if df is None or df.empty:
            result["data_status"] = "NO_DATA"
            result["error"] = f"Could not retrieve data for {ticker}"
            return result
        
        if len(df) < 200:
            result["data_status"] = "INSUFFICIENT_HISTORY"
            result["error"] = f"Only {len(df)} days of data. Need 200+ for full analysis."
            # Still try to calculate what we can
        
        # Calculate indicators
        df = calculate_indicators(df)
        latest = df.iloc[-1]
        
        # Extract current values
        price = latest.get('Close')
        sma_200 = latest.get('sma_200')
        vwap = latest.get('vwap_20')
        adx = latest.get('adx')
        rsi = latest.get('rsi')
        rvol = latest.get('rvol')
        
        result["data_status"] = "OK"
        result["current_price"] = round(price, 2) if price else None
        
        # Current metric values
        result["current_metrics"] = {
            "price": round(price, 2) if pd.notna(price) else None,
            "sma_200": round(sma_200, 2) if pd.notna(sma_200) else None,
            "vwap_20": round(vwap, 2) if pd.notna(vwap) else None,
            "adx": round(adx, 1) if pd.notna(adx) else None,
            "rsi": round(rsi, 1) if pd.notna(rsi) else None,
            "rvol": round(rvol, 2) if pd.notna(rvol) else None,
            "pct_from_vwap": round(latest.get('pct_from_vwap', 0), 2) if pd.notna(latest.get('pct_from_vwap')) else None
        }
        
        # Check for missing data
        has_all_data = all([
            pd.notna(price), pd.notna(sma_200), pd.notna(vwap),
            pd.notna(adx), pd.notna(rsi), pd.notna(rvol)
        ])
        
        if not has_all_data:
            result["data_status"] = "PARTIAL_DATA"
        
        # ========== URSA (BEARISH) CRITERIA BREAKDOWN ==========
        ursa_criteria = {
            "price_below_sma200": {
                "description": "Price < 200 SMA (Macro Bearish Trend)",
                "required": f"Price below {round(sma_200, 2) if pd.notna(sma_200) else 'N/A'}",
                "current": f"Price = {round(price, 2) if pd.notna(price) else 'N/A'}",
                "passed": bool(pd.notna(price) and pd.notna(sma_200) and price < sma_200)
            },
            "price_below_vwap": {
                "description": "Price < VWAP (Buyers Underwater = Trapped Longs)",
                "required": f"Price below {round(vwap, 2) if pd.notna(vwap) else 'N/A'}",
                "current": f"Price = {round(price, 2) if pd.notna(price) else 'N/A'}",
                "passed": bool(pd.notna(price) and pd.notna(vwap) and price < vwap)
            },
            "adx_trending": {
                "description": f"ADX > {filters['adx_min']} (Trending Market)",
                "required": f"ADX > {filters['adx_min']}",
                "current": f"ADX = {round(adx, 1) if pd.notna(adx) else 'N/A'}",
                "passed": bool(pd.notna(adx) and adx > filters['adx_min'])
            },
            "rsi_momentum_room": {
                "description": f"RSI > {filters['rsi_bear_min']} (Room to Fall)",
                "required": f"RSI > {filters['rsi_bear_min']}",
                "current": f"RSI = {round(rsi, 1) if pd.notna(rsi) else 'N/A'}",
                "passed": bool(pd.notna(rsi) and rsi > filters['rsi_bear_min'])
            },
            "rvol_institutional": {
                "description": f"RVOL > {filters['rvol_min']} (Institutional Activity)",
                "required": f"RVOL > {filters['rvol_min']}x",
                "current": f"RVOL = {round(rvol, 2) if pd.notna(rvol) else 'N/A'}x",
                "passed": bool(pd.notna(rvol) and rvol > filters['rvol_min'])
            }
        }
        
        result["criteria_breakdown"]["ursa_bearish"] = ursa_criteria
        ursa_passed = all(c["passed"] for c in ursa_criteria.values())
        result["criteria_breakdown"]["ursa_bearish"]["ALL_PASSED"] = ursa_passed
        
        # ========== TAURUS (BULLISH) CRITERIA BREAKDOWN ==========
        taurus_criteria = {
            "price_above_sma200": {
                "description": "Price > 200 SMA (Macro Bullish Trend)",
                "required": f"Price above {round(sma_200, 2) if pd.notna(sma_200) else 'N/A'}",
                "current": f"Price = {round(price, 2) if pd.notna(price) else 'N/A'}",
                "passed": bool(pd.notna(price) and pd.notna(sma_200) and price > sma_200)
            },
            "price_above_vwap": {
                "description": "Price > VWAP (Sellers Underwater = Trapped Shorts)",
                "required": f"Price above {round(vwap, 2) if pd.notna(vwap) else 'N/A'}",
                "current": f"Price = {round(price, 2) if pd.notna(price) else 'N/A'}",
                "passed": bool(pd.notna(price) and pd.notna(vwap) and price > vwap)
            },
            "adx_trending": {
                "description": f"ADX > {filters['adx_min']} (Trending Market)",
                "required": f"ADX > {filters['adx_min']}",
                "current": f"ADX = {round(adx, 1) if pd.notna(adx) else 'N/A'}",
                "passed": bool(pd.notna(adx) and adx > filters['adx_min'])
            },
            "rsi_momentum_room": {
                "description": f"RSI < {filters['rsi_bull_max']} (Room to Rise)",
                "required": f"RSI < {filters['rsi_bull_max']}",
                "current": f"RSI = {round(rsi, 1) if pd.notna(rsi) else 'N/A'}",
                "passed": bool(pd.notna(rsi) and rsi < filters['rsi_bull_max'])
            },
            "rvol_institutional": {
                "description": f"RVOL > {filters['rvol_min']} (Institutional Activity)",
                "required": f"RVOL > {filters['rvol_min']}x",
                "current": f"RVOL = {round(rvol, 2) if pd.notna(rvol) else 'N/A'}x",
                "passed": bool(pd.notna(rvol) and rvol > filters['rvol_min'])
            }
        }
        
        result["criteria_breakdown"]["taurus_bullish"] = taurus_criteria
        taurus_passed = all(c["passed"] for c in taurus_criteria.values())
        result["criteria_breakdown"]["taurus_bullish"]["ALL_PASSED"] = taurus_passed
        
        # ========== OVERALL VERDICT ==========
        if ursa_passed:
            result["overall_verdict"] = "URSA_SIGNAL"
            result["signal_data"] = check_ursa_signal(latest, ticker)
        elif taurus_passed:
            result["overall_verdict"] = "TAURUS_SIGNAL"
            result["signal_data"] = check_taurus_signal(latest, ticker)
        else:
            result["overall_verdict"] = "NO_SIGNAL"
            
            # Count how close to a signal
            ursa_count = sum(1 for c in ursa_criteria.values() if isinstance(c, dict) and c.get("passed"))
            taurus_count = sum(1 for c in taurus_criteria.values() if isinstance(c, dict) and c.get("passed"))
            
            result["near_miss"] = {
                "ursa_criteria_met": f"{ursa_count}/5",
                "taurus_criteria_met": f"{taurus_count}/5"
            }
        
    except Exception as e:
        result["data_status"] = "ERROR"
        result["error"] = str(e)
        logger.error(f"Error analyzing {ticker}: {e}")
    
    return result


async def run_full_scan(tickers: List[str] = None, mode: str = "all", include_watchlist: bool = True) -> Dict:
    """
    Run a full scan on multiple tickers
    
    WATCHLIST PRIORITY: Scans user's watchlist FIRST, then S&P 500
    
    Args:
        tickers: List of tickers to scan (default: watchlist + SP500_TOP_100)
        mode: "all", "ursa", or "taurus"
        include_watchlist: Whether to prioritize watchlist (default: True)
    
    Returns:
        {
            "scan_time": "ISO timestamp",
            "tickers_scanned": int,
            "signals_found": int,
            "watchlist_signals": int,
            "ursa_signals": [...],
            "taurus_signals": [...]
        }
    """
    if not SCANNER_AVAILABLE:
        return {
            "error": "Scanner dependencies not installed",
            "install": "pip install yfinance pandas_ta"
        }
    
    if not SCANNER_CONFIG["enabled"]:
        return {"error": "Scanner is disabled"}
    
    # Build scan list: WATCHLIST FIRST, then S&P 500
    watchlist = []
    sp500_list = []
    
    if tickers is None:
        if include_watchlist:
            watchlist = await _get_watchlist_symbols()
            # S&P 500 minus watchlist tickers (avoid duplicates)
            sp500_list = [t for t in SP500_TOP_100 if t not in watchlist]
        else:
            sp500_list = SP500_TOP_100
    else:
        sp500_list = tickers  # Custom list provided
    
    # Combine: watchlist first, then S&P 500
    all_tickers = watchlist + sp500_list
    
    logger.info(f"🎯 Hunter scan starting: {len(watchlist)} watchlist + {len(sp500_list)} S&P 500 = {len(all_tickers)} total, mode={mode}")
    start_time = datetime.now()
    
    ursa_signals = []
    taurus_signals = []
    watchlist_signal_count = 0
    
    # Scan each ticker
    for i, ticker in enumerate(all_tickers):
        is_watchlist = ticker in watchlist
        
        try:
            signals = await scan_single_ticker(ticker)
            
            for signal in signals:
                # Mark watchlist signals
                signal["from_watchlist"] = is_watchlist
                
                if signal["strategy_profile"]["bias"] == "BEARISH":
                    if mode in ["all", "ursa"]:
                        ursa_signals.append(signal)
                        if is_watchlist:
                            watchlist_signal_count += 1
                else:
                    if mode in ["all", "taurus"]:
                        taurus_signals.append(signal)
                        if is_watchlist:
                            watchlist_signal_count += 1
                        
        except Exception as e:
            logger.error(f"Error in scan loop for {ticker}: {e}")
            continue
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Sort by: Watchlist first, then priority, then RVOL
    def sort_key(x):
        return (
            x.get("from_watchlist", False),  # Watchlist first
            x["action_required"]["priority"] == "HIGH",
            x["quality_metrics"]["rvol_institutional"]
        )
    
    ursa_signals.sort(key=sort_key, reverse=True)
    taurus_signals.sort(key=sort_key, reverse=True)
    
    result = {
        "scan_time": datetime.now().isoformat(),
        "scan_duration_seconds": round(elapsed, 1),
        "tickers_scanned": len(all_tickers),
        "watchlist_count": len(watchlist),
        "sp500_count": len(sp500_list),
        "signals_found": len(ursa_signals) + len(taurus_signals),
        "watchlist_signals": watchlist_signal_count,
        "ursa_signals": ursa_signals[:20],  # Top 20
        "taurus_signals": taurus_signals[:20]  # Top 20
    }
    
    logger.info(f"✅ Hunter scan complete: {result['signals_found']} signals ({watchlist_signal_count} from watchlist) in {elapsed:.1f}s")
    
    return result


def get_scanner_config() -> Dict:
    """Return current scanner configuration"""
    return SCANNER_CONFIG.copy()


def set_scanner_enabled(enabled: bool) -> None:
    """Enable or disable the scanner"""
    SCANNER_CONFIG["enabled"] = enabled


def update_scanner_filters(filters: Dict) -> None:
    """Update scanner filter parameters"""
    SCANNER_CONFIG["filters"].update(filters)
