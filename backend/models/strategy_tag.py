"""The one author of the strategy_tag vocabulary — R-IV.624(d)2.

`unified_positions.strategy_tag` is `text`, nullable, with **no CHECK constraint**. That is
deliberate and documented (the cash_flows.flow_type precedent): enforcement was to live "in the
entry UI, where an unknown value can be a prompt rather than a 500".

MEASURED 2026-10-01, and the premise does not hold:

  * **No UI writes this field.** `grep strategy_tag frontend/` returns nothing. The only writer
    is the PATCH route on unified_positions. The enforcement point the decision rested on was
    never built, so nothing has ever checked a value.
  * **The declared vocabulary and the stored values are disjoint but for one word.** The list
    written in three places (the migration script's VOCAB, the column COMMENT it retyped, and a
    comment in the API model) reads
        CORE | B1_MACRO | B1_C_CONVEXITY | B2_TACTICAL | B3_SCALP | HEDGE | MOMENTUM | OTHER
    while all 16 tagged rows in the book read
        CONVEXITY (8) | B1 (4) | B2 (3) | CORE (1)
    Fifteen of sixteen carry a word the vocabulary does not contain. Nothing noticed, because
    nothing was looking.

So the canonical spellings here are the ones the book actually uses, which is also the family
TAIL joins (TA-044). The long forms are kept as recognised ALIASES rather than deleted: a tag
already stored, or already written down in a brief, must not become unreadable because the
vocabulary moved. Four long forms have no counterpart in use and are recorded as such — they
are recognised, so a future write is not refused, and they are listed apart so a reader is not
told they are current.

THE DURABLE PART: the column COMMENT is GENERATED from this module by
scripts/feat_position_lifecycle_strategy_tag.py. It used to be a retyped string literal in the
same file as the list, so the file disagreed with itself by one edit. A vocabulary with two
authors has no author.

Still no CHECK — that precedent is not this ruling's to overturn. But the vocabulary is now in
one place, so a CHECK could be *generated* from it the day one is wanted.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# ── the canonical set: what the book writes today, plus TAIL (TA-044) ──
CORE = "CORE"
B1 = "B1"
B2 = "B2"
CONVEXITY = "CONVEXITY"
TAIL = "TAIL"

TAGS: Tuple[str, ...] = (CORE, B1, B2, CONVEXITY, TAIL)

# ── long forms declared by R-IV.143(2) that map onto a canonical tag ──
ALIASES: Dict[str, str] = {
    "B1_MACRO": B1,
    "B2_TACTICAL": B2,
    "B1_C_CONVEXITY": CONVEXITY,
}

# ── declared in R-IV.143(2), never written to a row, and with no canonical
# counterpart. Recognised so a write is not refused; listed apart so nobody
# reads them as current. Promote one into TAGS the day a row carries it.
UNWRITTEN_DECLARED: Tuple[str, ...] = ("B3_SCALP", "HEDGE", "MOMENTUM", "OTHER")

# NULL is untagged and is NOT a tag. It never means OTHER: OTHER is a decision,
# NULL is the absence of one. Nothing here may be used as a default.
UNTAGGED = None


def canonical(tag: Optional[str]) -> Optional[str]:
    """The canonical spelling of `tag`, or None if it is not a recognised word.

    Returns None for None — an untagged row stays untagged. Returns None for an unknown
    string too, so a caller must distinguish "no tag" from "a tag I cannot read" by asking
    `is_known` rather than by reading a falsy value as either.
    """
    if tag is None:
        return None
    t = tag.strip().upper()
    if not t:
        return None
    if t in TAGS:
        return t
    if t in ALIASES:
        return ALIASES[t]
    if t in UNWRITTEN_DECLARED:
        return t
    return None


def is_known(tag: Optional[str]) -> bool:
    """True only for a word this vocabulary declares. None is not known — it is absent."""
    return tag is not None and canonical(tag) is not None


def all_recognised() -> Tuple[str, ...]:
    """Every word a write may carry: canonical, alias, and declared-but-unwritten."""
    return TAGS + tuple(ALIASES) + UNWRITTEN_DECLARED


def column_comment() -> str:
    """The text for `COMMENT ON COLUMN unified_positions.strategy_tag`, generated here.

    Generated, never retyped: the comment and the list were two copies in one file, so an
    edit to either left the database describing a vocabulary the code had moved on from.
    """
    return (
        "Strategy vocabulary, generated from backend/models/strategy_tag.py "
        "(R-IV.624(d)2; supersedes the retyped list of R-IV.143(2)). "
        "Canonical: " + " | ".join(TAGS) + ". "
        "Recognised aliases: " + " | ".join(f"{k}->{v}" for k, v in ALIASES.items()) + ". "
        "Declared but never written: " + " | ".join(UNWRITTEN_DECLARED) + ". "
        "Deliberately NO CHECK constraint (cash_flows.flow_type precedent). NOTE: that "
        "decision placed enforcement in the entry UI, and measurement on 2026-10-01 found no "
        "UI writes this column at all - the only writer is the PATCH route - which is why 15 "
        "of 16 tagged rows carried a word the old list did not contain. "
        "NULL means untagged, never OTHER: OTHER is a classification, NULL is its absence."
    )
