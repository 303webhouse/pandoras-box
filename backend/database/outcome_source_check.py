"""`signals.outcome_source_valid` — the one list of allowed outcome sources (R-IV.1443(c)).

WHY THIS EXISTS. `jobs/outcome_resolver._mark_ungradeable` writes outcome_source =
'UNGRADEABLE', but the CHECK constraint in production (migrations/017) never listed it. The
first ungradeable row would have its UPDATE refused, stay unresolved, and be retried every
cycle: the endless loop the 10-17 fix (6c4f943e) closed would reopen. No row has needed it
yet, which is the only reason nothing has broken.

ONE LIST. The boot step below and migrations/056 build the constraint from
`OUTCOME_SOURCE_VALUES`, and a test holds every writer's constant inside it. A new source is
added HERE, and the next boot widens the constraint.

ONLY EVER WIDENS. Postgres cannot alter a CHECK in place, so the step drops and re-adds it,
inside one transaction. It runs only when the live definition is missing a value, so an
ordinary boot changes nothing. The new constraint is added NOT VALID and validated after:
existing rows already satisfy the narrower list, and VALIDATE takes a lighter lock than a
plain ADD on a 300 MB table. A short lock_timeout keeps a busy table from hanging the boot;
on any failure the boot carries on and the next boot tries again.
"""
from __future__ import annotations

import logging
from typing import Iterable, Tuple

logger = logging.getLogger(__name__)

CONSTRAINT = "outcome_source_valid"

#: Every value any writer may put in signals.outcome_source.
OUTCOME_SOURCE_VALUES: Tuple[str, ...] = (
    "BAR_WALK",
    "ACTUAL_TRADE",
    "COUNTERFACTUAL",
    "EXPIRED",
    "INVALIDATED",
    "PROJECTED_FROM_BAR_WALK",
    "OPTIONS_PNL",
    "FWD_RETURN",
    "COMMITTEE_REVIEW",
    "UNGRADEABLE",        # R-IV.1443(c): outcome_resolver._mark_ungradeable
)


def check_clause(values: Iterable[str] = OUTCOME_SOURCE_VALUES) -> str:
    """The CHECK body, in SQL that Postgres and SQLite both accept."""
    vals = ", ".join("'%s'" % v for v in values)
    return "outcome_source IS NULL OR outcome_source IN (%s)" % vals


def missing_from(definition: str, values: Iterable[str] = OUTCOME_SOURCE_VALUES) -> list:
    """Values absent from a live `pg_get_constraintdef` string (quoted, as Postgres prints them)."""
    return [v for v in values if ("'%s'" % v) not in (definition or "")]


async def ensure_outcome_source_check(conn) -> str:
    """Widen the live constraint if it lacks any value. Returns what it did. NEVER raises."""
    try:
        definition = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'signals'::regclass AND conname = $1", CONSTRAINT)
        if definition is not None and not missing_from(definition):
            return "unchanged"
        absent = missing_from(definition or "")
        async with conn.transaction():
            await conn.execute("SET LOCAL lock_timeout = '5s'")
            await conn.execute("ALTER TABLE signals DROP CONSTRAINT IF EXISTS %s" % CONSTRAINT)
            await conn.execute("ALTER TABLE signals ADD CONSTRAINT %s CHECK (%s) NOT VALID"
                               % (CONSTRAINT, check_clause()))
        await conn.execute("ALTER TABLE signals VALIDATE CONSTRAINT %s" % CONSTRAINT)
        logger.warning("[boot] signals.%s widened: added %s", CONSTRAINT, ", ".join(absent))
        return "widened: " + ", ".join(absent)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[boot] signals.%s not widened this boot: %s", CONSTRAINT,
                       type(exc).__name__)
        return "failed: " + type(exc).__name__
