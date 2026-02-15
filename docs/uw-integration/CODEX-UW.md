# CODEX SPEC 3: Unusual Whales Integration via Pivot

**Pivot Repo:** `/opt/pivot/` on VPS (5.78.134.70)  
**Trading-Hub Repo:** `trading-hub/trading-hub/` (Railway)  
**Depends on:** CODEX-SIGNALS (Spec 2) must be completed first — the UW hooks in `cta_scanner.py` expect the Redis key patterns defined here.  
**Prerequisite:** Nick must purchase the UW Premium Discord Bot add-on ($6.95/mo) and configure it to auto-post Live Options Flow and Ticker Updates to dedicated channels in the Pandora's Box Discord server.

Read this ENTIRE document before writing any code.

---

## WHAT THIS BUILDS

A flow intelligence pipeline where:
1. The UW Premium Discord Bot auto-posts unusual options trades to channels in the Pandora's Box Discord server
2. A new Pivot service (Discord listener) monitors those channels and parses each embed into structured data
3. Pivot aggregates, filters, and scores the flow data
4. Pivot pushes two types of data to Railway Redis:
   - **Per-ticker flow summaries** (`uw:flow:{SYMBOL}`) — read by CTA scanner for signal confirmation (Spec 2 Item 8)
   - **Discovery list** (`uw:discovery`) — tickers with unusual activity that aren't in the watchlist, fed into the CTA scanner as priority scan targets
5. Aggressive filtering eliminates 0DTE noise, chronic high-volume tickers, and non-swing-relevant flow

---

## ARCHITECTURE OVERVIEW

```
UW Premium Bot ──auto-posts──► #uw-live-flow channel (Discord)
                               #uw-ticker-updates channel (Discord)
                                      │
                                      ▼
                    Pivot UW Listener (new service: pivot-uw.service)
                         │
                    Parse embeds → structured dicts
                         │
                    Filter: DTE ≥ 7, not blacklisted, relative unusualness
                         │
                    Aggregate per-ticker: net premium, sentiment, unusual count
                         │
                    ┌────┴────┐
                    ▼         ▼
            POST /uw/flow   POST /uw/discovery
            (Railway API)   (Railway API)
                    │         │
                    ▼         ▼
            Redis             Redis
            uw:flow:{SYM}     uw:discovery
            (1-hour TTL)      (4-hour TTL)
                    │         │
                    ▼         ▼
            CTA Scanner reads at signal time
            (Spec 2 Item 8: get_uw_flow_confirmation)
            CTA Scanner reads for priority scan targets
```

---

## TABLE OF CONTENTS

| Item | What It Does | Where |
|------|-------------|-------|
| 1 | Discord Setup Instructions — channel creation, bot configuration | Manual (Nick) |
| 2 | UW Listener Service — Discord.py bot that reads UW channel messages | Pivot VPS |
| 3 | Embed Parser — extracts structured data from UW bot embeds | Pivot VPS |
| 4 | Flow Filter — DTE, blacklist, relative unusualness scoring | Pivot VPS |
| 5 | Flow Aggregator — per-ticker summaries, discovery list | Pivot VPS |
| 6 | Railway API Endpoints — receive and cache UW data | Trading-Hub |
| 7 | Redis Key Schema — key patterns, TTLs, data shapes | Trading-Hub |
| 8 | CTA Scanner Discovery Integration — scan UW-discovered tickers | Trading-Hub |
| 9 | Configuration — env vars, filter thresholds, blacklist | Both |
| 10 | Systemd Service — pivot-uw.service | Pivot VPS |

---

## BUILD ORDER

1. **Discord Setup** (Item 1) — Nick does this manually, not code
2. **Configuration** (Item 9) — env vars and filter config first
3. **Embed Parser** (Item 3) — core parsing logic, testable standalone
4. **Flow Filter** (Item 4) — filtering logic, testable standalone
5. **Flow Aggregator** (Item 5) — aggregation logic
6. **Railway API Endpoints** (Item 6) — receive endpoints on trading-hub
7. **Redis Key Schema** (Item 7) — already defined, just documenting
8. **UW Listener Service** (Item 2) — ties everything together
9. **CTA Scanner Discovery** (Item 8) — scanner reads discovery list
10. **Systemd Service** (Item 10) — deploy and enable

---

## ITEM 1: Discord Setup Instructions (Manual — Nick Does This)

These steps must be completed before the code will work.

### Step 1: Purchase UW Premium Bot Add-On
- Go to https://unusualwhales.com/discord-bot
- Purchase the premium bot subscription ($6.95/mo) for the Pandora's Box Discord server

### Step 2: Create Dedicated Channels
In the Pandora's Box Discord server, create two new text channels:
- `#uw-live-flow` — for the live options flow stream
- `#uw-ticker-updates` — for ticker summary updates

### Step 3: Configure UW Bot Auto-Posts
In the `#uw-live-flow` channel, type `/configure` and enable:
- **Live Options Flow** — set to post to `#uw-live-flow`

In the `#uw-ticker-updates` channel, type `/configure` and enable:
- **Ticker Updates** — set to post to `#uw-ticker-updates`
- Add up to 10 high-priority tickers (e.g., SPY, QQQ, NVDA, TSLA, AAPL, AMZN, META, MSFT, GOOG, AMD)

### Step 4: Note the Channel IDs
Right-click each channel → Copy Channel ID (Developer Mode must be ON in Discord settings).
These go into the Pivot `.env` file as `UW_FLOW_CHANNEL_ID` and `UW_TICKER_CHANNEL_ID`.

### Step 5: Create a Bot Token for Pivot's Listener
The Pivot UW listener needs its own Discord bot token (or reuse the Pandora Bridge bot token if it has read access to these channels). The bot needs:
- `MESSAGE_CONTENT` intent (privileged — enable in Discord Developer Portal)
- Read Messages permission in `#uw-live-flow` and `#uw-ticker-updates`
- It does NOT need to send messages to these channels

---

## ITEM 2: UW Listener Service

### New File: `/opt/pivot/uw/listener.py`

This is a long-running Discord.py bot that listens for UW bot messages and processes them.

```python
"""
Unusual Whales Discord Listener for Pivot.

Monitors #uw-live-flow and #uw-ticker-updates channels for UW bot messages,
parses embeds into structured data, filters noise, aggregates flow,
and pushes summaries to Railway.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import tasks

from uw.parser import parse_flow_embed, parse_ticker_embed
from uw.filter import FlowFilter
from uw.aggregator import FlowAggregator
from collectors.base_collector import post_json

logger = logging.getLogger(__name__)

# Channel IDs from env
UW_FLOW_CHANNEL_ID = int(os.getenv("UW_FLOW_CHANNEL_ID", "0"))
UW_TICKER_CHANNEL_ID = int(os.getenv("UW_TICKER_CHANNEL_ID", "0"))

# The UW bot's user ID — used to filter only UW bot messages
# The free UW bot is "unusual_whales_crier" — get its user ID from Discord
UW_BOT_USER_ID = int(os.getenv("UW_BOT_USER_ID", "800519694754644029"))

DISCORD_TOKEN = os.getenv("PIVOT_DISCORD_TOKEN", "")


class UWListener(discord.Client):
    """Discord client that monitors UW bot channels."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read embed content
        super().__init__(intents=intents)

        self.flow_filter = FlowFilter()
        self.aggregator = FlowAggregator()

    async def on_ready(self):
        logger.info(f"UW Listener connected as {self.user} (ID: {self.user.id})")
        logger.info(f"Monitoring flow channel: {UW_FLOW_CHANNEL_ID}")
        logger.info(f"Monitoring ticker channel: {UW_TICKER_CHANNEL_ID}")
        self.push_aggregates.start()

    async def on_message(self, message: discord.Message):
        """Process messages from UW bot only."""
        # Ignore messages not from the UW bot
        if message.author.id != UW_BOT_USER_ID:
            return

        try:
            if message.channel.id == UW_FLOW_CHANNEL_ID:
                await self._handle_flow_message(message)
            elif message.channel.id == UW_TICKER_CHANNEL_ID:
                await self._handle_ticker_message(message)
        except Exception as e:
            logger.error(f"Error processing UW message: {e}", exc_info=True)

    async def _handle_flow_message(self, message: discord.Message):
        """Parse and filter a live options flow alert."""
        for embed in message.embeds:
            parsed = parse_flow_embed(embed)
            if parsed is None:
                continue

            # Apply filters
            if not self.flow_filter.passes(parsed):
                logger.debug(f"Filtered out: {parsed.get('ticker')} DTE={parsed.get('dte')} — {self.flow_filter.last_reject_reason}")
                continue

            # Add to aggregator
            self.aggregator.add_flow(parsed)
            logger.info(f"UW Flow: {parsed['ticker']} {parsed['side']} {parsed['strike']}{'C' if parsed['option_type'] == 'CALL' else 'P'} ${parsed['premium']:,.0f} DTE={parsed['dte']}")

    async def _handle_ticker_message(self, message: discord.Message):
        """Parse a ticker summary update."""
        for embed in message.embeds:
            parsed = parse_ticker_embed(embed)
            if parsed is None:
                continue

            # Ticker updates bypass flow filter (already curated by UW)
            self.aggregator.update_ticker_summary(parsed)
            logger.info(f"UW Ticker Update: {parsed['ticker']} P/C={parsed.get('put_call_ratio', 'N/A')}")

    @tasks.loop(minutes=5)
    async def push_aggregates(self):
        """
        Every 5 minutes, push aggregated flow data and discovery list to Railway.
        """
        try:
            # Push per-ticker flow summaries
            flow_summaries = self.aggregator.get_flow_summaries()
            if flow_summaries:
                await post_json("/uw/flow", {
                    "summaries": flow_summaries,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                logger.info(f"Pushed flow summaries for {len(flow_summaries)} tickers")

            # Push discovery list (tickers with unusual activity not in watchlist)
            discovery = self.aggregator.get_discovery_list()
            if discovery:
                await post_json("/uw/discovery", {
                    "tickers": discovery,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                logger.info(f"Pushed discovery list: {len(discovery)} tickers")

        except Exception as e:
            logger.error(f"Error pushing UW aggregates: {e}", exc_info=True)

    @push_aggregates.before_loop
    async def before_push(self):
        await self.wait_until_ready()


def run():
    """Entry point for the UW listener service."""
    if not DISCORD_TOKEN:
        logger.error("PIVOT_DISCORD_TOKEN not set — cannot start UW listener")
        return
    if not UW_FLOW_CHANNEL_ID:
        logger.error("UW_FLOW_CHANNEL_ID not set — cannot start UW listener")
        return

    client = UWListener()
    client.run(DISCORD_TOKEN)
```

### New File: `/opt/pivot/uw/__init__.py`

```python
# UW integration package
```

### New File: `/opt/pivot/uw/__main__.py`

```python
"""Entry point: python -m uw"""
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/opt/pivot/logs/uw.log"),
    ],
)
from uw.listener import run
run()
```

---

## ITEM 3: Embed Parser

### New File: `/opt/pivot/uw/parser.py`

UW bot embeds have a consistent structure. The parser extracts structured data from them.

```python
"""
Parse Unusual Whales Discord bot embeds into structured dicts.

UW flow embeds typically have these fields in the embed:
- Title: Ticker symbol and/or contract description
- Fields: Strike, Expiry, Premium, Side (BUY/SELL), Sentiment, Volume, OI, etc.
- Description: Additional context

IMPORTANT: The exact embed format may change when UW updates their bot.
If parsing starts failing, check the raw embed structure by enabling debug logging.
The parser uses defensive field access throughout — missing fields return None, not errors.
"""
import logging
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import discord

logger = logging.getLogger(__name__)


def parse_flow_embed(embed: discord.Embed) -> Optional[Dict[str, Any]]:
    """
    Parse a Live Options Flow embed from the UW premium bot.

    Returns a dict with standardized fields, or None if parsing fails.
    """
    try:
        fields = {f.name.strip().lower(): f.value.strip() for f in embed.fields}
        title = embed.title or ""
        description = embed.description or ""

        # Extract ticker from title (usually the first word or bolded text)
        ticker = _extract_ticker(title, description)
        if not ticker:
            logger.debug(f"Could not extract ticker from embed: {title}")
            return None

        # Extract core fields
        result = {
            "ticker": ticker.upper(),
            "option_type": _extract_option_type(fields, title, description),
            "strike": _extract_float(fields, ["strike", "strike price"]),
            "expiry": _extract_date(fields, ["expiry", "expiration", "exp"]),
            "premium": _extract_premium(fields, ["premium", "total premium", "value"]),
            "side": _extract_side(fields, title, description),
            "sentiment": _extract_sentiment(fields, title, description),
            "volume": _extract_int(fields, ["volume", "vol"]),
            "open_interest": _extract_int(fields, ["open interest", "oi"]),
            "dte": None,  # Calculated below
            "raw_title": title,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Calculate DTE
        if result["expiry"]:
            try:
                exp_date = datetime.strptime(result["expiry"], "%Y-%m-%d").date()
                result["dte"] = (exp_date - date.today()).days
            except (ValueError, TypeError):
                result["dte"] = None

        # Validate: must have at minimum ticker + premium OR ticker + volume
        if not result["ticker"]:
            return None
        if not result["premium"] and not result["volume"]:
            logger.debug(f"Insufficient data for {ticker}: no premium or volume")
            return None

        return result

    except Exception as e:
        logger.warning(f"Failed to parse flow embed: {e}")
        _debug_embed(embed)
        return None


def parse_ticker_embed(embed: discord.Embed) -> Optional[Dict[str, Any]]:
    """
    Parse a Ticker Update embed from the UW premium bot.

    Ticker updates contain summary data: price, volume, P/C ratio, total premium.
    """
    try:
        fields = {f.name.strip().lower(): f.value.strip() for f in embed.fields}
        title = embed.title or ""
        description = embed.description or ""

        ticker = _extract_ticker(title, description)
        if not ticker:
            return None

        result = {
            "ticker": ticker.upper(),
            "price": _extract_float(fields, ["price", "last"]),
            "share_volume": _extract_int(fields, ["share volume", "volume"]),
            "call_volume": _extract_int(fields, ["call volume", "calls"]),
            "put_volume": _extract_int(fields, ["put volume", "puts"]),
            "put_call_ratio": _extract_float(fields, ["put/call ratio", "p/c ratio", "pcr"]),
            "total_premium": _extract_premium(fields, ["total premium", "premium"]),
            "timestamp": datetime.utcnow().isoformat(),
        }

        return result

    except Exception as e:
        logger.warning(f"Failed to parse ticker embed: {e}")
        return None


# --- Extraction Helpers ---

def _extract_ticker(title: str, description: str) -> Optional[str]:
    """Extract ticker symbol from title or description."""
    # Common patterns: "$NVDA", "NVDA", "**NVDA**"
    patterns = [
        r'\$([A-Z]{1,5})\b',           # $NVDA
        r'\*\*([A-Z]{1,5})\*\*',       # **NVDA**
        r'^([A-Z]{1,5})\b',            # NVDA at start of title
        r'\b([A-Z]{1,5})\s+\d+',       # NVDA 850 (ticker before strike)
    ]
    for pattern in patterns:
        for text in [title, description]:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1)
                # Filter out common non-ticker words
                if candidate not in {"THE", "FOR", "AND", "BUY", "SELL", "PUT", "CALL", "NEW", "OI", "VOL"}:
                    return candidate
    return None


def _extract_option_type(fields: dict, title: str, description: str) -> Optional[str]:
    """Extract CALL or PUT."""
    combined = f"{title} {description} {' '.join(fields.values())}".upper()
    if "CALL" in combined or " C " in combined:
        return "CALL"
    elif "PUT" in combined or " P " in combined:
        return "PUT"
    return None


def _extract_side(fields: dict, title: str, description: str) -> Optional[str]:
    """Extract BUY or SELL side."""
    for key in ["side", "type", "transaction"]:
        if key in fields:
            val = fields[key].upper()
            if "BUY" in val or "ASK" in val:
                return "BUY"
            elif "SELL" in val or "BID" in val:
                return "SELL"
    # Check title/description
    combined = f"{title} {description}".upper()
    if "BOUGHT" in combined or "BUY" in combined or "ASK SIDE" in combined:
        return "BUY"
    elif "SOLD" in combined or "SELL" in combined or "BID SIDE" in combined:
        return "SELL"
    return None


def _extract_sentiment(fields: dict, title: str, description: str) -> Optional[str]:
    """Extract BULLISH or BEARISH sentiment."""
    for key in ["sentiment", "bias", "direction"]:
        if key in fields:
            val = fields[key].upper()
            if "BULL" in val:
                return "BULLISH"
            elif "BEAR" in val:
                return "BEARISH"
    # Infer from option type + side
    # Buy calls or sell puts = bullish; Buy puts or sell calls = bearish
    return None


def _extract_float(fields: dict, keys: List[str]) -> Optional[float]:
    """Extract a float value from multiple possible field names."""
    for key in keys:
        if key in fields:
            try:
                cleaned = re.sub(r'[,$%]', '', fields[key])
                return float(cleaned)
            except (ValueError, TypeError):
                continue
    return None


def _extract_int(fields: dict, keys: List[str]) -> Optional[int]:
    """Extract an integer value."""
    for key in keys:
        if key in fields:
            try:
                cleaned = re.sub(r'[,$]', '', fields[key])
                return int(float(cleaned))
            except (ValueError, TypeError):
                continue
    return None


def _extract_premium(fields: dict, keys: List[str]) -> Optional[float]:
    """Extract premium/dollar amount, handling K/M suffixes."""
    for key in keys:
        if key in fields:
            try:
                val = fields[key].strip().upper()
                val = val.replace('$', '').replace(',', '')
                if val.endswith('M'):
                    return float(val[:-1]) * 1_000_000
                elif val.endswith('K'):
                    return float(val[:-1]) * 1_000
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def _extract_date(fields: dict, keys: List[str]) -> Optional[str]:
    """Extract expiration date, normalize to YYYY-MM-DD."""
    for key in keys:
        if key in fields:
            val = fields[key].strip()
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%b %d, %Y", "%b %d %Y"]:
                try:
                    dt = datetime.strptime(val, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
    return None


def _debug_embed(embed: discord.Embed):
    """Log raw embed structure for debugging parse failures."""
    logger.debug(f"Embed title: {embed.title}")
    logger.debug(f"Embed description: {embed.description}")
    for f in embed.fields:
        logger.debug(f"  Field '{f.name}': '{f.value}'")
```

---

## ITEM 4: Flow Filter

### New File: `/opt/pivot/uw/filter.py`

```python
"""
Filter UW flow alerts to keep only swing-relevant institutional activity.

Three filter layers:
1. DTE Filter — reject 0DTE / short-dated options (< 7 DTE)
2. Blacklist Filter — suppress chronic high-volume tickers from discovery (configurable)
3. Relative Unusualness — decay novelty score for tickers that fire too frequently

The filter does NOT remove data — it prevents filtered alerts from reaching
the aggregator. Filtered tickers still get ticker-level flow summaries if
they come through the curated Ticker Updates channel.
"""
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# --- Configuration ---

# Minimum days to expiration. Anything below this is day-trading noise.
MIN_DTE = int(os.getenv("UW_MIN_DTE", "7"))

# Maximum DTE. Ignore LEAPS (> 180 days) as they're often hedges, not directional.
MAX_DTE = int(os.getenv("UW_MAX_DTE", "180"))

# Minimum premium in dollars. Filter out tiny retail trades.
MIN_PREMIUM = float(os.getenv("UW_MIN_PREMIUM", "50000"))  # $50K minimum

# Tickers excluded from the DISCOVERY pipeline (not from flow summaries).
# These generate constant flow and are already in the manual watchlist.
# They still get uw:flow:{SYMBOL} summaries for signal confirmation.
DISCOVERY_BLACKLIST = set(os.getenv(
    "UW_DISCOVERY_BLACKLIST",
    "SPY,QQQ,IWM,NVDA,TSLA,AAPL,AMZN,META,MSFT,GOOG,AMD"
).split(","))

# Max alerts per ticker per hour before novelty decays.
# If CRWD fires 1 alert, it's unusual. If it fires 20, each one means less.
NOVELTY_DECAY_THRESHOLD = int(os.getenv("UW_NOVELTY_THRESHOLD", "5"))

# Window for counting alerts (minutes)
NOVELTY_WINDOW_MINUTES = int(os.getenv("UW_NOVELTY_WINDOW", "60"))


class FlowFilter:
    """Stateful filter that tracks alert frequency for novelty scoring."""

    def __init__(self):
        # ticker → list of timestamps for recent alerts
        self._alert_history: Dict[str, list] = defaultdict(list)
        self.last_reject_reason: Optional[str] = None

    def passes(self, flow: dict) -> bool:
        """
        Return True if this flow alert passes all filters.
        Sets self.last_reject_reason on rejection.
        """
        self.last_reject_reason = None
        ticker = flow.get("ticker", "")

        # 1. DTE Filter
        dte = flow.get("dte")
        if dte is not None:
            if dte < MIN_DTE:
                self.last_reject_reason = f"DTE too low: {dte} < {MIN_DTE}"
                return False
            if dte > MAX_DTE:
                self.last_reject_reason = f"DTE too high: {dte} > {MAX_DTE}"
                return False

        # 2. Premium Filter
        premium = flow.get("premium")
        if premium is not None and premium < MIN_PREMIUM:
            self.last_reject_reason = f"Premium too low: ${premium:,.0f} < ${MIN_PREMIUM:,.0f}"
            return False

        # 3. Track frequency and score novelty
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=NOVELTY_WINDOW_MINUTES)

        # Clean old entries
        self._alert_history[ticker] = [
            t for t in self._alert_history[ticker] if t > cutoff
        ]

        # Add current
        self._alert_history[ticker].append(now)

        # Check novelty (don't reject — but mark as low novelty)
        # The aggregator uses this to weight signals
        alert_count = len(self._alert_history[ticker])
        flow["_novelty_score"] = min(1.0, NOVELTY_DECAY_THRESHOLD / max(alert_count, 1))
        flow["_alert_count_1h"] = alert_count

        return True

    def is_discovery_eligible(self, ticker: str) -> bool:
        """
        Return True if this ticker should be included in the discovery list.
        Blacklisted tickers are excluded from discovery but still get flow summaries.
        """
        return ticker.upper() not in DISCOVERY_BLACKLIST

    def get_novelty_score(self, ticker: str) -> float:
        """Return current novelty score for a ticker (0.0 to 1.0)."""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=NOVELTY_WINDOW_MINUTES)
        recent = [t for t in self._alert_history.get(ticker, []) if t > cutoff]
        count = len(recent)
        if count == 0:
            return 1.0
        return min(1.0, NOVELTY_DECAY_THRESHOLD / count)
```

---

## ITEM 5: Flow Aggregator

### New File: `/opt/pivot/uw/aggregator.py`

```python
"""
Aggregate parsed UW flow alerts into per-ticker summaries and a discovery list.

Maintains a rolling window of flow data. Every 5 minutes (triggered by the listener),
it produces:
1. Per-ticker flow summaries for all tickers seen
2. A ranked discovery list of tickers not in the user's watchlist
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# How long to keep flow data before aging it out
FLOW_WINDOW_MINUTES = 120  # 2 hours rolling window


class FlowAggregator:
    """Accumulates flow alerts and produces summaries."""

    def __init__(self):
        # ticker → list of parsed flow dicts
        self._flows: Dict[str, List[Dict]] = defaultdict(list)
        # ticker → latest ticker summary from UW Ticker Updates channel
        self._ticker_summaries: Dict[str, Dict] = {}

    def add_flow(self, flow: dict):
        """Add a parsed, filtered flow alert."""
        ticker = flow["ticker"]
        flow["_received_at"] = datetime.utcnow()
        self._flows[ticker].append(flow)

    def update_ticker_summary(self, summary: dict):
        """Update the latest ticker summary from the Ticker Updates channel."""
        self._ticker_summaries[summary["ticker"]] = summary

    def get_flow_summaries(self) -> List[Dict[str, Any]]:
        """
        Produce per-ticker flow summaries for all tickers with recent activity.
        This is what gets written to Redis as uw:flow:{SYMBOL}.
        """
        self._prune_old()
        summaries = []

        for ticker, flows in self._flows.items():
            if not flows:
                continue

            call_premium = 0.0
            put_premium = 0.0
            buy_count = 0
            sell_count = 0
            unusual_count = len(flows)
            avg_dte = 0
            total_dte = 0
            dte_count = 0
            max_premium_trade = None
            max_premium = 0

            for f in flows:
                premium = f.get("premium") or 0
                option_type = f.get("option_type")
                side = f.get("side")

                # Determine premium direction
                # Buy calls = bullish premium; Sell calls = bearish premium
                # Buy puts = bearish premium; Sell puts = bullish premium
                if option_type == "CALL":
                    if side == "BUY":
                        call_premium += premium
                        buy_count += 1
                    elif side == "SELL":
                        call_premium -= premium
                        sell_count += 1
                    else:
                        # Unknown side — default to bullish for calls
                        call_premium += premium
                elif option_type == "PUT":
                    if side == "BUY":
                        put_premium += premium
                        buy_count += 1
                    elif side == "SELL":
                        put_premium -= premium
                        sell_count += 1
                    else:
                        put_premium += premium

                # Track DTE
                if f.get("dte") is not None:
                    total_dte += f["dte"]
                    dte_count += 1

                # Track largest single trade
                if premium > max_premium:
                    max_premium = premium
                    max_premium_trade = f

            net_premium = call_premium - put_premium
            avg_dte = round(total_dte / dte_count) if dte_count > 0 else None

            # Determine overall sentiment
            if net_premium > 0 and call_premium > put_premium * 1.5:
                sentiment = "BULLISH"
            elif net_premium < 0 and put_premium > call_premium * 1.5:
                sentiment = "BEARISH"
            else:
                sentiment = "MIXED"

            # Novelty score: average across all flows for this ticker
            novelty_scores = [f.get("_novelty_score", 1.0) for f in flows]
            avg_novelty = sum(novelty_scores) / len(novelty_scores) if novelty_scores else 1.0

            # Compute an overall "unusualness" score
            # Factors: premium size, novelty, alert count
            # Higher = more interesting
            unusualness_score = round(
                (min(abs(net_premium), 5_000_000) / 5_000_000)  # Normalize premium to 0-1
                * avg_novelty                                     # Decay for frequent tickers
                * min(unusual_count / 3, 1.0)                    # Boost for multiple alerts
                * 100,                                            # Scale to 0-100
                1,
            )

            summary = {
                "ticker": ticker,
                "net_premium": round(net_premium, 2),
                "call_premium": round(call_premium, 2),
                "put_premium": round(put_premium, 2),
                "sentiment": sentiment,
                "unusual_count": unusual_count,
                "buy_count": buy_count,
                "sell_count": sell_count,
                "avg_dte": avg_dte,
                "novelty": round(avg_novelty, 2),
                "unusualness_score": unusualness_score,
                "largest_trade": {
                    "premium": max_premium,
                    "strike": max_premium_trade.get("strike") if max_premium_trade else None,
                    "expiry": max_premium_trade.get("expiry") if max_premium_trade else None,
                    "option_type": max_premium_trade.get("option_type") if max_premium_trade else None,
                } if max_premium_trade else None,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Merge ticker summary data if available
            ticker_summary = self._ticker_summaries.get(ticker)
            if ticker_summary:
                summary["put_call_ratio"] = ticker_summary.get("put_call_ratio")
                summary["share_volume"] = ticker_summary.get("share_volume")

            summaries.append(summary)

        return summaries

    def get_discovery_list(self) -> List[Dict[str, Any]]:
        """
        Produce a ranked list of tickers for the CTA scanner to investigate.
        Excludes blacklisted tickers (handled at the Railway endpoint).
        Sorted by unusualness_score descending.
        Returns top 20.
        """
        from uw.filter import FlowFilter
        flow_filter = FlowFilter()

        summaries = self.get_flow_summaries()

        # Filter for discovery eligibility
        discovery = []
        for s in summaries:
            if flow_filter.is_discovery_eligible(s["ticker"]):
                discovery.append({
                    "ticker": s["ticker"],
                    "unusualness_score": s["unusualness_score"],
                    "sentiment": s["sentiment"],
                    "net_premium": s["net_premium"],
                    "unusual_count": s["unusual_count"],
                    "avg_dte": s["avg_dte"],
                })

        # Sort by unusualness score, take top 20
        discovery.sort(key=lambda x: x["unusualness_score"], reverse=True)
        return discovery[:20]

    def _prune_old(self):
        """Remove flow alerts older than the rolling window."""
        cutoff = datetime.utcnow() - timedelta(minutes=FLOW_WINDOW_MINUTES)
        for ticker in list(self._flows.keys()):
            self._flows[ticker] = [
                f for f in self._flows[ticker]
                if f.get("_received_at", datetime.min) > cutoff
            ]
            if not self._flows[ticker]:
                del self._flows[ticker]
```

---

## ITEM 6: Railway API Endpoints

### Add to Trading-Hub: `backend/api/uw.py` (new file)

```python
"""
API endpoints for receiving UW flow data from Pivot and caching in Redis.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Request
from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/uw", tags=["unusual-whales"])

FLOW_TTL = 3600       # 1 hour TTL for per-ticker flow data
DISCOVERY_TTL = 14400  # 4 hour TTL for discovery list


@router.post("/flow")
async def receive_uw_flow(request: Request):
    """
    Receive per-ticker flow summaries from Pivot.
    Write each to Redis as uw:flow:{SYMBOL}.
    """
    try:
        body = await request.json()
        summaries = body.get("summaries", [])

        client = await get_redis_client()
        if not client:
            return {"status": "error", "message": "Redis unavailable"}

        written = 0
        for summary in summaries:
            ticker = summary.get("ticker")
            if not ticker:
                continue
            key = f"uw:flow:{ticker.upper()}"
            await client.set(key, json.dumps(summary), ex=FLOW_TTL)
            written += 1

        logger.info(f"UW flow: cached {written} ticker summaries")
        return {"status": "success", "cached": written}

    except Exception as e:
        logger.error(f"Error receiving UW flow: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/discovery")
async def receive_uw_discovery(request: Request):
    """
    Receive discovery list from Pivot.
    Write to Redis as uw:discovery (single key, list of tickers).
    """
    try:
        body = await request.json()
        tickers = body.get("tickers", [])

        client = await get_redis_client()
        if not client:
            return {"status": "error", "message": "Redis unavailable"}

        await client.set("uw:discovery", json.dumps(tickers), ex=DISCOVERY_TTL)

        logger.info(f"UW discovery: cached {len(tickers)} tickers")
        return {"status": "success", "cached": len(tickers)}

    except Exception as e:
        logger.error(f"Error receiving UW discovery: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/flow/{ticker}")
async def get_uw_flow(ticker: str):
    """
    Read cached UW flow data for a specific ticker.
    Used by the frontend to display flow context alongside signals.
    """
    client = await get_redis_client()
    if not client:
        return {"status": "error", "available": False}

    data = await client.get(f"uw:flow:{ticker.upper()}")
    if data:
        return {"status": "success", "available": True, "flow": json.loads(data)}
    return {"status": "success", "available": False, "flow": None}


@router.get("/discovery")
async def get_uw_discovery():
    """
    Read the current discovery list.
    Used by the dashboard and the CTA scanner.
    """
    client = await get_redis_client()
    if not client:
        return {"status": "error", "tickers": []}

    data = await client.get("uw:discovery")
    if data:
        return {"status": "success", "tickers": json.loads(data)}
    return {"status": "success", "tickers": []}
```

### Register the Router

In `backend/main.py`, add:

```python
from api.uw import router as uw_router
app.include_router(uw_router)
```

---

## ITEM 7: Redis Key Schema

| Key Pattern | Written By | Read By | TTL | Data Shape |
|---|---|---|---|---|
| `uw:flow:{SYMBOL}` | Railway POST /uw/flow | `get_uw_flow_confirmation()` in cta_scanner.py (Spec 2) | 3600s (1 hr) | `{"ticker": "CRWD", "net_premium": 1250000, "sentiment": "BULLISH", "unusual_count": 3, "novelty": 0.8, "unusualness_score": 72.5, "avg_dte": 28, ...}` |
| `uw:discovery` | Railway POST /uw/discovery | `run_cta_scan_scheduled()` in cta_scanner.py | 14400s (4 hr) | `[{"ticker": "CRWD", "unusualness_score": 72.5, "sentiment": "BULLISH", "net_premium": 1250000, "unusual_count": 3, "avg_dte": 28}, ...]` |

---

## ITEM 8: CTA Scanner Discovery Integration

### Modify `run_cta_scan_scheduled()` in `backend/scanners/cta_scanner.py`

At the start of each scheduled scan, check Redis for UW discovery tickers and add them to the scan universe with high priority:

```python
async def run_cta_scan_scheduled():
    """Run the full CTA scan on the universe."""
    from database.redis_client import get_redis_client
    import json

    # Get base universe from watchlist_tickers (Spec 1)
    universe = await get_scan_universe()

    # Inject UW discovery tickers if available
    try:
        client = await get_redis_client()
        if client:
            discovery_raw = await client.get("uw:discovery")
            if discovery_raw:
                discovery = json.loads(discovery_raw)
                discovery_tickers = {d["ticker"] for d in discovery if d.get("ticker")}
                existing_tickers = {t["ticker"] for t in universe}

                uw_added = 0
                for d in discovery:
                    ticker = d.get("ticker")
                    if ticker and ticker not in existing_tickers:
                        universe.append({
                            "ticker": ticker,
                            "source": "uw_discovery",
                            "priority": "high",
                            "uw_score": d.get("unusualness_score", 0),
                        })
                        uw_added += 1

                if uw_added:
                    logger.info(f"Added {uw_added} UW discovery tickers to scan universe")

                    # Also auto-add to watchlist_tickers with source='discovery'
                    # so they persist and get enriched
                    pool = await get_postgres_client()
                    if pool:
                        async with pool.acquire() as conn:
                            for d in discovery:
                                ticker = d.get("ticker")
                                if ticker and ticker not in existing_tickers:
                                    await conn.execute("""
                                        INSERT INTO watchlist_tickers
                                            (symbol, source, priority, added_at)
                                        VALUES ($1, 'discovery', 'low', NOW())
                                        ON CONFLICT (symbol) DO UPDATE
                                        SET last_scan = NOW()
                                    """, ticker)
    except Exception as e:
        logger.warning(f"Failed to load UW discovery: {e}")

    # Sort universe: high priority first, UW discovery second, rest after
    priority_order = {"high": 0, "medium": 1, "low": 2}
    universe.sort(key=lambda t: (
        priority_order.get(t.get("priority", "low"), 2),
        -t.get("uw_score", 0),  # Higher UW score = scan first
    ))

    # Continue with existing scan logic...
    # (the rest of the function stays the same)
```

### Discovery Ticker Cleanup

Discovery tickers that never produce a signal should age out. Add this to the nightly `score_pending_signals()` job (Spec 2 Item 11), or as a separate weekly job:

```python
async def cleanup_stale_discovery_tickers():
    """
    Remove discovery tickers from watchlist_tickers that:
    - Have source='discovery'
    - Were added more than 7 days ago
    - Never generated a signal (no entry in signal_outcomes for this ticker)
    """
    from database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    if not pool:
        return

    async with pool.acquire() as conn:
        deleted = await conn.execute("""
            DELETE FROM watchlist_tickers wt
            WHERE wt.source = 'discovery'
            AND wt.added_at < NOW() - INTERVAL '7 days'
            AND NOT EXISTS (
                SELECT 1 FROM signal_outcomes so
                WHERE so.symbol = wt.symbol
                AND so.created_at > wt.added_at
            )
        """)
        logger.info(f"Cleaned up stale discovery tickers: {deleted}")
```

---

## ITEM 9: Configuration

### Pivot `.env` additions (`/opt/pivot/.env`)

```bash
# UW Discord Listener
PIVOT_DISCORD_TOKEN=your_bot_token_here
UW_FLOW_CHANNEL_ID=123456789012345678
UW_TICKER_CHANNEL_ID=123456789012345679
UW_BOT_USER_ID=800519694754644029

# UW Filter Configuration
UW_MIN_DTE=7
UW_MAX_DTE=180
UW_MIN_PREMIUM=50000
UW_DISCOVERY_BLACKLIST=SPY,QQQ,IWM,NVDA,TSLA,AAPL,AMZN,META,MSFT,GOOG,AMD
UW_NOVELTY_THRESHOLD=5
UW_NOVELTY_WINDOW=60
```

### Notes on Configuration

- `PIVOT_DISCORD_TOKEN`: Can reuse the Pandora Bridge bot token IF that bot is in the same server and has MESSAGE_CONTENT intent. Otherwise, create a new bot application in the Discord Developer Portal.
- `UW_BOT_USER_ID`: Default is the public UW crier bot ID. Verify this is correct by right-clicking the UW bot in Discord → Copy User ID.
- `UW_DISCOVERY_BLACKLIST`: Comma-separated. These tickers still get `uw:flow:{SYMBOL}` data for signal confirmation — they're only excluded from the discovery pipeline that auto-adds new tickers to the scan universe. Nick can add/remove tickers from this list at any time.
- `UW_MIN_PREMIUM`: Set to $50K by default. If Nick finds too few signals passing, lower to $25K. If too noisy, raise to $100K.

---

## ITEM 10: Systemd Service

### New File: `/etc/systemd/system/pivot-uw.service`

```ini
[Unit]
Description=Pivot UW Discord Listener
After=network.target
Wants=pivot-collector.service

[Service]
Type=simple
User=pivot
WorkingDirectory=/opt/pivot
ExecStart=/opt/pivot/venv/bin/python -m uw
Restart=always
RestartSec=15
Environment=PYTHONPATH=/opt/pivot
EnvironmentFile=/opt/pivot/.env

[Install]
WantedBy=multi-user.target
```

### Deployment Commands

```bash
# Install discord.py in the Pivot venv
/opt/pivot/venv/bin/pip install discord.py

# Copy service file
sudo cp pivot-uw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pivot-uw
sudo systemctl start pivot-uw

# Verify
sudo systemctl status pivot-uw
tail -f /opt/pivot/logs/uw.log
```

---

## IMPORTANT NOTES FOR CODEX

### Embed Format Fragility

The UW bot embed format is NOT documented by UW and can change without notice. The parser (Item 3) is written defensively — every field extraction is optional and returns None on failure. If parsing starts failing:

1. Enable DEBUG logging on `uw.parser`
2. The `_debug_embed()` function logs raw embed structure
3. Update the extraction patterns in `parser.py` to match the new format
4. The rest of the pipeline handles None values gracefully

### Rate Limits

- The 5-minute push cycle (Item 2, `push_aggregates`) ensures Pivot doesn't hammer the Railway API. Even during heavy flow, it batches everything into a single POST per cycle.
- The UW premium bot may post 50-100+ flow alerts per hour during high-volume sessions. The filter (Item 4) reduces this to 10-30 relevant alerts. The aggregator (Item 5) compresses those into per-ticker summaries.
- Railway Redis writes are cheap — a few dozen SET operations every 5 minutes is negligible.

### Memory on VPS

The VPS has 2GB RAM. The cron_runner uses ~90MB. Discord.py with MESSAGE_CONTENT intent uses ~30-50MB at steady state. The flow aggregator's rolling 2-hour window of parsed dicts is small (a few MB even on heavy days). Total expected usage: ~150MB for both services, leaving plenty of headroom.

### Testing Without UW Premium

Before purchasing the UW premium add-on, the listener can be tested with the free bot's auto-post topics (Economic News Updates, Highest Volume Options Contracts). These use the same embed format. The parser should work on these embeds too, though the data content will be different.

---

## COMPLETE FILE LIST

### New Files — Pivot VPS
- `/opt/pivot/uw/__init__.py` — package init
- `/opt/pivot/uw/__main__.py` — entry point
- `/opt/pivot/uw/listener.py` — Discord listener service
- `/opt/pivot/uw/parser.py` — embed parsing
- `/opt/pivot/uw/filter.py` — DTE/premium/blacklist/novelty filtering
- `/opt/pivot/uw/aggregator.py` — flow aggregation and discovery list
- `/etc/systemd/system/pivot-uw.service` — systemd unit

### New Files — Trading-Hub
- `backend/api/uw.py` — API endpoints for receiving UW data

### Modified Files — Trading-Hub
- `backend/main.py` — register UW router
- `backend/scanners/cta_scanner.py` — inject discovery tickers into scan universe (Item 8)

### Modified Files — Pivot VPS
- `/opt/pivot/.env` — add UW configuration vars
- `/opt/pivot/requirements.txt` — add `discord.py`

### Do NOT Modify
- `/opt/pivot/scheduler/cron_runner.py` — UW listener is a separate service
- `/opt/pivot/collectors/base_collector.py` — reuse existing `post_json()` as-is
- `/opt/pivot/notifications/discord_notifications.py` — UW listener reads, doesn't write to webhooks
