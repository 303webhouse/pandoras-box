"""The B2 cut alert's own record — the read path for R-IV.1001(d).

WHY A ROUTE. TA-161 §1.1 makes the GATED MARK the input the verdict is computed from, so the
mark and its timestamp are the audit trail for every fire and every refusal. The job writes
them to `unified_positions` (`mark`, `mark_as_of`, `mark_integrity`, `mark_integrity_reason`),
and nothing served them: `/v2/positions` carries neither, so the figure a verdict rests on was
unreadable from outside the database. R-IV.552(b) -- routes exist so nobody needs direct SQL.

READ-ONLY BY CONSTRUCTION. Every statement is a SELECT.

CONVENTION #39 IS SERVED, NOT ASSUMED. Each timestamp is returned in BOTH clocks, labelled,
plus the exchange session date it belongs to. A reader comparing a mark against a cut session
must not have to do a timezone conversion to find out whether they are on the same day --
which is the exact defect R-IV.1001(c) corrected in S10.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from database.postgres_client import get_postgres_client
from utils.pivot_auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/b2-cut", tags=["b2-cut"])

ET = ZoneInfo("America/New_York")

RECORD_SQL = """
    SELECT p.position_id,
           p.ticker,
           p.bucket,
           p.status,
           p.structure,
           p.entry_date,
           p.entry_price,
           p.quantity,
           p.expiry,
           p.unrealized_pnl,
           p.mark,
           p.mark_as_of,
           p.mark_integrity,
           p.mark_integrity_reason,
           p.b2_cut_alerted_at,
           COALESCE((SELECT SUM(c.realized) FROM position_lot_closures c
                      WHERE c.position_id = p.position_id), 0)      AS realized_pnl
      FROM unified_positions p
     WHERE UPPER(COALESCE(p.bucket, '')) = 'B2'
       AND UPPER(COALESCE(p.status, '')) <> 'DUPLICATE_OF'
       AND ($1::text IS NULL OR UPPER(p.ticker) = UPPER($1))
     ORDER BY p.ticker
"""


def _stamp(ts: Any) -> Optional[Dict[str, Any]]:
    """One timestamp, in BOTH clocks plus its exchange session — convention #39.

    Returned as a structure rather than a string so a reader cannot mistake which clock they
    are holding. `None` stays `None`: an absent mark is not an epoch.
    """
    if ts is None:
        return None
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return {"raw": ts, "note": "not parseable as a timestamp"}
    if not isinstance(ts, datetime):
        return {"raw": str(ts), "note": "not a timestamp"}
    if ts.tzinfo is None:
        # Refusing to assume a zone is the point; a naive stamp is a defect, not a default.
        return {"raw": ts.isoformat(), "note": "NAIVE -- no timezone recorded, not converted"}
    utc = ts.astimezone(timezone.utc)
    et = ts.astimezone(ET)
    return {"utc": utc.isoformat(timespec="microseconds"),
            "utc_to_the_second": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "america_new_york": et.isoformat(timespec="microseconds"),
            "exchange_session": et.date().isoformat()}


@router.get("/record")
async def record(
    ticker: Optional[str] = Query(None, description="one ticker, or all B2 rows"),
    _auth: Any = Depends(require_api_key),
) -> Dict[str, Any]:
    """The mark each B2 row's cut was gated on, with its timestamp in both clocks.

    This is the alert's RECORD, not a fresh evaluation: it reports what was stored, so a
    verdict can be audited against the number it was actually taken on.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(RECORD_SQL, ticker)]
        from services.open_quantity import stamp_open_quantity
        await stamp_open_quantity(conn, rows)

    from models.b2_cut_alert import (ALERT_FIRST_DEPLOY_UTC, alert_first_deploy_session,
                                     cut_session, is_in_scope)

    out = []
    for r in rows:
        cut = cut_session(r.get("entry_date"))
        out.append({
            "position_id": r["position_id"],
            "ticker": r["ticker"],
            "structure": r["structure"],
            "in_scope": is_in_scope(r),
            "open_quantity": r.get("open_quantity"),
            "open_quantity_basis": r.get("open_quantity_basis"),
            "entry_price": str(r["entry_price"]) if r.get("entry_price") is not None else None,
            "entry_date": r["entry_date"].isoformat() if r.get("entry_date") else None,
            "cut_session": cut.isoformat() if cut else None,
            # THE GATED MARK and its stamp -- what R-IV.1001(d) asks for.
            "mark": str(r["mark"]) if r.get("mark") is not None else None,
            "mark_as_of": _stamp(r.get("mark_as_of")),
            "mark_integrity": r.get("mark_integrity"),
            "mark_integrity_reason": r.get("mark_integrity_reason"),
            "b2_cut_alerted_at": _stamp(r.get("b2_cut_alerted_at")),
            # Reported beside the mark and consulted for no verdict (TA-161).
            "unrealized_pnl": (str(r["unrealized_pnl"])
                               if r.get("unrealized_pnl") is not None else None),
            "realized_pnl": (str(r["realized_pnl"])
                             if r.get("realized_pnl") is not None else None),
        })

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "basis": ("sessions and the deploy anchor are compared in America/New_York "
                  "(convention #39); timestamps are stored and returned in UTC and converted "
                  "for display, never the reverse"),
        "alert_first_deploy": {
            "utc": ALERT_FIRST_DEPLOY_UTC.isoformat(),
            "exchange_session": alert_first_deploy_session().isoformat(),
            "note": "the alert's FIRST production deploy; never advanced by a later deploy",
        },
        "rows": out,
    }
