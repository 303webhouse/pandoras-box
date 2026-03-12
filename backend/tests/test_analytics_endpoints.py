"""
Analytics endpoint shape tests — verify endpoints return expected data structures.

Brief 3E — ensures Oracle, risk budget, and weekly reports return valid shapes.
"""
import pytest


class TestOracleEndpoint:
    """The Oracle endpoint returns expected payload shape."""

    def test_oracle_returns_expected_keys(self, client):
        resp = client.get("/api/analytics/oracle?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "system_health" in data
        assert "strategy_scorecards" in data
        assert "decision_quality" in data

    def test_oracle_system_health_shape(self, client):
        resp = client.get("/api/analytics/oracle?days=7")
        assert resp.status_code == 200
        health = resp.json().get("system_health", {})
        for key in ("win_rate", "total_trades", "trajectory"):
            assert key in health, f"Missing system_health.{key}"

    def test_oracle_accepts_asset_class_filter(self, client):
        resp = client.get("/api/analytics/oracle?days=30&asset_class=EQUITY")
        assert resp.status_code == 200

        resp = client.get("/api/analytics/oracle?days=30&asset_class=CRYPTO")
        assert resp.status_code == 200


class TestRiskBudgetEndpoint:
    """Risk budget returns equity and crypto sections."""

    def test_risk_budget_returns_sections(self, client):
        resp = client.get("/api/analytics/risk-budget")
        assert resp.status_code == 200
        data = resp.json()
        assert "equity" in data
        assert "crypto" in data
        assert "combined" in data

    def test_risk_budget_crypto_has_breakout_fields(self, client):
        resp = client.get("/api/analytics/risk-budget")
        assert resp.status_code == 200
        crypto = resp.json().get("crypto", {})
        assert "max_concurrent" in crypto
        assert "can_open_new" in crypto


class TestWeeklyReportsEndpoint:
    """Weekly reports endpoint returns list."""

    def test_weekly_reports_returns_list(self, client):
        resp = client.get("/api/analytics/weekly-reports")
        assert resp.status_code == 200
        data = resp.json()
        assert "reports" in data
        assert isinstance(data["reports"], list)


class TestSignalStatsEndpoint:
    """Signal stats endpoint accepts filters."""

    def test_signal_stats_with_source_filter(self, client):
        resp = client.get("/api/analytics/signal-stats?source=Holy_Grail&days=30")
        assert resp.status_code == 200
