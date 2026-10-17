"""R-IV.1195(d) — stops and targets are evaluated on POST-FIRE price action only.

THE FAULT, in one sentence: a short fired at 11:00 was "stopped" by its own 10:00 rally.

`score_signals.py` fetched daily bars `start=created_at.date()` and walked them from the first
row, so the signal-day bar -- which contains the whole session, including everything before the
signal existed -- decided the outcome. The same frame fed `max_favorable` / `max_adverse`, so
the favourable-excursion figures were also measured partly before the fire.

`outcome_resolver.py` already skipped pre-fire bars (`bar_ts < signal_ts: continue`), and that
half was correct. What it did wrong was the other half of this ruling: a row with no usable fire
timestamp hit a bare `continue`, which is not UNGRADEABLE. It stayed PENDING and was re-selected
on every 15-minute pass forever -- a silent hole in the book that also spent a vendor call each
time.

THE THREE TESTS THE RULING NAMES are the first three below. The rest exist because introducing a
new value into a field other code reads needs a census of its readers (Convention #29), and that
census found two places that would have miscounted:

  - score_signals.get_signal_stats() totals every non-PENDING row, so UNGRADEABLE would have
    inflated the denominator of every hit rate on the dashboard.
  - b2_options_resolver selects `outcome IS NOT NULL AND outcome_source = 'BAR_WALK'` and treats
    any outcome outside ("WIN","HIT_T1","HIT_T2") as the losing side -- so an UNGRADEABLE row
    tagged BAR_WALK would have had a LOSING OPTIONS P&L fabricated for it.

NEW GRADES ONLY. This ruling orders no historical regrade, so nothing here backfills and no
test asserts a change to an already-graded row.
"""
from __future__ import annotations

import datetime as dt
import os
import re

import pytest

from ._srcscan import code_of_file, function_code, read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORE = os.path.join(BACKEND, "jobs", "score_signals.py")
RESOLVER = os.path.join(BACKEND, "jobs", "outcome_resolver.py")


class _Bar:
    """A minimal stand-in for a pandas index entry: all `first_gradeable_bar_index` needs."""

    def __init__(self, d):
        self._d = d

    def date(self):
        return self._d


class _Frame:
    """Just enough of a DataFrame for the index walk. Deliberately NOT pandas: the function
    under test must work off the index alone, and a real frame would let an accidental
    column read pass unnoticed."""

    def __init__(self, days):
        self.index = [_Bar(d) for d in days]


# ── the three tests R-IV.1195(d) names ─────────────────────────────────────

def test_A_SHORT_FIRED_AT_11_IS_NOT_STOPPED_BY_ITS_PRE_FIRE_RALLY():
    """THE RULED TEST. The signal-day daily bar holds the 10:00 rally that crossed the stop.
    That bar must not be evaluated, so grading starts at the next session."""
    from jobs.score_signals import first_gradeable_bar_index
    fired = dt.datetime(2026, 10, 14, 15, 0)        # 11:00 ET
    frame = _Frame([dt.date(2026, 10, 14), dt.date(2026, 10, 15), dt.date(2026, 10, 16)])
    first = first_gradeable_bar_index(frame, fired)
    assert first == 1, "the signal-day bar is index 0 and must be dropped"
    assert frame.index[first].date() == dt.date(2026, 10, 15)


def test_POSITIVE_CONTROL_a_POST_FIRE_move_through_the_stop_IS_graded():
    """Without this, a function that returned None forever would satisfy the test above. The
    sessions after the fire are exactly what remains gradeable."""
    from jobs.score_signals import first_gradeable_bar_index
    fired = dt.datetime(2026, 10, 14, 15, 0)
    frame = _Frame([dt.date(2026, 10, 14), dt.date(2026, 10, 15), dt.date(2026, 10, 16)])
    first = first_gradeable_bar_index(frame, fired)
    remaining = [b.date() for b in frame.index[first:]]
    assert remaining == [dt.date(2026, 10, 15), dt.date(2026, 10, 16)]
    assert dt.date(2026, 10, 14) not in remaining


def test_A_MISSING_FIRE_TIME_GIVES_UNGRADEABLE():
    """THE RULED TEST. And in both graders -- they have separate helpers because they read
    different columns, so one of them being right would not have made the other right."""
    from jobs.outcome_resolver import _has_usable_fire_time
    from jobs.score_signals import has_usable_fire_time
    for fn in (has_usable_fire_time, _has_usable_fire_time):
        assert fn(None) is False
        assert fn(dt.datetime(2026, 10, 16, 0, 0, 0)) is False, (
            "a midnight-exact stamp is a DATE in a timestamp column (Convention #39), and "
            "grading on it means grading from the top of the session")
        assert fn(dt.date(2026, 10, 16)) is False, "a plain date has no time at all"
        assert fn(dt.datetime(2026, 10, 16, 15, 0, 0)) is True


# ── the boundaries of "after the fire" ─────────────────────────────────────

def test_a_fire_with_NO_LATER_SESSION_stays_PENDING_not_UNGRADEABLE():
    """Different states. "No session has completed since the fire" grades tomorrow; "this row
    can never be graded" never does. Conflating them would retire rows early."""
    from jobs.score_signals import first_gradeable_bar_index
    fired = dt.datetime(2026, 10, 16, 15, 0)
    assert first_gradeable_bar_index(_Frame([dt.date(2026, 10, 16)]), fired) is None


def test_the_signal_day_bar_is_dropped_however_early_the_fire():
    """Even a 09:31 fire leaves a minute of pre-fire action in the daily bar, and the ruling
    forbids the full signal-day bar outright rather than by a threshold."""
    from jobs.score_signals import first_gradeable_bar_index
    frame = _Frame([dt.date(2026, 10, 14), dt.date(2026, 10, 15)])
    for h, m in ((13, 31), (19, 59), (15, 0)):
        assert first_gradeable_bar_index(frame, dt.datetime(2026, 10, 14, h, m)) == 1


def test_the_grader_SLICES_THE_FRAME_before_the_excursion_figures():
    """`max_favorable` / `max_adverse` were computed over a frame that included the signal day,
    so the best excursion on record might never have happened after the signal existed."""
    code = function_code(SCORE, "score_pending_signals")
    i = code.index("first_gradeable_bar_index")
    j = code.index("max_favorable")
    assert i < j, "the slice must happen BEFORE the excursion maxima are taken"
    assert "df.iloc[first:]" in code[i:j]


def test_the_resolver_STILL_skips_pre_fire_bars():
    """The half that was already right. A fix to the other half must not disturb it."""
    code = function_code(RESOLVER, "_walk_touch")
    assert "bar_ts < signal_ts" in code
    assert "continue" in code


def test_neither_grader_falls_back_to_the_full_signal_day():
    """R-IV.1195(d) names this fallback specifically."""
    code = function_code(SCORE, "score_pending_signals")
    # The frame still STARTS at the signal day -- that is the vendor call's start date -- but
    # the walk must not begin there.
    assert "first_gradeable_bar_index" in code
    assert not re.search(r"for\s+_,\s*bar\s+in\s+df\.iterrows\(\)", code[:code.index(
        "first_gradeable_bar_index")]), "no walk may precede the slice"


# ── UNGRADEABLE is terminal, and the census (Convention #29) ───────────────

def test_UNGRADEABLE_is_TERMINAL_not_a_skip():
    """A bare `continue` left the row PENDING to be re-selected on every pass forever."""
    code = function_code(RESOLVER, "resolve_outcomes") if _has(RESOLVER, "resolve_outcomes") \
        else code_of_file(RESOLVER)
    assert "_mark_ungradeable" in code
    writer = function_code(RESOLVER, "_mark_ungradeable")
    assert "UPDATE signals" in writer
    assert "outcome IS NULL" in writer, (
        "guarded, so a row that got a real outcome between the read and the write is not "
        "overwritten by this one")


def _has(path, name):
    try:
        function_code(path, name)
        return True
    except Exception:
        return False


def test_the_UNGRADEABLE_SOURCE_IS_NOT_BAR_WALK():
    """THE CENSUS FINDING THAT MATTERS MOST. b2_options_resolver selects
    `outcome IS NOT NULL AND outcome_source = 'BAR_WALK'`, then treats any outcome outside
    ("WIN","HIT_T1","HIT_T2") as the losing side. Tagging an ungradeable row BAR_WALK would
    fabricate a LOSING OPTIONS P&L for a signal that was never graded."""
    from jobs.outcome_resolver import UNGRADEABLE_SOURCE
    assert UNGRADEABLE_SOURCE != "BAR_WALK"
    b2 = read_source(os.path.join(BACKEND, "jobs", "b2_options_resolver.py"))
    assert "outcome_source = 'BAR_WALK'" in b2, (
        "b2's predicate is what keeps UNGRADEABLE out; if it stops filtering on the source, "
        "this exclusion silently stops working")
    # And the losing-side test that makes it dangerous is still written that way.
    assert '("WIN", "HIT_T1", "HIT_T2")' in b2 or '"WIN", "HIT_T1", "HIT_T2"' in b2


def test_UNGRADEABLE_IS_EXCLUDED_FROM_THE_HIT_RATE_DENOMINATOR():
    """The other census finding. `get_signal_stats` totals every non-PENDING row, so this value
    would have inflated the denominator of every hit rate on the dashboard with rows that have
    no outcome. It is not an outcome; it is the admission that there isn't one.

    (The function is `get_hit_rates`. I first wrote `get_signal_stats` here, from the docstring
    rather than the def line, and the helper refused by name rather than scanning the whole
    module and matching something unrelated -- which is what that helper is for.)"""
    code = function_code(SCORE, "get_hit_rates")
    assert "NOT IN ('PENDING', 'UNGRADEABLE')" in code
    assert "outcome != 'PENDING'" not in code


def test_the_value_fits_the_column_in_both_tables():
    """`signal_outcomes.outcome` is VARCHAR(20) and `signals.outcome` is VARCHAR(30). A longer
    word would raise at the write, at 21:00 ET, on a row nobody was watching."""
    from jobs.outcome_resolver import OUTCOME_UNGRADEABLE
    from jobs.score_signals import OUTCOME_UNGRADEABLE as S
    assert OUTCOME_UNGRADEABLE == S == "UNGRADEABLE"
    assert len(OUTCOME_UNGRADEABLE) <= 20
    ddl = code_of_file(os.path.join(BACKEND, "database", "postgres_client.py"))
    assert "outcome VARCHAR(20)" in ddl


def test_NO_HISTORICAL_REGRADE_in_this_ruling():
    """R-IV.1195(d): "New grades only." Neither grader may rewrite a row that already has an
    outcome -- both select on an unresolved row, and the UNGRADEABLE write is guarded too."""
    resolver = code_of_file(RESOLVER)
    assert "outcome IS NULL" in resolver
    score = code_of_file(SCORE)
    assert "outcome = 'PENDING'" in score
    for banned in ("UPDATE signals SET outcome = $1 WHERE signal_id = $2 AND TRUE",):
        assert banned not in resolver
