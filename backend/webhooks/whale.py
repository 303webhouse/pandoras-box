"""
Whale Webhook Endpoint
Receives large-volume / dark-pool whale signals and forwards to Discord.

Payload schema (from TradingView or manual POST):
{
  "signal":        "WHALE",
  "ticker":        "SPY",
  "tf":            "5",
  "lean":          "BEARISH",
  "poc":           598.25,
  "price":         598.50,
  "vol":           5000000,
  "vol_delta_pct": 3.21,
  "poc_delta_pct": 0.08,
  "time":          "2026-02-17T14:30"
}

Response: {"status": "received"}
Discord:  Posts a 🐋 embed to DISCORD_WEBHOOK_SIGNALS.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import logging
import os
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")


class WhaleSignal(BaseModel):
    signal: str = "WHALE"
    ticker: str
    tf: Optional[str] = None
    lean: Optional[str] = None
    poc: Optional[float] = None
    price: Optional[float] = None
    vol: Optional[int] = None
    vol_delta_pct: Optional[float] = None
    poc_delta_pct: Optional[float] = None
    time: Optional[str] = None

    model_config = {"extra": "allow"}


def _lean_emoji(lean: Optional[str]) -> str:
    if not lean:
        return ""
    upper = lean.upper()
    if "BEAR" in upper:
        return "🔴"
    if "BULL" in upper:
        return "🟢"
    return "⚪"


def _build_discord_message(data: WhaleSignal) -> dict:
    lean_str = data.lean.upper() if data.lean else "N/A"
    lean_icon = _lean_emoji(data.lean)
    tf_str = f"{data.tf}m" if data.tf else "N/A"
    vol_str = f"{data.vol:,}" if data.vol is not None else "N/A"
    vol_delta_str = f"{data.vol_delta_pct:+.2f}%" if data.vol_delta_pct is not None else "N/A"
    poc_str = f"{data.poc:.2f}" if data.poc is not None else "N/A"
    poc_delta_str = f"{data.poc_delta_pct:+.2f}%" if data.poc_delta_pct is not None else "N/A"
    price_str = f"{data.price:.2f}" if data.price is not None else "N/A"
    time_str = data.time or datetime.now().strftime("%Y-%m-%dT%H:%M")

    color = 0xFF4444 if "BEAR" in lean_str else 0x44FF44 if "BULL" in lean_str else 0xAAAAAA

    return {
        "embeds": [
            {
                "title": f"🐋 WHALE ALERT — {data.ticker}",
                "color": color,
                "fields": [
                    {"name": "Lean", "value": f"{lean_icon} {lean_str}", "inline": True},
                    {"name": "Timeframe", "value": tf_str, "inline": True},
                    {"name": "Price", "value": price_str, "inline": True},
                    {"name": "POC", "value": poc_str, "inline": True},
                    {"name": "POC Δ", "value": poc_delta_str, "inline": True},
                    {"name": "Volume", "value": vol_str, "inline": True},
                    {"name": "Vol Δ%", "value": vol_delta_str, "inline": True},
                    {"name": "Time", "value": time_str, "inline": True},
                ],
                "footer": {"text": "Pandora's Box • Whale Detector"},
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ]
    }


async def _post_to_discord(payload: dict) -> None:
    if not DISCORD_WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_SIGNALS not set — skipping Discord notification")
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(DISCORD_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            logger.info("🐋 Whale alert posted to Discord")
    except Exception as exc:
        logger.error(f"Discord webhook failed: {exc}")


@router.post("/whale")
async def whale_webhook(data: WhaleSignal):
    """Receive a whale signal and forward to Discord."""
    logger.info(
        f"🐋 Whale signal received: {data.ticker} {data.lean} "
        f"vol={data.vol} poc={data.poc} price={data.price}"
    )

    discord_payload = _build_discord_message(data)
    await _post_to_discord(discord_payload)

    return {"status": "received"}
