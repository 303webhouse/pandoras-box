"""Read-only options flow accessors.

flow_radar.get_flow_radar is a pure read (Redis SCAN + Postgres SELECT only).
We import the specific function and call it directly to reuse its existing
aggregation logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from api.flow_radar import get_flow_radar as _api_get_flow_radar

logger = logging.getLogger(__name__)


async def get_flow_radar() -> Optional[Dict[str, Any]]:
    """Return the flow radar payload or None if the underlying fetch fails."""
    try:
        return await _api_get_flow_radar()
    except Exception as exc:
        logger.warning("flow radar read failed: %s", exc)
        return None
