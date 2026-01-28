"""
Funding Rate Scalper Strategy
Mean-reversion strategy that fades extreme funding rates

LOGIC:
- When funding is extremely positive (>0.05%), shorts are paying longs heavily
  → Market is overleveraged long → Fade with SHORT
- When funding is extremely negative (<-0.03%), longs are paying shorts
  → Market is overleveraged short → Fade with LONG
  
This strategy profits from the inevitable mean-reversion as overleveraged
positions get squeezed or funding becomes unsustainable.

TIMING:
- Best executed 15-30 minutes before funding settlement (every 8 hours on Bybit)
- Funding times: 00:00, 08:00, 16:00 UTC

RISK PROFILE: Conservative
- High win rate (~65-70%)
- Smaller moves, tighter stops
- Ideal for Breakout account funding phase
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FundingSignalType(str, Enum):
    """Types of funding signals"""
    EXTREME_POSITIVE = "extreme_positive"  # Fade with short
    EXTREME_NEGATIVE = "extreme_negative"  # Fade with long
    NEUTRAL = "neutral"


@dataclass
class FundingSignal:
    """Funding rate trading signal"""
    signal_type: FundingSignalType
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit_1: float  # Conservative target
    take_profit_2: float  # Extended target
    funding_rate: float
    next_funding_time: int
    time_to_funding_mins: float
    confidence: float  # 0-1
    reasoning: str
    timestamp: datetime


class FundingRateStrategy:
    """
    Funding Rate Mean Reversion Strategy
    
    Conservative strategy ideal for account funding phase.
    Trades against extreme funding to capture mean reversion.
    """
    
    # Funding thresholds (these are per-8h rates, not annualized)
    EXTREME_POSITIVE_THRESHOLD = 0.0005  # 0.05% per 8h = very bullish crowded
    EXTREME_NEGATIVE_THRESHOLD = -0.0003  # -0.03% per 8h = shorts crowded
    
    # Higher thresholds for stronger signals
    VERY_EXTREME_POSITIVE = 0.001  # 0.1% per 8h
    VERY_EXTREME_NEGATIVE = -0.0006  # -0.06% per 8h
    
    # Optimal trading window before funding (minutes)
    OPTIMAL_WINDOW_START = 30  # Start looking 30 mins before
    OPTIMAL_WINDOW_END = 5     # Stop 5 mins before (too close = volatile)
    
    # Risk parameters
    DEFAULT_STOP_PCT = 0.005   # 0.5% stop loss
    TARGET_1_MULTIPLIER = 1.5  # 1.5R first target
    TARGET_2_MULTIPLIER = 2.5  # 2.5R extended target
    
    def __init__(self):
        self.last_signal: Optional[FundingSignal] = None
        self.signal_history: List[FundingSignal] = []
        self.enabled = True
        
        # Cooldown tracking (avoid rapid signals)
        self.last_signal_time: Optional[datetime] = None
        self.cooldown_minutes = 60  # Minimum 1 hour between signals
    
    def analyze(
        self,
        current_price: float,
        funding_rate: float,
        next_funding_time: int,  # Unix timestamp in ms
        open_interest: float = None,
        recent_price_change_pct: float = None
    ) -> Optional[FundingSignal]:
        """
        Analyze current market conditions for funding rate signal
        
        Args:
            current_price: Current BTC price
            funding_rate: Current funding rate (e.g., 0.0005 = 0.05%)
            next_funding_time: Next funding settlement time (ms timestamp)
            open_interest: Current open interest (optional, for confirmation)
            recent_price_change_pct: Recent price move % (optional, for confirmation)
        
        Returns:
            FundingSignal if conditions met, None otherwise
        """
        
        if not self.enabled:
            return None
        
        # Check cooldown
        if self.last_signal_time:
            mins_since_last = (datetime.now(timezone.utc) - self.last_signal_time).total_seconds() / 60
            if mins_since_last < self.cooldown_minutes:
                return None
        
        # Calculate time to funding
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        time_to_funding_mins = (next_funding_time - now_ms) / 60000
        
        # Check if we're in optimal window
        in_window = self.OPTIMAL_WINDOW_START >= time_to_funding_mins >= self.OPTIMAL_WINDOW_END
        
        if not in_window:
            return None
        
        # Determine signal type
        signal_type = FundingSignalType.NEUTRAL
        direction = None
        confidence = 0.0
        reasoning_parts = []
        
        if funding_rate >= self.EXTREME_POSITIVE_THRESHOLD:
            signal_type = FundingSignalType.EXTREME_POSITIVE
            direction = "SHORT"
            
            # Calculate confidence based on how extreme
            if funding_rate >= self.VERY_EXTREME_POSITIVE:
                confidence = 0.85
                reasoning_parts.append(f"VERY extreme positive funding ({funding_rate*100:.4f}%)")
            else:
                confidence = 0.65
                reasoning_parts.append(f"Extreme positive funding ({funding_rate*100:.4f}%)")
            
            reasoning_parts.append("Longs paying significant premium - likely overleveraged")
            reasoning_parts.append("Mean reversion expected as funding becomes unsustainable")
            
        elif funding_rate <= self.EXTREME_NEGATIVE_THRESHOLD:
            signal_type = FundingSignalType.EXTREME_NEGATIVE
            direction = "LONG"
            
            if funding_rate <= self.VERY_EXTREME_NEGATIVE:
                confidence = 0.85
                reasoning_parts.append(f"VERY extreme negative funding ({funding_rate*100:.4f}%)")
            else:
                confidence = 0.65
                reasoning_parts.append(f"Extreme negative funding ({funding_rate*100:.4f}%)")
            
            reasoning_parts.append("Shorts paying longs - market oversold")
            reasoning_parts.append("Short squeeze potential as funding costs accumulate")
        
        else:
            return None  # No signal
        
        # Adjust confidence based on additional factors
        if recent_price_change_pct is not None:
            # If price has already moved significantly in our favor, reduce confidence
            # (might be too late)
            if direction == "LONG" and recent_price_change_pct > 2:
                confidence *= 0.8
                reasoning_parts.append("⚠️ Price already bounced - late entry risk")
            elif direction == "SHORT" and recent_price_change_pct < -2:
                confidence *= 0.8
                reasoning_parts.append("⚠️ Price already dropped - late entry risk")
            
            # If price moved against our direction, increase confidence
            # (better entry)
            elif direction == "LONG" and recent_price_change_pct < -1:
                confidence = min(confidence * 1.1, 0.9)
                reasoning_parts.append("✓ Price weakness = better long entry")
            elif direction == "SHORT" and recent_price_change_pct > 1:
                confidence = min(confidence * 1.1, 0.9)
                reasoning_parts.append("✓ Price strength = better short entry")
        
        # Calculate entry, stop, and targets
        stop_distance = current_price * self.DEFAULT_STOP_PCT
        
        if direction == "LONG":
            entry = current_price
            stop_loss = current_price - stop_distance
            take_profit_1 = current_price + (stop_distance * self.TARGET_1_MULTIPLIER)
            take_profit_2 = current_price + (stop_distance * self.TARGET_2_MULTIPLIER)
        else:  # SHORT
            entry = current_price
            stop_loss = current_price + stop_distance
            take_profit_1 = current_price - (stop_distance * self.TARGET_1_MULTIPLIER)
            take_profit_2 = current_price - (stop_distance * self.TARGET_2_MULTIPLIER)
        
        # Add timing context
        reasoning_parts.append(f"⏰ {time_to_funding_mins:.0f} mins until funding settlement")
        
        signal = FundingSignal(
            signal_type=signal_type,
            direction=direction,
            entry_price=round(entry, 2),
            stop_loss=round(stop_loss, 2),
            take_profit_1=round(take_profit_1, 2),
            take_profit_2=round(take_profit_2, 2),
            funding_rate=funding_rate,
            next_funding_time=next_funding_time,
            time_to_funding_mins=round(time_to_funding_mins, 1),
            confidence=round(confidence, 2),
            reasoning=" | ".join(reasoning_parts),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Update tracking
        self.last_signal = signal
        self.last_signal_time = signal.timestamp
        self.signal_history.append(signal)
        
        # Keep only last 100 signals
        if len(self.signal_history) > 100:
            self.signal_history = self.signal_history[-100:]
        
        logger.info(f"🎯 Funding Signal: {direction} @ ${entry:,.2f} | "
                   f"Funding: {funding_rate*100:.4f}% | Confidence: {confidence:.0%}")
        
        return signal
    
    def get_next_funding_windows(self) -> List[Dict[str, Any]]:
        """Get upcoming funding settlement times (UTC)"""
        from datetime import timedelta
        
        # Funding times are 00:00, 08:00, 16:00 UTC
        funding_hours = [0, 8, 16]
        
        now = datetime.now(timezone.utc)
        windows = []
        
        for i in range(3):  # Next 3 funding times
            target_date = now.date()
            
            for hour in funding_hours:
                funding_time = datetime(
                    target_date.year, target_date.month, target_date.day,
                    hour, 0, 0, tzinfo=timezone.utc
                )
                
                if funding_time > now:
                    optimal_start = funding_time - timedelta(minutes=self.OPTIMAL_WINDOW_START)
                    optimal_end = funding_time - timedelta(minutes=self.OPTIMAL_WINDOW_END)
                    
                    windows.append({
                        "funding_time": funding_time.isoformat(),
                        "optimal_window_start": optimal_start.isoformat(),
                        "optimal_window_end": optimal_end.isoformat(),
                        "minutes_until": (funding_time - now).total_seconds() / 60
                    })
                    
                    if len(windows) >= 3:
                        return windows
            
            target_date += timedelta(days=1)
        
        return windows
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert strategy state to dictionary"""
        return {
            "name": "Funding Rate Scalper",
            "enabled": self.enabled,
            "last_signal": {
                "direction": self.last_signal.direction,
                "entry": self.last_signal.entry_price,
                "stop": self.last_signal.stop_loss,
                "target_1": self.last_signal.take_profit_1,
                "target_2": self.last_signal.take_profit_2,
                "funding_rate": f"{self.last_signal.funding_rate*100:.4f}%",
                "confidence": f"{self.last_signal.confidence:.0%}",
                "timestamp": self.last_signal.timestamp.isoformat()
            } if self.last_signal else None,
            "upcoming_windows": self.get_next_funding_windows(),
            "thresholds": {
                "extreme_positive": f"{self.EXTREME_POSITIVE_THRESHOLD*100:.3f}%",
                "extreme_negative": f"{self.EXTREME_NEGATIVE_THRESHOLD*100:.3f}%"
            },
            "signal_count": len(self.signal_history)
        }


# Global instance
_funding_strategy: Optional[FundingRateStrategy] = None


def get_funding_strategy() -> FundingRateStrategy:
    """Get or create global funding strategy instance"""
    global _funding_strategy
    if _funding_strategy is None:
        _funding_strategy = FundingRateStrategy()
    return _funding_strategy
