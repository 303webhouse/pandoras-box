"""THE number a signal is judged by. R-IV.590(c).

THE DEFECT. Three expressions were live at once and none of them was named:

    the feed's ORDER BY      COALESCE(adjusted_score, score_v2, score, 0)
    the high-score flag      COALESCE(score_v2, score)
    the enricher's base      COALESCE(score, score_v2, 50)

ABACUS found the first two disagreeing on 41 of 48 rows on the page. Measured here on the
table, 2026-09-25: **46 of 54 ACTIVE rows differ** between the flag's number and the ranking's.
DE reads **93 by the flag and 85 by the ranking** -- the same row, one card, two numbers. A
reader cannot tell which is the signal's score, and neither can a query.

WORSE, AND THIS IS THE PART WORTH THE MODULE. `adjusted_score` is not "score_v2 adjusted". The
enricher takes its base as `score` FIRST (`signals/pipeline.py`, the `enrich_trade_idea` call)
and writes `base + context_modifier`. Measured: **54 of 54 ACTIVE rows satisfy
`adjusted_score = score + context_modifier`; 7 also happen to match score_v2, by coincidence of
equal values.** And **37 of 54 have a context_modifier of exactly 0** -- for those,
`adjusted_score` IS the legacy score under another name.

So ranking by `COALESCE(adjusted_score, ...)` does not rank by "the newer score with context
applied". It ranks by the LEGACY score, and `score_v2` only decides the order of rows the
enricher never reached. The mean gap between the two is 3.96 points and the maximum is 14, so
this is not cosmetic: MO reads 83 by the flag and 72 by the ranking on a ZERO modifier -- an
eleven-point move that adjusted nothing, it just swapped which scorer was speaking.

WHAT THIS MODULE DOES, AND DELIBERATELY DOES NOT DO. It makes the ranking expression the ONE
canonical score, exported as both SQL and Python so the ORDER BY and the flag are the same
sentence and cannot drift again. It does NOT change the enricher's base precedence. That would
re-rank the live feed on a Friday afternoon on my own initiative, and the choice between "the
legacy score is the base" and "score_v2 is the base" is a judgement about which scorer the
principal trusts, not a defect to be tidied. It is reported instead, with the numbers.

The components stay served beside it, so a reader who wants to see the disagreement still can.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

# The components, in the precedence the pipeline's own ORDER BY uses.
COMPONENTS = ("adjusted_score", "score_v2", "score")

# The SQL. Interpolated into every ORDER BY and predicate, never retyped -- the whole point is
# that there is one sentence.
CANONICAL_SCORE_SQL = "COALESCE(adjusted_score, score_v2, score, 0)"


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:                       # NaN passes every ordinary guard
        return None
    return out


def canonical_score(row: Mapping[str, Any]) -> Optional[float]:
    """The number this signal is ranked by, or None when it carries no usable score.

    The Python twin of `CANONICAL_SCORE_SQL`, with ONE difference that is on purpose: the SQL
    coalesces a missing score to 0 so it can sort, while this returns None. A row with no score
    and a row scoring zero are different claims, and a flag or a card that showed 0 for "we
    never scored this" would be stating something nobody measured.
    """
    for key in COMPONENTS:
        value = _as_float(row.get(key) if hasattr(row, "get") else None)
        if value is not None:
            return value
    return None


def score_components(row: Mapping[str, Any]) -> dict:
    """Every component, named, so the disagreement stays visible rather than being hidden.

    `source` says WHICH component the canonical number came from. Without it a reader seeing 85
    cannot tell whether context moved it or whether a scorer was simply absent, and those are
    the two cases this module exists to separate.
    """
    out = {k: _as_float(row.get(k) if hasattr(row, "get") else None) for k in COMPONENTS}
    source = None
    for key in COMPONENTS:
        if out[key] is not None:
            source = key
            break
    out["source"] = source
    out["context_modifier"] = _as_float(
        row.get("context_modifier") if hasattr(row, "get") else None)
    return out
