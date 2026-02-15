"""
Intent handlers for Pivot chat.

Each handler:
1. Gathers relevant context (market data, journal, DEFCON)
2. Builds an appropriate prompt using templates from llm/prompts.py
3. Calls the LLM via call_llm()
4. Returns the response text
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from llm.pivot_agent import call_llm
from llm.prompts import (
    build_trade_eval_prompt,
    build_flow_analysis_prompt,
    build_breakout_checkin_prompt,
    build_weekly_review_prompt,
)
from chat.context import (
    build_trade_eval_context,
    build_status_context,
    build_quote_context,
    build_review_context,
    format_context_for_prompt,
)
from chat.router import extract_ticker, extract_trade_details

logger = logging.getLogger(__name__)

# VIX DEFCON → Discord emoji mapping
_VIX_EMOJI = {"yellow": "🟡", "orange": "🟠", "red": "🔴"}


# ---------------------------------------------------------------------------
# Trade idea evaluation
# ---------------------------------------------------------------------------

async def handle_trade_idea(message_text: str) -> str:
    """
    Evaluate a trade idea against the Playbook's 9-point checklist.

    Gathers quote, chain, IV, earnings, VIX, bias, and DEFCON in
    parallel, then asks the LLM to evaluate the trade.
    """
    details = extract_trade_details(message_text)
    ticker = details.get("ticker")

    if not ticker:
        return (
            "I need a ticker to evaluate a trade. "
            'Try: "thinking about bear put spread on SPY 520/510 March"'
        )

    expiry = details.get("expiry")

    context = await build_trade_eval_context(ticker, expiry)

    market_data = format_context_for_prompt(context)
    bias_state = json.dumps(context.get("bias", {}), indent=2, default=str)

    prompt = build_trade_eval_prompt(
        trade_idea=message_text,
        market_data=market_data,
        bias_state=bias_state,
    )

    response = await call_llm(prompt, max_tokens=1000)
    return response or "Couldn't generate an evaluation. Try again."


# ---------------------------------------------------------------------------
# Trade open — log a new position
# ---------------------------------------------------------------------------

async def handle_trade_open(message_text: str) -> str:
    """
    Log a new trade to the journal.

    Extracts trade details, records current bias and DEFCON at entry,
    runs a compliance check, and warns on consecutive-loss streaks.
    """
    details = extract_trade_details(message_text)

    if not details.get("ticker"):
        return (
            "I need at least a ticker to log the trade. "
            'Try: "opened SPY 520/510 bear put spread, 2 contracts, $340 risk on Robinhood"'
        )

    # Capture bias and DEFCON at entry time
    try:
        from collectors.base_collector import get_json
        bias = await get_json("/bias/composite")
        details["bias_at_entry"] = bias.get("bias_level", "unknown")
    except Exception:
        details["bias_at_entry"] = "unknown"

    try:
        from monitors.defcon import get_current_defcon
        defcon = await get_current_defcon()
        details["defcon_at_entry"] = defcon.get("level", "unknown")
    except (ImportError, Exception):
        details["defcon_at_entry"] = "unknown"

    entry: Dict[str, Any] = {
        "account": details.get("account", "robinhood"),
        "ticker": details["ticker"],
        "direction": details.get("direction", "unknown"),
        "strategy": details.get("strategy"),
        "size": details.get("size"),
        "bias_at_entry": details.get("bias_at_entry"),
        "defcon_at_entry": details.get("defcon_at_entry"),
    }
    if details.get("strikes"):
        entry["entry_price"] = details["strikes"][0]
    if details.get("dollar_amounts"):
        entry["max_loss"] = details["dollar_amounts"][0]

    # Log to journal (Phase 2B) — graceful if not yet available
    trade_id: Optional[int] = None
    try:
        from journal.trades import open_trade
        trade_id = await asyncio.to_thread(open_trade, entry)
    except ImportError:
        # Journal not yet deployed — still provide a confirmation
        trade_id = None
    except Exception as exc:
        logger.error(f"Failed to log trade: {exc}")
        return f"❌ Failed to log trade: {exc}"

    # Compliance check
    warnings = []
    if trade_id is not None:
        try:
            from journal.reports import rule_compliance_check
            warnings = await asyncio.to_thread(rule_compliance_check, trade_id)
        except (ImportError, Exception):
            pass

    # Consecutive-loss streak warning
    streak_msg = ""
    if trade_id is not None:
        try:
            from journal.trades import get_streak
            streak = await asyncio.to_thread(get_streak, entry.get("account"))
            if streak and streak.get("type") == "loss" and streak.get("count", 0) >= 2:
                streak_msg = (
                    f"\n\n⚠️ **Streak alert:** {streak['count']} consecutive losses "
                    f"on {entry['account']}. Playbook says: HALF position size until a winner."
                )
        except (ImportError, Exception):
            pass

    # Build response
    id_label = f"#{trade_id}" if trade_id is not None else "(journal offline)"
    confirm = f"✅ **Trade {id_label} logged**\n"
    confirm += (
        f"**{entry['ticker']}** {entry.get('strategy', '')} ({entry.get('direction', '')}) "
        f"on {entry['account']}"
    )
    if entry.get("max_loss"):
        confirm += f" | Max loss: ${entry['max_loss']:.2f}"
    confirm += (
        f"\nBias at entry: {entry.get('bias_at_entry')} "
        f"| DEFCON: {entry.get('defcon_at_entry')}"
    )
    if warnings:
        confirm += "\n\n⚠️ **Rule warnings:**\n" + "\n".join(f"• {w}" for w in warnings)
    confirm += streak_msg

    return confirm


# ---------------------------------------------------------------------------
# Trade close — log an exit
# ---------------------------------------------------------------------------

async def handle_trade_close(message_text: str) -> str:
    """
    Log a trade exit.

    Finds the most recent open trade matching the ticker, closes it with
    P&L and exit reason, and prompts for a lesson learned.
    """
    details = extract_trade_details(message_text)
    ticker = details.get("ticker")

    if not ticker and details.get("pnl") is None:
        return (
            "I need the ticker and P&L to close a trade. "
            'Try: "closed SPY spread for +$220" or "stopped out of AAPL for -$80"'
        )

    try:
        from journal.trades import get_open_trades, close_trade

        open_trades = await asyncio.to_thread(get_open_trades)
        matching = (
            [t for t in open_trades if t.get("ticker") == ticker]
            if ticker
            else open_trades
        )

        if not matching:
            return (
                f"No open trades found{f' for {ticker}' if ticker else ''}. "
                "Log one first with 'opened...'"
            )

        trade = matching[0]
        trade_id = trade["id"]

        exit_data: Dict[str, Any] = {}
        if details.get("pnl") is not None:
            exit_data["pnl_dollars"] = details["pnl"]
        if details.get("dollar_amounts"):
            exit_data["exit_price"] = details["dollar_amounts"][0]

        text_lower = message_text.lower()
        if "stop" in text_lower:
            exit_data["exit_reason"] = "stop_hit"
        elif "target" in text_lower or "profit" in text_lower:
            exit_data["exit_reason"] = "target_hit"
        elif "expired" in text_lower:
            exit_data["exit_reason"] = "expired"
        else:
            exit_data["exit_reason"] = "manual"

        result = await asyncio.to_thread(close_trade, trade_id, exit_data)

        pnl = result.get("pnl_dollars", 0) or 0
        emoji = "🟢" if pnl >= 0 else "🔴"
        response = f"{emoji} **Trade #{trade_id} closed**\n"
        response += (
            f"**{result['ticker']}** {result.get('strategy', '')} | "
            f"P&L: **{'+'if pnl >= 0 else ''}{pnl:.2f}**\n"
            f"Exit: {exit_data.get('exit_reason', 'manual')}"
        )
        response += "\n\n📝 What's the takeaway? (Reply with your lesson and I'll save it)"
        return response

    except ImportError:
        return (
            "Journal not yet deployed (Phase 2B). "
            f"Noted: {ticker or 'trade'} closed for "
            f"{'%+.2f' % details['pnl'] if details.get('pnl') is not None else '?'}."
        )
    except Exception as exc:
        logger.error(f"Failed to close trade: {exc}")
        return f"❌ Failed to close trade: {exc}"


# ---------------------------------------------------------------------------
# Status check
# ---------------------------------------------------------------------------

async def handle_status(message_text: str) -> str:
    """
    Return a concise system status: bias, DEFCON, open positions, VIX.
    """
    context = await build_status_context()
    formatted = format_context_for_prompt(context)

    prompt = (
        "Nick is asking for a status check. Give a concise summary of:\n"
        "1. Current bias level and key factors\n"
        "2. DEFCON status\n"
        "3. Open positions (if any)\n"
        "4. Breakout account status (if data available)\n"
        "5. VIX regime\n\n"
        "Keep it tight — this is a quick check, not a full brief. "
        "One short paragraph max.\n\n"
        f"Nick's message: {message_text}\n\n"
        f"DATA:\n{formatted}"
    )

    response = await call_llm(prompt, max_tokens=500)
    return response or "Couldn't fetch status. API may be down."


# ---------------------------------------------------------------------------
# Quote / market data lookup
# ---------------------------------------------------------------------------

async def handle_quote(message_text: str) -> str:
    """
    Return a price quote, VIX status, crypto price, or options chain summary.
    """
    ticker = extract_ticker(message_text)
    text_lower = message_text.lower()

    # VIX-specific request
    if "vix" in text_lower:
        try:
            from tools.vix_status import get_vix_status
            vix = await get_vix_status()
            if vix.get("status") == "ok":
                emoji = _VIX_EMOJI.get(vix.get("defcon_signal"), "🟢")
                return (
                    f"{emoji} **VIX: {vix['vix']:.1f}** "
                    f"({vix.get('regime', 'unknown')} regime)\n"
                    f"VIX3M: {vix.get('vix3m', '?')} | "
                    f"Term: {vix.get('term_structure', '?')} "
                    f"(spread: {(vix.get('term_spread') or 0):+.2f})\n"
                    f"50-day MA: {vix.get('fifty_day_ma', '?')}"
                )
        except Exception as exc:
            logger.warning(f"VIX fetch failed: {exc}")

    # BTC/ETH crypto
    if ticker in ("BTC", "ETH") or "bitcoin" in text_lower or "btc" in text_lower:
        try:
            from tools.btc_price import get_btc_price, get_eth_price
            func = get_eth_price if ticker == "ETH" else get_btc_price
            data = await func()
            if data.get("status") == "ok":
                name = ticker or "BTC"
                price = data.get("price") or 0
                change = data.get("change_24h_pct") or 0
                low = data.get("low_24h") or 0
                high = data.get("high_24h") or 0
                return (
                    f"**{name}: ${price:,.2f}** ({change:+.2f}% 24h)\n"
                    f"24h range: ${low:,.0f} – ${high:,.0f}"
                )
        except Exception as exc:
            logger.warning(f"Crypto price fetch failed: {exc}")

    # Options chain request
    if ("chain" in text_lower or "options" in text_lower) and ticker:
        context = await build_trade_eval_context(ticker)
        formatted = format_context_for_prompt(context)
        prompt = (
            f"Nick wants options chain info for {ticker}. "
            "Summarize the key strikes, IV, and notable OI levels. "
            "Keep it concise (under 300 words).\n\n"
            f"DATA:\n{formatted}"
        )
        return await call_llm(prompt, max_tokens=600) or "Couldn't fetch chain data."

    # Standard equity/ETF quote
    if not ticker:
        return "What ticker? Try: `SPY?` or `what's AAPL at?`"

    context = await build_quote_context(ticker)
    quote_data = context.get("quote") or context.get("crypto") or {}

    if quote_data.get("status") == "ok":
        price = quote_data.get("price") or 0
        change = quote_data.get("change_percent") or 0
        emoji = "🟢" if change >= 0 else "🔴"
        response = f"{emoji} **{ticker}: ${price:,.2f}** ({change:+.2f}%)"

        ma50 = quote_data.get("fifty_day_ma")
        ma200 = quote_data.get("two_hundred_day_ma")
        if ma50:
            pos = "above" if price > ma50 else "below"
            response += f"\n50 MA: {ma50:.2f} ({pos})"
        if ma200:
            pos = "above" if price > ma200 else "below"
            response += f" | 200 MA: {ma200:.2f} ({pos})"

        return response

    return f"Couldn't get quote for {ticker}."


# ---------------------------------------------------------------------------
# Weekly/daily review
# ---------------------------------------------------------------------------

async def handle_review(message_text: str) -> str:
    """
    Generate a performance review from journal data.
    """
    period = "day" if any(w in message_text.lower() for w in ("today", "daily")) else "week"

    context = await build_review_context(period)
    formatted = format_context_for_prompt(context)

    prompt = build_weekly_review_prompt(formatted)
    response = await call_llm(prompt, max_tokens=1000)
    return response or "No journal data yet. Start logging trades and I can review them."


# ---------------------------------------------------------------------------
# General question — fallback handler
# ---------------------------------------------------------------------------

async def handle_question(message_text: str) -> str:
    """
    Handle general questions using Playbook knowledge and current market context.
    """
    context = await build_status_context()
    formatted = format_context_for_prompt(context)

    prompt = (
        "Nick is asking a question. Answer it using your Playbook knowledge "
        "and the current market context below. Be direct and concise.\n\n"
        f"Nick's question: {message_text}\n\n"
        f"CURRENT CONTEXT:\n{formatted}"
    )

    response = await call_llm(prompt, max_tokens=700)
    return response or "I'm not sure how to answer that. Can you rephrase?"
