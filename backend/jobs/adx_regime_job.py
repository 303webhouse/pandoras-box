"""SPY ADX regime writer (sub-brief 3 Chunk 3, shadow-first).

Computes SPY ADX(14) from UW daily bars and writes it to Redis
`regime:spy_adx_shadow` with a 90-min TTL + timestamp. SHADOW KEY: the live
scorer still reads `regime:spy_adx` (unchanged) until the Chunk 3 promote.

The 90-min TTL is deliberate — a dead writer lets the shadow key expire within
~3 missed 15-min cycles, so downstream reads fail to 'unknown' (fail-loud) rather
than serving a stale-but-confident regime.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SHADOW_KEY = "regime:spy_adx_shadow"
TTL_SECONDS = 5400  # 90 minutes


async def compute_and_store_spy_adx() -> dict | None:
    """Fetch SPY daily bars, compute ADX(14), classify, store the shadow key."""
    from indicators.bars import fetch_daily_ohlc
    from indicators.adx import latest_adx
    from scoring.adx_regime import classify_adx_regime

    ohlc = await fetch_daily_ohlc("SPY", lookback_sessions=60)
    if not ohlc:
        logger.warning("[adx_regime] SPY OHLC fetch returned no data — shadow key not refreshed")
        return None

    adx = latest_adx(ohlc["highs"], ohlc["lows"], ohlc["closes"], period=14)
    if adx is None:
        logger.warning(
            "[adx_regime] ADX compute returned None (insufficient bars: %d)",
            len(ohlc["closes"]),
        )
        return None

    regime = classify_adx_regime(adx)
    payload = {
        "adx": adx,
        "label": regime["label"],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": "uw_ohlc_1d",
        "bars": len(ohlc["closes"]),
    }

    try:
        from database.redis_client import get_redis_client
        rc = await get_redis_client()
        if rc:
            await rc.setex(SHADOW_KEY, TTL_SECONDS, json.dumps(payload))
            logger.info(
                "[adx_regime] SPY ADX=%.2f → %s (shadow, ttl=%ds, bars=%d)",
                adx, regime["label"], TTL_SECONDS, payload["bars"],
            )
    except Exception as exc:
        logger.warning("[adx_regime] Redis write failed: %s", exc)

    return payload
