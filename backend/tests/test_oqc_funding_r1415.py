"""R-IV.1415(c) — the +20 for option_quote_capture and its three conditions, and (b)1's line.

  (c)1 the calls count in the hub's daily total and under the existing shed levels
  (c)2 the job has its OWN FAIL-CLOSED CEILING, like the grid's
  (c)3 job_runs records each run
  (b)1 every bars run logs ONE line: the held sessions skipped (count AND range) and the
       sessions written

(c)2 and (c)3 were real changes. The ceiling was the literal 288 -- which is exactly
0.96 x 300, so the fraction was already there, frozen into a number. Two faults followed: a
quota raise did not move it, so this very +20 would have funded nothing; and an UNREGISTERED
tag would still have spent 288 on the governor's DEFAULT_QUOTA of 500, which is the
`outcome_resolver` fault the quota table already records. And nothing recorded this job's runs
at all, so a slot lost to a missing database pool left only a log line -- under the collector
law that slot is permanently absent.
"""
from __future__ import annotations

import ast
import os

import pytest

from integrations import uw_governor as g
from jobs import job_runs
from jobs import option_quote_capture as oqc

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)
OQC_FILE = os.path.join(BACKEND, "jobs", "option_quote_capture.py")
F_EXPORT = os.path.join(REPO, "scripts", "f_export.py")
BARS_JOB = os.path.join(REPO, "scripts", "f_export_bars.py")


def _src(path):
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _fn(path, name):
    for node in ast.walk(ast.parse(_src(path))):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name):
            return ast.unparse(node)
    raise AssertionError("%s not found in %s" % (name, path))


# ── (c)1 the calls are in the hub's total and under the existing shed ───────

def test_the_calls_count_in_the_HUB_total_and_shed_at_STANDARD():
    """Condition 1. The tag is in QUOTAS -- which IS the DAILY_BUDGET table -- so its calls are
    inside the hub total the shed thresholds are measured against, and it is STANDARD, so it
    sheds at 75%. Not FOREGROUND: a forward collection should be shed before a live quote."""
    from integrations.uw_api_cache import DAILY_BUDGET, UW_ACCOUNT_LIMIT

    assert oqc.CALLER_TAG in g.QUOTAS, "it would be funded from outside the hub total"
    assert oqc.CALLER_TAG not in g.FOREIGN_RESERVE_QUOTAS
    quota, tier = g.quota_for(oqc.CALLER_TAG)
    assert (quota, tier) == (320, g.TIER_STANDARD)
    assert g.ACCOUNT_SHED_AT[tier] == 0.75
    assert int(g.ACCOUNT_SHED_AT[tier] * UW_ACCOUNT_LIMIT) == 30000
    # And the raise came from the buffer, so the table still lands exactly on its ceiling.
    assert g.QUOTA_SAFETY_BUFFER == 1290
    assert sum(q for q, _ in g.QUOTAS.values()) == DAILY_BUDGET - g.QUOTA_SAFETY_BUFFER


def test_the_raise_RESTORES_the_sizing_margin_it_was_asked_for():
    """The whole point of the +20. Measured peak 244; this table's rule is quota >= 1.2 x peak,
    so the safe ceiling at 300 was 250 -- already reached BEFORE the 15:59 slot added
    ~14-20 calls a day. 320/1.2 = 266.7, which clears 244."""
    quota, _ = g.quota_for(oqc.CALLER_TAG)
    assert quota / 1.2 > 244, quota / 1.2


# ── (c)2 the fail-closed ceiling ────────────────────────────────────────────

def test_the_ceiling_is_DERIVED_from_the_ruled_quota():
    assert oqc.session_ceiling() == int(320 * oqc.SESSION_CEILING_FRACTION) == 307
    assert oqc.SESSION_CEILING_FRACTION == 0.96


def test_the_frozen_LITERAL_is_gone():
    """288 is exactly 0.96 x 300 -- the fraction was always there, frozen. While it was a
    literal, a quota raise moved nothing, so R-IV.1415(c)'s own +20 would have funded nothing.
    Scanned on PARSED code: the docstrings explain the number, and a raw-text scan would fail
    on the explanation."""
    tree = ast.parse(_src(OQC_FILE))
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            docs.add(id(body[0]))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            node.body = [n for n in body if id(n) not in docs] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "SESSION_CALL_CEILING" not in code, (
        "the frozen ceiling is still referenced in executable code")
    assert not hasattr(oqc, "SESSION_CALL_CEILING")


def test_it_FAILS_CLOSED_when_the_tag_is_unregistered():
    """Like the grid's. An unregistered tag is NOT inert -- `quota_for` falls back to
    DEFAULT_QUOTA 500 -- so a ceiling that ignored registration would spend 288 calls on a
    path nobody had approved."""
    assert oqc.tag_is_registered()
    saved = g.QUOTAS.pop(oqc.CALLER_TAG)
    try:
        assert oqc.tag_is_registered() is False
        assert oqc.session_ceiling() == 0
        assert oqc.slot_allowance(0, len(oqc.SLOT_TIMES_ET)) == 0, (
            "every slot must get a zero allowance while the tag is unfunded")
    finally:
        g.QUOTAS[oqc.CALLER_TAG] = saved
    assert oqc.session_ceiling() == 307


def test_an_unreadable_quota_table_is_not_a_licence_to_spend():
    import sys
    real = sys.modules.get("integrations.uw_governor")
    sys.modules["integrations.uw_governor"] = None
    try:
        assert oqc.tag_is_registered() is False
        assert oqc.session_ceiling() == 0
    finally:
        if real is not None:
            sys.modules["integrations.uw_governor"] = real
        else:
            sys.modules.pop("integrations.uw_governor", None)


def test_the_per_slot_allowance_follows_the_new_ceiling():
    """307 // 13 = 23, up from 288 // 13 = 22. Derived in the test too -- a literal here would
    have to be edited by whoever changes the quota next, and silently passes if they do not."""
    n = len(oqc.SLOT_TIMES_ET)
    assert oqc.slot_allowance(0, n) == oqc.session_ceiling() // n == 23
    # The close is still never starved: the last slot keeps a reserved share.
    assert oqc.slot_allowance(oqc.session_ceiling() - 5, 1) == 5


# ── (c)3 job_runs records each run ──────────────────────────────────────────

def test_the_job_name_is_in_the_vocabulary_module():
    assert job_runs.JOB_OPTION_QUOTE_CAPTURE == "option_quote_capture" == oqc.CALLER_TAG


def test_the_run_opens_PAST_both_early_returns():
    """PER SLOT ATTEMPT, never per tick. The loop wakes every 60 seconds and `capture_slot`
    returns "no slot due" on almost all of them; recording those would write ~1,440 rows a day
    and bury the thirteen that mean something."""
    code = _fn(OQC_FILE, "capture_slot")
    i_due = code.index("no slot due")
    i_already = code.index("already captured")
    i_start = code.index("start_run")
    assert i_due < i_start, "a tick with no slot due would open a run"
    assert i_already < i_start, "a re-visit to a captured slot would open a run"


def test_the_run_is_CLOSED_on_the_slots_one_exit():
    code = _fn(OQC_FILE, "capture_slot")
    assert "_finish(_run_id" in code
    closer = _fn(OQC_FILE, "_finish")
    assert "finish_run" in closer


@pytest.mark.asyncio
async def test_the_three_statuses_say_three_DIFFERENT_things():
    """`ok` stored rows; `completed_defective` ran and stored nothing; `error` had no database
    pool, so the slot is LOST. The third is the one worth having -- under the collector law a
    slot not captured is permanently absent, and its only trace was a log line."""
    import jobs.job_runs as jr

    seen = []
    real = jr.finish_run

    async def fake(run_id, status, **kw):
        seen.append((status, kw.get("rows_touched"), kw.get("error") or ""))

    jr.finish_run = fake
    try:
        await oqc._finish(1, {"slot": "15:59", "rows": 40, "absent": 0, "unavailable": 0,
                              "shed": 0, "planned": 8}, object())
        await oqc._finish(1, {"slot": "15:59", "rows": 0, "absent": 8, "unavailable": 0,
                              "shed": 0, "planned": 8}, object())
        await oqc._finish(1, {"slot": "15:59", "rows": 0, "absent": 0, "unavailable": 0,
                              "shed": 0, "planned": 8}, None)
        await oqc._finish(None, {"rows": 0}, None)      # no run opened -> nothing recorded
    finally:
        jr.finish_run = real

    assert len(seen) == 3, seen
    assert seen[0][0] == job_runs.STATUS_OK and seen[0][1] == 40
    assert seen[1][0] == job_runs.STATUS_COMPLETED_DEFECTIVE and "stored no rows" in seen[1][2]
    assert seen[2][0] == job_runs.STATUS_ERROR and "LOST" in seen[2][2]


def test_no_status_LABEL_is_INVENTED():
    known = {job_runs.STATUS_RUNNING, job_runs.STATUS_OK, job_runs.STATUS_ERROR,
             job_runs.STATUS_TIMEOUT, job_runs.STATUS_SKIPPED,
             job_runs.STATUS_COMPLETED_DEFECTIVE, job_runs.STATUS_DEGRADED}
    closer = _fn(OQC_FILE, "_finish")
    used = []
    for node in ast.walk(ast.parse(closer)):
        if isinstance(node, ast.Name) and node.id.startswith("STATUS_"):
            used.append(getattr(job_runs, node.id))
    assert used and set(used) <= known, set(used) - known


def test_the_record_cannot_break_the_capture():
    """Bookkeeping must not break the job it records -- and this job's product is a slot that
    cannot be recaptured."""
    for name in ("capture_slot", "_finish"):
        code = _fn(OQC_FILE, name)
        assert "except Exception" in code, name


def test_the_surface_reports_the_ceiling_and_the_registration():
    code = _fn(OQC_FILE, "capture_status")
    assert "session_ceiling()" in code and "tag_is_registered()" in code


# ── (b)1 one line, with the held RANGE ──────────────────────────────────────

def test_the_bars_run_logs_ONE_line_with_the_held_RANGE_and_what_it_wrote():
    """A bare count cannot be checked against R-IV.1378(c)'s 09-25..10-15, so a hold that
    silently widened or slipped would look identical to one working correctly. One line,
    because this log is read by scrolling to the end of a file."""
    code = _fn(BARS_JOB, "main")
    assert "held_range" in code and "wrote_range" in code
    assert "HELD" in code and "WROTE" in code
    # The range comes from real dates, not from the window bounds.
    assert "held_dates" in code


def test_the_export_keeps_the_held_DATES_not_just_a_count():
    """The range has to come from the sessions actually skipped. Deriving it from the ruling's
    own constants would make the line restate the rule rather than report the run."""
    code = _fn(F_EXPORT, "export_bars1m").replace('"', "'")
    assert "held_dates" in code
    assert "summary['held_dates'].add(d.isoformat())" in code
    assert "summary['held_dates'] = sorted(summary['held_dates'])" in code


def test_the_falsifier_lives_OUTSIDE_the_repo():
    """R-IV.1415(d)3 and the point of a falsifier: kept out of the repo so it cannot be made to
    agree with the code it tests, and so it survives the purge re-clone."""
    assert os.path.isfile(r"C:\lane-state\bars_hold_falsifier.py")
    assert not os.path.exists(os.path.join(REPO, "scripts", "bars_hold_falsifier.py"))
    src = _src(r"C:\lane-state\bars_hold_falsifier.py")
    # It hard-codes the held range rather than importing it, deliberately.
    assert "HELD_FROM = date(2026, 9, 25)" in src
    assert "HELD_TO = date(2026, 10, 15)" in src
    assert "from f_export import" not in src and "import f_export" not in src
