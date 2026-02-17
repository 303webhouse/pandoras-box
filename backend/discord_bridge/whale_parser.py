"""
Whale signal parsers for #whale-alerts channel.

Handles two message types posted to #whale-alerts:
  1. Whale Hunter signals — plain-text messages from our TradingView webhook.
     Format:
         🐋 **WHALE SIGNAL** — SPY (5m)
         🔴 Lean: **BEARISH**
         POC Level: **$598.25** | Price: $598.50
         Vol Match: 3.2% | POC Match: 0.080%

  2. Unusual Whales Premium bot embeds — structured embed fields with
     ticker, strike, expiry, type, premium, order type, volume, OI, etc.

Returns parsed dicts ready for Pivot LLM evaluation via build_flow_analysis_prompt.
Unknown embed field names are logged so we can refine the parser over time.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import discord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Whale Hunter (TradingView webhook) parser
# ---------------------------------------------------------------------------

def parse_whale_hunter_signal(message: discord.Message) -> Optional[dict]:
    """
    Parse a Whale Hunter signal posted by our TradingView webhook.

    Returns a dict with the extracted fields, or None if the message is
    not a Whale Hunter signal.
    """
    content = message.content
    if "WHALE SIGNAL" not in content and "🐋" not in content:
        return None

    result: dict = {
        "source": "whale_hunter",
        "ticker": None,
        "timeframe": None,
        "lean": None,
        "poc_level": None,
        "price": None,
        "vol_match": None,
        "poc_match": None,
        "raw": content[:500],
    }

    # Ticker + timeframe from header line: "WHALE SIGNAL — SPY (5m)"
    header_m = re.search(
        r'WHALE SIGNAL[^\w]*([A-Z]{1,5})\s*\(([^)]+)\)', content
    )
    if header_m:
        result["ticker"] = header_m.group(1)
        result["timeframe"] = header_m.group(2)

    # Lean direction
    lean_m = re.search(
        r'Lean:\s*\*{0,2}(BULLISH|BEARISH|NEUTRAL)\*{0,2}', content, re.IGNORECASE
    )
    if lean_m:
        result["lean"] = lean_m.group(1).upper()

    # POC level
    poc_m = re.search(r'POC Level:\s*\*{0,2}\$?([\d.]+)\*{0,2}', content)
    if poc_m:
        result["poc_level"] = float(poc_m.group(1))

    # Current price
    price_m = re.search(r'Price:\s*\$?([\d.]+)', content)
    if price_m:
        result["price"] = float(price_m.group(1))

    # Volume match %
    vol_m = re.search(r'Vol Match:\s*([\d.]+)%', content)
    if vol_m:
        result["vol_match"] = float(vol_m.group(1))

    # POC proximity %
    poc_delta_m = re.search(r'POC Match:\s*([\d.]+)%', content)
    if poc_delta_m:
        result["poc_match"] = float(poc_delta_m.group(1))

    if not result["ticker"]:
        logger.warning(
            "Whale Hunter signal detected but could not extract ticker: %s",
            content[:100],
        )
        return None

    logger.info(
        "🐋 Whale Hunter signal: %s %s lean=%s poc=$%s",
        result["ticker"], result["timeframe"], result["lean"], result["poc_level"]
    )
    return result


# ---------------------------------------------------------------------------
# Unusual Whales Premium bot embed parser
# ---------------------------------------------------------------------------

def parse_uw_premium_embed(embed: discord.Embed) -> Optional[dict]:
    """
    Parse an Unusual Whales Premium bot embed from #whale-alerts.

    UW embeds use structured fields. We attempt to extract:
    ticker, strike, expiry, option_type, premium, order_type,
    volume, open_interest, spot_price.

    Unknown field names are logged under DEBUG so we can refine later.
    Returns a dict or None if we can't extract a ticker.
    """
    if not embed.fields:
        return None

    # Normalise field names: lowercase and stripped
    raw_fields = {f.name.lower().strip(): f.value.strip() for f in embed.fields}

    title = embed.title or ""
    description = embed.description or ""

    result: dict = {
        "source": "unusual_whales",
        "ticker": None,
        "strike": None,
        "expiry": None,
        "option_type": None,
        "premium": None,
        "order_type": None,
        "volume": None,
        "open_interest": None,
        "spot_price": None,
        "embed_title": title[:200],
        "raw_fields": dict(raw_fields),
    }

    # --- ticker ---
    for key in ("ticker", "symbol", "stock", "underlying"):
        if key in raw_fields:
            m = re.search(r'\b([A-Z]{1,5})\b', raw_fields[key])
            if m:
                result["ticker"] = m.group(1)
                break

    # Fallback: extract from embed title
    if not result["ticker"] and title:
        m = re.match(r'\b([A-Z]{1,5})\b', title)
        if m:
            result["ticker"] = m.group(1)

    # --- strike ---
    for key in ("strike", "strike price"):
        if key in raw_fields:
            m = re.search(r'\$?([\d.]+)', raw_fields[key])
            if m:
                result["strike"] = float(m.group(1))
            break

    # --- expiry ---
    for key in ("expiry", "expiration", "exp", "expires"):
        if key in raw_fields:
            result["expiry"] = raw_fields[key]
            break

    # --- option type (call/put) ---
    for key in ("type", "option type", "call/put", "side", "contract type"):
        if key in raw_fields:
            val = raw_fields[key].upper()
            if "CALL" in val:
                result["option_type"] = "CALL"
            elif "PUT" in val:
                result["option_type"] = "PUT"
            break

    # Fallback from title/description
    if not result["option_type"]:
        combined = f"{title} {description}".upper()
        if "CALL" in combined:
            result["option_type"] = "CALL"
        elif "PUT" in combined:
            result["option_type"] = "PUT"

    # --- premium ---
    for key in ("premium", "total premium", "notional", "value"):
        if key in raw_fields:
            m = re.search(r'\$?([\d,.]+)\s*([KkMm])?', raw_fields[key])
            if m:
                amount = float(m.group(1).replace(',', ''))
                suffix = m.group(2)
                if suffix and suffix.lower() == 'k':
                    amount *= 1_000
                elif suffix and suffix.lower() == 'm':
                    amount *= 1_000_000
                result["premium"] = int(amount)
            break

    # --- order type (sweep/block/dark pool) ---
    for key in ("order type", "type", "flow type", "trade type"):
        if key in raw_fields:
            val = raw_fields[key].upper()
            if "SWEEP" in val:
                result["order_type"] = "SWEEP"
            elif "BLOCK" in val:
                result["order_type"] = "BLOCK"
            elif "DARK" in val or " DP" in val:
                result["order_type"] = "DARK_POOL"
            break

    # --- volume ---
    for key in ("volume", "vol", "contracts"):
        if key in raw_fields:
            m = re.search(r'([\d,]+)', raw_fields[key])
            if m:
                result["volume"] = int(m.group(1).replace(',', ''))
            break

    # --- open interest ---
    for key in ("open interest", "oi", "o/i"):
        if key in raw_fields:
            m = re.search(r'([\d,]+)', raw_fields[key])
            if m:
                result["open_interest"] = int(m.group(1).replace(',', ''))
            break

    # --- spot price ---
    for key in ("spot", "spot price", "price", "stock price", "underlying price"):
        if key in raw_fields:
            m = re.search(r'\$?([\d.]+)', raw_fields[key])
            if m:
                result["spot_price"] = float(m.group(1))
            break

    if not result["ticker"]:
        logger.debug(
            "UW embed: could not extract ticker. Fields: %s", list(raw_fields.keys())
        )
        return None

    logger.info(
        "🦅 UW embed: %s %s %s premium=%s order=%s",
        result["ticker"], result["option_type"], result["expiry"],
        result["premium"], result["order_type"],
    )
    return result


# ---------------------------------------------------------------------------
# LLM context formatters
# ---------------------------------------------------------------------------

def format_whale_hunter_for_llm(parsed: dict) -> str:
    """Format a parsed Whale Hunter signal as LLM flow data context."""
    ticker = parsed.get("ticker", "?")
    tf = parsed.get("timeframe", "?")
    lean = parsed.get("lean", "?")
    poc = parsed.get("poc_level")
    price = parsed.get("price")
    vol = parsed.get("vol_match")
    poc_delta = parsed.get("poc_match")

    lines = [
        "Source: Whale Hunter (TradingView volume + POC indicator)",
        f"Ticker: {ticker} | Timeframe: {tf}",
        f"Signal lean: {lean}",
    ]
    if poc:
        lines.append(f"POC level: ${poc:.2f}")
    if price:
        lines.append(f"Current price: ${price:.2f}")
    if vol is not None:
        lines.append(f"Volume match: {vol:.2f}% above threshold")
    if poc_delta is not None:
        lines.append(f"POC proximity: {poc_delta:.3f}% from price")
    return "\n".join(lines)


def format_uw_embed_for_llm(parsed: dict) -> str:
    """Format a parsed UW embed as LLM flow data context."""
    lines = [
        "Source: Unusual Whales Premium Bot",
        f"Ticker: {parsed.get('ticker', '?')}",
    ]
    if parsed.get("option_type"):
        lines.append(f"Option type: {parsed['option_type']}")
    if parsed.get("strike"):
        lines.append(f"Strike: ${parsed['strike']:.2f}")
    if parsed.get("expiry"):
        lines.append(f"Expiration: {parsed['expiry']}")

    premium = parsed.get("premium")
    if premium:
        if premium >= 1_000_000:
            lines.append(f"Premium: ${premium / 1_000_000:.2f}M")
        elif premium >= 1_000:
            lines.append(f"Premium: ${premium / 1_000:.0f}K")
        else:
            lines.append(f"Premium: ${premium:,}")

    if parsed.get("order_type"):
        lines.append(f"Order type: {parsed['order_type']}")
    if parsed.get("volume"):
        lines.append(f"Volume: {parsed['volume']:,} contracts")
    if parsed.get("open_interest"):
        lines.append(f"Open interest: {parsed['open_interest']:,}")
    if parsed.get("spot_price"):
        lines.append(f"Spot price: ${parsed['spot_price']:.2f}")
    if parsed.get("embed_title"):
        lines.append(f"Embed title: {parsed['embed_title']}")

    # Log unrecognised fields so Nick can screenshot and we can refine
    unknown = parsed.get("raw_fields", {})
    if unknown:
        logger.debug("UW embed raw fields for refinement: %s", unknown)

    return "\n".join(lines)
