"""
Type definitions for journal records.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class TradeEntry(TypedDict, total=False):
    """Fields for opening a trade."""
    account: str           # Required: '401k' | 'robinhood' | 'breakout'
    ticker: str            # Required
    direction: str         # Required: 'long' | 'short' | 'neutral'
    strategy: Optional[str]
    entry_price: Optional[float]
    entry_date: Optional[str]
    size: Optional[str]
    max_loss: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    bias_at_entry: Optional[str]
    defcon_at_entry: Optional[str]
    iv_rank: Optional[float]
    thesis: Optional[str]
    catalyst: Optional[str]
    invalidation: Optional[str]
    confidence: Optional[int]


class TradeExit(TypedDict, total=False):
    """Fields for closing a trade."""
    exit_price: Optional[float]
    exit_date: Optional[str]
    pnl_dollars: Optional[float]
    pnl_percent: Optional[float]
    followed_plan: Optional[bool]
    exit_reason: Optional[str]
    lesson: Optional[str]


class BreakoutSnapshot(TypedDict):
    """Breakout prop account state."""
    balance: float
    high_water_mark: float
    drawdown_floor_real: float
    drawdown_floor_personal: float
    daily_loss_used: float
    daily_loss_limit: float
    step: int
    notes: Optional[str]
