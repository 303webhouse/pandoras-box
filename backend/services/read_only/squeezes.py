"""Read-only Hydra squeeze score accessors.

Direct SELECT from squeeze_scores. We do NOT import api.hydra
because that module also contains POST endpoints that trigger writes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> Dict[str, Any]:
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


async def get_squeeze_scores(
    ticker: Optional[str] = None,
    min_score: float = 50.0,
    limit: int = 10,
) -> Optional[List[Dict[str, Any]]]:
    """Return ranked squeeze candidates, optionally filtered to one ticker.

    Returns None if the Postgres pool is unavailable; returns [] if no rows.
    """
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            if ticker:
                rows = await conn.fetch(
                    """SELECT * FROM squeeze_scores
                       WHERE ticker = $1 AND composite_score >= $2
                       ORDER BY composite_score DESC LIMIT $3""",
                    ticker.upper(),
                    min_score,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT * FROM squeeze_scores
                       WHERE composite_score >= $1
                       ORDER BY composite_score DESC LIMIT $2""",
                    min_score,
                    limit,
                )
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning("squeeze scores read failed: %s", exc)
        return None
