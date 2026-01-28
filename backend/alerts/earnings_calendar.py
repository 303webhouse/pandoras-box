"""
Earnings Calendar Integration

Filters out (or targets) tickers with upcoming earnings:

1. Avoid tickers with earnings in next 3 days (whipsaw risk)
2. Target tickers right after earnings (post-ER momentum)
3. Warn about earnings week for open positions

Uses yfinance earnings calendar data
Note: yfinance/pandas imported lazily inside functions to avoid startup timeout
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pytz

logger = logging.getLogger(__name__)

ET = pytz.timezone('America/New_York')

# Earnings Filter Configuration
EARNINGS_CONFIG = {
    "avoid_days_before": 3,      # Don't enter if earnings in next 3 days
    "target_days_after": 5,      # Target post-ER momentum within 5 days
    "bonus_score": 10,           # Bonus for post-ER momentum plays
    "penalty_score": -20,        # Penalty for pre-ER risk
}


def get_eastern_now() -> datetime:
    """Get current time in Eastern Time"""
    return datetime.now(ET)


def get_earnings_date(ticker: str) -> Optional[datetime]:
    """
    Get next earnings date for a ticker
    
    Returns None if no earnings data available
    """
    try:
        import yfinance as yf
        import pandas as pd
        stock = yf.Ticker(ticker)
        
        # Try to get earnings calendar
        calendar = stock.calendar
        
        if calendar is None or calendar.empty:
            logger.debug(f"{ticker}: No earnings calendar data")
            return None
        
        # Get earnings date
        if 'Earnings Date' in calendar.index:
            earnings_dates = calendar.loc['Earnings Date']
            
            if isinstance(earnings_dates, pd.Series):
                # Multiple dates - take the first
                next_earnings = earnings_dates.iloc[0]
            else:
                next_earnings = earnings_dates
            
            if pd.notna(next_earnings):
                # Convert to datetime if it's a Timestamp
                if hasattr(next_earnings, 'to_pydatetime'):
                    return next_earnings.to_pydatetime().replace(tzinfo=ET)
                else:
                    return next_earnings
        
        return None
        
    except Exception as e:
        logger.debug(f"{ticker}: Error fetching earnings date - {e}")
        return None


def check_earnings_timing(ticker: str, current_date: datetime = None) -> Dict[str, Any]:
    """
    Check earnings timing for a ticker
    
    Returns:
        - status: "PRE_EARNINGS", "POST_EARNINGS", "CLEAR", "UNKNOWN"
        - days_until: Days until/since earnings
        - recommendation: Trading recommendation
        - score_adjustment: Points to add/subtract from signal score
    """
    if current_date is None:
        current_date = get_eastern_now()
    
    earnings_date = get_earnings_date(ticker)
    
    if earnings_date is None:
        return {
            "ticker": ticker,
            "status": "UNKNOWN",
            "days_until": None,
            "earnings_date": None,
            "recommendation": "No earnings data available. Proceed with caution.",
            "score_adjustment": 0,
            "should_avoid": False,
            "should_target": False
        }
    
    # Calculate days until earnings
    days_until = (earnings_date.date() - current_date.date()).days
    
    # Pre-earnings window (avoid)
    if 0 <= days_until <= EARNINGS_CONFIG["avoid_days_before"]:
        return {
            "ticker": ticker,
            "status": "PRE_EARNINGS",
            "days_until": days_until,
            "earnings_date": earnings_date.strftime("%Y-%m-%d"),
            "recommendation": f"⚠️ Earnings in {days_until} day(s). HIGH WHIPSAW RISK. Avoid new entries.",
            "score_adjustment": EARNINGS_CONFIG["penalty_score"],
            "should_avoid": True,
            "should_target": False
        }
    
    # Post-earnings window (target)
    if -EARNINGS_CONFIG["target_days_after"] <= days_until < 0:
        days_ago = abs(days_until)
        return {
            "ticker": ticker,
            "status": "POST_EARNINGS",
            "days_until": days_until,
            "days_since": days_ago,
            "earnings_date": earnings_date.strftime("%Y-%m-%d"),
            "recommendation": f"✅ Earnings {days_ago} day(s) ago. Post-ER momentum opportunity.",
            "score_adjustment": EARNINGS_CONFIG["bonus_score"],
            "should_avoid": False,
            "should_target": True
        }
    
    # Clear window
    return {
        "ticker": ticker,
        "status": "CLEAR",
        "days_until": days_until if days_until > 0 else None,
        "earnings_date": earnings_date.strftime("%Y-%m-%d") if days_until > 0 else None,
        "recommendation": "Clear of earnings. Proceed normally.",
        "score_adjustment": 0,
        "should_avoid": False,
        "should_target": False
    }


def filter_tickers_by_earnings(tickers: List[str], avoid_pre_earnings: bool = True) -> Dict[str, Any]:
    """
    Filter a list of tickers based on earnings timing
    
    Args:
        tickers: List of ticker symbols
        avoid_pre_earnings: If True, remove tickers with upcoming earnings
        
    Returns:
        Dict with filtered tickers and earnings info
    """
    results = {
        "filtered_tickers": [],
        "avoided_tickers": [],
        "target_tickers": [],
        "earnings_info": {}
    }
    
    for ticker in tickers:
        earnings_check = check_earnings_timing(ticker)
        results["earnings_info"][ticker] = earnings_check
        
        if earnings_check["should_avoid"] and avoid_pre_earnings:
            results["avoided_tickers"].append(ticker)
            logger.info(f"🚫 {ticker}: Filtered out - {earnings_check['recommendation']}")
        elif earnings_check["should_target"]:
            results["target_tickers"].append(ticker)
            results["filtered_tickers"].append(ticker)
            logger.info(f"🎯 {ticker}: Post-ER target - {earnings_check['recommendation']}")
        else:
            results["filtered_tickers"].append(ticker)
    
    logger.info(f"📊 Earnings filter: {len(tickers)} → {len(results['filtered_tickers'])} (avoided {len(results['avoided_tickers'])})")
    
    return results


def check_open_position_earnings(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Check earnings timing for open positions
    
    Returns list of warnings for positions with upcoming earnings
    """
    warnings = []
    
    for position in positions:
        ticker = position.get("ticker")
        if not ticker:
            continue
        
        earnings_check = check_earnings_timing(ticker)
        
        if earnings_check["should_avoid"]:
            warnings.append({
                "ticker": ticker,
                "position": position,
                "warning": earnings_check["recommendation"],
                "severity": "HIGH",
                "days_until": earnings_check["days_until"],
                "action": "Consider closing or tightening stops before earnings"
            })
    
    return warnings
