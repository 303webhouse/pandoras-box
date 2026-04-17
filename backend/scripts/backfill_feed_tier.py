"""
Backfill feed_tier — ZEUS Phase 2.4

One-shot script. Classifies the last 7 days of signals that have
feed_tier = 'research_log' (the column default) using the same
classify_signal_tier() logic the live pipeline uses.

Run once after deploying ZEUS Phase 1B + Phase 2:

    cd backend
    python scripts/backfill_feed_tier.py

Idempotent: signals already classified to a non-default tier are skipped.
"""

import asyncio
import json
import logging
import os
import sys

# Allow imports from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill_feed_tier")


async def run_backfill() -> None:
    from database.postgres_client import get_postgres_client
    from scoring.feed_tier_classifier import classify_signal_tier

    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, signal_id, signal_type, signal_category, direction,
                   score, triggering_factors, feed_tier_ceiling, status
            FROM signals
            WHERE created_at > NOW() - INTERVAL '7 days'
              AND feed_tier = 'research_log'
            ORDER BY created_at DESC
            """,
        )

    logger.info("Backfill: %d signals to classify", len(rows))

    updated = 0
    skipped = 0

    async with pool.acquire() as conn:
        for row in rows:
            d = dict(row)

            # Rebuild a minimal signal_data for the classifier
            triggering_factors = {}
            if d.get("triggering_factors"):
                try:
                    tf_raw = d["triggering_factors"]
                    triggering_factors = (
                        json.loads(tf_raw) if isinstance(tf_raw, str) else dict(tf_raw)
                    )
                except Exception:
                    pass

            signal_data = {
                "signal_type":      d.get("signal_type") or "",
                "signal_category":  d.get("signal_category") or "TRADE_SETUP",
                "strategy":         "",   # not stored on old rows, default
                "direction":        d.get("direction") or "",
                "feed_tier_ceiling": d.get("feed_tier_ceiling"),
                "triggering_factors": triggering_factors,
            }

            score = float(d.get("score") or 0)
            tier  = classify_signal_tier(signal_data, score)

            if tier == "research_log":
                skipped += 1
                continue

            await conn.execute(
                "UPDATE signals SET feed_tier = $1 WHERE id = $2",
                tier,
                d["id"],
            )
            updated += 1
            logger.debug("  %s → %s (score=%.0f)", d["signal_id"], tier, score)

    logger.info(
        "Backfill complete — %d updated, %d left as research_log",
        updated, skipped,
    )


if __name__ == "__main__":
    asyncio.run(run_backfill())
