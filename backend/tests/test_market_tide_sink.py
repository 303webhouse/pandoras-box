"""`market_tide_history` keeps every reading UW returns — R-IV.675(b).

Tide has been fetched every five minutes for months and discarded: `_warm_tide` took
`series[-1]`, cached three scalars in Redis under a 1,800 s TTL, and dropped the rest. The tide
leg of the principal's confluence gate therefore had no row to test against.

Measured against the vendor on 2026-10-06, before any of this was written: one call returns the
whole session (81 rows, 09:30 -> 16:10 ET, a single distinct interval of 300 s), the premiums
arrive as STRINGS, and `?date=` serves past sessions.
"""

import ast
import io
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from jobs.market_tide_sink import (FIELD_LIVENESS, SKIP, SKIP_MALFORMED, SKIP_NO_PAYLOAD,
                                   SKIP_NO_ROWS, SKIP_NO_USABLE_ROW, liveness_report,
                                   parse_tick, persist_series, series_of)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# One reading exactly as the vendor sent it, copied from the 2026-10-06 probe.
REAL = {"timestamp": "2026-10-06T09:30:00-04:00", "date": "2026-10-06",
        "net_call_premium": "20650902.0000", "net_put_premium": "-4503628.0000",
        "net_volume": 61108}


def _code(rel):
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "".join(l for l in src.splitlines(keepends=True)
                   if not l.strip().startswith("#"))


def _series(n, start="2026-10-06T09:30:00-04:00", step=300, drop=()):
    base = datetime.fromisoformat(start)
    out = []
    for i in range(n):
        row = {"timestamp": (base + timedelta(seconds=step * i)).isoformat(),
               "date": "2026-10-06", "net_call_premium": "100.0000",
               "net_put_premium": "-50.0000", "net_volume": 10 + i}
        for f in drop:
            row[f] = None
        out.append(row)
    return out


class _Conn:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((" ".join(sql.split()), args))


class TestTheMoneyIsNotCastThroughFloat:
    def test_a_premium_string_becomes_decimal(self):
        """The vendor sends `"20650902.0000"`. This is the only point the exact value exists;
        `float()` here is a lossy cast of money that nothing downstream can undo."""
        t = parse_tick(REAL)
        assert isinstance(t["net_call_premium"], Decimal)
        assert t["net_call_premium"] == Decimal("20650902.0000")
        assert t["net_put_premium"] == Decimal("-4503628.0000")

        # THE TYPE AND THE VALUE ARE NOT ENOUGH, and a mutation run proved it: routing the
        # string through float() still yields a Decimal that still compares EQUAL, because
        # Decimal("20650902.0000") == Decimal("20650902.0"). Both assertions above stayed green
        # against the lossy version. These two catch it:
        #   - the exact scale survives (a float round-trip collapses the trailing zeros);
        #   - a value with more significant digits than a float64 can hold is kept intact.
        assert str(t["net_call_premium"]) == "20650902.0000"
        big = parse_tick(dict(REAL, net_call_premium="12345678901234567.8901"))
        assert str(big["net_call_premium"]) == "12345678901234567.8901"

    def test_the_column_is_numeric_not_double(self):
        src = _code("database/postgres_client.py")
        i = src.index("CREATE TABLE IF NOT EXISTS market_tide_history")
        # Bounded to the statement, not a char count: the DDL carries SQL `--` comments that a
        # fixed window silently truncated, and the test then "passed" on half a table.
        block = src[i:src.index('"""', i)]
        assert "net_call_premium NUMERIC" in block
        assert "net_put_premium NUMERIC" in block
        assert "DOUBLE" not in block.upper()
        assert "net_volume BIGINT" in block

    def test_a_premium_that_is_not_a_number_is_none_not_zero(self):
        """POSITIVE CONTROL. Zero is a reading; absent is not. Collapsing them would make a
        vendor hiccup look like a flat tape."""
        t = parse_tick(dict(REAL, net_call_premium="n/a"))
        assert t["net_call_premium"] is None


class TestTheKeyIsTheVendorsTick:
    def test_the_tick_is_stored_in_utc(self):
        t = parse_tick(REAL)
        assert t["tick_at"] == datetime(2026, 10, 6, 13, 30, tzinfo=timezone.utc)

    def test_the_session_date_is_kept_as_sent_not_derived(self):
        """A 16:10 ET tick is the NEXT day in UTC. Deriving the session from the instant would
        file the last 20 minutes of every session under tomorrow."""
        t = parse_tick({"timestamp": "2026-10-06T16:10:00-04:00", "date": "2026-10-06",
                        "net_call_premium": "1", "net_put_premium": "1", "net_volume": 1})
        assert t["tick_at"].date() == datetime(2026, 10, 6, 20, 10,
                                               tzinfo=timezone.utc).date()
        assert str(t["session_date"]) == "2026-10-06"

    def test_the_primary_key_is_tick_at(self):
        src = _code("database/postgres_client.py")
        i = src.index("CREATE TABLE IF NOT EXISTS market_tide_history")
        assert "tick_at TIMESTAMPTZ PRIMARY KEY" in src[i:src.index('"""', i)]

    def test_fetched_at_is_provenance_not_identity(self):
        """Keyed on the fetch time, the 5-minute cadence would mint 81 duplicate rows an hour."""
        src = _code("jobs/market_tide_sink.py")
        assert "ON CONFLICT (tick_at) DO UPDATE" in src
        assert "ON CONFLICT (fetched_at" not in src

    def test_a_reading_with_no_timestamp_is_dropped(self):
        assert parse_tick({"date": "2026-10-06", "net_volume": 1}) is None
        assert parse_tick({"timestamp": "not a time"}) is None


class TestTheWholeSeriesIsUpserted:
    @pytest.mark.asyncio
    async def test_every_reading_is_written(self):
        conn = _Conn()
        res = await persist_series(conn, {"data": _series(81)}, source="warmer")
        assert res["written"] == 81
        assert res["rows_touched"] == 81
        assert res["skipped"] is False
        assert len(conn.calls) == 81

    @pytest.mark.asyncio
    async def test_re_reading_the_same_session_is_idempotent(self):
        """Two polls of one session must converge, not accumulate. The upsert is what makes a
        re-read safe, and the 5-minute warmer re-reads the same series all day."""
        payload = {"data": _series(10)}
        a, b = _Conn(), _Conn()
        r1 = await persist_series(a, payload, source="warmer")
        r2 = await persist_series(b, payload, source="warmer")
        assert r1["written"] == r2["written"] == 10
        assert [c[1][0] for c in a.calls] == [c[1][0] for c in b.calls]

    @pytest.mark.asyncio
    async def test_the_source_is_required_and_recorded(self):
        """Keyword-only and required: a row that cannot say whether it came from the live
        warmer or a dated backfill cannot be audited, and a default would let one caller
        inherit the other's answer by silence."""
        with pytest.raises(TypeError):
            await persist_series(_Conn(), {"data": _series(2)})
        conn = _Conn()
        await persist_series(conn, {"data": _series(2)}, source="backfill")
        assert all(c[1][-1] == "backfill" for c in conn.calls)


class TestEverySkipRecordsItsReason:
    """§5.4 of the collector design law: the taxonomy is enumerated at design time."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload,expected", [
        (None, SKIP_NO_PAYLOAD),
        ({"data": "not a list"}, SKIP_MALFORMED),
        ({"data": []}, SKIP_NO_ROWS),
        ({"data": [{"net_volume": 1}]}, SKIP_NO_USABLE_ROW),
    ])
    async def test_each_failure_names_itself(self, payload, expected):
        res = await persist_series(_Conn(), payload, source="warmer")
        assert res["skipped"] is True
        assert res["skip_reason"] == expected
        assert res["rows_touched"] == 0

    def test_the_taxonomy_is_enumerated(self):
        assert len(SKIP) >= 5
        assert all(isinstance(s, str) and ":" in s for s in SKIP)

    @pytest.mark.asyncio
    async def test_a_skip_writes_nothing(self):
        """POSITIVE CONTROL. A skip that still wrote would be worse than no skip at all."""
        conn = _Conn()
        await persist_series(conn, {"data": []}, source="warmer")
        assert conn.calls == []


class TestFieldLivenessIsDeclaredAndEnforced:
    def test_the_declaration_exists_with_its_measurement(self):
        assert FIELD_LIVENESS["expected_interval_s"] == 300
        # A RANGE, corrected after the backfill measured a 16:15 ET tick on 19 of 66 sessions.
        assert FIELD_LIVENESS["expected_rows_per_complete_session"] == (81, 82)
        assert "16:15" in FIELD_LIVENESS["rows_note"]
        assert set(FIELD_LIVENESS["fields"]) == {"net_call_premium", "net_put_premium",
                                                 "net_volume"}
        assert "2026-10" in FIELD_LIVENESS["measured_on"]

    def test_a_complete_session_reports_the_declared_interval(self):
        ticks = [parse_tick(r) for r in _series(81)]
        rep = liveness_report(ticks)
        assert rep["rows"] == 81
        assert rep["complete"] is True
        assert rep["distinct_intervals_s"] == [300]
        assert rep["interval_as_declared"] is True

    @pytest.mark.asyncio
    async def test_a_complete_session_missing_a_declared_field_HALTS(self):
        res = await persist_series(_Conn(), {"data": _series(81, drop=("net_volume",))},
                                   source="warmer")
        assert res["skipped"] is True
        assert res["skip_reason"].startswith("HALT:")
        assert "net_volume" in res["skip_reason"]
        assert res["rows_touched"] == 0

    @pytest.mark.asyncio
    async def test_a_SHORT_poll_missing_a_field_does_NOT_halt(self):
        """POSITIVE CONTROL, and the subtle half. A 2-row mid-session poll cannot satisfy a
        95% rate in any meaningful sense, so halting on it would make the floor unsatisfiable
        by construction -- which is the defect §5.3 is written against, not an application of
        it. The floor binds only once the series is long enough to mean something."""
        res = await persist_series(_Conn(), {"data": _series(3, drop=("net_volume",))},
                                   source="warmer")
        assert res["skipped"] is False
        assert res["written"] == 3


class TestTheCollectorIsObservable:
    def test_the_tide_loop_runs_under_the_liveness_wrapper(self):
        """§5.1. A collector that goes dark must show as a flatlined job in /health, not as a
        table nobody thought to query -- DEF-TRITON-GRADER-DARK is exactly that failure."""
        src = _code("jobs/stable_jobs.py")
        # `_record` is the helper's REAL name -- all fifteen call sites use it. This assertion
        # said `_run_job`, a function that exists nowhere, so it matched the text I had just
        # written and the test agreed with the bug. The Tide cell was dark from the open on
        # 2026-10-07 because of it. The real guard is now
        # tests/test_tide_warmer_actually_runs.py, which runs a cycle and checks the cell;
        # this line only pins the wiring.
        assert '_record("market_tide", _warm_tide)' in src
        assert "_run_job" not in src, "there is no _run_job; calling one is a NameError at runtime"

    def test_the_warmer_persists_before_it_reduces_to_the_last_row(self):
        src = _code("jobs/stable_jobs.py")
        i = src.index("async def _warm_tide")
        body = src[i:src.index("\nasync def ", i + 10)]
        assert "persist_series(conn, raw, source=\"warmer\")" in body
        assert body.index("persist_series") < body.index("td = raw.get(\"data\", raw)")

    def test_a_failed_write_does_not_take_the_warmed_cell_down(self):
        """The v2 tide cell is what the principal reads. A failed WRITE is not a reason to
        withhold a good READING."""
        src = _code("jobs/stable_jobs.py")
        i = src.index("async def _warm_tide")
        body = src[i:src.index("\nasync def ", i + 10)]
        assert "market_tide_history write failed" in body
        assert "setex(\"board:tide:latest\"" in body

    def test_the_dated_fetch_is_not_cached_into_the_live_key(self):
        """The live reader's cache is keyed on "market" alone. Writing a dated series into it
        would serve yesterday's tide as today's."""
        src = _code("integrations/uw_api.py")
        i = src.index("async def get_market_tide_for_date")
        # Bounded to THIS function: a fixed window ran past it into get_darkpool_ticker and
        # caught that function's cache_set, so the assertion was about the wrong code.
        body = src[i:src.index("\nasync def ", i + 10)]
        assert "cache_set" not in body
        assert 'caller="market_tide_backfill"' in body
