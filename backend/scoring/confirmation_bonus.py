"""The confirmation bonus — one author, counting TYPES — R-IV.901(e).

THE DEFECT (found by LAB). The bonus was `min(5, max(0, (signal_count - 1) * 2))`, and
`signal_count` is `1 + len(related_signals)` — a count of ROWS. So one signal re-firing within
the grouping window earned +2 for confirming itself. A thesis supported by one scanner twice
scored the same as one supported by two independent scanners, which is the whole thing the bonus
is supposed to distinguish.

ONE FACT, TWO AUTHORS — fixed here as well. The identical expression lived in
`api/trade_ideas.py` and `signals/feed_service.py`, so a fix applied to one would have left the
other paying the old bonus, and the two surfaces would have disagreed about the same idea's
score. Both now call this.

DISTINCT TYPES, CASE-INSENSITIVELY. Stored casing is not guaranteed — the strategy column holds
`Whale_Hunter`, not `whale_hunter` (R-IV.849(d)) — so `TRAPPED_SHORTS` and `Trapped_Shorts`
would otherwise count as two independent confirmations of each other, reintroducing the defect
through a different door.

VERSIONED. The figure moves for existing ideas, so a reader comparing a display_score across the
change needs to know which rule produced it. `VERSION` travels with the result.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# v1: (row_count - 1) * 2, capped at 5 — counted ROWS, so a re-fire confirmed itself.
# v2: (distinct signal_type count - 1) * 2, capped at 5 — R-IV.901(e).
VERSION = 2

POINTS_PER_EXTRA_TYPE = 2
MAX_BONUS = 5


def _type_of(row: Optional[Dict[str, Any]]) -> Optional[str]:
    """A row's signal type, normalised for comparison. None when it has none.

    `signal_type` and not `strategy`: the ruling says TYPES, and the two are different vocabularies
    — one strategy can emit several types (the CTA scanner emits TRAPPED_LONGS and TRAPPED_SHORTS),
    and one type can come from several strategies (TRAPPED_SHORTS from both the CTA and the crypto
    scanner). Counting strategies would merge confirmations the ruling means to separate.
    """
    if not isinstance(row, dict):
        return None
    t = row.get("signal_type")
    if t is None or not str(t).strip():
        return None
    return str(t).strip().upper()


def distinct_supporting_types(primary: Optional[Dict[str, Any]],
                              related: Optional[Sequence[Dict[str, Any]]]) -> List[str]:
    """Every distinct type across the primary and its related rows, in first-seen order.

    First-seen order rather than sorted, so a log line reads as the group was built and two logs
    of the same group look the same.
    """
    out: List[str] = []
    for row in [primary] + list(related or []):
        t = _type_of(row)
        if t and t not in out:
            out.append(t)
    return out


def compute(primary: Optional[Dict[str, Any]],
            related: Optional[Sequence[Dict[str, Any]]]) -> Tuple[int, Dict[str, Any]]:
    """(bonus, provenance). The provenance carries the version and what was counted.

    A bonus with no record of how it was reached cannot be compared across the version change,
    which is the whole reason (e) asks for a before/after log.
    """
    types = distinct_supporting_types(primary, related)
    extra = max(0, len(types) - 1)
    bonus = min(MAX_BONUS, extra * POINTS_PER_EXTRA_TYPE)
    return bonus, {
        "confirmation_bonus_version": VERSION,
        "distinct_signal_types": types,
        "distinct_type_count": len(types),
        "rows_considered": 1 + len(list(related or [])),
    }


def legacy_v1(signal_count: Any) -> int:
    """The OLD figure, kept so the before/after log can show both.

    Not used for scoring. It exists because "the bonus changed" is not a reportable fact without
    the number it changed from, and recomputing it from memory later would be guesswork.
    """
    try:
        n = int(signal_count or 0)
    except (TypeError, ValueError):
        return 0
    return min(MAX_BONUS, max(0, (n - 1) * POINTS_PER_EXTRA_TYPE))
