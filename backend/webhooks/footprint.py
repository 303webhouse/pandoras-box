"""
Footprint Webhook Endpoint
Receives footprint imbalance signals (stacked buy/sell, absorption) from
TradingView's "Footprint Alert for Pandora" PineScript indicator.

Forward-test period: Mar 14 – Mar 28, 2026.
Runs alongside Whale Hunter for correlation analysis.

Payload schema:
{
  "signal":          "FOOTPRINT",
  "ticker":          "SPY",
  "tf":              "5",
  "sub_type":        "stacked_buy",    // stacked_buy, stacked_sell
  "direction":       "LONG",
  "price":           560.50,
  "stacked_layers":  4,
  "buy_imb_count":   6,
  "sell_imb_count":  1,
  "secret":          "..."
}

Response: {"status": "received"}
Discord:  Posts a footprint embed to DISCORD_WEBHOOK_SIGNALS.
Redis:    Caches at footprint:recent:{TICKER} for 30 min.
Pipeline: Writes to signals table with signal_category=FOOTPRINT, base_score=40.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import asyncio
import hashlib
import logging
import os
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")
FOOTPRINT_CONTEXT_TTL = 1800  # 30 minutes
DEDUP_WINDOW = 300  # 5 minutes


class FootprintSignal(BaseModel):
    signal: str = "FOOTPRINT"
    ticker: str
    tf: Optional[str] = None
    sub_type: Optional[str] = None
    direction: Optional[str] = None
    price: Optional[float] = None
    stacked_layers: Optional[int] = None
    buy_imb_count: Optional[int] = None
    sell_imb_count: Optional[int] = None
    # v2 quality-gate fields
    density_pct: Optional[float] = None      # % of rows with imbalances
    zone_coverage_pct: Optional[float] = None # stacked zone as % of bar range
    vol_ratio: Optional[float] = None         # bar volume vs 20-SMA
    secret: Optional[str] = None

    model_config = {"extra": "allow"}


def _direction_emoji(direction: Optional[str]) -> str:
    if not direction:
        return ""
    upper = direction.upper()
    if upper == "LONG":
        return "\U0001f7e2"
    if upper == "SHORT":
        return "\U0001f534"
    return "\u26aa"


def _sub_type_display(sub_type: Optional[str]) -> str:
    return {
        "stacked_buy": "Stacked Buy Imbalance",
        "stacked_sell": "Stacked Sell Imbalance",
    }.get(sub_type or "", sub_type or "Unknown")


def _build_discord_message(data: FootprintSignal) -> dict:
    direction = (data.direction or "N/A").upper()
    dir_emoji = _direction_emoji(data.direction)
    tf_str = f"{data.tf}m" if data.tf else "N/A"
    price_str = f"{data.price:.2f}" if data.price is not None else "N/A"
    sub_display = _sub_type_display(data.sub_type)
    stacked_str = str(data.stacked_layers) if data.stacked_layers is not None else "N/A"
    buy_imb = str(data.buy_imb_count) if data.buy_imb_count is not None else "0"
    sell_imb = str(data.sell_imb_count) if data.sell_imb_count is not None else "0"

    color = 0x44FF44 if direction == "LONG" else 0xFF4444 if direction == "SHORT" else 0xAAAAAA

    fields = [
        {"name": "Signal Type", "value": sub_display, "inline": True},
        {"name": "Direction", "value": f"{dir_emoji} {direction}", "inline": True},
        {"name": "Timeframe", "value": tf_str, "inline": True},
        {"name": "Price", "value": price_str, "inline": True},
        {"name": "Stacked Layers", "value": stacked_str, "inline": True},
        {"name": "Imbalances", "value": f"Buy: {buy_imb} | Sell: {sell_imb}", "inline": True},
    ]

    return {
        "embeds": [
            {
                "title": f"\U0001f52c FOOTPRINT ALERT \u2014 {data.ticker}",
                "color": color,
                "fields": fields,
                "footer": {"text": "Pandora's Box \u2022 Footprint Forward Test"},
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ]
    }


async def _post_to_discord(payload: dict) -> None:
    if not DISCORD_WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_SIGNALS not set \u2014 skipping Discord notification")
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(DISCORD_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            logger.info("\U0001f52c Footprint alert posted to Discord")
    except Exception as exc:
        logger.error(f"Discord webhook failed: {exc}")


async def _process_footprint_background(data: FootprintSignal) -> None:
    """Background processing: Discord post + Redis cache + pipeline.
    Runs via asyncio.ensure_future so the webhook returns immediately
    and TradingView doesn't timeout (~10s limit)."""

    # Discord notification
    discord_payload = _build_discord_message(data)
    await _post_to_discord(discord_payload)

    # Cache for correlation analysis (30 min TTL)
    try:
        from database.redis_client import get_redis_client
        import json as _json

        client = await get_redis_client()
        if client:
            cache_key = f"footprint:recent:{data.ticker.upper()}"
            cache_data = {
                "ticker": data.ticker.upper(),
                "sub_type": data.sub_type,
                "direction": data.direction,
                "price": data.price,
                "stacked_layers": data.stacked_layers,
                "buy_imb_count": data.buy_imb_count,
                "sell_imb_count": data.sell_imb_count,
                "density_pct": data.density_pct,
                "zone_coverage_pct": data.zone_coverage_pct,
                "vol_ratio": data.vol_ratio,
                "tf": data.tf,
                "cached_at": datetime.utcnow().isoformat() + "Z",
            }
            await client.set(cache_key, _json.dumps(cache_data), ex=FOOTPRINT_CONTEXT_TTL)
            logger.info(f"\U0001f52c Footprint context cached: {cache_key} (TTL {FOOTPRINT_CONTEXT_TTL}s)")
    except Exception as e:
        logger.warning(f"Failed to cache footprint context: {e}")

    # Pipeline integration: write to signals table
    try:
        from signals.pipeline import process_signal_unified

        direction = (data.direction or "").upper()
        if direction not in ("LONG", "SHORT"):
            logger.info("Footprint signal no direction \u2014 skipped pipeline (Discord-only)")
        else:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            short_hash = hashlib.md5(
                f"{data.ticker}{data.sub_type}{data.price}".encode()
            ).hexdigest()[:6]
            signal_id = f"FP_{data.ticker}_{ts}_{short_hash}"

            signal_data = {
                "signal_id": signal_id,
                "ticker": data.ticker.upper(),
                "strategy": "Footprint_Imbalance",
                "signal_type": f"FOOTPRINT_{direction}",
                "direction": direction,
                "entry_price": data.price,
                "stop_loss": None,
                "target_1": None,
                "target_2": None,
                "timeframe": data.tf or "5",
                "risk_reward": None,
                "asset_class": "EQUITY",
                "source": "footprint",
                "signal_category": "FOOTPRINT",
                "metadata": {
                    "sub_type": data.sub_type,
                    "stacked_layers": data.stacked_layers,
                    "buy_imb_count": data.buy_imb_count,
                    "sell_imb_count": data.sell_imb_count,
                    "density_pct": data.density_pct,
                    "zone_coverage_pct": data.zone_coverage_pct,
                    "vol_ratio": data.vol_ratio,
                },
                "timestamp": datetime.utcnow().isoformat(),
            }

            await process_signal_unified(signal_data, source="footprint")
            logger.info(f"Footprint signal entered pipeline: {signal_id}")

    except Exception as e:
        logger.warning(f"Footprint pipeline integration failed (Discord post succeeded): {e}")


@router.post("/footprint")
async def footprint_webhook(data: FootprintSignal):
    """Receive a footprint signal, forward to Discord, cache in Redis, enter pipeline."""
    # Validate webhook secret
    WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET") or ""
    if WEBHOOK_SECRET:
        if (data.secret or "") != WEBHOOK_SECRET:
            logger.warning("Rejected footprint webhook \u2014 invalid secret")
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Dedup: reject duplicate footprint signals within 300s window
    dedup_raw = f"{data.ticker}:{data.sub_type}:{data.direction}:{data.price}"
    dedup_hash = hashlib.md5(dedup_raw.encode()).hexdigest()[:16]
    dedup_key = f"webhook:dedup:footprint:{dedup_hash}"
    try:
        from database.redis_client import get_redis_client
        _rc = await get_redis_client()
        if _rc and await _rc.get(dedup_key):
            logger.info("Footprint dedup: skipping duplicate %s %s", data.ticker, data.sub_type)
            return {"status": "duplicate", "detail": "duplicate footprint signal within 300s window"}
        if _rc:
            await _rc.set(dedup_key, "1", ex=DEDUP_WINDOW)
    except Exception:
        pass

    logger.info(
        f"\U0001f52c Footprint signal received: {data.ticker} {data.direction} "
        f"sub_type={data.sub_type} stacked={data.stacked_layers} price={data.price}"
    )

    # Fire-and-forget: return 200 immediately, process in background
    # (TradingView has ~10s webhook timeout — Discord + Redis + pipeline can exceed it)
    asyncio.ensure_future(_process_footprint_background(data))

    return {"status": "received"}


@router.get("/footprint/recent/{ticker}")
async def get_recent_footprint(ticker: str):
    """Return cached footprint signal for a ticker (if any, within 30 min)."""
    try:
        from database.redis_client import get_redis_client
        import json as _json

        client = await get_redis_client()
        if not client:
            return {"available": False}

        data = await client.get(f"footprint:recent:{ticker.upper()}")
        if data:
            return {"available": True, "footprint": _json.loads(data)}
    except Exception as e:
        logger.warning(f"Error fetching footprint context for {ticker}: {e}")

    return {"available": False}
