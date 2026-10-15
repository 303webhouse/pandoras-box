"""Delivery for the 20% tactical reminder — R-IV.1033(e). The arithmetic lives elsewhere.

WHY THIS RUNS ON THE MARK REFRESH AND NOT ON THE WRITE, stated plainly because it is a
deviation from the ruling's wording.

R-IV.1033(e) says "on any position write". THERE IS NO SINGLE WRITE CHOKE POINT:
`api/unified_positions.py` alone has 35 INSERT/UPDATE statements across 30 writing endpoints,
and the existing write-scope guard is called from only 2 of them. Hooking "any write" today
means hooking thirty places, which is thirty chances to miss one -- and a cap reminder that
silently fails to fire is the failure that matters, since nobody notices a notification that
never came.

So it runs immediately after the mark-to-market refresh, which already fires at :02/:17/:32/:47
from 09:00-17:00 ET plus a forced closing-bell run. That gives COMPLETE coverage of every write
by every path, at a latency of at most fifteen minutes, and the marks are freshest exactly
there -- the cap is on MARKET value, so a figure computed before the refresh would be stale by
construction.

The trade is latency for coverage, and for a reminder that is the right way round. A write
choke point would be better and is worth building; until it exists, this cannot miss.

NEVER BLOCKS, NEVER RAISES. Nothing here is awaited by a write path, and every failure is
swallowed with a log.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("roth_cap_reminder")

#: Last percentage pushed, per account. In-process: a redeploy re-pushes the current figure
#: once, which is the right failure direction for a REMINDER -- a restart is a fresh chance to
#: be told, and one extra notification costs less than a missed one.
_LAST_PUSHED: Dict[str, Optional[str]] = {}

ACCOUNT_VALUE_SQL = """
    SELECT account_name, balance
      FROM account_balances
     WHERE UPPER(account_name) = ANY($1::text[])
"""

POSITIONS_SQL = """
    SELECT p.position_id, p.account, p.classification, p.structure,
           p.current_price, p.quantity
      FROM unified_positions p
     WHERE UPPER(COALESCE(p.status, '')) <> 'DUPLICATE_OF'
       AND UPPER(COALESCE(p.account, '')) = ANY($1::text[])
"""


async def run(*, pool=None) -> Dict[str, Any]:
    """Compute the tactical share for each capped account and push if it moved. NEVER raises."""
    from models.roth_tactical_cap import (CAP_ACCOUNTS, push_text, should_push,
                                          tactical_share)

    out: Dict[str, Any] = {"accounts": {}, "pushed": 0}
    accounts = sorted(CAP_ACCOUNTS)
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = [dict(r) for r in await conn.fetch(POSITIONS_SQL, accounts)]
            # `open_quantity` is NOT selected: `services.open_quantity` is the one author of
            # it (R-IV.660(b)2), and a second SUM here would be a second author.
            from services.open_quantity import stamp_open_quantity
            await stamp_open_quantity(conn, rows)
            bal = {(r["account_name"] or "").upper(): r["balance"]
                   for r in await conn.fetch(ACCOUNT_VALUE_SQL, accounts)}
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[roth-cap] could not read positions/balances: %s", type(exc).__name__)
        return out

    for acct in accounts:
        try:
            verdict = tactical_share(rows, acct, bal.get(acct))
            out["accounts"][acct] = verdict
            if verdict["pct"] is None:
                # Loud: a cap that cannot be computed is a cap that is not being watched, and
                # that must not look like a satisfied one.
                logger.warning("[roth-cap] %s: %s", acct, verdict["reason"])
                continue
            logger.info("[roth-cap] %s: %s%% of account (%d position(s)%s)",
                        acct, verdict["pct"], verdict["positions_counted"],
                        ", provisional" if verdict["provisional"] else "")
            if not should_push(verdict, _LAST_PUSHED.get(acct)):
                continue
            from integrations.ntfy_push import is_configured
            from integrations.ntfy_push import send as ntfy_send
            if not is_configured():
                continue
            label = "Roth" if acct == "FIDELITY_ROTH" else "401(a)"
            # Claim BEFORE the await, so two passes cannot both push the same figure.
            _LAST_PUSHED[acct] = verdict["pct"]
            await ntfy_send(label, "tactical cap reminder", push_text(verdict))
            out["pushed"] += 1
            logger.warning("[roth-cap] pushed %s at %s%% (reminder only, nothing blocked)",
                           label, verdict["pct"])
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("[roth-cap] %s failed: %s", acct, type(exc).__name__)
    return out
