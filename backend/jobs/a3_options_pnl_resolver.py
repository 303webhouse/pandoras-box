"""A3 — OPTIONS_PNL resolver.

Reads exited signal_options_expressions rows (b2_status='EXITED') and sets
signals.outcome_source = 'OPTIONS_PNL' as a secondary label under IS-NULL guard.

The actual options P&L grade lives in signal_options_expressions — this resolver
only writes the pointer on signals. No numbers are duplicated.

Design:
- IS-NULL guard: only writes outcome_source when currently NULL.
- Shadow mode: A3_SHADOW_MODE=true (default) → log only, no DB writes.
- Does NOT modify signal_options_expressions in any way.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

A3_SHADOW_MODE = os.getenv("A3_SHADOW_MODE", "true").lower() != "false"


async def resolve_options_pnl(
    pool,
    signal_ids: Optional[List[str]] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    Set signals.outcome_source = 'OPTIONS_PNL' for signals whose expression
    is in b2_status='EXITED' and whose outcome_source is still NULL.

    signal_ids: if provided, restrict to these signals (Gate 2 sample mode).
    """
    shadow = A3_SHADOW_MODE
    if shadow:
        logger.info("a3_opts: SHADOW MODE — compute+log only, no DB writes")

    async with pool.acquire() as conn:
        if signal_ids:
            rows = await conn.fetch(
                """
                SELECT soe.signal_id,
                       soe.options_pnl,
                       soe.exit_trigger,
                       soe.entry_mark,
                       soe.max_profit,
                       soe.max_loss,
                       s.ticker,
                       s.direction,
                       s.outcome_source
                FROM signal_options_expressions soe
                JOIN signals s ON s.signal_id = soe.signal_id
                WHERE soe.b2_status = 'EXITED'
                  AND soe.signal_id = ANY($1::text[])
                  AND s.outcome_source IS NULL
                """,
                signal_ids,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT soe.signal_id,
                       soe.options_pnl,
                       soe.exit_trigger,
                       soe.entry_mark,
                       soe.max_profit,
                       soe.max_loss,
                       s.ticker,
                       s.direction,
                       s.outcome_source
                FROM signal_options_expressions soe
                JOIN signals s ON s.signal_id = soe.signal_id
                WHERE soe.b2_status = 'EXITED'
                  AND s.outcome_source IS NULL
                LIMIT $1
                """,
                limit,
            )

    if not rows:
        logger.info("a3_opts: no exited expressions with NULL outcome_source")
        return {"eligible": 0, "written": 0, "shadow": shadow}

    written = 0
    for row in rows:
        sig_id   = row["signal_id"]
        pnl      = row["options_pnl"]
        trigger  = row["exit_trigger"]
        entry_m  = row["entry_mark"]
        max_p    = row["max_profit"]
        max_l    = row["max_loss"]

        # % of max_profit achieved (for context logging)
        pct_of_max = None
        if pnl is not None and max_p and float(max_p) != 0:
            pct_of_max = round(float(pnl) / float(max_p) * 100, 1)

        logger.info(
            "a3_opts: %s %s %s options_pnl=$%.2f trigger=%s pct_of_max=%s [%s]",
            sig_id, row["ticker"], row["direction"],
            float(pnl) if pnl else 0, trigger, pct_of_max,
            "SHADOW" if shadow else "WRITE",
        )

        if not shadow:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE signals
                    SET outcome_source = 'OPTIONS_PNL'
                    WHERE signal_id = $1
                      AND outcome_source IS NULL
                    """,
                    sig_id,
                )
            written += 1

    logger.info("a3_opts: done — eligible=%d written=%d shadow=%s", len(rows), written, shadow)
    return {"eligible": len(rows), "written": written, "shadow": shadow}
