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

2026-08-20 -- DEF-SIGNAL-PERSISTENCE-COLLAPSE (P0). This module previously had
NO non-finite branch: a float('nan') fell through to `return obj`, and a numpy
NaN was *converted* to a Python NaN. json.dumps then emitted the bare tokens
NaN / Infinity / -Infinity, which are valid JavaScript and INVALID JSON, so
Postgres rejected the bind with `invalid input syntax for type json`. The
exception was swallowed upstream and the pipeline reported success, costing 459
signals over 2026-08-18/19. Non-finite values now become null and are reported;
never zero, never silent (GREEKS-ZERO precedent). dumps_jsonb() is the single
chokepoint every JSONB bind must use.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Attached to a sanitized dict when any non-finite value was coerced to null.
NONFINITE_MARKER = "_degraded_nonfinite"


def _coerce_float(value: Any, path: str, degraded: list[str]) -> float | None:
    """Single funnel for EVERY float-producing conversion.

    A2: isfinite is tested AFTER conversion, so numpy/Decimal/any future
    converting branch inherits the check rather than bypassing it.
    """
    f = float(value)
    if not math.isfinite(f):
        degraded.append(path or "<root>")
        return None
    return f


def sanitize_for_json(obj: Any, _path: str = "", _degraded: list[str] | None = None) -> Any:
    """Recursively convert a payload into JSON-serializable values.

    Non-finite floats (NaN / Infinity / -Infinity) become None; their dotted
    paths are collected into _degraded. Callers that pass no _degraded keep the
    original one-argument signature and simply get the nulls.
    """
    degraded = [] if _degraded is None else _degraded

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # Keys are sanitized too: a non-finite float key reaches json.dumps as a
            # bare token exactly like a value would, and allow_nan=False then raises.
            if isinstance(k, float) and not math.isfinite(k):
                degraded.append(f"{_path}.<key {k!r}>" if _path else f"<key {k!r}>")
                k = repr(k)
            kp = f"{_path}.{k}" if _path else str(k)
            out[k] = sanitize_for_json(v, kp, degraded)
        return out
    if isinstance(obj, (list, tuple)):
        return [
            sanitize_for_json(item, f"{_path}[{i}]", degraded)
            for i, item in enumerate(obj)
        ]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, float):
        return _coerce_float(obj, _path, degraded)
    if isinstance(obj, Decimal):
        return _coerce_float(obj, _path, degraded)

    # Handle numpy-like scalars without importing numpy directly.
    type_name = f"{type(obj).__module__}.{type(obj).__name__}".lower()
    if "numpy" in type_name:
        if "bool" in type_name:
            return bool(obj)
        if "int" in type_name:
            return int(obj)
        if "float" in type_name:
            return _coerce_float(obj, _path, degraded)
        if hasattr(obj, "tolist"):
            try:
                return sanitize_for_json(obj.tolist(), _path, degraded)
            except Exception:
                return str(obj)
    return obj


def dumps_jsonb(obj: Any, *, marker: bool = True, **kwargs: Any) -> str:
    """THE chokepoint for every JSONB bind in the backend.

    Non-finite floats become null. Their paths are logged UNCONDITIONALLY, whatever
    the root type (A1), and are attached to the payload as NONFINITE_MARKER when the
    root is a dict AND marker=True.

    marker=False is for MAP-SHAPED payloads -- objects whose keys are domain entities
    (sector -> exposure, factor_id -> score) and which are read back and returned
    verbatim over HTTP. Injecting the marker there would invent a phantom entity in
    an API response. Degradation is still logged; it just is not smuggled into a map.

    **kwargs pass through to json.dumps (default=, indent=, sort_keys=, ...), EXCEPT
    allow_nan, which is LOCKED False and non-overridable: it is the assertion that a
    bare NaN/Infinity token can never be emitted, and a caller must not be able to
    switch the guard off.
    """
    kwargs.pop("allow_nan", None)  # locked -- callers may not re-enable bare tokens
    degraded: list[str] = []
    clean = sanitize_for_json(obj, _degraded=degraded)
    if degraded:
        logger.warning(
            "jsonb: %d non-finite value(s) coerced to null: %s",
            len(degraded),
            ", ".join(degraded[:20]),
        )
        if marker and isinstance(clean, dict):
            clean[NONFINITE_MARKER] = degraded
    return json.dumps(clean, allow_nan=False, **kwargs)
