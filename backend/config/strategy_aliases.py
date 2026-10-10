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

ICARUS (corrected, R-IV.843(e)): the name belongs to the on-screen setup
"ICARUS | Fade VAH" (`frontend/v2.js` SETUP_MAP). An earlier note here called it
a "0DTE SPY scalp": that was a 2026-06-10 shadow brief
(`docs/codex-briefs/2026-06-10-icarus-shadow-signal.md`, a B3 0DTE SPY signal off
PYTHIA ib_break events), Titans-approved and build-gated, and never built -- no
backend code implements it. The name does not refer to it.

THE NAME REGISTRY (R-IV.843(e)) -- this file is the ONE author of names.
  - `REGISTRY` maps raw identifiers to "CODENAME | Description" (principal-approved
    2026-10-09). `display_label()` serves it; `attach_codename()` stamps it.
  - APIS / KODIAK are TAGS, not names: an upgraded row's label is its BASE type's,
    with `upgrade_tag` beside it. The base comes from `triggering_factors.upgraded_from`
    (new rows) or `triggering_factors.l0_shadow.signal_type` (historical rows).
  - The legacy `codename()` map below is kept for its readers (strategy_class's
    roster test, Discord, the trade-ideas feed, the MCP tool, app.js). It is
    deliberately NOT widened to the new names: widening it would change what those
    screens show before the principal approves ABACUS's mockup. A test holds every
    overlapping entry to the registry's name.
  - ODYSSEUS is reserved by the principal and used nowhere.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

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
    # NEMESIS_LONG is what the CODED WRR writes today (strategies/wrr_buy_model.py:159):
    # that strategy is PHOENIX (R-IV.843(e)), not the March spec. NEMESIS_SHORT stays a
    # pre-map for the March spec, which no code implements.
    "NEMESIS_LONG": "Phoenix",
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
    "nemesis_wrr": "Phoenix",
}


# ── THE NAME REGISTRY (R-IV.843(e)) ─────────────────────────────────────────
# (CODENAME, Description, signal_types, strategies). signal_types match exactly
# (case-insensitive) and win over strategies. Suppressed types (PULLBACK_ENTRY,
# TRAPPED_LONGS, HOLY_GRAIL_*, ARTEMIS_LONG, STRIKE_IB_BREAK) need no name until
# unsuppressed; WH_ACCUMULATION and DARK_POOL take the fallback until named.
# Crypto is out of scope.
REGISTRY: Tuple[Tuple[str, str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    ("ACHILLES", "Sell the Rip", ("SELL_RIP_EMA", "SELL_RIP_VWAP", "SELL_RIP_EARLY"), ("sell_the_rip",)),
    ("MIDAS", "Golden Touch", ("GOLDEN_TOUCH",), ()),
    ("HECTOR", "Trapped Shorts", ("TRAPPED_SHORTS",), ()),
    # The March spec, once implemented; its approved types are WRR_LONG / WRR_SHORT.
    ("NEMESIS", "Washout Reversal", ("WRR_LONG", "WRR_SHORT", "NEMESIS_SHORT"), ("nemesis",)),
    # The coded WRR. It writes NEMESIS_LONG / nemesis_wrr today, mapped here on purpose.
    ("PHOENIX", "Uptrend Dip-Buy", ("NEMESIS_LONG",), ("nemesis_wrr",)),
    ("PERSEPHONE", "Two-Close Turn", ("TWO_CLOSE_VOLUME",), ()),
    ("PHAETHON", "Bearish Breakdown", ("BEARISH_BREAKDOWN",), ()),
    # A filter in the CTA scanner, never stored as a signal (cta_scanner.py:1427-1432).
    ("HADES", "Death Cross", ("DEATH_CROSS",), ()),
    ("SISYPHUS", "Resistance Rejection", ("RESISTANCE_REJECTION",), ()),
    # Per the Pine (artemis_v3.pine): a short at the upper VWAP band. ARTEMIS_LONG is
    # suppressed, so the strategy string is NOT mapped -- it would name the long a short.
    ("ARTEMIS", "VWAP Band Short", ("ARTEMIS_SHORT",), ()),
    ("HYPNOS", "Exhaustion Reversal", ("EXHAUSTION_BULL", "EXHAUSTION_BEAR"), ()),
    ("ORION", "Scout Sniper", ("SCOUT_ALERT",), ("scout sniper",)),
    ("AJAX", "Absorption Wall", ("PHALANX_BULL", "PHALANX_BEAR"), ("phalanx",)),
    ("CYCLOPS", "Footprint", ("FOOTPRINT_LONG", "FOOTPRINT_SHORT"), ("footprint_imbalance",)),
    ("PROTEUS", "Whale Reversal", ("WH_REVERSAL",), ("wh-reversal",)),
    ("TRITON", "Whale Hunting", ("WHALE_LONG", "WHALE_SHORT", "WHALE_BULLISH", "WHALE_BEARISH"),
     ("whale_hunter",)),
    ("CIRCE'S STEW", "Fade the Breakout", ("CIRCES_STEW",), ("circes_stew",)),
    # Unchanged on-screen setups (frontend/v2.js SETUP_MAP). No backend emitter writes
    # these identifiers; they resolve by their own key.
    ("ICARUS", "Fade VAH", ("ICARUS",), ()),
    ("HELEN", "Reclaim VA", ("HELEN",), ()),
    ("ARGO", "Range Break + Flow", ("ARGO",), ()),
    ("HERA", "3-10 Oscillator Cross", ("HERA",), ()),
)

_LABEL_BY_SIGNAL_TYPE: Dict[str, str] = {
    st: "%s | %s" % (name, desc) for name, desc, sts, _ in REGISTRY for st in sts
}
_LABEL_BY_STRATEGY: Dict[str, str] = {
    s: "%s | %s" % (name, desc) for name, desc, _, strats in REGISTRY for s in strats
}

# APIS / KODIAK are upgrade TAGS (pipeline.py: score >= 85 relabels the row).
UPGRADE_TAGS: Dict[str, Tuple[str, str]] = {
    "APIS_CALL": ("APIS", "Upgraded Long"),
    "KODIAK_CALL": ("KODIAK", "Upgraded Short"),
}
UNNAMED = "Unnamed Signal"


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


def _factors(triggering_factors: Any) -> Dict[str, Any]:
    """triggering_factors as a dict, whether it arrives as a dict or as JSON text."""
    if isinstance(triggering_factors, dict):
        return triggering_factors
    if isinstance(triggering_factors, str) and triggering_factors.strip():
        try:
            parsed = json.loads(triggering_factors)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def upgrade_tag(signal_type: Optional[str]) -> Optional[str]:
    """"APIS" / "KODIAK" on an upgraded row, else None."""
    tag = UPGRADE_TAGS.get(_norm(signal_type).upper())
    return tag[0] if tag else None


def base_signal_type(signal_type: Optional[str], triggering_factors: Any = None) -> Optional[str]:
    """The type an APIS/KODIAK row was before its upgrade, or None when not recorded.

    `upgraded_from` (written before the overwrite, explicit) wins over
    `l0_shadow.signal_type` (the L0 gate's record, taken before scoring).
    """
    if _norm(signal_type).upper() not in UPGRADE_TAGS:
        return None
    tf = _factors(triggering_factors)
    l0 = tf.get("l0_shadow") if isinstance(tf.get("l0_shadow"), dict) else {}
    for cand in (tf.get("upgraded_from"), l0.get("signal_type")):
        if isinstance(cand, str) and cand.strip() and cand.strip().upper() not in UPGRADE_TAGS:
            return cand.strip()
    return None


def record_upgraded_from(signal: Dict[str, Any]) -> None:
    """Call immediately BEFORE an APIS/KODIAK overwrite: keep the base type, explicitly.

    Writes `triggering_factors.upgraded_from` and nothing else. A row already carrying
    an upgrade type (a rescore of an upgraded row) keeps the base it already recorded.
    """
    if not isinstance(signal, dict):
        return
    current = _norm(signal.get("signal_type"))
    if not current or current.upper() in UPGRADE_TAGS:
        return
    tf = signal.get("triggering_factors")
    if not isinstance(tf, dict):
        tf = _factors(tf)
        signal["triggering_factors"] = tf
    tf.setdefault("upgraded_from", current)


def display_label(signal_type: Optional[str], strategy: Optional[str] = None,
                  triggering_factors: Any = None) -> str:
    """"CODENAME | Description", or a humanized fallback. Never an empty string.

    An APIS/KODIAK row is labelled by its BASE type (see `base_signal_type`); with no
    recorded base it reads "APIS | Upgraded Long (type not recorded)".
    """
    st = _norm(signal_type).upper()
    if st in UPGRADE_TAGS:
        base = base_signal_type(signal_type, triggering_factors)
        if base is None:
            tag, desc = UPGRADE_TAGS[st]
            return "%s | %s (type not recorded)" % (tag, desc)
        return display_label(base, strategy)
    if st and st in _LABEL_BY_SIGNAL_TYPE:
        return _LABEL_BY_SIGNAL_TYPE[st]
    strat = _norm(strategy).lower()
    if strat and strat in _LABEL_BY_STRATEGY:
        return _LABEL_BY_STRATEGY[strat]
    raw = _norm(signal_type) or _norm(strategy)
    return _humanize(raw) if raw else UNNAMED


def attach_codename(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Additively set `codename`, `display_label` and `upgrade_tag`, in place.

    `codename` is the legacy field, unchanged for its readers. Never mutates
    `signal_type` / `strategy`. Returns the same dict for chaining.
    """
    if isinstance(signal, dict):
        st, strat = signal.get("signal_type"), signal.get("strategy")
        signal["codename"] = codename(st, strat)
        signal["display_label"] = display_label(st, strat, signal.get("triggering_factors"))
        signal["upgrade_tag"] = upgrade_tag(st)
    return signal
