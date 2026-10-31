"""`GET /api/event-strip` — B4's live Event Strip.

Four sources, and the payload names each one beside the figures it produced, because they fail
independently and a strip that goes quiet should say WHICH part went quiet:

  * MACRO: Unusual Whales' economic calendar (one cached call, TTL 1800s - no new spend).
  * BOOK EXPIRIES: `unified_positions`, the book's own expiry dates.
  * EARNINGS COUNTS: the `earnings_calendar` table CHRONOS maintains, which already carries
    `in_position_book` - so "3 reporting, 1 of them yours" needs no second pass over the book.
  * BUYBACK BLACKOUT: an ESTIMATE from a published heuristic, carrying its rule. There is no
    public per-issuer blackout calendar.

A source that fails leaves its own field empty and names itself in `degraded`. The strip is
still drawn: the sessions, the OpEx date and the blackout estimate need no vendor at all.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from utils.pivot_auth import require_api_key

from models import event_strip_b4 as es
from stable_engine import market_calendar as mc

logger = logging.getLogger("api_event_strip")

router = APIRouter(prefix="/event-strip", tags=["event-strip"])

SESSIONS = 10


def _is_trading_day(d: _dt.date):
    """The calendar's own answer, THREE-STATE, passed through rather than rounded.

    `is_trading_day_or_none` returns None when it cannot answer, and the strip treats None as
    "show the day" -- hiding a session because the calendar was unsure would silently shorten
    the window, and a day shown in error is visible while a day dropped is not.
    """
    try:
        return mc.is_trading_day_or_none(d)
    except Exception:                                               # noqa: BLE001
        return None


async def _macro() -> (List[Dict[str, Any]], Optional[str]):
    try:
        from integrations import uw_api

        raw = await uw_api.get_economic_calendar()
    except Exception as exc:                                        # noqa: BLE001
        return [], "economic calendar: %s" % type(exc).__name__
    if not raw:
        return [], "economic calendar: no data returned"
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        d = row.get("time") or row.get("date") or row.get("reported_period")
        name = row.get("event") or row.get("name") or ""
        day = _as_date(d)
        if day and name:
            out.append({"date": day, "name": name})
    return out, None


def _as_date(v: Any) -> Optional[_dt.date]:
    """A vendor date in any of the shapes seen, or None. Never today's date as a fallback.

    A fallback to today would put an undated event on the first column of the strip, which is
    the one Nick looks at.
    """
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(s[:len(fmt) + 2].rstrip("Z"), fmt).date()
        except ValueError:
            continue
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


async def _book_expiries(conn) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT ticker, structure, expiry FROM unified_positions "
        " WHERE UPPER(COALESCE(status,'')) = 'OPEN' AND expiry IS NOT NULL")
    out = []
    for r in rows:
        shape = (r["structure"] or "position").replace("_", " ")
        # The shape in two words, so a column reads "QQQ put spread exp" and not a full
        # structure string that would wrap the cell.
        short = "spread" if "spread" in shape else shape.split()[-1]
        out.append({"date": r["expiry"], "label": "%s %s exp" % (r["ticker"], short)})
    return out


def _session_frame(now: Optional[_dt.datetime] = None):
    """(today ET, the next session the feed check looks at, the two completed sessions whose
    reactions get the day-after row)."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    et = mc._now_et(now)
    today = et.date()
    if _is_trading_day(today) and (et.hour, et.minute) < (16, 0):
        nxt = today
    else:
        nxt = mc.next_trading_day(today)
    last = mc.last_settled_session(now)
    return today, nxt, [mc.previous_trading_day(last), last]


async def _earnings(days: int, since: _dt.date) -> Optional[List[Dict[str, Any]]]:
    """R-IV.1461(f)5: per row the ticker, timing, the market's implied move and reaction, and
    YOURS (an open position in any account). None when the table cannot be read."""
    from services.read_only import earnings as earn
    today = _dt.date.today()
    rows = await earn.fetch_earnings(since, today + _dt.timedelta(days=days * 2))
    if rows is None:
        return None
    return [dict(r, date=r["report_date"], in_book=r["yours"]) for r in rows]


@router.get("")
async def get_event_strip(_: str = Depends(require_api_key)) -> Dict[str, Any]:
    # GATED, and found by the suite's own auth guard rather than by me: this handler reads
    # `unified_positions`, which is the book. `require_api_key` accepts the browser's signed
    # session cookie as well as a machine header, so the panel keeps working while an
    # unauthenticated caller gets 401 instead of Nick's expiries.
    degraded: List[str] = []
    try:
        from database.postgres_client import get_postgres_client

        today = _dt.date.today()
        macro, macro_err = await _macro()
        if macro_err:
            degraded.append(macro_err)
        expiries: List[Dict[str, Any]] = []
        earnings: List[Dict[str, Any]] = []
        try:
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                expiries = await _book_expiries(conn)
        except Exception as exc:                                    # noqa: BLE001
            degraded.append("book expiries: %s" % type(exc).__name__)
        _today_et, next_session, reaction_dates = _session_frame()
        got = await _earnings(SESSIONS, min(reaction_dates))
        earnings_read = got is not None
        if not earnings_read:
            degraded.append("earnings_calendar: unreadable")
        earnings = got or []

        strip = es.build_strip(today, is_trading_day=_is_trading_day, macro=macro,
                              book_expiries=expiries, earnings=earnings, sessions=SESSIONS,
                              next_session=next_session, reaction_dates=reaction_dates,
                              earnings_read=earnings_read)
        strip.update({
            "live": True,
            "sources": {
                "macro": "Unusual Whales /api/market/economic-calendar (cached, TTL 1800s)",
                "book_expiries": "unified_positions.expiry, open rows",
                "earnings": "earnings_calendar (CHRONOS, UW by date); YOURS = an open "
                            "unified_positions row in any account",
                "blackout": es.BLACKOUT_RULE,
            },
            "degraded": degraded,
            "as_of": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "field_origin": {"days": "derived", "next_opex": "derived",
                             "blackout": "derived", "earn": "stored"},
        })
        return strip
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[event-strip] failed: %s", type(exc).__name__)
        return {"live": True, "error": "%s" % type(exc).__name__, "days": [],
                "note": "the Event Strip read failed; no mock is substituted"}
