"""PYTHIA feed health — R-IV.1037(c)2. `rejecting` / `quiet` / `flowing`, and nothing else.

WHY THIS IS A SEPARATE AXIS FROM ok/stale/dark. Those three describe the LEVELS: how many
sessions behind the newest event is. They cannot distinguish "the market is quiet" from "every
alert is being refused", and the market-profile tool's own description already admits it
"CANNOT distinguish an upstream outage from a quiet market and does not try". The v2.6 cutover
is exactly that case: 65 consecutive 401s, and the surface reported `ok` with
`sessions_behind: 0` because the newest stored event was from the same session. So feed health
is reported BESIDE the freshness verdict, never folded into it.

THE DEFINITIONS, as ruled:

    rejecting   any rejected request since the last accepted event
    quiet       no accepted event for more than 3 RTH hours AND no rejections
    flowing     otherwise

`rejecting` is tested FIRST and needs no time window at all: one refusal since the last
accepted event is enough, because a refusal is positive evidence that something is arriving and
being turned away. "Quiet" is the absence of evidence and therefore needs a threshold.

RTH HOURS, NOT WALL HOURS, and that distinction is the whole reason this file has a calendar in
it. Three wall hours spans a whole overnight: a feed that stopped at 16:05 ET would read `quiet`
at 19:05 with the market shut, which says nothing about the feed. Three RTH hours is three hours
of time in which an event COULD have arrived.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("pythia.feed_health")

ET = ZoneInfo("America/New_York")

#: Regular trading hours, in ET. An event can only arrive while the market is open, so this is
#: the window elapsed time is measured inside.
RTH_OPEN, RTH_CLOSE = time(9, 30), time(16, 0)

#: R-IV.1037(c)2's threshold, in RTH hours.
QUIET_AFTER_RTH_HOURS = 3.0

REJECTING = "rejecting"
QUIET = "quiet"
FLOWING = "flowing"
UNKNOWN = "unknown"

#: Distinct from all three on purpose. "I could not read the feed's state" is not "the feed is
#: flowing", and defaulting to the healthy value is how a broken check reports health.
FEED_STATES = (REJECTING, QUIET, FLOWING, UNKNOWN)


def _is_trading_day(d: date) -> bool:
    """The exchange calendar, with a NAMED fallback.

    A holiday is not RTH, so counting it would inflate elapsed RTH hours and call a healthy
    feed `quiet`. `is_trading_day` RAISES past its enumerated horizon rather than guessing,
    which is right -- so the fallback here is weekday-only AND logged, never silent.
    """
    try:
        from stable_engine.market_calendar import is_trading_day
        return bool(is_trading_day(d))
    except Exception:                                               # noqa: BLE001
        logger.debug("[feed_health] %s outside the enumerated calendar; weekday fallback", d)
        return d.weekday() < 5


def rth_hours_between(start: datetime, end: datetime) -> float:
    """Hours of REGULAR TRADING TIME between two instants. Never negative.

    Walks the calendar days the interval touches and sums each day's overlap with
    09:30-16:00 ET. Both ends are converted to ET first, because a UTC date boundary falls in
    the middle of an ET session (convention #39).
    """
    if start is None or end is None:
        return 0.0
    a, b = start.astimezone(ET), end.astimezone(ET)
    if b <= a:
        return 0.0
    total = 0.0
    d = a.date()
    while d <= b.date():
        if _is_trading_day(d):
            o = datetime.combine(d, RTH_OPEN, tzinfo=ET)
            c = datetime.combine(d, RTH_CLOSE, tzinfo=ET)
            lo, hi = max(a, o), min(b, c)
            if hi > lo:
                total += (hi - lo).total_seconds() / 3600.0
        d += timedelta(days=1)
    return total


def classify(last_accepted_at: Optional[datetime],
             rejected_since_last_accept: Optional[int],
             *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The feed's state, with the figures it was decided from.

    `rejected_since_last_accept = None` means NOT MEASURED, which is not zero: it returns
    `unknown` rather than letting an unreadable count read as "no rejections".
    """
    now = now or datetime.now(timezone.utc)
    out: Dict[str, Any] = {
        "feed_health": UNKNOWN,
        "last_accepted_at": (last_accepted_at.astimezone(timezone.utc).isoformat()
                             if last_accepted_at else None),
        "last_accepted_at_et": (last_accepted_at.astimezone(ET).isoformat()
                                if last_accepted_at else None),
        "rejected_since_last_accept": rejected_since_last_accept,
        "rth_hours_since_last_accept": None,
        "quiet_after_rth_hours": QUIET_AFTER_RTH_HOURS,
        "basis": "",
    }

    if rejected_since_last_accept is None:
        out["basis"] = ("the rejection count could not be read, so nothing is claimed -- "
                        "'unknown' is NOT 'flowing'")
        return out

    # REJECTING FIRST, and it needs no window: one refusal since the last accepted event is
    # positive evidence that alerts are arriving and being turned away.
    if rejected_since_last_accept > 0:
        out["feed_health"] = REJECTING
        out["basis"] = ("%d request(s) rejected since the last accepted event -- alerts ARE "
                        "arriving and are being refused. A 401 is silent on TradingView's "
                        "side, so this is the only place it shows."
                        % rejected_since_last_accept)
        if last_accepted_at:
            out["rth_hours_since_last_accept"] = round(
                rth_hours_between(last_accepted_at, now), 2)
        return out

    if last_accepted_at is None:
        out["basis"] = ("no accepted event has ever been recorded and no rejections were "
                        "seen, so there is nothing to judge")
        return out

    hrs = rth_hours_between(last_accepted_at, now)
    out["rth_hours_since_last_accept"] = round(hrs, 2)
    if hrs > QUIET_AFTER_RTH_HOURS:
        out["feed_health"] = QUIET
        out["basis"] = ("no accepted event for %.2f RTH hours (threshold %.1f) and no "
                        "rejections. RTH hours, not wall hours: three wall hours spans an "
                        "overnight, in which nothing COULD arrive."
                        % (hrs, QUIET_AFTER_RTH_HOURS))
        return out

    out["feed_health"] = FLOWING
    out["basis"] = ("an accepted event %.2f RTH hours ago and no rejections since"
                    % hrs)
    return out
