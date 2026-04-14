"""
Bias Source Comparison — parallel scoring endpoint for The Great Consolidation.

During Sprint 2 validation period (5 trading days), the composite engine
scores GEX using BOTH Polygon (live) and UW API (shadow). Results are
logged to a comparison table for directional agreement analysis.

GET /api/bias/source-comparison — shows old vs new scores side by side.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

from database.postgres_client import get_postgres_client

logger = logging.getLogger("bias_source_comparison")
router = APIRouter(prefix="/bias", tags=["bias-comparison"])


async def log_comparison(factor_id: str, old_source: str, old_score: float,
                         new_source: str, new_score: float, old_detail: str = "",
                         new_detail: str = "") -> None:
    """Log a side-by-side comparison of old vs new data source scores."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO source_score_comparisons
                    (factor_id, old_source, old_score, new_source, new_score,
                     directional_agreement, magnitude_diff, old_detail, new_detail)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
                factor_id, old_source, old_score, new_source, new_score,
                (old_score > 0) == (new_score > 0),  # Both bullish or both bearish
                round(abs(old_score - new_score), 4),
                old_detail[:500] if old_detail else "",
                new_detail[:500] if new_detail else "",
            )
    except Exception as e:
        logger.warning("Failed to log source comparison: %s", e)


@router.get("/source-comparison")
async def get_source_comparison(
    factor_id: str = Query("gex", description="Factor to compare"),
    limit: int = Query(50, ge=1, le=200),
):
    """Show old vs new source scores side by side."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT factor_id, old_source, old_score, new_source, new_score,
                   directional_agreement, magnitude_diff, created_at
            FROM source_score_comparisons
            WHERE factor_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, factor_id, limit)

    comparisons = [{
        "factor_id": r["factor_id"],
        "old_source": r["old_source"],
        "old_score": float(r["old_score"]) if r["old_score"] else None,
        "new_source": r["new_source"],
        "new_score": float(r["new_score"]) if r["new_score"] else None,
        "directional_agreement": r["directional_agreement"],
        "magnitude_diff": float(r["magnitude_diff"]) if r["magnitude_diff"] else None,
        "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in rows]

    # Summary stats
    if comparisons:
        agree_count = sum(1 for c in comparisons if c["directional_agreement"])
        total = len(comparisons)
        avg_diff = sum(c["magnitude_diff"] or 0 for c in comparisons) / total
        return {
            "factor_id": factor_id,
            "total_comparisons": total,
            "directional_agreement_pct": round(agree_count / total * 100, 1),
            "avg_magnitude_diff": round(avg_diff, 4),
            "comparisons": comparisons,
        }

    return {"factor_id": factor_id, "total_comparisons": 0, "comparisons": []}
