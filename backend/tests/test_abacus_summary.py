"""R-IV.429 — /api/abacus/summary, the Abacus v2 page's data contract (stub).

What these pin down:
  * the route is gated like every book read (R-IV.417), before it ever carries real data;
  * every block carries `source` and `computed_at`, and while mock the whole payload says so;
  * the fixture's computed_at is its AUTHORED instant, never the request time (a mock
    stamped "now" would read as fresh);
  * the range is echoed, and `range_applied` is False while the figures ignore it;
  * rates carry their n, and unknown is None, never 0;
  * the page and its assets are served, and /app/abacus is not swallowed by /app/{mode}.
"""
import pytest
from unittest.mock import AsyncMock, patch

PATH = "/api/abacus/summary"


def _get(client, test_api_key, qs=""):
    return client.get(PATH + qs, headers={"X-API-Key": test_api_key})


LIVE_KEYS = {"net_profit", "win_rate"}


class _FakePool:
    """Records every query so a test can assert the predicate/window, not just the result."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    async def fetch(self, sql, *params):
        self.calls.append((sql, params))
        return self.rows


def _row(pnl, basis=None, basis_incomplete_reason=None):
    return {"realized_pnl": pnl, "cost_basis": basis, "basis_incomplete_reason": basis_incomplete_reason}


@pytest.fixture(autouse=True)
def book_pool():
    """R-IV.484(c) — net_profit/win_rate now read `unified_positions`. Default: an empty book,
    so every test not about the live book gets None/0 there rather than touching conftest's
    unconfigured mock pool. `patch_book(rows)` inside a test overrides this for the duration."""
    pool = _FakePool([])
    with patch("api.abacus.get_postgres_client", new=AsyncMock(return_value=pool)):
        yield pool


def _patch_book(rows):
    pool = _FakePool(rows)
    return pool, patch("api.abacus.get_postgres_client", new=AsyncMock(return_value=pool))


class TestAbacusSummaryGate:
    def test_no_credentials_is_401(self, client):
        assert client.get(PATH).status_code == 401

    def test_wrong_key_is_401(self, client):
        assert client.get(PATH, headers={"X-API-Key": "wrong"}).status_code == 401

    def test_machine_key_accepted(self, client, test_api_key):
        assert _get(client, test_api_key).status_code == 200

    def test_session_cookie_accepted(self, client):
        from utils.session import issue_session, COOKIE_NAME
        token = issue_session()
        assert token
        assert client.get(PATH, cookies={COOKIE_NAME: token}).status_code == 200


class TestAbacusSummaryContract:
    def test_mock_is_declared_everywhere_except_the_live_stats(self, client, test_api_key):
        """net_profit and win_rate went live at R-IV.484(c); everything else stays mock,
        including the discipline breakdown, which has no source columns yet."""
        d = _get(client, test_api_key).json()
        assert d["mock"] is True
        blocks = [d["scope"], d["equity"], d["leaks"], d["strategies"],
                  *(s for s in d["stats"] if s["key"] not in LIVE_KEYS), *d["breakdowns"]]
        assert blocks, "no blocks to check"
        for b in blocks:
            assert b["source"] == "mock", b.get("key") or b.get("label")
            assert b["computed_at"], b.get("key") or b.get("label")

    def test_net_profit_and_win_rate_are_live(self, client, test_api_key):
        from api.abacus import FIXTURE_AUTHORED_AT
        d = _get(client, test_api_key).json()
        for key in LIVE_KEYS:
            s = _stat(d, key)
            assert s["source"] == "live", key
            assert s["computed_at"] and s["computed_at"] != FIXTURE_AUTHORED_AT, key
            assert s["coverage"]["predicate"], key

    def test_computed_at_is_the_authored_instant_not_now(self, client, test_api_key):
        from api.abacus import FIXTURE_AUTHORED_AT
        d = _get(client, test_api_key).json()
        stamps = {d["scope"]["computed_at"], d["equity"]["computed_at"],
                  *(s["computed_at"] for s in d["stats"] if s["key"] not in LIVE_KEYS)}
        assert stamps == {FIXTURE_AUTHORED_AT}

    def test_rates_carry_n(self, client, test_api_key):
        rows = [_row(10.0), _row(-4.0), _row(3.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        win = next(s for s in d["stats"] if s["key"] == "win_rate")
        assert win["format"] == "pct" and win["n"] == 3

    def test_unknown_is_none_not_zero(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        for row in d["strategies"]["rows"]:
            assert row[1:5] == [None, None, None, None], row

    def test_equity_is_self_consistent(self, client, test_api_key):
        """The marked fall equals max drawdown. Both stay mock, so this is still an exact
        equality; net profit went live at R-IV.484(c) and no longer ties to the mock curve."""
        d = _get(client, test_api_key).json()
        pts, dd = d["equity"]["points"], d["equity"]["drawdown"]
        mdd = next(s for s in d["stats"] if s["key"] == "max_drawdown")["value"]
        assert pts[dd["to_index"]] - pts[dd["from_index"]] == dd["amount"] == mdd

    def test_breakdown_rows_match_columns(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        for t in [*d["breakdowns"], d["strategies"]]:
            for row in t["rows"]:
                assert len(row) == len(t["columns"]), (t.get("key"), row)

    def test_fixture_is_not_mutated_across_requests(self, client, test_api_key):
        _get(client, test_api_key, "?from=2026-01-01&to=2026-02-01")
        d = _get(client, test_api_key).json()
        assert d["range"]["key"] == "90d"


class TestAbacusSummaryRange:
    @pytest.mark.parametrize("key", ["30d", "90d", "ytd", "all"])
    def test_preset_is_echoed(self, client, test_api_key, key):
        d = _get(client, test_api_key, f"?range={key}").json()
        assert d["range"]["key"] == key
        assert d["range_applied"] is True

    def test_all_has_no_start(self, client, test_api_key):
        assert _get(client, test_api_key, "?range=all").json()["range"]["from"] is None

    def test_explicit_dates_win(self, client, test_api_key):
        d = _get(client, test_api_key, "?range=30d&from=2026-06-18&to=2026-09-16").json()
        assert d["range"] == {"key": "custom", "from": "2026-06-18", "to": "2026-09-16"}

    def test_bad_range_is_rejected(self, client, test_api_key):
        assert _get(client, test_api_key, "?range=7y").status_code == 422

    def test_inverted_dates_are_rejected(self, client, test_api_key):
        assert _get(client, test_api_key, "?from=2026-09-16&to=2026-06-18").status_code == 422


def _stat(d, key):
    return next(s for s in d["stats"] if s["key"] == key)


QUERIES = ["?range=30d", "?range=90d", "?range=ytd", "?range=all",
           "?from=2026-09-10&to=2026-09-11", "?from=2020-01-01&to=2020-02-01",
           "?from=2025-01-01&to=2026-09-16"]


class TestAbacusSummaryScaling:
    """Charter D2: the range changes the figures, server-side, and every range stays coherent."""

    def test_figures_change_with_the_range(self, client, test_api_key):
        """net_profit went live at R-IV.484(c) and no longer scales with the mock window;
        max_drawdown is still mock and still tracks the fixture's scaling rule."""
        dd = {q: _stat(_get(client, test_api_key, q).json(), "max_drawdown")["value"] for q in QUERIES[:4]}
        assert len(set(dd.values())) == 4, dd
        assert dd["?range=30d"] > dd["?range=90d"] > dd["?range=ytd"] > dd["?range=all"]

    def test_90d_is_the_base_fixture(self, client, test_api_key):
        d = _get(client, test_api_key, "?range=90d").json()
        assert _stat(d, "max_drawdown")["value"] == -1140
        assert d["scope"]["closed_positions"] == 249

    @pytest.mark.parametrize("q", QUERIES)
    def test_every_range_is_self_consistent(self, client, test_api_key, q):
        d = _get(client, test_api_key, q).json()
        pts, dd = d["equity"]["points"], d["equity"]["drawdown"]
        assert pts[dd["to_index"]] - pts[dd["from_index"]] == dd["amount"] == _stat(d, "max_drawdown")["value"]
        assert d["scope"]["closed_positions"] >= 1

    @pytest.mark.parametrize("q", QUERIES)
    def test_rates_do_not_scale(self, client, test_api_key, q):
        """win_rate went live at R-IV.484(c); profit_factor and expectancy stay mock and
        still hold at every range."""
        d = _get(client, test_api_key, q).json()
        assert _stat(d, "profit_factor")["value"] == 1.4
        assert _stat(d, "expectancy")["value"] == 6.30
        structure = next(b for b in d["breakdowns"] if b["key"] == "structure")
        assert [r[2] for r in structure["rows"]] == [0.58, 0.67, 0.49, 0.43, 0.42, 0.0]

    @pytest.mark.parametrize("q", QUERIES)
    def test_counts_stay_whole_and_positive(self, client, test_api_key, q):
        d = _get(client, test_api_key, q).json()
        for it in d["leaks"]["items"]:
            assert isinstance(it["n"], int) and it["n"] >= 1
        for b in d["breakdowns"]:
            for i, (_, kind) in enumerate(b["columns"]):
                if kind == "int":
                    assert all(isinstance(r[i], int) and r[i] >= 1 for r in b["rows"]), (q, b["key"])

    @pytest.mark.parametrize("q", QUERIES)
    def test_drawdown_is_dated_inside_the_window(self, client, test_api_key, q):
        d = _get(client, test_api_key, q).json()
        eq = d["equity"]
        assert eq["from"] <= eq["drawdown"]["date"] <= eq["to"]
        assert _stat(d, "max_drawdown")["date"] == eq["drawdown"]["date"]

    def test_unknown_stays_none_at_every_range(self, client, test_api_key):
        for q in QUERIES:
            for row in _get(client, test_api_key, q).json()["strategies"]["rows"]:
                assert row[1:5] == [None, None, None, None], (q, row)

    def test_version_is_declared(self, client, test_api_key):
        from api.abacus import SUMMARY_VERSION
        assert _get(client, test_api_key).json()["version"] == SUMMARY_VERSION == 1

    def test_leak_prose_carries_no_counts(self, client, test_api_key):
        """Counts live in `n` (R2); a count inside the prose would not scale with the range."""
        import re
        for it in _get(client, test_api_key, "?range=30d").json()["leaks"]["items"]:
            assert not re.search(r"\b\d+\s+(adds|bought|held past|with no)\b", it["detail"]), it["detail"]


class TestAbacusLiveBook:
    """R-IV.484(c): net_profit and win_rate read the book. Census predicate
    LOWER(status) IN ('closed','expired'), windowed on exit_date; basis-incomplete and
    sub -100%-of-basis rows are counted but never averaged in; a book that never recorded
    realized_pnl on a row is excluded the same way, never treated as a $0 trade."""

    def test_empty_book_is_null_not_zero(self, client, test_api_key):
        """The default fixture (no rows) -- unknown must read null, never 0.00 or 0%."""
        d = _get(client, test_api_key).json()
        net, win = _stat(d, "net_profit"), _stat(d, "win_rate")
        assert net["value"] is None and win["value"] is None
        assert win["n"] == 0
        assert net["coverage"] == win["coverage"] == {
            "predicate": "LOWER(status) IN ('closed','expired'), windowed on exit_date",
            "total": 0, "counted": 0,
            "excluded": {"basis_incomplete": 0, "return_below_neg100pct": 0, "no_realized_pnl": 0},
        }

    def test_counted_rows_sum_and_win_rate(self, client, test_api_key):
        rows = [_row(100.0), _row(-40.0), _row(0.0), _row(25.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net, win = _stat(d, "net_profit"), _stat(d, "win_rate")
        assert net["value"] == 85.0
        assert win["n"] == 4 and win["value"] == 0.5  # 2 of 4 strictly positive
        assert net["coverage"]["total"] == net["coverage"]["counted"] == 4

    def test_basis_incomplete_rows_are_excluded_not_averaged_in(self, client, test_api_key):
        rows = [_row(100.0), _row(9999.0, basis_incomplete_reason="R-IV.456(a) third leg unrecorded")]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net = _stat(d, "net_profit")
        assert net["value"] == 100.0, "the flagged 9999 must not land in the sum"
        assert net["coverage"]["total"] == 2
        assert net["coverage"]["counted"] == 1
        assert net["coverage"]["excluded"]["basis_incomplete"] == 1

    def test_return_below_neg100pct_is_excluded_not_averaged_in(self, client, test_api_key):
        # -150 on a 100 basis is a -150% return: past total loss, a data-integrity signal.
        rows = [_row(50.0, basis=200.0), _row(-150.0, basis=100.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net = _stat(d, "net_profit")
        assert net["value"] == 50.0
        assert net["coverage"]["excluded"]["return_below_neg100pct"] == 1

    def test_return_exactly_neg100pct_is_not_flagged(self, client, test_api_key):
        """A full loss of the stated basis is a real result, not a data-integrity signal --
        only a return that overshoots -100% is impossible and gets flagged."""
        rows = [_row(-100.0, basis=100.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net = _stat(d, "net_profit")
        assert net["value"] == -100.0
        assert net["coverage"]["excluded"]["return_below_neg100pct"] == 0

    def test_unrecorded_realized_pnl_is_excluded_not_zero(self, client, test_api_key):
        """A closed row with no realized_pnl at all is the book never having recorded it --
        excluded from both the sum and the win-rate denominator, never counted as a $0 loss."""
        rows = [_row(60.0), _row(None)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net, win = _stat(d, "net_profit"), _stat(d, "win_rate")
        assert net["value"] == 60.0
        assert win["n"] == 1
        assert net["coverage"]["excluded"]["no_realized_pnl"] == 1

    def test_return_check_is_skipped_without_a_basis(self, client, test_api_key):
        """A row with a real realized_pnl but no cost_basis to divide by can't have its return
        checked -- it must still count (nothing here says it's wrong), not be silently dropped."""
        rows = [_row(-9000.0, basis=None)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net = _stat(d, "net_profit")
        assert net["value"] == -9000.0
        assert net["coverage"]["counted"] == 1
        assert net["coverage"]["excluded"]["return_below_neg100pct"] == 0

    def test_predicate_and_window(self, client, test_api_key):
        pool, p = _patch_book([])
        with p:
            _get(client, test_api_key, "?from=2026-06-18&to=2026-09-16")
        sql, params = pool.calls[-1]
        assert "LOWER(status) IN ('closed', 'expired')" in sql
        assert "exit_date" in sql
        from datetime import date
        assert params == (date(2026, 9, 16), date(2026, 6, 18))

    def test_all_range_has_no_lower_bound_on_the_query(self, client, test_api_key):
        """range=all must not clamp to the mock book's fake start date -- that's a fixture-only
        artifact and has no place gating a real query."""
        pool, p = _patch_book([])
        with p:
            _get(client, test_api_key, "?range=all")
        sql, params = pool.calls[-1]
        assert len(params) == 1, "no lower-bound param when the range is open-ended"


class TestAbacusPageServed:
    @pytest.mark.parametrize("path,needle", [
        ("/app/abacus", b"abacus.js"),
        ("/abacus.css", b".ab-page"),
        ("/abacus.js", b"/api/abacus/summary"),
    ])
    def test_served(self, client, path, needle):
        r = client.get(path)
        assert r.status_code == 200, path
        assert needle in r.content, path

    def test_abacus_route_beats_the_catch_all(self, client):
        """/app/{mode} serves legacy index.html; /app/abacus must not be swallowed by it."""
        body = client.get("/app/abacus").content
        assert b"abacus.js" in body and b"/app.js" not in body

    def test_legacy_analytics_still_legacy(self, client):
        """R-IV.413(a): /app/analytics is not repointed until the replacement is live."""
        body = client.get("/app/analytics").content
        assert b"/app.js" in body
