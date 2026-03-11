"""
Whale Webhook Endpoint
Receives large-volume / dark-pool whale signals and forwards to Discord.
Also caches signals in Redis (30 min TTL) for committee confluence context.

Payload schema (from TradingView Whale Hunter v2):
{
  "signal":        "WHALE",
  "ticker":        "SPY",
  "tf":            "5",
  "lean":          "BEARISH",
  "poc":           598.25,
  "price":         598.50,
  "entry":         598.50,
  "stop":          599.80,
  "tp1":           597.20,
  "tp2":           596.00,
  "rvol":          2.41,
  "consec_bars":   3,
  "structural":    true,
  "regime":        "BEAR",
  "adx":           28.5,
  "vol":           5000000,
  "vol_delta_pct": 3.21,
  "poc_delta_pct": 0.08,
  "time":          "2026-02-17T14:30"
}

Response: {"status": "received"}
Discord:  Posts a whale embed to DISCORD_WEBHOOK_SIGNALS.
Redis:    Caches at whale:recent:{TICKER} for 30 min (committee confluence).
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import hashlib
import logging
import os
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")
WHALE_CONTEXT_TTL = 1800  # 30 minutes


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
    # v2 fields from Whale Hunter PineScript
    entry: Optional[float] = None
    stop: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    rvol: Optional[float] = None
    consec_bars: Optional[int] = None
    structural: Optional[bool] = None
    regime: Optional[str] = None
    adx: Optional[float] = None
    secret: Optional[str] = None

    model_config = {"extra": "allow"}


def _lean_emoji(lean: Optional[str]) -> str:
    if not lean:
        return ""
    upper = lean.upper()
    if "BEAR" in upper:
        return "\U0001f534"
    if "BULL" in upper:
        return "\U0001f7e2"
    return "\u26aa"


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
    rvol_str = f"{data.rvol:.2f}x" if data.rvol is not None else ""
    consec_str = f"{data.consec_bars} bars" if data.consec_bars is not None else ""
    regime_str = data.regime or ""
    structural_str = "\u2b50 Confirmed" if data.structural else ""

    color = 0xFF4444 if "BEAR" in lean_str else 0x44FF44 if "BULL" in lean_str else 0xAAAAAA

    fields = [
        {"name": "Lean", "value": f"{lean_icon} {lean_str}", "inline": True},
        {"name": "Timeframe", "value": tf_str, "inline": True},
        {"name": "Price", "value": price_str, "inline": True},
        {"name": "POC", "value": poc_str, "inline": True},
        {"name": "POC \u0394", "value": poc_delta_str, "inline": True},
        {"name": "Volume", "value": vol_str, "inline": True},
        {"name": "Vol \u0394%", "value": vol_delta_str, "inline": True},
        {"name": "Time", "value": time_str, "inline": True},
    ]

    # Add v2 fields if present
    v2_parts = [s for s in [rvol_str, consec_str, regime_str, structural_str] if s]
    if v2_parts:
        fields.append({"name": "v2 Context", "value": " | ".join(v2_parts), "inline": False})

    if data.entry is not None:
        plan_parts = [f"Entry: {data.entry:.2f}"]
        if data.stop is not None:
            plan_parts.append(f"Stop: {data.stop:.2f}")
        if data.tp1 is not None:
            plan_parts.append(f"TP1: {data.tp1:.2f}")
        if data.tp2 is not None:
            plan_parts.append(f"TP2: {data.tp2:.2f}")
        fields.append({"name": "Trade Plan", "value": " | ".join(plan_parts), "inline": False})

    return {
        "embeds": [
            {
                "title": f"\U0001f40b WHALE ALERT \u2014 {data.ticker}",
                "color": color,
                "fields": fields,
                "footer": {"text": "Pandora's Box \u2022 Whale Detector v2"},
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
            logger.info("\U0001f40b Whale alert posted to Discord")
    except Exception as exc:
        logger.error(f"Discord webhook failed: {exc}")


@router.post("/whale")
async def whale_webhook(data: WhaleSignal):
    """Receive a whale signal, forward to Discord, and cache for committee confluence."""
    # Validate webhook secret (same pattern as tradingview.py)
    WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET") or ""
    if WEBHOOK_SECRET:
        payload_secret = data.secret or ""
        if payload_secret != WEBHOOK_SECRET:
            logger.warning("Rejected whale webhook — invalid secret")
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Dedup: reject duplicate whale signals within 120s window
    dedup_raw = f"{data.ticker}:{data.lean}:{data.poc}:{data.vol}"
    dedup_hash = hashlib.md5(dedup_raw.encode()).hexdigest()[:16]
    dedup_key = f"webhook:dedup:whale:{dedup_hash}"
    try:
        from database.redis_client import get_redis_client
        _rc = await get_redis_client()
        if _rc and await _rc.get(dedup_key):
            logger.info("Whale dedup: skipping duplicate %s %s", data.ticker, data.lean)
            return {"status": "duplicate", "detail": "duplicate whale signal within 120s window"}
        if _rc:
            await _rc.set(dedup_key, "1", ex=120)
    except Exception:
        pass  # dedup is best-effort

    logger.info(
        f"\U0001f40b Whale signal received: {data.ticker} {data.lean} "
        f"vol={data.vol} poc={data.poc} price={data.price}"
    )

    discord_payload = _build_discord_message(data)
    await _post_to_discord(discord_payload)

    # Cache for committee confluence context (30 min TTL)
    try:
        from database.redis_client import get_redis_client
        import json as _json

        client = await get_redis_client()
        if client:
            cache_key = f"whale:recent:{data.ticker.upper()}"
            cache_data = {
                "ticker": data.ticker.upper(),
                "lean": data.lean,
                "poc": data.poc,
                "price": data.price,
                "entry": data.entry,
                "stop": data.stop,
                "tp1": data.tp1,
                "tp2": data.tp2,
                "rvol": data.rvol,
                "consec_bars": data.consec_bars,
                "structural": data.structural,
                "regime": data.regime,
                "adx": data.adx,
                "vol": data.vol,
                "vol_delta_pct": data.vol_delta_pct,
                "tf": data.tf,
                "cached_at": datetime.utcnow().isoformat() + "Z",
            }
            await client.set(cache_key, _json.dumps(cache_data), ex=WHALE_CONTEXT_TTL)
            logger.info(f"\U0001f40b Whale context cached: {cache_key} (TTL {WHALE_CONTEXT_TTL}s)")
    except Exception as e:
        logger.warning(f"Failed to cache whale context: {e}")

    # --- Pipeline integration: write whale signals to signals table ---
    try:
        from signals.pipeline import process_signal_unified
        import hashlib as _hashlib

        # Map whale fields to standard signal dict
        direction = "LONG" if (data.lean or "").upper() == "BULLISH" else (
            "SHORT" if (data.lean or "").upper() == "BEARISH" else None
        )

        # Skip CONTESTED signals — no clear direction for the pipeline
        if direction is None:
            logger.info("Whale signal CONTESTED — skipped pipeline (Discord-only)")
        else:
            # Generate unique signal ID
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            short_hash = _hashlib.md5(f"{data.ticker}{data.poc}{data.vol}".encode()).hexdigest()[:6]
            signal_id = f"WHALE_{data.ticker}_{ts}_{short_hash}"

            signal_data = {
                "signal_id": signal_id,
                "ticker": data.ticker.upper(),
                "strategy": "Whale_Hunter",
                "signal_type": f"WHALE_{direction}",
                "direction": direction,
                "entry_price": data.entry or data.price,
                "stop_loss": data.stop,
                "target_1": data.tp1,
                "target_2": data.tp2,
                "timeframe": data.tf or "5",
                "adx": data.adx,
                "rvol": data.rvol,
                "risk_reward": None,
                "asset_class": "EQUITY",
                "source": "whale_hunter",
                "signal_category": "DARK_POOL",
                "metadata": {
                    "poc": data.poc,
                    "lean": data.lean,
                    "consec_bars": data.consec_bars,
                    "structural": data.structural,
                    "regime": data.regime,
                    "vol": data.vol,
                    "vol_delta_pct": data.vol_delta_pct,
                    "poc_delta_pct": data.poc_delta_pct,
                },
                "timestamp": datetime.utcnow().isoformat(),
            }

            await process_signal_unified(signal_data, source="whale_hunter")
            logger.info(f"Whale signal entered pipeline: {signal_id}")

    except Exception as e:
        # Pipeline failure should never break the whale webhook
        logger.warning(f"Whale pipeline integration failed (Discord post succeeded): {e}")

    return {"status": "received"}


@router.get("/whale/recent/{ticker}")
async def get_recent_whale(ticker: str):
    """
    Return cached whale signal for a ticker (if any, within 30 min).
    Used by VPS committee context builder for confluence detection.
    """
    try:
        from database.redis_client import get_redis_client
        import json as _json

        client = await get_redis_client()
        if not client:
            return {"available": False}

        data = await client.get(f"whale:recent:{ticker.upper()}")
        if data:
            return {"available": True, "whale": _json.loads(data)}
    except Exception as e:
        logger.warning(f"Error fetching whale context for {ticker}: {e}")

    return {"available": False}
