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
        assert d["range_applied"] is False

    def test_all_has_no_start(self, client, test_api_key):
        assert _get(client, test_api_key, "?range=all").json()["range"]["from"] is None

    def test_explicit_dates_win(self, client, test_api_key):
        d = _get(client, test_api_key, "?range=30d&from=2026-06-18&to=2026-09-16").json()
        assert d["range"] == {"key": "custom", "from": "2026-06-18", "to": "2026-09-16"}

    def test_bad_range_is_rejected(self, client, test_api_key):
        assert _get(client, test_api_key, "?range=7y").status_code == 422


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
