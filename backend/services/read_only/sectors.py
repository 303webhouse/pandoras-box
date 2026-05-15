"""Read-only sector strength / rotation accessors.

Sources cached 11-sector rotation data computed by the bias_filters
scheduler. Read-only — the writer (`refresh_sector_rotation`) is owned
by the scheduler and never invoked from this module.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from bias_filters.sector_momentum import get_cached_rotation

logger = logging.getLogger(__name__)


async def get_sector_rotation() -> Optional[Dict[str, Dict[str, Any]]]:
    """Return per-sector rotation data keyed by sector name, or None."""
    try:
        return await get_cached_rotation()
    except Exception as exc:
        logger.warning("sector rotation read failed: %s", exc)
        return None
