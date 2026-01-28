"""
VWAP Reclaim/Reject Strategy
Intraday strategy trading price interaction with Volume Weighted Average Price

LOGIC:
- VWAP acts as "fair value" for the session
- Price reclaiming VWAP from below = bullish (buyers stepping in at value)
- Price rejecting at VWAP from below = bearish (sellers defending value)
- Price losing VWAP from above = bearish (buyers failing to hold value)
- Price bouncing off VWAP from above = bullish (buyers defending value)

CONFIRMATION REQUIREMENTS:
- Volume confirmation (above average volume on the move)
- Orderbook imbalance confirmation
- Clean price action (not choppy around VWAP)

RISK PROFILE: Moderate
- Win rate ~55-60%
- Good R:R potential (2:1 to 3:1)
- Requires active management
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class VWAPSignalType(str, Enum):
    """Types of VWAP signals"""
    RECLAIM_LONG = "reclaim_long"      # Price reclaims VWAP from below
    REJECT_SHORT = "reject_short"       # Price rejects at VWAP from below
    BOUNCE_LONG = "bounce_long"         # Price bounces off VWAP from above
    LOSE_SHORT = "lose_short"           # Price loses VWAP from above


@dataclass
class VWAPSignal:
    """VWAP trading signal"""
    signal_type: VWAPSignalType
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    vwap_price: float
    distance_from_vwap_pct: float
    volume_confirmation: bool
    orderbook_confirmation: bool
    confidence: float
    reasoning: str
    timestamp: datetime


class VWAPStrategy:
    """
    VWAP-based Intraday Strategy
    
    Trades price interaction with session VWAP using volume
    and orderbook confirmation.
    """
    
    # Distance thresholds (as % from VWAP)
    MIN_DISTANCE_FOR_TRADE = 0.001   # Must be at least 0.1% away
    MAX_DISTANCE_FOR_TRADE = 0.005   # Not more than 0.5% away (too extended)
    
    # Confirmation thresholds
    VOLUME_MULTIPLIER_THRESHOLD = 1.3  # 30% above average
    ORDERBOOK_IMBALANCE_THRESHOLD = 0.15  # 15% imbalance
    
    # Trade management
    STOP_BEYOND_VWAP_PCT = 0.003  # Stop 0.3% beyond VWAP
    TARGET_1_ATR_MULT = 1.0      # First target at 1 ATR
    TARGET_2_ATR_MULT = 2.0      # Second target at 2 ATR
    
    # State tracking
    PRICE_HISTORY_SIZE = 20  # Track last 20 price updates
    
    def __init__(self):
        self.enabled = True
        self.last_signal: Optional[VWAPSignal] = None
        self.signal_history: List[VWAPSignal] = []
        
        # Price state tracking
        self.price_history: deque = deque(maxlen=self.PRICE_HISTORY_SIZE)
        self.was_above_vwap: Optional[bool] = None
        self.cross_detected_at: Optional[datetime] = None
        
        # Volume tracking
        self.recent_volumes: deque = deque(maxlen=50)
        self.avg_volume: float = 0
        
        # Cooldown
        self.last_signal_time: Optional[datetime] = None
        self.cooldown_minutes = 15  # Shorter cooldown for intraday
        
        # ATR tracking (for targets)
        self.current_atr: float = 0
    
    def update_price(self, price: float, volume: float = None):
        """Update price history for cross detection"""
        self.price_history.append({
            "price": price,
            "timestamp": datetime.now(timezone.utc)
        })
        
        if volume:
            self.recent_volumes.append(volume)
            if len(self.recent_volumes) >= 10:
                self.avg_volume = sum(self.recent_volumes) / len(self.recent_volumes)
    
    def update_atr(self, atr_value: float):
        """Update ATR for target calculation"""
        self.current_atr = atr_value
    
    def analyze(
        self,
        current_price: float,
        vwap_price: float,
        current_volume: float = None,
        orderbook_imbalance: float = 0,  # -1 to 1
        recent_high: float = None,
        recent_low: float = None
    ) -> Optional[VWAPSignal]:
        """
        Analyze current conditions for VWAP-based signal
        
        Args:
            current_price: Current BTC price
            vwap_price: Current session VWAP
            current_volume: Current volume (for confirmation)
            orderbook_imbalance: -1 (ask heavy) to 1 (bid heavy)
            recent_high: Recent swing high (for context)
            recent_low: Recent swing low (for context)
        
        Returns:
            VWAPSignal if conditions met, None otherwise
        """
        
        if not self.enabled or vwap_price <= 0:
            return None
        
        # Check cooldown
        if self.last_signal_time:
            mins_since = (datetime.now(timezone.utc) - self.last_signal_time).total_seconds() / 60
            if mins_since < self.cooldown_minutes:
                return None
        
        # Update price tracking
        self.update_price(current_price, current_volume)
        
        # Calculate distance from VWAP
        distance_pct = (current_price - vwap_price) / vwap_price
        abs_distance_pct = abs(distance_pct)
        
        # Check if price is in tradeable range
        if abs_distance_pct < self.MIN_DISTANCE_FOR_TRADE:
            return None  # Too close, likely to chop
        if abs_distance_pct > self.MAX_DISTANCE_FOR_TRADE:
            return None  # Too extended
        
        # Determine current position relative to VWAP
        is_above_vwap = current_price > vwap_price
        
        # Detect VWAP cross
        signal_type = None
        direction = None
        reasoning_parts = []
        
        if self.was_above_vwap is not None:
            if not self.was_above_vwap and is_above_vwap:
                # Crossed above VWAP (reclaim)
                signal_type = VWAPSignalType.RECLAIM_LONG
                direction = "LONG"
                reasoning_parts.append("Price RECLAIMED VWAP from below")
                reasoning_parts.append("Buyers stepped in at fair value")
                
            elif self.was_above_vwap and not is_above_vwap:
                # Crossed below VWAP (lose)
                signal_type = VWAPSignalType.LOSE_SHORT
                direction = "SHORT"
                reasoning_parts.append("Price LOST VWAP from above")
                reasoning_parts.append("Buyers failed to hold fair value")
        
        # Also check for bounce/reject at VWAP (price touched but didn't cross)
        if signal_type is None and len(self.price_history) >= 3:
            recent_prices = [p["price"] for p in list(self.price_history)[-3:]]
            
            # Bounce: was above, touched near VWAP, bounced back up
            if is_above_vwap and min(recent_prices) < vwap_price * 1.002:
                touches_vwap = any(abs(p - vwap_price) / vwap_price < 0.001 for p in recent_prices)
                if touches_vwap and current_price > recent_prices[-2]:
                    signal_type = VWAPSignalType.BOUNCE_LONG
                    direction = "LONG"
                    reasoning_parts.append("Price BOUNCED off VWAP support")
                    reasoning_parts.append("Buyers defending fair value")
            
            # Reject: was below, touched near VWAP, rejected back down
            elif not is_above_vwap and max(recent_prices) > vwap_price * 0.998:
                touches_vwap = any(abs(p - vwap_price) / vwap_price < 0.001 for p in recent_prices)
                if touches_vwap and current_price < recent_prices[-2]:
                    signal_type = VWAPSignalType.REJECT_SHORT
                    direction = "SHORT"
                    reasoning_parts.append("Price REJECTED at VWAP resistance")
                    reasoning_parts.append("Sellers defending fair value")
        
        # Update state
        self.was_above_vwap = is_above_vwap
        
        if signal_type is None:
            return None
        
        # Check confirmations
        volume_confirmation = False
        if current_volume and self.avg_volume > 0:
            volume_ratio = current_volume / self.avg_volume
            volume_confirmation = volume_ratio >= self.VOLUME_MULTIPLIER_THRESHOLD
            if volume_confirmation:
                reasoning_parts.append(f"✓ Volume {volume_ratio:.1f}x average (confirmed)")
            else:
                reasoning_parts.append(f"⚠️ Volume {volume_ratio:.1f}x (weak)")
        
        orderbook_confirmation = False
        if direction == "LONG" and orderbook_imbalance >= self.ORDERBOOK_IMBALANCE_THRESHOLD:
            orderbook_confirmation = True
            reasoning_parts.append(f"✓ Bid-heavy orderbook +{orderbook_imbalance:.0%}")
        elif direction == "SHORT" and orderbook_imbalance <= -self.ORDERBOOK_IMBALANCE_THRESHOLD:
            orderbook_confirmation = True
            reasoning_parts.append(f"✓ Ask-heavy orderbook {orderbook_imbalance:.0%}")
        else:
            reasoning_parts.append(f"⚠️ Orderbook neutral ({orderbook_imbalance:.0%})")
        
        # Calculate confidence
        base_confidence = 0.5
        if volume_confirmation:
            base_confidence += 0.15
        if orderbook_confirmation:
            base_confidence += 0.15
        
        # Boost for reclaim/lose (stronger signals than bounce/reject)
        if signal_type in [VWAPSignalType.RECLAIM_LONG, VWAPSignalType.LOSE_SHORT]:
            base_confidence += 0.1
        
        confidence = min(base_confidence, 0.9)
        
        # Calculate entry, stop, targets
        # Use ATR if available, otherwise use percentage-based
        if self.current_atr > 0:
            stop_distance = self.current_atr * 0.5
            target_1_distance = self.current_atr * self.TARGET_1_ATR_MULT
            target_2_distance = self.current_atr * self.TARGET_2_ATR_MULT
        else:
            stop_distance = current_price * self.STOP_BEYOND_VWAP_PCT
            target_1_distance = stop_distance * 2
            target_2_distance = stop_distance * 3
        
        if direction == "LONG":
            entry = current_price
            stop_loss = min(vwap_price - stop_distance, current_price - stop_distance)
            take_profit_1 = current_price + target_1_distance
            take_profit_2 = current_price + target_2_distance
        else:  # SHORT
            entry = current_price
            stop_loss = max(vwap_price + stop_distance, current_price + stop_distance)
            take_profit_1 = current_price - target_1_distance
            take_profit_2 = current_price - target_2_distance
        
        # Add VWAP context
        reasoning_parts.append(f"VWAP: ${vwap_price:,.2f} | Distance: {distance_pct*100:.2f}%")
        
        signal = VWAPSignal(
            signal_type=signal_type,
            direction=direction,
            entry_price=round(entry, 2),
            stop_loss=round(stop_loss, 2),
            take_profit_1=round(take_profit_1, 2),
            take_profit_2=round(take_profit_2, 2),
            vwap_price=round(vwap_price, 2),
            distance_from_vwap_pct=round(distance_pct * 100, 3),
            volume_confirmation=volume_confirmation,
            orderbook_confirmation=orderbook_confirmation,
            confidence=round(confidence, 2),
            reasoning=" | ".join(reasoning_parts),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Update tracking
        self.last_signal = signal
        self.last_signal_time = signal.timestamp
        self.signal_history.append(signal)
        
        if len(self.signal_history) > 100:
            self.signal_history = self.signal_history[-100:]
        
        logger.info(f"🎯 VWAP Signal: {signal_type.value} {direction} @ ${entry:,.2f} | "
                   f"VWAP: ${vwap_price:,.2f} | Confidence: {confidence:.0%}")
        
        return signal
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert strategy state to dictionary"""
        return {
            "name": "VWAP Reclaim/Reject",
            "enabled": self.enabled,
            "current_state": {
                "above_vwap": self.was_above_vwap,
                "avg_volume": round(self.avg_volume, 2) if self.avg_volume else None,
                "current_atr": round(self.current_atr, 2) if self.current_atr else None
            },
            "last_signal": {
                "type": self.last_signal.signal_type.value,
                "direction": self.last_signal.direction,
                "entry": self.last_signal.entry_price,
                "stop": self.last_signal.stop_loss,
                "target_1": self.last_signal.take_profit_1,
                "vwap": self.last_signal.vwap_price,
                "confidence": f"{self.last_signal.confidence:.0%}",
                "timestamp": self.last_signal.timestamp.isoformat()
            } if self.last_signal else None,
            "signal_count": len(self.signal_history)
        }


# Global instance
_vwap_strategy: Optional[VWAPStrategy] = None


def get_vwap_strategy() -> VWAPStrategy:
    """Get or create global VWAP strategy instance"""
    global _vwap_strategy
    if _vwap_strategy is None:
        _vwap_strategy = VWAPStrategy()
    return _vwap_strategy
