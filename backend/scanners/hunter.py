"""
The Hunter - S&P 500 Stock Scanner
Scans for "Trapped Traders" with institutional volume backing

Finds:
- URSA candidates: Trapped longs (price < VWAP, below 200 SMA)
- TAURUS candidates: Trapped shorts (price > VWAP, above 200 SMA)

Requirements: yfinance, pandas, pandas_ta
"""

import pandas as pd
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import uuid
import asyncio

logger = logging.getLogger(__name__)

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
        "rvol_min": 1.5,
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


async def run_full_scan(tickers: List[str] = None, mode: str = "all") -> Dict:
    """
    Run a full scan on multiple tickers
    
    Args:
        tickers: List of tickers to scan (default: SP500_TOP_100)
        mode: "all", "ursa", or "taurus"
    
    Returns:
        {
            "scan_time": "ISO timestamp",
            "tickers_scanned": int,
            "signals_found": int,
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
    
    if tickers is None:
        tickers = SP500_TOP_100
    
    logger.info(f"🎯 Hunter scan starting: {len(tickers)} tickers, mode={mode}")
    start_time = datetime.now()
    
    ursa_signals = []
    taurus_signals = []
    
    # Scan each ticker
    for ticker in tickers:
        try:
            signals = await scan_single_ticker(ticker)
            
            for signal in signals:
                if signal["strategy_profile"]["bias"] == "BEARISH":
                    if mode in ["all", "ursa"]:
                        ursa_signals.append(signal)
                else:
                    if mode in ["all", "taurus"]:
                        taurus_signals.append(signal)
                        
        except Exception as e:
            logger.error(f"Error in scan loop for {ticker}: {e}")
            continue
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Sort by priority and quality metrics
    ursa_signals.sort(key=lambda x: (
        x["action_required"]["priority"] == "HIGH",
        x["quality_metrics"]["rvol_institutional"]
    ), reverse=True)
    
    taurus_signals.sort(key=lambda x: (
        x["action_required"]["priority"] == "HIGH",
        x["quality_metrics"]["rvol_institutional"]
    ), reverse=True)
    
    result = {
        "scan_time": datetime.now().isoformat(),
        "scan_duration_seconds": round(elapsed, 1),
        "tickers_scanned": len(tickers),
        "signals_found": len(ursa_signals) + len(taurus_signals),
        "ursa_signals": ursa_signals[:20],  # Top 20
        "taurus_signals": taurus_signals[:20]  # Top 20
    }
    
    logger.info(f"✅ Hunter scan complete: {result['signals_found']} signals in {elapsed:.1f}s")
    
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
