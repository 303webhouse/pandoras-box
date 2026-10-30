"""R-IV.1451(f): the CROWD futures row is ranked against the 52 most recent earlier weeks.

Relay RELAY_ABACUS_to_BUILD_2026-10-29_crowd-cftc-window-59: the route fetched 60 report dates
and ranked the newest against all 59 earlier ones, so the tile read "the last 59 weekly
readings" where R-IV.1369(f)4 rules 52.
"""
from __future__ import annotations

import datetime as _dt

from api import crowd
from models import crowd_b6 as cb


def _rows(weeks: int, total_for):
    """Socrata-shaped rows, ES and NQ, `weeks` Tuesdays newest first; total_for(i) is week i's
    ES+NQ net (i=0 newest), split evenly so the sum is exact."""
    es, nq = cb.CFTC_CONTRACTS["ES"], cb.CFTC_CONTRACTS["NQ"]
    newest = _dt.date(2026, 10, 27)
    out = []
    for i in range(weeks):
        d = (newest - _dt.timedelta(days=7 * i)).isoformat() + "T00:00:00.000"
        half = total_for(i) / 2.0
        for name in (es, nq):
            out.append({"report_date_as_yyyy_mm_dd": d, "contract_market_name": name,
                        "lev_money_positions_long": str(1_000_000 + half),
                        "lev_money_positions_short": "1000000"})
    return out


def _total(i):
    # Newest (i=0) reads 0. Weeks 1..52 read +1..+52 above it except the first 20 below it,
    # and the 7 OLDEST (53..59) are all far below, so ranking them too would raise the rank.
    if i == 0:
        return 0.0
    if i <= 52:
        return -float(i) if i <= 20 else float(i)
    return -1_000_000.0


def test_SIXTY_WEEKS_FETCHED_RANKS_AGAINST_THE_52_MOST_RECENT_EARLIER_ONES():
    blk = crowd._cftc_block(_rows(60, _total))
    assert len(blk["history"]) == cb.FULL_WINDOW == 52
    assert blk["as_of"] == _dt.date(2026, 10, 27)
    # The ranked weeks are 1..52, newest first: the 7 oldest (53..59) are not among them.
    assert blk["history"][0] == _total(1) and blk["history"][-1] == _total(52)
    assert -1_000_000.0 not in blk["history"]

    row = cb.cftc_row(blk["nets"], blk["history"], blk["as_of"], today=_dt.date(2026, 10, 30))
    assert row["history_n"] == 52 and row["history_full"] == 52
    assert row["thin"] is False

    # THE PERCENTILE MOVES: the same reading ranked against all 59 earlier weeks reads higher.
    all59 = [_total(i) for i in range(1, 60)]
    assert cb.percentile(0.0, all59) != row["pct"]
    assert cb.percentile(0.0, blk["history"]) == row["pct"]


def test_FEWER_THAN_52_EARLIER_WEEKS_ARE_ALL_RANKED_AND_MARKED_THIN():
    blk = crowd._cftc_block(_rows(30, _total))
    assert len(blk["history"]) == 29
    row = cb.cftc_row(blk["nets"], blk["history"], blk["as_of"], today=_dt.date(2026, 10, 30))
    assert row["history_n"] == 29 and row["thin"] is True
