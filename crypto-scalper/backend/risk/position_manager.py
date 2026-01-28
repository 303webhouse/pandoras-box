"""
Risk Management & Position Sizing Engine
Specifically designed for Breakout Prop Trading constraints:

BREAKOUT 1-STEP RULES:
- Max Drawdown: 6% STATIC from starting balance ($25,000 -> can't go below $23,500)
- Max Daily Loss: 4% from balance at 12:30 AM UTC
- Leverage: 5x for BTC/ETH, 2x for others
- Fees: 0.035% per side (7 bps round trip) + 0.09% daily swap

BREAKOUT 2-STEP RULES:
- Max Drawdown: 8% TRAILING from high water mark
- Max Daily Loss: 5% from balance at 12:30 AM UTC

CONSERVATIVE APPROACH (Phase 1 - Account Funding):
- Never risk more than 1.5% per trade (buffer for slippage/gaps)
- Target 2:1 minimum R:R 
- Max 2 concurrent positions
- Prefer 1-2x leverage until funded

This ensures we never breach even with 2 bad trades in a row.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class AccountType(str, Enum):
    """Breakout account types with different rules"""
    ONE_STEP = "1-step"
    TWO_STEP = "2-step"
    FUNDED = "funded"


class RiskPhase(str, Enum):
    """Trading phases with different risk parameters"""
    CONSERVATIVE = "conservative"  # Account funding phase: 0.5-1.5% risk
    GROWTH = "growth"              # Funded, building: 1-2% risk
    AGGRESSIVE = "aggressive"      # Two funded accounts, can swing: 2-4% risk


@dataclass
class AccountState:
    """Track account state for risk management"""
    account_type: AccountType = AccountType.ONE_STEP
    starting_balance: float = 25000.0
    current_balance: float = 25000.0
    high_water_mark: float = 25000.0
    daily_start_balance: float = 25000.0  # Balance at 12:30 AM UTC
    daily_start_time: datetime = None
    
    # Calculated limits
    max_drawdown_level: float = 0.0
    max_daily_loss_level: float = 0.0
    
    # Current status
    current_drawdown_pct: float = 0.0
    current_daily_pnl_pct: float = 0.0
    
    # Position tracking
    open_positions: List[Dict] = field(default_factory=list)
    total_open_risk: float = 0.0


@dataclass 
class RiskParameters:
    """Risk parameters based on current phase"""
    phase: RiskPhase
    max_risk_per_trade_pct: float
    max_concurrent_positions: int
    min_reward_risk_ratio: float
    max_leverage: float
    position_scale_factor: float  # 1.0 = full size, 0.5 = half size
    
    # Buffer from limits (safety margin)
    drawdown_warning_buffer_pct: float = 1.0  # Warn at 1% before limit
    daily_loss_warning_buffer_pct: float = 0.5


# Default risk parameters per phase
RISK_PHASES = {
    RiskPhase.CONSERVATIVE: RiskParameters(
        phase=RiskPhase.CONSERVATIVE,
        max_risk_per_trade_pct=1.0,      # 1% max risk
        max_concurrent_positions=2,
        min_reward_risk_ratio=2.0,        # Minimum 2:1 R:R
        max_leverage=2.0,                 # Stay conservative
        position_scale_factor=0.75,       # Scale down by 25%
        drawdown_warning_buffer_pct=1.5,
        daily_loss_warning_buffer_pct=1.0
    ),
    RiskPhase.GROWTH: RiskParameters(
        phase=RiskPhase.GROWTH,
        max_risk_per_trade_pct=1.5,
        max_concurrent_positions=3,
        min_reward_risk_ratio=1.5,
        max_leverage=3.0,
        position_scale_factor=1.0,
        drawdown_warning_buffer_pct=1.0,
        daily_loss_warning_buffer_pct=0.75
    ),
    RiskPhase.AGGRESSIVE: RiskParameters(
        phase=RiskPhase.AGGRESSIVE,
        max_risk_per_trade_pct=2.5,
        max_concurrent_positions=4,
        min_reward_risk_ratio=1.25,
        max_leverage=5.0,
        position_scale_factor=1.25,
        drawdown_warning_buffer_pct=0.5,
        daily_loss_warning_buffer_pct=0.5
    )
}


class PositionManager:
    """
    Manages position sizing and risk limits for Breakout accounts
    """
    
    # Breakout fee structure
    TRADING_FEE_PER_SIDE = 0.00035  # 0.035% = 3.5 bps
    DAILY_SWAP_FEE = 0.0009        # 0.09% per day at 00:00 UTC
    
    def __init__(
        self,
        account_type: AccountType = AccountType.ONE_STEP,
        starting_balance: float = 25000.0,
        risk_phase: RiskPhase = RiskPhase.CONSERVATIVE
    ):
        self.account = AccountState(
            account_type=account_type,
            starting_balance=starting_balance,
            current_balance=starting_balance,
            high_water_mark=starting_balance,
            daily_start_balance=starting_balance,
            daily_start_time=datetime.now(timezone.utc)
        )
        
        self.risk_phase = risk_phase
        self.risk_params = RISK_PHASES[risk_phase]
        
        # Initialize limits
        self._calculate_limits()
        
        logger.info(f"Position Manager initialized: {account_type.value} account, "
                   f"${starting_balance:,.2f}, {risk_phase.value} phase")
    
    def _calculate_limits(self):
        """Calculate max drawdown and daily loss levels"""
        
        if self.account.account_type == AccountType.ONE_STEP:
            # 6% STATIC from starting balance
            self.account.max_drawdown_level = self.account.starting_balance * 0.94
        else:  # TWO_STEP or FUNDED
            # 8% TRAILING from high water mark
            self.account.max_drawdown_level = self.account.high_water_mark * 0.92
        
        # Daily loss limit (4% for 1-step, 5% for 2-step)
        daily_loss_pct = 0.04 if self.account.account_type == AccountType.ONE_STEP else 0.05
        self.account.max_daily_loss_level = self.account.daily_start_balance * (1 - daily_loss_pct)
        
        # Calculate current status
        self.account.current_drawdown_pct = (
            (self.account.high_water_mark - self.account.current_balance) / 
            self.account.high_water_mark * 100
        )
        self.account.current_daily_pnl_pct = (
            (self.account.current_balance - self.account.daily_start_balance) / 
            self.account.daily_start_balance * 100
        )
    
    def update_balance(self, new_balance: float):
        """Update account balance and recalculate limits"""
        self.account.current_balance = new_balance
        
        # Update high water mark if new high
        if new_balance > self.account.high_water_mark:
            self.account.high_water_mark = new_balance
            
            # Recalculate trailing drawdown for 2-step
            if self.account.account_type != AccountType.ONE_STEP:
                self._calculate_limits()
        
        self._calculate_limits()
        
        # Check for warnings
        self._check_risk_warnings()
    
    def daily_reset(self, balance_at_reset: float):
        """Called at 12:30 AM UTC to reset daily loss calculation"""
        self.account.daily_start_balance = balance_at_reset
        self.account.daily_start_time = datetime.now(timezone.utc)
        self._calculate_limits()
        logger.info(f"Daily reset: Starting balance ${balance_at_reset:,.2f}")
    
    def _check_risk_warnings(self) -> List[str]:
        """Check for risk limit warnings"""
        warnings = []
        
        # Drawdown warning
        if self.account.account_type == AccountType.ONE_STEP:
            max_dd = 6.0
        else:
            max_dd = 8.0
        
        dd_warning_level = max_dd - self.risk_params.drawdown_warning_buffer_pct
        if self.account.current_drawdown_pct >= dd_warning_level:
            warnings.append(
                f"⚠️ DRAWDOWN WARNING: {self.account.current_drawdown_pct:.2f}% "
                f"(limit: {max_dd}%)"
            )
        
        # Daily loss warning
        daily_limit = 4.0 if self.account.account_type == AccountType.ONE_STEP else 5.0
        daily_warning_level = -(daily_limit - self.risk_params.daily_loss_warning_buffer_pct)
        if self.account.current_daily_pnl_pct <= daily_warning_level:
            warnings.append(
                f"⚠️ DAILY LOSS WARNING: {self.account.current_daily_pnl_pct:.2f}% "
                f"(limit: -{daily_limit}%)"
            )
        
        for warning in warnings:
            logger.warning(warning)
        
        return warnings
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float = None,
        leverage: float = 1.0,
        signal_confidence: float = 1.0  # 0-1 scale
    ) -> Dict[str, Any]:
        """
        Calculate position size based on risk parameters
        
        Returns:
            Dict with position_size, risk_amount, reward_risk_ratio, 
            position_value, warnings, and approval status
        """
        
        # Validate inputs
        if entry_price <= 0 or stop_loss_price <= 0:
            return {"approved": False, "reason": "Invalid prices"}
        
        # Determine direction
        is_long = stop_loss_price < entry_price
        
        # Calculate risk per unit (distance to stop as percentage)
        if is_long:
            risk_per_unit_pct = (entry_price - stop_loss_price) / entry_price
        else:
            risk_per_unit_pct = (stop_loss_price - entry_price) / entry_price
        
        if risk_per_unit_pct <= 0:
            return {"approved": False, "reason": "Stop loss in wrong direction"}
        
        # Calculate R:R if take profit provided
        reward_risk_ratio = None
        if take_profit_price:
            if is_long:
                reward = take_profit_price - entry_price
                risk = entry_price - stop_loss_price
            else:
                reward = entry_price - take_profit_price
                risk = stop_loss_price - entry_price
            
            if risk > 0:
                reward_risk_ratio = reward / risk
            
            # Check minimum R:R
            if reward_risk_ratio and reward_risk_ratio < self.risk_params.min_reward_risk_ratio:
                return {
                    "approved": False,
                    "reason": f"R:R of {reward_risk_ratio:.2f} below minimum {self.risk_params.min_reward_risk_ratio:.1f}",
                    "reward_risk_ratio": reward_risk_ratio
                }
        
        # Cap leverage at phase maximum
        effective_leverage = min(leverage, self.risk_params.max_leverage)
        
        # Calculate max risk amount for this trade
        base_risk_pct = self.risk_params.max_risk_per_trade_pct / 100
        
        # Adjust risk based on:
        # 1. Phase scale factor
        # 2. Signal confidence
        # 3. Current drawdown (reduce size if already down)
        
        drawdown_factor = 1.0
        if self.account.current_drawdown_pct > 2:
            # Reduce position size if already in drawdown
            drawdown_factor = max(0.5, 1 - (self.account.current_drawdown_pct / 10))
        
        adjusted_risk_pct = (
            base_risk_pct * 
            self.risk_params.position_scale_factor * 
            signal_confidence *
            drawdown_factor
        )
        
        # Calculate risk amount in dollars
        risk_amount = self.account.current_balance * adjusted_risk_pct
        
        # Calculate position size
        # Risk Amount = Position Size × Risk Per Unit × Leverage
        # Position Size = Risk Amount / (Risk Per Unit × Entry Price)
        position_size_btc = risk_amount / (risk_per_unit_pct * entry_price)
        
        # Calculate position value (notional)
        position_value = position_size_btc * entry_price
        
        # Calculate effective position with leverage
        leveraged_position_value = position_value * effective_leverage
        
        # Check if we have room for another position
        current_position_count = len(self.account.open_positions)
        if current_position_count >= self.risk_params.max_concurrent_positions:
            return {
                "approved": False,
                "reason": f"Max {self.risk_params.max_concurrent_positions} concurrent positions",
                "current_positions": current_position_count
            }
        
        # Check total open risk
        new_total_risk = self.account.total_open_risk + risk_amount
        max_total_risk = self.account.current_balance * (self.risk_params.max_risk_per_trade_pct * 2 / 100)
        
        if new_total_risk > max_total_risk:
            return {
                "approved": False,
                "reason": f"Total risk ${new_total_risk:.2f} exceeds max ${max_total_risk:.2f}",
                "current_open_risk": self.account.total_open_risk
            }
        
        # Calculate fees
        entry_fee = position_value * self.TRADING_FEE_PER_SIDE
        exit_fee = position_value * self.TRADING_FEE_PER_SIDE
        total_fees = entry_fee + exit_fee
        
        # Warnings
        warnings = self._check_risk_warnings()
        
        return {
            "approved": True,
            "direction": "LONG" if is_long else "SHORT",
            "position_size_btc": round(position_size_btc, 6),
            "position_value_usd": round(position_value, 2),
            "leveraged_value_usd": round(leveraged_position_value, 2),
            "effective_leverage": effective_leverage,
            "risk_amount_usd": round(risk_amount, 2),
            "risk_pct": round(adjusted_risk_pct * 100, 3),
            "entry_price": entry_price,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "reward_risk_ratio": round(reward_risk_ratio, 2) if reward_risk_ratio else None,
            "estimated_fees": round(total_fees, 2),
            "warnings": warnings,
            "account_state": {
                "balance": self.account.current_balance,
                "drawdown_pct": round(self.account.current_drawdown_pct, 2),
                "daily_pnl_pct": round(self.account.current_daily_pnl_pct, 2),
                "open_positions": current_position_count
            }
        }
    
    def add_position(self, position_data: Dict) -> str:
        """Track a new open position"""
        position_id = f"pos_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        position_data["id"] = position_id
        position_data["opened_at"] = datetime.now(timezone.utc).isoformat()
        
        self.account.open_positions.append(position_data)
        self.account.total_open_risk += position_data.get("risk_amount_usd", 0)
        
        logger.info(f"Position opened: {position_id}")
        return position_id
    
    def close_position(self, position_id: str, exit_price: float) -> Optional[Dict]:
        """Close a position and calculate P&L"""
        position = None
        for p in self.account.open_positions:
            if p.get("id") == position_id:
                position = p
                break
        
        if not position:
            return None
        
        # Calculate P&L
        entry_price = position.get("entry_price", 0)
        size = position.get("position_size_btc", 0)
        is_long = position.get("direction") == "LONG"
        
        if is_long:
            pnl = (exit_price - entry_price) * size
        else:
            pnl = (entry_price - exit_price) * size
        
        # Deduct fees
        position_value = size * entry_price
        fees = position_value * self.TRADING_FEE_PER_SIDE * 2
        net_pnl = pnl - fees
        
        # Update balance
        self.update_balance(self.account.current_balance + net_pnl)
        
        # Remove position
        self.account.open_positions.remove(position)
        self.account.total_open_risk -= position.get("risk_amount_usd", 0)
        
        result = {
            "position_id": position_id,
            "gross_pnl": round(pnl, 2),
            "fees": round(fees, 2),
            "net_pnl": round(net_pnl, 2),
            "new_balance": self.account.current_balance
        }
        
        logger.info(f"Position closed: {position_id}, P&L: ${net_pnl:.2f}")
        return result
    
    def get_status(self) -> Dict[str, Any]:
        """Get current risk management status"""
        
        # Calculate room to trade
        if self.account.account_type == AccountType.ONE_STEP:
            room_to_drawdown = 6.0 - self.account.current_drawdown_pct
            room_to_daily_loss = 4.0 + self.account.current_daily_pnl_pct
        else:
            room_to_drawdown = 8.0 - self.account.current_drawdown_pct
            room_to_daily_loss = 5.0 + self.account.current_daily_pnl_pct
        
        return {
            "account": {
                "type": self.account.account_type.value,
                "starting_balance": self.account.starting_balance,
                "current_balance": round(self.account.current_balance, 2),
                "high_water_mark": round(self.account.high_water_mark, 2),
                "daily_start_balance": round(self.account.daily_start_balance, 2)
            },
            "risk_status": {
                "phase": self.risk_phase.value,
                "current_drawdown_pct": round(self.account.current_drawdown_pct, 2),
                "current_daily_pnl_pct": round(self.account.current_daily_pnl_pct, 2),
                "max_drawdown_level": round(self.account.max_drawdown_level, 2),
                "max_daily_loss_level": round(self.account.max_daily_loss_level, 2),
                "room_to_drawdown_pct": round(room_to_drawdown, 2),
                "room_to_daily_loss_pct": round(room_to_daily_loss, 2)
            },
            "positions": {
                "open_count": len(self.account.open_positions),
                "max_allowed": self.risk_params.max_concurrent_positions,
                "total_open_risk": round(self.account.total_open_risk, 2)
            },
            "parameters": {
                "max_risk_per_trade_pct": self.risk_params.max_risk_per_trade_pct,
                "min_reward_risk": self.risk_params.min_reward_risk_ratio,
                "max_leverage": self.risk_params.max_leverage
            },
            "warnings": self._check_risk_warnings()
        }
    
    def set_risk_phase(self, phase: RiskPhase):
        """Change risk phase (e.g., after getting funded)"""
        self.risk_phase = phase
        self.risk_params = RISK_PHASES[phase]
        logger.info(f"Risk phase changed to: {phase.value}")


# Global instance
_position_manager: Optional[PositionManager] = None


def get_position_manager() -> PositionManager:
    """Get or create global position manager"""
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager()
    return _position_manager


def init_position_manager(
    account_type: AccountType = AccountType.ONE_STEP,
    starting_balance: float = 25000.0,
    risk_phase: RiskPhase = RiskPhase.CONSERVATIVE
) -> PositionManager:
    """Initialize position manager with custom settings"""
    global _position_manager
    _position_manager = PositionManager(
        account_type=account_type,
        starting_balance=starting_balance,
        risk_phase=risk_phase
    )
    return _position_manager
