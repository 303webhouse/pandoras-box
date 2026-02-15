"""
Context builder for Pivot chat responses.

Gathers relevant market data, journal state, and DEFCON status to
enrich LLM prompts with real information before generating a response.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from collectors.base_collector import get_json

logger = logging.getLogger(__name__)


async def build_trade_eval_context(
    ticker: str,
    expiry: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Gather all data needed for a trade evaluation.

    Runs in parallel:
    - Market data (quote, IV rank, earnings, VIX, options chain)
    - Bias state from Pandora API
    - DEFCON status
    - Open positions from journal
    - Breakout status

    Returns a dict with all gathered data for LLM prompt injection.
    """
    tasks: Dict[str, Any] = {}

    # Market data (Phase 2D tools)
    try:
        from tools import gather_trade_context
        tasks["market"] = gather_trade_context(ticker, expiry)
    except ImportError:
        logger.warning("tools module not available")

    # Bias state from Pandora API
    tasks["bias"] = get_json("/bias/composite")

    # DEFCON
    try:
        from monitors.defcon import get_current_defcon
        tasks["defcon"] = get_current_defcon()
    except ImportError:
        logger.debug("monitors.defcon not available (future phase)")

    # Journal — open positions
    try:
        from journal.trades import get_open_trades, get_streak
        tasks["open_trades"] = asyncio.to_thread(get_open_trades)
        tasks["streak"] = asyncio.to_thread(get_streak)
    except ImportError:
        logger.debug("journal module not available (future phase)")

    # Breakout status
    try:
        from journal.breakout import check_breakout_danger
        tasks["breakout"] = asyncio.to_thread(check_breakout_danger)
    except ImportError:
        pass

    results: Dict[str, Any] = {}
    if tasks:
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                logger.warning(f"Context gather failed for {key}: {result}")
                results[key] = {"status": "error", "error": str(result)}
            else:
                results[key] = result

    return results


async def build_status_context() -> Dict[str, Any]:
    """
    Gather system status: bias, DEFCON, open trades, Breakout, VIX.
    Used for "how's the market?" / "status check" queries.
    """
    tasks: Dict[str, Any] = {}

    tasks["bias"] = get_json("/bias/composite")

    try:
        from monitors.defcon import get_current_defcon
        tasks["defcon"] = get_current_defcon()
    except ImportError:
        pass

    try:
        from journal.trades import get_open_trades
        tasks["open_trades"] = asyncio.to_thread(get_open_trades)
    except ImportError:
        pass

    try:
        from journal.breakout import check_breakout_danger
        tasks["breakout"] = asyncio.to_thread(check_breakout_danger)
    except ImportError:
        pass

    try:
        from tools.vix_status import get_vix_status
        tasks["vix"] = get_vix_status()
    except ImportError:
        pass

    results: Dict[str, Any] = {}
    if tasks:
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                results[key] = {"status": "error", "error": str(result)}
            else:
                results[key] = result

    return results


async def build_quote_context(ticker: str) -> Dict[str, Any]:
    """
    Gather data for a simple quote request.
    """
    tasks: Dict[str, Any] = {}

    try:
        from tools.quote import get_quote
        tasks["quote"] = get_quote(ticker)
    except ImportError:
        pass

    # Crypto tickers use dedicated endpoint
    if ticker in ("BTC", "ETH"):
        try:
            from tools.btc_price import get_btc_price, get_eth_price
            tasks["crypto"] = get_eth_price() if ticker == "ETH" else get_btc_price()
        except ImportError:
            pass

    results: Dict[str, Any] = {}
    if tasks:
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                results[key] = {"status": "error", "error": str(result)}
            else:
                results[key] = result

    return results


async def build_review_context(period: str = "week") -> Dict[str, Any]:
    """
    Gather data for a performance review.
    """
    results: Dict[str, Any] = {}

    try:
        from journal.reports import weekly_summary, daily_summary
        if period == "week":
            results["summary"] = await asyncio.to_thread(weekly_summary)
        else:
            results["summary"] = await asyncio.to_thread(daily_summary)
    except ImportError:
        results["summary"] = {"status": "error", "error": "Journal not available (Phase 2B)"}

    try:
        from journal.trades import get_streak, get_open_trades
        results["streak"] = await asyncio.to_thread(get_streak)
        results["open_trades"] = await asyncio.to_thread(get_open_trades)
    except ImportError:
        pass

    try:
        from journal.breakout import check_breakout_danger
        results["breakout"] = await asyncio.to_thread(check_breakout_danger)
    except ImportError:
        pass

    return results


def format_context_for_prompt(context: Dict[str, Any]) -> str:
    """
    Convert gathered context dict to a formatted string for LLM injection.

    Filters out error responses (labels them as unavailable) and formats
    the rest as pretty-printed JSON sections.
    """
    parts = []

    for key, value in context.items():
        if isinstance(value, dict) and value.get("status") == "error":
            parts.append(
                f"[{key}: unavailable — {value.get('error', 'unknown error')}]"
            )
        else:
            try:
                formatted = json.dumps(value, indent=2, default=str)
                parts.append(f"### {key.upper()}\n{formatted}")
            except (TypeError, ValueError):
                parts.append(f"### {key.upper()}\n{str(value)}")

    return "\n\n".join(parts)
