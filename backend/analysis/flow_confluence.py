"""
Flow-Signal Confluence Detector (Brief 5I)

Scans for tickers that have BOTH active trade signals AND recent UW options
flow activity. When flow and signals align on the same ticker + direction,
it fires a Discord alert and caches the confluence for the frontend badge.

Scheduled: Every 15 minutes during market hours.
Redis key: `regime:flow_confluence`
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

CONFLUENCE_REDIS_KEY = "regime:flow_confluence"


async def _get_redis():
    try:
        from database.redis_client import get_redis_client
    except ModuleNotFoundError:
        from backend.database.redis_client import get_redis_client
    return await get_redis_client()


async def _get_active_signal_tickers() -> Dict[str, str]:
    """
    Get tickers with active signals and their directions.
    Returns {ticker: direction} for tickers with signal:active:* counters.
    """
    redis = await _get_redis()
    result = {}

    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match="signal:active:*", count=200)
        for key in keys:
            key_str = key if isinstance(key, str) else key.decode("utf-8")
            ticker = key_str.split("signal:active:")[-1]
            if ticker and len(ticker) <= 6:
                result[ticker.upper()] = "ACTIVE"
        if cursor == 0:
            break

    return result


async def _get_flow_tickers() -> Dict[str, Dict[str, Any]]:
    """
    Get tickers with recent UW flow data.
    Returns {ticker: flow_data} from uw:flow:* keys.
    """
    redis = await _get_redis()
    result = {}

    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match="uw:flow:*", count=200)
        for key in keys:
            key_str = key if isinstance(key, str) else key.decode("utf-8")
            if key_str in ("uw:flow:recent",):
                continue
            ticker = key_str.split("uw:flow:")[-1]
            if not ticker or len(ticker) > 6:
                continue
            try:
                raw = await redis.get(key_str)
                if raw:
                    data = json.loads(raw)
                    result[ticker.upper()] = data
            except Exception:
                continue
        if cursor == 0:
            break

    return result


async def run_flow_confluence_scan() -> Dict[str, Any]:
    """
    Find tickers with both active signals and UW flow.
    Cache results and fire alerts for new confluences.
    """
    redis = await _get_redis()

    signal_tickers = await _get_active_signal_tickers()
    flow_tickers = await _get_flow_tickers()

    # Find overlapping tickers
    overlap = set(signal_tickers.keys()) & set(flow_tickers.keys())

    confluences = []
    for ticker in sorted(overlap):
        flow = flow_tickers[ticker]
        flow_sentiment = (flow.get("flow_sentiment") or flow.get("sentiment") or "").upper()
        premium = flow.get("total_premium") or flow.get("premium") or 0
        pc_ratio = flow.get("pc_ratio")

        confluences.append({
            "ticker": ticker,
            "has_signal": True,
            "flow_sentiment": flow_sentiment or "NEUTRAL",
            "flow_premium": premium,
            "pc_ratio": pc_ratio,
        })

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "timestamp": now,
        "confluences": confluences,
        "count": len(confluences),
    }

    # Check for newly-added confluences vs last scan
    prev_raw = await redis.get(CONFLUENCE_REDIS_KEY)
    prev_tickers = set()
    if prev_raw:
        prev = json.loads(prev_raw)
        prev_tickers = {c["ticker"] for c in prev.get("confluences", [])}

    new_tickers = {c["ticker"] for c in confluences} - prev_tickers

    # Cache results
    await redis.setex(CONFLUENCE_REDIS_KEY, 3600, json.dumps(payload))

    # Fire alert for new confluences
    if new_tickers:
        await _send_confluence_alert([c for c in confluences if c["ticker"] in new_tickers])

    logger.info("Flow-signal confluence scan: %d overlaps (%d new)", len(confluences), len(new_tickers))
    return payload


async def _send_confluence_alert(confluences: List[Dict[str, Any]]) -> None:
    """Send Discord alert for new flow-signal confluences."""
    try:
        from bias_engine.anomaly_alerts import send_alert
    except ModuleNotFoundError:
        from backend.bias_engine.anomaly_alerts import send_alert

    lines = []
    for c in confluences[:10]:
        emoji = "🟢" if c["flow_sentiment"] == "BULLISH" else ("🔴" if c["flow_sentiment"] == "BEARISH" else "⚪")
        premium_str = f"${c['flow_premium']:,.0f}" if c['flow_premium'] else "N/A"
        lines.append(f"{emoji} **{c['ticker']}** — Flow: {c['flow_sentiment']}, Premium: {premium_str}")

    description = "Active signals + UW flow detected on same tickers:\n\n" + "\n".join(lines)
    await send_alert("🔗 Flow-Signal Confluence", description, severity="info")
