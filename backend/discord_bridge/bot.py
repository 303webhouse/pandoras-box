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
import json
import asyncio
import base64
import logging
import mimetypes
import sqlite3
import aiohttp
import time as time_module
from collections import defaultdict
from datetime import datetime, time, timezone, timedelta, date as date_cls
from typing import Optional, Dict, Any, List
import pytz
from discord_bridge.uw.parser import parse_flow_embed, parse_ticker_embed
from discord_bridge.uw.filter import FlowFilter
from discord_bridge.uw.aggregator import FlowAggregator
from discord_bridge.whale_parser import (
    parse_whale_hunter_signal,
    parse_uw_premium_embed,
    format_whale_hunter_for_llm,
    format_uw_embed_for_llm,
)

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
WHALE_ALERTS_CHANNEL_ID = int(os.getenv("WHALE_ALERTS_CHANNEL_ID", "0"))
PIVOT_CHAT_CHANNEL_ID = int(os.getenv("PIVOT_CHAT_CHANNEL_ID", "0"))
CRYPTO_ALERTS_CHANNEL_ID = int(os.getenv("CRYPTO_ALERTS_CHANNEL_ID", "0"))
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
intents.members = True
intents.guilds = True
intents.presences = True

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
recent_uw_flow: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
last_zone_shift_state: Optional[Dict[str, Any]] = None
uw_request_sent_state: Dict[str, str] = {}
uw_snapshot_received_state: Dict[str, Dict[str, Any]] = defaultdict(dict)
pending_trade_imports: Dict[int, Dict[str, Any]] = {}

UW_CONTEXT_WINDOW_SECONDS = 4 * 60 * 60
ZONE_CONTEXT_WINDOW_SECONDS = 6 * 60 * 60

COMPANY_TICKERS = {
    "carvana": "CVNA",
    "tesla": "TSLA",
    "apple": "AAPL",
    "nvidia": "NVDA",
    "google": "GOOGL",
    "amazon": "AMZN",
    "microsoft": "MSFT",
    "meta": "META",
    "netflix": "NFLX",
    "spy": "SPY",
    "qqq": "QQQ",
}

DIRECTIONAL_HINTS = {
    "short",
    "long",
    "bearish",
    "bullish",
    "put",
    "puts",
    "call",
    "calls",
    "spread",
    "entry",
    "setup",
    "trade",
}

JOURNAL_DB_PATH = os.getenv("PIVOT_JOURNAL_DB_PATH", "/opt/pivot/data/journal.db")
PIVOT_VISION_MAX_TOKENS = int(os.getenv("PIVOT_VISION_MAX_TOKENS", "1800"))
PIVOT_MAX_IMAGE_BYTES = int(os.getenv("PIVOT_MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))
PIVOT_JOURNAL_LOOKBACK_LIMIT = int(os.getenv("PIVOT_JOURNAL_LOOKBACK_LIMIT", "3"))
JOURNAL_REQUIRED_COLUMNS = {
    "strike": "REAL",
    "expiry": "TEXT",
    "structure": "TEXT",
    "short_strike": "REAL",
    "long_strike": "REAL",
}

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


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date_cls:
    d = date_cls(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    d += timedelta(days=7 * (n - 1))
    return d


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date_cls:
    if month == 12:
        d = date_cls(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date_cls(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observed_holiday(day: date_cls) -> date_cls:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _us_market_holidays(year: int) -> set[date_cls]:
    # Major market holidays (approximation, sufficient for reminder suppression).
    holidays = {
        _observed_holiday(date_cls(year, 1, 1)),                         # New Year's Day
        _nth_weekday_of_month(year, 1, 0, 3),                            # MLK Day
        _nth_weekday_of_month(year, 2, 0, 3),                            # Presidents Day
        _last_weekday_of_month(year, 5, 0),                              # Memorial Day
        _observed_holiday(date_cls(year, 7, 4)),                         # Independence Day
        _nth_weekday_of_month(year, 9, 0, 1),                            # Labor Day
        _nth_weekday_of_month(year, 11, 3, 4),                           # Thanksgiving
        _observed_holiday(date_cls(year, 12, 25)),                       # Christmas
    }
    return holidays


def is_us_market_open_day(ts: Optional[datetime] = None) -> bool:
    now = (ts or get_et_now()).astimezone(ET)
    if now.weekday() >= 5:
        return False
    holidays = _us_market_holidays(now.year)
    return now.date() not in holidays


def _uw_time_slot(now: Optional[datetime] = None) -> str:
    ts = (now or get_et_now()).astimezone(ET)
    if ts.hour < 12:
        return "morning"
    if ts.hour < 16:
        return "afternoon"
    return "close"


def _mark_uw_snapshot_received(dashboard_type: str, observed_at: Optional[datetime] = None) -> None:
    ts = (observed_at or get_et_now()).astimezone(ET)
    slot = _uw_time_slot(ts)
    day_key = ts.date().isoformat()
    uw_snapshot_received_state[day_key][slot] = dashboard_type


async def send_uw_screenshot_request(time_slot: str) -> None:
    channel_id = PIVOT_CHAT_CHANNEL_ID or NOTIFICATION_CHANNEL_ID
    channel = bot.get_channel(channel_id)
    if not channel:
        return

    now = get_et_now()
    if not is_us_market_open_day(now):
        return

    day_key = now.date().isoformat()
    slot_key = f"{day_key}:{time_slot}"
    if uw_request_sent_state.get(time_slot) == day_key or uw_request_sent_state.get(slot_key) == day_key:
        return

    messages = {
        "morning": (
            "ðŸ“Š **Morning data request** â€” when you can, please drop screenshots of:\n"
            "â€¢ **UW Market Tide**\n"
            "â€¢ **UW Dark Pool**\n"
            "No rush â€” anytime before noon works."
        ),
        "afternoon": (
            "ðŸ“Š **Power hour setup** â€” if you can grab:\n"
            "â€¢ **UW Market Tide**\n"
            "â€¢ **UW Dark Pool**\n"
            "This helps prep for late-session signal quality."
        ),
        "close": (
            "ðŸ“Š **EOD brief data request** â€” please drop when possible:\n"
            "â€¢ **UW Market Tide**\n"
            "â€¢ **UW Dark Pool**\n"
            "â€¢ **UW Options GEX**\n"
            "If nothing arrives by 4:30 PM ET, the brief will run with API-only flow context."
        ),
    }

    text = messages.get(time_slot)
    if not text:
        return

    await channel.send(text)
    uw_request_sent_state[time_slot] = day_key
    uw_request_sent_state[slot_key] = day_key


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _is_directional_question(text: str) -> bool:
    text_lower = (text or "").lower()
    if not text_lower.strip():
        return False
    if "?" in text_lower:
        return True
    return any(term in text_lower for term in DIRECTIONAL_HINTS)


def _repeat_high_stakes_prompt(full_context: str) -> str:
    """
    Repeat high-stakes prompts so the model re-reads full context before answer.
    Applied only to recommendation-style calls (not casual chat).
    """
    normalized = (full_context or "").strip()
    if not normalized:
        return full_context
    return f"{normalized}\n\n---\nREVIEW AND CONFIRM:\n{normalized}"


def _record_recent_uw_flow(
    ticker: Optional[str],
    *,
    sentiment: Optional[str] = None,
    flow_type: Optional[str] = None,
    premium: Optional[float] = None,
    strike: Optional[float] = None,
    option_type: Optional[str] = None,
    source: str = "local",
) -> None:
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return

    now = time_module.time()
    records = recent_uw_flow[symbol]
    records[:] = [r for r in records if now - float(r.get("ts", 0)) <= UW_CONTEXT_WINDOW_SECONDS]
    records.append(
        {
            "ticker": symbol,
            "sentiment": (sentiment or "").upper() or None,
            "flow_type": (flow_type or "").upper() or None,
            "premium": premium,
            "strike": strike,
            "option_type": (option_type or "").upper() or None,
            "source": source,
            "ts": now,
        }
    )
    if len(records) > 80:
        del records[:-80]


def _get_local_recent_uw_flow(ticker: str, max_age_seconds: int = UW_CONTEXT_WINDOW_SECONDS) -> List[Dict[str, Any]]:
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return []
    now = time_module.time()
    records = recent_uw_flow.get(symbol, [])
    valid = [r for r in records if now - float(r.get("ts", 0)) <= max_age_seconds]
    recent_uw_flow[symbol] = valid[-80:]
    return list(reversed(valid))


def _is_zone_shift_signal(signal: Dict[str, Any]) -> bool:
    signal_type = (signal.get("signal_type") or "").upper()
    strategy = (signal.get("strategy") or "").upper()
    return "ZONE" in signal_type or "ZONE" in strategy


def _capture_zone_shift_state(signal: Dict[str, Any]) -> None:
    global last_zone_shift_state

    signal_time = _parse_iso_datetime(signal.get("timestamp")) or datetime.now(timezone.utc)
    notes = str(signal.get("notes") or "")
    from_zone = None
    to_zone = signal.get("cta_zone")

    transition = re.search(r"from\s+([A-Z_]+)\s+to\s+([A-Z_]+)", notes, re.IGNORECASE)
    if transition:
        from_zone = transition.group(1).upper()
        to_zone = transition.group(2).upper()

    last_zone_shift_state = {
        "timestamp": signal_time,
        "signal_type": (signal.get("signal_type") or "").upper(),
        "direction": (signal.get("direction") or "").upper(),
        "from_zone": from_zone,
        "to_zone": (to_zone or "").upper() or None,
    }


def _build_zone_context_text(signal: Dict[str, Any]) -> str:
    now_utc = datetime.now(timezone.utc)
    cta_zone = (signal.get("cta_zone") or "").upper() or "UNKNOWN"

    if last_zone_shift_state:
        shift_ts = last_zone_shift_state.get("timestamp")
        if isinstance(shift_ts, datetime):
            age_seconds = (now_utc - shift_ts).total_seconds()
            if age_seconds <= ZONE_CONTEXT_WINDOW_SECONDS:
                age_hours = max(age_seconds / 3600, 0.1)
                to_zone = last_zone_shift_state.get("to_zone") or cta_zone
                return (
                    f"Confirmation: Zone shifted to {to_zone} {age_hours:.1f}h ago "
                    f"({last_zone_shift_state.get('direction', 'UNKNOWN')})."
                )

    return f"Zone context: Current CTA zone is {cta_zone} (no zone shift in last 6h)."

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
        
        logger.info(f"ðŸ“Š Parsed market_tide: {result['sentiment']}")
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
                if any(word in context for word in ["bullish", "call", "green", "â†‘", "+"]):
                    result["sectors"][sector] = "BULLISH"
                    result["bullish_sectors"].append(sector)
                elif any(word in context for word in ["bearish", "put", "red", "â†“", "-"]):
                    result["sectors"][sector] = "BEARISH"
                    result["bearish_sectors"].append(sector)
                else:
                    result["sectors"][sector] = "NEUTRAL"
        
        logger.info(f"ðŸ“Š Parsed sectorflow: {len(result['bullish_sectors'])} bullish, {len(result['bearish_sectors'])} bearish")
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
        
        logger.info(f"ðŸ“Š Parsed oi_{keyword}: {len(result['contracts'])} contracts")
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
        
        logger.info(f"ðŸ“Š Parsed economic_calendar: {len(result['events'])} events, high_impact={result['high_impact_today']}")
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
            ticker_match = re.search(r'\b([A-Z]{1,5})\s*[-â€“]\s*\$', combined)
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
            logger.info(f"ðŸ“Š Parsed flow_alert: {result['ticker']} {result['sentiment']}")
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
                    logger.info(f"âœ… Sent to Pandora {endpoint}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"âŒ Pandora API error: {response.status} - {error_text}")
                    return False
    except asyncio.TimeoutError:
        logger.error(f"âŒ Timeout sending to {endpoint}")
        return False
    except Exception as e:
        logger.error(f"âŒ Error sending to Pandora: {e}")
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
        logger.info(f"ðŸ“¤ Sent query: {command}")
    except Exception as e:
        logger.error(f"âŒ Failed to send query: {e}")


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


@tasks.loop(minutes=1)
async def uw_screenshot_request_scheduler():
    """
    Ask for UW screenshots at fixed checkpoints:
    - 10:00 ET
    - 15:00 ET
    - 16:05 ET
    """
    now = get_et_now()
    if not is_us_market_open_day(now):
        return

    hhmm = now.strftime("%H:%M")
    if hhmm == "10:00":
        await send_uw_screenshot_request("morning")
    elif hhmm == "15:00":
        await send_uw_screenshot_request("afternoon")
    elif hhmm == "16:05":
        await send_uw_screenshot_request("close")


@uw_screenshot_request_scheduler.before_loop
async def before_uw_screenshot_request_scheduler():
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
            if _is_zone_shift_signal(signal):
                _capture_zone_shift_state(signal)
                _seen_signal_ids.add(signal_id)
                logger.info(
                    "Suppressed standalone zone-shift alert: %s %s",
                    signal.get("ticker"),
                    signal.get("signal_type"),
                )
                continue
            if score < MIN_SCORE_FOR_ALERT:
                _seen_signal_ids.add(signal_id)
                continue

            _seen_signal_ids.add(signal_id)
            embed = format_trade_idea_embed(signal)
            embed.add_field(
                name="Bias Context",
                value=_build_zone_context_text(signal),
                inline=False,
            )
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
    logger.info("â° Scheduled queries task started")


# ================================
# WHALE ALERTS HANDLER
# ================================

_COMMON_WORDS = {
    "A",
    "AN",
    "AND",
    "ARE",
    "AS",
    "AT",
    "BE",
    "BEAR",
    "BEARISH",
    "BULL",
    "BULLISH",
    "BUT",
    "BY",
    "DO",
    "DOES",
    "FOR",
    "FROM",
    "HERE",
    "HOW",
    "IF",
    "IN",
    "IS",
    "IT",
    "LOOK",
    "LOOKS",
    "NOW",
    "OF",
    "ON",
    "OR",
    "SHOULD",
    "SO",
    "THAT",
    "THE",
    "THIS",
    "TO",
    "US",
    "VIX",
    "WHAT",
    "WHERE",
    "WHY",
    "WITH",
}


def _auth_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if PIVOT_API_KEY:
        headers["Authorization"] = f"Bearer {PIVOT_API_KEY}"
    return headers


def _extract_ticker_hint(text: str) -> Optional[str]:
    text_lower = (text or "").lower()
    for company_name, ticker in COMPANY_TICKERS.items():
        if re.search(rf"\b{re.escape(company_name)}\b", text_lower):
            return ticker

    for token in re.findall(r"\b[A-Za-z]{1,5}\b", (text or "").upper()):
        if token in _COMMON_WORDS:
            continue
        return token
    return None


async def _fetch_json(session: aiohttp.ClientSession, endpoint: str) -> Optional[Dict[str, Any]]:
    try:
        async with session.get(
            f"{PANDORA_API_URL}{endpoint}",
            headers=_auth_headers(),
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.debug("Context fetch failed for %s with status %s", endpoint, resp.status)
    except Exception as exc:
        logger.debug("Context fetch failed for %s: %s", endpoint, exc)
    return None


def _format_bias_context(bias_state: Optional[Dict[str, Any]]) -> str:
    if not bias_state:
        return "Composite Bias (DAILY): unavailable"
    level = bias_state.get("level", "UNKNOWN")
    trend = bias_state.get("trend", "UNKNOWN")
    details = bias_state.get("details") or {}
    total_vote = details.get("total_vote")
    max_possible = details.get("max_possible")
    if total_vote is None or max_possible is None:
        score = "unknown"
    else:
        score = f"{total_vote}/{max_possible}"
    return f"Composite Bias (DAILY): {level} | Score: {score} | Trend: {trend}"


def _format_vix_context(vix_term: Optional[Dict[str, Any]]) -> str:
    if not vix_term:
        return "VIX Term Structure: unavailable"
    vix_data = vix_term.get("data") or {}
    vix_current = vix_data.get("vix_current")
    vix_3m = vix_data.get("vix3m_current")
    term = vix_data.get("term_structure", "UNKNOWN")
    if vix_current is None:
        return f"VIX Term Structure: {term}"
    if vix_3m is None:
        return f"VIX: {vix_current} | Term Structure: {term}"
    return f"VIX: {vix_current} | VIX3M: {vix_3m} | Term Structure: {term}"


def _format_factor_health_context(composite_payload: Optional[Dict[str, Any]]) -> str:
    if not composite_payload:
        return "Factor Health: unavailable"

    active = composite_payload.get("active_factors") or []
    stale = composite_payload.get("stale_factors") or []
    if not isinstance(active, list):
        active = []
    if not isinstance(stale, list):
        stale = []

    total = len(active) + len(stale)
    if total == 0:
        return "Factor Health: unavailable"

    stale_count = len(stale)
    if stale_count:
        stale_names = ", ".join(str(x) for x in stale[:6])
        if len(stale) > 6:
            stale_names = f"{stale_names}, +{len(stale) - 6} more"
    else:
        stale_names = "none"

    summary = f"Factor Health: {len(active)}/{total} fresh ({stale_count} stale: {stale_names})"
    if stale_count > 5:
        summary += f"\nâš ï¸ Low data confidence - {stale_count} factors stale. Composite bias may be unreliable."
    return summary


def _format_convergence_context(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return "Signal Convergence (24h): unavailable"

    events = payload.get("convergence_events") or []
    if not isinstance(events, list):
        events = []
    if not events:
        return "Signal Convergence (24h): No signal convergence detected today."

    lines = ["Signal Convergence (24h):"]
    for event in events[:3]:
        ticker = str(event.get("ticker") or "?").upper()
        direction = str(event.get("direction") or "UNKNOWN").upper()
        sources = event.get("sources") or []
        source_names = ", ".join(str(s) for s in sources) if isinstance(sources, list) else str(sources)
        source_count = int(event.get("source_count") or (len(sources) if isinstance(sources, list) else 0))
        strength = "HIGH convergence" if source_count >= 3 else "MODERATE convergence"
        lines.append(f"- ðŸŽ¯ CONVERGENCE: {ticker} {direction} â€” confirmed by {source_names} ({strength})")
    return "\n".join(lines)


def _format_quote_context(symbol: str, quote_data: Optional[Dict[str, Any]]) -> str:
    if not quote_data:
        return f"{symbol}: unavailable"
    price = quote_data.get("price")
    if price is None:
        return f"{symbol}: unavailable"
    try:
        return f"{symbol}: ${float(price):.2f}"
    except (TypeError, ValueError):
        return f"{symbol}: {price}"


def _format_strategy_health_context(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return "Strategy Health: unavailable"

    grades = payload.get("grades") or []
    if not isinstance(grades, list) or not grades:
        return "Strategy Health (30d): no persisted grades yet"

    degraded: List[Dict[str, Any]] = []
    for row in grades:
        grade = str((row or {}).get("grade") or "").upper()
        if grade in {"C", "D", "F"}:
            degraded.append(row)

    unresolved = payload.get("unresolved_alerts")
    unresolved_text = ""
    if isinstance(unresolved, (int, float)):
        unresolved_text = f" | unresolved alerts: {int(unresolved)}"

    if not degraded:
        return f"Strategy Health (30d): no degraded sources (all >= B){unresolved_text}"

    lines = [f"Strategy Health Warning (30d){unresolved_text}:"]
    for row in degraded[:5]:
        source = str((row or {}).get("source") or "unknown")
        grade = str((row or {}).get("grade") or "?").upper()
        accuracy = row.get("accuracy")
        signals_count = row.get("signals_count")

        accuracy_text = "n/a"
        if isinstance(accuracy, (int, float)):
            accuracy_text = f"{float(accuracy) * 100:.1f}%"
        signals_text = str(signals_count) if isinstance(signals_count, (int, float)) else "n/a"

        lines.append(f"- {source}: grade {grade}, accuracy {accuracy_text}, signals {signals_text}")

    lines.append("Rule: C requires convergence. D means no solo recommendations.")
    return "\n".join(lines)


async def get_strategy_health_context(days: int = 30) -> str:
    endpoint = f"/analytics/strategy-health?days={max(1, int(days))}"
    async with aiohttp.ClientSession() as session:
        payload = await _fetch_json(session, endpoint)
    return _format_strategy_health_context(payload)


async def _get_options_context_for_ticker(
    ticker: str,
    *,
    target_price: Optional[float] = None,
) -> str:
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return "Options chain: unavailable (missing ticker)"
    try:
        from tools.options_chain import get_options_context  # type: ignore
        return await get_options_context(symbol, target_price=target_price, dte_range=(7, 45))
    except Exception as exc:
        return f"Options chain unavailable for {symbol}: {exc}"


def _extract_alert_epoch(alert: Dict[str, Any]) -> Optional[float]:
    dt = _parse_iso_datetime(alert.get("received_at") or alert.get("timestamp"))
    if dt:
        return dt.timestamp()

    ts = alert.get("ts")
    if isinstance(ts, (int, float)):
        return float(ts)
    return None


def _normalize_alert_type(alert: Dict[str, Any]) -> str:
    flow_type = (
        alert.get("flow_type")
        or alert.get("type")
        or alert.get("order_type")
        or "UNKNOWN"
    )
    return str(flow_type).upper()


def _normalize_alert_sentiment(alert: Dict[str, Any]) -> str:
    raw = str(alert.get("sentiment") or "").upper()
    if raw in {"BULLISH", "BEARISH"}:
        return raw

    net_premium = alert.get("net_premium")
    if isinstance(net_premium, (int, float)):
        if net_premium > 0:
            return "BULLISH"
        if net_premium < 0:
            return "BEARISH"
    return "UNKNOWN"


async def _fetch_backend_recent_uw_alerts(ticker: str, lookback_hours: int = 4) -> List[Dict[str, Any]]:
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return []

    cutoff = time_module.time() - (lookback_hours * 3600)
    alerts: List[Dict[str, Any]] = []
    async with aiohttp.ClientSession() as session:
        recent_payload = await _fetch_json(session, "/flow/recent?limit=80")
        if isinstance(recent_payload, dict):
            for alert in recent_payload.get("alerts", []) or []:
                if not isinstance(alert, dict):
                    continue
                if str(alert.get("ticker", "")).upper().strip() != symbol:
                    continue
                epoch = _extract_alert_epoch(alert)
                if epoch is None or epoch < cutoff:
                    continue
                alerts.append(alert)

        # Fallback if recent endpoint has no entry for this ticker.
        if not alerts:
            ticker_payload = await _fetch_json(session, f"/flow/ticker/{symbol}")
            flow_obj = ticker_payload.get("flow") if isinstance(ticker_payload, dict) else None
            if isinstance(flow_obj, dict):
                flow_obj = dict(flow_obj)
                flow_obj.setdefault("ticker", symbol)
                flow_obj.setdefault("source", ticker_payload.get("source", "backend"))
                flow_obj.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
                alerts.append(flow_obj)

    return alerts


def _merge_uw_alerts(
    ticker: str,
    backend_alerts: List[Dict[str, Any]],
    local_alerts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    symbol = (ticker or "").upper().strip()
    merged: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for source_alert in [*backend_alerts, *local_alerts]:
        alert = dict(source_alert)
        alert["ticker"] = symbol

        epoch = _extract_alert_epoch(alert)
        alert["_epoch"] = epoch or time_module.time()
        alert["sentiment"] = _normalize_alert_sentiment(alert)
        alert["flow_type"] = _normalize_alert_type(alert)

        key = (
            round(alert["_epoch"], 0),
            alert.get("ticker"),
            alert.get("flow_type"),
            alert.get("sentiment"),
            alert.get("premium") or alert.get("total_premium") or alert.get("largest_premium"),
            alert.get("strike"),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(alert)

    merged.sort(
        key=lambda x: (
            x.get("_epoch", 0),
            x.get("premium") or x.get("total_premium") or x.get("largest_premium") or 0,
        ),
        reverse=True,
    )
    return merged[:6]


def _format_uw_alert_line(alert: Dict[str, Any]) -> str:
    flow_type = alert.get("flow_type", "UNKNOWN")
    sentiment = alert.get("sentiment", "UNKNOWN")
    premium = (
        alert.get("premium")
        or alert.get("total_premium")
        or alert.get("largest_premium")
        or 0
    )
    try:
        premium_text = f"${float(premium):,.0f}"
    except Exception:
        premium_text = str(premium)

    strike = alert.get("strike")
    strike_text = ""
    if isinstance(strike, (int, float)):
        strike_text = f" strike ${float(strike):.1f}"

    option_type = str(alert.get("option_type") or "").upper()
    option_text = f" {option_type}" if option_type in {"CALL", "PUT"} else ""

    return f"- {flow_type} {sentiment}{option_text}{strike_text}, premium {premium_text}"


def _build_uw_context_block(ticker: str, alerts: List[Dict[str, Any]], lookback_hours: int = 4) -> str:
    symbol = (ticker or "").upper().strip()
    if not alerts:
        return f"UW Flow Context ({symbol}, last {lookback_hours}h): none detected"

    lines = [f"UW Flow Context ({symbol}, last {lookback_hours}h):"]
    dark_pool_count = 0
    for alert in alerts[:4]:
        if str(alert.get("flow_type", "")).upper() == "DARK_POOL":
            dark_pool_count += 1
        lines.append(_format_uw_alert_line(alert))
    if dark_pool_count:
        lines.append(f"Dark pool prints in window: {dark_pool_count}")
    return "\n".join(lines)


def _build_convergence_block(
    ticker: str,
    whale_lean: Optional[str],
    poc_level: Optional[float],
    alerts: List[Dict[str, Any]],
) -> Optional[str]:
    if not alerts or not whale_lean:
        return None

    lean = str(whale_lean).upper()
    if lean not in {"BULLISH", "BEARISH"}:
        return None

    directional = [a for a in alerts if a.get("sentiment") in {"BULLISH", "BEARISH"}]
    if not directional:
        return None

    match = next((a for a in directional if a.get("sentiment") == lean), None)
    lead = match or directional[0]
    conviction = "HIGH" if match else "MODERATE"

    price_text = f"${float(poc_level):.2f}" if isinstance(poc_level, (int, float)) else "N/A"
    uw_line = _format_uw_alert_line(lead).lstrip("- ").replace("premium ", "")
    return (
        f"âš¡ CONVERGENCE: Whale Hunter tape signal + UW options flow both active on {(ticker or '').upper()}\n"
        f"Whale: {lean} distribution/accumulation at {price_text}\n"
        f"UW Flow: {uw_line}\n"
        f"Conviction upgrade: {conviction}"
    )


async def _calculate_rvol_for_whale(
    ticker: str,
    event_ts: datetime,
    lookback_days: int = 20,
) -> Optional[float]:
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return None

    endpoint = f"/analytics/price-data?ticker={symbol}&timeframe=5m&days={max(10, lookback_days + 5)}&limit=20000"
    async with aiohttp.ClientSession() as session:
        payload = await _fetch_json(session, endpoint)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None

    target_et = event_ts.astimezone(ET)
    target_slot = target_et.strftime("%H:%M")
    current_volume: Optional[float] = None
    comparison: List[float] = []

    for row in rows:
        ts = _parse_iso_datetime(row.get("timestamp"))
        if not ts:
            continue
        ts_et = ts.astimezone(ET)
        if ts_et.strftime("%H:%M") != target_slot:
            continue
        vol = _safe_float(row.get("volume"))
        if vol is None:
            continue
        if ts_et.date() == target_et.date():
            current_volume = vol
        elif ts_et.date() < target_et.date():
            comparison.append(vol)

    if current_volume is None or not comparison:
        return None

    comparison = comparison[-lookback_days:]
    baseline = sum(comparison) / len(comparison) if comparison else 0.0
    if baseline <= 0:
        return None
    return float(current_volume / baseline)


def _apply_rvol_conviction_modifier(base_conviction: str, rvol: Optional[float]) -> tuple[str, str]:
    conviction = str(base_conviction or "MODERATE").upper()
    if conviction not in {"WATCH", "MODERATE", "HIGH"}:
        conviction = "MODERATE"
    if rvol is None:
        return conviction, "RVOL_UNAVAILABLE"
    if rvol > 2.0:
        if conviction == "WATCH":
            conviction = "MODERATE"
        elif conviction == "MODERATE":
            conviction = "HIGH"
        return conviction, "RVOL_CONFIRMED"
    if rvol < 0.8:
        if conviction == "HIGH":
            conviction = "MODERATE"
        elif conviction == "MODERATE":
            conviction = "WATCH"
        return conviction, "RVOL_THIN"
    return conviction, "RVOL_NORMAL"


async def _build_tick_whale_confirmation(
    whale_direction: Optional[str],
    reference_ts: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    lean = str(whale_direction or "").upper()
    if lean not in {"BULLISH", "BEARISH"}:
        return None

    async with aiohttp.ClientSession() as session:
        tick_payload = await _fetch_json(session, "/bias/tick")
    if not isinstance(tick_payload, dict) or tick_payload.get("status") not in {"ok", "success"}:
        return None

    updated_at = _parse_iso_datetime(tick_payload.get("updated_at"))
    now_utc = (reference_ts or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if updated_at and abs((now_utc - updated_at).total_seconds()) > 30 * 60:
        return None

    candidates = [
        _safe_float(tick_payload.get("tick_close")),
        _safe_float(tick_payload.get("tick_low")),
        _safe_float(tick_payload.get("tick_high")),
    ]
    values = [float(v) for v in candidates if isinstance(v, float)]
    if not values:
        return None

    tick_value = max(values, key=lambda x: abs(x))
    if abs(tick_value) < 800:
        return None

    tick_direction = "BEARISH" if tick_value < 0 else "BULLISH"
    status = "TICK_CONFIRMS" if tick_direction == lean else "TICK_CONTRADICTS"
    return {
        "tick_value": round(tick_value, 2),
        "tick_time": updated_at.isoformat() if updated_at else None,
        "tick_direction": tick_direction,
        "status": status,
    }


async def build_recent_uw_context(ticker: str, lookback_hours: int = 4) -> tuple[str, List[Dict[str, Any]]]:
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return "UW Flow Context: unavailable", []

    backend_alerts = await _fetch_backend_recent_uw_alerts(symbol, lookback_hours=lookback_hours)
    local_alerts = _get_local_recent_uw_flow(symbol, max_age_seconds=lookback_hours * 3600)
    merged = _merge_uw_alerts(symbol, backend_alerts, local_alerts)
    return _build_uw_context_block(symbol, merged, lookback_hours=lookback_hours), merged


async def build_market_context(user_text: str = "", ticker_hint: Optional[str] = None) -> str:
    target_ticker = (ticker_hint or _extract_ticker_hint(user_text) or "SPY").upper()
    symbols: List[str] = ["SPY"]
    if target_ticker != "SPY":
        symbols.append(target_ticker)

    async with aiohttp.ClientSession() as session:
        tasks = [
            _fetch_json(session, "/bias/DAILY"),
            _fetch_json(session, "/market-indicators/vix-term"),
            _fetch_json(session, "/bias/composite"),
            _fetch_json(session, "/analytics/strategy-health?days=30"),
            _fetch_json(session, "/analytics/convergence-stats?days=1&min_sources=2"),
        ]
        tasks.extend(_fetch_json(session, f"/hybrid/price/{symbol}") for symbol in symbols)
        results = await asyncio.gather(*tasks, return_exceptions=True)

    def as_dict(value: Any) -> Optional[Dict[str, Any]]:
        return value if isinstance(value, dict) else None

    bias_state = as_dict(results[0])
    vix_term = as_dict(results[1])
    composite_payload = as_dict(results[2])
    strategy_health_payload = as_dict(results[3])
    convergence_payload = as_dict(results[4])
    quote_results = [as_dict(value) for value in results[5:]]

    lines = [
        _format_bias_context(bias_state),
        _format_vix_context(vix_term),
        _format_factor_health_context(composite_payload),
        _format_convergence_context(convergence_payload),
        _format_strategy_health_context(strategy_health_payload),
    ]
    for symbol, quote_data in zip(symbols, quote_results):
        lines.append(_format_quote_context(symbol, quote_data))

    return "\n".join(lines)


def _message_embed_text(message: discord.Message) -> str:
    parts: List[str] = []
    for embed in message.embeds:
        if embed.title:
            parts.append(str(embed.title))
        if embed.description:
            parts.append(str(embed.description))
        for field in embed.fields or []:
            name = str(field.name or "").strip()
            value = str(field.value or "").strip()
            if name and value:
                parts.append(f"{name}: {value}")
            elif value:
                parts.append(value)
    return "\n".join(parts).strip()


def _message_signal_text(message: discord.Message) -> str:
    parts: List[str] = []
    if message.content and message.content.strip():
        parts.append(message.content.strip())
    embed_text = _message_embed_text(message)
    if embed_text:
        parts.append(embed_text)
    return "\n\n".join(parts).strip()


def _extract_crypto_ticker_hint(text: str) -> Optional[str]:
    upper_text = (text or "").upper()
    if not upper_text:
        return None

    ignore_tokens = _COMMON_WORDS | {
        "SCOUT",
        "SNIPER",
        "EXHAUSTION",
        "ALERT",
        "SIGNAL",
        "CRYPTO",
        "LONG",
        "SHORT",
        "BUY",
        "SELL",
    }

    candidates = re.findall(r"\b[A-Z]{2,10}(?:[-/]?(?:USDT|USD|PERP))?\b", upper_text)
    for raw in candidates:
        symbol = raw.replace("-", "").replace("/", "")
        if symbol in ignore_tokens:
            continue
        if symbol.endswith("USDT") or symbol.endswith("USD") or symbol.endswith("PERP"):
            return symbol
        if 2 <= len(symbol) <= 6:
            return symbol
    return None


def _format_crypto_price_context(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return "Crypto Price Context: unavailable"

    prices = payload.get("prices") or {}
    perps = prices.get("perps") or {}
    spot = prices.get("binance_spot") or prices.get("coinbase_spot")
    perp = (
        perps.get("source_price")
        or perps.get("binance")
        or perps.get("bybit")
        or perps.get("okx")
    )
    basis_pct = prices.get("basis_pct")

    segments: List[str] = []
    if isinstance(spot, (int, float)):
        segments.append(f"BTC Spot: ${float(spot):,.2f}")
    if isinstance(perp, (int, float)):
        segments.append(f"Perp: ${float(perp):,.2f}")
    if isinstance(basis_pct, (int, float)):
        segments.append(f"Basis: {float(basis_pct) * 100:+.2f}%")

    return " | ".join(segments) if segments else "Crypto Price Context: unavailable"


def _format_crypto_funding_context(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return "Funding: unavailable"
    funding = payload.get("funding") or {}
    primary = funding.get("primary") or {}
    rate = primary.get("rate")
    source = str(primary.get("source") or "unknown").upper()
    if isinstance(rate, (int, float)):
        return f"Funding ({source}): {float(rate) * 100:+.4f}%"
    return "Funding: unavailable"


def _format_crypto_cvd_context(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return "CVD: unavailable"
    cvd = payload.get("cvd") or {}
    direction = str(cvd.get("direction") or "UNKNOWN")
    confidence = str(cvd.get("direction_confidence") or "LOW")
    net_usd = cvd.get("net_usd")
    if isinstance(net_usd, (int, float)):
        return f"CVD: {direction} ({confidence}), net ${float(net_usd):,.0f}"
    return f"CVD: {direction} ({confidence})"


def _format_etf_window_context(
    current_session_payload: Optional[Dict[str, Any]],
    sessions_payload: Optional[Dict[str, Any]],
) -> str:
    if isinstance(current_session_payload, dict) and current_session_payload.get("in_session"):
        session_name = (
            current_session_payload.get("name")
            or (current_session_payload.get("current_session") or {}).get("name")
            or "ACTIVE SESSION"
        )
        return f"ETF Flow Window: active ({session_name})"

    sessions = (sessions_payload or {}).get("sessions") or {}
    etf_fix = sessions.get("etf_fixing") or {}
    etf_name = str(etf_fix.get("name") or "ETF Fixing Window")
    etf_time = str(etf_fix.get("ny_time") or "3pm-4pm ET")
    return f"ETF Flow Window: inactive (typically {etf_name}, {etf_time})"


async def build_crypto_market_context(ticker_hint: Optional[str] = None) -> str:
    symbol = (ticker_hint or "BTC").upper().strip()
    base_symbol = re.sub(r"(USDT|USD|PERP)$", "", symbol) or "BTC"

    async with aiohttp.ClientSession() as session:
        market_payload, current_session_payload, sessions_payload, hybrid_payload = await asyncio.gather(
            _fetch_json(session, "/crypto/market"),
            _fetch_json(session, "/btc/sessions/current"),
            _fetch_json(session, "/btc/sessions"),
            _fetch_json(session, f"/hybrid/price/{base_symbol}"),
            return_exceptions=True,
        )

    def as_dict(value: Any) -> Optional[Dict[str, Any]]:
        return value if isinstance(value, dict) else None

    market_payload = as_dict(market_payload)
    current_session_payload = as_dict(current_session_payload)
    sessions_payload = as_dict(sessions_payload)
    hybrid_payload = as_dict(hybrid_payload)

    lines = [
        _format_crypto_price_context(market_payload),
        _format_crypto_funding_context(market_payload),
        _format_crypto_cvd_context(market_payload),
        _format_etf_window_context(current_session_payload, sessions_payload),
    ]

    hybrid_price = hybrid_payload.get("price") if isinstance(hybrid_payload, dict) else None
    if isinstance(hybrid_price, (int, float)):
        lines.append(f"{base_symbol} API Quote: ${float(hybrid_price):,.2f}")

    return "\n".join(lines)


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True

    name = (attachment.filename or "").lower()
    return name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))


def _guess_image_mime_type(attachment: discord.Attachment) -> str:
    content_type = (attachment.content_type or "").split(";")[0].strip().lower()
    if content_type.startswith("image/"):
        return content_type

    guessed, _ = mimetypes.guess_type(attachment.filename or "")
    if guessed and guessed.startswith("image/"):
        return guessed
    return "image/png"


def _first_image_attachment(message: discord.Message) -> Optional[discord.Attachment]:
    for attachment in message.attachments:
        if _is_image_attachment(attachment):
            return attachment
    return None


async def _attachment_to_data_url(attachment: discord.Attachment) -> Optional[str]:
    if attachment.size and attachment.size > PIVOT_MAX_IMAGE_BYTES:
        logger.warning(
            "Skipping image %s: size %s exceeds max %s bytes",
            attachment.filename,
            attachment.size,
            PIVOT_MAX_IMAGE_BYTES,
        )
        return None

    try:
        raw = await attachment.read()
    except Exception as exc:
        logger.warning("Failed reading image attachment %s: %s", attachment.filename, exc)
        return None

    if not raw:
        return None

    if len(raw) > PIVOT_MAX_IMAGE_BYTES:
        logger.warning(
            "Skipping image %s: downloaded size %s exceeds max %s bytes",
            attachment.filename,
            len(raw),
            PIVOT_MAX_IMAGE_BYTES,
        )
        return None

    mime_type = _guess_image_mime_type(attachment)
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _data_url_to_image_parts(data_url: str) -> Optional[tuple[str, str]]:
    value = (data_url or "").strip()
    if not value.startswith("data:") or ";base64," not in value:
        return None
    header, b64_data = value.split(",", 1)
    media_type = header.replace("data:", "").replace(";base64", "").strip()
    if not media_type or not b64_data:
        return None
    return media_type, b64_data


def _detect_uw_dashboard_type(text: str, fallback: str = "") -> Optional[str]:
    corpus = f"{text}\n{fallback}".lower()
    if not corpus.strip():
        return None
    if "market tide" in corpus or "net premium" in corpus:
        return "market_tide"
    if "dark pool" in corpus or "darkpool" in corpus:
        return "dark_pool"
    if "gex" in corpus or "gamma exposure" in corpus or "put wall" in corpus or "call wall" in corpus:
        return "gex"
    return None


def _extract_uw_snapshot_structured_data(summary_text: str) -> Dict[str, Any]:
    text = summary_text or ""
    upper = text.upper()
    data: Dict[str, Any] = {}

    if "BULLISH" in upper:
        data["direction"] = "BULLISH"
    elif "BEARISH" in upper:
        data["direction"] = "BEARISH"
    elif "NEUTRAL" in upper:
        data["direction"] = "NEUTRAL"

    money_match = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([MB])", upper)
    if money_match:
        val = float(money_match.group(1))
        scale = money_match.group(2)
        if scale == "B":
            val *= 1000.0
        data["magnitude_millions"] = round(val, 2)

    tickers = re.findall(r"\b[A-Z]{1,5}\b", upper)
    top_tickers = []
    for symbol in tickers:
        if symbol in _COMMON_WORDS:
            continue
        if symbol in {"UW", "GEX", "POC", "IV", "ETF", "CVD", "VIX"}:
            continue
        if symbol not in top_tickers:
            top_tickers.append(symbol)
        if len(top_tickers) >= 3:
            break
    if top_tickers:
        data["top_tickers"] = top_tickers

    if "ACCELERAT" in upper:
        data["trend"] = "accelerating"
    elif "DECELERAT" in upper:
        data["trend"] = "decelerating"

    if "CONFIRM" in upper or "ALIGNS" in upper or "ALIGNED" in upper:
        data["signal_alignment"] = "confirms_bias"
    elif "CONTRADICT" in upper or "CONFLICT" in upper:
        data["signal_alignment"] = "contradicts_bias"
    else:
        data["signal_alignment"] = "neutral"

    return data


async def _post_uw_snapshot_to_backend(
    *,
    dashboard_type: str,
    summary_text: str,
    time_slot: Optional[str] = None,
) -> None:
    payload = {
        "dashboard_type": dashboard_type,
        "time_slot": time_slot or _uw_time_slot(),
        "extracted_data": _extract_uw_snapshot_structured_data(summary_text),
        "raw_summary": summary_text[:3000],
        "signal_alignment": _extract_uw_snapshot_structured_data(summary_text).get("signal_alignment", "neutral"),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PANDORA_API_URL}/analytics/log-uw-snapshot",
                json=payload,
                headers=_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status >= 400:
                    logger.debug("UW snapshot log failed with status %s", resp.status)
                    return
        _mark_uw_snapshot_received(dashboard_type)
    except Exception as exc:
        logger.debug("Could not persist UW snapshot context: %s", exc)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    try:
        return int(round(parsed))
    except Exception:
        return None


def _safe_sql_identifier(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""))


def _parse_expiry_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    parsed = _parse_iso_datetime(text)
    if parsed:
        return parsed

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text[:19], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _get_journal_table(conn: sqlite3.Connection) -> Optional[str]:
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    except Exception:
        return None

    table_names = [str(row[0]) for row in rows if row and row[0]]
    if not table_names:
        return None

    for candidate in ("trades", "positions", "journal_trades"):
        if candidate in table_names:
            return candidate

    for name in table_names:
        lowered = name.lower()
        if "trade" in lowered or "position" in lowered:
            return name
    return None


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    if not _safe_sql_identifier(table_name):
        return []
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return [str(row[1]) for row in rows if len(row) > 1 and row[1]]
    except Exception:
        return []


def _ensure_journal_schema_columns_sync() -> List[str]:
    """
    Add optional strike/expiry/structure columns when missing.
    Keeps existing journal DBs backward compatible.
    """
    if not os.path.exists(JOURNAL_DB_PATH):
        return []

    conn: Optional[sqlite3.Connection] = None
    added: List[str] = []
    try:
        conn = sqlite3.connect(JOURNAL_DB_PATH)
        table_name = _get_journal_table(conn)
        if not table_name or not _safe_sql_identifier(table_name):
            return []

        existing = set(_get_table_columns(conn, table_name))
        for col_name, sql_type in JOURNAL_REQUIRED_COLUMNS.items():
            if col_name in existing or not _safe_sql_identifier(col_name):
                continue
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type}")
            added.append(col_name)

        if added:
            conn.commit()
        return added
    except Exception as exc:
        logger.warning("Journal schema migration skipped: %s", exc)
        return []
    finally:
        if conn is not None:
            conn.close()


def _fetch_open_journal_positions(ticker: str) -> List[Dict[str, Any]]:
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return []
    if not os.path.exists(JOURNAL_DB_PATH):
        return []

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(JOURNAL_DB_PATH)
        conn.row_factory = sqlite3.Row

        table_name = _get_journal_table(conn)
        if not table_name:
            return []
        columns = _get_table_columns(conn, table_name)
        if "ticker" not in columns:
            return []

        preferred_cols = [
            "id",
            "ticker",
            "status",
            "direction",
            "side",
            "strategy",
            "structure",
            "option_type",
            "strike",
            "short_strike",
            "long_strike",
            "breakeven",
            "break_even",
            "expiry",
            "expiration",
            "entry_price",
            "entry_date",
            "opened_at",
            "created_at",
            "dte",
        ]
        selected = [name for name in preferred_cols if name in columns and _safe_sql_identifier(name)]
        if not selected:
            selected = [name for name in columns if _safe_sql_identifier(name)]

        if not selected:
            return []

        where_clauses = ["UPPER(ticker)=?"]
        params: List[Any] = [symbol]
        if "status" in columns:
            where_clauses.append("LOWER(status)='open'")
        elif "is_open" in columns:
            where_clauses.append("is_open=1")

        order_candidates = ["opened_at", "entry_date", "created_at", "id"]
        order_column = next((name for name in order_candidates if name in columns), None)

        sql = (
            f"SELECT {', '.join(selected)} FROM {table_name} "
            f"WHERE {' AND '.join(where_clauses)}"
        )
        if order_column:
            sql += f" ORDER BY {order_column} DESC"
        sql += f" LIMIT {max(1, PIVOT_JOURNAL_LOOKBACK_LIMIT)}"

        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("Journal lookup failed for %s: %s", symbol, exc)
        return []
    finally:
        if conn is not None:
            conn.close()


def _infer_option_type(position: Dict[str, Any]) -> str:
    option_type = str(position.get("option_type") or "").upper()
    if option_type in {"CALL", "PUT"}:
        return option_type

    joined = " ".join(
        str(position.get(key) or "")
        for key in ("direction", "side", "strategy", "structure")
    ).upper()
    if "PUT" in joined:
        return "PUT"
    if "CALL" in joined:
        return "CALL"
    return ""


def _infer_position_bias(position: Dict[str, Any]) -> str:
    joined = " ".join(
        str(position.get(key) or "")
        for key in ("direction", "side", "strategy", "structure", "option_type")
    ).upper()
    if any(token in joined for token in ("BEAR", "SHORT", "PUT")):
        return "BEARISH"
    if any(token in joined for token in ("BULL", "LONG", "CALL")):
        return "BULLISH"
    return "UNKNOWN"


def _format_position_structure(position: Dict[str, Any]) -> str:
    short_strike = _safe_float(position.get("short_strike"))
    long_strike = _safe_float(position.get("long_strike"))
    strike = _safe_float(position.get("strike"))
    option_type = _infer_option_type(position)
    strategy = str(position.get("strategy") or position.get("structure") or "").strip()

    if short_strike is not None and long_strike is not None:
        spread_name = "vertical spread"
        if option_type == "PUT":
            spread_name = "put spread"
        elif option_type == "CALL":
            spread_name = "call spread"
        return f"{spread_name} {short_strike:.1f}/{long_strike:.1f}"

    if strike is not None and option_type:
        bias = _infer_position_bias(position)
        side = "long" if bias == "BULLISH" else "short" if bias == "BEARISH" else "position"
        return f"{side} {option_type.lower()} {strike:.1f}"

    if strategy:
        return strategy

    return "open position (structure unavailable)"


def _compute_position_dte(position: Dict[str, Any]) -> Optional[int]:
    direct_dte = _safe_int(position.get("dte"))
    if direct_dte is not None:
        return direct_dte

    for key in ("expiry", "expiration"):
        expiry_dt = _parse_expiry_datetime(position.get(key))
        if not expiry_dt:
            continue
        return (expiry_dt.date() - get_et_now().date()).days
    return None


def _build_position_levels(position: Dict[str, Any]) -> Dict[str, float]:
    levels: Dict[str, float] = {}

    short_strike = _safe_float(position.get("short_strike"))
    long_strike = _safe_float(position.get("long_strike"))
    strike = _safe_float(position.get("strike"))
    breakeven = _safe_float(position.get("breakeven"))
    if breakeven is None:
        breakeven = _safe_float(position.get("break_even"))

    if short_strike is not None:
        levels["short strike"] = short_strike
    if long_strike is not None:
        levels["long strike"] = long_strike
    if strike is not None and "short strike" not in levels:
        levels["strike"] = strike
    if breakeven is not None:
        levels["breakeven"] = breakeven

    return levels


def _build_whale_position_guidance(
    position: Dict[str, Any],
    poc_level: Optional[float],
    whale_lean: Optional[str],
) -> Optional[str]:
    guidance_parts: List[str] = []
    levels = _build_position_levels(position)

    if isinstance(poc_level, (int, float)) and levels:
        nearest_label, nearest_price = min(
            levels.items(),
            key=lambda kv: abs(float(poc_level) - kv[1]),
        )
        distance = float(poc_level) - nearest_price
        abs_distance = abs(distance)
        relation = "above" if distance >= 0 else "below"

        if nearest_label == "short strike":
            guidance_parts.append(
                f"POC is ${abs_distance:.2f} {relation} your short strike (${nearest_price:.2f})"
            )
            if abs_distance <= 2:
                guidance_parts.append("tighten stop and defend short strike")
        elif nearest_label == "long strike":
            guidance_parts.append(
                f"POC is ${abs_distance:.2f} {relation} your long strike (${nearest_price:.2f})"
            )
        elif nearest_label == "breakeven":
            guidance_parts.append(
                f"POC is ${abs_distance:.2f} {relation} breakeven (${nearest_price:.2f})"
            )
        else:
            guidance_parts.append(
                f"POC is ${abs_distance:.2f} {relation} your strike (${nearest_price:.2f})"
            )

    whale_bias = str(whale_lean or "").upper()
    position_bias = _infer_position_bias(position)
    if whale_bias in {"BULLISH", "BEARISH"} and position_bias in {"BULLISH", "BEARISH"}:
        if whale_bias == position_bias:
            guidance_parts.append("whale confirms your direction - hold while level is intact")
        else:
            guidance_parts.append("whale is counter to your position - consider a defensive adjustment")

    if not guidance_parts:
        return None
    return "; ".join(guidance_parts)


def _build_journal_context_for_whale_sync(
    ticker: str,
    poc_level: Optional[float],
    whale_lean: Optional[str],
) -> Optional[str]:
    symbol = (ticker or "").upper().strip()
    if not symbol:
        return None

    positions = _fetch_open_journal_positions(symbol)
    if not positions:
        return None

    lines: List[str] = [f"Journal Open Positions ({symbol}):"]
    for position in positions[: max(1, PIVOT_JOURNAL_LOOKBACK_LIMIT)]:
        structure = _format_position_structure(position)
        dte = _compute_position_dte(position)
        dte_text = f" | {dte} DTE" if dte is not None else ""
        lines.append(f"- Holding: {structure}{dte_text}")

        guidance = _build_whale_position_guidance(position, poc_level, whale_lean)
        if guidance:
            lines.append(f"  Guidance: {guidance}")

    return "\n".join(lines)


async def _build_journal_context_for_whale(
    ticker: str,
    poc_level: Optional[float],
    whale_lean: Optional[str],
) -> Optional[str]:
    return await asyncio.to_thread(
        _build_journal_context_for_whale_sync,
        ticker,
        poc_level,
        whale_lean,
    )


async def call_pivot_llm(prompt: str, max_tokens: int = 900) -> str:
    """Call the Pivot LLM (OpenRouter). Returns empty string on failure."""
    try:
        from llm.pivot_agent import call_llm  # type: ignore
        return await call_llm(prompt, max_tokens=max_tokens)
    except Exception as exc:
        logger.warning("Pivot LLM call failed: %s", exc)
        return ""


async def call_pivot_llm_messages(messages: List[Dict[str, Any]], max_tokens: int = 1200) -> str:
    """Call the Pivot LLM with full message objects (supports vision blocks)."""
    try:
        from llm.pivot_agent import call_llm_messages  # type: ignore
        return await call_llm_messages(messages, max_tokens=max_tokens)
    except Exception as exc:
        logger.warning("Pivot multimodal LLM call failed: %s", exc)
        return ""


def _chunk_message(text: str, limit: int = 1900) -> List[str]:
    """Split long text into Discord-safe chunks."""
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < int(limit * 0.6):
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < int(limit * 0.6):
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def send_discord_chunks(channel: discord.abc.Messageable, text: str, limit: int = 1900) -> None:
    """Send text in one or more Discord messages within character limits."""
    for chunk in _chunk_message(text, limit=limit):
        await channel.send(chunk)


def _is_csv_attachment(attachment: discord.Attachment) -> bool:
    name = (attachment.filename or "").lower()
    ctype = (attachment.content_type or "").lower()
    return name.endswith(".csv") or "csv" in ctype


def _looks_like_trade_import_text(text: str) -> bool:
    lower = (text or "").lower()
    if not lower.strip():
        return False
    triggers = ["import trades", "log these trades", "here are my trades", "bought", "sold", "put spread", "call spread"]
    return any(token in lower for token in triggers)


async def _parse_robinhood_csv_attachment(attachment: discord.Attachment) -> Optional[Dict[str, Any]]:
    try:
        raw = await attachment.read()
    except Exception as exc:
        logger.warning("Failed to read CSV attachment %s: %s", attachment.filename, exc)
        return None

    form = aiohttp.FormData()
    form.add_field(
        "file",
        raw,
        filename=attachment.filename or "trades.csv",
        content_type=attachment.content_type or "text/csv",
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PANDORA_API_URL}/analytics/parse-robinhood-csv",
                data=form,
                headers=_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.warning("CSV parse API failed: status=%s", resp.status)
                    return None
                return await resp.json()
    except Exception as exc:
        logger.warning("CSV parse request failed: %s", exc)
        return None


async def _parse_trade_text_with_llm(text: str) -> Optional[Dict[str, Any]]:
    prompt = (
        "Extract trades from this text and return strict JSON with key `trades` (list).\n"
        "Each trade object fields: ticker, direction, structure, entry_date, exit_date, "
        "entry_price, exit_price, strike, short_strike, long_strike, expiry, quantity, "
        "pnl_dollars, pnl_percent, exit_reason, status, account.\n"
        "If unknown, use null. Output JSON only.\n\n"
        f"TEXT:\n{text}"
    )
    raw = await call_pivot_llm(prompt, max_tokens=1200)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _format_trade_import_preview(payload: Dict[str, Any]) -> str:
    trades = payload.get("trades") or []
    open_positions = payload.get("open_positions") or []
    rows = list(trades) + list(open_positions)
    if not rows:
        return "No trades parsed."

    lines = ["📋 **PARSED TRADES**", ""]
    lines.append("# | Ticker | Structure | Entry | Exit | P&L")
    lines.append("--|--------|-----------|-------|------|------")
    total_pnl = 0.0
    for idx, trade in enumerate(rows[:25], start=1):
        ticker = str(trade.get("ticker") or "--").upper()
        structure = str(trade.get("structure") or "--")
        entry_date = str(trade.get("entry_date") or "--")
        exit_date = str(trade.get("exit_date") or "--")
        pnl = trade.get("pnl_dollars")
        if isinstance(pnl, (int, float)):
            total_pnl += float(pnl)
            pnl_text = f"${float(pnl):,.2f}"
        else:
            pnl_text = "--"
        lines.append(f"{idx} | {ticker} | {structure} | {entry_date} | {exit_date} | {pnl_text}")

    lines.append("")
    lines.append(
        f"Closed: {len(trades)} | Open: {len(open_positions)} | Total P&L (closed): ${total_pnl:,.2f}\n"
        "Reply **`import all`** to confirm, or reply **`cancel import`**."
    )
    return "\n".join(lines)


async def _execute_trade_import(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    import_payload = {
        "trades": [*(payload.get("trades") or []), *(payload.get("open_positions") or [])],
        "account": "robinhood",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PANDORA_API_URL}/analytics/import-trades",
                json=import_payload,
                headers=_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Trade import failed: status=%s", resp.status)
                    return None
                return await resp.json()
    except Exception as exc:
        logger.warning("Trade import request failed: %s", exc)
        return None


async def handle_whale_alerts_message(message: discord.Message) -> None:
    """
    Handle a message in #whale-alerts.

    Two signal types are processed:
      A. Whale Hunter plain-text signals (from our TradingView webhook)
      B. Unusual Whales Premium bot embeds

    For each, we:
      1. Parse the signal fields
      2. Fetch current bias from Pandora
      3. Ask the Pivot LLM for a Playbook evaluation
      4. Reply in the channel
    """
    # Skip the bot's own messages
    if message.author == bot.user:
        return

    parsed = None
    flow_text = None

    # â”€â”€ A. Whale Hunter plain-text signal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if message.content:
        parsed = parse_whale_hunter_signal(message)
        if parsed:
            flow_text = format_whale_hunter_for_llm(parsed)

    # â”€â”€ B. Unusual Whales Premium bot embed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not parsed and message.embeds:
        for embed in message.embeds:
            parsed = parse_uw_premium_embed(embed)
            if parsed:
                flow_text = format_uw_embed_for_llm(parsed)
                _record_recent_uw_flow(
                    parsed.get("ticker"),
                    sentiment=parsed.get("sentiment"),
                    flow_type=parsed.get("order_type"),
                    premium=parsed.get("premium"),
                    strike=parsed.get("strike"),
                    option_type=parsed.get("option_type"),
                    source="whale_alerts_embed",
                )
                break
        else:
            # Embeds present but none parsed â€” log field names for refinement
            for embed in message.embeds:
                if embed.fields:
                    field_names = [f.name for f in embed.fields]
                    logger.info(
                        "whale-alerts embed not parsed â€” field names: %s", field_names
                    )

    if not parsed or not flow_text:
        return  # Nothing actionable

    ticker = parsed.get("ticker", "?")
    source = parsed.get("source", "unknown")

    # â”€â”€ Fetch market context (bias + VIX + SPY + ticker) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ticker_hint = ticker if isinstance(ticker, str) and ticker.isalpha() else None
    market_context = await build_market_context(flow_text, ticker_hint=ticker_hint)
    uw_context_text, uw_alerts = await build_recent_uw_context(str(ticker_hint or ticker))
    market_context = f"{market_context}\n\n{uw_context_text}"

    convergence_block = None
    whale_conviction = "MODERATE"
    rvol_value: Optional[float] = None
    rvol_modifier = "RVOL_UNAVAILABLE"
    tick_confirmation: Optional[Dict[str, Any]] = None

    if source == "whale_hunter":
        poc_level = parsed.get("poc_level")
        target_price = float(poc_level) if isinstance(poc_level, (int, float)) else None
        event_ts = message.created_at if isinstance(message.created_at, datetime) else datetime.now(timezone.utc)
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)

        rvol_value = await _calculate_rvol_for_whale(str(ticker_hint or ticker), event_ts)
        whale_conviction, rvol_modifier = _apply_rvol_conviction_modifier("MODERATE", rvol_value)

        tick_confirmation = await _build_tick_whale_confirmation(parsed.get("lean"), event_ts)
        if tick_confirmation:
            if tick_confirmation.get("status") == "TICK_CONFIRMS":
                if whale_conviction == "WATCH":
                    whale_conviction = "MODERATE"
                elif whale_conviction == "MODERATE":
                    whale_conviction = "HIGH"
            elif tick_confirmation.get("status") == "TICK_CONTRADICTS":
                if whale_conviction == "HIGH":
                    whale_conviction = "MODERATE"
                elif whale_conviction == "MODERATE":
                    whale_conviction = "WATCH"

        parsed["rvol"] = rvol_value
        parsed["rvol_modifier"] = rvol_modifier
        if tick_confirmation:
            parsed["tick_confirmation"] = tick_confirmation

        options_context = await _get_options_context_for_ticker(str(ticker_hint or ticker), target_price=target_price)
        enrichment_lines = [options_context]
        if isinstance(rvol_value, (int, float)):
            enrichment_lines.append(
                f"Whale RVOL: {float(rvol_value):.2f}x ({rvol_modifier}) | Conviction: {whale_conviction}"
            )
        else:
            enrichment_lines.append("Whale RVOL: unavailable (conviction unchanged)")
        if tick_confirmation:
            enrichment_lines.append(
                f"TICK Confirmation: {tick_confirmation.get('status')} | "
                f"value {tick_confirmation.get('tick_value')} | "
                f"time {tick_confirmation.get('tick_time') or 'unknown'}"
            )
        market_context = f"{market_context}\n\n" + "\n".join(enrichment_lines)

        journal_context = await _build_journal_context_for_whale(
            str(ticker_hint or ticker),
            target_price,
            parsed.get("lean"),
        )
        if journal_context:
            market_context = f"{market_context}\n\n{journal_context}"
        convergence_block = _build_convergence_block(
            str(ticker_hint or ticker),
            parsed.get("lean"),
            poc_level if isinstance(poc_level, (int, float)) else None,
            uw_alerts,
        )

    # â”€â”€ LLM evaluation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from llm.prompts import (  # type: ignore
            build_flow_analysis_prompt,
            build_whale_hunter_prompt,
        )

        if source == "whale_hunter":
            prompt = _repeat_high_stakes_prompt(build_whale_hunter_prompt(flow_text, market_context))
            llm_response = await call_pivot_llm(prompt, max_tokens=2500)
        else:
            prompt = build_flow_analysis_prompt(flow_text, market_context)
            llm_response = await call_pivot_llm(prompt, max_tokens=1200)
    except Exception as exc:
        logger.warning("Could not build flow prompt: %s", exc)
        llm_response = ""

    # â”€â”€ Reply in channel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if source == "whale_hunter":
        lean = parsed.get("lean", "?")
        poc = parsed.get("poc_level")
        header = (
            f"**Whale Hunter â€” {ticker}** | Lean: `{lean}`"
            + (f" | POC: `${poc:.2f}`" if poc else "")
            + (f" | Conviction: `{whale_conviction}`" if whale_conviction else "")
        )
    else:
        opt_type = parsed.get("option_type", "")
        order_type = parsed.get("order_type", "")
        header = f"**UW Flow â€” {ticker}** {opt_type} {order_type}".strip()

    if llm_response:
        if convergence_block:
            reply = f"{header}\n\n{convergence_block}\n\n{llm_response}"
        else:
            reply = f"{header}\n\n{llm_response}"
    else:
        reply = (
            f"{header}\n\n"
            f"*(LLM unavailable â€” raw data logged. "
            f"Source: {source}, ticker: {ticker})*"
        )

    try:
        await send_discord_chunks(message.channel, reply)
    except discord.Forbidden:
        logger.warning("No permission to send in whale-alerts channel")
    except Exception as exc:
        logger.error("Failed to send whale-alerts reply: %s", exc)


def _extract_crypto_direction(signal_text: str) -> str:
    upper = (signal_text or "").upper()
    if any(token in upper for token in ("SHORT", "BEAR", "SELL")):
        return "SHORT"
    if any(token in upper for token in ("LONG", "BULL", "BUY")):
        return "LONG"
    return "UNKNOWN"


def _extract_crypto_strategy(signal_text: str) -> str:
    upper = (signal_text or "").upper()
    if "SNIPER" in upper:
        return "SNIPER"
    if "SCOUT" in upper:
        return "SCOUT"
    if "EXHAUSTION" in upper:
        return "EXHAUSTION"
    if "TRIPLE" in upper:
        return "TRIPLE_LINE"
    return "CRYPTO_SIGNAL"


async def handle_crypto_alerts_message(message: discord.Message) -> None:
    """
    Evaluate incoming crypto alert messages with crypto-native context.
    """
    if message.author == bot.user:
        return

    signal_text = _message_signal_text(message)
    if not signal_text:
        return

    ticker_hint = _extract_crypto_ticker_hint(signal_text) or _extract_ticker_hint(signal_text)
    direction = _extract_crypto_direction(signal_text)
    strategy = _extract_crypto_strategy(signal_text)

    crypto_context = await build_crypto_market_context(ticker_hint=ticker_hint)
    bias_context = await build_market_context(signal_text, ticker_hint="SPY")

    prompt = (
        "A crypto signal was detected. Evaluate it using the CRYPTO SIGNAL framework in your instructions.\n\n"
        f"Signal Type: {strategy}\n"
        f"Direction: {direction}\n"
        f"Ticker: {ticker_hint or 'UNKNOWN'}\n\n"
        f"SIGNAL:\n{signal_text}\n\n"
        f"CRYPTO MARKET CONTEXT:\n{crypto_context}\n\n"
        f"BROAD MARKET CONTEXT:\n{bias_context}\n\n"
        "Provide a concise tradeability read, invalidation level, and risk framing."
    )

    llm_response = await call_pivot_llm(_repeat_high_stakes_prompt(prompt), max_tokens=2500)
    if not llm_response:
        llm_response = (
            "LLM unavailable for crypto evaluation.\n\n"
            f"Context:\n{crypto_context}"
        )

    header = f"**Crypto Alert â€” {ticker_hint or 'UNKNOWN'}** | `{strategy}` | `{direction}`"
    await send_discord_chunks(message.channel, f"{header}\n\n{llm_response}")


# ================================
# EVENT HANDLERS
# ================================

@bot.event
async def on_ready():
    """Called when bot is connected and ready"""
    logger.info(f"ðŸ‹ Pandora Bridge v2.0 connected as {bot.user}")
    logger.info(f"ðŸ“¡ Watching UW channel ID: {UW_CHANNEL_ID}")
    if WHALE_ALERTS_CHANNEL_ID:
        logger.info(f"ðŸ³ Watching #whale-alerts channel ID: {WHALE_ALERTS_CHANNEL_ID}")
    if CRYPTO_ALERTS_CHANNEL_ID:
        logger.info(f"ðŸª™ Watching #crypto-alerts channel ID: {CRYPTO_ALERTS_CHANNEL_ID}")

    added_cols = await asyncio.to_thread(_ensure_journal_schema_columns_sync)
    if added_cols:
        logger.info("Journal schema updated with columns: %s", ", ".join(added_cols))
    
    # Find and verify the channel
    channel = bot.get_channel(UW_CHANNEL_ID)
    if channel:
        logger.info(f"âœ… Found channel: #{channel.name}")
        try:
            await channel.send("ðŸ”— **Pandora Bridge v2.0 Online**\n"
                             "â€¢ Watching for UW alerts\n"
                             "â€¢ Scheduled queries active\n"
                             "â€¢ Type `!help_pandora` for commands")
        except discord.Forbidden:
            logger.warning("Cannot send messages to channel (no permission)")
    else:
        logger.error(f"âŒ Could not find channel {UW_CHANNEL_ID}")
    
    # Start scheduled tasks
    if not scheduled_queries.is_running():
        scheduled_queries.start()
    if not reminder_scheduler.is_running():
        reminder_scheduler.start()
    if not uw_screenshot_request_scheduler.is_running():
        uw_screenshot_request_scheduler.start()
    if not trade_idea_poller.is_running():
        trade_idea_poller.start()
    if not uw_aggregate_poller.is_running():
        uw_aggregate_poller.start()

    logger.info(
        "Task status: scheduled_queries=%s, reminder_scheduler=%s, uw_screenshot_request_scheduler=%s, trade_idea_poller=%s, uw_aggregate_poller=%s",
        "running" if scheduled_queries.is_running() else "stopped",
        "running" if reminder_scheduler.is_running() else "stopped",
        "running" if uw_screenshot_request_scheduler.is_running() else "stopped",
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
        _record_recent_uw_flow(
            parsed.get("ticker"),
            sentiment=parsed.get("sentiment") or parsed.get("side"),
            flow_type=parsed.get("flow_type") or parsed.get("type"),
            premium=parsed.get("premium"),
            strike=parsed.get("strike"),
            option_type=parsed.get("option_type"),
            source="uw_flow_channel",
        )
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

    # â”€â”€ #whale-alerts: Whale Hunter signals + UW Premium embeds â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if WHALE_ALERTS_CHANNEL_ID and message.channel.id == WHALE_ALERTS_CHANNEL_ID:
        await handle_whale_alerts_message(message)
        return

    if CRYPTO_ALERTS_CHANNEL_ID and message.channel.id == CRYPTO_ALERTS_CHANNEL_ID:
        await handle_crypto_alerts_message(message)
        return

    uw_channels = {UW_FLOW_CHANNEL_ID, UW_TICKER_CHANNEL_ID}
    if message.channel.id in uw_channels and any(uw_channels):
        if message.author.id != UW_BOT_USER_ID:
            return
        if message.channel.id == UW_FLOW_CHANNEL_ID:
            await handle_uw_flow_message(message)
        elif message.channel.id == UW_TICKER_CHANNEL_ID:
            await handle_uw_ticker_message(message)
        return

    # â”€â”€ #pivot-chat: Conversational LLM chat â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if PIVOT_CHAT_CHANNEL_ID and message.channel.id == PIVOT_CHAT_CHANNEL_ID:
        async with message.channel.typing():
            user_text = message.content or ""
            reply = ""

            # Trade import confirmation flow.
            user_key = int(message.author.id)
            lower_text = user_text.strip().lower()
            if lower_text in {"import all", "confirm import"}:
                pending = pending_trade_imports.get(user_key)
                if pending:
                    result = await _execute_trade_import(pending)
                    if result:
                        pending_trade_imports.pop(user_key, None)
                        reply = (
                            "✅ Trade import complete.\n"
                            f"Imported: {result.get('imported', 0)} | "
                            f"Signal matched: {result.get('signal_matched', 0)} | "
                            f"Duplicates skipped: {result.get('duplicates_skipped', 0)} | "
                            f"Open positions: {result.get('open_positions', 0)} | "
                            f"Total P&L: ${float(result.get('total_pnl') or 0):,.2f}"
                        )
                    else:
                        reply = "Import failed. Try again in a minute."
                else:
                    reply = "No pending parsed trades found. Upload a CSV or paste trades first."
            elif lower_text in {"cancel import", "cancel"}:
                if pending_trade_imports.pop(user_key, None):
                    reply = "Cancelled pending trade import."

            # CSV import path.
            if not reply:
                csv_attachment = next((a for a in message.attachments if _is_csv_attachment(a)), None)
                if csv_attachment:
                    parsed_csv = await _parse_robinhood_csv_attachment(csv_attachment)
                    if parsed_csv:
                        pending_trade_imports[user_key] = parsed_csv
                        reply = _format_trade_import_preview(parsed_csv)
                    else:
                        reply = "Could not parse the CSV attachment. Make sure it's a Robinhood export."

            # Pasted/freeform import path.
            if not reply and _looks_like_trade_import_text(user_text):
                parsed_text = await _parse_trade_text_with_llm(user_text)
                if parsed_text and isinstance(parsed_text.get("trades"), list) and parsed_text.get("trades"):
                    preview = {
                        "format_detected": "freeform_text",
                        "raw_transactions": len(parsed_text.get("trades") or []),
                        "filtered_transactions": len(parsed_text.get("trades") or []),
                        "grouped_trades": len(parsed_text.get("trades") or []),
                        "trades": parsed_text.get("trades") or [],
                        "open_positions": [],
                        "warnings": [],
                    }
                    pending_trade_imports[user_key] = preview
                    reply = _format_trade_import_preview(preview)

            image_attachment = _first_image_attachment(message)
            if not reply and image_attachment:
                data_url = await _attachment_to_data_url(image_attachment)
                if data_url:
                    vision_text = (
                        "Extract trading data from this screenshot and evaluate it.\n\n"
                        "If this is an Unusual Whales dashboard, extract structured data:\n"
                        "- Market Tide: direction, net premium magnitude, top 3 tickers, accel/decel\n"
                        "- Dark Pool: largest prints (ticker/level/size), net sentiment, whale alignment clues\n"
                        "- GEX: positive/negative gamma, key levels, put wall, call wall\n"
                        "Then note whether the screenshot confirms or contradicts current bias."
                    )
                    if user_text.strip():
                        vision_text = f"{vision_text}\n\nUser request:\n{user_text.strip()}"

                    vision_messages = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": data_url}},
                                {"type": "text", "text": vision_text},
                            ],
                        }
                    ]
                    image_analysis = await call_pivot_llm_messages(
                        vision_messages,
                        max_tokens=PIVOT_VISION_MAX_TOKENS,
                    )

                    if image_analysis and not image_analysis.startswith("[LLM error"):
                        uw_dashboard_type = _detect_uw_dashboard_type(
                            image_analysis,
                            f"{user_text}\n{image_attachment.filename}",
                        )
                        if uw_dashboard_type:
                            await _post_uw_snapshot_to_backend(
                                dashboard_type=uw_dashboard_type,
                                summary_text=image_analysis,
                                time_slot=_uw_time_slot(get_et_now()),
                            )
                        detected_ticker = _extract_ticker_hint(f"{user_text}\n{image_analysis}")
                        if detected_ticker:
                            market_context = await build_market_context(
                                user_text or image_analysis,
                                ticker_hint=detected_ticker,
                            )
                            uw_context_text, _ = await build_recent_uw_context(detected_ticker)
                            options_context = await _get_options_context_for_ticker(detected_ticker)
                            follow_up_prompt = (
                                "You already extracted data from a trading screenshot. "
                                "Now combine that with live market context and provide "
                                "a concise, actionable evaluation.\n\n"
                                f"LIVE MARKET CONTEXT:\n{market_context}\n\n"
                                f"{uw_context_text}\n\n"
                                f"{options_context}\n\n"
                                f"IMAGE EXTRACT:\n{image_analysis}\n\n"
                                f"USER MESSAGE:\n{user_text or 'Evaluate this screenshot.'}"
                            )
                            contextual_eval = await call_pivot_llm(
                                _repeat_high_stakes_prompt(follow_up_prompt),
                                max_tokens=2500,
                            )
                            if contextual_eval:
                                reply = (
                                    f"**Image Extract**\n{image_analysis}\n\n"
                                    f"**Contextual Evaluation**\n{contextual_eval}"
                                )
                        if not reply:
                            reply = image_analysis

            if not reply:
                ticker_hint = _extract_ticker_hint(user_text)
                market_context = await build_market_context(user_text, ticker_hint=ticker_hint)

                if ticker_hint and _is_directional_question(user_text):
                    uw_context_text, _ = await build_recent_uw_context(ticker_hint)
                    options_context = await _get_options_context_for_ticker(ticker_hint)
                    market_context = (
                        f"{market_context}\n\n"
                        f"{uw_context_text}\n\n"
                        f"{options_context}"
                    )

                prompt = (
                    "Use this current market context when answering.\n\n"
                    f"{market_context}\n\n"
                    f"USER MESSAGE:\n{user_text or 'Give a quick market read.'}"
                )
                if ticker_hint and _is_directional_question(user_text):
                    prompt = _repeat_high_stakes_prompt(prompt)
                reply = await call_pivot_llm(prompt, max_tokens=1600)
        if reply:
            await send_discord_chunks(message.channel, reply)
        return

    # Only process UW responses in the designated channel
    if message.channel.id != UW_CHANNEL_ID:
        return
    
    # Check if message is from UW bot
    author_name = message.author.name.lower()
    is_uw_bot = any(name.lower() in author_name for name in UW_BOT_NAMES) or message.author.bot
    
    if not is_uw_bot:
        return
    
    logger.info(f"ðŸ“¨ Processing message from {message.author.name}")
    
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
        logger.info("UW image detected; attempting AI vision parse...")
        parsed_data = None
        try:
            # Optional dependency. On the Pivot VPS we may not have Claude Vision
            # libs installed; skip cleanly rather than crashing the whole bot.
            from utils.vision_parser import parse_uw_image  # type: ignore

            parsed_data = await parse_uw_image(image_url)
        except Exception as exc:
            logger.warning(f"Vision parser unavailable; skipping image parse: {exc}")

        if parsed_data:
            data_type = parsed_data.get("data_type", "other")
            dashboard_map = {
                "market_tide": "market_tide",
                "flow_alerts": "dark_pool",
                "highest_volume_contracts": "dark_pool",
                "oi_change": "dark_pool",
                "gex": "gex",
            }
            dashboard_type = dashboard_map.get(str(data_type))
            if dashboard_type:
                await _post_uw_snapshot_to_backend(
                    dashboard_type=dashboard_type,
                    summary_text=json.dumps(parsed_data),
                    time_slot=_uw_time_slot(get_et_now()),
                )

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
                await message.add_reaction("ðŸ“Š")
                continue
        
        if pending_queries["sectorflow"]:
            parsed_data = parse_sectorflow(embed)
            if parsed_data:
                pending_queries["sectorflow"] = False
                latest_data["sectorflow"] = parsed_data
                await send_sectorflow_to_pandora(parsed_data)
                await message.add_reaction("ðŸ“ˆ")
                continue
        
        if pending_queries["oi_increase"]:
            parsed_data = parse_oi_change(embed, increase=True)
            if parsed_data:
                pending_queries["oi_increase"] = False
                latest_data["oi_increase"] = parsed_data
                await message.add_reaction("ðŸ“ˆ")
                continue
        
        if pending_queries["economic_calendar"]:
            parsed_data = parse_economic_calendar(embed)
            if parsed_data:
                pending_queries["economic_calendar"] = False
                latest_data["economic_calendar"] = parsed_data
                await message.add_reaction("ðŸ“…")
                continue
        
        # If no pending query matched, try general flow alert parsing
        parsed_data = parse_flow_alert(embed)
        if parsed_data and parsed_data.get("ticker"):
            await send_flow_alert_to_pandora(parsed_data)
            try:
                await message.add_reaction("âœ…")
            except discord.Forbidden:
                pass


# ================================
# BOT COMMANDS
# ================================

@bot.command(name="help_pandora")
async def help_command(ctx):
    """Show Pandora Bridge help"""
    help_text = """
ðŸ‹ **Pandora Bridge v2.0 Commands**

**Manual Queries:**
â€¢ `!tide` - Query market tide now
â€¢ `!sector` - Query sector flow now
â€¢ `!oi` - Query OI changes now
â€¢ `!calendar` - Query economic calendar now
â€¢ `!flow TICKER` - Query flow for a specific ticker
â€¢ `!maxpain TICKER` - Query max pain for a ticker

**Status:**
â€¢ `!status` - Check bot status
â€¢ `!latest` - Show latest parsed data

**Testing:**
â€¢ `!test TICKER` - Send test flow to Pandora

**Manual Logging:**
â€¢ `!logflow AAPL bull sweep 500k` - Log a flow alert manually
â€¢ `!logtide bullish 65` - Log market tide manually

**Scheduled Queries (automatic):**
â€¢ Market Tide: 9:35 AM, 12:00 PM, 3:30 PM ET
â€¢ Sector Flow: Monday 10:00 AM ET
â€¢ OI Increase: Monday 10:05 AM ET
â€¢ Economic Calendar: Daily 8:30 AM ET
"""
    await ctx.send(help_text)


@bot.command(name="status")
async def status_command(ctx):
    """Check bridge status"""
    now = get_et_now()
    await ctx.send(f"ðŸ”— **Pandora Bridge v2.0 Status**\n"
                   f"â€¢ Connected: âœ…\n"
                   f"â€¢ Channel: <#{UW_CHANNEL_ID}>\n"
                   f"â€¢ API: {PANDORA_API_URL}\n"
                   f"â€¢ Time (ET): {now.strftime('%H:%M:%S')}\n"
                   f"â€¢ Market Hours: {'âœ…' if is_market_hours() else 'âŒ'}\n"
                   f"â€¢ Scheduler: {'Running' if scheduled_queries.is_running() else 'Stopped'}")


@bot.command(name="tasks")
async def tasks_command(ctx):
    """Show background task status"""
    await ctx.send(
        "ðŸ§° **Background Tasks**\n"
        f"â€¢ scheduled_queries: {'Running' if scheduled_queries.is_running() else 'Stopped'}\n"
        f"â€¢ reminder_scheduler: {'Running' if reminder_scheduler.is_running() else 'Stopped'}\n"
        f"â€¢ trade_idea_poller: {'Running' if trade_idea_poller.is_running() else 'Stopped'}"
    )


@bot.command(name="latest")
async def latest_command(ctx):
    """Show latest parsed data"""
    response = "ðŸ“Š **Latest Parsed Data**\n\n"
    
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
    await ctx.send("ðŸ“Š Querying market tide...")


@bot.command(name="sector")
async def sector_command(ctx):
    """Manually query sector flow"""
    pending_queries["sectorflow"] = True
    await send_uw_command(ctx.channel, "/sectorflow")
    await ctx.send("ðŸ“ˆ Querying sector flow...")


@bot.command(name="oi")
async def oi_command(ctx):
    """Manually query OI changes"""
    pending_queries["oi_increase"] = True
    await send_uw_command(ctx.channel, "/oi_increase")
    await ctx.send("ðŸ“Š Querying OI increase...")


@bot.command(name="calendar")
async def calendar_command(ctx):
    """Manually query economic calendar"""
    pending_queries["economic_calendar"] = True
    await send_uw_command(ctx.channel, "/economic_calendar")
    await ctx.send("ðŸ“… Querying economic calendar...")


@bot.command(name="flow")
async def flow_command(ctx, ticker: str = None):
    """Query flow for a specific ticker"""
    if not ticker:
        await ctx.send("âŒ Usage: `!flow TICKER` (e.g., `!flow AAPL`)")
        return
    
    pending_queries["flow_ticker"] = ticker.upper()
    await send_uw_command(ctx.channel, f"/flow_ticker {ticker.upper()}")
    await ctx.send(f"ðŸ” Querying flow for **{ticker.upper()}**...")


@bot.command(name="maxpain")
async def maxpain_command(ctx, ticker: str = None):
    """Query max pain for a ticker"""
    if not ticker:
        await ctx.send("âŒ Usage: `!maxpain TICKER` (e.g., `!maxpain SPY`)")
        return
    
    pending_queries["max_pain"] = ticker.upper()
    await send_uw_command(ctx.channel, f"/max_pain {ticker.upper()}")
    await ctx.send(f"ðŸ“ Querying max pain for **{ticker.upper()}**...")


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
            f"âœ… Logged: **{ticker.upper()}** {sentiment_normalized} "
            f"{flow_type_normalized} ${premium_value:,}"
        )
    else:
        await ctx.send("âŒ Failed to log flow to Pandora")


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
        await ctx.send(f"âœ… Logged market tide: **{sentiment_normalized}**{pct_text}")
    else:
        await ctx.send("âŒ Failed to log market tide")


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
        await ctx.send(f"âœ… Test flow sent for **{ticker.upper()}**")
    else:
        await ctx.send(f"âŒ Failed to send test flow - is Pandora's Box running?")


# ================================
# MAIN
# ================================

def run_bot():
    """Run the Discord bot"""
    if not DISCORD_TOKEN:
        logger.error("âŒ DISCORD_BOT_TOKEN environment variable not set!")
        logger.error("Set it with: export DISCORD_BOT_TOKEN='your-token-here'")
        return
    
    logger.info("ðŸš€ Starting Pandora Bridge v2.0...")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    run_bot()

