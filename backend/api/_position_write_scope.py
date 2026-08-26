"""Column allowlists for writes to unified_positions.

FEAT-POSITION-LIFECYCLE D1, second half: "The trigger audits; the allowlist prevents."

The audit trigger records every mutation but cannot refuse one. These scopes refuse
the mutations that should never happen from a given caller — specifically, a manual
edit writing a mark or a realized field.

Two sites build their SET clause dynamically and so could otherwise write any column
the request model happens to carry:
  * unified_positions.py PATCH /v2/positions/{position_id}  -> MANUAL_EDIT
  * unified_positions.py reconcile mark-update path         -> MARK_JOB

Scope semantics:
  MANUAL_EDIT  a human editing the book. May write neither mark nor realized fields.
               Marks belong to the mark job; realized belongs to the close path.
  MARK_JOB     the pricing path. May write mark fields ONLY -- never realized, never
               position semantics (quantity, strikes, expiry).
  CLOSE_PATH   POST /v2/positions/{id}/close. May write realized and mark fields.

Deliberately NOT an enum of allowed columns per scope for MANUAL_EDIT: a denylist of
the two protected classes is the safer default, because a new semantic column added
to the request model should keep working, whereas a new *mark* column must be added
to MARK_COLUMNS to be writable at all. Fail toward refusing marks.
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable, Set

from fastapi import HTTPException

# Every field whose value is a price observation, not a fact about the position.
MARK_COLUMNS: frozenset[str] = frozenset({
    "current_price",
    "unrealized_pnl",
    "price_updated_at",
    "long_leg_price",
    "short_leg_price",
})

# Every field that records the outcome of a closed trade.
REALIZED_COLUMNS: frozenset[str] = frozenset({
    "realized_pnl",
    "exit_price",
    "exit_date",
    "trade_outcome",
})


class WriteScope(str, Enum):
    MANUAL_EDIT = "manual_edit"
    MARK_JOB = "mark_job"
    CLOSE_PATH = "close_path"


def forbidden_columns(scope: WriteScope) -> Set[str]:
    if scope is WriteScope.MANUAL_EDIT:
        return set(MARK_COLUMNS | REALIZED_COLUMNS)
    if scope is WriteScope.MARK_JOB:
        return set(REALIZED_COLUMNS)
    return set()


def assert_columns_allowed(columns: Iterable[str], scope: WriteScope) -> None:
    """Raise 400 if `columns` contains anything `scope` may not write.

    Called with the column names actually about to be interpolated into the SET
    clause -- not the request model's declared fields -- so a column reaching the
    SQL by any route is checked.
    """
    offending = sorted(set(columns) & forbidden_columns(scope))
    if not offending:
        return
    mark = sorted(set(offending) & MARK_COLUMNS)
    realized = sorted(set(offending) & REALIZED_COLUMNS)
    parts = []
    if mark:
        parts.append(
            f"mark fields {mark} are written only by the mark-to-market job; "
            "a manual edit must not set a price observation"
        )
    if realized:
        parts.append(
            f"realized fields {realized} are written only by "
            "POST /v2/positions/{position_id}/close"
        )
    raise HTTPException(
        status_code=400,
        detail=f"Write refused for scope '{scope.value}': " + "; ".join(parts),
    )
