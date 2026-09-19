"""Who wrote a row -- the name the audit trigger records (R-IV.462(b)).

unified_positions' audit trigger reads the transaction-local setting app.actor. A writer that
names no one is recorded as 'legacy-ui', R-IV.116's default for the legacy PATCH caller. Machine
writers never named themselves, so the audit holds 6,271 UPDATE rows labelled 'legacy-ui' from
2026-08-27 to 2026-09-19 (measured 05:30 UTC), 3,239 of them the mark job -- and a column that
cannot tell a person from a job cannot answer the one question it exists for.

Every machine writer now names itself IN THE SAME TRANSACTION as its write. set_config(..., true)
lasts until that transaction ends: a name set outside one reaches nothing, and a name set at
session level would ride a pooled connection into the next caller's write.

Rows written before the cutover are left as they are, and are ambiguous. audit_actor_epochs
records the instant named writers went live; the actor column's comment says what that means.
"""

from __future__ import annotations

from typing import Optional

MARK_TO_MARKET = "mark-to-market"
BOOT_MIGRATION = "boot-migration"


async def name_actor(conn, actor: str, reason: Optional[str] = None) -> None:
    """Name the writer for the audit trigger. Call inside `async with conn.transaction()`."""
    await conn.execute("SELECT set_config('app.actor', $1, true)", actor)
    if reason:
        await conn.execute("SELECT set_config('app.reason', $1, true)", reason)
