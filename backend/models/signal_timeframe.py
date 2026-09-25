"""What a signal's timeframe means, and how long it should live. R-IV.584(a).

THE DEFECT THIS REPLACES. `calculate_expiry` already keyed on `timeframe` rather than family --
that part was right, and the family correlation reported under R-IV.581 was an artifact of each
family emitting exactly one timeframe. What was wrong is how the column was READ.

Five spellings are live in it -- `15`, `60`, `D`, `DAILY`, `daily` -- matched by two hand-typed
tuples plus a digits-are-minutes branch. `"1H"` sat in the intraday tuple while `"60"`, the same
interval, went down the digit branch to the same answer: **consistent by luck, not by
construction.** And the fallback for anything unrecognised was FOUR HOURS -- the shortest lifetime
in the table. A new family writing `1h`, `1D` or `Daily` would have been given the most aggressive
expiry in the system, silently, and the only symptom would be its signals vanishing early.

R-IV.584(a): an unrecognised spelling is REFUSED AND FLAGGED, never given the shortest lifetime.

THE BANDS, which are the River's own rule:

    intraday   anything under a 4-hour bar        4 hours
    swing      4-hour bars through daily         24 hours
    weekly     weekly bars and longer             7 days

WHY MINUTES ARE THE COMMON UNIT. TradingView's `{{interval}}` is a minute COUNT for intraday
charts (`"60"`, `"240"`) and a letter for the rest (`"D"`, `"W"`). Reducing every spelling to
minutes first means the bands are compared one way rather than three, so a new spelling is a new
entry in one map instead of a new branch in a chain of `if`s.

NOTHING EMITS WEEKLY. The 7-day band has never fired. It is kept because the rule has three bands
and a band that exists only when something uses it is a band nobody notices is missing.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, Optional

MINUTE = 1
HOUR = 60
DAY = 24 * HOUR
WEEK = 7 * DAY

# Every spelling seen in the column or written by a known emitter, reduced to bar minutes.
# Keys are compared UPPER-CASED and stripped, so `daily`, `Daily` and `DAILY` are one entry.
_MINUTES: Dict[str, int] = {
    # letters (TradingView and the scanners)
    "D": DAY, "1D": DAY, "DAILY": DAY,
    "W": WEEK, "1W": WEEK, "WEEKLY": WEEK,
    "M": 30 * DAY, "1MO": 30 * DAY, "MONTHLY": 30 * DAY,
    # hour forms
    "1H": HOUR, "2H": 2 * HOUR, "4H": 4 * HOUR,
    # minute forms with a unit
    "1M": 1, "3M": 3, "5M": 5, "15M": 15, "30M": 30,
}

INTRADAY = "intraday"
SWING = "swing"
WEEKLY = "weekly"

BANDS = (INTRADAY, SWING, WEEKLY)

# The one place a band's lifetime is written down.
TTL: Dict[str, timedelta] = {
    INTRADAY: timedelta(hours=4),
    SWING: timedelta(hours=24),
    WEEKLY: timedelta(days=7),
}

# Band boundaries, in bar minutes. A 4-hour bar is the first swing bar; a weekly bar is the first
# weekly one. Inclusive at the lower edge so a bar never falls in two bands.
SWING_FROM_MINUTES = 4 * HOUR
WEEKLY_FROM_MINUTES = WEEK


class UnknownTimeframe(ValueError):
    """Raised when a timeframe spelling is not in the vocabulary.

    A refusal, deliberately, rather than a default. The old default was the SHORTEST lifetime,
    so an unrecognised spelling did not fail -- it quietly expired its family's signals four
    hours after they fired, and nothing anywhere said so.
    """


def bar_minutes(timeframe: Optional[str]) -> Optional[int]:
    """How many minutes one bar covers, or None when the spelling is not recognised.

    A bare number is minutes, which is what TradingView sends for intraday charts. `None` and
    the empty string are NOT recognised: a missing timeframe is not a 1-hour one, and treating
    it as one is how a signal with no timeframe at all got the intraday lifetime.
    """
    key = (timeframe or "").strip().upper()
    if not key:
        return None
    if key.isdigit():
        minutes = int(key)
        return minutes if minutes > 0 else None
    return _MINUTES.get(key)


def band_of(timeframe: Optional[str]) -> str:
    """`intraday`, `swing` or `weekly`. Raises `UnknownTimeframe` on anything else."""
    minutes = bar_minutes(timeframe)
    if minutes is None:
        raise UnknownTimeframe(
            "unrecognised timeframe %r — add it to models/signal_timeframe.py rather than "
            "letting it take the shortest lifetime by default" % (timeframe,))
    if minutes >= WEEKLY_FROM_MINUTES:
        return WEEKLY
    if minutes >= SWING_FROM_MINUTES:
        return SWING
    return INTRADAY


def ttl_for(timeframe: Optional[str]) -> timedelta:
    """How long a signal on this timeframe should live. Raises on an unknown spelling."""
    return TTL[band_of(timeframe)]


def is_intraday(timeframe: Optional[str]) -> bool:
    """R-IV.565 asks this question of every signal, so it is answered here.

    Raises on an unknown spelling for the same reason `ttl_for` does: the drop/hold policy drops
    an intraday signal fired outside regular hours, and a default that guessed `intraday` would
    silently discard a family whose spelling nobody had added.
    """
    return band_of(timeframe) == INTRADAY
