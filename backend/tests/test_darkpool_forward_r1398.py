"""R-IV.1398(b)3 — the forward dark-pool walk, and the three ways it could go quietly wrong.

THE FAULT IT ANSWERS, measured rather than inferred. `darkpool_backfill.py` carried

    ALLOWANCE_THROUGH = date(2026, 10, 23)

and at 00:00 UTC on 2026-10-24 its nightly loop hit `today > ALLOWANCE_THROUGH` and RETURNED --
the loop ended, it did not sleep. Run 19 became the last run there would ever be, so
`latest_ended_run_id` froze at 19; `scripts/f_export_gate.py` keys the F: archive export on
that id, so the export reports ALREADY_DONE on every tick forever, and `export_bars1m()` runs
inside that gate. One date literal stopped the dark-pool pages AND the yfinance bars.

What the tests here pin:

  1. the forward walk CANNOT SPEND before the funding ruling, checked on calls not on a flag;
  2. it CREATES AND ENDS A RUN, because an un-ended run is read by the gate as "in progress"
     and it waits -- a silence that looks like patience;
  3. it does not disturb the census instrument: the caller tag stays separable and the
     walker's defaults are unchanged.
"""
from __future__ import annotations

import ast
import os
from datetime import date, datetime, timezone

import pytest

from jobs import darkpool_backfill as census
from jobs import darkpool_forward as fwd
from tests._srcscan import code_of_file, function_code, read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FWD_FILE = os.path.join(BACKEND, "jobs", "darkpool_forward.py")
CENSUS_FILE = os.path.join(BACKEND, "jobs", "darkpool_backfill.py")

ET = census._ET_ZONE()
UTC = timezone.utc


@pytest.fixture(autouse=True)
def _clean():
    fwd.reset_for_tests()
    yield
    fwd.reset_for_tests()


# ── 1. it cannot spend before the ruling ────────────────────────────────────

@pytest.mark.asyncio
async def test_it_MAKES_NO_VENDOR_CALL_while_its_tag_is_unregistered():
    """An unregistered tag is not inert -- `quota_for` falls back to DEFAULT_QUOTA 500 and the
    walk would spend them on a path nobody approved. So the assertion is on `collect_one`
    never being reached, not on a boolean."""
    # FUNDED by R-IV.1408(b)1 at 250/night from the reserve. Same flip as the grid's, for
    # the same reason, and the property is proved the stronger way: remove the registration
    # and the refusal must return.
    from integrations import uw_governor as _gov
    assert fwd.tag_is_registered(), "R-IV.1408(b)1 registered this tag; it is missing"
    saved = _gov.FOREIGN_RESERVE_QUOTAS.pop(fwd.CALLER_TAG)
    calls = {"n": 0}

    async def _never(*a, **k):
        calls["n"] += 1
        return {}

    real = census.collect_one
    census.collect_one = _never
    try:
        out = await fwd.walk_night(now=datetime(2026, 10, 26, 21, 0, tzinfo=ET))
    finally:
        ceiling_unfunded = fwd.night_ceiling()
        census.collect_one = real
        _gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] = saved

    assert calls["n"] == 0, "the forward walk spent %d calls while unfunded" % calls["n"]
    assert out["blocked"] is True
    assert ceiling_unfunded == 0
    assert fwd.night_ceiling() == int(250 * fwd.NIGHT_CEILING_FRACTION) == 240


def test_the_two_gates_are_reported_SEPARATELY():
    from integrations import uw_governor as gov

    saved = gov.FOREIGN_RESERVE_QUOTAS.pop(fwd.CALLER_TAG)
    try:
        assert "quota table" in (fwd.preflight() or ""), fwd.preflight()
    finally:
        gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] = saved
    try:
        reason = fwd.preflight()
        assert reason is not None and fwd.ENV_FLAG in reason, reason
        assert fwd.night_ceiling() == int(250 * fwd.NIGHT_CEILING_FRACTION) == 240
        os.environ[fwd.ENV_FLAG] = "true"
        try:
            assert fwd.preflight() is None
        finally:
            del os.environ[fwd.ENV_FLAG]
    finally:
        # Restored to the RULED figure (R-IV.1408(b)1), never popped.
        gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] = (250, gov.TIER_STANDARD)


def test_an_empty_env_value_is_OFF():
    os.environ[fwd.ENV_FLAG] = ""
    try:
        assert fwd.enabled() is False
    finally:
        del os.environ[fwd.ENV_FLAG]


def test_an_unreadable_quota_table_is_not_a_licence_to_spend():
    import sys
    real = sys.modules.get("integrations.uw_governor")
    sys.modules["integrations.uw_governor"] = None
    try:
        assert fwd.tag_is_registered() is False
        assert fwd.night_ceiling() == 0, (
            "an unreadable quota table must not yield a spendable ceiling, funded or not")
    finally:
        if real is not None:
            sys.modules["integrations.uw_governor"] = real
        else:
            sys.modules.pop("integrations.uw_governor", None)


# ── 2. it must create AND end a run ─────────────────────────────────────────

def test_it_ENDS_the_run_because_the_F_EXPORT_GATE_READS_THAT():
    """The gate's identity is (latest_ended_run_id, eligible_count). A run created and never
    ended is RUN_IN_PROGRESS to the gate, which then waits indefinitely -- and that is how
    the census job's run 7 held the export shut until it was reconciled."""
    code = function_code(FWD_FILE, "walk_night")
    assert "darkpool_backfill_runs" in code, "the walk does not create a run at all"
    assert "_end_run" in code
    ender = function_code(FWD_FILE, "_end_run")
    assert "ended_at = NOW()" in ender
    assert "calls_spent" in ender and "stop_reason" in ender


def test_a_cancelled_walk_still_ends_its_run():
    """A deploy cancels the task mid-walk. CancelledError derives from BaseException, so an
    `except Exception` is blind to it -- which is exactly how run 7 was left in progress."""
    code = function_code(FWD_FILE, "walk_night")
    assert "CancelledError" in code, (
        "a deploy mid-walk would leave a run with a null ended_at, and the gate reads that "
        "as a run still going")
    tree = ast.parse(read_source(FWD_FILE))
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "walk_night"):
            handlers = [h for n in ast.walk(node) if isinstance(n, ast.Try)
                        for h in n.handlers]
            names = [getattr(h.type, "attr", getattr(h.type, "id", None))
                     for h in handlers if h.type is not None]
            assert "CancelledError" in names, names
            body = [ast.unparse(st) for h in handlers for st in h.body
                    if "CancelledError" in (getattr(h.type, "attr", "") or "")]
            assert any("_end_run" in b for b in body), body
            assert any("raise" == b.strip() for b in body), (
                "CancelledError must be re-raised: swallowing a cancellation makes a killed "
                "task look like a completed one")
            return
    raise AssertionError("walk_night not found")


def test_completeness_is_refreshed_so_the_ELIGIBLE_COUNT_moves_too():
    """The gate's identity has TWO parts. A run that ended while `reached_floor` stayed NULL
    would move the id and not the eligible count -- and R-IV.1005(d) already records the
    mirror of that: 40 ticker-sessions became exportable with no new run at all."""
    code = function_code(FWD_FILE, "walk_night")
    assert "refresh_completeness" in code


# ── 3. it does not disturb the census instrument ────────────────────────────

def test_the_two_tags_are_DIFFERENT_so_the_spends_stay_separable():
    assert fwd.CALLER_TAG == "darkpool_forward"
    assert fwd.CALLER_TAG != census.CALLER
    code = function_code(FWD_FILE, "walk_night")
    assert "CALLER_TAG" in code, "the walk does not pass its own tag to collect_one"


def test_the_walkers_DEFAULTS_are_unchanged_so_the_census_path_is_untouched():
    """The caller was threaded through `fetch_page` and `collect_one` additively. A default
    that drifted would charge the forward walk to the census tag and the two spends would be
    unseparable -- the `flow_per_expiry` / `hermes_session_poll` fault, twice recorded."""
    import inspect
    assert inspect.signature(census.fetch_page).parameters["caller"].default == census.CALLER
    assert inspect.signature(census.collect_one).parameters["caller"].default == census.CALLER
    assert census.CALLER == "darkpool_backfill_triton"


def test_it_does_not_touch_SM7s_collector():
    """R-IV.912(c)2, verbatim: do not change darkpool_collector, its tables or its caller tag.
    Scanned on PARSED code -- this module's docstring names it to say it is untouched, and a
    raw-text scan would fail on that sentence."""
    code = code_of_file(FWD_FILE)
    assert "darkpool_collector" not in code
    assert "darkpool_pages" not in code, (
        "darkpool_pages is SM7's table; this job writes darkpool_backfill_pages")


def test_it_carries_NO_EXPIRY_DATE():
    """The whole reason it is a separate instrument. A forward collection has no end date to
    write, and the census's date literal is what stopped the pages and the bars together."""
    code = code_of_file(FWD_FILE)
    assert "ALLOWANCE_THROUGH" not in code, (
        "the forward walk imported the census's expiry, which reintroduces the exact fault")
    for year in ("2026", "2027"):
        assert "date(%s," % year not in code, "a date literal that can lapse"


def test_the_census_expiry_is_LEFT_ALONE():
    """Its census is finished -- 312 of 312 ticker-sessions, outstanding 0 -- so the lapse is
    correct behaviour for that job and extending its date is not this build's business."""
    assert census.ALLOWANCE_THROUGH == date(2026, 10, 23)


# ── 4. which session, and the retry window ──────────────────────────────────

@pytest.mark.parametrize("y,m,d,expect", [
    (2026, 10, 23, "2026-10-23"),   # Friday, the session that just closed
    (2026, 10, 26, "2026-10-26"),   # Monday
    (2026, 10, 24, None),           # Saturday
    (2026, 10, 25, None),           # Sunday
])
def test_the_target_is_the_session_that_JUST_CLOSED_not_yesterday(y, m, d, expect):
    """The window opens at 20:30 ET, after the close, so the session that just ended is the ET
    date of the instant. The census used `today - 1` because it walked BACKWARDS through
    history from a UTC date; reusing that here would walk yesterday every night and never
    collect the session that had just finished."""
    got = fwd.target_session(datetime(y, m, d, 20, 30, tzinfo=ET))
    assert (got.isoformat() if got else None) == expect


def test_the_universe_is_the_CENSUS_EIGHT_and_is_not_called_tier_1():
    """R-IV.1408(b)3 settled the set: the census's eight names, the ones TRITON-R and R2 read,
    explicitly NOT Tier-1's sixteen.

    The eight were always right -- 158.6 calls a night is measured on exactly this set, so a
    divergent list would make the funded figure describe a different job. What was wrong was
    the NAME, which came from R-IV.1398(b)3's "floored Tier-1 job" wording and was published
    on /health, telling every reader of that surface the opposite of the scope.
    """
    assert fwd.census_names() == census.CORE_NAMES
    assert len(fwd.census_names()) == 8
    assert not hasattr(fwd, "tier_1_names"), (
        "the misnamed accessor is still present: a caller reaching for it gets the census set "
        "under a label the ruling rejected")


def test_a_blocked_or_holiday_tick_does_NOT_consume_the_night():
    """The retry window runs to 23:00 ET so a transient failure gets another attempt. Marking
    the vendor day fired on a blocked tick would mean a gate opened at 21:00 could never
    collect at 21:30."""
    code = function_code(FWD_FILE, "run_forever")
    i = code.index("_fired.add")
    guard = code[max(0, i - 220):i]
    assert "blocked" in guard and "session" in guard, guard


# ── 5. the surface ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_health_surface_NAMES_the_block():
    st = await fwd.status()
    assert st["job"] == "darkpool_forward"
    assert st["caller_tag"] == fwd.CALLER_TAG
    assert st["tag_registered"] is True, "R-IV.1408(b)1 registered this tag"
    assert st["env_enabled"] is False
    assert st["blocked"] and fwd.ENV_FLAG in st["blocked"], st["blocked"]
    assert "quota table" not in st["blocked"], (
        "the surface still blames the funding gate after the ruling funded it")
    assert st["ceiling"] == int(250 * fwd.NIGHT_CEILING_FRACTION) == 240
    assert len(st["census_names"]) == 8
    assert "tier_1" not in st, "the surface still publishes the rejected label"
    assert st["nights_fired_this_process"] == []
