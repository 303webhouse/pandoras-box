"""An exit plan as fields — R-IV.571 / gap 3, restated by R-IV.597(b)."""

import io
import os
from datetime import date

import pytest

from models.exit_plan import (BROKER_ORDER, DAILY_CLOSE, NONE, STOP_TYPES,
                              has_exit_line, parse_exit_line, stop_type_check_sql)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The four lines live on the open rows on 2026-09-26, copied verbatim.
LIVE = {
    "PDBC": ("EXIT: invalidation daily close below 18.75 · time stop none — D5 sleeve position "
             "· stop none; counts to T1 $226.39 per TA-034"),
    "RAMZ": ("EXIT: invalidation SMH daily close above its 50-day SMA · time stop 2026-10-24 "
             "· stop none — written daily-close level. Row holds NO LOTS, so the loss alert "
             "cannot compute it (R-IV.526)."),
    "SRTY": ("EXIT: invalidation IWM daily close above its 50-day SMA · time stop 2026-10-23 "
             "· stop none — written daily-close level; counts to T1 $226.39 per TA-034"),
    "WRTH": ("EXIT: invalidation daily close below 24.50, or VIX above 30 · time stop none "
             "— income position · stop none; counts to T1 $226.39 per TA-034"),
}


class TestTheRealLines:

    @pytest.mark.parametrize("ticker", sorted(LIVE))
    def test_every_live_line_parses_with_nothing_left_over(self, ticker):
        assert parse_exit_line(LIVE[ticker])["unparsed"] == []

    def test_the_invalidations(self):
        assert parse_exit_line(LIVE["PDBC"])["invalidation"] == "daily close below 18.75"
        assert parse_exit_line(LIVE["RAMZ"])["invalidation"] == "SMH daily close above its 50-day SMA"
        assert (parse_exit_line(LIVE["WRTH"])["invalidation"]
                == "daily close below 24.50, or VIX above 30")

    def test_the_time_stops(self):
        assert parse_exit_line(LIVE["RAMZ"])["time_stop"] == date(2026, 10, 24)
        assert parse_exit_line(LIVE["SRTY"])["time_stop"] == date(2026, 10, 23)
        # "time stop none" is an absence, not an unreadable value.
        assert parse_exit_line(LIVE["PDBC"])["time_stop"] is None
        assert parse_exit_line(LIVE["PDBC"])["unparsed"] == []

    def test_the_stop_is_found_even_where_it_sits_in_the_trailing_prose(self):
        """THE MEASURED FACT. Two of the four put the stop AFTER the em dash rather than in the
        third slot. A parser that trusted the stated shape would have read stop_type as unknown
        on half the rows it was written for."""
        for ticker in LIVE:
            assert parse_exit_line(LIVE[ticker])["stop_type"] == NONE, ticker
        assert "· stop none —" in LIVE["RAMZ"]          # the stated shape
        assert "— income position · stop none;" in LIVE["WRTH"]   # and the other one


class TestItReadsTheFieldAndNotThePose:

    def test_time_stop_is_never_mistaken_for_the_stop(self):
        """Without the negative lookbehind, every row's `time stop` reads as its stop type."""
        out = parse_exit_line("EXIT: invalidation x · time stop 2026-10-24 · stop broker order")
        assert out["time_stop"] == date(2026, 10, 24)
        assert out["stop_type"] == BROKER_ORDER

    def test_a_daily_close_invalidation_is_not_read_as_a_daily_close_stop(self):
        """R-IV.597(b)2: infer nothing from other prose. Every live row's invalidation IS a
        daily-close rule, and every live row's stop field says `none`. Reading the invalidation
        as the stop would have set `daily_close` on all four and lost what was written."""
        out = parse_exit_line(LIVE["SRTY"])
        assert "daily close" in out["invalidation"]
        assert out["stop_type"] == NONE
        # POSITIVE CONTROL: a line that DOES say so gets it.
        assert parse_exit_line(
            "EXIT: invalidation x · time stop none · stop daily close at 18"
        )["stop_type"] == DAILY_CLOSE

    def test_an_undeclared_stop_is_none_the_absence_not_none_the_choice(self):
        """A row whose line omits the stop has not declared one. Defaulting it to `none` would
        say the principal chose to have no stop when nobody wrote it down — the distinction the
        loss alert already keeps between an unknown broker stop and an absent one."""
        out = parse_exit_line("EXIT: invalidation x · time stop none")
        assert out["stop_type"] is None
        assert "stop" in out["unparsed"]
        # POSITIVE CONTROL: a declared none IS 'none'.
        assert parse_exit_line("EXIT: invalidation x · time stop none · stop none")["stop_type"] == NONE

    def test_an_unreadable_date_is_reported_not_swallowed(self):
        out = parse_exit_line("EXIT: invalidation x · time stop next Friday · stop none")
        assert out["time_stop"] is None
        assert any("time_stop" in u for u in out["unparsed"])

    def test_a_row_with_no_line_yields_nothing_and_says_so(self):
        for notes in (None, "", "Opened per TA-031. Plan to exit on strength.", "no plan here"):
            out = parse_exit_line(notes)
            assert out["invalidation"] is None
            assert out["unparsed"] == ["no EXIT line"]
            assert has_exit_line(notes) is False
        # POSITIVE CONTROL: the detector fires on a real line.
        assert has_exit_line(LIVE["PDBC"]) is True

    def test_prose_mentioning_an_exit_is_not_a_plan(self):
        """Eight of the nineteen unplanned open rows mention 'exit' in some other wording.
        Guessing from that prose would have invented plans for all eight."""
        assert has_exit_line("Trimmed half; will exit the rest into strength") is False


class TestTheVocabularyHasOneAuthor:

    def test_the_three_values(self):
        assert STOP_TYPES == (BROKER_ORDER, DAILY_CLOSE, NONE)

    def test_the_check_is_generated_not_retyped(self):
        sql = stop_type_check_sql()
        for value in STOP_TYPES:
            assert "'" + value + "'" in sql
        assert "stop_type IS NULL OR" in sql          # nullable, on purpose
        src = io.open(os.path.join(BACKEND, "database/postgres_client.py"),
                     encoding="utf-8").read()
        assert "_STOP_TYPES" in src
        assert "'broker_order', 'daily_close', 'none'" not in src   # never typed out

    def test_the_migration_leaves_notes_alone(self):
        """The sentence stays the record of what was written; the fields become what code
        reads. Nothing is deleted, so a disagreement between the two is always resolvable."""
        src = io.open(os.path.join(BACKEND, "..", "scripts", "migrate_exit_plans.py"),
                      encoding="utf-8").read()
        assert "SET invalidation = $2, time_stop = $3, stop_type = $4" in src
        assert "notes =" not in src
