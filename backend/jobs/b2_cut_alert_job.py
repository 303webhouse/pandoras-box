"""The B2 three-day cut alert, wired — TA-141 §3 / R-IV.888(c)1, R-IV.892(e)1.

`models/b2_cut_alert.py` holds the DECISION and is pure. This holds the query, the clock, the
alert and the flag write, which is the whole of what can go wrong operationally.

FOUR THINGS THIS FILE IS CAREFUL ABOUT.

**Open is `open_quantity > 0`, computed from the lots** — never `status`, never a tag
(R-IV.844(d)3). A partial exit leaves a row OPEN with real remaining size, and a status string
has been the wrong question before.

**Realized comes from the closure ledger, not the row.** A partial exit's realized stays on an
OPEN row and the row's own column has been measured under-reporting the book by 107.48. The
decision function totals what it is given; sourcing it correctly is this file's job.

**The flag is written only after the alert is DELIVERED.** Flagging first would convert a failed
webhook into a permanent silence: the row would read "already fired" forever and the prompt
would never arrive. Phase 1's Hermes rule, for the same reason.

**It never closes anything.** The alert is a prompt; the decision module is asserted not to call
any execution path, and this file only ever writes the flag column.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("b2.cut_alert")

ET = ZoneInfo("America/New_York")
FLAG = "B2_CUT_ALERT_ENABLED"
JOB_NAME = "b2_cut_alert"

# R-IV.462(b): every machine writer names itself IN THE TRANSACTION that carries its write.
# Without it the audit trigger reads an empty setting and records 'legacy-ui' -- which is how
# 6,271 UPDATE rows became unattributable, 3,239 of them from the mark job alone. The suite
# caught this file writing anonymously before it shipped.
AUDIT_ACTOR = "b2-cut-alert-job"

# The flag column, added here so the ledger of "already fired" lives on the row it describes.
DDL_FLAG = (
    "ALTER TABLE unified_positions "
    "ADD COLUMN IF NOT EXISTS b2_cut_alerted_at TIMESTAMPTZ"
)

# THE COLUMN NAMES HERE WERE WRONG ON THE FIRST WRITING, and checking the schema rather than
# deploying caught it: `position_lots.quantity` and `position_lot_closures.realized_pnl` do not
# exist. The real names are `qty` and `realized`.
#
# open_quantity is NOT computed here AT ALL. `services/open_quantity.py` exists "so no consumer
# computes it" (R-IV.660(b)2) and does the whole list in one lot query -- a second
# implementation would be a second author of the rule that decides what is still open.
#
# realized DOES come from the closure ledger rather than unified_positions.realized_pnl, because
# a partial exit's realized stays on an OPEN row and the row's column has been measured
# under-reporting the book by 107.48. Same `SUM(c.realized)` shape the abacus and
# unified_positions readers already use.
#
# DUPLICATE_OF is excluded case-insensitively (R-IV.874): a retired duplicate's money counts
# once, on its keeper.
SELECT_SQL = """
SELECT p.position_id,
       p.ticker,
       p.bucket,
       p.status,
       p.entry_date,
       p.expiry,
       p.unrealized_pnl,
       p.b2_cut_alerted_at,
       COALESCE((SELECT SUM(c.realized) FROM position_lot_closures c
                  WHERE c.position_id = p.position_id), 0)          AS realized_pnl
  FROM unified_positions p
 WHERE UPPER(COALESCE(p.bucket, '')) = 'B2'
   AND UPPER(COALESCE(p.status, '')) <> 'DUPLICATE_OF'
"""


def is_enabled() -> bool:
    """Empty-safe: Railway returns '' for an unset reference, so `or ""` then compare."""
    return (os.getenv(FLAG) or "").strip().lower() in ("1", "true", "yes", "on")


async def evaluate(now: Optional[datetime] = None, *, pool=None) -> List[Dict[str, Any]]:
    """Every B2 row's verdict. NEVER RAISES. Read-only; writes nothing."""
    from models.b2_cut_alert import decide, is_in_scope

    now = now or datetime.now(ET)
    out: List[Dict[str, Any]] = []
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(DDL_FLAG)
            rows = [dict(r) for r in await conn.fetch(SELECT_SQL)]
            # The one author for "what is still open", one lot query for the whole list.
            from services.open_quantity import stamp_open_quantity
            await stamp_open_quantity(conn, rows)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[b2.cut_alert] could not read positions: %s", exc)
        return out

    for row in rows:
        if not is_in_scope(row):
            continue
        verdict = decide(row, now=now)
        verdict["position_id"] = row.get("position_id")
        verdict["ticker"] = row.get("ticker")
        out.append(verdict)
    return out


async def run(now: Optional[datetime] = None, *, pool=None) -> Dict[str, Any]:
    """Evaluate, alert on each FIRE, flag only what was delivered. NEVER RAISES."""
    from models.b2_cut_alert import FIRE, UNDETERMINED

    verdicts = await evaluate(now, pool=pool)
    counts: Dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1

    # UNDETERMINED is logged at WARNING every pass, deliberately: a position nobody can price at
    # its cut is a gap in the alert's coverage, and a silent gap looks exactly like a pass.
    for v in verdicts:
        if v["verdict"] == UNDETERMINED:
            logger.warning("[b2.cut_alert] %s (%s) UNDETERMINED at its cut: %s",
                           v.get("ticker"), v.get("position_id"), v.get("reason"))

    fired = 0
    for v in verdicts:
        if v["verdict"] != FIRE:
            continue
        if not is_enabled():
            # The flag gates the PUSH, not the evaluation, so a live book can be watched
            # before anything reaches the phone.
            logger.info("[b2.cut_alert] WOULD ALERT (flag off): %s %s", v.get("ticker"),
                        v.get("reason"))
            continue
        if await _deliver(v) and await _mark_fired(v, pool=pool):
            fired += 1

    return {"evaluated": len(verdicts), "by_verdict": counts, "fired": fired,
            "enabled": is_enabled(), "rows_touched": fired}


async def _deliver(v: Dict[str, Any]) -> bool:
    """One message. Returns True only on a delivered alert; NEVER RAISES."""
    import httpx

    url = os.getenv("DISCORD_WEBHOOK_ALERTS") or ""
    if not url:
        logger.error("[b2.cut_alert] DISCORD_WEBHOOK_ALERTS not set; %s not alerted",
                     v.get("ticker"))
        return False
    content = (
        "**B2 three-day cut — %s**\n"
        "Total P&L %s at the close of the 3rd full trading session (%s).\n"
        "This is a prompt, not an action: nothing has been closed."
        % (v.get("ticker"), v.get("total_pnl"), v.get("cut_session"))
    )
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, json={"content": content})
        if resp.status_code >= 300:
            logger.error("[b2.cut_alert] discord HTTP %d for %s", resp.status_code,
                         v.get("ticker"))
            return False
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[b2.cut_alert] delivery failed for %s: %s", v.get("ticker"),
                     type(exc).__name__)
        return False

    # R-IV.901(b)2/(b)3: the phone relay runs in parallel until the principal confirms. The
    # ntfy payload is NOT this Discord text -- the Discord line carries the dollar P&L, and a
    # third-party relay must carry no dollar amount, account value or position size. So the
    # phone is told WHICH position and WHAT to do, and the figure stays on the channel we own.
    try:
        from integrations.ntfy_push import is_configured
        from integrations.ntfy_push import send as ntfy_send
        if is_configured():
            await ntfy_send(v.get("ticker") or "?", "B2 three-day cut",
                            "not profitable at the 3rd-session close; review it. "
                            "Nothing has been closed.")
    except Exception as exc:                                        # noqa: BLE001
        # Never affects the Discord verdict: the alert HAS been delivered.
        logger.warning("[b2.cut_alert] ntfy leg failed for %s: %s", v.get("ticker"),
                       type(exc).__name__)
    return True


async def _mark_fired(v: Dict[str, Any], *, pool=None) -> bool:
    """Flag the row. Only reached after a DELIVERED alert, so a webhook failure leaves the row
    un-flagged and the next pass tries again rather than going permanently quiet."""
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # SET LOCAL only takes effect inside a transaction; without one the setting is read
            # back empty and the audit falls through to 'legacy-ui'. Scoped to this transaction,
            # so concurrent passes cannot see each other's actor.
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.actor', $1, true)", AUDIT_ACTOR)
                await conn.execute(
                    "SELECT set_config('app.reason', $1, true)",
                    "B2 three-day cut alert delivered for session %s" % (v.get("cut_session"),))
                await conn.execute(
                    "UPDATE unified_positions SET b2_cut_alerted_at = NOW() "
                    "WHERE position_id = $1 AND b2_cut_alerted_at IS NULL",
                    v.get("position_id"))
        return True
    except Exception as exc:                                        # noqa: BLE001
        # The alert WENT OUT and the flag did not. ERROR, because the next pass will send it
        # again -- a duplicate prompt, which is the safe direction but worth knowing about.
        logger.error("[b2.cut_alert] ALERT SENT BUT NOT FLAGGED for %s: %s — it will repeat",
                     v.get("position_id"), type(exc).__name__)
        return False
