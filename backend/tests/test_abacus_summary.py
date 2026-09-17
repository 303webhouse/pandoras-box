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

PATH = "/api/abacus/summary"


def _get(client, test_api_key, qs=""):
    return client.get(PATH + qs, headers={"X-API-Key": test_api_key})


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
    def test_mock_is_declared_everywhere(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        assert d["mock"] is True
        blocks = [d["scope"], d["equity"], d["leaks"], d["strategies"], *d["stats"], *d["breakdowns"]]
        assert blocks, "no blocks to check"
        for b in blocks:
            assert b["source"] == "mock", b.get("key") or b.get("label")
            assert b["computed_at"], b.get("key") or b.get("label")

    def test_computed_at_is_the_authored_instant_not_now(self, client, test_api_key):
        from api.abacus import FIXTURE_AUTHORED_AT
        d = _get(client, test_api_key).json()
        stamps = {d["scope"]["computed_at"], d["equity"]["computed_at"], *(s["computed_at"] for s in d["stats"])}
        assert stamps == {FIXTURE_AUTHORED_AT}

    def test_rates_carry_n(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        win = next(s for s in d["stats"] if s["key"] == "win_rate")
        assert win["format"] == "pct" and win["n"] == 249

    def test_unknown_is_none_not_zero(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        for row in d["strategies"]["rows"]:
            assert row[1:5] == [None, None, None, None], row

    def test_equity_is_self_consistent(self, client, test_api_key):
        """Start-to-end equals net profit; the marked fall equals max drawdown."""
        d = _get(client, test_api_key).json()
        pts, dd = d["equity"]["points"], d["equity"]["drawdown"]
        net = next(s for s in d["stats"] if s["key"] == "net_profit")["value"]
        mdd = next(s for s in d["stats"] if s["key"] == "max_drawdown")["value"]
        assert pts[-1] - pts[0] == net
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
        net = {q: _stat(_get(client, test_api_key, q).json(), "net_profit")["value"] for q in QUERIES[:4]}
        assert len(set(net.values())) == 4, net
        assert net["?range=30d"] < net["?range=90d"] < net["?range=ytd"] < net["?range=all"]

    def test_90d_is_the_base_fixture(self, client, test_api_key):
        d = _get(client, test_api_key, "?range=90d").json()
        assert _stat(d, "net_profit")["value"] == 1573
        assert _stat(d, "max_drawdown")["value"] == -1140
        assert d["scope"]["closed_positions"] == 249

    @pytest.mark.parametrize("q", QUERIES)
    def test_every_range_is_self_consistent(self, client, test_api_key, q):
        d = _get(client, test_api_key, q).json()
        pts, dd = d["equity"]["points"], d["equity"]["drawdown"]
        assert pts[-1] - pts[0] == _stat(d, "net_profit")["value"]
        assert pts[dd["to_index"]] - pts[dd["from_index"]] == dd["amount"] == _stat(d, "max_drawdown")["value"]
        assert _stat(d, "win_rate")["n"] == d["scope"]["closed_positions"] >= 1

    @pytest.mark.parametrize("q", QUERIES)
    def test_rates_do_not_scale(self, client, test_api_key, q):
        d = _get(client, test_api_key, q).json()
        assert _stat(d, "win_rate")["value"] == 0.54
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
