"""
Detect rapid factor score changes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from collectors.base_collector import get_json

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parents[1] / "state" / "factor_velocity.json"
THRESHOLD = 0.3


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


async def check_factor_velocity() -> List[Dict[str, Any]]:
    try:
        composite = await get_json("/bias/composite")
    except Exception as exc:
        logger.warning(f"Factor velocity check failed: {exc}")
        return []

    factors = composite.get("factors", {}) or {}
    now = datetime.utcnow().isoformat()

    state = _load_state()
    previous_scores = state.get("scores", {})
    changes: List[Dict[str, Any]] = []

    for factor_id, reading in factors.items():
        if not reading:
            continue
        score = reading.get("score")
        if score is None:
            continue
        prev = previous_scores.get(factor_id)
        if prev is not None:
            delta = float(score) - float(prev)
            if abs(delta) >= THRESHOLD:
                changes.append({
                    "factor": factor_id,
                    "previous": prev,
                    "current": score,
                    "delta": delta,
                })

    state["scores"] = {fid: reading.get("score") for fid, reading in factors.items() if reading}
    state["updated_at"] = now
    _save_state(state)

    return changes
