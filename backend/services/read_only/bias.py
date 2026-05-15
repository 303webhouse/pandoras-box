"""Read-only bias data accessors."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bias_engine.composite import (
    get_active_override,
    get_cached_composite,
)

logger = logging.getLogger(__name__)


async def get_composite_bias() -> Optional[Dict[str, Any]]:
    """Return current composite bias snapshot or None if no cached reading.

    Reads only — does NOT recompute. The composite engine writer
    (bias_engine.composite.compute_composite) populates the cache on
    its own schedule. This namespace deliberately cannot trigger that
    path.
    """
    try:
        result = await get_cached_composite()
    except Exception as exc:
        logger.warning("composite bias read failed: %s", exc)
        return None
    if result is None:
        return None

    payload = result.model_dump(mode="json")
    payload["_fetched_at"] = datetime.now(timezone.utc).isoformat()
    return payload


async def get_manual_override() -> Optional[Dict[str, Any]]:
    """Return current manual bias override or None."""
    try:
        return await get_active_override()
    except Exception as exc:
        logger.warning("override read failed: %s", exc)
        return None
