"""
Analytics endpoint shape tests — verify endpoints return expected data structures.

Brief 3E — ensures Oracle, risk budget, and weekly reports return valid shapes.
"""
import pytest


@pytest.fixture
def auth(test_api_key):
    """These are SHAPE tests. Analytics reads require auth (R-IV.417); auth itself is
    tested in test_auth.py, so every request here carries a valid key."""
    return {"X-API-Key": test_api_key}


class TestOracleEndpoint:
    """The Oracle endpoint returns expected payload shape."""

    def test_oracle_returns_expected_keys(self, client, auth):
        resp = client.get("/api/analytics/oracle?days=30", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "system_health" in data
        assert "strategy_scorecards" in data
        assert "decision_quality" in data

    def test_oracle_system_health_shape(self, client, auth):
        resp = client.get("/api/analytics/oracle?days=7", headers=auth)
        assert resp.status_code == 200
        health = resp.json().get("system_health", {})
        for key in ("win_rate", "total_trades", "trajectory"):
            assert key in health, f"Missing system_health.{key}"

    def test_oracle_accepts_asset_class_filter(self, client, auth):
        resp = client.get("/api/analytics/oracle?days=30&asset_class=EQUITY", headers=auth)
        assert resp.status_code == 200

        resp = client.get("/api/analytics/oracle?days=30&asset_class=CRYPTO", headers=auth)
        assert resp.status_code == 200


class TestRiskBudgetEndpoint:
    """Risk budget returns equity and crypto sections."""

    def test_risk_budget_returns_sections(self, client, auth):
        resp = client.get("/api/analytics/risk-budget", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "equity" in data
        assert "crypto" in data
        assert "combined" in data

    def test_risk_budget_crypto_has_breakout_fields(self, client, auth):
        resp = client.get("/api/analytics/risk-budget", headers=auth)
        assert resp.status_code == 200
        crypto = resp.json().get("crypto", {})
        assert "max_concurrent" in crypto
        assert "can_open_new" in crypto


class TestWeeklyReportsEndpoint:
    """Weekly reports endpoint returns list."""

    def test_weekly_reports_returns_list(self, client, auth):
        resp = client.get("/api/analytics/weekly-reports", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "reports" in data
        assert isinstance(data["reports"], list)


class TestSignalStatsEndpoint:
    """Signal stats endpoint accepts filters."""

    def test_signal_stats_with_source_filter(self, client, auth):
        resp = client.get("/api/analytics/signal-stats?source=Holy_Grail&days=30", headers=auth)
        assert resp.status_code == 200
