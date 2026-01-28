"""
Session Open Breakout Strategy
Trades breakouts from the opening range of key crypto trading sessions

KEY SESSIONS (from existing BTC signals):
1. Asia Handoff (8-9pm ET / 00:00-01:00 UTC) - Funding reset, high vol
2. London Open (4-6am ET / 08:00-10:00 UTC) - Depth builds, spreads compress
3. Peak Volume (11am-1pm ET / 15:00-17:00 UTC) - Best for breakout scalps
4. ETF Fixing (3-4pm ET / 19:00-20:00 UTC) - ETF creation/redemption flow

LOGIC:
- Identify the high/low of the first 15-30 minutes of a session
- Wait for a decisive breakout above high or below low
- Enter on the breakout with stop at opposite end of range
- Target 2-3x the range size

RISK PROFILE: Moderate-Aggressive
- Win rate ~50-55%
- Excellent R:R (2:1 to 4:1)
- Requires patience and discipline
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, time, timedelta
from dataclasses import dataclass, field
from enum import Enum
import pytz

logger = logging.getLogger(__name__)


class SessionType(str, Enum):
    """Trading session types"""
    ASIA_HANDOFF = "asia_handoff"
    LONDON_OPEN = "london_open"
    PEAK_VOLUME = "peak_volume"
    ETF_FIXING = "etf_fixing"


class BreakoutDirection(str, Enum):
    """Direction of breakout"""
    LONG = "long"
    SHORT = "short"


@dataclass
class SessionRange:
    """Opening range for a session"""
    session: SessionType
    high: float
    low: float
    range_size: float
    formed_at: datetime
    candles_used: int


@dataclass
class BreakoutSignal:
    """Session breakout trading signal"""
    session: SessionType
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float  # 2x range
    take_profit_2: float  # 3x range
    range_high: float
    range_low: float
    range_size: float
    breakout_strength: float  # How far past the range
    confidence: float
    reasoning: str
    timestamp: datetime


# Session definitions (ET timezone)
SESSION_TIMES = {
    SessionType.ASIA_HANDOFF: {
        "start_hour": 20,  # 8pm ET
        "start_minute": 0,
        "duration_minutes": 60,
        "range_formation_minutes": 15,
        "description": "Asia Handoff + Funding Reset",
        "notes": "One of highest-vol hours; watch for funding volatility"
    },
    SessionType.LONDON_OPEN: {
        "start_hour": 4,  # 4am ET
        "start_minute": 0,
        "duration_minutes": 120,
        "range_formation_minutes": 30,
        "description": "London Cash FX Open",
        "notes": "Depth builds, spreads compress - good for breakouts"
    },
    SessionType.PEAK_VOLUME: {
        "start_hour": 11,  # 11am ET
        "start_minute": 0,
        "duration_minutes": 120,
        "range_formation_minutes": 20,
        "description": "Peak Global Volume",
        "notes": "BEST window for breakout scalps; higher slippage risk"
    },
    SessionType.ETF_FIXING: {
        "start_hour": 15,  # 3pm ET
        "start_minute": 0,
        "duration_minutes": 60,
        "range_formation_minutes": 15,
        "description": "ETF Fixing Window",
        "notes": "6.7% of spot volume for ETF creation/redemption"
    }
}


class SessionBreakoutStrategy:
    """
    Session Opening Range Breakout Strategy
    
    Identifies and trades breakouts from key session opening ranges.
    """
    
    # Breakout thresholds
    MIN_BREAKOUT_PCT = 0.001  # Must break by at least 0.1%
    STRONG_BREAKOUT_PCT = 0.003  # 0.3% is a strong breakout
    
    # Range requirements
    MIN_RANGE_PCT = 0.002  # Minimum 0.2% range (too tight = fake breakouts)
    MAX_RANGE_PCT = 0.015  # Maximum 1.5% range (too wide = bad R:R)
    
    # Target multipliers
    TARGET_1_RANGE_MULT = 2.0  # First target at 2x range
    TARGET_2_RANGE_MULT = 3.0  # Second target at 3x range
    
    def __init__(self):
        self.enabled = True
        self.et_tz = pytz.timezone('America/New_York')
        
        # Active session tracking
        self.active_session: Optional[SessionType] = None
        self.session_range: Optional[SessionRange] = None
        self.range_forming = False
        self.range_candles: List[Dict] = []
        
        # Breakout tracking
        self.breakout_triggered = False
        self.last_signal: Optional[BreakoutSignal] = None
        self.signal_history: List[BreakoutSignal] = []
        
        # Cooldown per session (one signal per session)
        self.session_signals_today: Dict[SessionType, bool] = {}
    
    def get_current_session(self) -> Optional[SessionType]:
        """Determine if we're currently in a key session"""
        now_et = datetime.now(self.et_tz)
        hour = now_et.hour
        minute = now_et.minute
        current_minutes = hour * 60 + minute
        
        for session_type, config in SESSION_TIMES.items():
            session_start = config["start_hour"] * 60 + config["start_minute"]
            session_end = session_start + config["duration_minutes"]
            
            # Handle day rollover (e.g., 11pm to 1am)
            if session_end > 1440:  # Past midnight
                if current_minutes >= session_start or current_minutes < session_end - 1440:
                    return session_type
            else:
                if session_start <= current_minutes < session_end:
                    return session_type
        
        return None
    
    def is_range_formation_period(self, session: SessionType) -> bool:
        """Check if we're in the range formation period of a session"""
        config = SESSION_TIMES[session]
        now_et = datetime.now(self.et_tz)
        
        session_start = now_et.replace(
            hour=config["start_hour"],
            minute=config["start_minute"],
            second=0,
            microsecond=0
        )
        
        formation_end = session_start + timedelta(minutes=config["range_formation_minutes"])
        
        return session_start <= now_et < formation_end
    
    def update_range(self, price: float, timestamp: datetime = None):
        """Update the forming range with new price data"""
        if not self.range_forming:
            return
        
        self.range_candles.append({
            "price": price,
            "timestamp": timestamp or datetime.now(timezone.utc)
        })
        
        # Update range high/low
        if self.session_range:
            if price > self.session_range.high:
                self.session_range.high = price
            if price < self.session_range.low:
                self.session_range.low = price
            
            self.session_range.range_size = self.session_range.high - self.session_range.low
            self.session_range.candles_used = len(self.range_candles)
    
    def analyze(
        self,
        current_price: float,
        volume: float = None,
        orderbook_imbalance: float = 0
    ) -> Optional[BreakoutSignal]:
        """
        Analyze current conditions for session breakout signal
        
        Args:
            current_price: Current BTC price
            volume: Current volume (for confirmation)
            orderbook_imbalance: -1 to 1 (for confirmation)
        
        Returns:
            BreakoutSignal if conditions met, None otherwise
        """
        
        if not self.enabled:
            return None
        
        # Check what session we're in
        current_session = self.get_current_session()
        
        if current_session is None:
            # Not in any key session
            self.active_session = None
            self.range_forming = False
            self.session_range = None
            return None
        
        # Check if we already signaled for this session today
        if self.session_signals_today.get(current_session, False):
            return None
        
        # Starting a new session
        if current_session != self.active_session:
            self.active_session = current_session
            self.range_forming = True
            self.breakout_triggered = False
            self.range_candles = []
            
            # Initialize range
            self.session_range = SessionRange(
                session=current_session,
                high=current_price,
                low=current_price,
                range_size=0,
                formed_at=datetime.now(timezone.utc),
                candles_used=0
            )
            
            logger.info(f"📊 New session started: {current_session.value} | "
                       f"Forming range from ${current_price:,.2f}")
            return None
        
        # Update range if still forming
        if self.is_range_formation_period(current_session):
            self.update_range(current_price)
            return None
        
        # Range formation complete - now looking for breakout
        if self.range_forming and self.session_range:
            self.range_forming = False
            
            range_pct = self.session_range.range_size / self.session_range.low
            
            # Validate range
            if range_pct < self.MIN_RANGE_PCT:
                logger.info(f"⚠️ Range too tight ({range_pct*100:.2f}%) - skipping session")
                return None
            
            if range_pct > self.MAX_RANGE_PCT:
                logger.info(f"⚠️ Range too wide ({range_pct*100:.2f}%) - skipping session")
                return None
            
            logger.info(f"✅ Range formed: ${self.session_range.low:,.2f} - "
                       f"${self.session_range.high:,.2f} "
                       f"({range_pct*100:.2f}%)")
        
        # Check for breakout
        if not self.session_range or self.breakout_triggered:
            return None
        
        range_high = self.session_range.high
        range_low = self.session_range.low
        range_size = self.session_range.range_size
        
        # Calculate breakout distances
        distance_above_high = (current_price - range_high) / range_high
        distance_below_low = (range_low - current_price) / range_low
        
        signal = None
        
        # Long breakout
        if distance_above_high >= self.MIN_BREAKOUT_PCT:
            self.breakout_triggered = True
            
            breakout_strength = distance_above_high / self.STRONG_BREAKOUT_PCT
            confidence = min(0.5 + (breakout_strength * 0.3), 0.85)
            
            # Adjust for orderbook
            if orderbook_imbalance > 0.2:
                confidence = min(confidence + 0.1, 0.9)
            
            reasoning_parts = [
                f"🔼 LONG BREAKOUT above {current_session.value} range",
                f"Range: ${range_low:,.2f} - ${range_high:,.2f}",
                f"Breakout strength: {distance_above_high*100:.2f}%",
                SESSION_TIMES[current_session]["notes"]
            ]
            
            if orderbook_imbalance > 0.15:
                reasoning_parts.append(f"✓ Bid support ({orderbook_imbalance:.0%} imbalance)")
            
            signal = BreakoutSignal(
                session=current_session,
                direction="LONG",
                entry_price=round(current_price, 2),
                stop_loss=round(range_low - (range_size * 0.1), 2),  # Just below range low
                take_profit_1=round(current_price + (range_size * self.TARGET_1_RANGE_MULT), 2),
                take_profit_2=round(current_price + (range_size * self.TARGET_2_RANGE_MULT), 2),
                range_high=round(range_high, 2),
                range_low=round(range_low, 2),
                range_size=round(range_size, 2),
                breakout_strength=round(distance_above_high * 100, 2),
                confidence=round(confidence, 2),
                reasoning=" | ".join(reasoning_parts),
                timestamp=datetime.now(timezone.utc)
            )
        
        # Short breakout
        elif distance_below_low >= self.MIN_BREAKOUT_PCT:
            self.breakout_triggered = True
            
            breakout_strength = distance_below_low / self.STRONG_BREAKOUT_PCT
            confidence = min(0.5 + (breakout_strength * 0.3), 0.85)
            
            # Adjust for orderbook
            if orderbook_imbalance < -0.2:
                confidence = min(confidence + 0.1, 0.9)
            
            reasoning_parts = [
                f"🔽 SHORT BREAKOUT below {current_session.value} range",
                f"Range: ${range_low:,.2f} - ${range_high:,.2f}",
                f"Breakout strength: {distance_below_low*100:.2f}%",
                SESSION_TIMES[current_session]["notes"]
            ]
            
            if orderbook_imbalance < -0.15:
                reasoning_parts.append(f"✓ Ask pressure ({orderbook_imbalance:.0%} imbalance)")
            
            signal = BreakoutSignal(
                session=current_session,
                direction="SHORT",
                entry_price=round(current_price, 2),
                stop_loss=round(range_high + (range_size * 0.1), 2),  # Just above range high
                take_profit_1=round(current_price - (range_size * self.TARGET_1_RANGE_MULT), 2),
                take_profit_2=round(current_price - (range_size * self.TARGET_2_RANGE_MULT), 2),
                range_high=round(range_high, 2),
                range_low=round(range_low, 2),
                range_size=round(range_size, 2),
                breakout_strength=round(distance_below_low * 100, 2),
                confidence=round(confidence, 2),
                reasoning=" | ".join(reasoning_parts),
                timestamp=datetime.now(timezone.utc)
            )
        
        if signal:
            self.last_signal = signal
            self.signal_history.append(signal)
            self.session_signals_today[current_session] = True
            
            if len(self.signal_history) > 100:
                self.signal_history = self.signal_history[-100:]
            
            logger.info(f"🎯 Breakout Signal: {signal.direction} @ ${signal.entry_price:,.2f} | "
                       f"Session: {current_session.value} | Confidence: {signal.confidence:.0%}")
        
        return signal
    
    def reset_daily(self):
        """Reset daily session tracking (call at start of new trading day)"""
        self.session_signals_today = {}
        logger.info("Session breakout daily reset")
    
    def get_upcoming_sessions(self) -> List[Dict[str, Any]]:
        """Get information about upcoming sessions"""
        now_et = datetime.now(self.et_tz)
        sessions = []
        
        for session_type, config in SESSION_TIMES.items():
            session_start = now_et.replace(
                hour=config["start_hour"],
                minute=config["start_minute"],
                second=0,
                microsecond=0
            )
            
            # If session already passed today, show tomorrow's
            if session_start < now_et:
                session_start += timedelta(days=1)
            
            mins_until = (session_start - now_et).total_seconds() / 60
            
            sessions.append({
                "session": session_type.value,
                "description": config["description"],
                "start_time_et": session_start.strftime("%I:%M %p ET"),
                "minutes_until": round(mins_until),
                "range_formation_mins": config["range_formation_minutes"],
                "already_signaled": self.session_signals_today.get(session_type, False),
                "notes": config["notes"]
            })
        
        # Sort by minutes until
        sessions.sort(key=lambda x: x["minutes_until"])
        return sessions
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert strategy state to dictionary"""
        return {
            "name": "Session Breakout",
            "enabled": self.enabled,
            "current_session": self.active_session.value if self.active_session else None,
            "range_forming": self.range_forming,
            "current_range": {
                "high": self.session_range.high,
                "low": self.session_range.low,
                "size": self.session_range.range_size,
                "candles": self.session_range.candles_used
            } if self.session_range else None,
            "breakout_triggered": self.breakout_triggered,
            "upcoming_sessions": self.get_upcoming_sessions(),
            "last_signal": {
                "session": self.last_signal.session.value,
                "direction": self.last_signal.direction,
                "entry": self.last_signal.entry_price,
                "stop": self.last_signal.stop_loss,
                "target_1": self.last_signal.take_profit_1,
                "range_size": self.last_signal.range_size,
                "confidence": f"{self.last_signal.confidence:.0%}",
                "timestamp": self.last_signal.timestamp.isoformat()
            } if self.last_signal else None,
            "signal_count": len(self.signal_history)
        }


# Global instance
_session_strategy: Optional[SessionBreakoutStrategy] = None


def get_session_strategy() -> SessionBreakoutStrategy:
    """Get or create global session strategy instance"""
    global _session_strategy
    if _session_strategy is None:
        _session_strategy = SessionBreakoutStrategy()
    return _session_strategy
