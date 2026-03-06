"""
Confluence Engine — Groups active signals by ticker+direction,
assigns STANDALONE / CONFIRMED / CONVICTION tiers.

Runs as a background task every 15 minutes during market hours.
Reads from trade_ideas table, updates confluence metadata, broadcasts via WebSocket.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any

try:
    import pytz
    ET = pytz.timezone("America/New_York")
except ImportError:
    ET = None

from confluence.lenses import get_lens, count_independent_lenses

logger = logging.getLogger(__name__)

# Confluence time window (hours)
CONFLUENCE_WINDOW_HOURS = 4


async def run_confluence_scan() -> Dict[str, Any]:
    """
    Main confluence scan. Called every 15 min during market hours.
    
    1. Query active signals from last 4 hours
    2. Group by (ticker, direction)
    3. For each group, determine unique lenses
    4. Assign tier: STANDALONE / CONFIRMED / CONVICTION
    5. Update signals with confluence metadata
    6. Post Discord alerts for CONFIRMED/CONVICTION
    7. Broadcast via WebSocket
    """
    from database.postgres_client import get_postgres_client

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=CONFLUENCE_WINDOW_HOURS)

    pool = await get_postgres_client()
    if not pool:
        return {"error": "No database connection", "updated": 0}

    try:
        async with pool.acquire() as conn:
            # Check if confluence columns exist, add them if not
            await _ensure_confluence_columns(conn)

            # Fetch active signals from last N hours
            rows = await conn.fetch("""
                SELECT id, signal_id, ticker, direction, strategy, signal_type,
                       score, timestamp, confidence
                FROM trade_ideas
                WHERE timestamp >= $1
                  AND status = 'ACTIVE'
                ORDER BY ticker, direction, timestamp
            """, cutoff)
    except Exception as e:
        logger.error("Confluence: failed to query signals: %s", e)
        return {"error": str(e), "updated": 0}

    if not rows:
        logger.debug("Confluence: no active signals in %d-hour window", CONFLUENCE_WINDOW_HOURS)
        return {"updated": 0, "confirmed": 0, "conviction": 0}

    # Group by (ticker, direction)
    groups: Dict[tuple, List[dict]] = {}
    for row in rows:
        r = dict(row)
        key = (r.get("ticker", ""), r.get("direction", ""))
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    updated = 0
    confirmed_count = 0
    conviction_count = 0
    confluence_events = []  # For Discord notifications

    for (ticker, direction), signals in groups.items():
        if len(signals) < 2:
            continue

        # Determine unique lenses in this group
        lenses = set()
        lens_to_signals: Dict[str, List[dict]] = {}
        for sig in signals:
            strategy = sig.get("strategy", "")
            lens = get_lens(strategy)
            if lens != "UNKNOWN":
                lenses.add(lens)
                if lens not in lens_to_signals:
                    lens_to_signals[lens] = []
                lens_to_signals[lens].append(sig)

        if len(lenses) < 2:
            continue  # Same lens = redundant, not confirming

        # Count truly independent lenses
        independent = count_independent_lenses(lenses)

        # Determine tier
        tier = _determine_tier(independent, lenses, signals)

        if tier == "STANDALONE":
            continue

        if tier == "CONVICTION":
            conviction_count += 1
        elif tier == "CONFIRMED":
            confirmed_count += 1

        # Update all signals in this group
        signal_ids = [sig["signal_id"] for sig in signals if sig.get("signal_id")]
        lens_list = sorted(lenses)

        try:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE trade_ideas
                    SET confluence_tier = $1,
                        confluence_count = $2,
                        confluence_updated_at = NOW()
                    WHERE signal_id = ANY($3::text[])
                """, tier, len(lenses), signal_ids)
            updated += len(signals)
        except Exception as e:
            logger.error("Confluence: failed to update %s %s: %s", ticker, direction, e)
            continue

        confluence_events.append({
            "ticker": ticker,
            "direction": direction,
            "tier": tier,
            "lenses": lens_list,
            "signals": signals,
            "independent_count": independent,
        })

    # Post Discord notifications
    for event in confluence_events:
        try:
            await _post_confluence_discord(event)
        except Exception as e:
            logger.warning("Confluence Discord notification failed: %s", e)

    # Broadcast via WebSocket
    if updated > 0:
        try:
            from websocket.broadcaster import manager
            await manager.broadcast({
                "type": "confluence_update",
                "updated": updated,
                "confirmed": confirmed_count,
                "conviction": conviction_count,
            })
        except Exception as e:
            logger.debug("Confluence WebSocket broadcast failed: %s", e)

    result = {
        "updated": updated,
        "confirmed": confirmed_count,
        "conviction": conviction_count,
        "groups_checked": len(groups),
        "total_signals": len(rows),
    }

    if updated > 0:
        logger.info(
            "\U0001f517 Confluence: %d signals updated (%d CONFIRMED, %d CONVICTION) from %d groups",
            updated, confirmed_count, conviction_count, len(groups),
        )

    return result


def _determine_tier(independent: int, lenses: set, signals: list) -> str:
    """
    Assign confluence tier based on independent lens count and quality gates.
    
    CONVICTION requires either:
    - 3+ independent lenses, OR
    - 2 independent lenses + quality gate (Scout score >= 5, or Holy Grail ADX >= 30)
    
    CONFIRMED requires:
    - 2+ different lenses (including adjacent)
    """
    if independent >= 3:
        return "CONVICTION"

    if independent >= 2:
        # Check quality gates for CONVICTION upgrade
        has_quality_gate = False
        for sig in signals:
            strategy = sig.get("strategy", "")
            lens = get_lens(strategy)

            # Scout Sniper with high quality score
            if lens == "REVERSAL_DETECTION" and sig.get("score") is not None:
                try:
                    if float(sig["score"]) >= 5:
                        has_quality_gate = True
                        break
                except (ValueError, TypeError):
                    pass

            # High-scoring signal from any strategy (score >= 80 in the trade_ideas scorer)
            if sig.get("score") is not None:
                try:
                    if float(sig["score"]) >= 80:
                        has_quality_gate = True
                        break
                except (ValueError, TypeError):
                    pass

        if has_quality_gate:
            return "CONVICTION"
        return "CONFIRMED"

    # 2 lenses but only 1 independent (adjacent pair like CTA + Holy Grail)
    if len(lenses) >= 2:
        return "CONFIRMED"

    return "STANDALONE"


async def _ensure_confluence_columns(conn) -> None:
    """
    Add confluence columns to trade_ideas table if they don't exist.
    Safe to call repeatedly (IF NOT EXISTS).
    """
    try:
        await conn.execute("""
            ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS confluence_tier VARCHAR(20) DEFAULT 'STANDALONE';
        """)
        await conn.execute("""
            ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS confluence_count INTEGER DEFAULT 0;
        """)
        await conn.execute("""
            ALTER TABLE trade_ideas ADD COLUMN IF NOT EXISTS confluence_updated_at TIMESTAMP;
        """)
    except Exception as e:
        # Column might already exist or table structure differs
        logger.debug("Confluence column check: %s", e)


async def _post_confluence_discord(event: dict) -> None:
    """
    Post a confluence alert to Discord via webhook.
    Uses the same webhook pattern as other signal notifications.
    """
    import os
    import json

    webhook_url = os.environ.get("DISCORD_SIGNALS_WEBHOOK")
    if not webhook_url:
        # Try the general webhook
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.debug("No Discord webhook configured for confluence alerts")
        return

    tier = event["tier"]
    ticker = event["ticker"]
    direction = event["direction"]
    lenses = event["lenses"]
    signals = event["signals"]
    independent = event["independent_count"]

    emoji = "\U0001f517" if tier == "CONFIRMED" else "\U0001f525"  # \U0001f517 = link, \U0001f525 = fire
    color = 0x3b82f6 if tier == "CONFIRMED" else 0xef4444

    strategies = list(set(sig.get("strategy", "?") for sig in signals))
    scores = [sig.get("score", 0) for sig in signals if sig.get("score") is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    embed = {
        "title": f"{emoji} {tier}: {ticker} {direction}",
        "color": color,
        "fields": [
            {"name": "Lenses", "value": " + ".join(lenses), "inline": False},
            {"name": "Strategies", "value": ", ".join(strategies), "inline": True},
            {"name": "Signals", "value": str(len(signals)), "inline": True},
            {"name": "Avg Score", "value": str(avg_score), "inline": True},
            {"name": "Independent Lenses", "value": str(independent), "inline": True},
        ],
        "footer": {"text": f"Confluence Engine \u2022 {CONFLUENCE_WINDOW_HOURS}h window"},
    }

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json={"embeds": [embed]})
    except ImportError:
        # Fallback to urllib if aiohttp not available
        import urllib.request
        data = json.dumps({"embeds": [embed]}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.warning("Discord confluence webhook failed: %s", e)
