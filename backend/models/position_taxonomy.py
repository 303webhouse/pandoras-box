"""Three taxonomies, three fields — TA-123, R-IV.794(b).

THE DEFECT. `unified_positions.strategy_tag` is one column carrying three INDEPENDENT
taxonomies, so each row shows whichever was written last and the other two are gone. That is not
a presentation nuisance: filtering it for the Roth's 20% tactical cap returned SOXS alone at
**8.26%**, against the truth of SOXS + TSLQ at **19.50%**, because TSLQ's `TACTICAL` had been
overwritten by its bucket `B2`. A cap read off that field is a cap read off the last edit, and it
under-reported by more than half.

So `strategy_tag` becomes a DISPLAY STRING with no authority, and the three live beside it:

    classification   STRATEGIC | TACTICAL      <- the hard cap depends on this one
    sleeve_tag       TAIL | CONVEXITY
    bucket           B1 | B2 | B3

NOTHING HERE GUESSES. `split_display_tag` returns a value only where the word names that
taxonomy unambiguously, and reports a REASON otherwise. R-IV.794(b)3 is explicit that ambiguous
rows are listed for TA and not filled in, so the ambiguity has to survive as data rather than be
resolved by whoever wrote the mapping.

MEASURED WHILE BUILDING THIS: `models/strategy_tag.py`, which calls itself "the one author of
the strategy_tag vocabulary", does not recognise `STRATEGIC`, `TACTICAL` or `B3` --
`is_known("STRATEGIC")` is False -- while nine live rows carry the first two. Its declared set is
(CORE, B1, B2, CONVEXITY, TAIL). The vocabularies below are the RULED ones and do not read from
it, because inheriting a list that is two labels behind the book is how this defect started.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

# ── the three ruled vocabularies. Independent: a row may carry all three, or none. ──
STRATEGIC = "STRATEGIC"
TACTICAL = "TACTICAL"
CLASSIFICATIONS: Tuple[str, ...] = (STRATEGIC, TACTICAL)

TAIL = "TAIL"
CONVEXITY = "CONVEXITY"
SLEEVE_TAGS: Tuple[str, ...] = (TAIL, CONVEXITY)

BUCKETS: Tuple[str, ...] = ("B1", "B2", "B3")

FIELDS: Tuple[str, ...] = ("classification", "sleeve_tag", "bucket")
VOCABULARIES: Dict[str, Tuple[str, ...]] = {
    "classification": CLASSIFICATIONS,
    "sleeve_tag": SLEEVE_TAGS,
    "bucket": BUCKETS,
}

# `CONVEXITY` reads as a sleeve today. On a row written before 2026-09-25 it may have been
# meant as a classification, so it is NOT auto-mapped there (R-IV.794(b)3 names this case).
CONVEXITY_SLEEVE_FROM = "2026-09-25"

# Words that belong to no ruled vocabulary. CORE and HEDGE were classifications under an older
# scheme; neither is STRATEGIC or TACTICAL, and choosing one here would be the guess the ruling
# forbids.
NOT_IN_ANY_VOCABULARY: Tuple[str, ...] = ("CORE", "HEDGE", "MOMENTUM", "OTHER")


def _norm(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().upper()
    return s or None


def split_display_tag(tag: Any, *, entry_date: Any = None
                      ) -> Tuple[Dict[str, Optional[str]], Optional[str]]:
    """`({classification, sleeve_tag, bucket}, reason)` for one display tag.

    Every field it cannot establish stays None, and `reason` says why. `reason` is None only
    when the tag mapped cleanly onto exactly one taxonomy.

    A tag names at most ONE of the three, which is the whole defect: the other two were never
    recorded anywhere. So a clean mapping still leaves two fields unknown, and that is correct —
    unknown is not a value to be filled in later by inference.
    """
    out: Dict[str, Optional[str]] = {f: None for f in FIELDS}
    t = _norm(tag)
    if t is None:
        return out, "no strategy_tag: nothing is recorded for any of the three"
    if t in CLASSIFICATIONS:
        out["classification"] = t
        return out, None
    if t in BUCKETS:
        out["bucket"] = t
        return out, None
    if t == TAIL:
        out["sleeve_tag"] = TAIL
        return out, None
    if t == CONVEXITY:
        # Ambiguous on an older row: CONVEXITY may have been a classification then.
        day = _as_day(entry_date)
        if day is not None and day < CONVEXITY_SLEEVE_FROM:
            return out, ("CONVEXITY on a pre-%s row: may have been written as a classification, "
                         "not a sleeve" % CONVEXITY_SLEEVE_FROM)
        out["sleeve_tag"] = CONVEXITY
        return out, None
    if t in NOT_IN_ANY_VOCABULARY:
        return out, "%s belongs to no ruled vocabulary (not STRATEGIC/TACTICAL)" % t
    return out, "unrecognised value %r" % t


def _as_day(value: Any) -> Optional[str]:
    """The YYYY-MM-DD prefix of a date or ISO string, or None."""
    if value is None:
        return None
    s = str(value)
    return s[:10] if len(s) >= 10 else None


def is_valid(field: str, value: Any) -> bool:
    """True when `value` is in `field`'s vocabulary. None is never valid — it is absence."""
    v = _norm(value)
    return v is not None and v in VOCABULARIES.get(field, ())


def cap_eligible(row: Mapping[str, Any]) -> bool:
    """Can the 20% tactical cap be applied to this row at all.

    False when `classification` is absent, and the CALLER must treat that as "cannot enforce",
    never as "not tactical". Counting an unclassified row as out-of-scope is what produced
    8.26% against a true 19.50%.
    """
    return _norm(row.get("classification")) in CLASSIFICATIONS


def column_ddl() -> Tuple[str, ...]:
    """The ADD COLUMN statements, generated from the vocabularies above.

    Nullable and with no CHECK, matching `strategy_tag`'s precedent: NULL here means "not
    recorded", and until the backfill lands it means "not yet migrated" — which is why the
    payload carries `classification_backfilled` rather than letting a reader infer from a null.
    """
    return tuple(
        "ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS %s TEXT" % f for f in FIELDS
    )


def column_comments() -> Dict[str, str]:
    """Generated, never retyped — a vocabulary with two authors has no author."""
    return {
        f: "TA-123/R-IV.794(b): one of %s, or NULL for not recorded. Independent of "
           "strategy_tag, which is a display string only and may not be used for any cap, "
           "gate or filter." % " | ".join(VOCABULARIES[f])
        for f in FIELDS
    }
