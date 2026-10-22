"""A contract past expiry leaves the B2 cut-alert's scope. R-IV.1342(d).

WHAT WAS WRONG, and it was live today. Row 1004 (IWM 10/19 269P, bucket B2, open quantity 2) was
THREE DAYS PAST EXPIRY and still in scope. The only thing stopping it sending Nick a cut alert
was that the vendor has no quote for a dead strike -- so the protection was a vendor's silence,
not a rule. A vendor that returned a last price for an expired contract would have sent a cut
alert on a position that cannot be cut. Row 980 (IBIT, bucket B2) carries status EXPIRED with
open quantity and was in the same place.

WHY `cut_verdict`'s EXPIRY_STOPPED DID NOT COVER THIS. That branch fires when the THIRD SESSION
falls on or after expiry -- a statement about a row already in scope, and only about the cut
date. A row whose cut session passed weeks ago and whose contract has since expired sails
through it. The two tests answer different questions: "did the cut land past expiry" versus "is
this contract dead now".

WHATEVER ITS STATUS OR OPEN QUANTITY. The ruling's words, and the test asserts them separately:
the expiry check runs FIRST and consults neither, because a row can be EXPIRED-with-size,
OPEN-with-size, or anything else, and past expiry none of it matters -- the alert asks "should
this be cut today" and a dead contract cannot be.

ONE FUNCTION, BOTH SURFACES. `/api/b2_cut_status` serves `is_in_scope(r)` per row and
`jobs/b2_cut_alert_job` gates on `if not is_in_scope(row)`, so both were fixed by fixing the one
function -- asserted below rather than assumed, because "they share a helper" is the kind of
thing that is true until someone inlines it.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models.b2_cut_alert import (BUCKET, is_expired,                # noqa: E402
                                 is_in_scope, session_date_et)

from ._srcscan import read_source                                  # noqa: E402

ET_TODAY = session_date_et()


def _row(expiry, *, bucket=BUCKET, qty=2, status="OPEN", **extra):
    r = {"bucket": bucket, "open_quantity": qty, "status": status,
         "expiry": None if expiry is None else str(expiry)}
    r.update(extra)
    return r


# ── the case the ruling names ───────────────────────────────────────────────

def test_a_PAST_EXPIRY_B2_row_WITH_A_MARK_stays_out_of_scope():
    """R-IV.1342(d)'s test, written with the mark present -- which is the whole point. Without a
    mark the row is harmless; the danger is precisely a vendor that DOES return a price for a
    dead contract."""
    row = _row(ET_TODAY - timedelta(days=3), current_price="1.25", mark_as_of="2026-10-22")
    assert is_expired(row) is True
    assert is_in_scope(row) is False


def test_row_1004s_SHAPE_is_out_of_scope():
    """IWM 10/19 269P, bucket B2, open quantity 2, a mark present. The row that was live in
    scope when the ruling was written."""
    row = _row("2026-10-19", qty=2, status="OPEN", ticker="IWM", strike="269",
               option_type="PUT", current_price="0.01")
    if ET_TODAY <= date(2026, 10, 19):
        pytest.skip("this shape is only past-expiry after 2026-10-19")
    assert is_in_scope(row) is False


def test_row_980s_SHAPE_is_out_of_scope_too():
    """Status EXPIRED with open quantity still on it. Status is not what decides -- but neither
    does its presence save the row."""
    row = _row("2026-09-30", qty=5, status="EXPIRED", ticker="IBIT", current_price="0.02")
    assert is_in_scope(row) is False


# ── and an unexpired row is unchanged ───────────────────────────────────────

def test_an_UNEXPIRED_row_is_UNCHANGED():
    """The control. If the guard dropped live rows too, the three tests above would pass while
    the alert quietly stopped working -- the invisible failure, and the worse one."""
    row = _row(ET_TODAY + timedelta(days=58), current_price="3.40")
    assert is_expired(row) is False
    assert is_in_scope(row) is True


def test_a_contract_expiring_TODAY_is_STILL_IN_SCOPE():
    """Strictly BEFORE today. A contract expiring today can still be closed during the session,
    and `cut_verdict` already hands that case to EXPIRY_STOPPED. Dropping it here would remove
    the alert on the one day it is most useful."""
    row = _row(ET_TODAY, current_price="0.55")
    assert is_expired(row) is False
    assert is_in_scope(row) is True


def test_a_row_with_NO_EXPIRY_is_not_treated_as_expired():
    """An absent or unreadable expiry is a row we know nothing about. Dropping it would silently
    stop alerting on live positions -- the opposite failure, and an invisible one."""
    for value in (None, "", "not-a-date", "0000-00-00"):
        row = _row(value)
        assert is_expired(row) is False, value
        assert is_in_scope(row) is True, value


# ── status and quantity do not enter the expiry test ────────────────────────

@pytest.mark.parametrize("status", ["OPEN", "EXPIRED", "CLOSED", "", None])
def test_the_expiry_test_ignores_STATUS(status):
    assert is_expired(_row(ET_TODAY - timedelta(days=1), status=status)) is True
    assert is_in_scope(_row(ET_TODAY - timedelta(days=1), status=status)) is False


@pytest.mark.parametrize("qty", [2, 100, "3", 0, None])
def test_the_expiry_test_ignores_OPEN_QUANTITY(qty):
    """"whatever its status or open quantity" -- so a past-expiry row is out even with size, and
    the expiry branch is reached before the quantity branch."""
    assert is_expired(_row(ET_TODAY - timedelta(days=1), qty=qty)) is True
    assert is_in_scope(_row(ET_TODAY - timedelta(days=1), qty=qty)) is False


def test_the_expiry_check_runs_FIRST():
    """Order matters for the reason above: a quantity check that ran first would return False on
    a zero-quantity expired row for the WRONG reason, and True-ish shapes would slip through.

    READ OFF THE STATEMENTS, not off the text. The first draft of this test sliced a character
    window and matched the function's own DOCSTRING, which explains the rule using the very words
    the rule is made of -- the prose trap, for the fourteenth time this session. `ast` gives the
    body statements with the docstring identifiable and droppable, so what is measured is the
    order of the CODE.
    """
    import ast

    tree = ast.parse((_BACKEND / "models" / "b2_cut_alert.py").read_text(encoding="utf-8-sig"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "is_in_scope")
    body = list(fn.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
        body = body[1:]                              # the docstring, which quotes the rule

    texts = [ast.unparse(s) for s in body]
    where = lambda needle: next(k for k, t in enumerate(texts) if needle in t)   # noqa: E731

    assert where("is_expired") == 0, texts
    assert where("is_expired") < where("bucket")
    assert where("is_expired") < where("open_quantity")


# ── the other scope rules still hold ────────────────────────────────────────

def test_a_NON_B2_bucket_is_still_out_of_scope():
    assert is_in_scope(_row(ET_TODAY + timedelta(days=30), bucket="B1")) is False
    assert is_in_scope(_row(ET_TODAY + timedelta(days=30), bucket="TAIL")) is False


def test_the_bucket_match_is_still_CASE_INSENSITIVE():
    """`Whale_Hunter` taught that stored casing is not guaranteed (R-IV.849(d))."""
    assert is_in_scope(_row(ET_TODAY + timedelta(days=30), bucket="b2")) is True
    assert is_in_scope(_row(ET_TODAY + timedelta(days=30), bucket=" B2 ")) is True


def test_a_CLOSED_OUT_row_is_still_out_of_scope():
    """open_quantity, not status, as R-IV.844(d)3 requires."""
    assert is_in_scope(_row(ET_TODAY + timedelta(days=30), qty=0)) is False


# ── the session date is ET ──────────────────────────────────────────────────

def test_the_session_date_is_EASTERN_and_not_UTC():
    """A UTC date rolls over at 20:00 ET, so a UTC-dated guard would call a contract expired for
    the last four hours of the session before it -- exactly when a cut alert matters most."""
    late = datetime(2026, 10, 22, 23, 30, tzinfo=timezone.utc)      # 19:30 ET, same session
    assert session_date_et(late) == date(2026, 10, 22)
    past_midnight_utc = datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc)   # 21:00 ET on the 22nd
    assert session_date_et(past_midnight_utc) == date(2026, 10, 22)


def test_a_row_expiring_today_is_live_even_late_in_the_UTC_day():
    """The practical form of the same point."""
    late = datetime(2026, 10, 22, 23, 30, tzinfo=timezone.utc)
    assert is_expired(_row("2026-10-22"), now=late) is False
    assert is_in_scope(_row("2026-10-22"), now=late) is True


# ── both surfaces go through the one function ───────────────────────────────

def test_the_API_ROUTE_and_the_ALERT_JOB_both_gate_on_is_in_scope():
    """Asserted rather than assumed: "they share a helper" stays true until someone inlines it,
    and this is the guard that keeps an alert from reaching Nick."""
    route = read_source(str(_BACKEND / "api" / "b2_cut_status.py"))
    assert "is_in_scope" in route
    assert '"in_scope": is_in_scope(' in route

    job = read_source(str(_BACKEND / "jobs" / "b2_cut_alert_job.py"))
    assert "from models.b2_cut_alert import" in job and "is_in_scope" in job
    assert "if not is_in_scope(row)" in job


def test_neither_surface_rebuilds_the_scope_rule_for_itself():
    """A second copy of the rule is a second place for the expiry guard to be missing."""
    for rel in ("api/b2_cut_status.py", "jobs/b2_cut_alert_job.py"):
        src = read_source(str(_BACKEND / rel))
        assert "def is_in_scope" not in src, rel
