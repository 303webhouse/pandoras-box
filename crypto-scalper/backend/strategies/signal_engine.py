"""
Signal Engine - Central Orchestrator
Coordinates all trading strategies and generates unified, actionable signals

This is the brain of the crypto scalper. It:
1. Receives real-time data from Bybit
2. Passes data to all enabled strategies
3. Validates signals against risk management
4. Ranks and prioritizes signals
5. Broadcasts actionable alerts

SIGNAL PRIORITY (for Breakout account funding):
1. Funding Rate (Conservative) - High win rate, smaller gains
2. VWAP Reclaim/Reject (Moderate) - Good R:R, requires judgment
3. Session Breakout (Moderate) - Excellent R:R, patience required
4. Liquidation Reversal (Aggressive) - Counter-trend, higher risk
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum

from .funding_rate import FundingRateStrategy, FundingSignal, get_funding_strategy
from .vwap_strategy import VWAPStrategy, VWAPSignal, get_vwap_strategy
from .session_breakout import SessionBreakoutStrategy, BreakoutSignal, get_session_strategy
from .liquidation_reversal import LiquidationReversalStrategy, LiquidationSignal, get_liquidation_strategy

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    """Available strategy types"""
    FUNDING_RATE = "funding_rate"
    VWAP = "vwap"
    SESSION_BREAKOUT = "session_breakout"
    LIQUIDATION_REVERSAL = "liquidation_reversal"


class SignalPriority(str, Enum):
    """Signal priority levels"""
    HIGH = "high"      # High confidence, good R:R, take immediately
    MEDIUM = "medium"  # Good setup, but needs confirmation
    LOW = "low"        # Valid signal, but lower confidence


@dataclass
class UnifiedSignal:
    """Unified signal format from any strategy"""
    id: str
    strategy: StrategyType
    direction: str  # "LONG" or "SHORT"
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: Optional[float]
    confidence: float
    priority: SignalPriority
    risk_reward_ratio: float
    reasoning: str
    position_size_btc: Optional[float]
    position_value_usd: Optional[float]
    risk_amount_usd: Optional[float]
    timestamp: datetime
    expires_at: Optional[datetime]
    metadata: Dict[str, Any]


class SignalEngine:
    """
    Central signal orchestration engine
    Coordinates strategies, validates with risk management, and broadcasts signals
    """
    
    def __init__(self):
        # Initialize strategies
        self.funding_strategy = get_funding_strategy()
        self.vwap_strategy = get_vwap_strategy()
        self.session_strategy = get_session_strategy()
        self.liquidation_strategy = get_liquidation_strategy()
        
        # Strategy enable/disable
        self.enabled_strategies: Dict[StrategyType, bool] = {
            StrategyType.FUNDING_RATE: True,
            StrategyType.VWAP: True,
            StrategyType.SESSION_BREAKOUT: True,
            StrategyType.LIQUIDATION_REVERSAL: True
        }
        
        # Signal tracking
        self.active_signals: List[UnifiedSignal] = []
        self.signal_history: List[UnifiedSignal] = []
        self.max_active_signals = 5
        
        # Callbacks for signal broadcast
        self.on_new_signal: Optional[Callable] = None
        self.on_signal_expired: Optional[Callable] = None
        
        # Risk manager reference (will be set externally)
        self.position_manager = None
        
        # Signal counter for IDs
        self._signal_counter = 0
        
        # Last price for calculations
        self.last_price: float = 0
    
    def set_position_manager(self, pm):
        """Set reference to position manager for risk calculations"""
        self.position_manager = pm
    
    def set_signal_callback(self, callback: Callable):
        """Set callback for new signals"""
        self.on_new_signal = callback
    
    def enable_strategy(self, strategy: StrategyType, enabled: bool = True):
        """Enable or disable a strategy"""
        self.enabled_strategies[strategy] = enabled
        logger.info(f"Strategy {strategy.value}: {'enabled' if enabled else 'disabled'}")
    
    def _generate_signal_id(self, strategy: StrategyType) -> str:
        """Generate unique signal ID"""
        self._signal_counter += 1
        timestamp = datetime.now().strftime("%H%M%S")
        return f"{strategy.value[:3].upper()}_{timestamp}_{self._signal_counter}"
    
    def _calculate_risk_reward(self, entry: float, stop: float, target: float) -> float:
        """Calculate risk/reward ratio"""
        risk = abs(entry - stop)
        reward = abs(target - entry)
        if risk > 0:
            return round(reward / risk, 2)
        return 0
    
    def _determine_priority(self, confidence: float, rr_ratio: float, strategy: StrategyType) -> SignalPriority:
        """Determine signal priority based on confidence and R:R"""
        
        # Base score
        score = confidence * 0.6 + min(rr_ratio / 5, 1) * 0.4
        
        # Strategy adjustment (funding rate gets priority for conservative phase)
        if strategy == StrategyType.FUNDING_RATE:
            score += 0.1
        elif strategy == StrategyType.LIQUIDATION_REVERSAL:
            score -= 0.1  # Counter-trend is riskier
        
        if score >= 0.75:
            return SignalPriority.HIGH
        elif score >= 0.55:
            return SignalPriority.MEDIUM
        else:
            return SignalPriority.LOW
    
    def _validate_with_risk_manager(self, signal: UnifiedSignal) -> UnifiedSignal:
        """Validate signal with position manager and calculate position size"""
        
        if not self.position_manager:
            return signal
        
        # Calculate position size
        result = self.position_manager.calculate_position_size(
            entry_price=signal.entry_price,
            stop_loss_price=signal.stop_loss,
            take_profit_price=signal.take_profit_1,
            leverage=1.0,  # Start with 1x, can increase based on confidence
            signal_confidence=signal.confidence
        )
        
        if result.get("approved"):
            signal.position_size_btc = result.get("position_size_btc")
            signal.position_value_usd = result.get("position_value_usd")
            signal.risk_amount_usd = result.get("risk_amount_usd")
            
            # Add warnings to reasoning if any
            warnings = result.get("warnings", [])
            if warnings:
                signal.reasoning += " | " + " | ".join(warnings)
        else:
            # Not approved - add reason to metadata
            signal.metadata["risk_rejected"] = True
            signal.metadata["rejection_reason"] = result.get("reason", "Unknown")
            signal.priority = SignalPriority.LOW  # Downgrade priority
        
        return signal
    
    def _create_unified_signal(
        self,
        strategy_type: StrategyType,
        direction: str,
        entry: float,
        stop: float,
        tp1: float,
        tp2: float,
        tp3: Optional[float],
        confidence: float,
        reasoning: str,
        metadata: Dict[str, Any]
    ) -> UnifiedSignal:
        """Create a unified signal from strategy output"""
        
        rr_ratio = self._calculate_risk_reward(entry, stop, tp1)
        priority = self._determine_priority(confidence, rr_ratio, strategy_type)
        
        signal = UnifiedSignal(
            id=self._generate_signal_id(strategy_type),
            strategy=strategy_type,
            direction=direction,
            symbol="BTCUSDT",
            entry_price=entry,
            stop_loss=stop,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            confidence=confidence,
            priority=priority,
            risk_reward_ratio=rr_ratio,
            reasoning=reasoning,
            position_size_btc=None,
            position_value_usd=None,
            risk_amount_usd=None,
            timestamp=datetime.now(timezone.utc),
            expires_at=None,
            metadata=metadata
        )
        
        # Validate with risk manager
        signal = self._validate_with_risk_manager(signal)
        
        return signal
    
    async def process_price_update(
        self,
        price: float,
        vwap: float,
        volume: float,
        orderbook_imbalance: float
    ) -> List[UnifiedSignal]:
        """
        Process a price update through all enabled strategies
        
        Args:
            price: Current BTC price
            vwap: Current session VWAP
            volume: Current volume
            orderbook_imbalance: -1 to 1 orderbook imbalance
        
        Returns:
            List of new signals generated
        """
        
        self.last_price = price
        new_signals = []
        
        # Update VWAP strategy price tracking
        if self.enabled_strategies[StrategyType.VWAP]:
            self.vwap_strategy.update_price(price, volume)
        
        # Update liquidation strategy price
        if self.enabled_strategies[StrategyType.LIQUIDATION_REVERSAL]:
            self.liquidation_strategy.update_price(price)
        
        # Check VWAP strategy
        if self.enabled_strategies[StrategyType.VWAP]:
            vwap_signal = self.vwap_strategy.analyze(
                current_price=price,
                vwap_price=vwap,
                current_volume=volume,
                orderbook_imbalance=orderbook_imbalance
            )
            
            if vwap_signal:
                unified = self._create_unified_signal(
                    strategy_type=StrategyType.VWAP,
                    direction=vwap_signal.direction,
                    entry=vwap_signal.entry_price,
                    stop=vwap_signal.stop_loss,
                    tp1=vwap_signal.take_profit_1,
                    tp2=vwap_signal.take_profit_2,
                    tp3=None,
                    confidence=vwap_signal.confidence,
                    reasoning=vwap_signal.reasoning,
                    metadata={
                        "signal_type": vwap_signal.signal_type.value,
                        "vwap_price": vwap_signal.vwap_price,
                        "volume_confirmed": vwap_signal.volume_confirmation,
                        "orderbook_confirmed": vwap_signal.orderbook_confirmation
                    }
                )
                new_signals.append(unified)
        
        # Check session breakout strategy
        if self.enabled_strategies[StrategyType.SESSION_BREAKOUT]:
            session_signal = self.session_strategy.analyze(
                current_price=price,
                volume=volume,
                orderbook_imbalance=orderbook_imbalance
            )
            
            if session_signal:
                unified = self._create_unified_signal(
                    strategy_type=StrategyType.SESSION_BREAKOUT,
                    direction=session_signal.direction,
                    entry=session_signal.entry_price,
                    stop=session_signal.stop_loss,
                    tp1=session_signal.take_profit_1,
                    tp2=session_signal.take_profit_2,
                    tp3=None,
                    confidence=session_signal.confidence,
                    reasoning=session_signal.reasoning,
                    metadata={
                        "session": session_signal.session.value,
                        "range_high": session_signal.range_high,
                        "range_low": session_signal.range_low,
                        "range_size": session_signal.range_size,
                        "breakout_strength": session_signal.breakout_strength
                    }
                )
                new_signals.append(unified)
        
        # Check liquidation strategy
        if self.enabled_strategies[StrategyType.LIQUIDATION_REVERSAL]:
            liq_signal = self.liquidation_strategy.analyze(current_price=price)
            
            if liq_signal:
                unified = self._create_unified_signal(
                    strategy_type=StrategyType.LIQUIDATION_REVERSAL,
                    direction=liq_signal.direction,
                    entry=liq_signal.entry_price,
                    stop=liq_signal.stop_loss,
                    tp1=liq_signal.take_profit_1,
                    tp2=liq_signal.take_profit_2,
                    tp3=liq_signal.take_profit_3,
                    confidence=liq_signal.confidence,
                    reasoning=liq_signal.reasoning,
                    metadata={
                        "event_type": liq_signal.event_type.value,
                        "liq_volume_usd": liq_signal.liq_volume_usd,
                        "long_liq_pct": liq_signal.long_liq_pct,
                        "price_move_pct": liq_signal.price_drop_pct
                    }
                )
                new_signals.append(unified)
        
        # Process new signals
        for signal in new_signals:
            await self._add_signal(signal)
        
        return new_signals
    
    async def process_funding_update(
        self,
        price: float,
        funding_rate: float,
        next_funding_time: int,
        open_interest: float = None
    ) -> Optional[UnifiedSignal]:
        """Process funding rate update"""
        
        if not self.enabled_strategies[StrategyType.FUNDING_RATE]:
            return None
        
        funding_signal = self.funding_strategy.analyze(
            current_price=price,
            funding_rate=funding_rate,
            next_funding_time=next_funding_time,
            open_interest=open_interest
        )
        
        if funding_signal:
            unified = self._create_unified_signal(
                strategy_type=StrategyType.FUNDING_RATE,
                direction=funding_signal.direction,
                entry=funding_signal.entry_price,
                stop=funding_signal.stop_loss,
                tp1=funding_signal.take_profit_1,
                tp2=funding_signal.take_profit_2,
                tp3=None,
                confidence=funding_signal.confidence,
                reasoning=funding_signal.reasoning,
                metadata={
                    "signal_type": funding_signal.signal_type.value,
                    "funding_rate": funding_signal.funding_rate,
                    "time_to_funding": funding_signal.time_to_funding_mins
                }
            )
            
            await self._add_signal(unified)
            return unified
        
        return None
    
    async def process_liquidation(
        self,
        liq_data: Dict,
        current_price: float
    ) -> Optional[UnifiedSignal]:
        """Process a liquidation event"""
        
        if not self.enabled_strategies[StrategyType.LIQUIDATION_REVERSAL]:
            return None
        
        liq_signal = self.liquidation_strategy.analyze(
            current_price=current_price,
            liquidation_data=liq_data
        )
        
        if liq_signal:
            unified = self._create_unified_signal(
                strategy_type=StrategyType.LIQUIDATION_REVERSAL,
                direction=liq_signal.direction,
                entry=liq_signal.entry_price,
                stop=liq_signal.stop_loss,
                tp1=liq_signal.take_profit_1,
                tp2=liq_signal.take_profit_2,
                tp3=liq_signal.take_profit_3,
                confidence=liq_signal.confidence,
                reasoning=liq_signal.reasoning,
                metadata={
                    "event_type": liq_signal.event_type.value,
                    "liq_volume_usd": liq_signal.liq_volume_usd,
                    "long_liq_pct": liq_signal.long_liq_pct,
                    "price_move_pct": liq_signal.price_drop_pct
                }
            )
            
            await self._add_signal(unified)
            return unified
        
        return None
    
    async def _add_signal(self, signal: UnifiedSignal):
        """Add a new signal and trigger callback"""
        
        # Check for duplicates (same strategy, same direction within last 5 mins)
        recent_cutoff = datetime.now(timezone.utc).timestamp() - 300  # 5 minutes
        for existing in self.active_signals:
            if (existing.strategy == signal.strategy and 
                existing.direction == signal.direction and
                existing.timestamp.timestamp() > recent_cutoff):
                logger.debug(f"Duplicate signal ignored: {signal.id}")
                return
        
        # Add to active signals
        self.active_signals.append(signal)
        self.signal_history.append(signal)
        
        # Trim if too many
        if len(self.active_signals) > self.max_active_signals:
            removed = self.active_signals.pop(0)
            if self.on_signal_expired:
                await self.on_signal_expired(removed)
        
        if len(self.signal_history) > 500:
            self.signal_history = self.signal_history[-500:]
        
        # Trigger callback
        if self.on_new_signal:
            await self.on_new_signal(signal)
        
        logger.info(f"🚨 NEW SIGNAL: {signal.strategy.value} {signal.direction} | "
                   f"Entry: ${signal.entry_price:,.2f} | "
                   f"Stop: ${signal.stop_loss:,.2f} | "
                   f"Target: ${signal.take_profit_1:,.2f} | "
                   f"R:R {signal.risk_reward_ratio:.1f} | "
                   f"Priority: {signal.priority.value}")
    
    def get_active_signals(self) -> List[Dict[str, Any]]:
        """Get all active signals as dictionaries"""
        signals = []
        for s in self.active_signals:
            signal_dict = asdict(s)
            signal_dict["timestamp"] = s.timestamp.isoformat()
            signal_dict["expires_at"] = s.expires_at.isoformat() if s.expires_at else None
            signal_dict["strategy"] = s.strategy.value
            signal_dict["priority"] = s.priority.value
            signals.append(signal_dict)
        
        # Sort by priority (high first) then by timestamp (recent first)
        priority_order = {SignalPriority.HIGH: 0, SignalPriority.MEDIUM: 1, SignalPriority.LOW: 2}
        signals.sort(key=lambda x: (priority_order.get(SignalPriority(x["priority"]), 2), 
                                    -datetime.fromisoformat(x["timestamp"]).timestamp()))
        
        return signals
    
    def dismiss_signal(self, signal_id: str) -> bool:
        """Remove a signal from active signals"""
        for i, s in enumerate(self.active_signals):
            if s.id == signal_id:
                self.active_signals.pop(i)
                logger.info(f"Signal dismissed: {signal_id}")
                return True
        return False
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """Get status of all strategies"""
        return {
            "funding_rate": {
                "enabled": self.enabled_strategies[StrategyType.FUNDING_RATE],
                **self.funding_strategy.to_dict()
            },
            "vwap": {
                "enabled": self.enabled_strategies[StrategyType.VWAP],
                **self.vwap_strategy.to_dict()
            },
            "session_breakout": {
                "enabled": self.enabled_strategies[StrategyType.SESSION_BREAKOUT],
                **self.session_strategy.to_dict()
            },
            "liquidation_reversal": {
                "enabled": self.enabled_strategies[StrategyType.LIQUIDATION_REVERSAL],
                **self.liquidation_strategy.to_dict()
            }
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of signal engine status"""
        return {
            "active_signals": len(self.active_signals),
            "total_signals_generated": len(self.signal_history),
            "last_price": self.last_price,
            "enabled_strategies": sum(self.enabled_strategies.values()),
            "signals_by_priority": {
                "high": len([s for s in self.active_signals if s.priority == SignalPriority.HIGH]),
                "medium": len([s for s in self.active_signals if s.priority == SignalPriority.MEDIUM]),
                "low": len([s for s in self.active_signals if s.priority == SignalPriority.LOW])
            }
        }


# Global instance
_signal_engine: Optional[SignalEngine] = None


def get_signal_engine() -> SignalEngine:
    """Get or create global signal engine instance"""
    global _signal_engine
    if _signal_engine is None:
        _signal_engine = SignalEngine()
    return _signal_engine
