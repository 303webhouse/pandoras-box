"""
Liquidation Cascade Reversal Strategy
Fades large liquidation events that create temporary price dislocations

LOGIC:
- Large liquidation cascades create forced selling/buying unrelated to market direction
- When >80% of liquidations are longs → market oversold, buy the dip
- When >80% of liquidations are shorts → market overbought, sell the rip
- Best entries come after the cascade exhausts (price stabilizes)

From BTC Bottom Signals framework:
"Bottom cannot form if shorts getting squeezed; >80% Long liqs = over-leveraged bulls ejected"

RISK PROFILE: Aggressive (counter-trend)
- Lower win rate (~45-50%)
- Excellent R:R (3:1 to 5:1)
- Requires discipline to wait for confirmation
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class LiquidationEventType(str, Enum):
    """Types of liquidation events"""
    LONG_CASCADE = "long_cascade"    # Heavy long liquidations → buy signal
    SHORT_SQUEEZE = "short_squeeze"  # Heavy short liquidations → sell signal


@dataclass
class LiquidationEvent:
    """Tracked liquidation cascade event"""
    event_type: LiquidationEventType
    total_volume_usd: float
    long_volume_usd: float
    short_volume_usd: float
    long_percentage: float
    peak_price: float
    bottom_price: float
    started_at: datetime
    ended_at: Optional[datetime] = None


@dataclass
class LiquidationSignal:
    """Liquidation reversal trading signal"""
    event_type: LiquidationEventType
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float  # Conservative
    take_profit_2: float  # Extended
    take_profit_3: float  # Full reversal
    liq_volume_usd: float
    long_liq_pct: float
    price_drop_pct: float  # Or rise for short squeeze
    confidence: float
    reasoning: str
    timestamp: datetime


class LiquidationReversalStrategy:
    """
    Liquidation Cascade Reversal Strategy
    
    Identifies exhaustion of liquidation cascades and trades the reversal.
    """
    
    # Liquidation thresholds
    MIN_CASCADE_VOLUME_USD = 5_000_000  # $5M minimum to be significant
    LARGE_CASCADE_VOLUME_USD = 20_000_000  # $20M is a large cascade
    EXTREME_CASCADE_VOLUME_USD = 50_000_000  # $50M is extreme
    
    # Composition thresholds
    LONG_DOMINANCE_THRESHOLD = 0.75  # 75% longs = buy signal
    SHORT_DOMINANCE_THRESHOLD = 0.75  # 75% shorts = sell signal
    
    # Confirmation requirements
    MIN_PRICE_MOVE_PCT = 0.02  # 2% minimum price move
    STABILIZATION_WINDOW_SECS = 60  # Price must stabilize for 60 seconds
    
    # Risk parameters
    STOP_BEYOND_CASCADE_PCT = 0.005  # Stop 0.5% beyond cascade extreme
    TARGET_1_PCT = 0.015  # 1.5% conservative target
    TARGET_2_PCT = 0.025  # 2.5% extended target
    TARGET_3_PCT = 0.04   # 4% full reversal target
    
    def __init__(self):
        self.enabled = True
        
        # Liquidation tracking (1 hour window)
        self.liquidations: deque = deque(maxlen=1000)
        self.window_seconds = 3600  # 1 hour
        
        # Current cascade tracking
        self.active_cascade: Optional[LiquidationEvent] = None
        self.cascade_start_price: Optional[float] = None
        self.cascade_extreme_price: Optional[float] = None  # Low for long liqs, high for short
        
        # Price stabilization tracking
        self.recent_prices: deque = deque(maxlen=60)  # Last 60 price updates
        self.stabilization_start: Optional[datetime] = None
        
        # Signal tracking
        self.last_signal: Optional[LiquidationSignal] = None
        self.signal_history: List[LiquidationSignal] = []
        
        # Cooldown
        self.last_signal_time: Optional[datetime] = None
        self.cooldown_minutes = 30
    
    def add_liquidation(self, liq_data: Dict):
        """
        Add a liquidation event to tracking
        
        Args:
            liq_data: Dict with price, size, side (Buy=short liq, Sell=long liq)
        """
        liq_record = {
            "price": liq_data.get("price", 0),
            "size_usd": liq_data.get("size", 0) * liq_data.get("price", 0),
            "side": liq_data.get("side", ""),  # Buy = short liq, Sell = long liq
            "is_long_liq": liq_data.get("side") == "Sell",
            "timestamp": datetime.now(timezone.utc)
        }
        
        self.liquidations.append(liq_record)
    
    def update_price(self, price: float):
        """Update price tracking for stabilization detection"""
        self.recent_prices.append({
            "price": price,
            "timestamp": datetime.now(timezone.utc)
        })
        
        # Track cascade extremes
        if self.active_cascade:
            if self.active_cascade.event_type == LiquidationEventType.LONG_CASCADE:
                if price < self.cascade_extreme_price:
                    self.cascade_extreme_price = price
                    self.stabilization_start = None  # Reset stabilization
            else:  # SHORT_SQUEEZE
                if price > self.cascade_extreme_price:
                    self.cascade_extreme_price = price
                    self.stabilization_start = None
    
    def _get_window_stats(self) -> Dict[str, Any]:
        """Get liquidation stats for the rolling window"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)
        
        # Filter to window
        window_liqs = [l for l in self.liquidations if l["timestamp"] > cutoff]
        
        if not window_liqs:
            return {
                "total_volume": 0,
                "long_volume": 0,
                "short_volume": 0,
                "long_pct": 0.5,
                "count": 0
            }
        
        long_volume = sum(l["size_usd"] for l in window_liqs if l["is_long_liq"])
        short_volume = sum(l["size_usd"] for l in window_liqs if not l["is_long_liq"])
        total_volume = long_volume + short_volume
        
        return {
            "total_volume": total_volume,
            "long_volume": long_volume,
            "short_volume": short_volume,
            "long_pct": long_volume / total_volume if total_volume > 0 else 0.5,
            "count": len(window_liqs)
        }
    
    def _check_price_stabilization(self) -> bool:
        """Check if price has stabilized after cascade"""
        if len(self.recent_prices) < 30:
            return False
        
        # Get prices from last 30 seconds
        now = datetime.now(timezone.utc)
        recent = [p for p in self.recent_prices 
                  if (now - p["timestamp"]).total_seconds() < 30]
        
        if len(recent) < 10:
            return False
        
        prices = [p["price"] for p in recent]
        price_range = max(prices) - min(prices)
        avg_price = sum(prices) / len(prices)
        
        # Stabilized if range is less than 0.2% in last 30 seconds
        range_pct = price_range / avg_price
        return range_pct < 0.002
    
    def analyze(
        self,
        current_price: float,
        liquidation_data: Optional[Dict] = None
    ) -> Optional[LiquidationSignal]:
        """
        Analyze current conditions for liquidation reversal signal
        
        Args:
            current_price: Current BTC price
            liquidation_data: Latest liquidation event (if any)
        
        Returns:
            LiquidationSignal if conditions met, None otherwise
        """
        
        if not self.enabled:
            return None
        
        # Add any new liquidation
        if liquidation_data:
            self.add_liquidation(liquidation_data)
        
        # Update price tracking
        self.update_price(current_price)
        
        # Check cooldown
        if self.last_signal_time:
            mins_since = (datetime.now(timezone.utc) - self.last_signal_time).total_seconds() / 60
            if mins_since < self.cooldown_minutes:
                return None
        
        # Get window stats
        stats = self._get_window_stats()
        
        # Check if cascade is forming/active
        if stats["total_volume"] >= self.MIN_CASCADE_VOLUME_USD:
            
            # Detect cascade type
            event_type = None
            
            if stats["long_pct"] >= self.LONG_DOMINANCE_THRESHOLD:
                event_type = LiquidationEventType.LONG_CASCADE
            elif stats["long_pct"] <= (1 - self.SHORT_DOMINANCE_THRESHOLD):
                event_type = LiquidationEventType.SHORT_SQUEEZE
            
            if event_type and not self.active_cascade:
                # New cascade detected
                self.active_cascade = LiquidationEvent(
                    event_type=event_type,
                    total_volume_usd=stats["total_volume"],
                    long_volume_usd=stats["long_volume"],
                    short_volume_usd=stats["short_volume"],
                    long_percentage=stats["long_pct"],
                    peak_price=current_price,
                    bottom_price=current_price,
                    started_at=datetime.now(timezone.utc)
                )
                self.cascade_start_price = current_price
                self.cascade_extreme_price = current_price
                
                logger.info(f"🌊 Liquidation cascade detected: {event_type.value} | "
                           f"Volume: ${stats['total_volume']/1e6:.1f}M | "
                           f"Long%: {stats['long_pct']:.0%}")
                
                return None  # Wait for confirmation
            
            elif self.active_cascade:
                # Update active cascade
                self.active_cascade.total_volume_usd = stats["total_volume"]
                self.active_cascade.long_volume_usd = stats["long_volume"]
                self.active_cascade.short_volume_usd = stats["short_volume"]
                self.active_cascade.long_percentage = stats["long_pct"]
        
        # Check for signal conditions
        if not self.active_cascade or not self.cascade_start_price:
            return None
        
        # Calculate price move
        if self.active_cascade.event_type == LiquidationEventType.LONG_CASCADE:
            price_move_pct = (self.cascade_start_price - self.cascade_extreme_price) / self.cascade_start_price
        else:
            price_move_pct = (self.cascade_extreme_price - self.cascade_start_price) / self.cascade_start_price
        
        # Need minimum price move
        if price_move_pct < self.MIN_PRICE_MOVE_PCT:
            return None
        
        # Check price stabilization
        if not self._check_price_stabilization():
            return None
        
        # Generate signal
        stats = self._get_window_stats()
        
        # Calculate confidence based on cascade size
        base_confidence = 0.5
        
        if stats["total_volume"] >= self.EXTREME_CASCADE_VOLUME_USD:
            base_confidence = 0.75
        elif stats["total_volume"] >= self.LARGE_CASCADE_VOLUME_USD:
            base_confidence = 0.65
        
        # Adjust for composition extremity
        composition_factor = abs(stats["long_pct"] - 0.5) * 2  # 0 to 1
        confidence = min(base_confidence + (composition_factor * 0.15), 0.9)
        
        # Build signal
        reasoning_parts = []
        
        if self.active_cascade.event_type == LiquidationEventType.LONG_CASCADE:
            direction = "LONG"
            reasoning_parts.append(f"🔴 LONG CASCADE EXHAUSTION - {stats['long_pct']:.0%} long liqs")
            reasoning_parts.append(f"${stats['total_volume']/1e6:.1f}M liquidated")
            reasoning_parts.append(f"Price dropped {price_move_pct*100:.1f}% - now stabilizing")
            reasoning_parts.append("Over-leveraged bulls ejected → bounce expected")
            
            entry = current_price
            stop_loss = self.cascade_extreme_price * (1 - self.STOP_BEYOND_CASCADE_PCT)
            tp1 = entry * (1 + self.TARGET_1_PCT)
            tp2 = entry * (1 + self.TARGET_2_PCT)
            tp3 = entry * (1 + self.TARGET_3_PCT)
            
        else:  # SHORT_SQUEEZE
            direction = "SHORT"
            reasoning_parts.append(f"🟢 SHORT SQUEEZE EXHAUSTION - {(1-stats['long_pct']):.0%} short liqs")
            reasoning_parts.append(f"${stats['total_volume']/1e6:.1f}M liquidated")
            reasoning_parts.append(f"Price pumped {price_move_pct*100:.1f}% - now stabilizing")
            reasoning_parts.append("Over-leveraged shorts ejected → pullback expected")
            
            entry = current_price
            stop_loss = self.cascade_extreme_price * (1 + self.STOP_BEYOND_CASCADE_PCT)
            tp1 = entry * (1 - self.TARGET_1_PCT)
            tp2 = entry * (1 - self.TARGET_2_PCT)
            tp3 = entry * (1 - self.TARGET_3_PCT)
        
        signal = LiquidationSignal(
            event_type=self.active_cascade.event_type,
            direction=direction,
            entry_price=round(entry, 2),
            stop_loss=round(stop_loss, 2),
            take_profit_1=round(tp1, 2),
            take_profit_2=round(tp2, 2),
            take_profit_3=round(tp3, 2),
            liq_volume_usd=round(stats["total_volume"], 2),
            long_liq_pct=round(stats["long_pct"] * 100, 1),
            price_drop_pct=round(price_move_pct * 100, 2),
            confidence=round(confidence, 2),
            reasoning=" | ".join(reasoning_parts),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Update tracking
        self.last_signal = signal
        self.last_signal_time = signal.timestamp
        self.signal_history.append(signal)
        
        # Reset cascade tracking
        self.active_cascade.ended_at = datetime.now(timezone.utc)
        self.active_cascade = None
        self.cascade_start_price = None
        self.cascade_extreme_price = None
        
        if len(self.signal_history) > 100:
            self.signal_history = self.signal_history[-100:]
        
        logger.info(f"🎯 Liquidation Reversal: {direction} @ ${entry:,.2f} | "
                   f"Volume: ${stats['total_volume']/1e6:.1f}M | "
                   f"Confidence: {confidence:.0%}")
        
        return signal
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Get current liquidation statistics"""
        stats = self._get_window_stats()
        
        return {
            "window_hours": self.window_seconds / 3600,
            "total_volume_usd": round(stats["total_volume"], 2),
            "long_volume_usd": round(stats["long_volume"], 2),
            "short_volume_usd": round(stats["short_volume"], 2),
            "long_percentage": round(stats["long_pct"] * 100, 1),
            "liquidation_count": stats["count"],
            "cascade_active": self.active_cascade is not None,
            "cascade_type": self.active_cascade.event_type.value if self.active_cascade else None
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert strategy state to dictionary"""
        stats = self._get_window_stats()
        
        return {
            "name": "Liquidation Cascade Reversal",
            "enabled": self.enabled,
            "current_stats": self.get_current_stats(),
            "thresholds": {
                "min_cascade_usd": f"${self.MIN_CASCADE_VOLUME_USD/1e6:.0f}M",
                "large_cascade_usd": f"${self.LARGE_CASCADE_VOLUME_USD/1e6:.0f}M",
                "long_dominance": f"{self.LONG_DOMINANCE_THRESHOLD:.0%}",
                "short_dominance": f"{self.SHORT_DOMINANCE_THRESHOLD:.0%}"
            },
            "active_cascade": {
                "type": self.active_cascade.event_type.value,
                "volume": f"${self.active_cascade.total_volume_usd/1e6:.1f}M",
                "long_pct": f"{self.active_cascade.long_percentage:.0%}",
                "started": self.active_cascade.started_at.isoformat()
            } if self.active_cascade else None,
            "last_signal": {
                "type": self.last_signal.event_type.value,
                "direction": self.last_signal.direction,
                "entry": self.last_signal.entry_price,
                "stop": self.last_signal.stop_loss,
                "target_1": self.last_signal.take_profit_1,
                "liq_volume": f"${self.last_signal.liq_volume_usd/1e6:.1f}M",
                "confidence": f"{self.last_signal.confidence:.0%}",
                "timestamp": self.last_signal.timestamp.isoformat()
            } if self.last_signal else None,
            "signal_count": len(self.signal_history)
        }


# Global instance
_liq_strategy: Optional[LiquidationReversalStrategy] = None


def get_liquidation_strategy() -> LiquidationReversalStrategy:
    """Get or create global liquidation strategy instance"""
    global _liq_strategy
    if _liq_strategy is None:
        _liq_strategy = LiquidationReversalStrategy()
    return _liq_strategy
