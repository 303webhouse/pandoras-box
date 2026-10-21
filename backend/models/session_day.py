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


#: THE EXCHANGE SESSION of a timestamp. R-IV.1272(b)1 says a closure's trade date is "fill_time's
#: ET date, labelled as such", and that is a DIFFERENT QUESTION from the one `day_sql` answers.
#:
#:   `day_sql`   answers "which of the PRINCIPAL'S days did this land on" -- the Abacus census's
#:               question, measured over 557 rows, with the midnight-UTC discriminator because
#:               that column holds days-written-down as well as moments.
#:   this one    answers "which EXCHANGE SESSION was this trade in". A session belongs to the
#:               exchange's clock, not the principal's, so it is Eastern with no discriminator.
#:
#: They differ in practice, not just in theory: a fill at 05:00 UTC is 23:00 the previous day in
#: Mountain and 01:00 the SAME day in Eastern, so the two rules return different dates. Using
#: `day_sql` for a trade date would date a late-evening fill to the session before it.
#:
#: `day_sql` IS DELIBERATELY NOT CHANGED. It is the predicate Abacus windows its period figures
#: on, and moving it would move trades between periods -- the exact silent reclassification its
#: own byte-identical test was written to prevent.
#:
#: BUT THE MIDNIGHT-UTC DISCRIMINATOR IS KEPT, and it had to be, measured on the two closures
#: that still carry no date (1942 and 1943, written 2026-10-13 before the column existed):
#:
#:     lot 3900   stored 2026-10-09 00:00:00 UTC   as written 2026-10-09 Fri   ET 2026-10-08 Thu
#:     lot 3901   stored 2026-10-12 00:00:00 UTC   as written 2026-10-12 Mon   ET 2026-10-11 SUN
#:     lot 3947   stored 2026-10-19 06:00:00 UTC   as written 2026-10-19 Mon   ET 2026-10-19 Mon
#:
#: R-IV.1272(b)1 says "fill_time's ET date", and a BLANKET ET conversion would have dated lot
#: 3901's trade to a SUNDAY -- a day the exchange was shut. A midnight-UTC stamp is a DAY
#: WRITTEN DOWN, not a moment, and converting it moves it backwards; that is the same finding
#: R-IV.726 measured over 557 rows, and it does not stop being true because the target column
#: changed. So the ruling's ET rule applies to the case it describes -- a real fill time -- and
#: a day written down is taken as written. Lot 3947, the row that decayed, is unaffected: its
#: 06:00 UTC is Mountain midnight, not UTC midnight, and both branches give 2026-10-19.
SESSION_DATE_SQL = (
    "(CASE WHEN ({c} AT TIME ZONE 'UTC')::time = TIME '00:00:00' "
    "THEN ({c} AT TIME ZONE 'UTC')::date "
    "ELSE ({c} AT TIME ZONE 'America/New_York')::date END)")

#: The basis label written beside the date, so the row says WHERE the date came from (R-IV.1272(b)1,
#: "labelled as such"). A figure whose derivation is not recorded is one a later reader has to
#: guess at, and the guess is usually "the obvious one".
#:
#: TWO LABELS, because there are two readings and a reader must be able to tell which applied.
#: Derived from THE SAME DISCRIMINATOR as the date, in the same statement, so the date and its
#: label cannot disagree -- a date carrying the wrong basis is worse than a date carrying none.
BASIS_FILL_TIME_ET = "FILL_TIME_ET"
BASIS_FILL_TIME_DAY = "FILL_TIME_DAY"

SESSION_BASIS_SQL = (
    "(CASE WHEN ({c} AT TIME ZONE 'UTC')::time = TIME '00:00:00' "
    "THEN '%s' ELSE '%s' END)" % (BASIS_FILL_TIME_DAY, BASIS_FILL_TIME_ET))

#: Reserved and NOT USED, with the reason written down rather than left as an empty branch:
#: R-IV.1272(b)1 prefers "the disposal lot's broker action date", and `position_lots` HAS NO SUCH
#: COLUMN. Its date-bearing fields are `fill_time` (NOT NULL, the lot's own record of when the
#: trade happened) and `verified_at`, whose own comment states it is "the time of the MATCH, never
#: of the fill". So there is exactly one usable source today, and the label says so on every row
#: instead of a nullable column implying a second source exists.
BASIS_BROKER_ACTION = "BROKER_ACTION"


def session_date_sql(col: str = "fill_time") -> str:
    """The exchange session a stored fill_time denotes, by the rule above."""
    return SESSION_DATE_SQL.format(c=col)


def session_basis_sql(col: str = "fill_time") -> str:
    """The label for the branch `session_date_sql` took on the same value."""
    return SESSION_BASIS_SQL.format(c=col)


#: The trade date of a closure, derived from ITS OWN DISPOSAL LOT rather than from a clock or a
#: caller. R-IV.1265(b): `position_lot_closures.trade_date` is the session the disposal happened
#: in, and the disposal lot is the row that records the disposal -- so the two cannot disagree,
#: and no caller can pass a day the lot does not support. Substituted into the INSERT as the
#: `trade_date` value, with the disposal lot's id as the parameter.
#:
#: Written as a SELECT inside the INSERT, deliberately, rather than read in Python first: a
#: separate read could race the lot's own write and would put the derivation in three places.
TRADE_DATE_FROM_DISPOSAL = (
    "(SELECT %s FROM position_lots WHERE id = $%%d)" % session_date_sql())

#: The matching basis, from the SAME row and the SAME discriminator.
TRADE_BASIS_FROM_DISPOSAL = (
    "(SELECT %s FROM position_lots WHERE id = $%%d)" % session_basis_sql())


def trade_date_from_disposal(param_index: int) -> str:
    """`TRADE_DATE_FROM_DISPOSAL` bound to a parameter position, e.g. `$2` for the disposal id."""
    return TRADE_DATE_FROM_DISPOSAL % int(param_index)


#: THE PAIR, EMITTED TOGETHER. The date and the label that says where it came from have to agree,
#: and the way they come to disagree is one INSERT naming the column and forgetting the value --
#: so the columns and the values are produced by one helper each and a test asserts both appear
#: at every site. A date with the wrong basis beside it is worse than a date with none.
TRADE_DATE_COLUMNS = "trade_date, trade_date_basis"


def trade_basis_from_disposal(param_index: int) -> str:
    return TRADE_BASIS_FROM_DISPOSAL % int(param_index)


def trade_date_values(param_index: int) -> str:
    """The VALUES fragment matching `TRADE_DATE_COLUMNS`, bound to the disposal lot's parameter.

    The basis is DERIVED, not a constant: with two readings of a fill_time there are two labels,
    and hard-coding one would have labelled every day-written-down row as a converted one.
    """
    i = int(param_index)
    return "%s, %s" % (trade_date_from_disposal(i), trade_basis_from_disposal(i))
