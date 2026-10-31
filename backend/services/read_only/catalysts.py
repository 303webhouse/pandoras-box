"""Read-only catalyst / event accessors.

Reuses api.catalyst_calendar.get_upcoming_catalysts — pure read (static
file + Redis LRANGE on regime:custom_catalysts).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from api.catalyst_calendar import get_upcoming_catalysts as _api_get_upcoming

logger = logging.getLogger(__name__)


async def get_upcoming_catalysts(days: int = 14, lookback_hours: int = 24) -> Optional[Dict[str, Any]]:
    """Return catalysts from `lookback_hours` ago to `days` ahead, or None on failure.

    R-IV.1471(b): the API function gained `lookback_hours` (R-IV.1461(f)4) and this wrapper did
    not, so hub_get_hermes_alerts raised TypeError on every call from 4783239f to the fix. The
    test for it drives the MCP tool through this wrapper, not around it.
    """
    try:
        return await _api_get_upcoming(days=days, lookback_hours=lookback_hours)
    except Exception as exc:
        logger.warning("catalyst calendar read failed: %s", exc)
        return None
