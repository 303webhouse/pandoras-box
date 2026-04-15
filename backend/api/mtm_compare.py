"""
MTM Comparison — runs both Polygon and UW valuations side-by-side.

GET /api/positions/mtm-compare — compares mark-to-market values from both sources.
Used during Sprint 4 validation to verify UW matches Polygon before cutover.
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends

from database.postgres_client import get_postgres_client
from utils.pivot_auth import require_api_key

logger = logging.getLogger("api.mtm_compare")
router = APIRouter()


@router.get("/positions/mtm-compare")
async def compare_mtm(_=Depends(require_api_key)):
    """
    Compare Polygon vs UW MTM values for all open positions.
    Returns per-position comparison with diff percentages.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN'"
        )

    if not rows:
        return {"status": "no_open_positions", "positions": []}

    # Try importing both sources
    polygon_available = False
    uw_available = False

    try:
        from integrations.polygon_options import (
            get_spread_value as poly_spread,
            get_single_option_value as poly_single,
        )
        polygon_available = True
    except ImportError:
        poly_spread = None
        poly_single = None

    try:
        from integrations.uw_api import (
            get_spread_value as uw_spread,
            get_single_option_value as uw_single,
        )
        uw_available = True
    except ImportError:
        uw_spread = None
        uw_single = None

    comparisons = []
    max_diff_pct = 0.0
    total_diff = 0.0
    compared = 0

    for row in rows:
        pos = dict(row)
        ticker = pos.get("ticker", "")
        structure = (pos.get("structure") or "").lower()
        long_strike = pos.get("long_strike")
        short_strike = pos.get("short_strike")
        expiry = pos.get("expiry") or pos.get("expiration")
        at = (pos.get("asset_type") or "").upper()

        # Only compare options positions
        if at not in ("OPTION", "OPTIONS", "SPREAD") and "spread" not in structure and "call" not in structure and "put" not in structure:
            continue

        if not expiry or not long_strike:
            continue

        entry = {
            "position_id": pos.get("id"),
            "ticker": ticker,
            "structure": pos.get("structure"),
            "long_strike": long_strike,
            "short_strike": short_strike,
            "expiry": str(expiry),
            "polygon_mtm": None,
            "uw_mtm": None,
            "diff": None,
            "diff_pct": None,
        }

        # Get Polygon value
        if polygon_available and short_strike:
            try:
                result = await poly_spread(ticker, float(long_strike), float(short_strike), str(expiry), structure)
                if result:
                    entry["polygon_mtm"] = result.get("spread_value")
            except Exception as e:
                logger.debug("Polygon spread failed for %s: %s", ticker, e)
        elif polygon_available and not short_strike:
            try:
                opt_type = "put" if "put" in structure else "call"
                result = await poly_single(ticker, float(long_strike), str(expiry), opt_type)
                if result:
                    entry["polygon_mtm"] = result.get("option_value")
            except Exception as e:
                logger.debug("Polygon single failed for %s: %s", ticker, e)

        # Get UW value
        if uw_available and short_strike:
            try:
                result = await uw_spread(ticker, float(long_strike), float(short_strike), str(expiry), structure)
                if result:
                    entry["uw_mtm"] = result.get("spread_value")
            except Exception as e:
                logger.debug("UW spread failed for %s: %s", ticker, e)
        elif uw_available and not short_strike:
            try:
                opt_type = "put" if "put" in structure else "call"
                result = await uw_single(ticker, float(long_strike), str(expiry), opt_type)
                if result:
                    entry["uw_mtm"] = result.get("option_value")
            except Exception as e:
                logger.debug("UW single failed for %s: %s", ticker, e)

        # Calculate diff
        if entry["polygon_mtm"] is not None and entry["uw_mtm"] is not None:
            diff = abs(entry["polygon_mtm"] - entry["uw_mtm"])
            entry["diff"] = round(diff, 4)
            base = max(abs(entry["polygon_mtm"]), 0.01)  # avoid div/0
            entry["diff_pct"] = round((diff / base) * 100, 2)
            max_diff_pct = max(max_diff_pct, entry["diff_pct"])
            total_diff += entry["diff_pct"]
            compared += 1

        comparisons.append(entry)

    avg_diff = round(total_diff / compared, 2) if compared > 0 else 0

    return {
        "positions": comparisons,
        "compared": compared,
        "max_diff_pct": round(max_diff_pct, 2),
        "avg_diff_pct": avg_diff,
        "pass": max_diff_pct < 1.0 if compared > 0 else None,
        "polygon_available": polygon_available,
        "uw_available": uw_available,
    }
