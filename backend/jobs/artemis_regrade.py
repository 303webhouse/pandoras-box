"""The ARTEMIS_SHORT one-shot regrade (R-IV.1392(d), R-IV.1441(d)): pure replay half.

`outcome_resolver` and `score_signals` only select ungraded rows, so the post-fire fix (6c4f943e)
never reaches the 2,770 ARTEMIS_SHORT rows graded before it. This module recomputes what the
FIXED grader gives for a row -- by REPLAYING the live job, not by one walk over all bars:

  * score_signals runs at 21:00 ET on NYSE trading days. Each night it walks every bar from the
    fire to that night, and the FIRST night with an outcome freezes the row. So a T1 touch on
    day 2 is HIT_T1 for good even if the stop is hit on day 3; one walk over all bars would call
    that STOPPED_OUT. Replaying night by night is the only faithful regrade.
  * A row still without an outcome on a night when it is more than MAX_SIGNAL_AGE_DAYS old is
    EXPIRED that night, before any walk.
  * The walk itself is `score_signals.walk_outcome`, imported -- never reimplemented.

`sliced=False` replays the PRE-fix grader (no post-fire slice) so a dry run can tell a change
the fix caused from replay noise (a missed night, a revised bar).

Nothing here touches a database or the network.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from jobs.score_signals import (ET, MAX_SIGNAL_AGE_DAYS, GRADER_VERSION, _nyse_holidays, _to_utc,
                                first_gradeable_bar_index, has_usable_fire_time, walk_outcome,
                                OUTCOME_UNGRADEABLE)

SIGNAL_TYPE = "ARTEMIS_SHORT"
RUN_HOUR_ET = 21                      # bias_scheduler: CronTrigger(mon-fri, hour=21, tz=ET)
REGRADE_GRADER_VERSION = GRADER_VERSION


def trading_nights(first: date, last: date) -> List[date]:
    """NYSE trading days in [first, last] by score_signals' own calendar (is_trading_day)."""
    hol = set()
    for y in range(first.year - 1, last.year + 2):
        hol |= _nyse_holidays(y)
    out, d = [], first
    while d <= last:
        if d.weekday() < 5 and d not in hol:
            out.append(d)
        d += timedelta(days=1)
    return out


def _run_instant(night: date) -> datetime:
    return datetime.combine(night, time(RUN_HOUR_ET, 0), tzinfo=ET).astimezone(timezone.utc)


def replay(bars, row: Dict[str, Any], *, until: date, sliced: bool = True) -> Dict[str, Any]:
    """What score_signals would have written for `row`, run every trading night up to `until`.

    `bars` is a daily frame (index = session timestamps, columns High/Low/Close) for the row's
    symbol, as `yf.Ticker(sym).history(...)` returns it. `row` carries the signal_outcomes fields
    (created_at, direction, entry, stop, t1, t2, invalidation_level).

    Returns {outcome, outcome_price, days_to_outcome, max_favorable, max_adverse, night}, with
    outcome "PENDING" when no night up to `until` produced one.
    """
    created_raw = row["created_at"]
    created = _to_utc(created_raw)
    num = lambda k: float(row[k]) if row.get(k) is not None else None
    entry, stop, t1, t2, inv = (num("entry"), num("stop"), num("t1"), num("t2"),
                                num("invalidation_level"))
    start_day = created.date()                        # history(start=created_at UTC date)
    first_night = created.astimezone(ET).date()
    result = {"outcome": "PENDING", "outcome_price": None, "days_to_outcome": None,
              "max_favorable": None, "max_adverse": None, "night": None}
    for night in trading_nights(first_night, until):
        now = _run_instant(night)
        if now < created:
            continue                                  # the row did not exist at that run
        age = (now - created).days
        if age > MAX_SIGNAL_AGE_DAYS:
            return dict(result, outcome="EXPIRED", days_to_outcome=age, night=night.isoformat())
        if sliced and not has_usable_fire_time(created_raw):
            return dict(result, outcome=OUTCOME_UNGRADEABLE, days_to_outcome=age,
                        night=night.isoformat())
        days = [ts.date() if hasattr(ts, "date") else ts for ts in bars.index]
        keep = [start_day <= d <= night for d in days]
        df = bars[keep]
        if df is None or df.empty:
            continue
        if sliced:
            first = first_gradeable_bar_index(df, created)
            if first is None:
                continue
            df = df.iloc[first:]
            if df.empty:
                continue
        if entry is None:
            return result
        outcome, price, mfe, mae = walk_outcome(df, row["direction"], entry, stop, t1, t2, inv)
        if outcome:
            return {"outcome": outcome, "outcome_price": price, "days_to_outcome": age,
                    "max_favorable": round(mfe, 2), "max_adverse": round(mae, 2),
                    "night": night.isoformat()}
    return result


WIN, LOSS = {"HIT_T1", "HIT_T2"}, {"STOPPED_OUT"}


def side(outcome: Optional[str]) -> str:
    """win / loss / other -- the direction a change is reported in (R-IV.1441(d)1)."""
    return "win" if outcome in WIN else "loss" if outcome in LOSS else "other"


def tally(pairs: Iterable[tuple]) -> Dict[str, int]:
    """Count (stored, regraded) outcome pairs by direction of change."""
    out: Dict[str, int] = {}
    for before, after in pairs:
        if before == after:
            key = "unchanged"
        else:
            key = "%s->%s" % (side(before), side(after))
            if side(before) == side(after):
                key += " (%s->%s)" % (before, after)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))
