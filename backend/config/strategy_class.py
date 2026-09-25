"""R-IV.577(b) — what a feed row IS: roster, shadow, or non-roster.

THE DEFECT THIS REPLACES. The page worked out roster membership from whether the
route had attached a `codename`. That is a DISPLAY field -- `strategy_aliases` says
so in its own first line -- and it returns None for anything unmapped. So "this
family is not on the roster" and "the display layer did not run" arrived at the page
as the same thing, and if the attachment ever stopped, a whole family would drop out
of Watch in silence, looking exactly like a family that had never been there.

The page groups; the server says what a row is.

WHY IT STILL READS THE SAME MAP. The roster IS the codename roster -- inventing a
second list of which strategies are on it would be the two-authors failure, and the
second copy is always the one that goes stale. What changes is that the CLASS is
stated as its own field, computed from the raw `signal_type` / `strategy` the row
carries, and it is never None: an unmapped family is `non-roster`, which is a claim,
where None was an absence.

A test strips `codename` from a row and asserts the class is unchanged, because that
is the exact failure being removed.

SHADOW is not a guess either. Triton is declared SHADOW-ONLY in its own modules --
"no scoring/pipeline coupling", writes only to `triton_flow_shadow`, and its forward
window is a registered study whose grades no live decision reads. A row from a
strategy that does not trade is not a row the principal should see in Watch beside
ones that do, and calling it `roster` would put it there.
"""

from __future__ import annotations

from typing import Optional

from config.strategy_aliases import codename

ROSTER = "roster"
SHADOW = "shadow"
NON_ROSTER = "non-roster"

CLASSES = (ROSTER, SHADOW, NON_ROSTER)

# Codenamed families that TRADE. The roster from the rebuild brief's naming section.
ROSTER_CODENAMES = frozenset({
    "Midas", "Achilles", "Hector", "Apis", "Kodiak", "Icarus", "Nemesis",
})

# Codenamed families that are declared shadow in the codebase itself, not judged so
# here. Triton: `jobs/triton_shadow_*`, "SHADOW-ONLY: no scoring/pipeline coupling",
# and a registered forward window whose grades no live decision consumes.
SHADOW_CODENAMES = frozenset({"Triton"})


def strategy_class(signal_type: Optional[str] = None,
                   strategy: Optional[str] = None) -> str:
    """`roster`, `shadow` or `non-roster`. Never None.

    Computed from the RAW identifiers the row carries, so it does not depend on any
    display layer having run first.
    """
    name = codename(signal_type, strategy)
    if name in SHADOW_CODENAMES:
        return SHADOW
    if name in ROSTER_CODENAMES:
        return ROSTER
    return NON_ROSTER


def attach_strategy_class(row: dict) -> dict:
    """Stamp `strategy_class` on a serialized row, in place. Returns the row.

    Additive, like `attach_codename` beside it: the raw `signal_type` / `strategy`
    are untouched, because outcome history, the n-gates and the committee branching
    all key on them.
    """
    if isinstance(row, dict):
        row["strategy_class"] = strategy_class(row.get("signal_type"),
                                               row.get("strategy"))
    return row
