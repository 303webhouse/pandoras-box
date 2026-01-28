"""API module for Crypto Scalper"""
from .btc_integration import (
    BTCIntegrationManager,
    get_btc_manager,
    get_btc_bottom_confluence,
    get_current_btc_session,
    get_btc_session_schedule
)

__all__ = [
    'BTCIntegrationManager',
    'get_btc_manager',
    'get_btc_bottom_confluence',
    'get_current_btc_session',
    'get_btc_session_schedule'
]
