"""
Position Overlap Utility
Checks if a ticker overlaps with any position in unified_positions,
either directly or as a top-10 ETF component.
"""

import logging
from typing import Dict, List

logger = logging.getLogger("position_overlap")

# Hardcoded ETF top-10 holdings (updated quarterly)
ETF_COMPONENTS = {
    "XLF": ["JPM", "BRK.B", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "AXP"],
    "SMH": ["NVDA", "TSM", "AVGO", "ASML", "TXN", "QCOM", "AMD", "AMAT", "LRCX", "MU"],
    "HYG": [],
    "IYR": ["PLD", "AMT", "EQIX", "WELL", "SPG", "DLR", "PSA", "O", "CCI", "VICI"],
    "IWM": [],
    "IBIT": [],
}


async def check_position_overlap(ticker: str) -> Dict:
    """
    Returns:
    {
        "overlaps": True/False,
        "positions": ["XLF", "SMH"],
        "relationship": "direct" | "component" | None
    }
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker FROM unified_positions WHERE status = 'OPEN'"
        )
    position_tickers = [r["ticker"] for r in rows]

    # Direct match
    if ticker in position_tickers:
        return {"overlaps": True, "positions": [ticker], "relationship": "direct"}

    # Component match: is this ticker in any ETF that Nick holds?
    overlapping_positions = []
    for pos_ticker in position_tickers:
        components = ETF_COMPONENTS.get(pos_ticker, [])
        if ticker in components:
            overlapping_positions.append(pos_ticker)

    if overlapping_positions:
        return {"overlaps": True, "positions": overlapping_positions, "relationship": "component"}

    return {"overlaps": False, "positions": [], "relationship": None}


async def refresh_etf_components():
    """
    Refresh ETF_COMPONENTS dict from FMP ETF holdings API.
    Call this weekly (or on demand) to keep holdings current.
    Falls back to hardcoded values if FMP fails.
    """
    from integrations.fmp_client import fetch_etf_holdings

    etf_tickers = ["XLF", "SMH", "IYR"]  # Only ETFs with meaningful single-stock components

    for etf in etf_tickers:
        try:
            holdings = await fetch_etf_holdings(etf, limit=10)
            if holdings:
                new_components = [h.get("asset", "").upper() for h in holdings if h.get("asset")]
                if new_components:
                    ETF_COMPONENTS[etf] = new_components
                    logger.info("Refreshed %s components: %s", etf, ETF_COMPONENTS[etf])
                else:
                    logger.info("FMP returned empty holdings for %s — keeping hardcoded values", etf)
            else:
                logger.info("FMP ETF holdings unavailable for %s (likely paid-only) — keeping hardcoded values", etf)
        except Exception as e:
            logger.warning("Failed to refresh %s components from FMP: %s — keeping hardcoded values", etf, e)
