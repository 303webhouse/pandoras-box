"""The yield box's numbers keep up with their source, and a stale refusal reads as stale.

R-IV.1343(b) and (c).

WHAT WAS WRONG, measured on production at 2026-10-22 22:22Z and not reasoned about. Asked
directly, FRED served `DGS10 2026-10-21 = 5.13` and `T10Y2Y 2026-10-22 = 0.31`. At the same
moment the hub's own `/api/yield-curve` served `10Y as of 2026-10-20 = 5.12` and
`2s10s as of 2026-10-21 = 0.32`. Every figure in the box was EXACTLY ONE SESSION behind its own
source -- with `key_present: true`, no `unavailable_reason` on any tenor, nothing blank and a
clean browser console. The box looked healthy and was wrong, which is the only kind of wrong
that survives.

THE CAUSE WAS A CACHE KEYED ON THE UTC DATE. `fetch_series` returned a cached copy whenever
`hit[0] == today`, on the stated premise that "these are daily series, so polling them more
often spends a call to receive the same number". That premise fails for the hours that matter:
FRED's H.15 series publish session D's value on the NEXT business day, late in the ET
afternoon. The hub started at 19:03:00Z, about 75 minutes before FRED published 10-21, so it
cached a pre-release copy -- and a key of (series, UTC date) pinned that copy until the UTC date
rolled at 20:00 ET. The window is a few hours long, it recurs daily, and it heals itself
overnight, which is exactly why it had never been caught.

THE OTHER HALF OF THIS BOX ALREADY KNEW. `models/yield_intraday.py` carries
`CACHE_SECONDS = 15 * 60` and a test called `test_the_cache_is_one_bar_long_and_not_one_day`,
whose stated reason -- "a day-long cache on an intraday series serves the open all afternoon" --
is this fault one tier up. A daily series does not need a 15-minute window; it needs one shorter
than the gap between a release and the end of the UTC day.

AND THE HEADER OVERCLAIMED ITS OWN FRESHNESS. `as_of` was `max()` over tenors AND spreads, and
those two do not move together: FRED publishes the computed spread a session ahead of the DGS
levels. So the header read "as of 2026-10-21" directly above five levels dated 10-20. Convention
#29 governs a field whose MEANING changes, so the readers were counted first: all three are in
the yield box header and tooltips (v2.js 3823, 3825, 3832) and every one words it as the date of
"the FRED values", which is the levels. The field now means what its only readers already said.

(b) IS A SEPARATE FAULT IN THE SAME FAMILY -- a reading whose AGE is invisible. The regime
card's reason string said "last run: degraded - ... SPY: HTTP 403" on 2026-10-22 while the audit
row behind it was written on 10-20, and it cost a wrong first reading of the v2.1 cutover: a
stale audit row looked like a live Polygon failure on brand-new code.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from integrations import fred_series as fs                           # noqa: E402

from ._srcscan import read_source                                   # noqa: E402


def _points(dates):
    return [(dt.date.fromisoformat(d), float(i + 1)) for i, d in enumerate(dates)]


# ── (c) the cache must not outlive FRED's release ───────────────────────────

def test_the_cache_window_is_SECONDS_and_not_a_UTC_DAY():
    """The fix, asserted as a number. A day-keyed cache cannot pick up a release that happens
    after it was filled, however many times it is asked."""
    assert isinstance(fs.CACHE_SECONDS, int)
    assert 0 < fs.CACHE_SECONDS <= 3600, fs.CACHE_SECONDS


def test_a_fetch_is_REUSED_inside_the_window(monkeypatch):
    """Still cached -- the point was never to stop caching."""
    calls = []

    fs._cache.clear()
    monkeypatch.setattr(fs, "key_present", lambda: True)
    # The real function runs; only the fredapi boundary is stubbed.
    monkeypatch.setitem(sys.modules, "fredapi", _FakeFredapi(["2026-10-19", "2026-10-20"], calls))
    first = fs.fetch_series("DGS10")
    second = fs.fetch_series("DGS10")
    assert first == second
    assert len(calls) == 1, "the second call should have been served from cache"


def test_the_cache_EXPIRES_so_a_post_release_value_can_arrive(monkeypatch):
    """THE REGRESSION TEST FOR THE MEASURED FAULT, and it discriminates.

    Fetch before the release, advance only the CLOCK past the window, fetch again. The UTC
    date never changes -- which is the whole point, because that is the situation production
    was in between FRED's release and 20:00 ET.

    Under the old `hit[0] == today` rule this FAILS: the second fetch returns the pre-release
    copy no matter how much time has passed. Verified by reverting the predicate and watching
    this test go red (Convention #30), which an earlier draft of it could not do -- it faked
    the expiry by writing into `_cache`, and the old predicate never read that number at all.
    """
    calls = []
    fs._cache.clear()
    monkeypatch.setattr(fs, "key_present", lambda: True)
    clock = [1000.0]
    monkeypatch.setattr(fs, "_now", lambda: clock[0])

    # before the release: FRED's newest observation is 10-20
    monkeypatch.setitem(sys.modules, "fredapi",
                        _FakeFredapi(["2026-10-19", "2026-10-20"], calls))
    before = fs.fetch_series("DGS10")
    assert before[-1][0].isoformat() == "2026-10-20"
    assert len(calls) == 1

    # FRED publishes 10-21. Time passes. THE UTC DATE IS UNCHANGED.
    monkeypatch.setitem(sys.modules, "fredapi",
                        _FakeFredapi(["2026-10-19", "2026-10-20", "2026-10-21"], calls))
    clock[0] = 1000.0 + fs.CACHE_SECONDS + 1

    after = fs.fetch_series("DGS10")
    assert after[-1][0].isoformat() == "2026-10-21", (
        "a released observation must be reachable without waiting for the UTC date to roll")
    assert len(calls) == 2


def test_time_passing_INSIDE_the_window_still_serves_the_cache(monkeypatch):
    """The other side of the same seam, so the TTL is not just "always refetch"."""
    calls = []
    fs._cache.clear()
    monkeypatch.setattr(fs, "key_present", lambda: True)
    clock = [1000.0]
    monkeypatch.setattr(fs, "_now", lambda: clock[0])
    monkeypatch.setitem(sys.modules, "fredapi", _FakeFredapi(["2026-10-20"], calls))
    fs.fetch_series("DGS10")
    clock[0] = 1000.0 + fs.CACHE_SECONDS - 1
    fs.fetch_series("DGS10")
    assert len(calls) == 1


def test_the_cache_is_NOT_keyed_on_the_date_any_more():
    """Positive and structural: the old predicate is gone from the fetch path."""
    src = read_source(str(_BACKEND / "integrations" / "fred_series.py"))
    i = src.index("def fetch_series(")
    block = src[i:i + 3000]
    assert "hit[0] == today" not in block
    assert "CACHE_SECONDS" in block
    assert "_now()" in block            # the clock seam, not a bare monotonic call


def test_the_module_still_refuses_without_a_key_and_never_names_it(monkeypatch):
    """Unchanged behaviour, re-asserted because the fetch path was edited: no key means an
    EMPTY series, not a stale one, and nothing anywhere prints the value."""
    fs._cache.clear()
    monkeypatch.setattr(fs, "key_present", lambda: False)
    assert fs.fetch_series("DGS10") == []
    src = read_source(str(_BACKEND / "integrations" / "fred_series.py"))
    assert 'os.environ["FRED_API_KEY"]' in src          # used
    assert "FRED_API_KEY present" in src                # reported as presence only


# ── (c) staleness has to be VISIBLE, not just short-lived ───────────────────

def test_cache_state_reports_the_age_and_the_newest_observation(monkeypatch):
    calls = []
    fs._cache.clear()
    monkeypatch.setattr(fs, "key_present", lambda: True)
    monkeypatch.setitem(sys.modules, "fredapi",
                        _FakeFredapi(["2026-10-19", "2026-10-20"], calls))
    fs.fetch_series("DGS10")
    st = fs.cache_state()
    assert st["ttl_seconds"] == fs.CACHE_SECONDS
    assert st["series"]["DGS10"]["newest_observation"] == "2026-10-20"
    assert st["series"]["DGS10"]["age_seconds"] >= 0
    assert st["series"]["DGS10"]["observations"] == 2


def test_cache_state_names_no_key_and_no_value(monkeypatch):
    """It reports series ids, ages and observation DATES. R-IV.1210(c)/1212(c) and the standing
    rule: presence, never a value, never a length, never a prefix."""
    calls = []
    fs._cache.clear()
    monkeypatch.setattr(fs, "key_present", lambda: True)
    monkeypatch.setitem(sys.modules, "fredapi", _FakeFredapi(["2026-10-20"], calls))
    fs.fetch_series("DGS10")
    import json
    blob = json.dumps(fs.cache_state())
    assert "FRED_API_KEY" not in blob
    for forbidden in ("api_key", "apikey", "secret", "token"):
        assert forbidden not in blob.lower()


def test_the_newest_observation_SKIPS_HOLES():
    """FRED marks an unpublished day with a hole, and `latest` already skipped them. The cache
    report has to agree with `latest` or the two would disagree about the same series."""
    pts = [(dt.date(2026, 10, 19), 5.0), (dt.date(2026, 10, 20), None)]
    fs._cache.clear()
    fs._cache["X"] = (fs._time.monotonic(), pts)
    assert fs.cache_state()["series"]["X"]["newest_observation"] == "2026-10-19"
    assert fs.latest(pts)[0].isoformat() == "2026-10-19"


# ── (c) the header's date is the LEVELS' date ───────────────────────────────

def test_as_of_is_the_LEVELS_date_and_the_spreads_carry_their_own():
    """The measured shape: tenors a session behind the spread. The header sits above the levels,
    so it must not advertise the spread's newer date."""
    import api.yield_curve as ycapi

    src = read_source(str(_BACKEND / "api" / "yield_curve.py"))
    assert "level_as_ofs" in src and "spread_as_ofs" in src
    i = src.index('"as_of": max(')
    assert "level_as_ofs" in src[i:i + 80]
    assert '"as_of_spreads"' in src
    assert "max(as_ofs)" not in src
    assert hasattr(ycapi, "payload")


def test_the_route_surfaces_the_FRED_CACHE_state():
    src = read_source(str(_BACKEND / "api" / "yield_curve.py"))
    assert '"fred_cache": fred.cache_state()' in src
    assert '"fred_cache": "derived"' in src


# ── (b) a stale refusal reads as stale ──────────────────────────────────────

def test_an_OLD_audit_row_renders_its_TIMESTAMP_and_its_AGE():
    """R-IV.1343(b)'s required test, run against the real string builder with a fake row.

    The row is two days old, which is the case that misled a reader: without a timestamp, "last
    run: degraded - SPY: HTTP 403" on brand-new code reads as the new code failing.
    """
    import asyncio

    from jobs import regime_job

    written = dt.datetime(2026, 10, 20, 1, 33, 0, tzinfo=dt.timezone.utc)

    class FakeConn:
        async def fetch(self, *a, **k):
            return []                      # no snapshot for this version -> the reason path

        async def fetchrow(self, *a, **k):
            return {"action": "degraded",
                    "detail": "DEGRADED, no label written: SPY: HTTP 403",
                    "created_at": written}

    out = asyncio.run(regime_job.latest_with_diff(FakeConn(), "v2.1"))
    why = out["unavailable_reason"]

    assert "no regime_snapshots row for rules v2.1" in why
    assert "2026-10-20T01:33:00" in why, why          # the timestamp itself
    assert "h ago)" in why, why                        # and its age
    assert "degraded" in why and "HTTP 403" in why     # the original content is kept


def test_a_NAIVE_created_at_is_read_as_UTC_and_does_not_RAISE():
    """The column is TIMESTAMPTZ so asyncpg hands back an aware value -- but the whole block
    sits inside an `except Exception` that would turn a formatting slip into "regime_audit
    unreadable" and hide the real reason. So a naive value is handled rather than trusted."""
    import asyncio

    from jobs import regime_job

    class FakeConn:
        async def fetch(self, *a, **k):
            return []

        async def fetchrow(self, *a, **k):
            return {"action": "refused", "detail": "not a trading day",
                    "created_at": dt.datetime(2026, 10, 20, 1, 33, 0)}   # naive

    why = asyncio.run(regime_job.latest_with_diff(FakeConn(), "v2.1"))["unavailable_reason"]
    assert "unreadable" not in why, why
    assert "2026-10-20T01:33:00" in why


def test_a_MISSING_created_at_says_so_rather_than_inventing_one():
    import asyncio

    from jobs import regime_job

    class FakeConn:
        async def fetch(self, *a, **k):
            return []

        async def fetchrow(self, *a, **k):
            return {"action": "refused", "detail": "x", "created_at": None}

    why = asyncio.run(regime_job.latest_with_diff(FakeConn(), "v2.1"))["unavailable_reason"]
    assert "unrecorded" in why, why
    assert "unreadable" not in why


def test_the_audit_lookup_is_still_UNFILTERED_and_the_comment_says_so():
    """The query is unchanged ON PURPOSE -- (b) approved showing the age, not narrowing the
    query. That it spans every version and every date is the reason the row can be old at all,
    so it is written down next to the code rather than left to be rediscovered."""
    src = read_source(str(_BACKEND / "jobs" / "regime_job.py"))
    # ANCHORED ON THE FUNCTION, not on the first textual match. This read
    # `src.index("FROM regime_audit")`, and P11 (R-IV.1354(b)) added
    # `version_live_instant` ABOVE this one -- whose lookup is deliberately filtered by
    # rules_version. The locator then pointed at the wrong query and this test failed
    # while the thing it checks was untouched. Same class as the 9000-character window.
    f = src.index("async def latest_with_diff(")
    i = src.index("FROM regime_audit", f)
    block = src[f:i + 400]
    assert "ORDER BY created_at DESC" in block
    assert "rules_version" not in block.split("FROM regime_audit")[1][:200]


class _FakeFredapi:
    """A stand-in for the `fredapi` module, so the real `fetch_series` body runs.

    Patched into `sys.modules` rather than onto the module under test: `fetch_series` does
    `from fredapi import Fred` INSIDE the function, so an attribute set on `fred_series` would
    never be consulted. (Memory's suite trap is the mirror image of this -- patch the real
    module, not `sys.modules`, when the import is at module scope. The rule is to match where
    the import actually happens.)
    """

    def __init__(self, dates, calls):
        self._dates = list(dates)
        self._calls = calls
        outer = self

        class _Fred:
            def __init__(self, api_key=None):
                pass

            def get_series(self, series_id, observation_start=None):
                outer._calls.append(series_id)
                return _FakeSeries(outer._dates)

        self.Fred = _Fred


class _FakeSeries:
    """The minimum of a pandas Series that `fetch_series` touches: `.empty` and `.items()`."""

    def __init__(self, dates):
        self._items = [(dt.date.fromisoformat(d), float(i + 1)) for i, d in enumerate(dates)]
        self.empty = not self._items

    def __len__(self):
        return len(self._items)

    def items(self):
        return iter(self._items)
