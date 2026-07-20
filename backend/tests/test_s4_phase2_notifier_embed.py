"""S-4 Phase 2 -- scripts/signal_notifier.py's crypto embed additions
(fetch_crypto_state, post_crypto_signal_alert's 4 new gap fields).

signal_notifier.py lives outside backend/ (a standalone VPS script), so
this test file imports it directly via a sys.path insert rather than the
usual backend.* import style. No live HTTP calls -- http_json is mocked.
"""

import json
import sys
import os
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import signal_notifier as sn  # noqa: E402

_STATE_LIVE = {
    "symbol": "BTC",
    "tier": 1,
    "regime": {"state": "CHOP", "degraded": False},
    "session": {"partition": "LONDON", "degraded": False},
    "funding": {"rate_pct": 0.0123, "degraded": False},
    "liquidations": {"total_usd": 7_000_000, "long_pct": 71.4, "degraded": False},
    "atr": {"atr": 412.5, "degraded": False},
}

_SIGNAL = {
    "ticker": "BTC",
    "direction": "LONG",
    "score": 75,
    "strategy": "CVD_ABSORPTION",
    "entry_price": 62500.0,
    "stop_loss": 62200.0,
    "target_1": 63000.0,
    "enrichment_data": json.dumps({}),
}


def _discord_ok_response(url, method="GET", headers=None, payload=None, timeout=30):
    if "/crypto/state/" in url:
        return dict(_STATE_LIVE)
    return {"id": "123", "ok": True}  # simulated Discord response


# ---------------------------------------------------------------------------
# fetch_crypto_state
# ---------------------------------------------------------------------------

def test_fetch_crypto_state_returns_parsed_json():
    with patch.object(sn, "http_json", side_effect=_discord_ok_response):
        result = sn.fetch_crypto_state("https://hub/api", "BTC")
    assert result["tier"] == 1


def test_fetch_crypto_state_honest_none_on_failure():
    with patch.object(sn, "http_json", side_effect=RuntimeError("network down")):
        result = sn.fetch_crypto_state("https://hub/api", "BTC")
    assert result is None


# ---------------------------------------------------------------------------
# post_crypto_signal_alert -- new gap fields
# ---------------------------------------------------------------------------

def _post_and_capture_embed(state_response, api_url="https://hub/api"):
    captured = {}

    def _fake_http_json(url, method="GET", headers=None, payload=None, timeout=30):
        if "/crypto/state/" in url:
            if state_response is None:
                raise RuntimeError("state fetch failed")
            return state_response
        captured["payload"] = payload
        return {"id": "123"}

    with patch.object(sn, "http_json", side_effect=_fake_http_json):
        sn.post_crypto_signal_alert("tok", "chan", dict(_SIGNAL), "SIG1", api_url)
    return captured["payload"]["embeds"][0]


def test_first_line_regime_session_tier():
    embed = _post_and_capture_embed(_STATE_LIVE)
    first_line = embed["description"].split("\n")[0]
    assert first_line == "**CHOP | LONDON | Tier 1**"


def test_funding_line_not_double_converted():
    """Regression lock: rate_pct is already a percentage (coinalyze_client
    multiplies by 100 internally) -- must render as 0.0123%, not 1.2300%."""
    embed = _post_and_capture_embed(_STATE_LIVE)
    assert "Funding: +0.0123%/8h" in embed["description"]


def test_liquidations_and_atr_line():
    embed = _post_and_capture_embed(_STATE_LIVE)
    assert "Liq(1h): $7.0M (71% long)" in embed["description"]
    assert "ATR: $412.50" in embed["description"]


def test_degraded_fields_omitted_not_fabricated():
    degraded_state = {
        "symbol": "BTC", "tier": 1,
        "regime": {"state": "CHOP", "degraded": False},
        "session": {"partition": "LONDON", "degraded": False},
        "funding": {"rate_pct": None, "degraded": True},
        "liquidations": {"total_usd": None, "degraded": True},
        "atr": {"atr": None, "degraded": True},
    }
    embed = _post_and_capture_embed(degraded_state)
    assert "Funding:" not in embed["description"]
    assert "Liq(1h):" not in embed["description"]
    assert "ATR:" not in embed["description"]
    # First line still renders using what IS available
    assert "CHOP | LONDON | Tier 1" in embed["description"]


def test_state_fetch_failure_degrades_gracefully_core_alert_unaffected():
    """If /crypto/state/{ticker} fails entirely, the pre-existing embed
    (entry/stop/target etc.) must still post -- new fields are additive,
    never blocking, matching the FA-4-equivalent constraint (Sec3.5)."""
    embed = _post_and_capture_embed(None)  # state fetch raises
    assert "Entry: $62,500.00" in embed["description"]
    assert "Funding:" not in embed["description"]
    # No crash, no exception propagated -- proven by reaching this assert


def test_no_api_url_skips_state_fetch_entirely():
    captured = {}

    def _fake_http_json(url, method="GET", headers=None, payload=None, timeout=30):
        assert "/crypto/state/" not in url, "state should never be fetched when api_url is empty"
        captured["payload"] = payload
        return {"id": "123"}

    with patch.object(sn, "http_json", side_effect=_fake_http_json):
        sn.post_crypto_signal_alert("tok", "chan", dict(_SIGNAL), "SIG1", api_url="")
    embed = captured["payload"]["embeds"][0]
    assert "Entry: $62,500.00" in embed["description"]


def test_pre_existing_embed_fields_unchanged_when_state_present():
    """Regression: R:R/risk, buttons, title, footer all still correct with
    the new fields present -- additive only, nothing displaced or broken."""
    captured = {}

    def _fake_http_json(url, method="GET", headers=None, payload=None, timeout=30):
        if "/crypto/state/" in url:
            return _STATE_LIVE
        captured["payload"] = payload
        return {"id": "123"}

    with patch.object(sn, "http_json", side_effect=_fake_http_json):
        sn.post_crypto_signal_alert("tok", "chan", dict(_SIGNAL), "SIG1", "https://hub/api")
    payload = captured["payload"]
    embed = payload["embeds"][0]
    assert "R:R" in embed["description"]
    assert embed["title"].startswith("\U0001f7e2 LONG BTC | CVD_ABSORPTION")
    assert embed["footer"]["text"] == "Signal ID: SIG1 | Crypto"
    labels = [c["label"] for c in payload["components"][0]["components"]]
    assert labels == ["Take", "Watching", "Pass"]
