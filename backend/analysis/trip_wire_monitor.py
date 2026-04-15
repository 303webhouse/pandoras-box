"""
Trip Wire Monitor (Brief 5F)

Monitors key market levels and fires alerts when thresholds are breached.
Trip wires are user-configurable via API and stored in Redis.

Default wires: VIX > 25, VIX > 35, SPY below 200-SMA, 10Y yield > 5%.
Scheduled: Every 15 minutes during market hours.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TRIPWIRE_REDIS_KEY = "regime:trip_wires"
TRIPWIRE_ALERTS_KEY = "regime:trip_wire_alerts"

# Default trip wires (seeded on first run if none exist)
DEFAULT_TRIP_WIRES = [
    {
        "id": "vix_elevated",
        "label": "VIX Elevated",
        "ticker": "VIX",
        "field": "price",
        "operator": ">",
        "threshold": 25.0,
        "severity": "warning",
        "enabled": True,
    },
    {
        "id": "vix_extreme",
        "label": "VIX Extreme Fear",
        "ticker": "VIX",
        "field": "price",
        "operator": ">",
        "threshold": 35.0,
        "severity": "critical",
        "enabled": True,
    },
    {
        "id": "spy_below_200sma",
        "label": "SPY Below 200-SMA",
        "ticker": "SPY",
        "field": "below_sma200",
        "operator": "==",
        "threshold": True,
        "severity": "warning",
        "enabled": True,
    },
    {
        "id": "tnx_high",
        "label": "10Y Yield > 5%",
        "ticker": "TNX",
        "field": "price",
        "operator": ">",
        "threshold": 50.0,
        "severity": "warning",
        "enabled": True,
    },
]


async def _get_redis():
    try:
        from database.redis_client import get_redis_client
    except ModuleNotFoundError:
        from backend.database.redis_client import get_redis_client
    return await get_redis_client()


async def get_trip_wires() -> List[Dict[str, Any]]:
    """Load trip wires from Redis, seed defaults if empty."""
    redis = await _get_redis()
    raw = await redis.get(TRIPWIRE_REDIS_KEY)
    if raw:
        return json.loads(raw)

    # Seed defaults
    await redis.set(TRIPWIRE_REDIS_KEY, json.dumps(DEFAULT_TRIP_WIRES))
    return DEFAULT_TRIP_WIRES


async def save_trip_wires(wires: List[Dict[str, Any]]) -> None:
    redis = await _get_redis()
    await redis.set(TRIPWIRE_REDIS_KEY, json.dumps(wires))


async def _get_current_value(ticker: str, field: str) -> Any:
    """Fetch the current value for a trip wire check."""
    try:
        from integrations.uw_api import get_snapshot, get_bars
    except ModuleNotFoundError:
        from backend.integrations.uw_api import get_snapshot, get_bars

    if field == "below_sma200":
        bars = await get_bars(ticker, 1, "day")
        if not bars or len(bars) < 200:
            return None
        closes = [b["c"] for b in bars if b.get("c") is not None]
        if len(closes) < 200:
            return None
        sma200 = sum(closes[-200:]) / 200
        current = closes[-1]
        return current < sma200

    if field == "price":
        snap = await get_snapshot(ticker)
        if snap and snap.get("day"):
            return snap["day"].get("c") or snap["day"].get("o")
        if snap and snap.get("prevDay"):
            return snap["prevDay"].get("c")
        return None

    return None


def _check_condition(value: Any, operator: str, threshold: Any) -> bool:
    """Evaluate a trip wire condition."""
    if value is None:
        return False
    try:
        if operator == ">":
            return float(value) > float(threshold)
        elif operator == "<":
            return float(value) < float(threshold)
        elif operator == ">=":
            return float(value) >= float(threshold)
        elif operator == "<=":
            return float(value) <= float(threshold)
        elif operator == "==":
            return value == threshold
    except (ValueError, TypeError):
        return False
    return False


async def run_trip_wire_scan() -> Dict[str, Any]:
    """
    Check all enabled trip wires. Returns scan results and fires Discord
    alerts for newly-breached wires.
    """
    wires = await get_trip_wires()
    redis = await _get_redis()

    # Load previously-breached set to avoid duplicate alerts
    prev_raw = await redis.get("regime:trip_wire_breached")
    previously_breached = set(json.loads(prev_raw)) if prev_raw else set()

    results = []
    newly_breached = []
    currently_breached = set()

    for wire in wires:
        if not wire.get("enabled", True):
            results.append({**wire, "status": "disabled", "current_value": None})
            continue

        wire_id = wire["id"]
        ticker = wire["ticker"]
        field = wire.get("field", "price")

        try:
            value = await _get_current_value(ticker, field)
            triggered = _check_condition(value, wire["operator"], wire["threshold"])

            status = "triggered" if triggered else "ok"
            results.append({**wire, "status": status, "current_value": value})

            if triggered:
                currently_breached.add(wire_id)
                if wire_id not in previously_breached:
                    newly_breached.append(wire)

        except Exception as e:
            logger.warning("Trip wire check failed for %s: %s", wire_id, e)
            results.append({**wire, "status": f"error: {e}", "current_value": None})

    # Update breached set in Redis
    await redis.setex(
        "regime:trip_wire_breached", 86400,
        json.dumps(list(currently_breached))
    )

    # Store scan results
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "timestamp": now,
        "wires": results,
        "triggered_count": len(currently_breached),
        "newly_breached": [w["label"] for w in newly_breached],
    }
    await redis.setex("regime:trip_wire_latest", 3600, json.dumps(payload))

    # Fire Discord alerts for newly breached wires
    if newly_breached:
        await _send_trip_wire_alerts(newly_breached)

        # Log alerts
        for wire in newly_breached:
            alert_entry = {
                "wire_id": wire["id"],
                "label": wire["label"],
                "severity": wire.get("severity", "warning"),
                "timestamp": now,
            }
            await redis.lpush(TRIPWIRE_ALERTS_KEY, json.dumps(alert_entry))
        await redis.ltrim(TRIPWIRE_ALERTS_KEY, 0, 99)
        await redis.expire(TRIPWIRE_ALERTS_KEY, 86400 * 7)

    logger.info(
        "Trip wire scan: %d wires, %d triggered, %d new breaches",
        len(results), len(currently_breached), len(newly_breached),
    )

    return payload


async def _send_trip_wire_alerts(wires: List[Dict[str, Any]]) -> None:
    """Send Discord embed for newly breached trip wires."""
    try:
        from bias_engine.anomaly_alerts import send_alert
    except ModuleNotFoundError:
        from backend.bias_engine.anomaly_alerts import send_alert

    lines = []
    max_severity = "warning"
    for w in wires:
        emoji = "🔴" if w.get("severity") == "critical" else "🟡"
        lines.append(f"{emoji} **{w['label']}**: {w['ticker']} {w['operator']} {w['threshold']}")
        if w.get("severity") == "critical":
            max_severity = "critical"

    description = "The following trip wires have been breached:\n\n" + "\n".join(lines)
    await send_alert("⚡ Trip Wire Alert", description, severity=max_severity)
