"""
Parsers for whale-alerts channel messages.

Supports:
- Whale Hunter plain-text alerts
- Unusual Whales premium-style embeds
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


_TICKER_RE = re.compile(r"\b([A-Z]{1,6})\b")
_DOLLAR_VALUE_RE = re.compile(r"\$?\s*([0-9]+(?:\.[0-9]+)?)")
_PERCENT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _extract_line_value(text: str, label: str) -> Optional[str]:
    pattern = re.compile(rf"{re.escape(label)}\s*[:\-]\s*(.+)", re.IGNORECASE)
    match = pattern.search(text or "")
    return match.group(1).strip() if match else None


def _normalize_lean(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    upper = str(raw).upper()
    if "BEAR" in upper or "URSA" in upper or "SHORT" in upper:
        return "BEARISH"
    if "BULL" in upper or "TORO" in upper or "LONG" in upper:
        return "BULLISH"
    return None


def parse_whale_hunter_signal(message: Any) -> Optional[Dict[str, Any]]:
    """
    Parse Whale Hunter plain text messages from Discord.
    Returns normalized dict or None when message is not a whale signal.
    """
    content = getattr(message, "content", None)
    text = str(content or "").strip()
    if not text:
        return None

    upper = text.upper()
    if "WHALE" not in upper and "POC" not in upper:
        return None

    ticker = None
    ticker_match = re.search(r"\b([A-Z]{1,6})\s*\((\d+\s*[mhd])\)", text)
    timeframe = None
    if ticker_match:
        ticker = ticker_match.group(1).upper()
        timeframe = ticker_match.group(2).replace(" ", "").lower()

    if not ticker:
        for candidate in _TICKER_RE.findall(upper):
            if candidate not in {"WHALE", "SIGNAL", "LEAN", "POC", "PRICE", "VOL", "MATCH"}:
                ticker = candidate
                break

    lean_line = _extract_line_value(text, "Lean")
    lean = _normalize_lean(lean_line) or ("BEARISH" if "BEAR" in upper else "BULLISH" if "BULL" in upper else None)

    poc_level = None
    poc_match = re.search(r"POC(?:\s+LEVEL)?\s*[:\-]?\s*\**\$?\s*([0-9]+(?:\.[0-9]+)?)", upper, re.IGNORECASE)
    if poc_match:
        poc_level = _safe_float(poc_match.group(1))

    price = None
    price_match = re.search(r"PRICE\s*[:\-]?\s*\$?\s*([0-9]+(?:\.[0-9]+)?)", upper, re.IGNORECASE)
    if price_match:
        price = _safe_float(price_match.group(1))

    vol_match_pct = None
    vol_match = re.search(r"VOL(?:UME)?\s+MATCH\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%", upper, re.IGNORECASE)
    if vol_match:
        vol_match_pct = _safe_float(vol_match.group(1))

    poc_match_pct = None
    poc_match_line = re.search(r"POC\s+MATCH\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%", upper, re.IGNORECASE)
    if poc_match_line:
        poc_match_pct = _safe_float(poc_match_line.group(1))

    if not ticker:
        return None

    return {
        "source": "whale_hunter",
        "ticker": ticker,
        "timeframe": timeframe,
        "lean": lean or "UNKNOWN",
        "poc_level": poc_level,
        "price": price,
        "vol_match_pct": vol_match_pct,
        "poc_match_pct": poc_match_pct,
        "raw_text": text,
    }


def parse_uw_premium_embed(embed: Any) -> Optional[Dict[str, Any]]:
    """
    Parse Unusual Whales-style embed payloads.
    Returns normalized dict or None if required fields cannot be inferred.
    """
    title = str(getattr(embed, "title", "") or "")
    description = str(getattr(embed, "description", "") or "")
    fields = getattr(embed, "fields", []) or []
    full_text = "\n".join([title, description] + [f"{getattr(f, 'name', '')}: {getattr(f, 'value', '')}" for f in fields])
    upper = full_text.upper()

    ticker = None
    ticker_match = re.search(r"\b([A-Z]{1,6})\b", upper)
    if ticker_match:
        ticker = ticker_match.group(1)

    option_type = None
    if " PUT" in f" {upper}" or "PUTS" in upper:
        option_type = "put"
    elif " CALL" in f" {upper}" or "CALLS" in upper:
        option_type = "call"

    order_type = None
    for token in ("SWEEP", "BLOCK", "SPLIT", "UNUSUAL"):
        if token in upper:
            order_type = token.lower()
            break

    premium = None
    premium_match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)\s*([KMB])?", upper)
    if premium_match:
        base = _safe_float(premium_match.group(1))
        unit = premium_match.group(2)
        if base is not None:
            mult = 1.0
            if unit == "K":
                mult = 1_000.0
            elif unit == "M":
                mult = 1_000_000.0
            elif unit == "B":
                mult = 1_000_000_000.0
            premium = base * mult

    strike = None
    strike_match = re.search(r"\b([0-9]{2,5}(?:\.[0-9]+)?)\s*(?:C|P)\b", upper)
    if strike_match:
        strike = _safe_float(strike_match.group(1))
    if strike is None:
        strike_tag = re.search(r"STRIKE\s*[:\-]?\s*\$?\s*([0-9]+(?:\.[0-9]+)?)", upper)
        if strike_tag:
            strike = _safe_float(strike_tag.group(1))

    sentiment = "NEUTRAL"
    if option_type == "put":
        sentiment = "BEARISH"
    elif option_type == "call":
        sentiment = "BULLISH"

    if not ticker:
        return None

    return {
        "source": "uw_premium",
        "ticker": ticker,
        "option_type": option_type or "unknown",
        "order_type": order_type or "unknown",
        "premium": premium,
        "strike": strike,
        "sentiment": sentiment,
        "raw_text": full_text.strip(),
    }


def format_whale_hunter_for_llm(parsed: Dict[str, Any]) -> str:
    ticker = str(parsed.get("ticker") or "?").upper()
    lean = str(parsed.get("lean") or "UNKNOWN").upper()
    timeframe = parsed.get("timeframe") or "5m"
    poc = parsed.get("poc_level")
    price = parsed.get("price")
    vol_match_pct = parsed.get("vol_match_pct")
    poc_match_pct = parsed.get("poc_match_pct")

    lines = [
        f"WHALE HUNTER SIGNAL — {ticker} ({timeframe})",
        f"Lean: {lean}",
        f"POC Level: ${poc:.2f}" if isinstance(poc, (int, float)) else "POC Level: N/A",
        f"Price: ${price:.2f}" if isinstance(price, (int, float)) else "Price: N/A",
    ]
    if isinstance(vol_match_pct, (int, float)):
        lines.append(f"Vol Match: {float(vol_match_pct):.3f}%")
    if isinstance(poc_match_pct, (int, float)):
        lines.append(f"POC Match: {float(poc_match_pct):.3f}%")
    return "\n".join(lines)


def format_uw_embed_for_llm(parsed: Dict[str, Any]) -> str:
    ticker = str(parsed.get("ticker") or "?").upper()
    option_type = str(parsed.get("option_type") or "unknown").lower()
    order_type = str(parsed.get("order_type") or "unknown").lower()
    sentiment = str(parsed.get("sentiment") or "NEUTRAL").upper()
    strike = parsed.get("strike")
    premium = parsed.get("premium")

    premium_text = "N/A"
    if isinstance(premium, (int, float)):
        if premium >= 1_000_000:
            premium_text = f"${premium / 1_000_000:.2f}M"
        elif premium >= 1_000:
            premium_text = f"${premium / 1_000:.1f}K"
        else:
            premium_text = f"${premium:.2f}"

    return "\n".join(
        [
            f"UNUSUAL WHALES FLOW — {ticker}",
            f"Sentiment: {sentiment}",
            f"Contract: {option_type}",
            f"Flow Type: {order_type}",
            f"Strike: ${float(strike):.2f}" if isinstance(strike, (int, float)) else "Strike: N/A",
            f"Premium: {premium_text}",
        ]
    )

