"""THE ONE RULE for the calendar day a stored timestamp denotes. R-IV.726, R-IV.1265(b).

WHY THIS MODULE EXISTS. The rule was measured and written once, inside `api/abacus.py`, for the
realized census. R-IV.1265(b) then needed the same rule in the POSITION WRITER, so that a
closure's `trade_date` is the trade's own session and not the clock the row happened to be
written at. Two copies of a rule this subtle disagree eventually, and the copy that disagrees is
the one nobody re-read -- so the rule moved here and both callers import it. `api/abacus.py`
keeps its measured prose and delegates the arithmetic.

THE RULE, AND WHY IT IS PER VALUE. `entry_date`, `exit_date` and `position_lots.fill_time` are
`timestamptz` holding BOTH KINDS OF THING. Measured over the 557-row census: 454 entry values
sit at exactly midnight UTC, which is A DAY WRITTEN DOWN, and 103 carry a real time of day,
which is A MOMENT. No single rule is right for both, and "convert everything to Mountain Time"
-- shipped under R-IV.705 -- was wrong for the 454:

    WRTH (948) is stored `2026-10-01 00:00:00+00`. Converted, that is 6 PM on 2026-09-30, and
    the page reported 09-30. Both Fidelity exports date its fills 10-01, and its own position_id
    reads POS_WRTH_20261001_R635_7. The day was never ambiguous; the reading of it was.

So the kind is decided PER VALUE, by the only discriminator the data offers:

  * exactly midnight UTC  -> a DAY. Taken as written; converting it moves it backwards.
  * anything else         -> a MOMENT. Converted to Mountain Time, because the principal's
                             calendar day decides which side of a cutoff a 9 PM fill falls on.

This is correct for all three conventions present in the database: a day at midnight UTC (taken
as written), a day at Mountain midnight (`snapshot_date`, `activity_date`, stored 06:00/07:00Z --
a "moment" that converts back to its own midnight), and a real fill time (converted).

THE ONE CASE IT CANNOT TELL APART is a genuine fill at exactly 00:00:00.000000 UTC, which it
reads as a day. That is 6 PM Mountain, after the close, and no such row exists in the book. If
intraday crypto fills ever land here, this needs a better discriminator than the clock -- a
column saying which kind the value is. Convention #39's standing proposal is that column.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")


def day_of(value) -> Optional[_dt.date]:
    """The calendar day `value` denotes, by the rule above. Passes a non-datetime through."""
    if value is None:
        return None
    if not isinstance(value, _dt.datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.timezone.utc)
    utc = value.astimezone(_dt.timezone.utc)
    if (utc.hour, utc.minute, utc.second, utc.microsecond) == (0, 0, 0, 0):
        return utc.date()
    return value.astimezone(MT).date()


def day_sql(col: str) -> str:
    """The same rule in SQL, for a predicate or a derived column.

    A bare date cast on a `timestamptz` with no conversion reads a 9 PM Mountain close as the
    NEXT day, which at a range boundary silently moves a trade into the wrong window.
    """
    return ("(CASE WHEN ({c} AT TIME ZONE 'UTC')::time = TIME '00:00:00' "
            "THEN ({c} AT TIME ZONE 'UTC')::date "
            "ELSE ({c} AT TIME ZONE 'America/Denver')::date END)").format(c=col)


#: The trade date of a closure, derived from ITS OWN DISPOSAL LOT rather than from a clock or a
#: caller. R-IV.1265(b): `position_lot_closures.trade_date` is the session the disposal happened
#: in, and the disposal lot is the row that records the disposal -- so the two cannot disagree,
#: and no caller can pass a day the lot does not support. Substituted into the INSERT as the
#: `trade_date` value, with the disposal lot's id as the parameter.
#:
#: Written as a SELECT inside the INSERT, deliberately, rather than read in Python first: a
#: separate read could race the lot's own write and would put the derivation in three places.
TRADE_DATE_FROM_DISPOSAL = (
    "(SELECT %s FROM position_lots WHERE id = $%%d)" % day_sql("fill_time"))


def trade_date_from_disposal(param_index: int) -> str:
    """`TRADE_DATE_FROM_DISPOSAL` bound to a parameter position, e.g. `$2` for the disposal id."""
    return TRADE_DATE_FROM_DISPOSAL % int(param_index)
