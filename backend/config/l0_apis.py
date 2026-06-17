"""L0.3 — APIS_CALL label gating (shadow-first, behind a flag).

The APIS_CALL label is applied at two LIVE sites when a LONG signal scores >= 85
(verified 2026-06-17): `signals/pipeline.py` (in apply_scoring) and
`api/positions.py` (the re-score path). Its edge is non-liquid-only, so this
module decides — gated by `L0_APIS_ENFORCE` — whether the APIS label should be
applied for a given ticker.

SHADOW vs ENFORCE
-----------------
`L0_APIS_ENFORCE` defaults to False:
  - False (shadow/default): `apply_apis_label()` ALWAYS returns True →
    behavior is UNCHANGED from today (APIS applies exactly as before).
  - True (enforce): APIS applies only when the ticker is `apis_eligible`
    (i.e. non-liquid); on liquid tickers the label is withheld and the
    original signal_type is preserved.

This namespace is independent of L0.1a's `L0_ENFORCE` so each gate flips on its
own validated window. KODIAK_CALL is NOT gated (zero liquid fires — a no-op).

Validation is retrospective (scripts/l0_apis_measure.py) — the gate logic is
trivial and unit-tested; no live shadow tag is needed.
"""

from __future__ import annotations

import os
from typing import Optional

from config.liquid_universe import apis_eligible


def _apis_enforce_enabled() -> bool:
    """Read L0_APIS_ENFORCE (default False = shadow).

    Empty-safe per the repo pattern: `getenv(...) or default` (Railway returns
    '' for unset refs, not None).
    """
    raw = (os.getenv("L0_APIS_ENFORCE") or "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


# Module-level snapshot for cheap reads; default-False intent is explicit.
L0_APIS_ENFORCE: bool = _apis_enforce_enabled()


def apply_apis_label(ticker: Optional[str]) -> bool:
    """Whether the APIS_CALL label should be applied for `ticker`.

    Shadow (flag off) → always True (unchanged behavior). Enforce (flag on) →
    True only when the ticker is APIS-eligible (non-liquid). Reads the env each
    call so an enforce flip takes effect without re-import.
    """
    if not _apis_enforce_enabled():
        return True
    return apis_eligible(ticker)
