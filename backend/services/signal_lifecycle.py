"""THE writer for a signal's lifecycle state. R-IV.584(e).

Nothing else writes `signals.status` or `signals.user_action`. Both move together, from the pair
`models.signal_lifecycle` holds, and every move leaves an audit row saying who moved it and why.

WHY AN AUDIT ROW AND NOT JUST A NOTE. The five previous writers appended prose to `notes` — "Auto
-expired after 24h", "Auto-dismissed: conflicting signals on COIN" — and prose is not a field. It
cannot be counted, it cannot be grouped, and reading it back to recover what happened is how a
reworded log line becomes a wrong answer. `signal_lifecycle_events` records the two columns
before and after, the reason, and the actor, as data.

THE GUARD THAT MATTERS. `set_state` does NOT require the row to be in any particular state first.
That is deliberate and it is the whole repair: the previous cleanup writer had
`WHERE status = 'ACTIVE'`, so a row that had drifted out of ACTIVE could never be brought back —
which is why 750 rows sat in a state nobody had put them in and nothing could take them out of.
Callers that DO need a precondition pass `only_if`, and get told when it did not hold rather than
silently writing nothing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

from models.signal_lifecycle import columns_for, state_of

logger = logging.getLogger(__name__)

# Who moved it. A machine writer names itself, because a column that cannot tell a person from a
# job cannot answer the one question it exists for (R-IV.462(b)).
ACTOR_PRINCIPAL = "principal"
ACTOR_AGE_SWEEP = "age-sweep"
ACTOR_CONFLICT = "conflict-rule"
ACTOR_PIPELINE = "pipeline"
ACTOR_RECONCILE = "reconcile"


async def set_state(
    conn,
    signal_id: str,
    state: str,
    *,
    reason: str,
    actor: str,
    ruling: str = "",
    only_if: Optional[Iterable[str]] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Move one signal to `state`. Both columns, together, with an audit row.

    `only_if` is a set of STATES (not raw status values) the row must already be in. A row whose
    two columns do not agree on any state reads as `None`, and `None` is never in `only_if` — so
    a caller with a precondition will refuse a corrupted row rather than write over the evidence.

    Returns what happened: `{changed, before_state, before_status, before_user_action, reason}`.
    `changed` is False when the row is already in `state`, when it is missing, or when `only_if`
    did not hold — and `reason` says which. A caller that needs to know cannot mistake one for
    another, which the old writers' bare row counts could not tell apart.
    """
    status, user_action = columns_for(state)

    row = await conn.fetchrow(
        "SELECT signal_id, status, user_action FROM signals WHERE signal_id = $1", signal_id)
    if row is None:
        return {"changed": False, "reason": "no such signal", "signal_id": signal_id}

    before_status, before_action = row["status"], row["user_action"]
    before_state = state_of(before_status, before_action)

    if only_if is not None and before_state not in set(only_if):
        return {
            "changed": False,
            "reason": "row is %s, not one of %s" % (
                before_state or "in no state at all", ", ".join(sorted(only_if))),
            "signal_id": signal_id,
            "before_state": before_state,
            "before_status": before_status,
            "before_user_action": before_action,
        }

    if before_status == status and before_action == user_action:
        return {"changed": False, "reason": "already " + state, "signal_id": signal_id,
                "before_state": before_state}

    async with conn.transaction():
        from utils.audit_actor import name_actor

        await name_actor(conn, actor, reason)
        if note:
            await conn.execute(
                """UPDATE signals
                      SET status = $2, user_action = $3,
                          notes = CASE WHEN notes IS NULL OR notes = '' THEN $4
                                       ELSE notes || ' | ' || $4 END
                    WHERE signal_id = $1""",
                signal_id, status, user_action, note)
        else:
            await conn.execute(
                "UPDATE signals SET status = $2, user_action = $3 WHERE signal_id = $1",
                signal_id, status, user_action)
        await conn.execute(
            """INSERT INTO signal_lifecycle_events
                   (signal_id, from_status, from_user_action, from_state,
                    to_status, to_user_action, to_state, reason, ruling, actor)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
            signal_id, before_status, before_action, before_state,
            status, user_action, state, reason, ruling, actor)

    return {
        "changed": True,
        "signal_id": signal_id,
        "before_state": before_state,
        "before_status": before_status,
        "before_user_action": before_action,
        "state": state,
        "reason": reason,
    }


async def set_state_many(
    conn,
    signal_ids: Iterable[str],
    state: str,
    *,
    reason: str,
    actor: str,
    ruling: str = "",
    only_if: Optional[Iterable[str]] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """`set_state` over several ids, reporting the counts rather than one number.

    A bulk writer that returns "UPDATE 47" cannot say whether the other three were missing,
    already there, or refused — and those need different remedies.
    """
    changed, unchanged, refusals = 0, 0, []
    for signal_id in signal_ids:
        result = await set_state(conn, signal_id, state, reason=reason, actor=actor,
                                 ruling=ruling, only_if=only_if, note=note)
        if result.get("changed"):
            changed += 1
        else:
            unchanged += 1
            refusals.append({"signal_id": signal_id, "reason": result.get("reason")})
    return {"changed": changed, "unchanged": unchanged, "refusals": refusals, "state": state}
