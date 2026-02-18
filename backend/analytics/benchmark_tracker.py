"""
Benchmark tracker for analytics performance baselines.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)


def _bias_direction(level: Optional[str]) -> int:
    label = (level or "").upper()
    if "TORO" in label:
        return 1
    if "URSA" in label:
        return -1
    return 0


async def _load_daily_closes(conn, ticker: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (DATE(timestamp))
            DATE(timestamp) AS day,
            close
        FROM price_history
        WHERE ticker = $1
          AND timeframe = 'D'
          AND close IS NOT NULL
        ORDER BY DATE(timestamp), timestamp DESC
        """,
        ticker,
    )
    output: List[Dict[str, Any]] = []
    for row in rows:
        output.append({"day": row["day"], "close": float(row["close"])})
    output.sort(key=lambda r: r["day"])
    return output


async def _load_daily_bias_direction(conn) -> Dict[Any, int]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (DATE(created_at))
            DATE(created_at) AS day,
            bias_level
        FROM bias_composite_history
        ORDER BY DATE(created_at), created_at DESC
        """
    )
    return {row["day"]: _bias_direction(row["bias_level"]) for row in rows}


def _compute_bias_follow_return(closes: List[Dict[str, Any]], day_direction: Dict[Any, int]) -> Optional[float]:
    if len(closes) < 2:
        return None
    equity = 1.0
    for idx in range(1, len(closes)):
        prev_close = closes[idx - 1]["close"]
        curr_close = closes[idx]["close"]
        if prev_close <= 0:
            continue
        daily_return = (curr_close / prev_close) - 1.0
        direction = day_direction.get(closes[idx]["day"], 0)
        equity *= 1.0 + (direction * daily_return)
    return equity - 1.0


async def update_benchmarks() -> Dict[str, Any]:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        closes = await _load_daily_closes(conn, "SPY")
        if len(closes) < 2:
            return {"status": "insufficient_data", "message": "Need at least 2 daily SPY bars"}

        start_close = closes[0]["close"]
        end_close = closes[-1]["close"]
        if start_close <= 0:
            return {"status": "invalid_data", "message": "Start close must be > 0"}

        spy_buy_hold = (end_close / start_close) - 1.0
        bias_direction = await _load_daily_bias_direction(conn)
        bias_follow = _compute_bias_follow_return(closes, bias_direction)

        elapsed_days = max((closes[-1]["day"] - closes[0]["day"]).days, 1)
        risk_free = (1.05 ** (elapsed_days / 365.0)) - 1.0

        ts = datetime.now(timezone.utc)
        rows_to_insert = [
            ("SPY_BUY_HOLD", spy_buy_hold),
            ("BIAS_FOLLOW", bias_follow),
            ("RISK_FREE_5PCT", risk_free),
        ]

        for benchmark, cumulative_return in rows_to_insert:
            await conn.execute(
                """
                INSERT INTO benchmarks (timestamp, benchmark, cumulative_return)
                VALUES ($1, $2, $3)
                """,
                ts,
                benchmark,
                float(cumulative_return) if cumulative_return is not None else None,
            )

    logger.info(
        "Benchmarks updated: SPY=%.4f BIAS=%.4f RF=%.4f",
        spy_buy_hold,
        bias_follow or 0.0,
        risk_free,
    )
    return {
        "status": "ok",
        "timestamp": ts.isoformat(),
        "benchmarks": {
            "SPY_BUY_HOLD": spy_buy_hold,
            "BIAS_FOLLOW": bias_follow,
            "RISK_FREE_5PCT": risk_free,
        },
    }

