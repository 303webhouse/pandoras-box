"""
Parse Unusual Whales Discord bot embeds into structured dicts.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, date, timezone
from typing import Any, Dict, Optional

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

        ticker = _extract_ticker(title, description)
        if not ticker:
            logger.debug("Could not extract ticker from embed: %s", title)
            return None

        result: Dict[str, Any] = {
            "ticker": ticker.upper(),
            "option_type": _extract_option_type(fields, title, description),
            "strike": _extract_float(fields, ["strike", "strike price"]),
            "expiry": _extract_date(fields, ["expiry", "expiration", "exp"]),
            "premium": _extract_premium(fields, ["premium", "total premium", "value"]),
            "side": _extract_side(fields, title, description),
            "sentiment": _extract_sentiment(fields, title, description),
            "volume": _extract_int(fields, ["volume", "vol"]),
            "open_interest": _extract_int(fields, ["open interest", "oi"]),
            "dte": None,
            "raw_title": title,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if result["expiry"]:
            try:
                exp_date = datetime.strptime(result["expiry"], "%Y-%m-%d").date()
                result["dte"] = (exp_date - date.today()).days
            except (ValueError, TypeError):
                result["dte"] = None

        if not result["premium"] and not result["volume"]:
            logger.debug("Insufficient data for %s: no premium or volume", ticker)
            return None

        return result

    except Exception as exc:
        logger.warning("Failed to parse flow embed: %s", exc)
        _debug_embed(embed)
        return None


def parse_ticker_embed(embed: discord.Embed) -> Optional[Dict[str, Any]]:
    """
    Parse a Ticker Update embed from the UW premium bot.
    """
    try:
        fields = {f.name.strip().lower(): f.value.strip() for f in embed.fields}
        title = embed.title or ""
        description = embed.description or ""

        ticker = _extract_ticker(title, description)
        if not ticker:
            return None

        return {
            "ticker": ticker.upper(),
            "price": _extract_float(fields, ["price", "last"]),
            "share_volume": _extract_int(fields, ["share volume", "volume"]),
            "call_volume": _extract_int(fields, ["call volume", "calls"]),
            "put_volume": _extract_int(fields, ["put volume", "puts"]),
            "put_call_ratio": _extract_float(fields, ["put/call ratio", "p/c ratio", "pcr"]),
            "total_premium": _extract_premium(fields, ["total premium", "premium"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.warning("Failed to parse ticker embed: %s", exc)
        return None


def _extract_ticker(title: str, description: str) -> Optional[str]:
    patterns = [
        r"\$([A-Z]{1,5})\b",
        r"\*\*([A-Z]{1,5})\*\*",
        r"^([A-Z]{1,5})\b",
        r"\b([A-Z]{1,5})\s+\d+",
    ]
    for pattern in patterns:
        for text in (title, description):
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1)
                if candidate not in {"THE", "FOR", "AND", "BUY", "SELL", "PUT", "CALL", "NEW", "OI", "VOL"}:
                    return candidate
    return None


def _extract_option_type(fields: dict, title: str, description: str) -> Optional[str]:
    combined = f"{title} {description} {' '.join(fields.values())}".upper()
    if "CALL" in combined or " C " in combined:
        return "CALL"
    if "PUT" in combined or " P " in combined:
        return "PUT"
    return None


def _extract_side(fields: dict, title: str, description: str) -> Optional[str]:
    for key in ("side", "type", "transaction"):
        if key in fields:
            val = fields[key].upper()
            if "BUY" in val or "ASK" in val:
                return "BUY"
            if "SELL" in val or "BID" in val:
                return "SELL"
    combined = f"{title} {description}".upper()
    if "BOUGHT" in combined or "BUY" in combined or "ASK SIDE" in combined:
        return "BUY"
    if "SOLD" in combined or "SELL" in combined or "BID SIDE" in combined:
        return "SELL"
    return None


def _extract_sentiment(fields: dict, title: str, description: str) -> Optional[str]:
    for key in ("sentiment", "bias", "direction"):
        if key in fields:
            val = fields[key].upper()
            if "BULL" in val:
                return "BULLISH"
            if "BEAR" in val:
                return "BEARISH"
    return None


def _extract_float(fields: dict, keys: list[str]) -> Optional[float]:
    for key in keys:
        if key in fields:
            try:
                cleaned = re.sub(r"[,$%]", "", fields[key])
                return float(cleaned)
            except (ValueError, TypeError):
                continue
    return None


def _extract_int(fields: dict, keys: list[str]) -> Optional[int]:
    for key in keys:
        if key in fields:
            try:
                cleaned = re.sub(r"[,$]", "", fields[key])
                return int(float(cleaned))
            except (ValueError, TypeError):
                continue
    return None


def _extract_premium(fields: dict, keys: list[str]) -> Optional[float]:
    for key in keys:
        if key in fields:
            try:
                val = fields[key].strip().upper().replace("$", "").replace(",", "")
                if val.endswith("M"):
                    return float(val[:-1]) * 1_000_000
                if val.endswith("K"):
                    return float(val[:-1]) * 1_000
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def _extract_date(fields: dict, keys: list[str]) -> Optional[str]:
    for key in keys:
        if key in fields:
            raw = fields[key].strip()
            # Normalize common formats to YYYY-MM-DD
            try:
                if "/" in raw:
                    parsed = datetime.strptime(raw, "%m/%d/%Y").date()
                else:
                    parsed = datetime.strptime(raw, "%Y-%m-%d").date()
                return parsed.isoformat()
            except ValueError:
                continue
    return None


def _debug_embed(embed: discord.Embed) -> None:
    try:
        logger.debug("Embed title: %s", embed.title)
        logger.debug("Embed description: %s", embed.description)
        for field in embed.fields:
            logger.debug("Field: %s = %s", field.name, field.value)
    except Exception:
        return
