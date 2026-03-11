"""
Webhook validation tests — verify secret field enforcement.

Phase 0G — TradingView webhooks must include the correct secret.
"""
import pytest


class TestTradingViewWebhookSecret:
    """TradingView webhook secret validation."""

    WEBHOOK_ENDPOINTS = [
        (
            "/webhook/tradingview",
            {
                "ticker": "SPY",
                "strategy": "test",
                "direction": "LONG",
                "interval": "15",
                "price": "590.50",
            },
        ),
    ]

    @pytest.mark.parametrize("path,payload", WEBHOOK_ENDPOINTS)
    def test_wrong_secret_rejected(self, client, path, payload):
        payload_with_bad_secret = {**payload, "secret": "wrong-secret"}
        response = client.post(path, json=payload_with_bad_secret)
        assert response.status_code == 401

    @pytest.mark.parametrize("path,payload", WEBHOOK_ENDPOINTS)
    def test_correct_secret_accepted(self, client, webhook_secret, path, payload):
        payload_with_secret = {**payload, "secret": webhook_secret}
        response = client.post(path, json=payload_with_secret)
        assert response.status_code != 401

    @pytest.mark.parametrize("path,payload", WEBHOOK_ENDPOINTS)
    def test_missing_secret_rejected(self, client, path, payload):
        response = client.post(path, json=payload)
        assert response.status_code == 401
