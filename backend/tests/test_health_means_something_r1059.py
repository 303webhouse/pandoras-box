"""R-IV.1059(b)+(c) — `degraded` must mean a real fault; and a read-only spend route.

MEASURED 2026-10-15 02:10 MT, before this change: the ONLY two classes in flatline were the
ONLY two with `registered: false`, and every registered class was `ok`.

    class            age      job_runs    signals ever   schedule
    lab_registered   21.2 h   2 runs      3              one morning pass per session
    wrr_scanner      11.8 h   NONE        1              16:20 ET, Mon-Fri, post-close

Neither was broken. Each had last emitted on its own scheduled run, and both were judged
against the 4-hour DEFAULT SLO -- which a once-daily producer cannot satisfy for ~20 hours of
every 24. Both are therefore **EXPECTED**, and the classification is implemented as this file
already does for the other session passes: registered, session-scoped, judged on whether a due
PASS completed rather than on whether anything was emitted.

THE ORDER MATTERED, and this file says so itself about the crypto producers: re-pointing a
class at `job_runs` it does not write renders `no_data`, which does NOT set `any_flatline` --
turning the sentinel off and calling it a fix. `wrr_daily_scan` was given its job_runs write in
bias_scheduler FIRST; `lab_registered_shadow` already had one.
"""
from __future__ import annotations

import ast
import inspect
import os

import pytest

from stable_engine import signals_freshness as f

BOTH = ("lab_registered", "wrr_scanner")


def _code_only(src: str) -> str:
    """Source with comments AND DOCSTRINGS removed.

    THE DISTINCTION THAT BIT ME: `ast.unparse` drops comments but KEEPS docstrings. The first
    version of `test_it_writes_NOTHING` matched the word "UPDATE" in this very module's own
    docstring, which says it performs no INSERT, UPDATE or DELETE. Eighth instance of the prose
    trap in this register, and the first one where "parsed, not grepped" was not enough on its
    own. Docstrings are removed BY IDENTITY -- the first statement of a body -- never by
    comparing against `ast.get_docstring()`, which cleans indentation and so never matches.
    """
    tree = ast.parse(src)
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
    return ast.unparse(tree)


def _read(path: str) -> str:
    """utf-8-sig, because `scheduler/bias_scheduler.py` carries a BOM and `ast.parse` rejects
    U+FEFF outright. A plain utf-8 read made the parse fail rather than the assertion."""
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


# ── 1. the classification: EXPECTED, implemented as a session pass ───────────

@pytest.mark.parametrize("cls", BOTH)
def test_the_class_is_registered(cls):
    """Unregistered was half the defect: it could degrade the hub while nobody had declared
    what it was supposed to do."""
    assert cls in f.REGISTERED_CLASSES


@pytest.mark.parametrize("cls", BOTH)
def test_it_is_judged_as_a_once_per_session_pass(cls):
    assert cls in f.SESSION_JOB_CLASSES


@pytest.mark.parametrize("cls", BOTH)
def test_the_four_hour_default_no_longer_applies(cls):
    """THE DEFECT ITSELF. A once-daily producer measured against 4 hours is stale ~20 hours a
    day by construction -- the "guaranteed false red" this module warns about twice already."""
    assert f.SLO_SECONDS.get(cls) == 26 * 3600
    assert f.SLO_SECONDS[cls] > f.DEFAULT_SLO_SECONDS


@pytest.mark.parametrize("cls", BOTH)
def test_it_is_judged_on_the_pass_not_on_emission(cls):
    """Three signals ever for one, one for the other, both by design. Emission is the wrong
    instrument; whether the scan ran is the right one."""
    assert f.AGE_SOURCES.get(cls) == f.AGE_SOURCE_JOB_RUNS


def test_each_class_points_at_the_job_name_that_actually_writes_job_runs():
    assert f.AGE_SOURCE_JOB_NAME["lab_registered"] == "lab_registered_shadow"
    assert f.AGE_SOURCE_JOB_NAME["wrr_scanner"] == "wrr_daily_scan"


def test_the_wrr_job_WRITES_the_job_runs_row_it_is_now_judged_on():
    """THE ORDERING CONTROL, and the most important test here.

    `wrr_scanner` had NO job_runs row at all. Pointing it at job_runs without writing one
    renders `no_data`, which does not set `any_flatline` -- so /health would have gone quiet
    about a class it could no longer judge. The write has to exist for the mapping to be
    anything but a suppression.

    Parsed, not grepped: the file is 3,000+ lines of prose-heavy comments and the job name
    appears in several of them.
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scheduler", "bias_scheduler.py")
    tree = ast.parse(_read(path))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
               and n.name == "run_wrr_scan_job"), None)
    assert fn is not None, "run_wrr_scan_job not found"
    code = ast.unparse(fn)
    assert "_record" in code, "the WRR job does not record a run"
    assert "'wrr_daily_scan'" in code or '"wrr_daily_scan"' in code
    assert "session_date" in code, "without session_date, _record writes no job_runs row"


def test_lab_registered_already_had_its_write():
    """Asserted rather than assumed -- it is why only one of the two needed a new write."""
    from strategies import registered_shadow
    assert registered_shadow.JOB_NAME == "lab_registered_shadow"
    code = _code_only(inspect.getsource(registered_shadow.run))
    assert "_record" in code and "session_date" in code


# ── 2. the aggregate: only a declared expectation can be violated ────────────

#: `signals_freshness_summary` is async and reads the database, so the aggregate RULE is
#: asserted on the code that implements it here, and the BEHAVIOUR is verified through the
#: live /health payload after deploy. Neither alone would be enough: the source check cannot
#: prove the payload changed, and the live check cannot run in CI.


def test_only_a_registered_class_can_move_the_aggregate():
    """The rule, asserted on the code that implements it. Before this, the union of
    "registry + anything observed" let an unsupervised class set `any_flatline`, so /health's
    `degraded` was driven by two classes nobody had armed."""
    src = inspect.getsource(f.signals_freshness_summary)
    code = ast.unparse(ast.parse(src))
    assert "if cls in REGISTERED_CLASSES" in code, (
        "the aggregate must gate on registration:\n%s" % code[:1200])


def test_an_unregistered_class_is_still_SURFACED_by_name():
    """Not a suppression. The union stays, the class keeps its own status, and it is listed --
    so a new producer appears by name instead of silently setting off an alarm nobody armed,
    and instead of vanishing."""
    src = ast.unparse(ast.parse(inspect.getsource(f.signals_freshness_summary)))
    assert "unregistered_classes" in src
    assert "worst_status_unregistered" in src
    assert "aggregate_basis" in src, "the payload must say which question it answers"


def test_the_union_that_surfaces_them_is_still_there():
    """THE PAIR. If the union were narrowed to the registry instead, an unregistered producer
    would disappear from /health entirely -- a worse failure than the false alarm."""
    src = ast.unparse(ast.parse(inspect.getsource(f.signals_freshness_summary)))
    assert "REGISTERED_CLASSES | set(ages) | set(counters)" in src.replace("\n", " ")


def test_the_registered_set_did_not_lose_anybody():
    """A reallocation of attention, not a cull."""
    for cls in ("tradingview", "server_scanner", "cta_scanner", "crypto_scanner",
                "crypto_engine", "crypto_cvd_engine", "footprint", "STRIKE_IB_BREAK",
                "triton_grader", "circes_stew", "circes_stew_unsurfaced", "shadow_grader"):
        assert cls in f.REGISTERED_CLASSES, cls


# ── 3. (c) the read-only spend route ─────────────────────────────────────────

def test_the_route_exists_and_is_authed():
    from api import uw_spend
    assert uw_spend.router.prefix == "/uw"
    paths = [r.path for r in uw_spend.router.routes]
    assert "/uw/spend" in paths
    src = inspect.getsource(uw_spend.uw_spend)
    assert "require_api_key" in src or "Depends(require_api_key)" in inspect.getsource(uw_spend)


def test_it_is_GET_only():
    from api import uw_spend
    for r in uw_spend.router.routes:
        assert set(getattr(r, "methods", set())) <= {"GET", "HEAD"}, r.path


def test_it_writes_NOTHING():
    """R-IV.1059(c): no writes. Asserted on the parsed source so a comment mentioning INSERT
    cannot fail it and a real INSERT cannot hide behind one."""
    from api import uw_spend
    code = _code_only(inspect.getsource(uw_spend))
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "insert into", "ALTER "):
        assert verb.lower() not in code.lower(), verb


def test_it_spends_no_UW_budget():
    """A route built to diagnose over-spending must not itself spend."""
    from api import uw_spend
    code = _code_only(inspect.getsource(uw_spend))
    for spender in ("_uw_request", "get_snapshot", "get_ohlc", "httpx"):
        assert spender not in code, spender


def test_headroom_is_reported_against_the_1_2x_RULE_not_just_the_quota():
    """The figure that would have caught the Hermes outage BEFORE it broke: a tag at its own
    measured peak x1.0 has no margin left under the rule the table was built with, even though
    it has breached nothing yet."""
    from api.uw_spend import SIZING_MULTIPLIER, _headroom
    assert SIZING_MULTIPLIER == 1.2
    h = _headroom(1100, 1000)
    assert h["safe_ceiling_at_1_2x"] == int(1100 / 1.2)
    assert h["over_sizing_rule"] is True
    assert h["at_or_over_quota"] is False


def test_the_two_states_are_distinguished():
    """At-or-over quota is a fault NOW; over the sizing rule is a fault SOON. Collapsing them
    would either cry wolf or report the outage only once it had happened."""
    from api.uw_spend import _headroom
    at = _headroom(1100, 1100)
    assert at["at_or_over_quota"] is True
    assert at["calls_left"] == 0
    fine = _headroom(1100, 500)
    assert fine["over_sizing_rule"] is False and fine["at_or_over_quota"] is False


def test_the_snapshot_outage_is_reproducible_through_the_helper():
    """The measured figures from the outage, run back through the instrument."""
    from api.uw_spend import _headroom
    assert _headroom(1100, 1106)["at_or_over_quota"] is True          # 2026-10-13
    assert _headroom(1100, 1100)["at_or_over_quota"] is True          # 2026-10-14
    assert _headroom(1100, 458)["at_or_over_quota"] is False          # 2026-10-12 baseline


def test_a_failed_ledger_read_is_null_not_zero():
    """A spend of 0 and "I could not read the spend" are opposite facts. Reporting the second
    as the first is how a quota outage hides."""
    from api import uw_spend
    code = _code_only(inspect.getsource(uw_spend))
    assert "read_error" in code
    assert "None if read_error" in code.replace("\n", " ")
