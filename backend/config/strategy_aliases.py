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


# ── R-IV.833, authored under R-IV.925(b) ──────────────────────────────────────────────────────
#
# `display_label` = "CODENAME | Short description", and `upgrade_tag` = "APIS" / "KODIAK" / absent.
#
# THE DESCRIPTION IS READ FROM THE CARD, NOT COPIED INTO THIS FILE. `docs/strategies/*.md` already
# opens with exactly the shape the ruling asks for -- "# HECTOR | Trapped Shorts (`TRAPPED_SHORTS`)"
# -- so the card is the one author of a strategy's description, and this module derives the label
# instead of keeping a second copy that would drift the first time a card is reworded. That is why
# the ruling specifies a no-card fallback: with no card there is nothing to read, and the label is
# the codename alone.
#
# If `docs/` is absent at runtime (a slimmer image, a different working directory), every label
# degrades to codename-only -- which IS the ruled fallback, so the failure mode is specified
# rather than surprising. It is logged once so the degradation is visible and not merely quiet.

import logging as _logging
import os as _os
import re as _re

_log = _logging.getLogger("strategy_aliases")

# "# CODENAME | Description (`TYPE_A`, `TYPE_B`)" -> codename, description
_CARD_TITLE = _re.compile(r"^#\s+([A-Z][A-Z'’ ]{1,30}?)\s*\|\s*(.+?)\s*$")

_CARDS_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "docs", "strategies")

_DESCRIPTION_BY_CODENAME: Optional[Dict[str, str]] = None


def _strip_trailing_refs(text: str) -> str:
    """Drop a trailing parenthetical that only lists signal types or a short reference.

    "Trapped Shorts (TRAPPED_SHORTS in backticks)" -> "Trapped Shorts". A parenthetical with real
    prose is LEFT ALONE: deciding that some of a card's own description is surplus is an editorial
    judgement, and the ruling says the description is the card's, not mine.
    """
    out = text.strip()
    m = _re.search(r"\s*\(([^()]*)\)\s*$", out)
    while m:
        inner = m.group(1)
        looks_like_refs = bool(_re.fullmatch(r"[`A-Z0-9_,/\s.\-]+", inner)) and len(inner) <= 60
        if not looks_like_refs:
            break
        out = out[:m.start()].strip()
        m = _re.search(r"\s*\(([^()]*)\)\s*$", out)
    return out.strip(" .")


def _load_card_descriptions() -> Dict[str, str]:
    """{CODENAME: description} from the cards' title lines. Never raises."""
    found: Dict[str, str] = {}
    try:
        names = sorted(n for n in _os.listdir(_CARDS_DIR) if n.endswith(".md"))
    except OSError:
        _log.info("[strategy_aliases] no %s — every display_label degrades to the codename "
                  "alone, which is R-IV.925(b)'s specified fallback", _CARDS_DIR)
        return found
    for name in names:
        try:
            with open(_os.path.join(_CARDS_DIR, name), encoding="utf-8", errors="ignore") as fh:
                first = fh.readline()
        except OSError:
            continue
        m = _CARD_TITLE.match(first.strip())
        if not m:
            continue                      # not a strategy card (e.g. a definition note)
        found[m.group(1).strip().upper()] = _strip_trailing_refs(m.group(2))
    return found


def card_descriptions() -> Dict[str, str]:
    global _DESCRIPTION_BY_CODENAME
    if _DESCRIPTION_BY_CODENAME is None:
        _DESCRIPTION_BY_CODENAME = _load_card_descriptions()
    return _DESCRIPTION_BY_CODENAME


def reset_card_cache_for_tests() -> None:
    global _DESCRIPTION_BY_CODENAME, _CODENAME_BY_CARD_TYPE
    _DESCRIPTION_BY_CODENAME = None
    _CODENAME_BY_CARD_TYPE = None


_CODENAME_BY_CARD_TYPE: Optional[Dict[str, str]] = None


def card_codenames() -> Dict[str, str]:
    """{SIGNAL_TYPE: CODENAME} read from the cards' own title lines.

    WHY THIS EXISTS. Seven of the eleven cards name a codename that `CODENAME_BY_SIGNAL_TYPE`
    does not map any type to -- ARTEMIS, CIRCE'S STEW, HYPNOS, PERSEPHONE, PHAETHON, PHOENIX,
    SISYPHUS. Their types therefore fell through to the humanised fallback and produced labels
    like "Wrr Long" and "Circes Stew" instead of the card's own name.

    This is NOT inventing a label. Each card title states the pairing itself --
    "# PHAETHON | Bearish Breakdown (`BEARISH_BREAKDOWN`)" -- so the codename, the description
    AND which types they belong to are all the card's, read rather than authored. It is used
    only as a FALLBACK after `codename()`, so the existing hardcoded map stays authoritative and
    nothing that works today changes.
    """
    global _CODENAME_BY_CARD_TYPE
    if _CODENAME_BY_CARD_TYPE is not None:
        return _CODENAME_BY_CARD_TYPE
    out: Dict[str, str] = {}
    try:
        names = sorted(n for n in _os.listdir(_CARDS_DIR) if n.endswith(".md"))
    except OSError:
        _CODENAME_BY_CARD_TYPE = out
        return out
    for name in names:
        try:
            with open(_os.path.join(_CARDS_DIR, name), encoding="utf-8", errors="ignore") as fh:
                first = fh.readline().strip()
        except OSError:
            continue
        m = _CARD_TITLE.match(first)
        if not m:
            continue
        cn = m.group(1).strip()
        for t in _re.findall(r"`([A-Z][A-Z0-9_]{2,})`", m.group(2)):
            out.setdefault(t.upper(), cn)
    _CODENAME_BY_CARD_TYPE = out
    return out


def display_label(signal_type: Optional[str], strategy: Optional[str] = None) -> str:
    """"CODENAME | Short description", or the codename alone when the card has none.

    No pipe when there is no description -- a dangling separator would read as a missing value
    rather than an absent one.
    """
    # The hardcoded map first, then the card's own pairing, then the humanised fallback. Order
    # matters: the existing map stays authoritative so nothing that works today changes.
    cn = (codename(signal_type, strategy)
          or card_codenames().get(_norm(signal_type).upper())
          or display_name(signal_type, strategy))
    if not cn:
        return ""
    desc = card_descriptions().get(cn.strip().upper())
    return "%s | %s" % (cn, desc) if desc else cn


def upgrade_tag(signal_type: Optional[str], strategy: Optional[str] = None) -> Optional[str]:
    """"APIS" for APIS_* types, "KODIAK" for KODIAK_* types, otherwise None.

    Keyed on the SIGNAL TYPE's prefix exactly as ruled, and on the type only -- not the strategy
    -- so a strategy that happens to emit one of these types cannot tag its other types too.
    """
    t = _norm(signal_type).upper()
    if t.startswith("APIS_"):
        return "APIS"
    if t.startswith("KODIAK_"):
        return "KODIAK"
    return None


def attach_label_fields(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Additively set `display_label` and `upgrade_tag`, in place. Returns the same dict."""
    if isinstance(signal, dict):
        st, sg = signal.get("signal_type"), signal.get("strategy")
        signal["display_label"] = display_label(st, sg)
        signal["upgrade_tag"] = upgrade_tag(st, sg)
    return signal
