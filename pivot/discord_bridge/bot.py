"""
Pivot Discord Bot — implementation module.

Handles two responsibilities:
1. Unusual Whales flow channel monitoring (UW_FLOW_CHANNEL_ID / UW_TICKER_CHANNEL_ID)
2. Interactive chat in #pivot-chat (PIVOT_CHAT_CHANNEL_ID)

Called by pivot/bot.py via run_bot().
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import discord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True  # Required to read message content

bot = discord.Client(intents=intents)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def send_long_message(channel: discord.TextChannel, text: str) -> None:
    """
    Send a message, splitting into ≤2000-char chunks if needed.

    Splits on double-newline (paragraph) boundaries first, then on
    single newlines when a paragraph is still too long.
    """
    if not text:
        return
    if len(text) <= 2000:
        await channel.send(text)
        return

    MAX = 1950  # leave buffer below Discord's hard limit

    # First pass: split on paragraph breaks
    chunks = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = (current + "\n\n" + paragraph) if current else paragraph
        if len(candidate) > MAX:
            if current:
                chunks.append(current.strip())
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current.strip())

    # Second pass: further split any chunk still over MAX
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= MAX:
            final_chunks.append(chunk)
        else:
            current = ""
            for line in chunk.split("\n"):
                candidate = (current + "\n" + line) if current else line
                if len(candidate) > MAX:
                    if current:
                        final_chunks.append(current.strip())
                    current = line
                else:
                    current = candidate
            if current:
                final_chunks.append(current.strip())

    for chunk in final_chunks:
        if chunk:
            await channel.send(chunk)


def _channel_id(env_key: str) -> Optional[int]:
    """Parse an env var as an integer channel/user ID, returning None if unset."""
    val = os.getenv(env_key, "").strip()
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        logger.warning(f"Invalid integer for env var {env_key}: {val!r}")
        return None


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    logger.info(f"Pivot bot connected as {bot.user} (id: {bot.user.id})")
    chat_ch = _channel_id("PIVOT_CHAT_CHANNEL_ID")
    logger.info(
        f"Chat channel: {chat_ch or 'not configured (set PIVOT_CHAT_CHANNEL_ID)'}"
    )


@bot.event
async def on_message(message: discord.Message) -> None:
    # Never respond to bots (including self)
    if message.author.bot:
        return

    # ── #pivot-chat interactive handler ────────────────────────────────────
    chat_channel_id = _channel_id("PIVOT_CHAT_CHANNEL_ID")
    owner_id_str = os.getenv("PIVOT_OWNER_ID", "").strip()

    if chat_channel_id and message.channel.id == chat_channel_id:
        # Only respond to the designated owner
        if owner_id_str and str(message.author.id) != owner_id_str:
            return

        await _handle_chat_message(message)
        return

    # ── Unusual Whales flow monitoring ─────────────────────────────────────
    uw_bot_user_id = os.getenv("UW_BOT_USER_ID", "").strip()
    if uw_bot_user_id and str(message.author.id) != uw_bot_user_id:
        return

    uw_channels: set[int] = set()
    for key in ("UW_FLOW_CHANNEL_ID", "UW_TICKER_CHANNEL_ID"):
        ch = _channel_id(key)
        if ch:
            uw_channels.add(ch)

    if message.channel.id not in uw_channels:
        return

    try:
        from discord_bridge.uw_parser import parse_and_forward
        await parse_and_forward(message)
    except ImportError:
        pass  # UW parser not yet deployed
    except Exception as exc:
        logger.error(f"UW parse error: {exc}", exc_info=True)


async def _handle_chat_message(message: discord.Message) -> None:
    """
    Classify and dispatch a #pivot-chat message to the correct handler.
    """
    from chat.router import classify
    from chat import handlers

    intent, confidence = classify(message.content)
    logger.info(
        f"Chat: intent={intent} conf={confidence:.1f} "
        f"msg={message.content[:80]!r}"
    )

    handler_map = {
        "trade_idea": handlers.handle_trade_idea,
        "trade_open": handlers.handle_trade_open,
        "trade_close": handlers.handle_trade_close,
        "status": handlers.handle_status,
        "quote": handlers.handle_quote,
        "review": handlers.handle_review,
        "question": handlers.handle_question,
    }

    handler = handler_map.get(intent, handlers.handle_question)

    try:
        async with message.channel.typing():
            response = await handler(message.content)
        await send_long_message(message.channel, response)
    except Exception as exc:
        logger.error(f"Chat handler error (intent={intent}): {exc}", exc_info=True)
        await message.channel.send(f"⚠️ Something went wrong: {str(exc)[:200]}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_bot() -> None:
    """Configure logging and start the Discord bot. Called by pivot/bot.py."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        logger.error("DISCORD_BOT_TOKEN not set — bot cannot start")
        return

    logger.info("Starting Pivot Discord bot...")
    bot.run(token)
