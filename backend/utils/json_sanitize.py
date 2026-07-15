"""Shared JSON-sanitization for payloads headed into json.dumps().

Consolidates three previously-duplicated implementations (database/redis_client.py,
websocket/broadcaster.py, database/postgres_client.py) into one. The Redis/
WebSocket copies only handled numpy scalars; postgres_client.py's also handled
datetime/Decimal -- which is why persistence silently succeeded while
cache_signal()/broadcast_signal_smart() threw "Object of type datetime is not
JSON serializable" for any signal carrying a raw datetime (e.g.
signals/pipeline.py's expires_at field, set on every signal via
calculate_expiry()). Found during the S-1 F-4 crypto cutover's live
verification, 2026-07-15 -- see docs/strategy-reviews/stater-swap-redesign/
s1-phase4-findings.md.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert a payload into JSON-serializable values."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)

    # Handle numpy-like scalars without importing numpy directly.
    type_name = f"{type(obj).__module__}.{type(obj).__name__}".lower()
    if "numpy" in type_name:
        if "bool" in type_name:
            return bool(obj)
        if "int" in type_name:
            return int(obj)
        if "float" in type_name:
            return float(obj)
        if hasattr(obj, "tolist"):
            try:
                return obj.tolist()
            except Exception:
                return str(obj)
    return obj
