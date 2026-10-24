"""R-IV.1412(b) the catch-up, and (d) the missing-header probe.

THE GAP (b) CLOSES. `target_session()` returns only the session of the instant it is called
at, so the first version of this walk could never have collected 2026-10-23: its first fire is
Monday 20:30 ET for 10-26, and 10-23 was in no future target. The census walk that would once
have swept it up lapsed on 2026-10-24. One session, permanently missing, with no error anywhere.

THE ORDER IS THE WHOLE RULING. The session that just closed is walked FIRST and
unconditionally, because nothing will ever target it again; the backlog gets only the
REMAINDER, so however long a backlog grows it can never starve the live collection. Within the
catch-up, oldest first, because the vendor drops its oldest dark-pool session every trading day.
"""
from __future__ import annotations

import ast
import asyncio
import os
from datetime import date, datetime, timedelta

import pytest

from jobs import darkpool_backfill as census
from jobs import darkpool_forward as fwd

ET = census._ET_ZONE()
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FWD_FILE = os.path.join(BACKEND, "jobs", "darkpool_forward.py")

MON = date(2026, 10, 26)
NAMES = fwd.census_names()


@pytest.fixture(autouse=True)
def _clean():
    fwd.reset_for_tests()
    yield
    fwd.reset_for_tests()


# ── 1. which sessions the catch-up picks ────────────────────────────────────

def test_the_session_that_prompted_this_is_found():
    """2026-10-23, with every other session in the lookback already written. The one case the
    ruling exists for."""
    span = fwd.catchup_sessions(MON, set(), NAMES)
    done = {(t, d) for t in NAMES for d in span if d != date(2026, 10, 23)}
    assert fwd.catchup_sessions(MON, done, NAMES) == [date(2026, 10, 23)]


def test_the_CURRENT_session_is_never_its_own_catch_up_candidate():
    """It is walked first and unconditionally by the caller. Including it here would let the
    remainder be spent on it a second time."""
    assert MON not in fwd.catchup_sessions(MON, set(), NAMES)


def test_candidates_are_OLDEST_FIRST():
    """The vendor drops its OLDEST dark-pool session every trading day, so of two unwritten
    sessions the older one has less time left."""
    got = fwd.catchup_sessions(MON, set(), NAMES)
    assert got == sorted(got)
    assert got[0] < got[-1] < MON


def test_the_lookback_is_BOUNDED():
    """"Oldest unwritten" over an unbounded history walks toward the census's 2026-08-28
    origin -- far outside the vendor's retention -- and would spend every night's remainder on
    sessions that cannot be fetched at all."""
    got = fwd.catchup_sessions(MON, set(), NAMES)
    assert len(got) <= fwd.CATCHUP_LOOKBACK_SESSIONS == 10
    assert all(d.weekday() < 5 for d in got), "a weekend was offered as a session"


def test_a_PARTIALLY_walked_session_still_counts_as_unwritten():
    """`done` is DONE_SQL's set -- exhausted AND reached_floor AND prints > 0 -- so a
    ticker-session walked but not floored is still a candidate tomorrow, and `collect_one`
    resumes it from its stored page rather than re-walking from page 1. That is what makes the
    catch-up CONVERGE rather than declare victory on a partial walk."""
    target = date(2026, 10, 23)
    span = fwd.catchup_sessions(MON, set(), NAMES)
    # Seven of eight names finished; one still outstanding.
    done = {(t, d) for t in NAMES for d in span if d != target}
    done |= {(t, target) for t in NAMES[:-1]}
    assert fwd.catchup_sessions(MON, done, NAMES) == [target]


def test_nothing_outstanding_means_no_catch_up():
    span = fwd.catchup_sessions(MON, set(), NAMES)
    done = {(t, d) for t in NAMES for d in span}
    assert fwd.catchup_sessions(MON, done, NAMES) == []


# ── 2. the order, which is the ruling ───────────────────────────────────────

def test_the_current_session_is_walked_BEFORE_any_catch_up_in_the_source():
    """Structural, because the order is the whole point and a reordering would not fail any
    behavioural test that only counted calls."""
    code = _fn_src("walk_night")
    i = code.index("for ticker in names:")
    j = code.index("catchup_sessions(")
    assert i < j, "the catch-up is planned before the current session is walked"


def _fn_src(name):
    with open(FWD_FILE, encoding="utf-8-sig") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name):
            return ast.unparse(node)
    raise AssertionError("%s not found" % name)


class _Conn:
    async def execute(self, *a, **k):
        return None

    async def fetch(self, *a, **k):
        return []

    async def fetchval(self, *a, **k):
        return 20


class _Acq:
    async def __aenter__(self):
        return _Conn()

    async def __aexit__(self, *a):
        return False


class _Pool:
    def acquire(self):
        return _Acq()


@pytest.mark.asyncio
async def test_END_TO_END_the_current_session_is_FULLY_walked_first():
    """Eight calls for the current session before a single catch-up call, then the remainder on
    the oldest unwritten. Checked on the ORDER of the calls, not merely on their count."""
    import database.postgres_client as pg
    from integrations import uw_governor as gov

    seen = []

    async def _collect(pool, ticker, session, budget, caller=None):
        seen.append((session.isoformat(), ticker))
        budget.spend()
        return {"ticker": ticker, "session": session.isoformat(), "pages": 1, "prints": 10,
                "exhausted": True, "reached_floor": True}

    async def _pool():
        return _Pool()

    async def _noop(*a, **k):
        return {}

    gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] = (250, gov.TIER_STANDARD)
    os.environ[fwd.ENV_FLAG] = "true"
    real = (census.collect_one, pg.get_postgres_client, census.refresh_completeness)
    census.collect_one, pg.get_postgres_client = _collect, _pool
    census.refresh_completeness = _noop
    try:
        out = await fwd.walk_night(now=datetime(2026, 10, 26, 21, 0, tzinfo=ET))
    finally:
        census.collect_one, pg.get_postgres_client, census.refresh_completeness = real
        del os.environ[fwd.ENV_FLAG]
        gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] = (250, gov.TIER_STANDARD)

    assert out.get("blocked") is not True, out
    assert out["session"] == "2026-10-26"
    first8 = seen[:len(NAMES)]
    assert {s for s, _t in first8} == {"2026-10-26"}, (
        "a catch-up call was made before the current session was finished: %r" % (seen[:12],))
    assert {t for _s, t in first8} == set(NAMES)
    assert out["collected"] == len(NAMES)
    # And then the remainder went to the OLDEST unwritten session, not the newest.
    later = [s for s, _t in seen[len(NAMES):]]
    assert later, "no catch-up happened at all"
    assert later[0] < "2026-10-26"
    assert out["catchup_collected"] > 0
    assert out["catchup_sessions"], out


@pytest.mark.asyncio
async def test_the_catch_up_STOPS_at_the_ceiling():
    """The remainder is a remainder. A backlog cannot spend past the ruled 250 a night."""
    import database.postgres_client as pg
    from integrations import uw_governor as gov

    calls = {"n": 0}

    async def _collect(pool, ticker, session, budget, caller=None):
        calls["n"] += 1
        # Each ticker-session costs 30 calls, so the 240 ceiling binds after 8.
        for _ in range(30):
            budget.spend()
        return {"ticker": ticker, "session": session.isoformat(), "pages": 1, "prints": 1,
                "exhausted": True, "reached_floor": True}

    async def _pool():
        return _Pool()

    async def _noop(*a, **k):
        return {}

    gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] = (250, gov.TIER_STANDARD)
    os.environ[fwd.ENV_FLAG] = "true"
    real = (census.collect_one, pg.get_postgres_client, census.refresh_completeness)
    census.collect_one, pg.get_postgres_client = _collect, _pool
    census.refresh_completeness = _noop
    try:
        out = await fwd.walk_night(now=datetime(2026, 10, 26, 21, 0, tzinfo=ET))
    finally:
        census.collect_one, pg.get_postgres_client, census.refresh_completeness = real
        del os.environ[fwd.ENV_FLAG]
        gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] = (250, gov.TIER_STANDARD)

    assert out["calls_spent"] <= fwd.night_ceiling() + 30, out["calls_spent"]
    assert calls["n"] == len(NAMES), (
        "the ceiling did not bind: %d ticker-sessions walked" % calls["n"])
    assert out["catchup_collected"] == 0, "the current session should have used the budget"


@pytest.mark.asyncio
async def test_the_catch_up_is_REPORTED_SEPARATELY():
    """"the live session was collected" and "the backlog moved" must never be one number: a
    night that collected only backlog would otherwise look like a night that worked."""
    from integrations import uw_governor as gov

    gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] = (250, gov.TIER_STANDARD)
    os.environ[fwd.ENV_FLAG] = "true"
    try:
        out = await fwd.walk_night(now=datetime(2026, 10, 24, 21, 0, tzinfo=ET))  # Saturday
    finally:
        del os.environ[fwd.ENV_FLAG]
    # A non-trading day is a STATED absence, not a run that collected nothing -- and it is
    # reached only with both gates open, which is why they are opened here.
    assert out.get("session") is None and out["reason"] == "not a trading session", out
    st = await fwd.status()
    code = _fn_src("walk_night")
    for key in ("catchup_sessions", "catchup_collected", "catchup_pending"):
        assert key in code, key
    assert "collected" in code and "already_done" in code
    assert st["job"] == "darkpool_forward"


# ── 3. (d) the missing-header probe ─────────────────────────────────────────

class _Resp:
    def __init__(self, names, status=200):
        self.status_code = status
        self._names = names

    class _H:
        def __init__(self, names):
            self._names = names

        def get(self, k, d=None):
            return None

        def keys(self):
            return self._names

    @property
    def headers(self):
        return self._H(self._names)


def test_the_probe_logs_header_NAMES_and_never_VALUES():
    """A response's headers can carry things with no business in a log. The names alone answer
    the only open question -- whether UW renamed the counter or stopped sending it."""
    from integrations import uw_api as u

    src = _uw_capture_src()
    assert "resp.headers.keys()" in src, "the probe must read names, not items"
    for leak in ("resp.headers.values()", "resp.headers.items()", "dict(resp.headers)"):
        assert leak not in src, leak


def _uw_capture_src():
    path = os.path.join(BACKEND, "integrations", "uw_api.py")
    with open(path, encoding="utf-8-sig") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_capture_quota_headers"):
            return ast.unparse(node)
    raise AssertionError("_capture_quota_headers not found")


def test_the_probe_fires_ONCE_per_process(caplog):
    """At ~14,000 calls a day a per-call line would bury the log it exists to inform."""
    import logging

    from integrations import uw_api as u

    u._QUOTA_HEADER_NAMES_LOGGED = False
    try:
        with caplog.at_level(logging.WARNING):
            asyncio.run(u._capture_quota_headers(_Resp(["content-type", "x-request-id"])))
            asyncio.run(u._capture_quota_headers(_Resp(["content-type", "x-request-id"])))
        hits = [r for r in caplog.records if "NEITHER x-uw-daily-req-count" in r.message]
        assert len(hits) == 1, [r.message for r in caplog.records]
        assert "x-request-id" in hits[0].getMessage()
    finally:
        u._QUOTA_HEADER_NAMES_LOGGED = False


def test_the_probe_does_NOT_change_the_gates_behaviour():
    """An unmeasured account must still fail OPEN -- that is the whole posture of
    `account_shed`, and a probe that armed the gate on an absent reading would turn the
    instrument into an outage of its own."""
    src = _uw_capture_src()
    i = src.index("_QUOTA_HEADER_NAMES_LOGGED = True")
    j = src.index("return", i)
    branch = src[i:j]
    assert "REDIS_KEY_UW_QUOTA" not in branch, (
        "the probe writes a QUOTA READING it does not have: %s" % branch[-200:])
    # Its own key is fine and is the point: that one carries header NAMES, not a figure.
    assert "REDIS_KEY_UW_HEADER_PROBE" in branch
    # And the branch still ENDS in a return, so an absent reading never falls through into the
    # write path below it.
    assert src[j:j + 6] == "return"


def test_a_429_still_records_itself_even_with_no_headers():
    """A 429 carries no counter, but it is still a measurement: UW turned a request away at a
    known instant. The probe must not displace that."""
    src = _uw_capture_src()
    i = src.index("if used is None and limit is None")
    # The ASSIGNMENT, not the bare name: `ast.unparse` hoists the `global` declaration to the
    # top of the function, so the name itself appears before `_record_429()` and a slice bounded
    # by it is empty -- which would have passed for the wrong reason.
    j = src.index("_QUOTA_HEADER_NAMES_LOGGED = True")
    assert i < j, "the probe now precedes the no-headers check"
    assert "_record_429()" in src[i:j], (
        "the 429 record now sits after the probe, or has been lost")


# ── 4. (d) the probe has to be READABLE, not merely logged ──────────────────
#
# MY OWN DESIGN ERROR, measured. The probe logs ONCE per process, so its line is among the
# first that process emits -- and `railway logs` serves a TAIL. Checked 397 seconds after the
# deploy, with ours_attributed risen 464 -> 468 so calls had certainly happened: 500 log lines
# captured, ZERO probe matches. The line had already scrolled out.
#
# A diagnostic nobody can page back to is the same fault as `open:no_header` itself: a state
# technically recorded and practically unreadable.

def test_the_probe_writes_its_finding_where_the_QUESTION_is_asked():
    """`/health.uw_quota` is where "can we see the account" is asked, so it is where "and here
    is what UW sent instead" belongs."""
    from integrations import uw_api as u
    src = _uw_capture_src()
    assert "REDIS_KEY_UW_HEADER_PROBE" in src
    assert u.REDIS_KEY_UW_HEADER_PROBE == "uw:quota_header_probe"
    assert u.REDIS_KEY_UW_HEADER_PROBE != u.REDIS_KEY_UW_QUOTA, (
        "the probe must not overwrite the quota reading it is reporting the absence of")


def test_the_probe_surface_carries_NAMES_ONLY():
    src = _uw_capture_src()
    i = src.index("REDIS_KEY_UW_HEADER_PROBE")
    block = src[i:i + 700]
    assert "header_names" in block
    for leak in (".values()", ".items()", "dict(resp.headers)"):
        assert leak not in block, leak


def test_the_probe_write_cannot_fail_the_call_or_delay_the_early_return():
    """Telemetry must never fail the call it observes, and must never postpone the return that
    keeps an unmeasured account failing OPEN."""
    src = _uw_capture_src()
    i = src.index("REDIS_KEY_UW_HEADER_PROBE")
    j = src.index("return", i)
    block = src[i:j]
    assert "except Exception" in block, "the probe write is not guarded"
    # The write sits BEFORE the return, and the return is still there.
    assert src[j:j + 6] == "return"


def test_the_probe_reading_survives_a_deploy():
    """36 hours, matching the quota key. A probe that died with the process would be erased by
    exactly the deploy whose logs someone was about to read."""
    src = _uw_capture_src()
    i = src.index("REDIS_KEY_UW_HEADER_PROBE")
    assert "36 * 3600" in src[i:i + 400]


def test_the_surface_reads_the_probe_back_only_when_there_is_NO_reading():
    """It explains an ABSENCE. Attaching it beside a real reading would be noise, and worse,
    would suggest the account is unmeasured when it is not."""
    path = os.path.join(BACKEND, "integrations", "uw_api.py")
    with open(path, encoding="utf-8-sig") as fh:
        tree = ast.parse(fh.read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "account_quota")
    src = ast.unparse(fn)
    i = src.index("account_shed")
    j = src.index("REDIS_KEY_UW_HEADER_PROBE")
    assert i < j, "the probe is read before the no-reading branch is established"
    # And it is inside that branch, not after it: the gate_state read follows both.
    k = src.index("gate_state")
    assert j < k, "the probe read escaped the no-reading branch"
    # The branch it sits in is the SETTLED one, not a pending one (R-IV.1417(a)1).
    assert "INACTIVE" in src[i:j]
