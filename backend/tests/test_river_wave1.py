"""The River, wave 1 — R-IV.566(e) RV1/RV4/RV5 and R-IV.577(b).

Each test names the defect it holds shut, and the negatives carry positive controls
(#30) so a test that passes because nothing ran is distinguishable from one that
passes because the rule holds.
"""

import ast
import io
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from config.asset_class import EXCLUDE_CRYPTO_SQL, is_crypto
from config.strategy_class import (NON_ROSTER, ROSTER, SHADOW,
                                   attach_strategy_class, strategy_class)
from database.postgres_client import iso_utc, serialize_db_row
from signals.feed_service import session_of, tag_row
from stable_engine import sessions

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROW_SERIALIZERS = [
    "api/portfolio.py",
    "api/trade_watchlist.py",
    "api/unified_positions.py",
    "services/read_only/balances.py",
    "services/read_only/positions.py",
    "services/read_only/squeezes.py",
]


def _source(rel):
    return io.open(os.path.join(BACKEND, rel), encoding="utf-8").read()


def _code_without_docstrings(rel):
    """The module's text with every docstring removed.

    Three separate tests have already failed on a docstring that names the very thing
    live code must not name. A docstring is documentation, not behaviour.
    """
    src = _source(rel)
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return src


# ---------------------------------------------------------------- RV1: the clock

class TestRV1NaiveUtcCarriesItsOffset:
    """A naive TIMESTAMP is UTC in this database -- ten of the twelve timestamp
    columns on `signals` are `timestamp without time zone`. Served with no offset,
    `Date.parse` reads it as LOCAL, which is six hours off in Mountain Time."""

    def test_the_control_from_the_ruling(self):
        # "a signal fired at 19:45Z reads 13:45 MT on the page"
        served = iso_utc(datetime(2026, 9, 24, 19, 45))
        assert served.endswith("+00:00"), served
        mt = datetime.fromisoformat(served).astimezone(ZoneInfo("America/Denver"))
        assert (mt.hour, mt.minute) == (13, 45), mt

    def test_without_the_offset_the_page_is_six_hours_out(self):
        """The POSITIVE CONTROL for the test above: the defect, reproduced. Without
        this, `test_the_control_from_the_ruling` would pass on any string that merely
        happened to parse."""
        bare = datetime(2026, 9, 24, 19, 45).isoformat()
        assert not bare.endswith("+00:00")
        read_as_local = datetime.fromisoformat(bare).replace(
            tzinfo=ZoneInfo("America/Denver"))
        assert read_as_local.astimezone(timezone.utc).hour == 1   # next day, 6h out

    def test_an_aware_value_is_not_double_stamped(self):
        aware = datetime(2026, 9, 24, 19, 45, tzinfo=timezone.utc)
        assert iso_utc(aware) == iso_utc(datetime(2026, 9, 24, 19, 45))

    def test_a_plain_date_is_not_given_an_offset(self):
        """A date is not an instant. Handing `expiry` a midnight-UTC offset would move
        an option's expiry a day in either direction depending on who read it, so the
        stamping is narrowed to `datetime` and a `date` passes through as it was."""
        out = serialize_db_row({"timestamp": datetime(2026, 9, 24, 19, 45),
                                "expiry": date(2026, 10, 16)})
        assert out["timestamp"].endswith("+00:00")
        assert out["expiry"] == date(2026, 10, 16)

        from services.read_only.positions import _row_to_dict
        rendered = _row_to_dict({"expiry": date(2026, 10, 16),
                                 "created_at": datetime(2026, 9, 24, 19, 45)})
        assert rendered["expiry"] == "2026-10-16"
        assert rendered["created_at"].endswith("+00:00")

    @pytest.mark.parametrize("rel", ROW_SERIALIZERS)
    def test_every_row_serializer_routes_its_datetime_through_the_one_helper(self, rel):
        """Six copies of `_row_to_dict` existed, each its own chance to emit a naive
        string. The scan finds the `isinstance(v, datetime)` branch and asserts what
        that branch calls."""
        tree = ast.parse(_source(rel))
        branches = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if not (isinstance(test, ast.Call)
                    and isinstance(test.func, ast.Name)
                    and test.func.id == "isinstance"):
                continue
            arg = test.args[1] if len(test.args) > 1 else None
            names = []
            if isinstance(arg, ast.Name):
                names = [arg.id]
            elif isinstance(arg, ast.Tuple):
                names = [e.id for e in arg.elts if isinstance(e, ast.Name)]
            if "datetime" in names and "date" not in names:
                branches.append(node)
        assert branches, "no datetime branch found in %s" % rel
        for node in branches:
            # `node.body` ONLY. Walking the whole If reaches its `elif isinstance(v,
            # date)` sibling, whose `isoformat()` is correct and expected -- scanning
            # it would fail every module for the branch that is right.
            body = [n for stmt in node.body for n in ast.walk(stmt)]
            called = {n.func.id for n in body
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            attrs = {n.func.attr for n in body
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
            assert "iso_utc" in called, (rel, called, attrs)
            assert "isoformat" not in attrs, (rel, attrs)

            # POSITIVE CONTROL: the same scan on the sibling `date` branch DOES find
            # the bare isoformat, so a green result above is the rule holding and not
            # the walk having missed the code.
            sibling = [n for stmt in node.orelse for n in ast.walk(stmt)]
            sibling_attrs = {n.func.attr for n in sibling
                             if isinstance(n, ast.Call)
                             and isinstance(n.func, ast.Attribute)}
            assert "isoformat" in sibling_attrs, (rel, sibling_attrs)


# ---------------------------------------------------------- RV4: crypto is excluded

class TestRV4CryptoDoesNotReachTheRiver:

    def test_one_author(self):
        """The predicate is written once. A second literal in a feed's SQL is how a
        fifth feed gets added without it -- and the symptom is not an error, it is the
        feed filling with crypto again."""
        assert EXCLUDE_CRYPTO_SQL == "COALESCE(asset_class, '') <> 'CRYPTO'"
        for rel in ("api/trade_ideas.py", "signals/feed_service.py"):
            code = _code_without_docstrings(rel)
            assert "<> 'CRYPTO'" not in code, rel
            assert "EXCLUDE_CRYPTO_SQL" in code, rel

    def test_coalesce_is_not_optional(self):
        """`asset_class` is nullable and `NULL <> 'CRYPTO'` is NULL, not true. A bare
        `<>` would silently drop every equity row whose class was never set."""
        assert "COALESCE" in EXCLUDE_CRYPTO_SQL

    def test_the_python_twin_agrees_with_the_sql(self):
        assert is_crypto("CRYPTO")
        assert is_crypto("crypto")
        assert is_crypto(" Crypto ")
        # POSITIVE CONTROL: the rows the feed must KEEP.
        assert not is_crypto(None)
        assert not is_crypto("")
        assert not is_crypto("EQUITY")

    def test_it_is_a_feed_filter_and_never_a_write_filter(self):
        """A crypto signal excluded from the expiry cron would never expire, and a
        dismiss that skipped crypto would report success having changed nothing. Both
        were briefly true in this file before the write sites were separated out."""
        code = _code_without_docstrings("api/trade_ideas.py")
        assert "UPDATE signals" in code, "positive control: the writes are still here"
        for chunk in code.split("UPDATE signals")[1:]:
            statement = chunk.split('"""')[0]
            assert "EXCLUDE_CRYPTO_SQL" not in statement, statement[:400]


# --------------------------------------------------- RV5: the session at fire time

class TestRV5SessionAtFireTime:

    @pytest.mark.parametrize("utc,expected", [
        (datetime(2026, 9, 24, 13, 30), sessions.REGULAR),      # 09:30 ET, the open
        (datetime(2026, 9, 24, 19, 45), sessions.REGULAR),      # 15:45 ET
        (datetime(2026, 9, 24, 12, 0), sessions.PRE_MARKET),    # 08:00 ET
        (datetime(2026, 9, 24, 8, 0), sessions.PRE_MARKET),     # 04:00 ET, its open
        (datetime(2026, 9, 24, 20, 0), sessions.AFTER_HOURS),   # 16:00 ET, the close
        (datetime(2026, 9, 24, 23, 59), sessions.AFTER_HOURS),  # 19:59 ET
        (datetime(2026, 9, 25, 0, 0), sessions.CLOSED),         # 20:00 ET
        (datetime(2026, 9, 24, 7, 59), sessions.CLOSED),        # 03:59 ET
        (datetime(2026, 9, 26, 17, 0), sessions.CLOSED),        # a Saturday
    ])
    def test_the_boundaries(self, utc, expected):
        assert sessions.session_at(utc) == expected

    def test_the_close_belongs_to_after_hours_and_not_to_both(self):
        assert sessions.session_at(datetime(2026, 9, 24, 19, 59, 59)) == sessions.REGULAR
        assert sessions.session_at(datetime(2026, 9, 24, 20, 0, 0)) == sessions.AFTER_HOURS

    def test_a_naive_value_is_read_as_utc_not_local(self):
        """Reading this database's naive UTC as local IS the RV1 defect. A session
        tagger that repeated it would mislabel every overnight signal."""
        naive = datetime(2026, 9, 24, 23, 0)
        aware = datetime(2026, 9, 24, 23, 0, tzinfo=timezone.utc)
        assert sessions.session_at(naive) == sessions.session_at(aware)
        assert sessions.session_at(naive) == sessions.AFTER_HOURS

    def test_unknown_is_not_closed(self):
        """'The market was shut' and 'nobody knows' are different claims. R-IV.565's
        drop/hold policy keys on this answer, and must not drop a signal on a missing
        one."""
        assert sessions.session_at(None) is None
        assert sessions.is_rth(None) is None
        assert sessions.is_outside_regular_hours(None) is None
        assert session_of({}) is None
        assert session_of({"timestamp": "not a timestamp"}) is None
        # POSITIVE CONTROL: a readable instant still answers.
        assert session_of({"timestamp": "2026-09-24T19:45:00+00:00"}) == sessions.REGULAR

    def test_a_serialized_row_and_a_raw_row_agree(self):
        """Some callers reach `session_of` with a raw record and some with a row that
        has already been through `serialize_db_row`. One signal, one answer."""
        raw = {"timestamp": datetime(2026, 9, 24, 19, 45)}
        assert session_of(raw) == session_of(serialize_db_row(dict(raw)))
        assert session_of(raw) == sessions.REGULAR

    def test_created_at_is_the_fallback_not_the_preference(self):
        row = {"timestamp": datetime(2026, 9, 24, 19, 45),
               "created_at": datetime(2026, 9, 25, 3, 0)}
        assert session_of(row) == sessions.REGULAR
        assert session_of({"created_at": row["created_at"]}) == sessions.CLOSED

    def test_is_rth_is_tri_state(self):
        """A caller that needs a boolean must say which way an unreadable calendar
        falls, rather than inheriting whichever way this module happened to round."""
        assert sessions.is_rth(datetime(2026, 9, 24, 19, 45)) is True
        assert sessions.is_rth(datetime(2026, 9, 26, 17, 0)) is False
        assert sessions.is_rth(None) is None


# ------------------------------------------- R-IV.577(b): what a feed row IS

class TestStrategyClass:

    def test_the_three_classes(self):
        assert strategy_class("GOLDEN_TOUCH") == ROSTER
        assert strategy_class("WHALE_LONG") == SHADOW
        assert strategy_class("SOMETHING_NOBODY_MAPPED") == NON_ROSTER

    def test_it_never_returns_none(self):
        """THE DEFECT. The page inferred roster membership from `codename`, a DISPLAY
        field that returns None for anything unmapped -- so 'not on the roster' and
        'the display layer did not run' arrived as one thing."""
        for args in [(None, None), ("", ""), ("X", None), (None, "y")]:
            assert strategy_class(*args) in (ROSTER, SHADOW, NON_ROSTER)

    def test_it_does_not_depend_on_the_display_layer_having_run(self):
        """The exact failure being removed: strip `codename` and the class stands."""
        row = {"signal_type": "GOLDEN_TOUCH", "strategy": None, "codename": "Midas"}
        attach_strategy_class(row)
        first = row["strategy_class"]
        row.pop("codename")
        attach_strategy_class(row)
        assert row["strategy_class"] == first == ROSTER

    def test_the_raw_identifiers_are_untouched(self):
        """Outcome history, the n-gates and committee branching all key on them."""
        row = {"signal_type": "GOLDEN_TOUCH", "strategy": "golden_touch"}
        attach_strategy_class(row)
        assert row["signal_type"] == "GOLDEN_TOUCH"
        assert row["strategy"] == "golden_touch"

    def test_a_shadow_family_is_not_served_as_roster(self):
        """Triton is declared shadow in its own modules -- it writes only to
        `triton_flow_shadow` and no live decision reads its grades. Calling it
        `roster` would put a strategy that does not trade in Watch beside ones that
        do."""
        assert strategy_class("WHALE_BEARISH") == SHADOW
        assert strategy_class(None, "whale_hunter") == SHADOW

    def test_class_is_about_the_strategy_not_the_asset(self):
        """TRAPPED_SHORTS is Hector whatever it fired on. RV4 excludes on ASSET class;
        this field states STRATEGY class. Conflating them would drop Hector's equity
        rows as well."""
        assert strategy_class("TRAPPED_SHORTS", "Crypto Scanner") == ROSTER


class TestTagRowStampsBoth:

    def test_both_fields_land(self):
        row = tag_row({"signal_type": "GOLDEN_TOUCH",
                       "timestamp": datetime(2026, 9, 24, 19, 45)})
        assert row["strategy_class"] == ROSTER
        assert row["session"] == sessions.REGULAR

    def test_one_author_for_both_feeds(self):
        """The flat feed and the grouped feed must not come to different answers about
        the same signal, so neither defines its own copy of the tagger."""
        code = _code_without_docstrings("api/trade_ideas.py")
        assert "def tag_row" not in code
        assert "def session_of" not in code
        assert "from signals.feed_service import" in code
