"""
Message intent classifier for Pivot chat.

Classifies Nick's messages into actionable intents using keyword/pattern
matching first (fast, free) with a fallback to "question" for the LLM to handle.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent definitions with pattern matching
# ---------------------------------------------------------------------------

INTENT_PATTERNS: Dict[str, Dict[str, Any]] = {
    "trade_idea": {
        "description": "Nick is presenting a trade idea for evaluation",
        "patterns": [
            r"thinking about",
            r"what do you think about",
            r"considering",
            r"looking at",
            r"how about",
            r"evaluate",
            r"should i",
            r"would you",
            r"bear(ish)?\s+(put|call|spread|condor|butterfly)",
            r"bull(ish)?\s+(put|call|spread|condor|butterfly)",
            r"iron\s+condor",
            r"butterfly",
            r"straddle",
            r"strangle",
            r"debit\s+spread",
            r"credit\s+spread",
            r"broken.?wing",
        ],
    },
    "trade_open": {
        "description": "Nick is logging a trade he just opened",
        "patterns": [
            r"just (opened|bought|sold|entered)",
            r"opened?\s+(a\s+)?",
            r"bought\s+\d+",
            r"sold\s+\d+",
            r"entered\s+(a\s+)?",
            r"new position",
            r"got (in|into)",
            r"filled (on|at)",
        ],
    },
    "trade_close": {
        "description": "Nick is logging a trade exit",
        "patterns": [
            r"just (closed|sold|exited|covered)",
            r"closed?\s+(the|my)",
            r"\bclosed?\b.{0,30}\bfor\b\s+[+\-$]",
            r"took profit",
            r"stopped out",
            r"expired",
            r"cut (the\s+)?loss",
        ],
    },
    "status": {
        "description": "Nick wants current system status",
        "patterns": [
            r"(what.?s|how.?s|how\s+is|what\s+is)\s+(the\s+)?(bias|defcon|breakout|status|market)",
            r"bias\s+(check|status|level)",
            r"\bbias\b",
            r"defcon\s+(check|status|level)",
            r"\bdefcon\b",
            r"breakout\s+(check|status|balance)",
            r"where\s+(am i|are we|do we stand)",
            r"current\s+(bias|defcon|status)",
            r"^status$",
        ],
    },
    "quote": {
        "description": "Nick wants a price quote or market data",
        "patterns": [
            r"(what.?s|where.?s|what\s+is|where\s+is)\s+\w{1,5}\s+(at|trading|price)",
            r"price\s+(of|on|for)\s+",
            r"quote\s+(on|for)\s+",
            r"btc\s+price",
            r"bitcoin\s+price",
            r"^[A-Z]{1,5}\s*\??$",
            r"check\s+(the\s+)?(price|chain|iv|vix)",
            r"options?\s+chain",
            r"iv\s+(rank|percentile)",
            r"vix\s+(status|level|check)",
        ],
    },
    "review": {
        "description": "Nick wants to review performance",
        "patterns": [
            r"(how.?d|how did)\s+(this|the|my|last)\s+week",
            r"weekly\s+review",
            r"(show|list)\s+(my\s+)?(trades|positions|open)",
            r"performance",
            r"win\s+rate",
            r"p&?l",
            r"(what.?s|how.?s)\s+my\s+(record|streak|stats)",
        ],
    },
}


def classify(message_text: str) -> Tuple[str, float]:
    """
    Classify a message into an intent.

    Returns:
        (intent_name, confidence)
        confidence: 1.0 for pattern match, 0.5 for fallback

    Defaults to ("question", 0.5) when no pattern matches.
    """
    text = message_text.lower().strip()

    for intent, config in INTENT_PATTERNS.items():
        for pattern in config["patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                return (intent, 1.0)

    return ("question", 0.5)


def extract_ticker(message_text: str) -> Optional[str]:
    """
    Extract a stock/ETF ticker from a message.

    Looks for $TICKER patterns, uppercase 1-5 letter words, and
    common crypto names (btc/bitcoin, eth/ethereum).

    Returns the ticker in uppercase or None if not found.
    """
    text = message_text

    # $TICKER pattern (most explicit)
    dollar_match = re.search(r'\$([A-Za-z]{1,5})\b', text)
    if dollar_match:
        return dollar_match.group(1).upper()

    # BTC/ETH special cases (check before general uppercase scan)
    if re.search(r'\b(btc|bitcoin)\b', text, re.IGNORECASE):
        return "BTC"
    if re.search(r'\b(eth|ethereum)\b', text, re.IGNORECASE):
        return "ETH"

    # Uppercase ticker pattern (avoid matching common English words)
    COMMON_WORDS = {
        "I", "A", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO",
        "IF", "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR",
        "SO", "TO", "UP", "US", "WE", "THE", "AND", "BUT", "FOR",
        "NOT", "YOU", "ALL", "CAN", "HER", "WAS", "ONE", "OUR",
        "OUT", "HAS", "HIS", "HOW", "ITS", "MAY", "NEW", "NOW",
        "OLD", "SEE", "WAY", "WHO", "DID", "GET", "HIM", "LET",
        "SAY", "SHE", "TOO", "USE", "PUT", "CALL", "JUST", "LONG",
        "SHORT", "BUY", "SELL", "OPEN", "CLOSE", "STOP", "WITH",
        "THAT", "THIS", "FROM", "WHAT", "WHEN", "RISK", "LOSS",
        "HALF", "FULL", "MARCH", "APRIL", "JUNE", "JULY",
        "DTE", "ATM", "OTM", "ITM", "MAX",
    }
    upper_matches = re.findall(r'\b([A-Z]{1,5})\b', text)
    for match in upper_matches:
        if match not in COMMON_WORDS:
            return match

    return None


def extract_trade_details(message_text: str) -> Dict[str, Any]:
    """
    Extract structured trade details from a message.

    Attempts to parse: ticker, direction, strategy, strikes, expiry,
    size, dollar amounts, P&L, and account. Returns a dict of extracted
    fields (may be partial — LLM fills the gaps).
    """
    details: Dict[str, Any] = {}
    text = message_text.lower()

    # Ticker
    ticker = extract_ticker(message_text)
    if ticker:
        details["ticker"] = ticker

    # Direction
    if any(w in text for w in ["bearish", "bear", "short", "put"]):
        details["direction"] = "short"
    elif any(w in text for w in ["bullish", "bull", "long", "call"]):
        details["direction"] = "long"

    # Strategy
    strategy_patterns = {
        "bear_put_spread": r"bear\s*(?:ish)?\s*put\s*spread",
        "bull_call_spread": r"bull\s*(?:ish)?\s*call\s*spread",
        "bull_put_spread": r"bull\s*(?:ish)?\s*put\s*spread",
        "bear_call_spread": r"bear\s*(?:ish)?\s*call\s*spread",
        "iron_condor": r"iron\s*condor",
        "broken_wing_butterfly": r"broken.?wing|bwb",
        "butterfly": r"butterfly",
        "straddle": r"straddle",
        "strangle": r"strangle",
        "naked_put": r"naked\s*put",
        "naked_call": r"naked\s*call",
        "long_call": r"(?:long|bought?)\s*call",
        "long_put": r"(?:long|bought?)\s*put",
        "covered_call": r"covered\s*call",
    }
    for strategy, pattern in strategy_patterns.items():
        if re.search(pattern, text):
            details["strategy"] = strategy
            break

    # Strikes — numbers near strike context, then plain 3-4 digit numbers
    strike_matches = re.findall(
        r'(\d{2,4}(?:\.\d{1,2})?)\s*(?:p|c|put|call|strike|/)', text
    )
    if not strike_matches:
        strike_matches = re.findall(r'\b(\d{3,4}(?:\.\d{1,2})?)\b', text)
    if strike_matches:
        details["strikes"] = [float(s) for s in strike_matches]

    # Expiry — explicit date
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if date_match:
        details["expiry"] = date_match.group(1)

    # Expiry — month name
    month_pattern = (
        r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|'
        r'jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|'
        r'oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
    )
    month_match = re.search(month_pattern, text)
    if month_match:
        details["expiry_month"] = month_match.group(1)

    # Size — "2 contracts" / "x2" / "2x"
    size_match = (
        re.search(r'(\d+)\s*(?:contracts?|x\b|lots?)', text)
        or re.search(r'x\s*(\d+)', text)
    )
    if size_match:
        details["size"] = f"{size_match.group(1)} contracts"

    # Dollar amounts
    dollar_matches = re.findall(r'\$\s*(\d+(?:\.\d{2})?)', text)
    if dollar_matches:
        details["dollar_amounts"] = [float(d) for d in dollar_matches]

    # P&L for trade_close
    pnl_match = re.search(r'[+\-]\s*\$?\s*(\d+(?:\.\d{2})?)', text)
    if pnl_match:
        sign = "-" if "-" in text[: pnl_match.start() + 5] else "+"
        details["pnl"] = float(f"{sign}{pnl_match.group(1)}")

    # Account
    if "401k" in text or "401(k)" in text or "brokerage" in text:
        details["account"] = "401k"
    elif "robinhood" in text or " rh " in text:
        details["account"] = "robinhood"
    elif "breakout" in text or "prop" in text:
        details["account"] = "breakout"

    return details
