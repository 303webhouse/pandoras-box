"""The B2 three-day cut alert — TA-141 §3 / R-IV.888(c)1.

Six rules, each with the case that must NOT fire beside it (Convention #30):

  1. the cut is the close of the 3rd FULL trading session after the entry session
  2. total P&L > 0 passes; FLAT FIRES
  3. a null mark is UNDETERMINED — neither a pass nor a fire
  4. EXPIRY-STOPPED when the 3rd session falls ON OR AFTER expiry
  5. it fires once, then flags; it never closes anything
  6. THE CLOCK NEVER RESETS
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models.b2_cut_alert import (  # noqa: E402
    ALREADY_FIRED, EXPIRY_STOPPED, FIRE, NOT_YET, PASS, SESSIONS_TO_CUT, UNDETERMINED,
    cut_session, decide, is_in_scope, total_pnl,
)

ET = ZoneInfo("America/New_York")

# Monday 2026-10-12 is a trading day; no holiday in that week.
MON = datetime(2026, 10, 12, 10, 0, tzinfo=ET)


def _post_close_mark_for(entry_date):
    """16:30 ET on the row's OWN cut session -- i.e. after that session's 16:00 close.

    Derived, not fixed: these tests span several entry dates and therefore several cuts, and a
    single hard-coded instant would be post-close for some rows and pre-close for others. A
    fixture that silently decides which tests reach their subject is worse than no fixture.
    """
    from datetime import datetime

    from models.b2_cut_alert import ET, cut_session
    cut = cut_session(entry_date)
    if cut is None:
        return None
    return datetime(cut.year, cut.month, cut.day, 16, 30, tzinfo=ET)


def _row(**over):
    # TA-161 (R-IV.983(b)): the verdict is computed from the gated mark, so `structure`,
    # `entry_price` and `open_quantity` are now its INPUTS and `unrealized_pnl` is not read for
    # it at all. One share at a basis of 0.25 keeps the arithmetic at $1 per unit, so every
    # figure below reads directly: cut_pnl = mark - 0.25.
    r = {"bucket": "B2", "structure": "stock", "entry_price": "0.25",
         "open_quantity": 1, "quantity": 1, "entry_date": MON,
         "expiry": date(2026, 11, 20), "realized_pnl": None, "unrealized_pnl": "50.00",
         "b2_cut_alerted_at": None}
    r.update(over)
    # TA-152: the gate needs a mark at or after the cut session's close before any P&L is
    # totalled. Supplied here so these tests keep testing the cut and the total, which is what
    # they are about. The gate itself is covered by test_b2_post_close_mark_r940.
    r.setdefault("mark", 0.5)
    r.setdefault("mark_integrity", "ok")
    r.setdefault("mark_as_of", _post_close_mark_for(r.get("entry_date")))
    return r


# ── 1 · the cut point ───────────────────────────────────────────────────────

def test_the_cut_is_three_trading_sessions_after_the_entry_session():
    """Entry Monday -> Tue(1) Wed(2) Thu(3). The entry session is EXCLUDED, which is what
    "after the entry session" settles."""
    assert SESSIONS_TO_CUT == 3
    assert cut_session(MON) == date(2026, 10, 15)


def test_a_weekend_does_not_count_as_a_session():
    """Entry Thursday -> Fri(1), Mon(2), Tue(3). Counting calendar days would have said Sunday."""
    assert cut_session(datetime(2026, 10, 15, 10, 0, tzinfo=ET)) == date(2026, 10, 20)


def test_a_holiday_does_not_count_as_a_session():
    """Thanksgiving 2026-11-26. Entry Tue 11-24 -> Wed(1), Fri(2) [Thu is the holiday],
    Mon(3) = 11-30."""
    assert cut_session(datetime(2026, 11, 24, 10, 0, tzinfo=ET)) == date(2026, 11, 30)


def test_the_entry_time_of_day_does_not_change_the_cut():
    """09:31 and 15:58 get the same three sessions: the entry session is excluded, not
    prorated. This is also why no intraday time enters the calculation at all."""
    early = cut_session(datetime(2026, 10, 12, 9, 31, tzinfo=ET))
    late = cut_session(datetime(2026, 10, 12, 15, 58, tzinfo=ET))
    assert early == late == date(2026, 10, 15)


def test_a_utc_entry_timestamp_is_read_as_its_ET_session():
    """entry_date is TIMESTAMPTZ. 2026-10-12 21:00 UTC is 17:00 ET on the SAME session; the UTC
    date would agree here, but 2026-10-13 01:00 UTC is still 2026-10-12 ET and must not shift
    the clock a day forward."""
    assert cut_session(datetime(2026, 10, 13, 1, 0, tzinfo=timezone.utc)) == date(2026, 10, 15)


def test_the_cut_is_not_reached_during_the_third_session():
    """AT the close, not during it. 15:00 on the cut day is still NOT_YET."""
    d = decide(_row(mark="0.15"),
               now=datetime(2026, 10, 15, 15, 0, tzinfo=ET))
    assert d["verdict"] == NOT_YET, d


def test_the_cut_IS_reached_at_the_close_of_the_third_session():
    d = decide(_row(mark="0.15"),
               now=datetime(2026, 10, 15, 16, 0, tzinfo=ET))
    assert d["verdict"] == FIRE, d


# ── 2 · the bar, and FLAT FIRES ─────────────────────────────────────────────

AT_CUT = datetime(2026, 10, 15, 16, 0, tzinfo=ET)


def test_a_profitable_position_passes():
    assert decide(_row(mark="0.26"), now=AT_CUT)["verdict"] == PASS


def test_a_losing_position_fires():
    assert decide(_row(mark="0.24"), now=AT_CUT)["verdict"] == FIRE


def test_EXACTLY_FLAT_FIRES():
    """The rule most easily coded as `< 0`. The bar is "> 0", so zero does not pass."""
    d = decide(_row(mark="0.25"), now=AT_CUT)
    assert d["verdict"] == FIRE, d
    assert "flat fires" in d["reason"]


def test_realized_is_NOT_included_in_the_cut_verdict_under_ta161():
    """TA-161 REVERSES what this test used to assert, and that is a question for SPINE.

    R-IV.888 established -- with this test and its own rationale -- that a partial exit's
    realized P&L counts toward the cut, so a position up overall but down on the remainder
    PASSES. TA-161's formula has no realized term:

        cut_pnl = orientation x (mark_gated - entry_basis_per_unit) x multiplier x open_quantity

    So the same position now FIRES. Implemented exactly as ruled, because the ruling states the
    formula explicitly; RAISED rather than reconciled, because reversing a property an earlier
    ruling deliberately established is not a call this lane should make silently.

    `total_pnl` is still reported beside the verdict, so the booked figure is not lost -- it
    simply no longer decides anything.
    """
    d = decide(_row(realized_pnl="120.00", unrealized_pnl="-50.00", mark="0.15"), now=AT_CUT)
    # The contrast, in one row: UP 70.00 overall, DOWN 0.10 on what is still held.
    assert d["total_pnl"] == "70.00", d        # reported, not consulted
    assert d["cut_pnl"] == "-0.10", d          # the remainder alone, on the gated mark
    assert d["verdict"] == FIRE, d             # R-IV.888 would have said PASS
    # And the disagreement between the two writers is recorded rather than resolved here.
    assert d["pnl_divergence"] is not None, d


def test_a_cent_is_not_lost_to_float():
    """Decimal(str(x)) throughout: Decimal(32.99) is 32.98999999999999488, and a total compared
    against zero must not be decided by a float artefact."""
    total, reason = total_pnl("32.99", "-32.99")
    assert reason is None
    assert str(total) == "0.00"
    assert total == 0          # and therefore FIRES, by the flat rule


# ── 3 · a null mark is UNDETERMINED ─────────────────────────────────────────

def test_a_null_mark_is_undetermined():
    d = decide(_row(mark=None), now=AT_CUT)
    assert d["verdict"] == UNDETERMINED, d
    assert "no mark" in d["reason"]


def test_a_null_mark_is_not_treated_as_zero():
    """The pair for the flat rule. Zero FIRES; absent must not, or an unpriceable position gets
    reported as flat and the alert cries wolf about something nobody can value."""
    assert decide(_row(mark="0.25"), now=AT_CUT)["verdict"] == FIRE
    assert decide(_row(mark=None), now=AT_CUT)["verdict"] == UNDETERMINED


def test_a_null_REALIZED_is_a_known_zero_not_an_unknown():
    """The asymmetry. No closures means no realized P&L -- a known zero. Treating it as unknown
    would make every untouched position undeterminable."""
    total, reason = total_pnl(None, "25.00")
    assert reason is None
    assert str(total) == "25.00"


# ── 4 · EXPIRY-STOPPED ─────────────────────────────────────────────────────

def test_expiry_before_the_cut_stops_it():
    d = decide(_row(expiry=date(2026, 10, 14), mark="0.15"), now=AT_CUT)
    assert d["verdict"] == EXPIRY_STOPPED, d


def test_expiry_EXACTLY_ON_the_cut_stops_it():
    """"On or after", so `>=`. A cut landing on expiry day is the expiry's business."""
    d = decide(_row(expiry=date(2026, 10, 15), mark="0.15"), now=AT_CUT)
    assert d["verdict"] == EXPIRY_STOPPED, d


def test_expiry_one_day_after_the_cut_does_NOT_stop_it():
    """The pair. Without this, an off-by-one that stopped everything would pass the two above."""
    d = decide(_row(expiry=date(2026, 10, 16), mark="0.15"), now=AT_CUT)
    assert d["verdict"] == FIRE, d


def test_a_position_with_no_expiry_is_not_expiry_stopped():
    """Shares have no expiry; a null must not read as "expiry already passed"."""
    d = decide(_row(expiry=None, mark="0.15"), now=AT_CUT)
    assert d["verdict"] == FIRE, d


# ── 5 · fires once, then flags ─────────────────────────────────────────────

def test_once_flagged_it_does_not_fire_again():
    d = decide(_row(mark="0.15", b2_cut_alerted_at="2026-10-15T16:00:00Z"),
               now=AT_CUT)
    assert d["verdict"] == ALREADY_FIRED, d


def test_the_flag_wins_even_if_the_position_later_turns_profitable():
    """It fires once. A later recovery does not un-fire it, and must not re-arm it either."""
    d = decide(_row(mark="5.00", b2_cut_alerted_at="2026-10-15T16:00:00Z"),
               now=AT_CUT)
    assert d["verdict"] == ALREADY_FIRED, d


def test_nothing_in_the_module_closes_anything():
    """It is a PROMPT. Asserted against the module's PARSED source -- a comment promising not to
    close would satisfy a substring search."""
    import ast

    src = open(__file__.rsplit("tests", 1)[0] + "models/b2_cut_alert.py", encoding="utf-8").read()
    called = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name:
                called.add(name)
    for forbidden in ("close_position", "reduce_position", "execute", "post", "submit"):
        assert forbidden not in called, "the alert must not act: %s" % forbidden


# ── 6 · THE CLOCK NEVER RESETS ─────────────────────────────────────────────

def test_cut_session_cannot_see_the_current_time():
    """Structural, not behavioural: a cut that can read a clock is a cut that can move. Asserted
    on the signature, so a future `now=` parameter fails here rather than silently allowing a
    reset."""
    import inspect

    params = list(inspect.signature(cut_session).parameters)
    assert params == ["entry"], params


@pytest.mark.parametrize("later", [
    datetime(2026, 10, 16, 16, 0, tzinfo=ET),
    datetime(2026, 10, 20, 16, 0, tzinfo=ET),
    datetime(2026, 12, 1, 16, 0, tzinfo=ET),
])
def test_the_cut_stays_put_however_late_the_check_runs(later):
    """A missed day, a redeploy, a weekend outage: the verdict arrives late but the cut does
    not move, so a position that was flat at its cut is still reported against THAT session."""
    d = decide(_row(mark="0.24"), now=later)
    assert d["cut_session"] == "2026-10-15", d
    assert d["verdict"] == FIRE


def test_a_later_add_does_not_move_the_cut():
    """The clock is a function of the ENTRY session alone. Adding size changes quantity, not the
    entry, so the cut is unchanged -- and this is asserted rather than assumed because "the
    clock never resets" is the rule most easily broken by a well-meaning recalculation."""
    base = decide(_row(mark="0.24"), now=AT_CUT)
    added = decide(_row(mark="0.24", open_quantity=10), now=AT_CUT)
    assert base["cut_session"] == added["cut_session"] == "2026-10-15"


# ── scope ──────────────────────────────────────────────────────────────────

def test_only_B2_is_in_scope():
    assert is_in_scope(_row()) is True
    for other in ("B1", "B3", "TAIL", None, ""):
        assert is_in_scope(_row(bucket=other)) is False, other


def test_the_bucket_match_is_case_insensitive():
    """Stored casing is not guaranteed -- `Whale_Hunter`, not `whale_hunter` (R-IV.849(d))."""
    for spelling in ("B2", "b2", " b2 "):
        assert is_in_scope(_row(bucket=spelling)) is True, spelling


def test_open_is_decided_by_open_quantity_not_status():
    """R-IV.844(d)3. A closed row has no size; a partially exited row still does."""
    assert is_in_scope(_row(open_quantity=0)) is False
    assert is_in_scope(_row(open_quantity=1)) is True
    # status is not consulted at all, so a mislabelled row with real size is still in scope
    assert is_in_scope(_row(open_quantity=3, status="CLOSED")) is True
