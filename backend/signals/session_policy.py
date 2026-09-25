"""When a signal may be shown — the River's session policy. R-IV.565, decided by R-IV.587(b).

THE PROBLEM. A signal fires whenever its scanner runs, which for a daily-bar strategy is often
overnight or at a weekend. It then sat on the feed reading as a live idea at 03:00, hours before
anyone could act on it, and by the open it had aged out. An intraday signal fired at the same
hour is worse: its setup is gone by morning, and showing it is showing something that no longer
exists.

THE RULE, by band:

    intraday, outside regular hours   DROP     -- the setup is gone before anyone can act
    swing or weekly, outside hours    HOLD     -- until the next regular open
    anything, during regular hours    DELIVER

HOLDING LIVES IN THE DATA (R-IV.587(b)2). A held signal is a row whose `release_at` is in the
future; the feed serves rows whose `release_at` is null or already past. Nothing waits in memory,
so a restart cannot lose a hold — and this process restarts on every deploy.

THE FIRE TIME IS KEPT. `release_at` is a second stamp, not a correction of the first. Both are
served, so the page can say when a signal fired AND when it was released. Rewriting the fire time
to the release would destroy the only record of when the setup actually appeared, which is what
every outcome study reads.

TWO PLACES THIS REFUSES TO DECIDE, and they fail in opposite directions on purpose:

  * The CALENDAR could not answer -- `session_at` returned None, meaning past its horizon or no
    readable instant. DELIVER. "The market was shut" and "nobody knows" are different claims, and
    a policy that dropped a signal on a missing answer would discard a family the day the holiday
    table ran out.
  * The TIMEFRAME spelling is not in the vocabulary. DELIVER. R-IV.584(a) refuses rather than
    guessing a band, and dropping on a guessed band is exactly the silent discard that rule
    exists to prevent.

ONE PLACE IT DOES DEFAULT, because R-IV.565 says so in terms: a signal with NO timeframe at all is
treated as INTRADAY ("webhooks by timeframe, none = intraday"). That is a different case from an
unrecognised spelling -- absence, not a word nobody added -- and it is the one input that can be
dropped without its band being known. Measured before wiring it: **1 of 23,155 rows has a null
timeframe** -- a July shadow-test row, `S1_PHASE2_SHADOW_TEST_BTC_20260713`, long since
EXPIRED -- so the default governs nothing real today. It is logged when it fires, so the
first row it ever governs says so.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Tuple

from models.signal_timeframe import UnknownTimeframe, bar_minutes, is_intraday
from stable_engine import sessions

logger = logging.getLogger(__name__)

DELIVER = "deliver"
DROP = "drop"
HOLD = "hold"

ACTIONS = (DELIVER, DROP, HOLD)

# The predicate every feed uses. One author, interpolated and never retyped -- the same reason
# `config.asset_class` exists: a feed added later without it would not error, it would just show
# held rows again.
SERVE_RELEASED_SQL = "(release_at IS NULL OR release_at <= NOW())"


def _next_regular_open(instant: datetime) -> Optional[datetime]:
    """The next instant the regular session opens, at or after `instant`, in UTC.

    Walks forward a day at a time over `market_calendar`, so a weekend and a holiday are the same
    case and neither is special-cased here. Returns None when the calendar cannot answer within
    its horizon -- the caller delivers rather than holding a signal until a date nobody can name.
    """
    et = sessions.to_et(instant)
    for _ in range(10):                       # a long weekend plus holidays, then give up
        try:
            from stable_engine.market_calendar import is_trading_day_or_none

            trading = is_trading_day_or_none(et.date())
        except Exception:  # noqa: BLE001
            return None
        if trading is None:
            return None
        if trading:
            open_et = et.replace(hour=sessions.REGULAR_OPEN.hour,
                                 minute=sessions.REGULAR_OPEN.minute,
                                 second=0, microsecond=0)
            if open_et >= et:
                return open_et.astimezone(timezone.utc)
        et = (et + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    return None


def decide(timeframe: Optional[str], fired_at: Optional[datetime],
           signal_id: Optional[str] = None) -> Tuple[str, Optional[datetime], str]:
    """`(action, release_at, reason)` for one signal.

    `release_at` is set only for HOLD. For DELIVER it is None, which is what the feed predicate
    treats as "serve it now" -- so a delivered signal and a signal from before this rule existed
    are the same row shape, and no backfill is needed.
    """
    if fired_at is None:
        return DELIVER, None, "no fire time to judge; delivered rather than guessed"

    session = sessions.session_at(fired_at)
    if session is None:
        return DELIVER, None, (
            "the session calendar could not answer; delivered, because a missing answer is not "
            "a closed market")
    if session == sessions.REGULAR:
        return DELIVER, None, "fired during regular hours"

    # Outside regular hours. Which way depends on the band, and only on the band.
    if timeframe is None or (isinstance(timeframe, str) and not timeframe.strip()):
        # R-IV.565: a webhook that names no timeframe is intraday.
        logger.info("session policy: %s carries no timeframe; treating it as intraday "
                    "(R-IV.565) — it fired %s and is being dropped", signal_id, session)
        intraday = True
    else:
        try:
            intraday = is_intraday(timeframe)
        except UnknownTimeframe:
            return DELIVER, None, (
                "timeframe %r is not in the vocabulary; delivered rather than dropped on a "
                "guessed band (R-IV.584(a))" % (timeframe,))

    if intraday:
        return DROP, None, "an intraday setup fired %s is gone before anyone can act" % session

    release_at = _next_regular_open(fired_at)
    if release_at is None:
        return DELIVER, None, (
            "no next open inside the calendar's horizon; delivered rather than held until a date "
            "nobody can name")
    return HOLD, release_at, "fired %s; held to the next regular open" % session


def is_held(release_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    """True while a row is still waiting. The Python twin of `SERVE_RELEASED_SQL`."""
    if release_at is None:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    if release_at.tzinfo is None:
        release_at = release_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return release_at > now


def expiry_counts_from(fired_at: Optional[datetime],
                       release_at: Optional[datetime]) -> Optional[datetime]:
    """When a signal's clock starts. R-IV.587(b)3.

    From `release_at` when it is set, otherwise from the fire time. A held signal that counted its
    life from firing would arrive at the open with most of it already spent -- a 24-hour swing
    idea held from Friday evening would be dead before Monday's bell, which is the opposite of
    what holding it is for.
    """
    return release_at or fired_at
