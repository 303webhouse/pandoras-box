"""The B2 cut alert, wired — R-IV.892(e)1.

The decision is tested in test_b2_cut_alert_r888.py. This covers what can only go wrong once it
is connected to a webhook and a column:

  * the flag is written ONLY after a delivered alert, so a failed webhook retries instead of
    going permanently quiet;
  * the flag gates the PUSH, not the evaluation;
  * UNDETERMINED is reported rather than swallowed;
  * nothing closes anything.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from jobs import b2_cut_alert_job as job  # noqa: E402

ET = ZoneInfo("America/New_York")
AT_CUT = datetime(2026, 10, 15, 16, 0, tzinfo=ET)


def _verdict(**over):
    v = {"verdict": "NOT_PROFITABLE", "position_id": "P1", "ticker": "KNX", "total_pnl": "-12.00",
         "cut_session": "2026-10-15", "reason": "flat fires"}
    v.update(over)
    return v


@pytest.fixture(autouse=True)
def _no_webhook_by_default(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_ALERTS", raising=False)
    monkeypatch.delenv(job.FLAG, raising=False)


# ── the flag gates the push, not the evaluation ──────────────────────────────

def test_with_the_flag_off_it_evaluates_but_never_delivers(monkeypatch):
    delivered = []

    async def fake_eval(now=None, pool=None):
        return [_verdict()]

    async def fake_deliver(v):
        delivered.append(v)
        return True

    monkeypatch.setattr(job, "evaluate", fake_eval)
    monkeypatch.setattr(job, "_deliver", fake_deliver)
    out = asyncio.run(job.run(AT_CUT))
    assert out["evaluated"] == 1
    assert out["by_verdict"] == {"NOT_PROFITABLE": 1}
    assert out["fired"] == 0
    assert delivered == [], "the flag must gate the PUSH, and it delivered anyway"


def test_with_the_flag_on_it_delivers_then_flags(monkeypatch):
    order = []

    async def fake_eval(now=None, pool=None):
        return [_verdict()]

    async def fake_deliver(v):
        order.append("deliver")
        return True

    async def fake_mark(v, pool=None):
        order.append("flag")
        return True

    monkeypatch.setenv(job.FLAG, "true")
    monkeypatch.setattr(job, "evaluate", fake_eval)
    monkeypatch.setattr(job, "_deliver", fake_deliver)
    monkeypatch.setattr(job, "_mark_fired", fake_mark)
    out = asyncio.run(job.run(AT_CUT))
    assert out["fired"] == 1
    assert order == ["deliver", "flag"], order


# ── THE ORDERING THAT MATTERS ───────────────────────────────────────────────

def test_a_failed_delivery_does_NOT_flag_the_row(monkeypatch):
    """Flagging first would turn one failed webhook into a PERMANENT silence: the row would read
    "already fired" forever and the prompt would never arrive. Phase 1's Hermes rule, same
    reason. So the flag write must be unreachable when delivery fails."""
    flagged = []

    async def fake_eval(now=None, pool=None):
        return [_verdict()]

    async def failed_deliver(v):
        return False

    async def fake_mark(v, pool=None):
        flagged.append(v)
        return True

    monkeypatch.setenv(job.FLAG, "true")
    monkeypatch.setattr(job, "evaluate", fake_eval)
    monkeypatch.setattr(job, "_deliver", failed_deliver)
    monkeypatch.setattr(job, "_mark_fired", fake_mark)
    out = asyncio.run(job.run(AT_CUT))
    assert out["fired"] == 0
    assert flagged == [], "a failed delivery flagged the row and silenced it for good"


def test_a_delivered_alert_whose_flag_write_fails_is_not_counted(monkeypatch):
    """The other half: the alert went out, the flag did not. It must not count as fired, so the
    next pass sends it again -- a duplicate prompt, which is the safe direction."""
    async def fake_eval(now=None, pool=None):
        return [_verdict()]

    async def ok_deliver(v):
        return True

    async def failed_mark(v, pool=None):
        return False

    monkeypatch.setenv(job.FLAG, "true")
    monkeypatch.setattr(job, "evaluate", fake_eval)
    monkeypatch.setattr(job, "_deliver", ok_deliver)
    monkeypatch.setattr(job, "_mark_fired", failed_mark)
    assert asyncio.run(job.run(AT_CUT))["fired"] == 0


def test_the_flag_update_only_touches_an_unflagged_row():
    """`AND b2_cut_alerted_at IS NULL` on the UPDATE, so a concurrent pass cannot overwrite the
    first fire's timestamp and move the record of when it fired."""
    import inspect

    src = inspect.getsource(job._mark_fired)
    assert "b2_cut_alerted_at IS NULL" in src


# ── UNDETERMINED is reported, not swallowed ─────────────────────────────────

def test_undetermined_is_logged_at_warning(monkeypatch, caplog):
    """A position nobody can price at its cut is a GAP in the alert's coverage, and a silent gap
    looks exactly like a pass."""
    import logging

    async def fake_eval(now=None, pool=None):
        return [_verdict(verdict="UNDETERMINED", reason="no mark on the position")]

    monkeypatch.setattr(job, "evaluate", fake_eval)
    with caplog.at_level(logging.WARNING, logger="b2.cut_alert"):
        out = asyncio.run(job.run(AT_CUT))
    assert out["by_verdict"] == {"UNDETERMINED": 1}
    assert any("UNDETERMINED" in r.message or "UNDETERMINED" in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]


# ── it never acts ───────────────────────────────────────────────────────────

def test_the_job_writes_only_the_flag_column():
    """PARSED for SQL verbs: the only write is the flag UPDATE and the ADD COLUMN. An alert that
    could close a position is not an alert."""
    import ast
    import re

    src = open(__file__.rsplit("tests", 1)[0] + "jobs/b2_cut_alert_job.py",
               encoding="utf-8").read()
    # Docstrings removed so the prose explaining "never closes" cannot satisfy the check.
    tree = ast.parse(src)
    kill = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = getattr(node, "body", None) or []
            if (b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                kill.update(range(b[0].lineno - 1, (b[0].end_lineno or b[0].lineno)))
    code = "\n".join("" if i in kill else l.split("#")[0]
                     for i, l in enumerate(src.split("\n")))

    updates = re.findall(r"UPDATE\s+(\w+)", code, re.I)
    # TA-152 adds a SECOND write: the alert now reads its own post-close mark and stores it.
    # So the guard polices the COLUMNS rather than the statement count -- which is the stronger
    # question anyway, because the thing that must never happen is a write that could close a
    # position, not a write that exists.
    assert set(updates) == {"unified_positions"}, updates
    assert len(updates) == 2, "expected the flag write and the mark write, found %d" % len(updates)
    assert "SET b2_cut_alerted_at" in code

    # Only the flag and the four mark columns may be assigned, and nothing that could close,
    # resize or re-price a position.
    assigned = set(re.findall(r"(?:SET|,)\s*(\w+)\s*=\s*(?:\$\d+|NOW\(\))", code))
    allowed = {"b2_cut_alerted_at", "mark", "mark_as_of", "mark_integrity",
               "mark_integrity_reason"}
    assert assigned <= allowed, "the job assigns columns it may not: %s" % (assigned - allowed)
    for forbidden in ("status", "closed_at", "quantity", "open_quantity", "entry_price",
                      "current_price", "realized_pnl", "unrealized_pnl"):
        assert "SET %s" % forbidden not in code and ", %s =" % forbidden not in code, forbidden
    for verb in ("DELETE FROM", "INSERT INTO", "DROP "):
        assert verb not in code.upper(), verb


def test_open_quantity_is_not_recomputed_here():
    """R-IV.660(b)2: services/open_quantity.py exists so no consumer computes it. A second
    implementation would be a second author of the rule for what is still open."""
    import ast

    src = open(__file__.rsplit("tests", 1)[0] + "jobs/b2_cut_alert_job.py",
               encoding="utf-8").read()
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.update("%s.%s" % (node.module, a.name) for a in node.names)
    assert "services.open_quantity.stamp_open_quantity" in imported, sorted(imported)


def test_realized_comes_from_the_closure_ledger_not_the_row():
    """A partial exit's realized stays on an OPEN row and the row's column has been measured
    under-reporting the book by 107.48."""
    assert "SUM(c.realized)" in job.SELECT_SQL
    assert "p.realized_pnl" not in job.SELECT_SQL


def test_duplicate_rows_are_excluded_case_insensitively():
    """R-IV.874: a retired duplicate's money counts once, on its keeper."""
    assert "UPPER(COALESCE(p.status, ''))" in job.SELECT_SQL
    assert "<> 'DUPLICATE_OF'" in job.SELECT_SQL
