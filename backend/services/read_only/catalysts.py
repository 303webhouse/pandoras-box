"""Read-only catalyst / event accessors.

Reuses api.catalyst_calendar.get_upcoming_catalysts — pure read (static
file + Redis LRANGE on regime:custom_catalysts).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from api.catalyst_calendar import get_upcoming_catalysts as _api_get_upcoming

logger = logging.getLogger(__name__)


async def get_upcoming_catalysts(days: int = 14) -> Optional[Dict[str, Any]]:
    """Return upcoming catalysts within `days` of today, or None on failure."""
    try:
        return await _api_get_upcoming(days=days)
    except Exception as exc:
        logger.warning("catalyst calendar read failed: %s", exc)
        return None
