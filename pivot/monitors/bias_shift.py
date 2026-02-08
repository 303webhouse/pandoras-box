"""
Detect composite bias level transitions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from collectors.base_collector import get_json

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parents[1] / "state" / "bias_shift.json"


def _load_state() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(data: Dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


async def check_bias_shift() -> Optional[Dict[str, Any]]:
    try:
        composite = await get_json("/bias/composite")
    except Exception as exc:
        logger.warning(f"Bias shift check failed: {exc}")
        return None

    current = composite.get("bias_level")
    score = composite.get("composite_score")
    timestamp = composite.get("timestamp") or datetime.utcnow().isoformat()

    if not current:
        return None

    state = _load_state()
    previous = state.get("bias_level")

    if previous != current:
        state["bias_level"] = current
        state["updated_at"] = timestamp
        _save_state(state)
        return {
            "type": "bias_shift",
            "previous": previous,
            "current": current,
            "score": score,
            "timestamp": timestamp,
        }

    return None
