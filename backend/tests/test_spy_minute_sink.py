"""1-minute SPY is kept as a system of record — R-IV.680(b).

Side-measure 3 prices SPY at the finest bar at or before each fire minute, and the vendor serves
1m for the TRAILING 30 DAYS ONLY — Yahoo says so in its own error text. So the lens's own inputs
expire: August's are gone and W1's leave around 10-15. CC-QUERY's ferry capture is evidence, not a
system of record a grader can read.

MEASURED 2026-10-07 before any of this was written: yfinance serves 1m SPY back to 2026-09-09, so
every session from 09-15 is still live and the capture is a contingency rather than a dependency;
390 bars per full session; the index is tz-aware UTC; and yfinance 0.2.59 returns MultiIndex
columns for a single ticker, so a bare `df["Close"]` is a DataFrame rather than a Series.
"""

import ast
import io
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from jobs.spy_minute_backfill import chunks, compare_to_capture, load_capture
from jobs.spy_minute_sink import (FIELD_LIVENESS, FULL_SESSION_BARS, HALF_SESSION_BARS,
                                  PROV_YFINANCE, SKIP, ferry_provenance, frame_to_bars,
                                  persist_bars, session_report)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(rel):
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "".join(l for l in src.splitlines(keepends=True)
                   if not l.strip().startswith("#"))


class _Conn:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((" ".join(sql.split()), args))


def _bars(n, day=date(2026, 9, 15), start_utc=(13, 30)):
    base = datetime(day.year, day.month, day.day, start_utc[0], start_utc[1],
                    tzinfo=timezone.utc)
    return [{"bar_at": base + timedelta(minutes=i), "session_date": day,
             "open": Decimal("660.1"), "high": Decimal("660.4"), "low": Decimal("660.0"),
             "close": Decimal("660.25"), "volume": 1000 + i} for i in range(n)]


class TestTheVendorIsTheGradersVendor:
    def test_the_fetch_is_yfinance_and_the_basis_is_in_the_provenance(self):
        """The grader grades on yfinance end to end (`triton_shadow_common`). Pricing the lens
        from a different vendor would make the excess figure a comparison of two vendors rather
        than of a row against the market."""
        assert "yfinance" in PROV_YFINANCE
        assert "auto_adjust=false" in PROV_YFINANCE
        src = _code("jobs/spy_minute_sink.py")
        assert 'interval="1m"' in src
        assert "import yfinance as yf" in src

    def test_auto_adjust_is_required_keyword_only(self):
        """0.2.59 changed the library default to True, and an adjusted 1-minute series is not the
        price a row fired at. No caller may inherit that answer by silence."""
        import inspect

        from jobs.spy_minute_sink import fetch_1m

        p = inspect.signature(fetch_1m).parameters["auto_adjust"]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
        assert p.default is inspect.Parameter.empty


class TestTheVendorsFrameIsReadCorrectly:
    def test_multiindex_columns_are_handled(self):
        """yfinance 0.2.59 returns ('Close','SPY') for a single ticker. Reading `df["Close"]`
        yields a DataFrame -- it does not raise, it just gives something that is not a number,
        which is the `price` vs `spot` fault in another costume."""
        pd = pytest.importorskip("pandas")
        idx = pd.DatetimeIndex([datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc),
                                datetime(2026, 9, 15, 13, 31, tzinfo=timezone.utc)])
        cols = pd.MultiIndex.from_tuples(
            [("Open", "SPY"), ("High", "SPY"), ("Low", "SPY"), ("Close", "SPY"),
             ("Volume", "SPY")])
        df = pd.DataFrame([[1.0, 2.0, 0.5, 1.5, 10], [1.1, 2.1, 0.6, 1.6, 11]],
                          index=idx, columns=cols)
        bars = frame_to_bars(df, "SPY")
        assert len(bars) == 2
        assert bars[0]["close"] == Decimal("1.5")
        assert bars[0]["volume"] == 10

    def test_a_flat_frame_still_works(self):
        """POSITIVE CONTROL: the handling must not depend on the MultiIndex being present."""
        pd = pytest.importorskip("pandas")
        idx = pd.DatetimeIndex([datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc)])
        df = pd.DataFrame([[1.0, 2.0, 0.5, 1.5, 10]], index=idx,
                          columns=["Open", "High", "Low", "Close", "Volume"])
        bars = frame_to_bars(df, "SPY")
        assert len(bars) == 1 and bars[0]["close"] == Decimal("1.5")

    def test_a_nan_close_is_not_a_price(self):
        """`float("nan")` survives every `if not x` guard -- `not nan` is False and `nan <= 0` is
        False -- so it is caught by name or it looks like a reading."""
        pd = pytest.importorskip("pandas")
        idx = pd.DatetimeIndex([datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc),
                                datetime(2026, 9, 15, 13, 31, tzinfo=timezone.utc)])
        df = pd.DataFrame([[1.0, 2.0, 0.5, float("nan"), 10],
                          [1.1, 2.1, 0.6, 1.6, 11]], index=idx,
                         columns=["Open", "High", "Low", "Close", "Volume"])
        bars = frame_to_bars(df, "SPY")
        assert len(bars) == 1, "the NaN-close bar prices nothing and is dropped"
        assert bars[0]["close"] == Decimal("1.6")

    def test_the_session_is_the_ET_date_not_the_UTC_one(self):
        """A bar after 00:00 UTC belongs to the PREVIOUS ET session, and that is the only case
        that can tell the two derivations apart.

        My first version of this used 2026-01-15 14:30Z and asserted "2026-01-15" -- but that is
        09:30 EST and the UTC date is the same, so the assertion held whichever derivation was
        used. A mutation run replacing the zoneinfo conversion with `ts.date()` left it green.
        Worth recording WHY, because it bears on the production data: a regular-session bar
        (09:30-16:00 ET) can never straddle midnight UTC, so the conversion is defensive rather
        than load-bearing for SPY today. It is still the right derivation -- an extended-hours or
        futures bar would straddle, and a fixed -4 offset would be wrong for four months a year.
        """
        pd = pytest.importorskip("pandas")
        idx = pd.DatetimeIndex([
            datetime(2026, 9, 16, 0, 30, tzinfo=timezone.utc),    # 20:30 ET on 09-15
            datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc),   # 09:30 ET on 09-15
            datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc),   # 09:30 EST (-5), not -4
        ])
        df = pd.DataFrame([[1.0, 2.0, 0.5, 1.5, 10]] * 3, index=idx,
                          columns=["Open", "High", "Low", "Close", "Volume"])
        got = {b["bar_at"].isoformat(): str(b["session_date"]) for b in frame_to_bars(df, "SPY")}
        assert got["2026-09-16T00:30:00+00:00"] == "2026-09-15", (
            "a 00:30Z bar is the previous ET session; `ts.date()` would say 09-16")
        assert got["2026-09-15T13:30:00+00:00"] == "2026-09-15"
        assert got["2026-01-15T14:30:00+00:00"] == "2026-01-15"


class TestFieldLivenessIsPerSession:
    def test_the_declaration_carries_its_measurement(self):
        assert FIELD_LIVENESS["expected_bars_full_session"] == 390
        assert FIELD_LIVENESS["vendor_horizon_days"] == 30
        assert "2026-10-07" in FIELD_LIVENESS["measured_on"]

    def test_a_full_session_is_recognised(self):
        rep = session_report(_bars(FULL_SESSION_BARS))
        assert rep["known_length"] is True
        assert rep["per_session"]["2026-09-15"]["bars"] == 390
        assert rep["per_session"]["2026-09-15"]["distinct_gaps_s"] == [60]

    def test_counts_are_per_session_not_over_the_batch(self):
        """The first version compared the TOTAL against one session's length, so a correct
        two-session fetch (780 bars) reported `known_length: False`. An instrument that calls a
        correct batch defective is how a HALT comes to be ignored."""
        two = _bars(FULL_SESSION_BARS) + _bars(FULL_SESSION_BARS, day=date(2026, 9, 16))
        rep = session_report(two)
        assert rep["bars"] == 780
        assert rep["known_length"] is True
        assert rep["sessions"] == ["2026-09-15", "2026-09-16"]
        assert all(v["bars"] == 390 for v in rep["per_session"].values())
        # and the overnight boundary is NOT counted as a gap in either session
        assert all(v["distinct_gaps_s"] == [60] for v in rep["per_session"].values())

    def test_a_half_day_is_a_known_length(self):
        assert session_report(_bars(HALF_SESSION_BARS))["known_length"] is True

    def test_an_odd_length_is_named_not_guessed(self):
        rep = session_report(_bars(200))
        assert rep["known_length"] is False
        assert rep["sessions_of_unknown_length"] == ["2026-09-15"]


class TestProvenanceIsOnEveryRow:
    @pytest.mark.asyncio
    async def test_the_provenance_is_required_and_written(self):
        with pytest.raises(TypeError):
            await persist_bars(_Conn(), _bars(2))
        conn = _Conn()
        await persist_bars(conn, _bars(2), provenance=PROV_YFINANCE)
        assert all(c[1][-1] == PROV_YFINANCE for c in conn.calls)

    def test_a_ferry_row_names_the_capture_it_came_from(self):
        p = ferry_provenance("2db41815DEAD")
        assert p.startswith("ferry:")
        assert "2db41815dead" in p

    def test_the_column_is_not_null_so_a_row_cannot_omit_it(self):
        """A provenance column that only appears when something is wrong is one nobody reads."""
        src = _code("database/postgres_client.py")
        i = src.index("CREATE TABLE IF NOT EXISTS spy_minute_bars")
        block = src[i:src.index('"""', i)]
        assert "provenance TEXT NOT NULL" in block
        assert "bar_at TIMESTAMPTZ PRIMARY KEY" in block
        # EVERY price column, named. Asserting the substring once let a mutation narrow `close`
        # alone to NUMERIC(12,4) while the other three still matched -- so the test passed while
        # the column that the lens actually reads was the one silently truncating.
        for col in ("open", "high", "low", "close"):
            assert "%s NUMERIC(18,8)" % col in block, (
                "%s must hold the vendor's value faithfully; a narrower scale truncates it" % col)

    @pytest.mark.asyncio
    async def test_the_upsert_is_idempotent_on_the_bar_instant(self):
        a, b = _Conn(), _Conn()
        r1 = await persist_bars(a, _bars(5), provenance=PROV_YFINANCE)
        r2 = await persist_bars(b, _bars(5), provenance=PROV_YFINANCE)
        assert r1["written"] == r2["written"] == 5
        assert "ON CONFLICT (bar_at) DO UPDATE" in a.calls[0][0]


class TestTheCaptureIsOnlyAdmissibleHashVerified:
    def _cap(self, tmp_path, rows):
        import json

        p = tmp_path / "cap.json"
        p.write_text(json.dumps(rows), encoding="utf-8")
        return str(p)

    def test_a_matching_prefix_is_accepted(self, tmp_path):
        from jobs.spy_minute_backfill import capture_sha256

        p = self._cap(tmp_path, [{"bar_at": "2026-09-15T13:30:00+00:00", "close": "660.25"}])
        cap, err = load_capture(p, capture_sha256(p)[:12])
        assert err is None and cap["count"] == 1

    def test_a_truncated_hash_with_an_ellipsis_is_accepted(self, tmp_path):
        """R-IV.680(b) quotes the hash truncated ("2db41815…"), so demanding full equality would
        reject the very file the ruling names."""
        from jobs.spy_minute_backfill import capture_sha256

        p = self._cap(tmp_path, [{"bar_at": "x", "close": "1"}])
        cap, err = load_capture(p, capture_sha256(p)[:8] + "…")
        assert err is None

    def test_a_wrong_hash_is_refused_and_the_file_is_not_read(self, tmp_path):
        p = self._cap(tmp_path, [{"bar_at": "x", "close": "1"}])
        cap, err = load_capture(p, "deadbeef")
        assert cap is None and "mismatch" in err

    def test_no_hash_at_all_is_refused(self, tmp_path):
        """POSITIVE CONTROL. The capture is admissible only hash-verified, so an unverified file
        must be refused rather than trusted -- otherwise the gate is decorative."""
        p = self._cap(tmp_path, [{"bar_at": "x", "close": "1"}])
        cap, err = load_capture(p, "")
        assert cap is None and "hash-verified" in err

    def test_a_too_short_prefix_is_refused(self, tmp_path):
        p = self._cap(tmp_path, [{"bar_at": "x", "close": "1"}])
        cap, err = load_capture(p, "2db4")
        assert cap is None and "too short" in err

    def test_the_cross_check_reports_disagreement_rather_than_asserting_agreement(self):
        """Which of two sources is wrong is not this function's call to make."""
        bars = _bars(2)
        cap = {"by_instant": {bars[0]["bar_at"].isoformat(): {"close": "660.25"},
                              bars[1]["bar_at"].isoformat(): {"close": "999.99"}}}
        res = compare_to_capture(bars, cap)
        assert res["checked"] == 2 and res["agreed"] == 1
        assert res["disagreements"][0]["capture"] == "999.99"


class TestTheForwardCollectorIsObservable:
    def test_it_runs_under_the_liveness_wrapper_with_a_session_date(self):
        """§5.1, plus the durable `job_runs` row that makes "did today's capture happen?"
        survive a restart -- the in-process set cannot."""
        src = _code("jobs/stable_jobs.py")
        assert '_run_job(SPY_MINUTE_JOB, _run, session_date=day)' in src

    def test_it_is_gated_on_the_post_close_time_and_a_trading_day(self):
        src = _code("jobs/stable_jobs.py")
        i = src.index("await _maybe_capture_spy_minute(et)")
        before = src[:i]
        assert "if _traded is True:" in before
        assert "(et.hour, et.minute) >= (pch, pcm)" in before

    def test_a_pass_that_produces_nothing_is_a_defective_completion(self):
        """R-IV.426(b): not a success and not a crash. A skip recorded as success would make a
        missing session invisible, and the vendor only keeps 30 days."""
        src = _code("jobs/stable_jobs.py")
        i = src.index("async def _maybe_capture_spy_minute")
        body = src[i:src.index("\nasync def ", i + 10)]
        assert body.count("OutputCheckFailed") == 2

    def test_every_skip_names_itself(self):
        assert len(SKIP) >= 4
        assert all(":" in s for s in SKIP)


class TestTheBackfillWindowing:
    def test_chunks_respect_the_vendors_seven_day_cap(self):
        cs = chunks(date(2026, 9, 15), date(2026, 10, 7))
        assert all((b - a).days <= 7 for a, b in cs)
        assert cs[0][0] == date(2026, 9, 15)
        assert cs[-1][1] == date(2026, 10, 7)
        # contiguous, no gap and no overlap
        assert all(cs[i][1] == cs[i + 1][0] for i in range(len(cs) - 1))

    def test_the_default_start_is_the_ruling_s_date(self):
        from jobs.spy_minute_backfill import DEFAULT_START

        assert DEFAULT_START == date(2026, 9, 15)
