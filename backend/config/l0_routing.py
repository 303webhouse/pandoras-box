"""L0.1a — signal_type suppression gate (SHADOW).

A single declarative gate, keyed on `signal_type`, that decides KEEP vs
SUPPRESS for each signal. It runs at the top of `process_signal_unified`
(the universal chokepoint) so every scanner/webhook path is covered by one
rule table instead of scattered per-scanner `if`s.

SHADOW vs ENFORCE
-----------------
This module computes the KEEP/SUPPRESS decision and tags it (under
`triggering_factors.l0_shadow`); it NEVER drops or alters persistence — the
audit trail + outcome grading continue for suppressed rows. ENFORCE is now the
default (2026-07-03 flip, after a >=2-week shadow window + Nick/Claude greenlight):
actionable READ surfaces exclude would_suppress rows via l0_enforce_where_clause()
(surface-suppression). `L0_ENFORCE=false` is the single-flag rollback to shadow.

Routing keys on `signal_type`, NOT `strategy`
---------------------------------------------
The casual name "Holy Grail" is the *strategy*; the suppress targets are the
*signal_types* `HOLY_GRAIL_1H` / `HOLY_GRAIL_15M`. A gate keyed on the
strategy string would match the wrong rows.

Source of verdicts (the docs are truth, not memory):
  - `docs/strategy-reviews/holy-grail-gate-test-2026-06-16.md` (KILL)
  - `docs/strategy-reviews/cta-artemis-decompose-and-uw-era-2026-06-16.md`
    (route CTA by signal_type; RESISTANCE_REJECTION liquid-only)
  - `docs/codex-briefs/2026-06-17-L0-session1-cc-launch-brief.md` §T2

Scope note (Phase-0 2026-06-17): the equity scanners (Holy Grail, CTA) route
through `process_signal_unified`, so this gate covers them. The crypto scanner
(`bias_scheduler.py` crypto path) writes via `log_signal` directly and is NOT
covered — by design: its `PULLBACK_ENTRY` population (strategy='Crypto
Scanner') was never in the -0.25 equity analysis. Whether crypto PULLBACK_ENTRY
should be suppressed is an explicit decision for the enforce brief.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from config.liquid_universe import is_liquid

# Decision schema version — bump if the tag shape changes (for query stability).
L0_SHADOW_VERSION = 1

# Rule labels written into the tag.
RULE_KEEP = "KEEP"
RULE_SUPPRESS = "SUPPRESS"
RULE_SUPPRESS_IF_NON_LIQUID = "SUPPRESS_IF_NON_LIQUID"

# signal_types suppressed unconditionally (every timeframe / direction).
SUPPRESS_ALWAYS: frozenset[str] = frozenset({
    "HOLY_GRAIL_1H",   # Holy_Grail — KILL confirmed (negative every regime)
    "HOLY_GRAIL_15M",  # Holy_Grail — KILL confirmed
    "PULLBACK_ENTRY",  # CTA Scanner — high-vol bleeder (-0.25)
    "TRAPPED_LONGS",   # CTA Scanner — -2.54
    "ARTEMIS_LONG",    # Artemis — no-long-edge (-0.11 alpha n=1,118; score>=80 slice -0.52%);
                       # named eviction candidate, cta-artemis-decompose 2026-06-16.
                       # ARTEMIS_SHORT stays live (salvageable-marginal, +0.04).
})

# signal_types suppressed ONLY when the ticker is not in the liquid universe.
SUPPRESS_IF_NON_LIQUID: frozenset[str] = frozenset({
    "RESISTANCE_REJECTION",  # +0.73 liquid (KEEP) / -1.76 single-name (SUPPRESS)
})

# Everything not named above is KEPT untouched (GOLDEN_TOUCH, TRAPPED_SHORTS,
# TWO_CLOSE_VOLUME, APIS_CALL, sell_the_rip*, ARTEMIS_SHORT, footprint, etc.).


def _enforce_enabled() -> bool:
    """Read the L0_ENFORCE flag (default True = ENFORCE as of 2026-07-03).

    L0.1a enforcement is now the default; `L0_ENFORCE=false` (or 0/no/off) is the
    single-flag rollback to shadow. Empty-safe pattern `getenv(...) or default`:
    Railway returns '' (not None) for unset refs, so an empty/unset value defaults
    to ENFORCE (the intended live state) — the rollback must be an EXPLICIT false.
    """
    raw = (os.getenv("L0_ENFORCE") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


# Module-level snapshot for cheap reads; tests/callers can also call
# _enforce_enabled() directly. Default True (2026-07-03 flip) = enforce live.
L0_ENFORCE: bool = _enforce_enabled()


def evaluate_l0_gate(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the L0.1a suppression decision for one signal.

    Pure / side-effect-free: reads `signal_type` and `ticker`, returns the
    decision dict to be tagged under `triggering_factors.l0_shadow`. Does NOT
    mutate `signal_data` and NEVER drops/diverts (that is the caller's job, and
    only under a future enforce flip).
    """
    signal_type = (signal_data.get("signal_type") or "").strip()
    ticker = signal_data.get("ticker")

    rule = RULE_KEEP
    would_suppress = False
    liquid: Optional[bool] = None
    reason = "not in any suppress set"

    if signal_type in SUPPRESS_ALWAYS:
        rule = RULE_SUPPRESS
        would_suppress = True
        reason = "signal_type in unconditional suppress set"
    elif signal_type in SUPPRESS_IF_NON_LIQUID:
        rule = RULE_SUPPRESS_IF_NON_LIQUID
        liquid = is_liquid(ticker)
        would_suppress = not liquid
        reason = (
            "liquid → keep" if liquid else "non-liquid → suppress"
        )

    return {
        "v": L0_SHADOW_VERSION,
        "mode": "enforce" if L0_ENFORCE else "shadow",
        "signal_type": signal_type,
        "rule": rule,
        "would_suppress": would_suppress,
        "is_liquid": liquid,
        "reason": reason,
    }


def should_divert(decision: Dict[str, Any]) -> bool:
    """Whether a signal should actually be diverted (enforce-only).

    SHADOW → always False. Provided for the future enforce brief; this session
    never calls it in a way that drops a signal.
    """
    return bool(decision.get("would_suppress")) and _enforce_enabled()


# ── L0.1a ENFORCE (2026-07-02 flip brief) ────────────────────────────
# Surface-suppression: keep persisting + grading suppressed signals (audit trail),
# but EXCLUDE them from actionable read surfaces when L0_ENFORCE=true. The filter
# keys on the recorded l0_shadow TAG (`would_suppress`), NOT the live signal_type
# column: signal_type can drift after gate eval (a Holy_Grail signal relabeled
# APIS_CALL keeps its correct SUPPRESS tag), and the tag is exactly what the
# ≥2-week "zero keepers lost" shadow window validated. Rows with no tag
# (pre-gate history, the crypto path that bypasses the chokepoint) COALESCE to keep.
_L0_SUPPRESS_PREDICATE = (
    "COALESCE((triggering_factors->'l0_shadow'->>'would_suppress')::boolean, false) = false"
)


def l0_enforce_where_clause() -> str:
    """WHERE-fragment (no leading AND) that EXCLUDES gate-suppressed rows from
    actionable feeds when enforcing; '' (no-op) in shadow mode. Static string —
    safe to concatenate into a signals query (no user input, no params)."""
    return _L0_SUPPRESS_PREDICATE if _enforce_enabled() else ""


def _row_would_suppress(row: Any) -> bool:
    """True iff a signal dict carries an l0_shadow tag with would_suppress=true.
    Tolerates triggering_factors as a dict OR a JSON string (Redis payloads
    serialize it as text). Mirrors _L0_SUPPRESS_PREDICATE's keep/drop logic:
    a missing tag/field COALESCEs to keep (returns False)."""
    if not isinstance(row, dict):
        return False
    tf = row.get("triggering_factors")
    if isinstance(tf, str):
        try:
            import json as _json
            tf = _json.loads(tf)
        except (ValueError, TypeError):
            return False
    if not isinstance(tf, dict):
        return False
    l0 = tf.get("l0_shadow")
    if not isinstance(l0, dict):
        return False
    return bool(l0.get("would_suppress"))


def l0_enforce_filter_rows(rows):
    """Python-side twin of l0_enforce_where_clause() for feeds that don't hit a
    SQL WHERE — e.g. the Redis-cached queue path. Drops gate-suppressed rows when
    enforcing; pass-through (no-op) in shadow mode. Fail-safe: non-list → unchanged."""
    if not _enforce_enabled() or not isinstance(rows, list):
        return rows
    return [r for r in rows if not _row_would_suppress(r)]


async def l0_status(pool) -> Dict[str, Any]:
    """E3 enforcement visibility: {enforce, suppressed_today}. Read-only,
    fail-safe. Makes enforcement observable — quiet success and quiet failure
    look identical without a counter (the Triton Bug-1 lesson)."""
    enabled = _enforce_enabled()
    suppressed_today: Optional[int] = None
    try:
        if pool:
            async with pool.acquire() as conn:
                suppressed_today = await conn.fetchval(
                    "SELECT COUNT(*) FROM signals "
                    "WHERE created_at >= CURRENT_DATE AND "
                    "COALESCE((triggering_factors->'l0_shadow'->>'would_suppress')::boolean, false)"
                )
    except Exception:
        pass
    return {"enforce": enabled, "suppressed_today": suppressed_today}
