"""
Pandora Bridge - Discord Bot (v2.0)
Bridges Unusual Whales data from Discord to Pandora's Box

This bot:
1. WATCHES for UW bot responses and parses them
2. SENDS scheduled queries to UW bot (market_tide, sectorflow, etc.)
3. POSTS parsed data to Pandora's Box API for bias integration
4. CONFIRMS flow before trades on-demand

Scheduled Queries:
- /market_tide: 9:35 AM, 12:00 PM, 3:30 PM ET (Daily Bias)
- /sectorflow: Monday 10:00 AM ET (Weekly Bias)
- /oi_increase: Monday 10:00 AM ET (Weekly Bias)
- /economic_calendar: Daily 8:30 AM ET (Event awareness)
"""

import os
import re
import asyncio
import logging
import aiohttp
from datetime import datetime, time, timezone
from typing import Optional, Dict, Any, List
import pytz
from utils.vision_parser import parse_uw_image
from discord_bridge.uw.parser import parse_flow_embed, parse_ticker_embed
from discord_bridge.uw.filter import FlowFilter
from discord_bridge.uw.aggregator import FlowAggregator

# Discord.py imports
try:
    import discord
    from discord.ext import commands, tasks
except ImportError:
    print("discord.py not installed. Run: pip install discord.py")
    raise

# ================================
# CONFIGURATION
# ================================

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PIVOT_API_KEY = os.getenv("PIVOT_API_KEY", "")
UW_CHANNEL_ID = int(os.getenv("DISCORD_UW_CHANNEL_ID", "1463692055694807201"))
UW_FLOW_CHANNEL_ID = int(os.getenv("UW_FLOW_CHANNEL_ID", "0"))
UW_TICKER_CHANNEL_ID = int(os.getenv("UW_TICKER_CHANNEL_ID", "0"))
UW_BOT_USER_ID = int(os.getenv("UW_BOT_USER_ID", "1100705854271008798"))
PANDORA_API_URL = os.getenv("PANDORA_API_URL", "https://pandoras-box-production.up.railway.app/api")
NOTIFICATION_CHANNEL_ID = int(os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID", str(UW_CHANNEL_ID)))
TRADE_ALERT_CHANNEL_ID = int(os.getenv("DISCORD_TRADE_ALERT_CHANNEL_ID", str(NOTIFICATION_CHANNEL_ID)))
MIN_SCORE_FOR_ALERT = int(os.getenv("DISCORD_MIN_SCORE_FOR_ALERT", "80"))

# UW Bot identification
UW_BOT_NAMES = ["unusual_whales_crier", "unusual whales", "uw"]

# Timezone for market hours
ET = pytz.timezone('America/New_York')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PandoraBridge")

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================================
# STATE TRACKING
# ================================

# Track pending queries so we know what response to expect
pending_queries = {
    "market_tide": False,
    "sectorflow": False,
    "oi_increase": False,
    "oi_decrease": False,
    "economic_calendar": False,
    "congress_recent": False,
    "flow_ticker": None,  # Will store ticker name when querying
    "max_pain": None,
    "overview": None,
}

# Store latest parsed data
latest_data = {
    "market_tide": None,
    "sectorflow": None,
    "oi_increase": None,
    "economic_calendar": None,
}

_seen_signal_ids: set[str] = set()
uw_flow_filter = FlowFilter()
uw_flow_aggregator = FlowAggregator()

# ================================
# HELPER FUNCTIONS
# ================================

def get_et_now() -> datetime:
    """Get current time in Eastern Time"""
    return datetime.now(ET)

def is_market_hours() -> bool:
    """Check if market is open (9:30 AM - 4:00 PM ET, weekdays)"""
    now = get_et_now()
    if now.weekday() >= 5:  # Weekend
        return False
    market_open = time(9, 30)
    market_close = time(16, 0)
    return market_open <= now.time() <= market_close

def is_trading_day() -> bool:
    """Check if today is a trading day (weekday)"""
    return get_et_now().weekday() < 5

# ================================
# UW RESPONSE PARSERS
# ================================

def parse_market_tide(embed: discord.Embed) -> Optional[Dict[str, Any]]:
    """
    Parse /market_tide response
    
    Expected format varies but typically includes:
    - Bullish/Bearish percentages
    - Overall sentiment
    """
    try:
        title = (embed.title or "").lower()
        description = embed.description or ""
        
        # Check if this is a market tide response
        if "tide" not in title and "market" not in title:
            return None
        
        result = {
            "type": "market_tide",
            "timestamp": datetime.now().isoformat(),
            "raw_text": description,
            "bullish_pct": None,
            "bearish_pct": None,
            "sentiment": "NEUTRAL"
        }
        
        # Try to extract percentages
        # Pattern: "Bullish: 65%" or "65% bullish"
        bullish_match = re.search(r'(\d+(?:\.\d+)?)\s*%?\s*bull', description, re.IGNORECASE)
        bearish_match = re.search(r'(\d+(?:\.\d+)?)\s*%?\s*bear', description, re.IGNORECASE)
        
        if bullish_match:
            result["bullish_pct"] = float(bullish_match.group(1))
        if bearish_match:
            result["bearish_pct"] = float(bearish_match.group(1))
        
        # Determine sentiment
        if result["bullish_pct"] and result["bearish_pct"]:
            if result["bullish_pct"] > result["bearish_pct"] + 10:
                result["sentiment"] = "BULLISH"
            elif result["bearish_pct"] > result["bullish_pct"] + 10:
                result["sentiment"] = "BEARISH"
        
        # Also check for explicit sentiment words
        if "strongly bullish" in description.lower():
            result["sentiment"] = "STRONGLY_BULLISH"
        elif "strongly bearish" in description.lower():
            result["sentiment"] = "STRONGLY_BEARISH"
        
        # Parse fields for additional data
        for field in embed.fields:
            field_name = field.name.lower()
            field_value = field.value
            
            if "call" in field_name:
                call_match = re.search(r'\$?([\d,]+)', field_value)
                if call_match:
                    result["call_premium"] = int(call_match.group(1).replace(',', ''))
            elif "put" in field_name:
                put_match = re.search(r'\$?([\d,]+)', field_value)
                if put_match:
                    result["put_premium"] = int(put_match.group(1).replace(',', ''))
        
        logger.info(f"📊 Parsed market_tide: {result['sentiment']}")
        return result
        
    except Exception as e:
        logger.error(f"Error parsing market_tide: {e}")
        return None


def parse_sectorflow(embed: discord.Embed) -> Optional[Dict[str, Any]]:
    """
    Parse /sectorflow response
    
    Expected format: List of sectors with flow direction
    """
    try:
        title = (embed.title or "").lower()
        description = embed.description or ""
        
        if "sector" not in title and "sector" not in description.lower():
            return None
        
        result = {
            "type": "sectorflow",
            "timestamp": datetime.now().isoformat(),
            "sectors": {},
            "bullish_sectors": [],
            "bearish_sectors": []
        }
        
        # Common sector names to look for
        sectors = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB", "XLRE", "XLC"]
        
        all_text = f"{description} "
        for field in embed.fields:
            all_text += f"{field.name} {field.value} "
        
        # Parse each sector
        for sector in sectors:
            # Look for sector with sentiment indicator
            pattern = rf'{sector}[:\s]*([^\n]+)'
            match = re.search(pattern, all_text, re.IGNORECASE)
            if match:
                context = match.group(1).lower()
                if any(word in context for word in ["bullish", "call", "green", "↑", "+"]):
                    result["sectors"][sector] = "BULLISH"
                    result["bullish_sectors"].append(sector)
                elif any(word in context for word in ["bearish", "put", "red", "↓", "-"]):
                    result["sectors"][sector] = "BEARISH"
                    result["bearish_sectors"].append(sector)
                else:
                    result["sectors"][sector] = "NEUTRAL"
        
        logger.info(f"📊 Parsed sectorflow: {len(result['bullish_sectors'])} bullish, {len(result['bearish_sectors'])} bearish")
        return result
        
    except Exception as e:
        logger.error(f"Error parsing sectorflow: {e}")
        return None


def parse_oi_change(embed: discord.Embed, increase: bool = True) -> Optional[Dict[str, Any]]:
    """
    Parse /oi_increase or /oi_decrease response
    
    Expected format: List of contracts with OI changes
    """
    try:
        title = (embed.title or "").lower()
        description = embed.description or ""
        
        keyword = "increase" if increase else "decrease"
        if "oi" not in title and "open interest" not in title.lower():
            return None
        
        result = {
            "type": f"oi_{keyword}",
            "timestamp": datetime.now().isoformat(),
            "contracts": [],
            "tickers_bullish": [],
            "tickers_bearish": []
        }
        
        all_text = f"{description} "
        for field in embed.fields:
            all_text += f"{field.name}: {field.value}\n"
        
        # Parse ticker patterns like "AAPL 150C 2/21" or "NVDA $500 Put"
        # This is a simplified parser - UW format may vary
        lines = all_text.split('\n')
        for line in lines:
            ticker_match = re.search(r'\b([A-Z]{1,5})\b', line)
            if ticker_match:
                ticker = ticker_match.group(1)
                is_call = 'call' in line.lower() or 'c' in line.lower()
                is_put = 'put' in line.lower() or 'p' in line.lower()
                
                contract = {
                    "ticker": ticker,
                    "type": "CALL" if is_call else "PUT" if is_put else "UNKNOWN",
                    "raw": line.strip()[:100]
                }
                result["contracts"].append(contract)
                
                # OI increase in calls = bullish, puts = bearish
                if increase:
                    if is_call:
                        result["tickers_bullish"].append(ticker)
                    elif is_put:
                        result["tickers_bearish"].append(ticker)
                else:
                    # OI decrease in calls = less bullish, puts = less bearish
                    pass
        
        logger.info(f"📊 Parsed oi_{keyword}: {len(result['contracts'])} contracts")
        return result
        
    except Exception as e:
        logger.error(f"Error parsing oi_change: {e}")
        return None


def parse_economic_calendar(embed: discord.Embed) -> Optional[Dict[str, Any]]:
    """
    Parse /economic_calendar response
    """
    try:
        title = (embed.title or "").lower()
        description = embed.description or ""
        
        if "economic" not in title and "calendar" not in title:
            return None
        
        result = {
            "type": "economic_calendar",
            "timestamp": datetime.now().isoformat(),
            "events": [],
            "high_impact_today": False
        }
        
        all_text = f"{description} "
        for field in embed.fields:
            all_text += f"{field.name}: {field.value}\n"
            
            # Each field might be an event
            event = {
                "name": field.name,
                "details": field.value,
                "high_impact": any(word in field.value.lower() for word in ["fomc", "cpi", "nfp", "gdp", "pce", "fed"])
            }
            result["events"].append(event)
            
            if event["high_impact"]:
                result["high_impact_today"] = True
        
        logger.info(f"📊 Parsed economic_calendar: {len(result['events'])} events, high_impact={result['high_impact_today']}")
        return result
        
    except Exception as e:
        logger.error(f"Error parsing economic_calendar: {e}")
        return None


def parse_flow_alert(embed: discord.Embed) -> Optional[Dict[str, Any]]:
    """
    Parse general flow alert from UW bot
    """
    try:
        title = embed.title or ""
        description = embed.description or ""
        
        result = {
            "type": "flow_alert",
            "timestamp": datetime.now().isoformat(),
            "ticker": None,
            "sentiment": "NEUTRAL",
            "flow_type": "UNUSUAL_VOLUME",
            "premium": 100000,
            "notes": ""
        }
        
        combined = f"{title} {description}"
        
        # Extract ticker
        ticker_match = re.match(r'^([A-Z]{1,5})\b', title)
        if not ticker_match:
            ticker_match = re.search(r'\b([A-Z]{1,5})\s*[-–]\s*\$', combined)
        if not ticker_match:
            ticker_match = re.search(r'\b([A-Z]{2,5})\b', combined)
        
        if ticker_match:
            result["ticker"] = ticker_match.group(1)
        
        # Determine sentiment from color and content
        if embed.color:
            color_value = embed.color.value
            if color_value in [0x00FF00, 0x2ECC71, 0x00ff00]:  # Green
                result["sentiment"] = "BULLISH"
            elif color_value in [0xFF0000, 0xE74C3C, 0xff0000]:  # Red
                result["sentiment"] = "BEARISH"
        
        desc_lower = description.lower()
        if "call" in desc_lower or "bullish" in desc_lower:
            result["sentiment"] = "BULLISH"
        elif "put" in desc_lower or "bearish" in desc_lower:
            result["sentiment"] = "BEARISH"
        
        # Extract premium
        premium_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d+)?)\s*([KkMm])?', combined)
        if premium_match:
            amount = float(premium_match.group(1).replace(',', ''))
            suffix = premium_match.group(2)
            if suffix and suffix.lower() == 'k':
                amount *= 1000
            elif suffix and suffix.lower() == 'm':
                amount *= 1000000
            result["premium"] = int(amount)
        
        # Determine flow type
        if "sweep" in desc_lower:
            result["flow_type"] = "SWEEP"
        elif "block" in desc_lower:
            result["flow_type"] = "BLOCK"
        elif "dark" in desc_lower:
            result["flow_type"] = "DARK_POOL"
        
        result["notes"] = f"Auto-parsed from UW: {title[:100]}"
        
        if result["ticker"]:
            logger.info(f"📊 Parsed flow_alert: {result['ticker']} {result['sentiment']}")
            return result
        
        return None
        
    except Exception as e:
        logger.error(f"Error parsing flow_alert: {e}")
        return None


# ================================
# API COMMUNICATION
# ================================

async def send_to_pandora(endpoint: str, data: Dict[str, Any]) -> bool:
    """Send parsed data to Pandora's Box API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{PANDORA_API_URL}{endpoint}"
            headers = {}
            if PIVOT_API_KEY:
                headers["Authorization"] = f"Bearer {PIVOT_API_KEY}"
            async with session.post(
                url,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    logger.info(f"✅ Sent to Pandora {endpoint}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Pandora API error: {response.status} - {error_text}")
                    return False
    except asyncio.TimeoutError:
        logger.error(f"❌ Timeout sending to {endpoint}")
        return False
    except Exception as e:
        logger.error(f"❌ Error sending to Pandora: {e}")
        return False


async def send_market_tide_to_pandora(data: Dict[str, Any]) -> bool:
    """Send market tide data to update Daily Bias"""
    payload = {
        "source": "uw_market_tide",
        "sentiment": data.get("sentiment", "NEUTRAL"),
        "bullish_pct": data.get("bullish_pct"),
        "bearish_pct": data.get("bearish_pct"),
        "call_premium": data.get("call_premium"),
        "put_premium": data.get("put_premium"),
        "timestamp": data.get("timestamp")
    }
    return await send_to_pandora("/bias/uw/market_tide", payload)


async def send_sectorflow_to_pandora(data: Dict[str, Any]) -> bool:
    """Send sector flow data to update Weekly Bias"""
    payload = {
        "source": "uw_sectorflow",
        "sectors": data.get("sectors", {}),
        "bullish_sectors": data.get("bullish_sectors", []),
        "bearish_sectors": data.get("bearish_sectors", []),
        "timestamp": data.get("timestamp")
    }
    return await send_to_pandora("/bias/uw/sectorflow", payload)


async def send_flow_alert_to_pandora(data: Dict[str, Any]) -> bool:
    """Send flow alert for trade confirmation"""
    payload = {
        "ticker": data.get("ticker"),
        "sentiment": data.get("sentiment"),
        "flow_type": data.get("flow_type"),
        "premium": data.get("premium"),
        "notes": data.get("notes", "")
    }
    return await send_to_pandora("/flow/manual", payload)


async def push_uw_aggregates() -> None:
    """Push UW flow summaries and discovery list to Pandora."""
    flow_summaries = uw_flow_aggregator.get_flow_summaries()
    if flow_summaries:
        await send_to_pandora(
            "/uw/flow",
            {
                "summaries": flow_summaries,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info("Pushed UW flow summaries: %s tickers", len(flow_summaries))

    discovery = uw_flow_aggregator.get_discovery_list()
    if discovery:
        await send_to_pandora(
            "/uw/discovery",
            {
                "tickers": discovery,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info("Pushed UW discovery list: %s tickers", len(discovery))


def format_uw_summary(data: Dict[str, Any]) -> Optional[str]:
    """Format a short summary of parsed UW data."""
    data_type = data.get("data_type", "other")

    if data_type == "highest_volume_contracts":
        contracts = data.get("contracts", [])
        calls = data.get("total_calls", 0)
        puts = data.get("total_puts", 0)
        sentiment = data.get("sentiment", "NEUTRAL")
        return f"Parsed {len(contracts)} contracts | Calls: {calls} | Puts: {puts} | Sentiment: {sentiment}"

    if data_type == "market_tide":
        bull = data.get("bullish_pct", "?")
        bear = data.get("bearish_pct", "?")
        sentiment = data.get("sentiment", "NEUTRAL")
        return f"Market Tide | Bull: {bull}% | Bear: {bear}% | Sentiment: {sentiment}"

    if data_type == "sector_flow":
        bullish = ", ".join(data.get("bullish_sectors", [])[:3]) or "None"
        bearish = ", ".join(data.get("bearish_sectors", [])[:3]) or "None"
        overall = data.get("overall_sentiment", "NEUTRAL")
        return f"Sector Flow | Bullish: {bullish} | Bearish: {bearish} | Overall: {overall}"

    if data_type == "economic_calendar":
        high_impact = data.get("high_impact_count", 0)
        caution = "CAUTION" if data.get("trading_caution") else "Clear"
        return f"Economic Calendar | High-impact events: {high_impact} | {caution}"

    if data_type == "flow_alerts":
        alerts = data.get("alerts", [])
        sentiment = data.get("dominant_sentiment", "MIXED")
        return f"Flow Alerts | {len(alerts)} alerts | Sentiment: {sentiment}"

    return None


# ================================
# QUERY FUNCTIONS
# ================================

async def send_uw_command(channel: discord.TextChannel, command: str):
    """Send a slash command to the UW bot"""
    # Note: We can't actually invoke slash commands programmatically
    # Instead, we send the command as a message and hope UW bot responds
    # OR we use Discord's interaction system if UW supports it
    
    # For now, we'll send it as a message - some bots respond to this
    try:
        await channel.send(command)
        logger.info(f"📤 Sent query: {command}")
    except Exception as e:
        logger.error(f"❌ Failed to send query: {e}")


# ================================
# SCHEDULED TASKS
# ================================

@tasks.loop(minutes=1)
async def scheduled_queries():
    """Run scheduled UW queries based on time of day"""
    now = get_et_now()
    current_time = now.strftime("%H:%M")
    weekday = now.weekday()
    
    channel = bot.get_channel(UW_CHANNEL_ID)
    if not channel:
        return
    
    # Market Tide: 9:35 AM, 12:00 PM, 3:30 PM ET on trading days
    if is_trading_day():
        if current_time in ["09:35", "12:00", "15:30"]:
            pending_queries["market_tide"] = True
            await send_uw_command(channel, "/market_tide")
    
    # Sector Flow: Monday 10:00 AM ET
    if weekday == 0 and current_time == "10:00":
        pending_queries["sectorflow"] = True
        await send_uw_command(channel, "/sectorflow")
    
    # OI Increase: Monday 10:05 AM ET (stagger to avoid rate limits)
    if weekday == 0 and current_time == "10:05":
        pending_queries["oi_increase"] = True
        await send_uw_command(channel, "/oi_increase")
    
    # Economic Calendar: Daily 8:30 AM ET
    if is_trading_day() and current_time == "08:30":
        pending_queries["economic_calendar"] = True
        await send_uw_command(channel, "/economic_calendar")


@tasks.loop(minutes=1)
async def reminder_scheduler():
    """Send reminders for manual UW commands."""
    now = get_et_now()
    current_time = now.strftime("%H:%M")
    day_of_week = now.weekday()  # 0=Monday

    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if not channel:
        return

    # Market Tide reminders (weekdays)
    if day_of_week < 5 and current_time in ["09:35", "12:00", "15:30"]:
        await channel.send(
            "Reminder: Time to check market tide.\n"
            "Run `/market_tide` in the UW channel and I'll parse the response."
        )

    # Sector Flow reminder (Monday)
    if day_of_week == 0 and current_time == "10:00":
        await channel.send(
            "Reminder: Weekly sector flow check.\n"
            "Run `/sectorflow` in the UW channel."
        )

    # Economic Calendar (weekdays)
    if day_of_week < 5 and current_time == "08:30":
        await channel.send(
            "Reminder: Check economic calendar.\n"
            "Run `/economic_calendar` in the UW channel."
        )


@reminder_scheduler.before_loop
async def before_reminder_scheduler():
    await bot.wait_until_ready()


@tasks.loop(minutes=2)
async def trade_idea_poller():
    """Poll for new high-score trade ideas and post to Discord."""
    global _seen_signal_ids

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{PANDORA_API_URL}/signals/active") as resp:
                if resp.status != 200:
                    return
                data = await resp.json()

        signals = data.get("signals", [])
        channel = bot.get_channel(TRADE_ALERT_CHANNEL_ID)
        if not channel:
            return

        for signal in signals:
            signal_id = signal.get("signal_id")
            score = signal.get("score", 0)

            if not signal_id:
                continue
            if signal_id in _seen_signal_ids:
                continue
            if score < MIN_SCORE_FOR_ALERT:
                _seen_signal_ids.add(signal_id)
                continue

            _seen_signal_ids.add(signal_id)
            embed = format_trade_idea_embed(signal)
            await channel.send(embed=embed)
            logger.info(f"Posted trade alert: {signal.get('ticker')} score={score}")

        # Cleanup old IDs (keep last 500)
        if len(_seen_signal_ids) > 500:
            _seen_signal_ids = set(list(_seen_signal_ids)[-500:])

    except Exception as e:
        logger.error(f"Error polling trade ideas: {e}")


@trade_idea_poller.before_loop
async def before_trade_poller():
    await bot.wait_until_ready()


@tasks.loop(minutes=5)
async def uw_aggregate_poller():
    """Push UW aggregates (flow + discovery) to Pandora."""
    if not UW_FLOW_CHANNEL_ID and not UW_TICKER_CHANNEL_ID:
        return
    await push_uw_aggregates()


@uw_aggregate_poller.before_loop
async def before_uw_aggregate_poller():
    await bot.wait_until_ready()


def format_trade_idea_embed(signal: Dict[str, Any]) -> discord.Embed:
    """Format a trade signal as a Discord embed."""
    ticker = signal.get("ticker", "???")
    direction = signal.get("direction", "???")
    score = signal.get("score", 0)
    strategy = signal.get("strategy", "Unknown")
    entry = signal.get("entry_price", 0)
    stop = signal.get("stop_loss", 0)
    target = signal.get("target_1", 0)

    color = 0x00FF00 if direction == "LONG" else 0xFF0000
    embed = discord.Embed(
        title=f"Trade Idea: {ticker} {direction}",
        color=color
    )

    embed.add_field(name="Score", value=f"{score:.0f}/100", inline=True)
    embed.add_field(name="Strategy", value=strategy, inline=True)
    embed.add_field(name="Direction", value=direction, inline=True)

    embed.add_field(name="Entry", value=f"${entry:.2f}", inline=True)
    embed.add_field(name="Stop", value=f"${stop:.2f}", inline=True)
    embed.add_field(name="Target", value=f"${target:.2f}", inline=True)

    if entry and stop and target:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        embed.add_field(name="R:R", value=f"{rr:.1f}:1", inline=True)

    alignment = signal.get("bias_alignment", "Unknown")
    embed.add_field(name="Bias", value=alignment, inline=True)

    signal_id = signal.get("signal_id", "N/A")
    embed.set_footer(text=f"Signal ID: {str(signal_id)[:8]}")
    embed.timestamp = datetime.now()

    return embed


@scheduled_queries.before_loop
async def before_scheduled_queries():
    """Wait until bot is ready before starting scheduled tasks"""
    await bot.wait_until_ready()
    logger.info("⏰ Scheduled queries task started")


# ================================
# EVENT HANDLERS
# ================================

@bot.event
async def on_ready():
    """Called when bot is connected and ready"""
    logger.info(f"🐋 Pandora Bridge v2.0 connected as {bot.user}")
    logger.info(f"📡 Watching channel ID: {UW_CHANNEL_ID}")
    
    # Find and verify the channel
    channel = bot.get_channel(UW_CHANNEL_ID)
    if channel:
        logger.info(f"✅ Found channel: #{channel.name}")
        try:
            await channel.send("🔗 **Pandora Bridge v2.0 Online**\n"
                             "• Watching for UW alerts\n"
                             "• Scheduled queries active\n"
                             "• Type `!help_pandora` for commands")
        except discord.Forbidden:
            logger.warning("Cannot send messages to channel (no permission)")
    else:
        logger.error(f"❌ Could not find channel {UW_CHANNEL_ID}")
    
    # Start scheduled tasks
    if not scheduled_queries.is_running():
        scheduled_queries.start()
    if not reminder_scheduler.is_running():
        reminder_scheduler.start()
    if not trade_idea_poller.is_running():
        trade_idea_poller.start()
    if not uw_aggregate_poller.is_running():
        uw_aggregate_poller.start()

    logger.info(
        "Task status: scheduled_queries=%s, reminder_scheduler=%s, trade_idea_poller=%s, uw_aggregate_poller=%s",
        "running" if scheduled_queries.is_running() else "stopped",
        "running" if reminder_scheduler.is_running() else "stopped",
        "running" if trade_idea_poller.is_running() else "stopped",
        "running" if uw_aggregate_poller.is_running() else "stopped",
    )


async def handle_uw_flow_message(message: discord.Message) -> None:
    for embed in message.embeds:
        parsed = parse_flow_embed(embed)
        if parsed is None:
            continue
        if not uw_flow_filter.passes(parsed):
            logger.debug(
                "Filtered UW flow: %s DTE=%s reason=%s",
                parsed.get("ticker"),
                parsed.get("dte"),
                uw_flow_filter.last_reject_reason,
            )
            continue
        uw_flow_aggregator.add_flow(parsed)
        logger.info(
            "UW Flow: %s %s %s premium=%s",
            parsed.get("ticker"),
            parsed.get("side"),
            parsed.get("option_type"),
            parsed.get("premium"),
        )


async def handle_uw_ticker_message(message: discord.Message) -> None:
    for embed in message.embeds:
        parsed = parse_ticker_embed(embed)
        if parsed is None:
            continue
        uw_flow_aggregator.update_ticker_summary(parsed)
        logger.info("UW Ticker Update: %s", parsed.get("ticker"))


@bot.event
async def on_message(message: discord.Message):
    """Process incoming messages"""
    
    # Ignore our own messages
    if message.author == bot.user:
        return
    
    # Process commands first
    await bot.process_commands(message)

    uw_channels = {UW_FLOW_CHANNEL_ID, UW_TICKER_CHANNEL_ID}
    if message.channel.id in uw_channels and any(uw_channels):
        if message.author.id != UW_BOT_USER_ID:
            return
        if message.channel.id == UW_FLOW_CHANNEL_ID:
            await handle_uw_flow_message(message)
        elif message.channel.id == UW_TICKER_CHANNEL_ID:
            await handle_uw_ticker_message(message)
        return

    # Only process UW responses in the designated channel
    if message.channel.id != UW_CHANNEL_ID:
        return
    
    # Check if message is from UW bot
    author_name = message.author.name.lower()
    is_uw_bot = any(name.lower() in author_name for name in UW_BOT_NAMES) or message.author.bot
    
    if not is_uw_bot:
        return
    
    logger.info(f"📨 Processing message from {message.author.name}")
    
    # Check for UW image posts and parse with vision
    image_url = None

    for attachment in message.attachments:
        if attachment.content_type and "image" in attachment.content_type:
            image_url = attachment.url
            break

    if not image_url:
        for embed in message.embeds:
            if embed.image and embed.image.url:
                image_url = embed.image.url
                break

    if image_url:
        logger.info("UW image detected, parsing with AI vision...")
        parsed_data = await parse_uw_image(image_url)

        if parsed_data:
            data_type = parsed_data.get("data_type", "other")

            endpoint_map = {
                "highest_volume_contracts": "/bias/uw/highest_volume",
                "market_tide": "/bias/uw/market_tide",
                "sector_flow": "/bias/uw/sectorflow",
                "economic_calendar": "/bias/uw/economic_calendar",
                "flow_alerts": "/bias/uw/flow_alerts",
                "oi_change": "/bias/uw/flow_alerts",
                "other": "/bias/uw/generic"
            }

            endpoint = endpoint_map.get(data_type, "/bias/uw/generic")
            await send_to_pandora(endpoint, parsed_data)

            sentiment = (
                parsed_data.get("sentiment")
                or parsed_data.get("overall_sentiment")
                or parsed_data.get("dominant_sentiment")
                or "UNKNOWN"
            )
            logger.info(f"Parsed UW {data_type}: sentiment={sentiment}")

            summary = format_uw_summary(parsed_data)
            if summary:
                await message.channel.send(summary)
    
    # Process embeds
    for embed in message.embeds:
        parsed_data = None
        
        # Try each parser based on pending queries or content
        if pending_queries["market_tide"]:
            parsed_data = parse_market_tide(embed)
            if parsed_data:
                pending_queries["market_tide"] = False
                latest_data["market_tide"] = parsed_data
                await send_market_tide_to_pandora(parsed_data)
                await message.add_reaction("📊")
                continue
        
        if pending_queries["sectorflow"]:
            parsed_data = parse_sectorflow(embed)
            if parsed_data:
                pending_queries["sectorflow"] = False
                latest_data["sectorflow"] = parsed_data
                await send_sectorflow_to_pandora(parsed_data)
                await message.add_reaction("📈")
                continue
        
        if pending_queries["oi_increase"]:
            parsed_data = parse_oi_change(embed, increase=True)
            if parsed_data:
                pending_queries["oi_increase"] = False
                latest_data["oi_increase"] = parsed_data
                await message.add_reaction("📈")
                continue
        
        if pending_queries["economic_calendar"]:
            parsed_data = parse_economic_calendar(embed)
            if parsed_data:
                pending_queries["economic_calendar"] = False
                latest_data["economic_calendar"] = parsed_data
                await message.add_reaction("📅")
                continue
        
        # If no pending query matched, try general flow alert parsing
        parsed_data = parse_flow_alert(embed)
        if parsed_data and parsed_data.get("ticker"):
            await send_flow_alert_to_pandora(parsed_data)
            try:
                await message.add_reaction("✅")
            except discord.Forbidden:
                pass


# ================================
# BOT COMMANDS
# ================================

@bot.command(name="help_pandora")
async def help_command(ctx):
    """Show Pandora Bridge help"""
    help_text = """
🐋 **Pandora Bridge v2.0 Commands**

**Manual Queries:**
• `!tide` - Query market tide now
• `!sector` - Query sector flow now
• `!oi` - Query OI changes now
• `!calendar` - Query economic calendar now
• `!flow TICKER` - Query flow for a specific ticker
• `!maxpain TICKER` - Query max pain for a ticker

**Status:**
• `!status` - Check bot status
• `!latest` - Show latest parsed data

**Testing:**
• `!test TICKER` - Send test flow to Pandora

**Manual Logging:**
• `!logflow AAPL bull sweep 500k` - Log a flow alert manually
• `!logtide bullish 65` - Log market tide manually

**Scheduled Queries (automatic):**
• Market Tide: 9:35 AM, 12:00 PM, 3:30 PM ET
• Sector Flow: Monday 10:00 AM ET
• OI Increase: Monday 10:05 AM ET
• Economic Calendar: Daily 8:30 AM ET
"""
    await ctx.send(help_text)


@bot.command(name="status")
async def status_command(ctx):
    """Check bridge status"""
    now = get_et_now()
    await ctx.send(f"🔗 **Pandora Bridge v2.0 Status**\n"
                   f"• Connected: ✅\n"
                   f"• Channel: <#{UW_CHANNEL_ID}>\n"
                   f"• API: {PANDORA_API_URL}\n"
                   f"• Time (ET): {now.strftime('%H:%M:%S')}\n"
                   f"• Market Hours: {'✅' if is_market_hours() else '❌'}\n"
                   f"• Scheduler: {'Running' if scheduled_queries.is_running() else 'Stopped'}")


@bot.command(name="tasks")
async def tasks_command(ctx):
    """Show background task status"""
    await ctx.send(
        "🧰 **Background Tasks**\n"
        f"• scheduled_queries: {'Running' if scheduled_queries.is_running() else 'Stopped'}\n"
        f"• reminder_scheduler: {'Running' if reminder_scheduler.is_running() else 'Stopped'}\n"
        f"• trade_idea_poller: {'Running' if trade_idea_poller.is_running() else 'Stopped'}"
    )


@bot.command(name="latest")
async def latest_command(ctx):
    """Show latest parsed data"""
    response = "📊 **Latest Parsed Data**\n\n"
    
    for key, data in latest_data.items():
        if data:
            timestamp = data.get("timestamp", "Unknown")
            if key == "market_tide":
                response += f"**Market Tide** ({timestamp[:16]})\n"
                response += f"  Sentiment: {data.get('sentiment', 'N/A')}\n"
                response += f"  Bullish: {data.get('bullish_pct', 'N/A')}%\n"
                response += f"  Bearish: {data.get('bearish_pct', 'N/A')}%\n\n"
            elif key == "sectorflow":
                response += f"**Sector Flow** ({timestamp[:16]})\n"
                response += f"  Bullish: {', '.join(data.get('bullish_sectors', [])) or 'None'}\n"
                response += f"  Bearish: {', '.join(data.get('bearish_sectors', [])) or 'None'}\n\n"
        else:
            response += f"**{key}**: No data yet\n\n"
    
    await ctx.send(response)


@bot.command(name="tide")
async def tide_command(ctx):
    """Manually query market tide"""
    pending_queries["market_tide"] = True
    await send_uw_command(ctx.channel, "/market_tide")
    await ctx.send("📊 Querying market tide...")


@bot.command(name="sector")
async def sector_command(ctx):
    """Manually query sector flow"""
    pending_queries["sectorflow"] = True
    await send_uw_command(ctx.channel, "/sectorflow")
    await ctx.send("📈 Querying sector flow...")


@bot.command(name="oi")
async def oi_command(ctx):
    """Manually query OI changes"""
    pending_queries["oi_increase"] = True
    await send_uw_command(ctx.channel, "/oi_increase")
    await ctx.send("📊 Querying OI increase...")


@bot.command(name="calendar")
async def calendar_command(ctx):
    """Manually query economic calendar"""
    pending_queries["economic_calendar"] = True
    await send_uw_command(ctx.channel, "/economic_calendar")
    await ctx.send("📅 Querying economic calendar...")


@bot.command(name="flow")
async def flow_command(ctx, ticker: str = None):
    """Query flow for a specific ticker"""
    if not ticker:
        await ctx.send("❌ Usage: `!flow TICKER` (e.g., `!flow AAPL`)")
        return
    
    pending_queries["flow_ticker"] = ticker.upper()
    await send_uw_command(ctx.channel, f"/flow_ticker {ticker.upper()}")
    await ctx.send(f"🔍 Querying flow for **{ticker.upper()}**...")


@bot.command(name="maxpain")
async def maxpain_command(ctx, ticker: str = None):
    """Query max pain for a ticker"""
    if not ticker:
        await ctx.send("❌ Usage: `!maxpain TICKER` (e.g., `!maxpain SPY`)")
        return
    
    pending_queries["max_pain"] = ticker.upper()
    await send_uw_command(ctx.channel, f"/max_pain {ticker.upper()}")
    await ctx.send(f"📍 Querying max pain for **{ticker.upper()}**...")


@bot.command(name="logflow")
async def log_flow_command(
    ctx,
    ticker: str,
    sentiment: str,
    flow_type: str = "sweep",
    premium: str = "100k"
):
    """
    Quick manual flow entry
    Usage: !logflow AAPL bull sweep 500k
    """
    premium_clean = premium.lower().replace(",", "")
    if "m" in premium_clean:
        premium_value = int(float(premium_clean.replace("m", "")) * 1_000_000)
    elif "k" in premium_clean:
        premium_value = int(float(premium_clean.replace("k", "")) * 1_000)
    else:
        premium_value = int(float(premium_clean))

    sentiment_map = {
        "bull": "BULLISH", "bullish": "BULLISH", "b": "BULLISH",
        "bear": "BEARISH", "bearish": "BEARISH", "s": "BEARISH",
        "neutral": "NEUTRAL", "n": "NEUTRAL"
    }
    sentiment_normalized = sentiment_map.get(sentiment.lower(), "NEUTRAL")

    type_map = {
        "sweep": "SWEEP", "block": "BLOCK", "split": "SPLIT",
        "unusual": "UNUSUAL_VOLUME", "dark": "DARK_POOL", "dp": "DARK_POOL"
    }
    flow_type_normalized = type_map.get(flow_type.lower(), "UNUSUAL_VOLUME")

    flow_data = {
        "ticker": ticker.upper(),
        "sentiment": sentiment_normalized,
        "flow_type": flow_type_normalized,
        "premium": premium_value,
        "source": "manual_discord"
    }

    success = await send_flow_alert_to_pandora(flow_data)

    if success:
        await ctx.send(
            f"✅ Logged: **{ticker.upper()}** {sentiment_normalized} "
            f"{flow_type_normalized} ${premium_value:,}"
        )
    else:
        await ctx.send("❌ Failed to log flow to Pandora")


@bot.command(name="logtide")
async def log_tide_command(ctx, sentiment: str, bullish_pct: int = None):
    """
    Quick market tide entry
    Usage: !logtide bullish 65
    """
    sentiment_map = {
        "bull": "BULLISH", "bullish": "BULLISH",
        "bear": "BEARISH", "bearish": "BEARISH",
        "neutral": "NEUTRAL"
    }
    sentiment_normalized = sentiment_map.get(sentiment.lower(), "NEUTRAL")

    tide_data = {
        "type": "market_tide",
        "sentiment": sentiment_normalized,
        "bullish_pct": bullish_pct,
        "bearish_pct": 100 - bullish_pct if bullish_pct is not None else None,
        "timestamp": datetime.now().isoformat(),
        "source": "manual_discord"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PANDORA_API_URL}/bias/uw/market_tide",
                json=tide_data
            ) as resp:
                success = resp.status == 200
    except Exception:
        success = False

    if success:
        pct_text = f" ({bullish_pct}% bullish)" if bullish_pct is not None else ""
        await ctx.send(f"✅ Logged market tide: **{sentiment_normalized}**{pct_text}")
    else:
        await ctx.send("❌ Failed to log market tide")


@bot.command(name="test")
async def test_command(ctx, ticker: str = "TEST"):
    """Send a test flow to Pandora"""
    test_flow = {
        "ticker": ticker.upper(),
        "sentiment": "BULLISH",
        "flow_type": "SWEEP",
        "premium": 250000,
        "notes": "Manual test from Discord bridge v2.0"
    }
    
    success = await send_flow_alert_to_pandora(test_flow)
    
    if success:
        await ctx.send(f"✅ Test flow sent for **{ticker.upper()}**")
    else:
        await ctx.send(f"❌ Failed to send test flow - is Pandora's Box running?")


# ================================
# MAIN
# ================================

def run_bot():
    """Run the Discord bot"""
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_BOT_TOKEN environment variable not set!")
        logger.error("Set it with: export DISCORD_BOT_TOKEN='your-token-here'")
        return
    
    logger.info("🚀 Starting Pandora Bridge v2.0...")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    run_bot()
