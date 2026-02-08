"""
Detect CTA zone changes on watchlist tickers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from collectors.base_collector import get_json

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parents[1] / "state" / "cta_zones.json"


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


async def check_cta_zones() -> List[Dict[str, Any]]:
    try:
        flat = await get_json("/watchlist/flat?limit=500")
    except Exception as exc:
        logger.warning(f"CTA zone check failed: {exc}")
        return []

    tickers = flat.get("tickers", []) if isinstance(flat, dict) else []
    current_zones = {t.get("symbol"): t.get("cta_zone") for t in tickers if t.get("symbol")}

    state = _load_state()
    previous = state.get("zones", {})

    changes: List[Dict[str, Any]] = []
    for symbol, zone in current_zones.items():
        prev = previous.get(symbol)
        if zone != prev and zone is not None:
            changes.append({
                "ticker": symbol,
                "previous": prev,
                "current": zone,
            })

    state["zones"] = current_zones
    state["updated_at"] = datetime.utcnow().isoformat()
    _save_state(state)

    return changes
