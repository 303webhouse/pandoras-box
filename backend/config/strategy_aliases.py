"""L0.4 — strategy alias / codename DISPLAY layer.

The single canonical map from raw DB identifiers (`signal_type` / `strategy`)
to the rebuild-roster codenames (Midas / Achilles / Hector / Apis / Kodiak /
Triton / Nemesis / Icarus).

CRITICAL — this is an ADDITIVE display layer, NOT a mutation. The raw
`signal_type` / `strategy` values stay frozen everywhere: outcome history, the
n-gates, CSS classes, feed filters, and committee branching all key on the raw
strings (e.g. `pivot2_committee.classify_signal_source` branches on
`"ZONE" in signal_type`, `TV_WHALE_STRATEGIES`, etc.). Mutating the raw values
would orphan history and break that logic. So every consumer ADDS a `codename`
alongside the raw fields; nothing replaces them.

Source of the map: `docs/codex-briefs/2026-06-16-rebuild-stack-master-brief.md`
§11 naming roster + parent brief §L0.4.

Precedence (codename()):
  1. signal_type-keyed match (most specific)
  2. strategy-keyed match (covers multi-signal_type families, e.g. all
     SELL_RIP_* under strategy `sell_the_rip` → Achilles)
  3. unmapped → None  (callers fall back to the existing display formatting;
     returning None — not the raw string — is deliberate so the frontend's
     `signal.codename || formatSignalType(...)` prefer-pattern degrades to the
     richer JS formatter instead of surfacing a raw UPPER_SNAKE value)

Two public lookups:
  - codename(signal_type, strategy) -> Optional[str]   (branded name or None)
  - display_name(signal_type, strategy) -> str         (codename or humanized
        raw fallback; for Python-only surfaces with no JS formatter — Discord,
        notifier, committee prompts)

NOTE — Icarus (0DTE SPY scalp) has no discoverable underlying signal_type /
strategy identifier in the codebase as of 2026-06-17; it is intentionally left
unmapped (falls through to display_name's humanized fallback) until its
identifier is confirmed. L2 names (Triton/Nemesis) are pre-mapped so they are
ready when those strategies emit.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# signal_type (UPPER) → codename. Most specific; checked first.
CODENAME_BY_SIGNAL_TYPE: Dict[str, str] = {
    "GOLDEN_TOUCH": "Midas",
    "TRAPPED_SHORTS": "Hector",
    "APIS_CALL": "Apis",
    "KODIAK_CALL": "Kodiak",
    # Achilles family — also covered by the strategy map, listed here so a row
    # carrying only signal_type still resolves.
    "SELL_RIP_EMA": "Achilles",
    "SELL_RIP_VWAP": "Achilles",
    "SELL_RIP_EARLY": "Achilles",
    # L2 (pre-mapped, ready for emit)
    "NEMESIS_LONG": "Nemesis",
    "NEMESIS_SHORT": "Nemesis",
    "WHALE_LONG": "Triton",
    "WHALE_SHORT": "Triton",
    "WHALE_BULLISH": "Triton",
    "WHALE_BEARISH": "Triton",
}

# strategy (lower) → codename. Checked after signal_type. Covers families where
# one strategy spans several signal_types.
CODENAME_BY_STRATEGY: Dict[str, str] = {
    "sell_the_rip": "Achilles",
    "whale_hunter": "Triton",
    "nemesis": "Nemesis",
    "nemesis_wrr": "Nemesis",
}


def _norm(value: Optional[str]) -> str:
    return value.strip() if value else ""


def codename(signal_type: Optional[str], strategy: Optional[str] = None) -> Optional[str]:
    """Return the roster codename for a signal, or None if unmapped.

    Precedence: signal_type (exact, case-insensitive) → strategy
    (case-insensitive) → None. Pure / side-effect-free.
    """
    st = _norm(signal_type).upper()
    if st and st in CODENAME_BY_SIGNAL_TYPE:
        return CODENAME_BY_SIGNAL_TYPE[st]

    strat = _norm(strategy).lower()
    if strat and strat in CODENAME_BY_STRATEGY:
        return CODENAME_BY_STRATEGY[strat]

    return None


def _humanize(raw: str) -> str:
    """Title-case an UPPER_SNAKE / kebab raw identifier for fallback display."""
    return raw.replace("_", " ").replace("-", " ").strip().title()


def display_name(signal_type: Optional[str], strategy: Optional[str] = None) -> str:
    """Codename if mapped, else a humanized fallback from the raw identifiers.

    For surfaces with no JS display formatter (Discord, notifier, committee
    prompts). Never returns an empty string unless both inputs are blank.
    """
    cn = codename(signal_type, strategy)
    if cn:
        return cn
    raw = _norm(signal_type) or _norm(strategy)
    return _humanize(raw) if raw else ""


def attach_codename(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Additively set `signal['codename']` from its raw fields, in place.

    Sets the key to the codename or None (JSON null) — never mutates
    `signal_type` / `strategy`. Returns the same dict for chaining.
    """
    if isinstance(signal, dict):
        signal["codename"] = codename(signal.get("signal_type"), signal.get("strategy"))
    return signal
