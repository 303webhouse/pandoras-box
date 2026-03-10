"""
Factor Staleness Monitor — alerts when bias factors go stale.

Checks each factor's last FactorReading timestamp against its configured
staleness_hours from FACTOR_CONFIG. Exposes an endpoint for the health
dashboard and optionally posts warnings to Discord.
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = (
    os.getenv("DISCORD_WEBHOOK_ALERTS")
    or os.getenv("DISCORD_WEBHOOK_SIGNALS")
    or ""
)

# Grace multiplier — only alert if factor is stale beyond N× its staleness_hours
STALENESS_GRACE_MULTIPLIER = 1.5


async def check_factor_staleness() -> Dict:
    """
    Check all factors for staleness. Returns a dict with:
      - stale_factors: list of {factor_id, hours_stale, staleness_hours, timeframe}
      - healthy_factors: list of factor_ids that are current
      - missing_factors: list of factor_ids with no reading at all
      - checked_at: ISO timestamp
    """
    from database.redis_client import get_redis_client
    from bias_engine.composite import FACTOR_CONFIG, REDIS_KEY_FACTOR_LATEST

    now = datetime.now(timezone.utc)
    stale: List[Dict] = []
    healthy: List[str] = []
    missing: List[str] = []

    try:
        client = await get_redis_client()
    except Exception as e:
        logger.error("Factor staleness: Redis unavailable: %s", e)
        return {
            "error": f"Redis unavailable: {e}",
            "stale_factors": [],
            "healthy_factors": [],
            "missing_factors": list(FACTOR_CONFIG.keys()),
            "checked_at": now.isoformat(),
        }

    for factor_id, config in FACTOR_CONFIG.items():
        key = REDIS_KEY_FACTOR_LATEST.format(factor_id=factor_id)
        try:
            raw = await client.get(key)
        except Exception as e:
            logger.warning("Factor staleness: failed to read %s: %s", key, e)
            missing.append(factor_id)
            continue

        if not raw:
            missing.append(factor_id)
            continue

        try:
            reading = json.loads(raw)
            ts_str = reading.get("timestamp", "")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            age_hours = (now - ts).total_seconds() / 3600
            threshold = config["staleness_hours"] * STALENESS_GRACE_MULTIPLIER

            if age_hours > threshold:
                stale.append({
                    "factor_id": factor_id,
                    "hours_stale": round(age_hours, 1),
                    "staleness_hours": config["staleness_hours"],
                    "threshold_hours": threshold,
                    "timeframe": config["timeframe"],
                    "last_updated": ts.isoformat(),
                })
            else:
                healthy.append(factor_id)
        except Exception as e:
            logger.warning("Factor staleness: failed to parse %s: %s", factor_id, e)
            missing.append(factor_id)

    return {
        "stale_factors": stale,
        "healthy_factors": healthy,
        "missing_factors": missing,
        "checked_at": now.isoformat(),
    }


async def alert_stale_factors(stale_factors: List[Dict]) -> None:
    """Post stale factor alerts to Discord."""
    if not stale_factors or not DISCORD_WEBHOOK_URL:
        return

    lines = []
    for f in stale_factors:
        lines.append(
            f"**{f['factor_id']}** ({f['timeframe']}): "
            f"{f['hours_stale']}h old (limit: {f['staleness_hours']}h)"
        )

    payload = json.dumps({
        "embeds": [{
            "title": "\U0001f7e1 Factor Staleness Warning",
            "description": (
                f"{len(stale_factors)} factor(s) are stale:\n" + "\n".join(lines)
            ),
            "color": 0xFFAA00,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }).encode("utf-8")

    req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Pivot-II/2.0")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                logger.warning("Factor staleness: Discord returned %s", resp.status)
    except Exception as e:
        logger.error("Factor staleness: Discord post failed: %s", e)


async def run_staleness_check(alert: bool = True) -> Dict:
    """Run staleness check and optionally alert. Returns check results."""
    result = await check_factor_staleness()
    if alert and result.get("stale_factors"):
        await alert_stale_factors(result["stale_factors"])
    return result
