"""The B2 gate needs a POST-CLOSE mark — TA-152, built under R-IV.940(c).

TA's words: the alert "requires a mark TIMESTAMPED AT OR AFTER THE CUT SESSION'S CLOSE. Not
'within 26 hours,' not 'flagged ok' -- at or after the close."

The arithmetic that makes this load-bearing rather than belt-and-braces: the hub's mark
refreshes run at 09:17 and 16:47 ET and the alert runs at 16:15 ET, BETWEEN them. So the stored
mark at alert time is always the MORNING one, and without the job reading its own mark every B2
row would return UNDETERMINED every single day.
"""
from __future__ import annotations

import ast
import inspect
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models import mark_integrity as mi  # noqa: E402
from models.b2_cut_alert import (  # noqa: E402
    NO_POST_CLOSE_MARK, UNDETERMINED, decide, post_close_mark,
)

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:                                                 # pragma: no cover
    import pytz
    ET = pytz.timezone("America/New_York")

CUT = date(2026, 10, 13)
POST_CLOSE = datetime(2026, 10, 13, 16, 47, tzinfo=ET)
MORNING = datetime(2026, 10, 13, 9, 17, tzinfo=ET)


# ── TA-152's own requirement ──────────────────────────────────────────────

def test_a_post_close_mark_is_accepted():
    ok, why = post_close_mark(CUT, POST_CLOSE, mi.OK, 0.05)
    assert ok is True and "at or after" in why


def test_the_MORNING_mark_is_REFUSED_even_though_it_is_fresh():
    """THE CASE THAT MATTERS. A 09:17 ET mark on the cut day is seven hours old -- fresh by any
    display bound, and flagged `ok` -- and it still says nothing about where the position
    closed. "Not 'within 26 hours,' not 'flagged ok'."""
    ok, why = post_close_mark(CUT, MORNING, mi.OK, 0.05)
    assert ok is False
    assert NO_POST_CLOSE_MARK in why and "BEFORE" in why


def test_exactly_at_the_close_counts_as_AT_OR_AFTER():
    ok, _ = post_close_mark(CUT, datetime(2026, 10, 13, 16, 0, tzinfo=ET), mi.OK, 0.05)
    assert ok is True


def test_one_minute_before_the_close_does_not():
    ok, _ = post_close_mark(CUT, datetime(2026, 10, 13, 15, 59, tzinfo=ET), mi.OK, 0.05)
    assert ok is False


@pytest.mark.parametrize("flag", [mi.WIDE, mi.UNKNOWN])
def test_a_wide_or_unknown_mark_is_refused_even_post_close(flag):
    """TA-151's half of the precondition."""
    ok, why = post_close_mark(CUT, POST_CLOSE, flag, 0.05)
    assert ok is False
    assert "under integrity repair" in why


def test_a_STALE_flag_is_NOT_consulted_by_the_gate():
    """Convention #38: the 26-hour verdict is for DISPLAY. The gate's own requirement already
    subsumes it -- a mark at or after today's close cannot be 26 hours old -- so `stale` must
    not be a second, weaker reason to refuse."""
    ok, _ = post_close_mark(CUT, POST_CLOSE, mi.STALE, 0.05)
    assert ok is True
    assert mi.is_gateable(mi.STALE) is True
    assert mi.is_gateable(mi.WIDE) is False
    assert mi.is_gateable(mi.UNKNOWN) is False


@pytest.mark.parametrize("ts", [None, "not a date", 12345])
def test_an_unusable_timestamp_is_refused(ts):
    ok, why = post_close_mark(CUT, ts, mi.OK, 0.05)
    assert ok is False and NO_POST_CLOSE_MARK in why


def test_a_naive_timestamp_is_refused_not_assumed():
    """Guessing a zone is how a mark taken at 16:47 ET reads as fresh at 16:47 UTC -- six hours
    early, and on the wrong side of the close."""
    ok, why = post_close_mark(CUT, datetime(2026, 10, 13, 16, 47), mi.OK, 0.05)
    assert ok is False and "no timezone" in why


def test_no_mark_at_all_is_refused():
    ok, why = post_close_mark(CUT, POST_CLOSE, mi.OK, None)
    assert ok is False and NO_POST_CLOSE_MARK in why


# ── decide() returns UNDETERMINED and NAMES the row ─────────────────────

def _row(**kw):
    row = {"position_id": "POS_IBIT_20261008_172311", "ticker": "IBIT", "bucket": "B2",
           "open_quantity": 2, "entry_date": date(2026, 10, 8), "expiry": date(2026, 10, 16),
           "realized_pnl": None, "unrealized_pnl": "-28.00",
           "mark": 0.05, "mark_as_of": POST_CLOSE, "mark_integrity": mi.OK}
    row.update(kw)
    return row


def test_a_morning_mark_makes_the_verdict_UNDETERMINED_and_names_the_row():
    out = decide(_row(mark_as_of=MORNING), now=datetime(2026, 10, 16, 16, 20, tzinfo=ET))
    assert out["verdict"] == UNDETERMINED
    assert "POS_IBIT_20261008_172311" in out["reason"]
    assert NO_POST_CLOSE_MARK in out["reason"]


def test_the_undetermined_verdict_carries_the_mark_and_its_timestamp():
    """R-IV.935(c)3 / TA-152: it "prints the mark it has with its timestamp"."""
    out = decide(_row(mark_as_of=MORNING), now=datetime(2026, 10, 16, 16, 20, tzinfo=ET))
    assert out["mark"] == 0.05
    assert out["mark_as_of"] == MORNING
    assert out["mark_integrity"] == mi.OK


def test_a_post_close_mark_lets_the_cut_be_decided():
    """The pair. IBIT 980's real numbers: entry 0.19, mark 0.05, 2 contracts -> -28.00, a loss,
    so the cut FIRES -- and legitimately, because the mark is post-close and tight."""
    out = decide(_row(), now=datetime(2026, 10, 16, 16, 20, tzinfo=ET))
    assert out["verdict"] == "FIRE"
    assert out["total_pnl"] == "-28.00"


def test_a_wide_mark_holds_the_row_rather_than_firing_on_it():
    out = decide(_row(mark_integrity=mi.WIDE),
                 now=datetime(2026, 10, 16, 16, 20, tzinfo=ET))
    assert out["verdict"] == UNDETERMINED
    assert "under integrity repair" in out["reason"]


# ── mark_integrity: the four words and the thresholds ───────────────────

def test_the_wide_threshold_is_50_percent_and_lives_in_ONE_place():
    assert mi.WIDE_SPREAD_PCT == 50.0


def test_the_measured_wide_books_are_all_caught():
    """The books actually read from production, so a future loosening has to face them."""
    now = datetime(2026, 10, 13, 20, 47, tzinfo=timezone.utc)
    for bid, ask, label in ((0.11, 0.46, "ORCL 65P, zero volume"),
                            (0.40, 1.13, "KRE 60P"),
                            (0.20, 0.57, "HYG 76P")):
        v, why = mi.evaluate((bid + ask) / 2, mark_as_of=now, bid=bid, ask=ask, now=now)
        assert v == mi.WIDE, (label, v, why)


def test_the_tight_traded_book_is_NOT_caught():
    """IBIT 43P: 0.06/0.07 on 2,175 contracts. The control -- a threshold that flagged this
    would hold every alert for ever."""
    now = datetime(2026, 10, 13, 20, 47, tzinfo=timezone.utc)
    v, _ = mi.evaluate(0.065, mark_as_of=now, bid=0.06, ask=0.07, now=now)
    assert v == mi.OK


def test_a_mark_past_the_26_hour_bound_is_stale():
    now = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
    v, why = mi.evaluate(0.05, mark_as_of=now - timedelta(hours=27), now=now)
    assert v == mi.STALE and "27.0 hours old" in why


def test_an_absent_timestamp_is_UNKNOWN_not_ok():
    v, why = mi.evaluate(0.05, mark_as_of=None)
    assert v == mi.UNKNOWN and "age cannot be established" in why


@pytest.mark.parametrize("bad", [None, 0, -1, "x"])
def test_an_unusable_mark_is_unknown(bad):
    v, _ = mi.evaluate(bad)
    assert v == mi.UNKNOWN


def test_a_one_sided_book_has_NO_width_rather_than_zero():
    """Calling a one-sided book 0% wide would report the tightest possible market."""
    assert mi.spread_pct(0.20, None) is None
    assert mi.spread_pct(None, 0.57) is None
    assert mi.spread_pct(0, 0.57) is None


def test_the_payload_shape_is_an_instant_a_word_and_a_reason():
    """R-IV.935(e): mark_as_of is an exact UTC instant, never a day; mark_integrity is a word,
    never a number."""
    now = datetime(2026, 10, 13, 20, 47, tzinfo=timezone.utc)
    p = mi.payload(0.05, mark_as_of=now, bid=0.06, ask=0.07, now=now)
    assert p["mark_as_of"] == "2026-10-13T20:47:00+00:00"
    assert "T" in p["mark_as_of"] and p["mark_as_of"].endswith("+00:00")
    assert p["mark_integrity"] in (mi.OK, mi.STALE, mi.WIDE, mi.UNKNOWN)
    assert isinstance(p["mark_integrity_reason"], str) and p["mark_integrity_reason"]


def test_evaluate_never_raises():
    for mark in (None, "x", object(), float("inf")):
        for ts in (None, "x", 1, datetime(2026, 1, 1)):
            v, why = mi.evaluate(mark, mark_as_of=ts)
            assert v in (mi.OK, mi.STALE, mi.WIDE, mi.UNKNOWN)
            assert isinstance(why, str) and why


# ── the 26-hour guard finally receives a timestamp ──────────────────────

def test_all_THREE_call_sites_pass_price_asof():
    """R-IV.935(c)1. `evaluate_mark` has taken a `price_asof` and applied a 26-hour bound since
    R-IV.394, and nothing ever passed it -- so the staleness arm had NEVER fired and a mark 18
    days old evaluated MARK_OK. Counted from the parsed tree, because a comment about
    `price_asof` is not a call that passes it."""
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "api" / "unified_positions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "evaluate_mark"]
    assert len(calls) == 3, "expected the three known call sites, found %d" % len(calls)
    for c in calls:
        kw = {k.arg for k in c.keywords}
        assert "price_asof" in kw, ast.dump(c)


def test_the_guard_still_treats_an_absent_timestamp_as_NOT_stale():
    """Unchanged behaviour, asserted so the wiring above cannot be mistaken for a new refusal:
    an unmeasured age is not an old age, and the display verdict says `unknown` instead."""
    from api.mark_guard import MARK_OK, evaluate_mark
    assert evaluate_mark(100.0, entry_price=100.0, price_asof=None)[0] == MARK_OK


# ── the alert prints the trio ────────────────────────────────────────────

def test_the_alert_body_prints_the_mark_its_timestamp_and_its_flag():
    from jobs.b2_cut_alert_job import _describe_mark

    line = _describe_mark({"mark": 0.05, "mark_as_of": POST_CLOSE,
                           "mark_integrity": mi.OK, "mark_integrity_reason": "two-sided quote"})
    assert "0.05" in line
    assert "2026-10-13T16:47" in line
    assert "ok" in line


def test_the_job_reads_its_OWN_mark_at_run_time():
    """TA-152(c)1, from the parsed tree: the evaluate loop must call the run-time reader before
    deciding, not trust whatever the morning refresh left behind."""
    from jobs import b2_cut_alert_job as job

    src = inspect.getsource(job.evaluate)
    tree = ast.parse(inspect.cleandoc("\n".join(src.splitlines()[1:])) if False else src)
    names = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "read_mark_now" in names
    assert "decide" in names


def test_the_run_time_mark_is_STORED_and_the_write_NAMES_ITSELF():
    """The SQL is inlined inside its named transaction rather than held in a module constant:
    the audit guard walks string constants containing a write and requires an enclosing named
    transaction, and a module-level constant has none. It caught this write, as it caught the
    flag write under R-IV.892."""
    from jobs import b2_cut_alert_job as job

    src = inspect.getsource(job.evaluate)
    assert "UPDATE unified_positions " in src
    assert "mark_as_of = $3" in src and "mark_integrity = $4" in src
    assert "set_config('app.actor'" in src
    assert "mark_as_of TIMESTAMPTZ" in job.DDL_MARK
