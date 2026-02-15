"""
Pivot on-demand market data tools.

These are callable utilities (not cron jobs) that return structured data
for use in LLM prompts and interactive trade evaluations.

Usage:
    from tools.quote import get_quote
    data = await get_quote("SPY")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Shared lock for yfinance calls (not thread-safe with concurrent access)
YF_LOCK = asyncio.Lock()


async def gather_trade_context(ticker: str, expiry: Optional[str] = None) -> dict:
    """
    Gather all relevant market data for evaluating a trade idea.

    Calls quote, iv_rank, earnings_check, vix_status in parallel.
    Optionally calls options_chain if expiry is provided.

    Returns a combined dict ready to inject into an LLM prompt.
    """
    from tools.quote import get_quote
    from tools.iv_rank import get_iv_rank
    from tools.earnings_check import check_earnings
    from tools.vix_status import get_vix_status

    task_map = {
        "quote": get_quote(ticker),
        "iv_rank": get_iv_rank(ticker),
        "earnings": check_earnings(ticker),
        "vix": get_vix_status(),
    }

    if expiry:
        from tools.options_chain import get_options_chain
        task_map["options_chain"] = get_options_chain(ticker, expiry)

    gathered = await asyncio.gather(*task_map.values(), return_exceptions=True)

    results: dict = {}
    for key, result in zip(task_map.keys(), gathered):
        if isinstance(result, Exception):
            results[key] = {"status": "error", "error": str(result)}
        else:
            results[key] = result

    results["status"] = "ok"
    return results
