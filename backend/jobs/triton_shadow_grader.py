"""Triton Step-0 B3 — whale-flow shadow grader.

Daily post-close pass: for triton_flow_shadow rows with graded_at IS NULL, compute
direction-adjusted forward returns (fwd_ret_1d/3d/5d) from 'r'-filtered daily
closes. Batched one bar-fetch per unique ticker (triton_flow_shadow BACKGROUND
caller). Skip-and-retry when a horizon bar doesn't exist yet; graded_at is set
only once the 5d horizon fills (fully graded).

Extends the a3 PATTERN — does NOT modify a3. Writes ONLY triton_flow_shadow
columns; the signals table is UNTOUCHED, no outcome_source writes anywhere.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

logger = logging.getLogger("triton_shadow")

HORIZONS = (1, 3, 5)
GRADE_LIMIT = 1000  # rows/pass ceiling


def _dir_adj(entry: float, close: float, direction: str) -> float:
    """Direction-adjusted return %. BULL = raw; BEAR = -raw. Positive = correct."""
    raw = (close - entry) / entry * 100.0
    if (direction or "").upper() == "BEAR":
        raw = -raw
    return round(raw, 4)


async def run_triton_shadow_grader() -> dict:
    """One grading pass. Never raises (fail-open). Returns a small summary."""
    from database.postgres_client import get_postgres_client
    from jobs.triton_shadow_common import (
        fetch_r_close_index, nth_trading_day, close_on_or_near, _f,
    )

    pool = await get_postgres_client()
    if not pool:
        return {"graded": 0, "skipped": 0}

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ticker, direction, fired_at, spot_at_fire
            FROM triton_flow_shadow
            WHERE graded_at IS NULL
              AND fired_at IS NOT NULL
              AND fired_at < NOW() - INTERVAL '1 day'   -- at least T+1 could exist
            ORDER BY fired_at
            LIMIT $1
            """,
            GRADE_LIMIT,
        )
    if not rows:
        return {"graded": 0, "skipped": 0}

    # Group by ticker for batched bar fetches
    by_ticker: dict = {}
    for r in rows:
        by_ticker.setdefault((r["ticker"] or "").upper(), []).append(r)

    today = datetime.now(timezone.utc).date()
    graded = fully = skipped = 0

    for ticker, group in by_ticker.items():
        if not ticker:
            skipped += len(group)
            continue
        earliest = min(
            (g["fired_at"].date() if hasattr(g["fired_at"], "date") else g["fired_at"])
            for g in group
        )
        lookback_days = (today - earliest).days + 12  # cover oldest fire + 5td + buffer
        idx = await fetch_r_close_index(ticker, lookback_days)
        if not idx:
            logger.warning("triton_grader: no 'r' bars for %s — skip %d", ticker, len(group))
            skipped += len(group)
            continue

        for g in group:
            try:
                fire_d = g["fired_at"].date() if hasattr(g["fired_at"], "date") else g["fired_at"]
                direction = g["direction"] or "BULL"
                # entry reference: fire-time spot, else fire-date 'r' close
                entry = _f(g["spot_at_fire"])
                if not entry or entry <= 0:
                    entry = close_on_or_near(idx, fire_d)
                if not entry or entry <= 0:
                    skipped += 1
                    continue

                vals = {1: None, 3: None, 5: None}
                for k in HORIZONS:
                    tgt = nth_trading_day(fire_d, k)
                    if tgt > today:
                        continue  # horizon not reached yet
                    close_k = close_on_or_near(idx, tgt)
                    if close_k is not None:
                        vals[k] = _dir_adj(entry, close_k, direction)

                if all(v is None for v in vals.values()):
                    skipped += 1
                    continue

                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE triton_flow_shadow
                        SET fwd_ret_1d = COALESCE($2, fwd_ret_1d),
                            fwd_ret_3d = COALESCE($3, fwd_ret_3d),
                            fwd_ret_5d = COALESCE($4, fwd_ret_5d),
                            graded_at  = CASE WHEN $4 IS NOT NULL THEN NOW() ELSE graded_at END
                        WHERE id = $1
                        """,
                        g["id"], vals[1], vals[3], vals[5],
                    )
                graded += 1
                if vals[5] is not None:
                    fully += 1
            except Exception as exc:
                logger.warning("triton_grader: row %s skip: %s", g["id"], type(exc).__name__)
                skipped += 1
                continue

    logger.info("triton_grader: touched=%d fully_graded=%d skipped=%d", graded, fully, skipped)
    return {"graded": graded, "fully_graded": fully, "skipped": skipped}
