"""A trade keeps the day it happened on, including in the cash ledger — R-IV.660(c)2.

TA-083: BX was traded 09-30 and logged 10-06. The row and its opening lot have carried the
principal's `entry_date` since R-IV.464(a) -- but the CASH EVENT did not. It defaulted to
`date.today()`, so the money moved on the day the trade was typed in.

That is not cosmetic. `cash_flows.activity_date` is what a reconciliation against a broker
statement joins on, and what the weekly and monthly figures bucket by. A six-day error puts an
entry in the wrong week, and at a month boundary in the wrong month.

The close path had the same gap in the same place, and one half of its own stated bound missing:
the comment says the exit date is "bounded on both sides", but only the future side was enforced.
"""

import ast
import io
import os

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(rel):
    """Live code only: docstrings and comment lines removed, so an assertion cannot be
    satisfied by a comment that happens to mention the right words."""
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "".join(l for l in src.splitlines(keepends=True)
                   if not l.strip().startswith("#"))


def _route(src, name, end="\n@router"):
    i = src.index(name)
    return src[i:src.index(end, i)]


class TestTheCashEventCarriesTheTradeDate:
    def test_the_create_path_dates_its_cash_event_by_entry_date(self):
        """Anchored to THIS call, not to the route. The add branch lives in the same function
        and also passes `event_date`, so a bare "the name appears somewhere in the body" check
        stayed green when the create site lost it. A mutation run caught that."""
        body = _route(_code("api/unified_positions.py"), "async def create_position")
        i = body.index('description="position opened"')
        assert "event_date=" in body[i:i + 220]
        assert 'req.entry_date' in body[i:i + 220]

    def test_the_add_path_dates_its_cash_event_by_entry_date(self):
        """An add is a fill and it has its own date. The lot already used it; the money did not."""
        body = _route(_code("api/unified_positions.py"), "async def create_position")
        assert 'description="added to position"' in body
        i = body.index('description="added to position"')
        assert "event_date=" in body[i:i + 220]

    def test_the_close_path_dates_its_cash_event_by_the_exit_instant(self):
        body = _route(_code("api/unified_positions.py"), "async def close_position")
        assert 'description="closed position"' in body
        i = body.index('description="closed position"')
        assert "event_date=now.date()" in body[i:i + 160]

    def test_the_helper_still_defaults_to_today_when_no_date_is_given(self):
        """POSITIVE CONTROL. The default must survive: a caller that genuinely has no date for
        the movement should get today, not None written into a NOT NULL column. What changed is
        that the callers who DO know now say so."""
        src = _code("api/unified_positions.py")
        body = src[src.index("async def _adjust_account_cash_with_conn"):]
        assert "when = event_date or date.today()" in body


class TestTheRowAndTheLotAlreadyCarriedIt:
    """Recorded, not re-derived: the two writes the ruling asks me to confirm."""

    def test_the_position_row_takes_the_entry_date(self):
        src = _code("api/unified_positions.py")
        assert 'optional_instant(req.entry_date, "entry_date")' in src

    def test_the_opening_lot_takes_the_entry_date(self):
        """`_entry_fill_time` is the one author: the principal's date when he gave one, the
        row's creation stamp only as a last resort."""
        src = _code("api/unified_positions.py")
        body = src[src.index("def _entry_fill_time"):]
        body = body[:body.index("\nasync def ")]
        assert 'getattr(req, "entry_date", None)' in body
        assert '_when(candidate, "entry_date")' in body


class TestACloseDateDefaultsToNowAndCannotBeLater:
    def test_it_defaults_to_now(self):
        body = _route(_code("api/unified_positions.py"), "async def close_position")
        assert "now = datetime.now(timezone.utc)" in body

    def test_it_can_be_set_earlier(self):
        body = _route(_code("api/unified_positions.py"), "async def close_position")
        assert 'now = _when(req.exit_date, "exit_date")' in body

    def test_a_future_date_is_refused_by_the_one_date_reader(self):
        """`_when` refuses a future value for EVERY date entering the book, so "never later"
        is not a rule this route keeps for itself."""
        import pytest
        from fastapi import HTTPException

        from api.unified_positions import _when

        with pytest.raises(HTTPException) as exc:
            _when("2099-01-01", "exit_date")
        assert "future" in str(exc.value.detail)

    def test_a_date_that_is_not_a_date_is_refused_rather_than_coerced(self):
        import pytest
        from fastapi import HTTPException

        from api.unified_positions import _when

        with pytest.raises(HTTPException):
            _when("not a date", "exit_date")

    def test_an_exit_before_the_opening_is_refused(self):
        """THE BOUND THE ROUTE ALREADY CLAIMED TO HAVE. Its comment says the exit date is
        bounded on both sides; nothing compared it against the position's own entry, while
        /closed-from-evidence has had that check all along -- so the two paths disagreed about
        the same impossible row. A comment asserting a guard that does not exist is worse than
        no comment: it stops the next reader looking."""
        body = _route(_code("api/unified_positions.py"), "async def close_position")
        assert "is before the position" in body
        assert "if now < _opened_at:" in body

    def test_the_bound_only_applies_when_a_date_was_given(self):
        """POSITIVE CONTROL. A default close (no exit_date) must never be refused for being
        before an entry stamp that is itself in the future, or a clock skew would make the book
        uncloseable."""
        body = _route(_code("api/unified_positions.py"), "async def close_position")
        i = body.index("if now < _opened_at:")
        guard = body[:i]
        assert "if req.exit_date:" in guard
