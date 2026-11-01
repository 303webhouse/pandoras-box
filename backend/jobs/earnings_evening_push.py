"""The evening earnings push — R-IV.1461(h), as ruled by R-IV.1472(b).

ONE PHONE NOTIFICATION AN EVENING, at 15:00 MT (17:00 ET) on trading days and on Sundays:
tonight's after-the-close (AMC) reporters and the next session's before-the-open (BMO)
reporters, limited to names held in the book (YOURS) and the ten largest S&P 500 members by
market cap. Each line: ticker, BMO/AMC, the implied move, YOURS, and for tonight's AMC names
the after-hours move once there is a post-market print -- "after-hours move not yet available"
when there is not, never blank. Nothing else: no beat/miss call, no trade language.

CHANNEL: ntfy, never Discord (R-IV.1472(b)2; the principal asked 10-12 that alerts not go
through Discord if they do not have to). Sent through integrations.ntfy_push, which never logs
the topic and refuses a payload carrying a money figure. The text also goes through the
no-orders lint (services.regime_playbook.order_findings) first; a finding stops the send.

THE TOP TEN (R-IV.1472(b)1): S&P 500 members ranked by market cap -- the stand-in Hermes
already uses -- not SPY's own weights (no weights feed is bought). Membership has to be pieced
together, because `earnings_calendar.is_sp500` exists only on rows fetched since 10-31 and is
NULL on most of the largest names (they reported before it existed), while non-members such as
TSM and ASML sit in the same table. So a ticker counts as a member when ANY of its rows says
is_sp500, or it is in `sector_constituents` (the 11 sector SPDRs hold only S&P 500 names; that
table was last refreshed 2026-03-27) -- and never when its newest row says is_sp500 = false.
Rank = its newest row's market cap.

AT MOST ONE AN EVENING: a `job_runs` row per MT date; a completed one (ok or
completed_defective) stops a second send, across restarts and deploys.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

MT = ZoneInfo("America/Denver")
ET = ZoneInfo("America/New_York")
CALLER_TAG = "earnings_push"
#: The send window, MT. A process that boots after it waits for tomorrow rather than pushing late.
SEND_FROM_MT = time(15, 0)
SEND_UNTIL_MT = time(16, 0)
TOP_N = 10
NO_AH = "after-hours move not yet available"
FEED_EMPTY = "earnings feed empty"
TITLE = "Pandora: earnings tonight"
#: R-IV.1472(b)4: "First send Mon 11-02 15:00 MT". Without this the Sunday rule would have sent
#: a first, empty list on Sun 11-01.
FIRST_SEND = date(2026, 11, 2)

TOP_SQL = """
WITH latest AS (
    SELECT DISTINCT ON (ticker) ticker, market_cap, is_sp500
    FROM earnings_calendar
    WHERE market_cap IS NOT NULL
    ORDER BY ticker, report_date DESC
)
SELECT l.ticker
FROM latest l
WHERE l.is_sp500 IS DISTINCT FROM FALSE
  AND (EXISTS (SELECT 1 FROM earnings_calendar e WHERE e.ticker = l.ticker AND e.is_sp500)
       OR EXISTS (SELECT 1 FROM sector_constituents s WHERE s.ticker = l.ticker))
ORDER BY l.market_cap DESC
LIMIT $1
"""


# ── when ────────────────────────────────────────────────────────────────────────────────────

def push_day(d: date) -> Optional[bool]:
    """Trading days and Sundays. None past the calendar's horizon (never guessed)."""
    from stable_engine.market_calendar import is_trading_day_or_none
    if d.weekday() == 6:
        return True
    return is_trading_day_or_none(d)


def due(now_mt: datetime) -> bool:
    return (now_mt.date() >= FIRST_SEND and bool(push_day(now_mt.date()))
            and SEND_FROM_MT <= now_mt.time() < SEND_UNTIL_MT)


def evening_frame(today: date) -> Tuple[Optional[date], date]:
    """(the date whose AMC reporters are 'tonight' -- None on a Sunday or a holiday --,
    the next session whose BMO reporters are included)."""
    from stable_engine.market_calendar import is_trading_day, next_trading_day
    tonight = today if is_trading_day(today) else None
    return tonight, next_trading_day(today)


# ── who ─────────────────────────────────────────────────────────────────────────────────────

async def top_members(n: int = TOP_N) -> Optional[List[str]]:
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(TOP_SQL, n)
        return [r["ticker"] for r in rows]
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[earnings_push] top-%d read failed: %s", n, type(exc).__name__)
        return None


def select(rows: List[Dict[str, Any]], tonight: Optional[date], nxt: date,
           top: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(tonight's AMC rows, the next session's BMO rows): held or top-ten names only, held
    first, then by market cap."""
    topset = set(top or [])
    keep = [r for r in rows if r.get("yours") or r.get("ticker") in topset]
    key = (lambda r: (not r.get("yours"), -(r.get("market_cap") or 0), r.get("ticker") or ""))
    amc = sorted([r for r in keep if tonight and r["report_date"] == tonight
                  and r.get("timing") == "AMC"], key=key)
    bmo = sorted([r for r in keep if r["report_date"] == nxt and r.get("timing") == "BMO"],
                 key=key)
    return amc, bmo


# ── the after-hours move ────────────────────────────────────────────────────────────────────

def _parse(ts: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


async def ah_move(ticker: str, session: date) -> Optional[float]:
    """Percent from `session`'s regular close to the latest post-market print, or None when
    there is no post-market print after 16:00 ET on `session` (or the quote is unreadable).

    The post-market print is UW's /stock-state (the read the hub's quote uses: during the
    post-market `close` is the last trade); the regular close is the date-checked regular-session
    bar from uw_api._get_regular_session_change, never /stock-state's rolling prev_close.
    """
    from integrations import uw_api
    try:
        state = await uw_api._uw_request("/api/stock/%s/stock-state" % ticker.upper(),
                                         caller=CALLER_TAG)
        if not isinstance(state, dict) or not isinstance(state.get("data"), dict):
            return None
        d = state["data"]
        if str(d.get("market_time") or "").lower() != "postmarket":
            return None
        at = _parse(d.get("tape_time"))
        if at is None:
            return None
        at_et = at.astimezone(ET)
        if at_et.date() != session or at_et.time() < time(16, 0):
            return None
        last = float(d.get("close"))
        reg = await uw_api._get_regular_session_change(ticker.upper())
        if not isinstance(reg, dict) or str(reg.get("today_date") or "")[:10] != session.isoformat():
            return None
        close = float(reg.get("today_close") or 0)
        if not close:
            return None
        return (last / close - 1.0) * 100.0
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[earnings_push] after-hours read failed for %s: %s",
                       ticker, type(exc).__name__)
        return None


# ── what ────────────────────────────────────────────────────────────────────────────────────

def _imp(r: Dict[str, Any]) -> str:
    v = r.get("implied_move_pct")
    return "implied ±%.1f%%" % v if v is not None else "implied move not available"


def line(r: Dict[str, Any], ah: Optional[str] = None) -> str:
    """ "AAPL AMC implied ±3.7% · after hours +2.1%" -- dates, times and the market's numbers."""
    bits = [r["ticker"], r.get("timing") or "", _imp(r)]
    if r.get("yours"):
        bits.append("YOURS")
    head = " ".join(b for b in bits if b)
    return "%s · %s" % (head, ah) if ah else head


def build_text(today: date, tonight: Optional[date], nxt: date,
               amc: List[Tuple[Dict[str, Any], Optional[float]]],
               bmo: List[Dict[str, Any]], feed_empty: bool) -> str:
    day = lambda d: d.strftime("%a %m-%d")                                  # noqa: E731
    if feed_empty:
        return "%s: no rows for %s%s." % (FEED_EMPTY, day(nxt),
                                          (" or tonight" if tonight else ""))
    out = []
    if tonight:
        out.append("Tonight after the close (%s):" % day(tonight))
        if amc:
            for r, mv in amc:
                out.append(line(r, ("after hours %+.1f%%" % mv) if mv is not None else NO_AH))
        else:
            out.append("none of your names or the 10 largest.")
    out.append("%s before the open:" % day(nxt))
    if bmo:
        out.extend(line(r) for r in bmo)
    else:
        out.append("none of your names or the 10 largest.")
    out.append("Your names and the 10 largest S&P 500 members by market cap.")
    return "\n".join(out)


def lint(text: str) -> List[str]:
    from services.regime_playbook import order_findings
    return order_findings(text)


# ── the run ─────────────────────────────────────────────────────────────────────────────────

async def run_evening_push(now: Optional[datetime] = None, *, send=None, fetch=None,
                           top=None, ah=None) -> Dict[str, Any]:
    """Build, lint, send once, record. `send`/`fetch`/`top`/`ah` are seams for tests only."""
    from jobs.job_runs import (JOB_EARNINGS_PUSH, STATUS_COMPLETED_DEFECTIVE, STATUS_ERROR,
                               STATUS_OK, finish_run, has_completed, start_run)
    from services.read_only import earnings as earn

    now_mt = (now or datetime.now(timezone.utc)).astimezone(MT)
    today = now_mt.date()
    done = await has_completed(JOB_EARNINGS_PUSH, today)
    if done:
        return {"sent": False, "reason": "already sent for %s" % today}
    if done is None:
        # Unreadable is not "not sent": a second push is worse than a missed one.
        return {"sent": False, "reason": "job_runs unreadable; not risking a second push"}

    run_id = await start_run(JOB_EARNINGS_PUSH, today)
    try:
        tonight, nxt = evening_frame(today)
        rows = await (fetch or earn.fetch_earnings)(tonight or nxt, nxt)
        if rows is None:
            await finish_run(run_id, STATUS_ERROR, error="earnings_calendar unreadable")
            return {"sent": False, "reason": "earnings_calendar unreadable"}
        tops = await (top or top_members)()
        if tops is None:
            await finish_run(run_id, STATUS_ERROR, error="top-10 read failed")
            return {"sent": False, "reason": "top-10 read failed"}
        feed_empty = not any(r["report_date"] == nxt for r in rows)
        amc_rows, bmo = select(rows, tonight, nxt, tops)
        amc = []
        for r in amc_rows:
            amc.append((r, await (ah or ah_move)(r["ticker"], tonight)))
        text = build_text(today, tonight, nxt, amc, bmo, feed_empty)
        findings = lint(text)
        if findings:
            # Completed-defective, not error: the text would fail the same way in a minute, so
            # retrying is pointless; the evening is done and the row says why.
            await finish_run(run_id, STATUS_COMPLETED_DEFECTIVE,
                             skip_reason="NOT sent (no-orders lint): " + text[:800],
                             error="no-orders lint: %s" % findings[:3])
            return {"sent": False, "reason": "no-orders lint", "findings": findings, "text": text}
        if send is None:
            from integrations.ntfy_push import send as send
        res = await send("EARNINGS", "evening list %s" % today.isoformat(), text, title=TITLE)
        ok = bool(res.get("sent"))
        names = ",".join([r["ticker"] for r, _ in amc] + [r["ticker"] for r in bmo]) or "none"
        await finish_run(run_id, STATUS_OK if ok else STATUS_ERROR,
                         rows_touched=len(amc) + len(bmo),
                         skip_reason=("sent: " if ok else "NOT sent: ") + text[:900],
                         error=None if ok else str(res.get("reason"))[:200])
        logger.info("[earnings_push] %s for %s: %s", "sent" if ok else "NOT sent", today, names)
        return {"sent": ok, "text": text, "names": names, "result": res}
    except Exception as exc:                                        # noqa: BLE001
        await finish_run(run_id, STATUS_ERROR, error="%s: %s" % (type(exc).__name__, str(exc)[:200]))
        logger.error("[earnings_push] failed: %s", type(exc).__name__, exc_info=True)
        return {"sent": False, "reason": type(exc).__name__}


async def earnings_push_loop() -> None:
    """Every minute: inside the 15:00-16:00 MT window on a push day, send once."""
    import asyncio
    await asyncio.sleep(120)
    while True:
        try:
            now_mt = datetime.now(timezone.utc).astimezone(MT)
            if due(now_mt):
                res = await run_evening_push()
                if not res.get("sent") and not str(res.get("reason", "")).startswith("already"):
                    # A failed send retries, but every 5 minutes, not every minute.
                    await asyncio.sleep(240)
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("[earnings_push] loop error: %s", type(exc).__name__)
        await asyncio.sleep(60)
