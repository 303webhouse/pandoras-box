"""
Crypto Scalper Trading Strategies

This package contains specialized trading strategies optimized for:
- BTC perpetual swap futures
- Breakout prop trading account constraints
- Conservative to aggressive risk profiles

Strategies:
1. Funding Rate Scalper - Mean reversion on extreme funding
2. VWAP Reclaim/Reject - Intraday fair value trading  
3. Session Breakout - Opening range breakout trading
4. Liquidation Reversal - Fade liquidation cascades

All strategies output signals through the unified SignalEngine.
"""

from .funding_rate import FundingRateStrategy, get_funding_strategy
from .vwap_strategy import VWAPStrategy, get_vwap_strategy
from .session_breakout import SessionBreakoutStrategy, get_session_strategy
from .liquidation_reversal import LiquidationReversalStrategy, get_liquidation_strategy
from .signal_engine import SignalEngine, get_signal_engine, UnifiedSignal, StrategyType, SignalPriority

__all__ = [
    'FundingRateStrategy',
    'get_funding_strategy',
    'VWAPStrategy', 
    'get_vwap_strategy',
    'SessionBreakoutStrategy',
    'get_session_strategy',
    'LiquidationReversalStrategy',
    'get_liquidation_strategy',
    'SignalEngine',
    'get_signal_engine',
    'UnifiedSignal',
    'StrategyType',
    'SignalPriority'
]
