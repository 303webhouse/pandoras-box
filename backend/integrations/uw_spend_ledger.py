"""Durable per-caller UW spend, per UW day, kept 90 days — R-IV.886(e).

WHY THIS EXISTS. The governor's own counters live in Redis with a 48-HOUR TTL, so when SPINE
asked for ten sessions of per-caller spend the answer was two days — and both of them happened
to be non-sessions (Saturday 10-11 and a pre-market Monday). A quota resize fitted to that would
be fitted to noise. This table is independent of those counters and keeps 90 days, so the same
question has an answer next week and every week after.

IT IS A SEPARATE STORE, NOT A LONGER TTL. Raising the Redis TTL would have been one line, but
the counters are also the governor's live input: they are read on the hot path, they must stay
cheap, and they are deliberately allowed to vanish (fail-open) so an infra blip never blocks a
UW call. A measurement record wants the opposite properties — durable, append-only, queryable by
day. Two different jobs, two stores.

THE DAY IS THE **UW** DAY, NOT THE UTC DAY. UW's cap resets at 20:00 ET, so a call at 21:00 ET
belongs to the NEXT UW day while still being the same UTC date. The Redis counters key on
`date.today()` (UTC on Railway) and therefore straddle the boundary by up to four hours. Getting
that wrong would blur the one number the resize depends on -- a day's peak -- so `uw_day()` is
computed from ET and tested at both edges.

NOTHING HERE GATES A CALL. It records what already happened. A failure to record is logged and
dropped: the measurement must never be the reason a UW request does not go out.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("uw.spend_ledger")

ET = ZoneInfo("America/New_York")

# UW's daily counter resets at 20:00 ET (18:00 after 2026-11-01 per the collector's own clock,
# but the RESET itself is 20:00 ET year-round as far as the cap is concerned).
UW_DAY_ROLLOVER_HOUR_ET = 20

RETENTION_DAYS = 90

TABLE = "uw_caller_spend_daily"

DDL = """
CREATE TABLE IF NOT EXISTS uw_caller_spend_daily (
    uw_day      DATE NOT NULL,
    caller      TEXT NOT NULL,
    requests    INTEGER NOT NULL DEFAULT 0,
    rate_limited INTEGER NOT NULL DEFAULT 0,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (uw_day, caller)
)
"""

DDL_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_uw_caller_spend_day "
    "ON uw_caller_spend_daily (uw_day DESC)"
)


def uw_day(now: Optional[datetime] = None) -> date:
    """The UW day a moment belongs to.

    At or after 20:00 ET the account's counter has reset, so the call belongs to the NEXT
    calendar day's UW window. Before that it belongs to today's. Expressed in ET because that is
    the clock UW resets on; the server runs UTC and would place 21:00 ET on the wrong day.
    """
    now = now or datetime.now(timezone.utc)
    et = now.astimezone(ET)
    if et.hour >= UW_DAY_ROLLOVER_HOUR_ET:
        return (et + timedelta(days=1)).date()
    return et.date()


async def record(caller: str, *, rate_limited: bool = False, n: int = 1,
                 now: Optional[datetime] = None, pool=None) -> bool:
    """Add n requests for `caller` on the current UW day. NEVER RAISES.

    Upsert rather than insert: one row per (uw_day, caller), so the table stays one row per
    caller per day however many calls that day holds.
    """
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        day = uw_day(now)
        async with pool.acquire() as conn:
            await conn.execute(DDL)
            await conn.execute(DDL_INDEX)
            await conn.execute(
                "INSERT INTO uw_caller_spend_daily (uw_day, caller, requests, rate_limited)"
                " VALUES ($1,$2,$3,$4)"
                " ON CONFLICT (uw_day, caller) DO UPDATE SET"
                "   requests = uw_caller_spend_daily.requests + $3,"
                "   rate_limited = uw_caller_spend_daily.rate_limited + $4,"
                "   last_seen = NOW()",
                day, caller or "untagged", int(n), 1 if rate_limited else 0,
            )
        return True
    except Exception as exc:                                        # noqa: BLE001
        # Dropped, not raised: a measurement must never be why a UW call does not go out.
        logger.warning("[uw_spend_ledger] not recorded for %s: %s", caller, type(exc).__name__)
        return False


async def prune(pool=None) -> int:
    """Drop rows older than RETENTION_DAYS. Returns the number removed, or -1 on failure."""
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(DDL)
            res = await conn.execute(
                "DELETE FROM uw_caller_spend_daily WHERE uw_day < CURRENT_DATE - $1::int",
                RETENTION_DAYS,
            )
        try:
            return int(str(res).strip().split()[-1])
        except (ValueError, IndexError):
            return 0
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[uw_spend_ledger] prune failed: %s", type(exc).__name__)
        return -1


async def day_detail(day: date, pool=None) -> Dict[str, Any]:
    """Per-caller spend for ONE UW day: {caller: {used, rate_limited}}. R-IV.1059(c).

    THE SQL LIVES HERE, not in the route, for two reasons that turned out to be the same one.
    This module is the single author of `uw_caller_spend_daily`'s schema and queries, and it
    runs `DDL` before reading -- so the read cannot depend on a writer having created the
    table, which is R-IV.1052(b)'s rule.

    The route was written with the SELECT inline first, and MY OWN first-boot guard failed it:
    "a READ path queries a table the startup migrations do not create". Moving the query here
    fixes the finding at its cause rather than widening the debt register, and it leaves the
    route a thin HTTP shell over this function. `summary()` above already had this shape; the
    route simply needed the per-day grain that `summary()`'s aggregate cannot express.

    Returns {} with `error` set when the read fails. NEVER partial-silently: a caller that gets
    {} and no error would read "nobody spent anything today", which is the opposite of "I could
    not look".
    """
    out: Dict[str, Any] = {"uw_day": day.isoformat(), "callers": {}, "error": None}
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(DDL)
            rows = await conn.fetch(
                "SELECT caller, requests, rate_limited FROM uw_caller_spend_daily"
                " WHERE uw_day = $1", day)
        out["callers"] = {r["caller"]: {"used": int(r["requests"] or 0),
                                       "rate_limited": int(r["rate_limited"] or 0)}
                          for r in rows}
    except Exception as exc:                                        # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
        logger.error("[uw_spend_ledger] day_detail(%s) failed: %s", day, out["error"])
    return out


async def summary(days: int = 10, pool=None) -> Dict[str, Any]:
    """Per-caller max / median / total over the last `days` UW DAYS THAT HAVE ROWS.

    "Days that have rows" and not "the last N calendar days" on purpose: a weekend has no
    session and padding it with zeros would halve a median for reasons that have nothing to do
    with spend. The count of days actually covered is returned, so a figure can never be read as
    resting on more evidence than it has (strategy-lab §3.4's lesson, applied to quotas).
    """
    out: Dict[str, Any] = {"days_requested": days, "days_covered": 0, "callers": {},
                           "account_total_by_day": {}}
    try:
        if pool is None:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(DDL)
            days_rows = await conn.fetch(
                "SELECT DISTINCT uw_day FROM uw_caller_spend_daily"
                " ORDER BY uw_day DESC LIMIT $1", days)
            covered: List[date] = [r["uw_day"] for r in days_rows]
            out["days_covered"] = len(covered)
            if not covered:
                return out
            rows = await conn.fetch(
                "SELECT caller,"
                "       MAX(requests) AS max_req,"
                "       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY requests) AS median_req,"
                "       SUM(requests) AS total_req,"
                "       SUM(rate_limited) AS total_429,"
                "       COUNT(*) AS n_days"
                "  FROM uw_caller_spend_daily WHERE uw_day = ANY($1::date[])"
                " GROUP BY caller ORDER BY max_req DESC", covered)
            out["callers"] = {
                r["caller"]: {
                    "max": int(r["max_req"] or 0),
                    "median": float(r["median_req"] or 0),
                    "total": int(r["total_req"] or 0),
                    "rate_limited": int(r["total_429"] or 0),
                    "days_present": int(r["n_days"] or 0),
                } for r in rows
            }
            totals = await conn.fetch(
                "SELECT uw_day, SUM(requests) AS t FROM uw_caller_spend_daily"
                " WHERE uw_day = ANY($1::date[]) GROUP BY uw_day ORDER BY uw_day DESC", covered)
            out["account_total_by_day"] = {
                r["uw_day"].isoformat(): int(r["t"] or 0) for r in totals}
    except Exception as exc:                                        # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out
