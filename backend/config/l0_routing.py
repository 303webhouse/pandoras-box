"""L0.1a — signal_type suppression gate (SHADOW).

A single declarative gate, keyed on `signal_type`, that decides KEEP vs
SUPPRESS for each signal. It runs at the top of `process_signal_unified`
(the universal chokepoint) so every scanner/webhook path is covered by one
rule table instead of scattered per-scanner `if`s.

SHADOW vs ENFORCE
-----------------
This module ONLY computes a decision and lets the caller TAG it (under
`triggering_factors.l0_shadow`). It never drops, diverts, or alters signal
flow. The `L0_ENFORCE` flag (default False) is the single switch a future,
separately-gated enforce brief will flip; the actual divert wiring is NOT
built here on purpose (see the L0 foundation brief — enforce is a distinct
step, gated on a ≥1-week shadow window + greenlight).

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
})

# signal_types suppressed ONLY when the ticker is not in the liquid universe.
SUPPRESS_IF_NON_LIQUID: frozenset[str] = frozenset({
    "RESISTANCE_REJECTION",  # +0.73 liquid (KEEP) / -1.76 single-name (SUPPRESS)
})

# Everything not named above is KEPT untouched (GOLDEN_TOUCH, TRAPPED_SHORTS,
# TWO_CLOSE_VOLUME, APIS_CALL, sell_the_rip*, Artemis*, footprint, etc.).


def _enforce_enabled() -> bool:
    """Read the L0_ENFORCE flag (default False = shadow).

    Follows the repo's empty-safe env pattern: `getenv(...) or default`, since
    Railway returns '' (not None) for unset refs.
    """
    raw = (os.getenv("L0_ENFORCE") or "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


# Module-level snapshot for cheap reads; tests/callers can also call
# _enforce_enabled() directly. Kept as a function-backed constant so the
# default-False intent is obvious at import.
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
