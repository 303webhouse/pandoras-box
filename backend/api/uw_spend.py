"""GET /api/uw/spend — per-caller UW quota, used, 429s and headroom. READ-ONLY.

R-IV.1059(c). Approved because diagnosing the Hermes outage needed exactly this and there was
no route: `uw_caller_spend_daily` has no reader, so the diagnosis went through the ledger
module's own accessor and, where that could not answer per-day, a read on the module's pool.
R-IV.552(b) says routes exist so nobody needs direct SQL — here no route existed, and the next
person diagnosing a quota outage would have faced the same choice.

WHAT IT ANSWERS, which is the question the outage posed:

    is any caller tag at or over its quota today, and how much room does the 1.2x rule leave?

`snapshot` sat at 1,106/1,100 on 2026-10-13 and 1,100/1,100 on 2026-10-14 with 429s = 0 on
every row. Those three figures side by side are the whole diagnosis: at quota, and UW's own
limiter never fired, so the block was this hub's governor on an under-funded tag.

NO WRITES. Not a single INSERT, UPDATE or DELETE, and no call that spends UW budget: it reads
the spend ledger and the in-process quota table, nothing else. A route built to diagnose
over-spending must not itself spend.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from utils.pivot_auth import require_api_key

logger = logging.getLogger("api.uw_spend")

router = APIRouter(prefix="/uw", tags=["uw-spend"])

#: The table's own sizing convention: max(observed, projected) x ~1.2. Headroom is reported
#: against THIS, not against the bare quota, because a tag sitting at 1.0x its own measured
#: peak is already the failure -- that is exactly how `snapshot` broke.
SIZING_MULTIPLIER = 1.2


def _headroom(quota: int, used: int) -> Dict[str, Any]:
    """Room left, stated three ways so no reader has to compute the interesting one.

    `calls_left` is the blunt figure. `pct_used` is what a dashboard wants. `over_sizing_rule`
    is the one that would have caught this outage BEFORE it happened: a tag whose usage has
    reached quota/1.2 has no safety margin left under the rule the table was built with, even
    though it has not technically breached anything yet.
    """
    safe_ceiling = int(quota / SIZING_MULTIPLIER) if quota else 0
    return {
        "calls_left": quota - used,
        "pct_used": round(100.0 * used / quota, 1) if quota else None,
        "safe_ceiling_at_1_2x": safe_ceiling,
        "over_sizing_rule": used > safe_ceiling,
        "at_or_over_quota": used >= quota,
    }


@router.get("/spend")
async def uw_spend(uw_day: Optional[str] = Query(
                       None, description="UW day (YYYY-MM-DD). Defaults to today's UW day, "
                                         "whose boundary is 20:00 ET, not midnight."),
                   _=Depends(require_api_key)) -> Dict[str, Any]:
    """Per caller tag for one UW day: quota, used, 429s, headroom. Read-only."""
    from integrations import uw_spend_ledger as ledger
    from integrations.uw_governor import (
        DAILY_BUDGET, FOREIGN_RESERVE_QUOTAS, QUOTAS, quota_for,
    )

    try:
        day = date.fromisoformat(uw_day) if uw_day else ledger.uw_day()
    except ValueError:
        return {"error": "uw_day must be YYYY-MM-DD", "uw_day": uw_day}

    # THE QUERY LIVES IN THE LEDGER MODULE, not here. This route had the SELECT inline first
    # and the R-IV.1052(b) first-boot guard failed it: "a READ path queries a table the startup
    # migrations do not create". `day_detail` runs the ledger's own DDL before reading, so the
    # read cannot depend on a writer, and the schema keeps one author. Fixed at the cause
    # rather than by widening the debt register -- which is what that register is for.
    #
    # The error is NAMED and propagated, never swallowed into zeros: a spend of 0 and "I could
    # not read the spend" are opposite facts, and reporting the second as the first is how a
    # quota outage hides.
    detail = await ledger.day_detail(day)
    used_by_caller: Dict[str, Dict[str, int]] = detail.get("callers") or {}
    read_error: Optional[str] = detail.get("error")
    if read_error:
        logger.error("[uw_spend] ledger read failed: %s", read_error)

    callers: Dict[str, Dict[str, Any]] = {}
    for tag in sorted(set(QUOTAS) | set(FOREIGN_RESERVE_QUOTAS) | set(used_by_caller)):
        quota, tier = quota_for(tag)
        rec = used_by_caller.get(tag)
        registered = tag in QUOTAS or tag in FOREIGN_RESERVE_QUOTAS
        entry: Dict[str, Any] = {
            "quota": quota,
            "tier": tier,
            "registered": registered,
            # An absent row means NO CALLS RECORDED, which is genuinely zero for a day that
            # has begun -- but if the read itself failed, `used` is null and says so.
            "used": None if read_error else (rec or {}).get("used", 0),
            "rate_limited": None if read_error else (rec or {}).get("rate_limited", 0),
            "funded_from": ("foreign_reserve" if tag in FOREIGN_RESERVE_QUOTAS
                            else "daily_budget" if tag in QUOTAS else "default_quota"),
        }
        if not registered:
            entry["note"] = ("not in QUOTAS: running on the unknown-code-path default, which "
                             "is the `outcome_resolver` fault -- register it or retire it")
        if entry["used"] is not None:
            entry.update(_headroom(quota, entry["used"]))
        callers[tag] = entry

    committed = sum(q for q, _ in QUOTAS.values())
    exceeded = sorted(t for t, e in callers.items() if e.get("at_or_over_quota"))
    tight = sorted(t for t, e in callers.items()
                   if e.get("over_sizing_rule") and not e.get("at_or_over_quota"))

    return {
        "uw_day": day.isoformat(),
        "uw_day_basis": "the UW day boundary is 20:00 ET (uw_spend_ledger.uw_day), not midnight",
        "read_error": read_error,
        "sizing_multiplier": SIZING_MULTIPLIER,
        "budget": {
            "daily_budget": DAILY_BUDGET,
            "committed_quota": committed,
            "account_total_used": (None if read_error
                                   else sum(v["used"] for v in used_by_caller.values())),
        },
        # The two lists a reader actually acts on, so nobody has to scan 40 tags to find them.
        "at_or_over_quota": exceeded,
        "over_sizing_rule_only": tight,
        "callers": callers,
    }
