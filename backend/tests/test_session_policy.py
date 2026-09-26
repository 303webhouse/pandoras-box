"""The River's session policy — R-IV.565, decided by R-IV.587(b).

Controls as the ruling states them, plus a restart between the hold and the release.
"""

import ast
import importlib
import io
import os
from datetime import datetime, timedelta, timezone

import pytest

from models.signal_timeframe import UnknownTimeframe
from signals import session_policy as sp
from stable_engine import sessions

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTC = timezone.utc


def _code_without_docstrings(rel):
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return src


def _et(dt):
    return sessions.to_et(dt).strftime("%a %H:%M")


# ───────────────────────────────── the rule itself

class TestTheRule:

    def test_intraday_during_hours_is_delivered(self):
        action, release, _ = sp.decide("15", datetime(2026, 9, 24, 19, 45))
        assert action == sp.DELIVER and release is None

    def test_intraday_outside_hours_is_dropped(self):
        """Its setup is gone before anyone can act on it."""
        for utc in (datetime(2026, 9, 25, 1, 0),     # 21:00 ET, after hours
                    datetime(2026, 9, 25, 11, 0),    # 07:00 ET, pre-market
                    datetime(2026, 9, 26, 17, 0)):   # a Saturday
            action, release, _ = sp.decide("15", utc)
            assert action == sp.DROP, _et(utc)
            assert release is None

    def test_swing_outside_hours_is_held_to_the_next_open(self):
        action, release, _ = sp.decide("DAILY", datetime(2026, 9, 25, 1, 0))
        assert action == sp.HOLD
        assert _et(release) == "Fri 09:30"

    def test_a_weekend_and_a_holiday_are_the_same_case(self):
        """Neither is special-cased: the walk asks the calendar a day at a time."""
        friday_night = sp.decide("DAILY", datetime(2026, 9, 26, 1, 0))[1]   # Fri 21:00 ET
        sunday = sp.decide("DAILY", datetime(2026, 9, 27, 17, 0))[1]        # Sun 13:00 ET
        assert _et(friday_night) == _et(sunday) == "Mon 09:30"

    def test_weekly_is_held_not_dropped(self):
        action, release, _ = sp.decide("W", datetime(2026, 9, 26, 2, 0))
        assert action == sp.HOLD and release is not None

    def test_the_release_is_the_open_and_not_midnight(self):
        release = sp.decide("DAILY", datetime(2026, 9, 25, 1, 0))[1]
        et = sessions.to_et(release)
        assert (et.hour, et.minute) == (9, 30)
        assert sessions.session_at(release) == sessions.REGULAR


class TestWhereItRefusesToDecide:
    """Two unknowns, failing in opposite directions on purpose."""

    def test_an_unreadable_calendar_delivers_rather_than_drops(self):
        """'The market was shut' and 'nobody knows' are different claims. A policy that dropped
        on a missing answer would discard a family the day the holiday table ran out."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sp.sessions, "session_at", lambda _: None)
            action, release, why = sp.decide("15", datetime(2026, 9, 25, 1, 0))
        assert action == sp.DELIVER and release is None
        assert "could not answer" in why
        # POSITIVE CONTROL: the same instant IS dropped when the calendar can answer.
        assert sp.decide("15", datetime(2026, 9, 25, 1, 0))[0] == sp.DROP

    def test_an_unrecognised_spelling_delivers_rather_than_drops(self):
        """R-IV.584(a) refuses rather than guessing a band, and dropping on a guessed band is
        the silent discard that rule exists to prevent."""
        action, _, why = sp.decide("nonsense", datetime(2026, 9, 25, 1, 0))
        assert action == sp.DELIVER
        assert "not in the vocabulary" in why
        with pytest.raises(UnknownTimeframe):
            sp.is_intraday("nonsense")

    def test_no_fire_time_delivers(self):
        assert sp.decide("15", None)[0] == sp.DELIVER

    def test_a_missing_timeframe_is_intraday_because_the_ruling_says_so(self):
        """R-IV.565: 'webhooks by timeframe, none = intraday'. ABSENCE, which the ruling gives a
        default, is a different case from a word nobody added, which is refused above.

        Measured before wiring it: 1 of 23,155 rows has a null timeframe, a July shadow-test row
        long since EXPIRED. The default governs nothing real today.
        """
        for empty in (None, "", "   "):
            assert sp.decide(empty, datetime(2026, 9, 25, 1, 0))[0] == sp.DROP, repr(empty)
        # ...and during hours it is delivered like anything else: the default decides the BAND,
        # not the outcome.
        assert sp.decide(None, datetime(2026, 9, 24, 19, 45))[0] == sp.DELIVER

    def test_no_next_open_inside_the_horizon_delivers(self):
        """Held until a date nobody can name is worse than shown early."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sp, "_next_regular_open", lambda _: None)
            action, release, why = sp.decide("DAILY", datetime(2026, 9, 25, 1, 0))
        assert action == sp.DELIVER and release is None
        assert "horizon" in why


# ───────────────────────────────── (b)1 and (b)2: the hold is in the data

class TestTheHoldLivesInTheRow:

    def test_is_held_is_the_twin_of_the_sql(self):
        assert sp.SERVE_RELEASED_SQL == "(release_at IS NULL OR release_at <= NOW())"
        now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
        assert sp.is_held(now + timedelta(minutes=1), now) is True
        assert sp.is_held(now - timedelta(minutes=1), now) is False
        assert sp.is_held(now, now) is False           # released exactly now is served
        assert sp.is_held(None, now) is False          # NULL means serve it

    def test_a_naive_stamp_is_read_as_utc(self):
        """The column is `TIMESTAMP`, naive UTC, which is the RV1 lesson applied here."""
        now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
        assert sp.is_held(datetime(2026, 9, 25, 12, 30), now) is True
        assert sp.is_held(datetime(2026, 9, 25, 11, 30), now) is False

    @pytest.mark.parametrize("rel", ["signals/feed_service.py", "api/trade_ideas.py"])
    def test_every_feed_asks_the_database_on_every_query(self, rel):
        """THE RESTART CONTROL, first half. The predicate is in the SQL, so the question is
        re-answered by the database each time a feed is read — there is no moment at which a
        process decided a row was released and remembered it."""
        code = _code_without_docstrings(rel)
        assert "SERVE_RELEASED_SQL" in code, rel
        # and never retyped: one author, as with the crypto predicate
        assert "release_at IS NULL" not in code, rel

    def test_nothing_holds_a_signal_in_memory(self):
        """THE RESTART CONTROL, second half. A hold kept in a module-level container would be
        lost on the next deploy, releasing everything early, once, silently — and this process
        restarts on every deploy."""
        code = _code_without_docstrings("signals/session_policy.py")
        tree = ast.parse(code)
        containers = [t.id for node in tree.body if isinstance(node, ast.Assign)
                      for t in node.targets
                      if isinstance(t, ast.Name)
                      and isinstance(node.value, (ast.Dict, ast.List, ast.Set))]
        assert not containers, containers

    def test_a_restart_between_the_hold_and_the_release_changes_nothing(self):
        """THE RESTART CONTROL itself. The verdict is a pure function of the stamp and the
        clock, so reloading every module involved — which is what a deploy does — cannot move
        it. Held before, held after; released before, released after."""
        release_at = datetime(2026, 9, 28, 13, 30)
        before_open = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
        after_open = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)

        assert sp.is_held(release_at, before_open) is True
        assert sp.is_held(release_at, after_open) is False

        reloaded = importlib.reload(sp)
        assert reloaded.is_held(release_at, before_open) is True
        assert reloaded.is_held(release_at, after_open) is False
        assert reloaded.SERVE_RELEASED_SQL == sp.SERVE_RELEASED_SQL
        # POSITIVE CONTROL: the reload really did rebind the module object.
        assert reloaded is sp


# ───────────────────────────────── (b)3: the clock starts at the release

class TestTheExpiryCountsFromTheRelease:

    def test_it_counts_from_the_release_when_there_is_one(self):
        fired = datetime(2026, 9, 26, 1, 0)
        release = datetime(2026, 9, 28, 13, 30)
        assert sp.expiry_counts_from(fired, release) == release
        assert sp.expiry_counts_from(fired, None) == fired

    def test_a_held_swing_signal_is_not_dead_before_the_bell(self):
        """THE DEFECT this half prevents: a 24-hour idea held from Friday evening and counting
        its life from firing would expire before Monday's open — the opposite of holding it."""
        from signals.pipeline import calculate_expiry

        release = datetime(2026, 9, 28, 13, 30)
        expiry = calculate_expiry({"timeframe": "DAILY", "release_at": release})
        assert expiry == release + timedelta(hours=24)
        assert expiry > release

        # POSITIVE CONTROL: with no hold, the clock still starts now.
        before = datetime.utcnow()
        unheld = calculate_expiry({"timeframe": "DAILY"})
        assert abs((unheld - before).total_seconds() - 24 * 3600) < 5

    def test_an_aware_release_is_reduced_to_the_naive_utc_the_column_holds(self):
        from signals.pipeline import calculate_expiry

        aware = datetime(2026, 9, 28, 13, 30, tzinfo=UTC)
        naive = datetime(2026, 9, 28, 13, 30)
        assert (calculate_expiry({"timeframe": "DAILY", "release_at": aware})
                == calculate_expiry({"timeframe": "DAILY", "release_at": naive}))


# ───────────────────────────────── (b)4: both stamps are served

class TestBothStampsAreServed:

    def test_a_delivered_row_and_a_pre_rule_row_are_the_same_shape(self):
        """`release_at` is None for both, so the page never has to work out which case it is
        looking at, and no backfill is needed."""
        from signals.feed_service import tag_row

        row = tag_row({"signal_type": "GOLDEN_TOUCH",
                       "timestamp": datetime(2026, 9, 24, 19, 45)})
        assert row["held"] is False
        assert row["fired_at"] == datetime(2026, 9, 24, 19, 45)

    def test_a_held_row_says_so_and_keeps_its_fire_time(self):
        """The fire time is NOT rewritten to the release: it is the only record of when the
        setup appeared, and every outcome study reads it."""
        from signals.feed_service import tag_row

        fired = datetime(2026, 9, 26, 1, 0)
        row = tag_row({"signal_type": "GOLDEN_TOUCH", "timestamp": fired,
                       "release_at": datetime(2099, 1, 1)})
        assert row["held"] is True
        assert row["fired_at"] == fired
        assert row["session"] == sessions.CLOSED      # when it fired, not when it releases

    def test_both_stamps_parse_the_same_way_whatever_shape_they_arrive_in(self):
        from signals.feed_service import tag_row

        as_objects = tag_row({"timestamp": datetime(2026, 9, 26, 1, 0),
                              "release_at": datetime(2099, 1, 1)})
        as_strings = tag_row({"timestamp": "2026-09-26T01:00:00+00:00",
                              "release_at": "2099-01-01T00:00:00+00:00"})
        assert as_objects["held"] == as_strings["held"] is True
        assert as_objects["session"] == as_strings["session"]


# ───────────────────────────────── R-IV.590(b): the drop is countable

class TestADropIsARow:

    def test_the_pipeline_persists_it_rather_than_bailing_out(self):
        """R-IV.565(1) keeps dropped signals for the record. I had followed this file's
        existing 'mark REJECTED and return' pattern, which never persists — the same
        uncountable shape R-IV.584(d) had just replaced for conflicts, reintroduced one ruling
        later in a different function."""
        code = _code_without_docstrings("signals/pipeline.py")
        assert "_persist_withheld" in code
        # The old shape, gone: a mark-and-return that never reached the table.
        assert "return signal_data" in code
        assert '"REJECTED"' not in code.split("_persist_withheld")[0][-1200:]

    def test_it_is_written_in_two_steps_and_the_reason_is_the_insert(self):
        """`log_signal` writes `"SHADOW" if status == "SHADOW" else "ACTIVE"`, discarding every
        other status (DEF-SIGNAL-STATUS-DISCARDED). Passing WITHHELD straight in would land the
        row ACTIVE — on the feed, the exact opposite of withholding it."""
        import inspect

        from database import postgres_client as pc
        from signals import pipeline

        insert = inspect.getsource(pc.log_signal)
        assert '"SHADOW" if signal_data.get("status") == "SHADOW" else "ACTIVE"' in insert

        src = inspect.getsource(pipeline._persist_withheld)
        assert "log_signal" in src and "set_state" in src

    def test_it_uses_the_same_state_a_conflict_uses(self):
        """Same fact: nobody judged the setup, it just cannot be shown. `session_policy` says
        WHICH withholding it was, so the two are separable without a second state."""
        from models.signal_lifecycle import WITHHELD, columns_for

        assert columns_for(WITHHELD) == ("WITHHELD", "WITHHELD")
        code = _code_without_docstrings("signals/pipeline.py")
        assert "intraday outside regular hours" in code

    def test_a_shadow_signal_is_neither_withheld_nor_held(self):
        """A shadow row is not on an actionable surface, so there is nothing to withhold or hold
        it back FROM, and writing either would put a policy decision in a lane that must not
        have one. Both branches carry the guard — the drop had it and the hold did not."""
        code = _code_without_docstrings("signals/pipeline.py")
        assert "if _action == DROP and not shadow:" in code
        assert "if _action == HOLD and not shadow:" in code
