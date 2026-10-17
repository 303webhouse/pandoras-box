"""R-IV.1203(c) — unsettled captures in `stable_daily_bars`: find them, convict carefully, repair.

THE HARD PART IS NOT FINDING MISMATCHES, IT IS CONVICTING THE RIGHT ONES.

`stable_daily_bars` is FULLY ADJUSTED -- `bars_yf` passes `auto_adjust=True`, so splits and
dividends -- and R-IV.1203(c) rules that basis CORRECT for moving averages and breadth, so it
stays. Polygon's `adjusted=true` is split-only. The two bases therefore DISAGREE BY DESIGN on
every bar before a dividend, and a repair that reads that as an unsettled capture would
overwrite a correct row with one on the wrong basis. The defect would be replaced by a worse one
that nothing is looking for.

THE DISCRIMINATOR is about the SHAPE of the disagreement, not its size:

  an adjustment SCALES all four prices by one factor -> same bar, moved
  an unsettled capture TRUNCATES the session      -> stored range inside the true range,
                                                     and the four ratios disagree

A row is convicted only on the second. Everything else is reported and left alone.

`classify_row` is pure, which is the point: the decision that authorises a WRITE is testable
without a database or a vendor, and these tests pin both directions of it.
"""
from __future__ import annotations

import datetime as dt
import os

import pytest

from ._srcscan import code_of_file, read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── the discriminator: an unsettled capture ───────────────────────────────

def test_THE_MEASURED_SPY_ROW_IS_CONVICTED():
    """The live case. SPY 2026-10-16: stored close 764.29, settled close 763.25, and the stored
    range sits inside the session's true range -- an intraday snapshot in a settled-looking row."""
    from jobs.bars_audit import classify_row
    stored = {"o": 773.24, "h": 770.10, "l": 762.00, "c": 764.29}
    true = {"o": 773.24, "h": 773.25, "l": 760.64, "c": 763.25}
    v = classify_row(stored, true)
    assert v["verdict"] == "unsettled_capture", v
    assert "before the session finished" in v["why"]


def test_a_DIVIDEND_BASIS_DIFFERENCE_IS_NOT_CONVICTED():
    """THE TEST THAT MATTERS MOST. A dividend adjustment scales all four prices by one factor,
    so the bar is the same shape moved -- and R-IV.1203(c) keeps that basis. Convicting it would
    rewrite a correct row onto the wrong basis."""
    from jobs.bars_audit import classify_row
    true = {"o": 100.00, "h": 101.00, "l": 99.00, "c": 100.50}
    f = 0.9950                                   # a ~0.5% dividend adjustment
    stored = {k: round(v * f, 4) for k, v in true.items()}
    v = classify_row(stored, true)
    assert v["verdict"] == "basis_difference", v
    assert "left alone" in v["why"]


def test_a_SPLIT_sized_factor_is_also_a_basis_difference():
    """The same shape at a much larger factor. Size is not the signal."""
    from jobs.bars_audit import classify_row
    true = {"o": 400.0, "h": 404.0, "l": 396.0, "c": 402.0}
    stored = {k: v / 4.0 for k, v in true.items()}
    assert classify_row(stored, true)["verdict"] == "basis_difference"


def test_an_AGREEING_close_is_a_match():
    from jobs.bars_audit import classify_row
    true = {"o": 1.0, "h": 2.0, "l": 0.5, "c": 763.25}
    assert classify_row(dict(true), true)["verdict"] == "match"
    # Within rounding.
    assert classify_row(dict(true, c=763.2512), true)["verdict"] == "match"


def test_an_UNEXPLAINED_MISMATCH_IS_NOT_REPAIRED():
    """Stored range NOT inside the true range and no single scaling factor. Nothing here
    establishes which side is right, and repairing what you do not understand is how a correct
    row becomes a wrong one."""
    from jobs.bars_audit import classify_row
    stored = {"o": 100.0, "h": 120.0, "l": 80.0, "c": 110.0}     # wider than true
    true = {"o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5}
    v = classify_row(stored, true)
    assert v["verdict"] == "mismatch_unexplained"
    assert "NOT repaired" in v["why"]


def test_a_MISSING_CLOSE_is_unreadable_not_a_match():
    from jobs.bars_audit import classify_row
    assert classify_row({"c": None}, {"c": 1.0})["verdict"] == "unreadable"
    assert classify_row({"c": 1.0}, {"c": None})["verdict"] == "unreadable"


def test_a_truncated_session_that_only_MISSED_THE_LOW_is_convicted():
    """One side of the range is enough. A capture at 15:55 may have the day's high already."""
    from jobs.bars_audit import classify_row
    stored = {"o": 100.0, "h": 101.0, "l": 99.5, "c": 100.8}
    true = {"o": 100.0, "h": 101.0, "l": 97.0, "c": 97.5}
    assert classify_row(stored, true)["verdict"] == "unsettled_capture"


# ── the repair writes only what was convicted ─────────────────────────────

@pytest.mark.asyncio
async def test_THE_REPAIR_TOUCHES_ONLY_UNSETTLED_CAPTURES():
    from jobs import bars_audit

    writes = []

    class _Conn:
        async def execute(self, sql, *a):
            writes.append(a)

    report = {"findings": [
        {"ticker": "SPY", "date": "2026-10-16", "verdict": "unsettled_capture",
         "stored_c": 764.29,
         "vendor": {"o": 773.24, "h": 773.25, "l": 760.64, "c": 763.25, "v": 64384579}},
        {"ticker": "QQQ", "date": "2026-10-16", "verdict": "basis_difference",
         "stored_c": 712.57, "vendor": {"o": 1, "h": 1, "l": 1, "c": 709.80, "v": 1}},
        {"ticker": "IWM", "date": "2026-10-16", "verdict": "mismatch_unexplained",
         "stored_c": 270.67, "vendor": {"o": 1, "h": 1, "l": 1, "c": 270.44, "v": 1}},
        {"ticker": "SMH", "date": "2026-10-16", "verdict": "match", "stored_c": 1.0,
         "vendor": {"o": 1, "h": 1, "l": 1, "c": 1.0, "v": 1}},
    ]}
    out = await bars_audit.repair(_Conn(), report)
    assert out["repaired_count"] == 1
    assert out["repaired"][0] == {"ticker": "SPY", "date": "2026-10-16",
                                  "was": 764.29, "now": 763.25}
    assert len(writes) == 1, "only the convicted row is written"
    assert writes[0][0] == "SPY"
    assert writes[0][1] == dt.date(2026, 10, 16), "a date object, not a string"
    # The others are reported as skipped so a reader sees they were considered.
    skipped = {s["verdict"] for s in out["skipped"]}
    assert skipped == {"basis_difference", "mismatch_unexplained"}


@pytest.mark.asyncio
async def test_an_INCOMPLETE_VENDOR_BAR_is_not_written():
    """A convicted row still needs four prices to replace it with. A None would write a NULL
    over a wrong-but-present number, which is worse."""
    from jobs import bars_audit

    class _Conn:
        async def execute(self, sql, *a):
            raise AssertionError("nothing may be written")

    out = await bars_audit.repair(_Conn(), {"findings": [
        {"ticker": "SPY", "date": "2026-10-16", "verdict": "unsettled_capture",
         "stored_c": 764.29, "vendor": {"o": None, "h": 1, "l": 1, "c": 763.25, "v": 1}}]})
    assert out["repaired_count"] == 0
    assert out["skipped"][0]["verdict"] == "vendor_bar_incomplete"


def test_the_repair_is_an_UPDATE_of_named_rows_not_a_delete_and_reinsert():
    code = code_of_file(os.path.join(BACKEND, "jobs", "bars_audit.py"))
    assert "UPDATE stable_daily_bars" in code
    assert "WHERE ticker = $1 AND date = $2" in code
    assert "DELETE" not in code.upper()


def test_the_repair_states_the_SEAM_it_is_crossing():
    """It writes split-only figures into a fully-adjusted table. For the newest sessions, before
    any dividend has gone ex, the two bases are the same number -- which is exactly the window
    the ruling names. That is written down, because it is not a licence for deep history."""
    raw = read_source(os.path.join(BACKEND, "jobs", "bars_audit.py"))
    # A fragment that does not straddle the line wrap -- "not a licence" is split across two
    # source lines, so asserting the whole sentence fails on the newline, not on the content.
    assert "licence to repair deep history" in raw
    assert "the two bases are the same number" in raw


# ── (c)1: the capture job writes only settled sessions ────────────────────

def test_THE_CAPTURE_JOB_WRITES_ONLY_SETTLED_SESSIONS():
    """R-IV.1203(c)1. Already true from the R-IV.1176 clamp, and locked here now it is ruled:
    `include_unsettled` defaults False and the window is clamped either way."""
    import inspect
    from stable_engine import bars_yf
    sig = inspect.signature(bars_yf.download_and_store)
    assert sig.parameters["include_unsettled"].default is False
    code = code_of_file(os.path.join(BACKEND, "stable_engine", "bars_yf.py"))
    assert "last_settled_session()" in code
    i = code.index("if include_unsettled:")
    assert "last_settled_session" in code[i:i + 400], (
        "the else branch must clamp to the last settled session")


def test_NOTHING_IN_THE_APP_OPTS_INTO_UNSETTLED_BARS():
    """The clamp only helps if no caller turns it off. Checked across the app, tests excluded --
    one test opts in deliberately, to prove the flag still works."""
    offenders = []
    for base, dirs, files in os.walk(BACKEND):
        parts = base.split(os.sep)
        if any(p in parts for p in ("tests", "__pycache__")):
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(base, f)
            try:
                src = code_of_file(path)
            except (SyntaxError, UnicodeDecodeError):
                continue
            if "include_unsettled=True" in src:
                offenders.append(os.path.relpath(path, BACKEND))
    assert offenders == [], offenders


def test_THE_BAR_TABLE_HAS_EXACTLY_ONE_WRITER():
    """A second writer would not have to honour the clamp, and that is how the 10-16 row got
    there in the first place -- written before the clamp existed."""
    writers = []
    for base, dirs, files in os.walk(BACKEND):
        parts = base.split(os.sep)
        if any(p in parts for p in ("tests", "__pycache__")):
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(base, f)
            try:
                src = code_of_file(path)
            except (SyntaxError, UnicodeDecodeError):
                continue
            if "INSERT INTO stable_daily_bars" in src:
                writers.append(os.path.relpath(path, BACKEND).replace(os.sep, "/"))
    assert writers == ["stable_engine/db.py"], writers


# ── (c)3: the docstring line ──────────────────────────────────────────────

def test_THE_BASIS_LINE_IS_IN_THE_DOCSTRING():
    """R-IV.1203(c): "Add one line to its docstring: not a returns basis (strategy-lab §3.3)." """
    import stable_engine.bars_yf as m
    doc = m.__doc__ or ""
    assert "not a returns basis" in doc
    assert "strategy-lab" in doc and "3.3" in doc
    assert "fully adjusted" in doc, "and what the basis IS, so the line has a subject"


def test_the_docstring_also_names_where_a_returns_basis_LIVES():
    """A line saying what a thing is NOT, with no pointer to what is, sends the next reader
    looking. `regime_daily_bars` is the split-adjusted, dividend-unadjusted series."""
    import stable_engine.bars_yf as m
    assert "regime_daily_bars" in (m.__doc__ or "")


# ── the route is authed and read-only by default ──────────────────────────

def test_THE_AUDIT_ROUTE_IS_AUTHED_AND_READ_ONLY_BY_DEFAULT():
    """`repair=true` rewrites rows, so it sits behind require_api_key like every other write on
    this hub -- and the audit can be run and read without the power to change anything."""
    src = read_source(os.path.join(BACKEND, "api", "stable.py"))
    i = src.index('@router.post("/bars-audit")')
    body = src[i:i + 1600]
    assert "Depends(require_api_key)" in body
    assert "repair: bool = Query(False)" in body
    import api.stable as s
    route = next(r for r in s.router.routes if r.path == "/stable/bars-audit")
    assert set(route.methods) == {"POST"}


def test_the_core8_is_CITED_not_restated():
    """Eight names, taken from the one 8-ticker census this repo defines, so the two cannot
    drift apart."""
    from api.darkpool_backfill_status import CENSUS
    from jobs.bars_audit import CORE8
    assert tuple(CORE8) == tuple(CENSUS)
    assert len(CORE8) == 8
    code = code_of_file(os.path.join(BACKEND, "jobs", "bars_audit.py"))
    assert "from api.darkpool_backfill_status import CENSUS" in code
