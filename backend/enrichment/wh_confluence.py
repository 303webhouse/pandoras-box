"""
WH-CONFLUENCE Enricher — ZEUS Phase 1B.2

Checks whether an incoming signal is backed by:
  1. A recent WH-ACCUMULATION signal for the same ticker (within 48h)
  2. Fresh, sizeable darkpool activity (flow_events total_premium > $2M within 4h)

When both are present, returns a bonus and a list of recent Tier 3 TA signals
on the same ticker + direction (within 4h) for use by apply_tier3_confluence_bonus().

Called from pipeline.py apply_scoring() BEFORE apply_tier3_confluence_bonus().

Returns:
    {
        "confluence_found": bool,
        "bonus":            int,      # WH-ACC backing bonus (0, 4, or 8)
        "ta_signals":       list,     # Tier 3 signal_types found on same ticker/direction
        "details":          dict,     # For triggering_factors storage
    }
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("wh_confluence")

_WH_ACC_LOOKBACK_HOURS  = 48
_DARKPOOL_LOOKBACK_HOURS = 4
_DARKPOOL_MIN_PREMIUM    = 2_000_000   # $2M
_TA_SIGNAL_LOOKBACK_HOURS = 4

# Bonus values
_BONUS_BOTH   = 8   # WH-ACC signal + fresh darkpool blocks
_BONUS_ACC_ONLY = 4  # WH-ACC signal only (darkpool too stale or below threshold)


async def check_wh_confluence(ticker: str, direction: str) -> Dict[str, Any]:
    """
    Check if the given ticker/direction pair has WH-ACCUMULATION backing
    plus fresh darkpool evidence, and collects any aligned Tier 3 TA signals.

    Args:
        ticker:    Ticker symbol (uppercase).
        direction: Signal direction ('LONG', 'SHORT', etc.).

    Returns:
        Confluence result dict (always — never raises).
    """
    _empty = {"confluence_found": False, "bonus": 0, "ta_signals": [], "details": {}}

    if not ticker:
        return _empty

    try:
        from database.postgres_client import get_postgres_client
        from scoring.feed_tier_classifier import TIER3_SIGNAL_TYPES
        pool = await get_postgres_client()
    except Exception as exc:
        logger.debug("WH confluence setup failed: %s", exc)
        return _empty

    try:
        async with pool.acquire() as conn:
            # ── Check 1: Recent WH-ACCUMULATION signal ─────────────────────
            acc_row = await conn.fetchrow(
                "SELECT signal_id FROM signals "
                "WHERE ticker = $1 AND signal_type = 'WH_ACCUMULATION' "
                f"AND timestamp > NOW() - INTERVAL '{_WH_ACC_LOOKBACK_HOURS} hours' "
                "ORDER BY timestamp DESC LIMIT 1",
                ticker.upper(),
            )

            if not acc_row:
                return _empty

            # ── Check 2: Fresh darkpool activity proxy via flow_events ──────
            # flow_events total_premium is the aggregate call+put premium;
            # a high value suggests significant institutional positioning.
            dp_row = await conn.fetchrow(
                "SELECT total_premium FROM flow_events "
                "WHERE ticker = $1 "
                f"AND captured_at > NOW() - INTERVAL '{_DARKPOOL_LOOKBACK_HOURS} hours' "
                "AND total_premium > $2 "
                "ORDER BY captured_at DESC LIMIT 1",
                ticker.upper(),
                _DARKPOOL_MIN_PREMIUM,
            )

            has_darkpool = dp_row is not None
            bonus = _BONUS_BOTH if has_darkpool else _BONUS_ACC_ONLY

            # ── Collect recent Tier 3 TA signals (same ticker, aligned direction) ──
            bullish_dirs = {"LONG", "BUY", "BULLISH"}
            bearish_dirs = {"SHORT", "SELL", "BEARISH"}
            dir_upper = direction.upper()
            if dir_upper in bullish_dirs:
                dir_set = list(bullish_dirs)
            elif dir_upper in bearish_dirs:
                dir_set = list(bearish_dirs)
            else:
                dir_set = []

            ta_signals: List[str] = []
            if dir_set:
                ta_rows = await conn.fetch(
                    "SELECT DISTINCT signal_type FROM signals "
                    "WHERE ticker = $1 "
                    "AND UPPER(direction) = ANY($2::text[]) "
                    f"AND created_at > NOW() - INTERVAL '{_TA_SIGNAL_LOOKBACK_HOURS} hours' "
                    "AND status NOT IN ('DISMISSED', 'REJECTED')",
                    ticker.upper(),
                    [d.upper() for d in dir_set],
                )
                tier3_types = TIER3_SIGNAL_TYPES
                ta_signals = [
                    r["signal_type"] for r in ta_rows
                    if r["signal_type"] and r["signal_type"].upper() in tier3_types
                ]

    except Exception as exc:
        logger.debug("WH confluence DB query failed for %s: %s", ticker, exc)
        return _empty

    details = {
        "acc_signal_id":   acc_row["signal_id"],
        "has_darkpool":    has_darkpool,
        "darkpool_premium": int(dp_row["total_premium"]) if dp_row else 0,
        "ta_signal_count": len(ta_signals),
    }

    logger.debug(
        "WH confluence %s %s: bonus=%+d ta=%s",
        ticker, direction, bonus, ta_signals,
    )

    return {
        "confluence_found": True,
        "bonus":            bonus,
        "ta_signals":       ta_signals,
        "details":          details,
    }
