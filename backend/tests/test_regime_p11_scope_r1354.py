"""The report card scores only sessions that closed after the cutover. P11, R-IV.1354(b).

THE BREACH THIS CLOSES, measured on the live payload. Friday's fallback labelled session
2026-10-20 as v2.1 (row 930). **The row is not wrong** -- it reproduces v2's own 10-20 reading
exactly, which is what the cutover verifier predicted. But 10-20 CLOSED at
2026-10-20T16:00-04:00, which is before the cutover instant of 2026-10-22T19:03:00.396505Z, and
the card served `first_session: 2026-10-20` with `backfilled: false`. It had become a scoring
card with a BACKDATED START: claiming to measure the new rules against a session that predates
them, and asserting it had not backfilled while nothing had checked. The scope was wrong, not
the classifier.

THE INSTANT IS A RECORDED FACT, and that is not a detail. It cannot be re-derived: v2.1 went
live with the deploy whose process started at 19:03:00.396505Z on 2026-10-22, and the hub has
restarted since -- so `/health`'s `process_started_at` now reports the CURRENT process (05:29:43Z
on 10-23). Reading the boundary from /health would walk it forward on every deploy and quietly
pull already-scored sessions back OUT of scope, which is the same class of error as the
backdated start, pointed the other way. So the instant is written once into `regime_audit` as a
`version_live` marker, from the value R-IV.1354(b)1 states, and every reader reads the marker.

WHY THE CLOSE IS COMPUTED AND NOT ASSUMED. The exchange closes at 16:00 LOCAL: 20:00Z under EDT,
21:00Z under EST, and the changeover falls in the first week of November -- inside the span this
card will be scoring within two weeks. A fixed `date + "T20:00:00Z"` would put every November
session an hour early, and for any session closing within an hour of a cutover it would decide
the wrong side of the boundary.

QUERY's checker (sha256 989f19f4...) was run on the payloads this code produces, over both of
its scope controls, BEFORE any of it deployed: OK-1 (row 930 only) and OK-2 (a post-cutover
session) both returned `CONFORMANT: no findings`.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models import regime_report_scoring as rs                       # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

INSTANT = dt.datetime.fromisoformat("2026-10-22T19:03:00.396505+00:00")


# ── the close, and why it is computed ───────────────────────────────────────

def test_a_session_closes_at_1600_NEW_YORK():
    c = rs.session_close("2026-10-22")
    assert (c.hour, c.minute) == (16, 0)
    assert c.date() == dt.date(2026, 10, 22)


def test_the_close_is_DST_CORRECT_across_the_November_changeover():
    """October is EDT (-04:00) and late November is EST (-05:00). A fixed UTC offset would be
    wrong for every session after the first week of November -- which this card reaches in two
    weeks."""
    oct_close = rs.session_close("2026-10-22")
    nov_close = rs.session_close("2026-11-20")
    assert oct_close.utcoffset() == dt.timedelta(hours=-4), oct_close
    assert nov_close.utcoffset() == dt.timedelta(hours=-5), nov_close
    assert oct_close.astimezone(dt.timezone.utc).hour == 20
    assert nov_close.astimezone(dt.timezone.utc).hour == 21


def test_the_close_accepts_a_date_or_a_string():
    assert rs.session_close(dt.date(2026, 10, 22)) == rs.session_close("2026-10-22")


# ── the scope predicate ─────────────────────────────────────────────────────

def test_ROW_930s_SESSION_IS_OUT_OF_SCOPE():
    """The measured case. 2026-10-20 closed at 16:00-04:00 = 20:00Z on 10-20, before the
    19:03Z instant on 10-22."""
    assert rs.in_scope("2026-10-20", INSTANT) is False


@pytest.mark.parametrize("d", ["2026-10-19", "2026-10-20", "2026-10-21"])
def test_every_PRE_CUTOVER_session_is_out_of_scope(d):
    assert rs.in_scope(d, INSTANT) is False


def test_the_CUTOVER_DAYS_OWN_SESSION_IS_IN_SCOPE():
    """10-22 closed at 20:00Z, and the cutover was 19:03Z -- 57 minutes EARLIER. So the session
    of the cutover day itself qualifies, and that is not an accident of rounding: its close
    genuinely came after the new rules went live."""
    assert rs.in_scope("2026-10-22", INSTANT) is True


@pytest.mark.parametrize("d", ["2026-10-23", "2026-10-26", "2026-11-20"])
def test_every_POST_CUTOVER_session_is_in_scope(d):
    assert rs.in_scope(d, INSTANT) is True


def test_the_comparison_is_STRICTLY_AFTER():
    """A session whose close EQUALS the instant did not close after it."""
    exact = rs.session_close("2026-10-22")
    assert rs.in_scope("2026-10-22", exact) is False
    assert rs.in_scope("2026-10-22", exact - dt.timedelta(seconds=1)) is True


def test_an_UNKNOWN_instant_scores_NOTHING_not_everything():
    """The failure direction matters. Treating an unknown boundary as "no boundary" is exactly
    the backdated card again."""
    assert rs.in_scope("2026-10-23", None) is False
    assert rs.in_scope("1999-01-04", None) is False


def test_there_is_ONE_scope_predicate_and_the_card_uses_it():
    """A second copy of the rule is a second place for the boundary to be wrong."""
    src = read_source(str(_BACKEND / "services" / "read_only" / "regime_strategy.py"))
    assert "rs.in_scope(" in src
    assert "def in_scope" not in src, "the card must not define its own"


# ── the marker ──────────────────────────────────────────────────────────────

def test_the_STATED_instant_is_the_one_the_ruling_gave():
    from jobs.regime_job import STATED_VERSION_LIVE

    assert STATED_VERSION_LIVE["v2.1"] == "2026-10-22T19:03:00.396505+00:00"


def test_the_marker_is_NEVER_re_derived_from_health():
    """R-IV.1354(b)1, and the reason it is a stated fact: the process has restarted since, so
    /health cannot produce this value any more."""
    src = read_source(str(_BACKEND / "jobs" / "regime_job.py"))
    i = src.index("async def ensure_version_live(")
    block = src[i:src.index("async def version_live_instant", i)]
    assert "/health" not in block
    assert "urlopen" not in block and "requests" not in block


@pytest.mark.asyncio
async def test_the_marker_is_written_ONCE_and_a_restart_writes_NOTHING():
    from jobs import regime_job

    calls = []

    class _Conn:
        def __init__(self, present):
            self.present = present

        async def fetchrow(self, sql, *a):
            calls.append((sql, a))
            # the guarded INSERT returns no row when the marker already exists
            return None if self.present else {"id": 1}

    first = await regime_job.ensure_version_live(_Conn(False), "v2.1", "2026-10-23T05:00:00Z")
    assert first["written"] is True
    assert first["instant"] == "2026-10-22T19:03:00.396505+00:00", (
        "the STATED instant must win over this process's start time")

    again = await regime_job.ensure_version_live(_Conn(True), "v2.1", "2026-10-23T05:00:00Z")
    assert again["written"] is False
    assert again.get("already_present") is True


@pytest.mark.asyncio
async def test_the_idempotence_is_IN_THE_STATEMENT_not_a_read_then_write():
    """Two processes booting together would both pass a SELECT-then-INSERT and write two
    markers with different instants -- and the scope rule would then depend on which one a
    later reader picked. `regime_audit` has no unique index to lean on (it is an append-only
    log where repeated actions are normal), so the guard has to be in the statement."""
    src = read_source(str(_BACKEND / "jobs" / "regime_job.py"))
    i = src.index("async def ensure_version_live(")
    block = src[i:src.index("async def version_live_instant", i)]
    assert "WHERE NOT EXISTS" in block
    assert "INSERT INTO regime_audit" in block


@pytest.mark.asyncio
async def test_a_FUTURE_version_records_ITS_OWN_first_boot():
    """Only v2.1 needs a stated value, because its moment has passed. A new version's first
    boot IS the moment it went live."""
    from jobs import regime_job

    class _Conn:
        async def fetchrow(self, sql, *a):
            _Conn.detail = a[2]
            return {"id": 1}

    out = await regime_job.ensure_version_live(_Conn(), "v3", "2026-12-01T14:00:00+00:00")
    assert out["written"] is True
    assert out["source"] == "process"
    assert "2026-12-01T14:00:00+00:00" in _Conn.detail


@pytest.mark.asyncio
async def test_with_NO_instant_at_all_nothing_is_written():
    """A marker holding "now" would be a fabricated boundary."""
    from jobs import regime_job

    class _Conn:
        async def fetchrow(self, sql, *a):
            raise AssertionError("must not write")

    out = await regime_job.ensure_version_live(_Conn(), "v3", None)
    assert out["written"] is False and "skipped" in out


@pytest.mark.asyncio
async def test_the_instant_is_READ_BACK_from_the_marker():
    from jobs import regime_job

    class _Conn:
        async def fetchrow(self, sql, *a):
            return {"detail": "process_started_at = 2026-10-22T19:03:00.396505+00:00",
                    "created_at": dt.datetime.now(dt.timezone.utc)}

    inst, src = await regime_job.version_live_instant(_Conn(), "v2.1")
    assert inst == INSTANT
    assert "version_live" in src and "v2.1" in src


@pytest.mark.asyncio
async def test_the_OLDEST_marker_wins_if_two_ever_exist():
    """A second marker -- a bug, a manual insert -- must not move the boundary. The FIRST one
    is the one the already-scored sessions were scored under."""
    src = read_source(str(_BACKEND / "jobs" / "regime_job.py"))
    i = src.index("async def version_live_instant(")
    block = src[i:i + 2500]
    assert "ORDER BY created_at ASC" in block
    assert "ORDER BY created_at DESC" not in block


@pytest.mark.asyncio
async def test_a_MISSING_marker_is_reported_and_not_guessed():
    from jobs import regime_job

    class _Conn:
        async def fetchrow(self, sql, *a):
            return None

    inst, why = await regime_job.version_live_instant(_Conn(), "v2.1")
    assert inst is None
    assert "no version_live marker" in why


@pytest.mark.asyncio
async def test_an_UNREADABLE_marker_detail_is_reported_and_not_guessed():
    from jobs import regime_job

    class _Conn:
        async def fetchrow(self, sql, *a):
            return {"detail": "someone wrote prose here",
                    "created_at": dt.datetime.now(dt.timezone.utc)}

    inst, why = await regime_job.version_live_instant(_Conn(), "v2.1")
    assert inst is None
    assert "readable instant" in why


# ── the card, over QUERY's two scope controls ───────────────────────────────

class _CardConn:
    def __init__(self, sessions, marker="process_started_at = 2026-10-22T19:03:00.396505+00:00"):
        self.sessions = sessions
        self.marker = marker

    async def fetch(self, sql, *a):
        if "FROM regime_snapshots" in sql and "shown_regime" in sql:
            return [{"as_of": dt.date.fromisoformat(d), "shown_regime": g}
                    for d, g in self.sessions]
        return []

    async def fetchrow(self, sql, *a):
        if "regime_audit" in sql:
            return (None if self.marker is None
                    else {"detail": self.marker,
                          "created_at": dt.datetime.now(dt.timezone.utc)})
        return None

    async def fetchval(self, sql, *a):
        return None


@pytest.mark.asyncio
async def test_OK1_row_930_ALONE_gives_E1_and_NAMES_the_excluded_row(monkeypatch):
    """R-IV.1354(b)3: row 930 STAYS, leaves scope, and appears under excluded_pre_cutover. A
    card that dropped it silently would leave a reader unable to tell "nothing scored yet" from
    "nothing exists"."""
    from services.read_only import regime_strategy as svc

    card = await svc._report_card(_CardConn([("2026-10-20", "range_chop")]))
    sc = card["scope"]
    assert card["available"] is False, "a pre-cutover-only card must be E1, not a scoring card"
    assert sc["first_session"] is None
    assert sc["sessions"] == 0
    assert sc["excluded_pre_cutover"] == ["2026-10-20"]
    assert sc["cutover_instant"] == "2026-10-22T19:03:00.396505+00:00"
    assert sc["cutover_source"]


@pytest.mark.asyncio
async def test_OK2_a_POST_cutover_session_gives_a_scoring_card(monkeypatch):
    from services.read_only import regime_strategy as svc

    card = await svc._report_card(_CardConn([("2026-10-20", "range_chop"),
                                             ("2026-10-23", "range_chop")]))
    sc = card["scope"]
    assert card["available"] is True
    assert sc["first_session"] == "2026-10-23"
    assert sc["sessions"] == 1, "the pre-cutover row must not be counted"
    assert sc["excluded_pre_cutover"] == ["2026-10-20"], "and must still be NAMED"


@pytest.mark.asyncio
async def test_first_session_may_NEVER_precede_the_instant():
    """QUERY's N1/N2. The boundary is breached if first_session's close is not after it."""
    from services.read_only import regime_strategy as svc

    card = await svc._report_card(_CardConn([("2026-10-20", "range_chop"),
                                             ("2026-10-23", "range_chop")]))
    sc = card["scope"]
    if sc.get("first_session"):
        assert rs.session_close(sc["first_session"]) > INSTANT


@pytest.mark.asyncio
async def test_BACKFILLED_is_ASSERTED_not_defaulted():
    """It read `False` as a literal with nothing having checked anything -- a claim the payload
    had not earned. It is now the result of the scope test, with the instant, its source and the
    excluded rows all present so a reader can repeat the check."""
    from services.read_only import regime_strategy as svc

    card = await svc._report_card(_CardConn([("2026-10-23", "range_chop")]))
    sc = card["scope"]
    assert sc["backfilled"] is False
    assert sc["first_session_close"] == "2026-10-23T16:00:00-04:00"
    assert rs.session_close(sc["first_session"]).isoformat() == sc["first_session_close"]

    src = read_source(str(_BACKEND / "services" / "read_only" / "regime_strategy.py"))
    assert '"backfilled": False' not in src, "a literal False is the thing P11 forbids"


@pytest.mark.asyncio
async def test_the_three_required_fields_are_present_WHENEVER_available():
    from services.read_only import regime_strategy as svc

    card = await svc._report_card(_CardConn([("2026-10-23", "range_chop")]))
    assert card["available"] is True
    for key in ("cutover_instant", "cutover_source", "excluded_pre_cutover"):
        assert key in card["scope"], key


@pytest.mark.asyncio
async def test_NO_MARKER_scores_nothing_and_says_why():
    from services.read_only import regime_strategy as svc

    card = await svc._report_card(_CardConn([("2026-10-23", "range_chop")], marker=None))
    assert card["available"] is False
    assert "not recorded" in card["reason"]
    assert card["scope"]["cutover_instant"] is None


@pytest.mark.asyncio
async def test_the_startup_writes_the_marker_on_EVERY_path():
    """It records when the version went live, which the card scopes on -- so it cannot sit
    inside the cutover branch. A version that seeded, one that inherited and one that found
    rows present all went live at the same moment."""
    src = read_source(str(_BACKEND / "main.py"))
    i = src.index("ensure_version_live")
    # it must come BEFORE the branch that distinguishes the three cases
    assert i < src.index("elif _RV in _PRED:")
    assert i < src.index("_have = await _conn.fetchval")
