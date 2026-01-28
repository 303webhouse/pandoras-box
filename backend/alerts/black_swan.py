"""
Black Swan Alert System

Detects high-probability reversal conditions and sustained momentum breaks:

1. VIX Spike Alerts (>20% intraday move)
2. Gap Moves (>3% overnight gap in SPY/QQQ)
3. Fed Events (FOMC, rate decisions, Powell speeches)
4. Breadth Extremes (>90% up/down days)
5. Volatility Regime Shifts (VIX term structure inversion)

Use Cases:
- FOMC days: Warn of whipsaw risk, suggest wait-and-see
- VIX spike: Potential reversal setup (mean reversion)
- Gap up/down: Fade or follow based on breadth confirmation
"""

import yfinance as yf
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pytz

logger = logging.getLogger(__name__)

ET = pytz.timezone('America/New_York')

# Black Swan Alert Thresholds
ALERT_CONFIG = {
    "vix_spike_threshold": 20.0,          # 20% intraday VIX move
    "vix_absolute_threshold": 30.0,       # VIX > 30 = fear
    "gap_threshold_pct": 3.0,             # 3% overnight gap
    "breadth_extreme_threshold": 90.0,    # >90% up/down day
    "volume_surge_threshold": 2.0,        # 2x average volume
}

# Fed Event Calendar (manual maintenance for key dates)
FED_EVENTS_2026 = [
    {"date": "2026-01-29", "type": "FOMC", "description": "FOMC Rate Decision + Powell Press Conference"},
    {"date": "2026-03-19", "type": "FOMC", "description": "FOMC Rate Decision + Powell Press Conference"},
    {"date": "2026-05-07", "type": "FOMC", "description": "FOMC Rate Decision"},
    {"date": "2026-06-18", "type": "FOMC", "description": "FOMC Rate Decision + Powell Press Conference"},
    {"date": "2026-07-30", "type": "FOMC", "description": "FOMC Rate Decision"},
    {"date": "2026-09-17", "type": "FOMC", "description": "FOMC Rate Decision + Powell Press Conference"},
    {"date": "2026-11-05", "type": "FOMC", "description": "FOMC Rate Decision"},
    {"date": "2026-12-17", "type": "FOMC", "description": "FOMC Rate Decision + Powell Press Conference"},
]


def get_eastern_now() -> datetime:
    """Get current time in Eastern Time"""
    return datetime.now(ET)


def check_fed_event(date: datetime = None) -> Optional[Dict[str, Any]]:
    """
    Check if today or upcoming days have Fed events
    
    Returns alert if event is today or within next 2 days
    """
    if date is None:
        date = get_eastern_now()
    
    date_str = date.strftime("%Y-%m-%d")
    
    # Check today and next 2 days
    for event in FED_EVENTS_2026:
        event_date = datetime.strptime(event["date"], "%Y-%m-%d").replace(tzinfo=ET)
        days_until = (event_date.date() - date.date()).days
        
        if days_until == 0:
            # Event is TODAY
            return {
                "alert_type": "FED_EVENT_TODAY",
                "severity": "CRITICAL",
                "title": f"⚠️ {event['type']} TODAY",
                "description": event["description"],
                "recommendation": "High whipsaw risk. Avoid new entries. Consider closing positions or tightening stops.",
                "date": event["date"],
                "days_until": 0
            }
        elif 0 < days_until <= 2:
            # Event within 2 days
            return {
                "alert_type": "FED_EVENT_UPCOMING",
                "severity": "HIGH",
                "title": f"📅 {event['type']} in {days_until} day(s)",
                "description": event["description"],
                "recommendation": f"Volatility likely to increase. Consider position sizing and stops.",
                "date": event["date"],
                "days_until": days_until
            }
    
    return None


def check_vix_spike() -> Optional[Dict[str, Any]]:
    """
    Check for VIX spike (fear spike or complacency drop)
    
    Signals:
    - VIX > 30: Fear mode (potential bottom setup)
    - VIX +20% intraday: Panic (fade or wait)
    - VIX -20% intraday: Complacency returning (risk-on)
    """
    try:
        vix = yf.Ticker("^VIX")
        df = vix.history(period="5d", interval="1d")
        
        if df.empty or len(df) < 2:
            return None
        
        current_vix = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2])
        day_high = float(df['High'].iloc[-1])
        day_low = float(df['Low'].iloc[-1])
        
        # Check absolute level
        if current_vix > ALERT_CONFIG["vix_absolute_threshold"]:
            return {
                "alert_type": "VIX_EXTREME",
                "severity": "HIGH",
                "title": f"🔴 VIX ELEVATED: {current_vix:.1f}",
                "description": f"VIX above {ALERT_CONFIG['vix_absolute_threshold']} indicates fear mode",
                "recommendation": "Market bottoms often form at VIX extremes. Watch for reversal signals.",
                "current_level": round(current_vix, 1),
                "threshold": ALERT_CONFIG["vix_absolute_threshold"]
            }
        
        # Check intraday spike
        pct_change = ((current_vix - prev_close) / prev_close) * 100
        intraday_range = ((day_high - day_low) / day_low) * 100
        
        if abs(pct_change) > ALERT_CONFIG["vix_spike_threshold"]:
            if pct_change > 0:
                # VIX spiking = fear
                return {
                    "alert_type": "VIX_SPIKE_UP",
                    "severity": "HIGH",
                    "title": f"🚨 VIX SPIKE: +{pct_change:.1f}%",
                    "description": f"VIX jumped from {prev_close:.1f} to {current_vix:.1f}",
                    "recommendation": "Fear spike. Potential mean reversion setup. Wait for confirmation.",
                    "pct_change": round(pct_change, 1),
                    "current_level": round(current_vix, 1)
                }
            else:
                # VIX dropping = complacency
                return {
                    "alert_type": "VIX_DROP",
                    "severity": "MEDIUM",
                    "title": f"📉 VIX DROP: {pct_change:.1f}%",
                    "description": f"VIX fell from {prev_close:.1f} to {current_vix:.1f}",
                    "recommendation": "Fear subsiding. Risk-on environment resuming.",
                    "pct_change": round(pct_change, 1),
                    "current_level": round(current_vix, 1)
                }
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking VIX spike: {e}")
        return None


def check_gap_moves() -> List[Dict[str, Any]]:
    """
    Check for significant overnight gaps in major indices
    
    Gaps >3% often reverse (fade) or continue with conviction
    Decision depends on volume and breadth
    """
    alerts = []
    
    tickers = ["SPY", "QQQ", "IWM"]
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="2d", interval="1d")
            
            if df.empty or len(df) < 2:
                continue
            
            prev_close = float(df['Close'].iloc[-2])
            today_open = float(df['Open'].iloc[-1])
            
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            
            if abs(gap_pct) >= ALERT_CONFIG["gap_threshold_pct"]:
                direction = "UP" if gap_pct > 0 else "DOWN"
                
                alerts.append({
                    "alert_type": f"GAP_{direction}",
                    "severity": "HIGH",
                    "title": f"{'🟢' if gap_pct > 0 else '🔴'} {ticker} GAP {direction}: {abs(gap_pct):.1f}%",
                    "description": f"{ticker} gapped from ${prev_close:.2f} to ${today_open:.2f}",
                    "recommendation": f"Large gap. Monitor for {'fade opportunity' if abs(gap_pct) > 4 else 'continuation or fill'}.",
                    "ticker": ticker,
                    "gap_pct": round(gap_pct, 2),
                    "prev_close": round(prev_close, 2),
                    "today_open": round(today_open, 2)
                })
        
        except Exception as e:
            logger.error(f"Error checking gap for {ticker}: {e}")
            continue
    
    return alerts


def check_breadth_extremes() -> Optional[Dict[str, Any]]:
    """
    Check for breadth extremes (>90% up or down days)
    
    These often mark short-term exhaustion and reversal points
    """
    try:
        # Use NYSE Advance-Decline data from market breadth
        # This is a simplified check - would need real A/D data for production
        
        spy = yf.Ticker("SPY")
        df = spy.history(period="1d")
        
        if df.empty:
            return None
        
        # Placeholder - would need actual A/D line data
        # For now, check if SPY is at extreme RSI levels
        
        return None  # TODO: Implement with real breadth data
        
    except Exception as e:
        logger.error(f"Error checking breadth: {e}")
        return None


def check_volume_surge(ticker: str = "SPY") -> Optional[Dict[str, Any]]:
    """
    Check for unusual volume surge (>2x average)
    
    High volume confirms conviction in a move
    """
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1mo")
        
        if df.empty or len(df) < 20:
            return None
        
        current_volume = float(df['Volume'].iloc[-1])
        avg_volume = float(df['Volume'].rolling(20).mean().iloc[-1])
        
        volume_ratio = current_volume / avg_volume
        
        if volume_ratio >= ALERT_CONFIG["volume_surge_threshold"]:
            return {
                "alert_type": "VOLUME_SURGE",
                "severity": "MEDIUM",
                "title": f"📊 {ticker} VOLUME SURGE: {volume_ratio:.1f}x",
                "description": f"Volume: {current_volume:,.0f} vs 20-day avg: {avg_volume:,.0f}",
                "recommendation": "High volume confirms conviction. Move likely to continue.",
                "ticker": ticker,
                "volume_ratio": round(volume_ratio, 1),
                "current_volume": int(current_volume),
                "avg_volume": int(avg_volume)
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking volume surge for {ticker}: {e}")
        return None


def get_all_black_swan_alerts() -> List[Dict[str, Any]]:
    """
    Run all Black Swan checks and return active alerts
    
    Returns list of alerts sorted by severity
    """
    alerts = []
    
    # 1. Fed Events (highest priority)
    fed_alert = check_fed_event()
    if fed_alert:
        alerts.append(fed_alert)
    
    # 2. VIX Spikes
    vix_alert = check_vix_spike()
    if vix_alert:
        alerts.append(vix_alert)
    
    # 3. Gap Moves
    gap_alerts = check_gap_moves()
    alerts.extend(gap_alerts)
    
    # 4. Volume Surges
    for ticker in ["SPY", "QQQ"]:
        vol_alert = check_volume_surge(ticker)
        if vol_alert:
            alerts.append(vol_alert)
    
    # 5. Breadth Extremes
    breadth_alert = check_breadth_extremes()
    if breadth_alert:
        alerts.append(breadth_alert)
    
    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    alerts.sort(key=lambda x: severity_order.get(x.get("severity", "LOW"), 3))
    
    return alerts


def should_pause_trading() -> bool:
    """
    Determine if trading should be paused due to Black Swan conditions
    
    Returns True if:
    - Fed event TODAY
    - VIX spike >30%
    - Multiple gap moves
    """
    alerts = get_all_black_swan_alerts()
    
    critical_alerts = [a for a in alerts if a.get("severity") == "CRITICAL"]
    if critical_alerts:
        return True
    
    high_alerts = [a for a in alerts if a.get("severity") == "HIGH"]
    if len(high_alerts) >= 2:
        return True
    
    return False
