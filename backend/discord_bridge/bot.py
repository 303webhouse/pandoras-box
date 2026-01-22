"""
Pandora Bridge - Discord Bot
Bridges Unusual Whales alerts from Discord to Pandora's Box

This bot:
1. Watches #flow-alerts channel for UW bot messages
2. Parses the flow data from embeds
3. Sends to Pandora's Box API
4. Auto-scores each alert
"""

import os
import re
import asyncio
import logging
import aiohttp
from datetime import datetime

# Discord.py imports
try:
    import discord
    from discord.ext import commands
except ImportError:
    print("discord.py not installed. Run: pip install discord.py")
    raise

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
FLOW_CHANNEL_ID = int(os.getenv("DISCORD_FLOW_CHANNEL_ID", "1463692055694807201"))
PANDORA_API_URL = os.getenv("PANDORA_API_URL", "https://pandoras-box-production.up.railway.app/api")

# UW Bot user ID (we'll detect by username if needed)
UW_BOT_NAMES = ["unusual_whales_crier", "Unusual Whales Options Bot"]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PandoraBridge")

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)


def parse_flow_from_embed(embed: discord.Embed) -> dict:
    """
    Parse flow data from a UW bot embed
    
    Returns dict with:
    - ticker: str
    - sentiment: BULLISH/BEARISH
    - flow_type: SWEEP/BLOCK/etc
    - premium: int
    - details: str
    """
    try:
        # Get title - usually contains ticker and flow type
        title = embed.title or ""
        description = embed.description or ""
        
        # Extract ticker from title (e.g., "SPY - $100K+ Flow - Wed Jan 21")
        ticker_match = re.match(r'^([A-Z]+)', title)
        ticker = ticker_match.group(1) if ticker_match else "UNKNOWN"
        
        # Determine sentiment from embed color or content
        # Green = bullish, Red = bearish
        sentiment = "NEUTRAL"
        if embed.color:
            color_value = embed.color.value
            if color_value == 0x00FF00 or color_value == 0x2ECC71:  # Green
                sentiment = "BULLISH"
            elif color_value == 0xFF0000 or color_value == 0xE74C3C:  # Red
                sentiment = "BEARISH"
        
        # Look for call/put indicators in description
        desc_lower = description.lower()
        if "call" in desc_lower or "bullish" in desc_lower:
            sentiment = "BULLISH"
        elif "put" in desc_lower or "bearish" in desc_lower:
            sentiment = "BEARISH"
        
        # Try to extract premium amount
        premium = 100000  # Default
        premium_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d+)?)\s*[KkMm]?', title + description)
        if premium_match:
            amount_str = premium_match.group(1).replace(',', '')
            premium = int(float(amount_str))
            # Check for K/M suffix
            if 'k' in title.lower() or 'K' in title:
                premium *= 1000
            elif 'm' in title.lower() or 'M' in title:
                premium *= 1000000
        
        # Determine flow type
        flow_type = "UNUSUAL_VOLUME"
        if "sweep" in desc_lower or "sweep" in title.lower():
            flow_type = "SWEEP"
        elif "block" in desc_lower or "block" in title.lower():
            flow_type = "BLOCK"
        elif "dark" in desc_lower or "dark pool" in title.lower():
            flow_type = "DARK_POOL"
        
        # Parse fields if available
        fields_text = []
        for field in embed.fields:
            fields_text.append(f"{field.name}: {field.value}")
        
        return {
            "ticker": ticker,
            "sentiment": sentiment,
            "flow_type": flow_type,
            "premium": premium,
            "notes": f"Auto-imported from UW Discord. {' | '.join(fields_text)}"[:500],
            "source": "discord_bridge",
            "raw_title": title,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error parsing embed: {e}")
        return None


def parse_flow_from_image(message: discord.Message) -> dict:
    """
    Parse flow data from UW bot messages that use images/tables
    
    The UW bot often sends flow as an image table. We extract what we can
    from the message text and any embeds.
    """
    try:
        # Check for embeds first
        if message.embeds:
            for embed in message.embeds:
                result = parse_flow_from_embed(embed)
                if result:
                    return result
        
        # Parse from message content
        content = message.content or ""
        
        # Look for ticker mentions
        ticker_match = re.search(r'\b([A-Z]{1,5})\b', content)
        ticker = ticker_match.group(1) if ticker_match else None
        
        # If no useful data, return None
        if not ticker:
            return None
        
        return {
            "ticker": ticker,
            "sentiment": "NEUTRAL",
            "flow_type": "UNUSUAL_VOLUME",
            "premium": 100000,
            "notes": f"Auto-imported from UW Discord: {content[:200]}",
            "source": "discord_bridge",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error parsing message: {e}")
        return None


async def send_to_pandora(flow_data: dict) -> bool:
    """Send parsed flow data to Pandora's Box API"""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "ticker": flow_data["ticker"],
                "sentiment": flow_data["sentiment"],
                "flow_type": flow_data["flow_type"],
                "premium": flow_data["premium"],
                "notes": flow_data.get("notes", "")
            }
            
            async with session.post(
                f"{PANDORA_API_URL}/flow/manual",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ Sent to Pandora: {flow_data['ticker']} - {flow_data['sentiment']}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Pandora API error: {response.status} - {error_text}")
                    return False
                    
    except asyncio.TimeoutError:
        logger.error("❌ Timeout sending to Pandora API")
        return False
    except Exception as e:
        logger.error(f"❌ Error sending to Pandora: {e}")
        return False


@bot.event
async def on_ready():
    """Called when bot is connected and ready"""
    logger.info(f"🐋 Pandora Bridge connected as {bot.user}")
    logger.info(f"📡 Watching channel ID: {FLOW_CHANNEL_ID}")
    
    # Find and verify the channel
    channel = bot.get_channel(FLOW_CHANNEL_ID)
    if channel:
        logger.info(f"✅ Found channel: #{channel.name}")
        # Send a startup message
        try:
            await channel.send("🔗 **Pandora Bridge Online** - Now forwarding flow alerts to Pandora's Box!")
        except discord.Forbidden:
            logger.warning("Cannot send messages to channel (no permission)")
    else:
        logger.error(f"❌ Could not find channel {FLOW_CHANNEL_ID}")


@bot.event
async def on_message(message: discord.Message):
    """Process incoming messages"""
    
    # Ignore our own messages
    if message.author == bot.user:
        return
    
    # Only process messages from the flow alerts channel
    if message.channel.id != FLOW_CHANNEL_ID:
        return
    
    # Check if message is from UW bot
    author_name = message.author.name.lower()
    is_uw_bot = any(name.lower() in author_name for name in UW_BOT_NAMES)
    
    # Also check if it's from a bot with relevant content
    if not is_uw_bot and not message.author.bot:
        return  # Skip non-bot messages unless they're from UW
    
    logger.info(f"📨 Processing message from {message.author.name}")
    
    # Try to parse the flow data
    flow_data = None
    
    # First try embeds
    if message.embeds:
        for embed in message.embeds:
            flow_data = parse_flow_from_embed(embed)
            if flow_data:
                break
    
    # If no embed data, try message content
    if not flow_data:
        flow_data = parse_flow_from_image(message)
    
    # Send to Pandora if we got valid data
    if flow_data and flow_data.get("ticker"):
        success = await send_to_pandora(flow_data)
        
        # React to the message to show we processed it
        try:
            if success:
                await message.add_reaction("✅")
            else:
                await message.add_reaction("⚠️")
        except discord.Forbidden:
            pass  # No permission to add reactions
    
    # Process commands if any
    await bot.process_commands(message)


@bot.command(name="status")
async def status_command(ctx):
    """Check bridge status"""
    await ctx.send(f"🔗 **Pandora Bridge Status**\n"
                   f"• Connected: ✅\n"
                   f"• Watching: <#{FLOW_CHANNEL_ID}>\n"
                   f"• API: {PANDORA_API_URL}")


@bot.command(name="test")
async def test_command(ctx, ticker: str = "TEST"):
    """Send a test flow to Pandora"""
    test_flow = {
        "ticker": ticker.upper(),
        "sentiment": "BULLISH",
        "flow_type": "SWEEP",
        "premium": 250000,
        "notes": "Manual test from Discord bridge"
    }
    
    success = await send_to_pandora(test_flow)
    
    if success:
        await ctx.send(f"✅ Test flow sent for **{ticker.upper()}**")
    else:
        await ctx.send(f"❌ Failed to send test flow")


def run_bot():
    """Run the Discord bot"""
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_BOT_TOKEN environment variable not set!")
        logger.error("Set it with: export DISCORD_BOT_TOKEN='your-token-here'")
        return
    
    logger.info("🚀 Starting Pandora Bridge...")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    run_bot()
