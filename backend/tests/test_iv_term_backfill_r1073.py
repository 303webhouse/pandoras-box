"""R-IV.1073(c) — the IV term-structure backfill: scope, funding, and the reserve-date guard.

THE GUARD IS THE POINT OF THIS FILE. 2026-09-25 → 10-09 is the sealed TRITON-R reserve window
that R-IV.1064(a) pulls and R-IV.1073(d) says nobody analyses before step 8. A backfill that
fetched one of those dates would put holdout data into `iv_snapshots`, which this lane reads
freely -- and that cannot be undone by deleting the row, because the fetch itself is the leak.

So the guard RAISES and is asserted per request, not once per run. Every test below is paired:
the last approved date must be ACCEPTED, or a guard that refused everything would pass the
refusal tests and deliver nothing.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import os
from datetime import date

import pytest

from tests._srcscan import code_of, code_of_file, function_code

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO, "scripts", "iv_term_backfill.py")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("_iv_term_backfill", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── 1. the reserve guard ─────────────────────────────────────────────────────

def test_the_first_reserve_date_is_refused(mod):
    with pytest.raises(mod.ReserveDateRequested):
        mod.assert_not_reserve(date(2026, 9, 25))


@pytest.mark.parametrize("d", [date(2026, 9, 25), date(2026, 9, 28), date(2026, 10, 9),
                               date(2026, 10, 14), date(2027, 1, 1)])
def test_every_date_at_or_after_the_window_is_refused(d, mod):
    """A ceiling, not a range. Refusing only 09-25..10-09 would let 10-10 through, and the
    reserve window's END is not a thing this backfill should need to know."""
    with pytest.raises(mod.ReserveDateRequested):
        mod.assert_not_reserve(d)


def test_the_LAST_APPROVED_date_is_ACCEPTED(mod):
    """THE PAIR FOR THE WHOLE FILE. A guard that refused everything would satisfy every
    refusal test above and quietly deliver nothing -- the fake-safe answer."""
    mod.assert_not_reserve(date(2026, 9, 24))          # must not raise


@pytest.mark.parametrize("d", [date(2026, 9, 1), date(2026, 9, 10), date(2026, 9, 24)])
def test_dates_inside_the_approved_window_pass(d, mod):
    mod.assert_not_reserve(d)


def test_the_boundary_is_exactly_09_25(mod):
    assert mod.RESERVE_FIRST_DATE == date(2026, 9, 25)
    assert mod.WINDOW_END == date(2026, 9, 24)
    assert mod.WINDOW_END < mod.RESERVE_FIRST_DATE


def test_the_guard_is_applied_PER_REQUEST_not_once_per_run(mod):
    """A per-run check passes while a loop that computes its own dates walks past it. Parsed,
    not grepped: the docstrings here discuss the guard at length."""
    src = inspect.getsource(mod.run)
    tree = ast.parse(src.lstrip())
    fn = tree.body[0]
    doc = fn.body[0] if (fn.body and isinstance(fn.body[0], ast.Expr)
                         and isinstance(getattr(fn.body[0], "value", None), ast.Constant)
                         and isinstance(fn.body[0].value.value, str)) else None
    code = "\n".join(ast.unparse(n) for n in fn.body if n is not doc)
    assert "assert_not_reserve" in code, "run() must assert the guard itself"
    # and `sessions()` asserts it while BUILDING the list, so both layers check
    scode = ast.unparse(ast.parse(inspect.getsource(mod.sessions).lstrip()))
    assert "assert_not_reserve" in scode


def test_the_session_list_never_contains_a_reserve_date(mod):
    days = mod.sessions()
    assert len(days) == 17, days
    assert max(days) == date(2026, 9, 24)
    assert all(d < mod.RESERVE_FIRST_DATE for d in days)


# ── 2. the scope the ruling approved ─────────────────────────────────────────

def test_the_universe_is_the_EIGHT_census_names(mod):
    assert set(mod.CENSUS) == {"SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA"}
    assert len(mod.CENSUS) == 8


def test_it_does_NOT_reuse_the_nightly_hundred_name_universe(mod):
    """`iv_snapshot.universe()` is the registered shadow universe (~100 names) plus open
    underlyings. Reusing it would have turned a 136-call backfill into a four-figure one."""
    from strategies.registered_shadow import UNIVERSE
    assert len(UNIVERSE) > 50
    assert set(mod.CENSUS) != set(UNIVERSE)
    code = code_of(mod.run)
    assert "universe(" not in code


def test_the_planned_call_count_is_the_approved_136(mod):
    assert len(mod.sessions()) * len(mod.CENSUS) == 136


# ── 3. the funding, which is the other half of the ruling ────────────────────

def test_it_spends_the_RESERVE_tag(mod):
    from integrations.uw_governor import FOREIGN_RESERVE_QUOTAS, quota_for
    assert mod.CALLER_TAG == "iv_term_backfill"
    assert mod.CALLER_TAG in FOREIGN_RESERVE_QUOTAS
    quota, _tier = quota_for(mod.CALLER_TAG)
    assert quota >= 136, quota


def test_it_does_NOT_spend_iv_snapshot(mod):
    """`iv_snapshot` is 250/day from DAILY_BUDGET with a measured peak of 208. 136 calls
    through it would have exhausted the nightly IV snapshot -- the Hermes outage one tag over."""
    from integrations.uw_governor import QUOTAS
    assert QUOTAS["iv_snapshot"][0] == 250
    # ASSERT THE TAG, NOT THE SUBSTRING. The first version failed on `FROM iv_snapshots` in the
    # resume query -- the TABLE's name contains the CALLER TAG's name as a prefix. A bare
    # substring test cannot tell a table from a tag, and the module legitimately uses both.
    code = code_of(mod.run)
    assert "caller=CALLER_TAG" in code, "the fetch must carry this backfill's own tag"
    assert 'caller="iv_snapshot"' not in code and "caller='iv_snapshot'" not in code
    assert mod.CALLER_TAG != "iv_snapshot"


def test_it_does_not_touch_the_two_tags_at_their_ceiling(mod):
    """R-IV.1071(c): `darkpool_collector` and `triton_flow_shadow` were at 250/250 and 450/450
    on 2026-10-14 and may not be raised or spent without a ruling."""
    # CODE ONLY. This module's docstring names both tags in order to say it does NOT use
    # them, and the first version of this test failed on exactly that sentence -- the ninth
    # instance of the prose trap on record. `code_of_file` strips docstrings and comments.
    code = code_of_file(SCRIPT)
    for tag in ("darkpool_collector", "triton_flow_shadow"):
        assert tag not in code, tag


def test_the_reserve_still_has_room_after_this_claim():
    from integrations.uw_api_cache import UW_FOREIGN_RESERVE
    from integrations.uw_governor import FOREIGN_RESERVE_QUOTAS
    committed = sum(q for q, _ in FOREIGN_RESERVE_QUOTAS.values())
    assert committed <= UW_FOREIGN_RESERVE, (committed, UW_FOREIGN_RESERVE)
    # and the daily budget is untouched by a reserve claim
    from integrations.uw_governor import QUOTAS, QUOTA_SAFETY_BUFFER
    from integrations.uw_api_cache import DAILY_BUDGET as _DB
    # R-IV.1265(d) MOVED THE TOTAL: `notables_strip` (50) was funded by cutting the
    # safety buffer 2,000 -> 1,950, so the table now sums to 26,050. The literal 26,000
    # was hard-coded in FIVE separate test files, each written by a different carve to
    # say "this sum must not move" -- so the first ruled move broke all five at once.
    # The INVARIANT was never the literal; it is that the table fills the budget minus
    # the buffer exactly. Asserted that way now, so the next ruled change to either
    # number does not require editing five files that were never about the number.
    assert sum(q for q, _ in QUOTAS.values()) == _DB - QUOTA_SAFETY_BUFFER


def test_the_fetch_takes_a_caller_and_still_defaults_to_the_nightly_tag():
    from integrations.uw_api import get_iv_term_structure
    sig = inspect.signature(get_iv_term_structure)
    assert "caller" in sig.parameters
    assert sig.parameters["caller"].default == "iv_snapshot"
    assert sig.parameters["caller"].kind == inspect.Parameter.KEYWORD_ONLY


# ── 4. a refusal stops rather than spending the rest of the reserve ──────────

def test_a_governor_refusal_stops_the_run(mod):
    code = code_of(mod.run)
    assert "UWUnavailable" in code
    assert "stopped_early" in code


def test_it_reuses_the_snapshot_jobs_schema_rather_than_declaring_its_own(mod):
    """One author for `iv_snapshots`. A backfill writing its own near-identical DDL is how a
    table ends up with two definitions that drift."""
    code = code_of(mod.run)
    assert "from jobs.iv_snapshot import" in code or "jobs.iv_snapshot" in code
    assert "CREATE TABLE" not in code


def test_it_reports_counts_only(mod):
    """R-IV.1073(c)/1071(b)2: counts, not values. No IV or price may be printed."""
    src = open(SCRIPT, encoding="utf-8").read()
    code = code_of_file(SCRIPT)
    for leak in ("iv_near']", 's["iv_30d"]'):
        assert ("print" not in code) or (leak not in code.split("print")[-1]), leak
    assert "COUNTS ONLY" in src
