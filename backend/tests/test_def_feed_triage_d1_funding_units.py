"""DEF-FEED-TRIAGE D1 -- funding-rate unit fix (bias_filters/coinalyze_client.py)
and the "no FIRING while degraded" contract change (api/crypto_market.py).

Root cause (live-verified 2026-07-20): Coinalyze's /funding-rate "value" field
is ALREADY a percentage (confirmed: raw value=0.001058 for a real ~0.001%/8h
BTC rate, cross-checked against OKX's raw fraction 0.0000121... at the same
moment). OKX's raw fundingRate IS a true fraction and correctly needs *100.
The old code applied *100 to both vendors -- a ~100x inflation for every
Coinalyze-sourced read. Same bug in get_term_structure()'s history-derived
values (same "v" field, same vendor).

No live API calls -- _make_request/_make_okx_request are mocked.
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bias_filters.coinalyze_client import get_funding_rate, get_term_structure


def _run(coro):
    return asyncio.run(coro)


def _clear_cache():
    import bias_filters.coinalyze_client as cc
    cc._cache.clear()


# ---------------------------------------------------------------------------
# get_funding_rate -- Coinalyze primary path (the bug)
# ---------------------------------------------------------------------------

def test_coinalyze_funding_rate_not_multiplied_by_100():
    """Raw Coinalyze value=0.001058 (already a percent) must render as
    0.001058%, not 0.1058% -- regression lock for the live-confirmed bug."""
    _clear_cache()
    coinalyze_response = [{"symbol": "BTCUSD_PERP.A", "value": 0.001058, "update": 1}]
    with patch("bias_filters.coinalyze_client._make_request", new=AsyncMock(return_value=coinalyze_response)), \
         patch("bias_filters.coinalyze_client.record_observation", new=AsyncMock(return_value="LIVE")):
        result = _run(get_funding_rate("BTC"))
    assert result["funding_rate"] == round(0.001058, 4)  # 0.0011 -- code rounds to 4dp
    assert result["source"] == "coinalyze"


def test_coinalyze_funding_rate_realistic_value_reads_neutral():
    """Post-fix sanity (brief D1.6): a real ~0.0016%/8h rate must NOT cross
    the 0.05% FIRING threshold."""
    _clear_cache()
    coinalyze_response = [{"symbol": "BTCUSD_PERP.A", "value": 0.0016, "update": 1}]
    with patch("bias_filters.coinalyze_client._make_request", new=AsyncMock(return_value=coinalyze_response)), \
         patch("bias_filters.coinalyze_client.record_observation", new=AsyncMock(return_value="LIVE")):
        result = _run(get_funding_rate("ETH"))
    assert result["signal"] == "NEUTRAL"
    assert result["sentiment"] == "neutral"


def test_coinalyze_funding_rate_predicted_not_multiplied():
    _clear_cache()
    coinalyze_response = [{"symbol": "BTCUSD_PERP.A", "value": 0.001, "predictedValue": 0.0012, "update": 1}]
    with patch("bias_filters.coinalyze_client._make_request", new=AsyncMock(return_value=coinalyze_response)), \
         patch("bias_filters.coinalyze_client.record_observation", new=AsyncMock(return_value="LIVE")):
        result = _run(get_funding_rate("SOL"))
    assert result["predicted_rate"] == 0.0012


# ---------------------------------------------------------------------------
# get_funding_rate -- OKX fallback path (must stay unchanged -- true fraction)
# ---------------------------------------------------------------------------

def test_okx_fallback_funding_rate_still_multiplied_by_100():
    """OKX's raw fundingRate is a genuine fraction (confirmed live:
    0.0000121883658011 = 0.00121883658011%) -- *100 here is correct and
    must NOT be touched by the Coinalyze-side fix."""
    _clear_cache()
    okx_response = {"code": "0", "data": [{"fundingRate": "0.0000121883658011", "nextFundingRate": ""}]}
    with patch("bias_filters.coinalyze_client._make_request", new=AsyncMock(return_value=None)), \
         patch("bias_filters.coinalyze_client._make_okx_request", new=AsyncMock(return_value=okx_response)), \
         patch("bias_filters.coinalyze_client.record_observation", new=AsyncMock(return_value="LIVE")):
        result = _run(get_funding_rate("BTC"))
    assert result["funding_rate"] == 0.0012
    assert result["source"] == "okx_fallback"


# ---------------------------------------------------------------------------
# get_term_structure -- Coinalyze primary path (same bug, same file)
# ---------------------------------------------------------------------------

def test_coinalyze_term_structure_not_multiplied_by_100():
    _clear_cache()
    history_response = [{
        "symbol": "BTCUSD_PERP.A",
        "history": [{"v": 0.001}, {"v": 0.0012}, {"v": 0.0009}],
    }]
    with patch("bias_filters.coinalyze_client._make_request", new=AsyncMock(return_value=history_response)), \
         patch("bias_filters.coinalyze_client.record_observation", new=AsyncMock(return_value="LIVE")):
        result = _run(get_term_structure("BTC"))
    assert result["current_funding"] == 0.0009
    # avg of 0.001, 0.0012, 0.0009 = 0.0010333... rounded 4dp
    assert result["avg_funding_24h"] == round((0.001 + 0.0012 + 0.0009) / 3, 4)
    # Realistic magnitude must stay well under the 0.02/-0.01 structure
    # thresholds -- proves the fix, not just the arithmetic in isolation.
    assert result["structure"] == "flat"


def test_okx_fallback_term_structure_still_multiplied_by_100():
    _clear_cache()
    okx_history = {"code": "0", "data": [
        {"fundingRate": "0.0000100000000000"},
        {"fundingRate": "0.0000110000000000"},
    ]}
    with patch("bias_filters.coinalyze_client._make_request", new=AsyncMock(return_value=None)), \
         patch("bias_filters.coinalyze_client._make_okx_request", new=AsyncMock(return_value=okx_history)), \
         patch("bias_filters.coinalyze_client.record_observation", new=AsyncMock(return_value="LIVE")):
        result = _run(get_term_structure("BTC"))
    assert result["source"] == "okx_fallback"
    # fractions * 100 -> ~0.001% range, not zeroed or 100x'd
    assert 0.0009 < result["current_funding"] < 0.0012


# ---------------------------------------------------------------------------
# D1.4 contract change: no FIRING while degraded (api/crypto_market.py)
# ---------------------------------------------------------------------------

def test_funding_field_suppresses_firing_when_degraded():
    from api.crypto_market import get_crypto_state

    degraded_firing = {
        "funding_rate": 1.0, "signal": "FIRING", "sentiment": "overleveraged_longs",
        "source": "coinalyze", "symbol": "BTC", "timestamp": "2026-07-20T14:05:00Z",
        "health_status": "DEGRADED",
    }

    async def _run_it():
        with patch("bias_filters.coinalyze_client.get_funding_rate", new=AsyncMock(return_value=degraded_firing)), \
             patch("bias_filters.coinalyze_client.get_open_interest", new=AsyncMock(return_value={"state": "NA", "reason": "t"})), \
             patch("bias_filters.binance_client.get_quarterly_basis", new=AsyncMock(return_value={"state": "NA", "reason": "t"})), \
             patch("config.crypto_gate_loader.get_gate_config", new=AsyncMock(return_value=(1, {"partition_utc": {}}))), \
             patch("utils.crypto_sessions.get_session_state", return_value={"current_session": None, "label": None, "partition": None}), \
             patch("database.postgres_client.get_postgres_client", new=AsyncMock(side_effect=RuntimeError("no db in unit test"))), \
             patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=[])), \
             patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value={"state": "NA", "reason": "t"})):
            return await get_crypto_state("BTC")

    result = asyncio.run(_run_it())
    funding = result["funding"]
    assert funding["degraded"] is True
    assert funding["signal"] == "NEUTRAL"  # suppressed, not FIRING
    assert funding["rate_pct"] == 1.0  # raw value still surfaced, just not actioned


def test_funding_field_preserves_firing_when_not_degraded():
    """Regression: a genuinely healthy FIRING reading must NOT be suppressed."""
    from api.crypto_market import get_crypto_state

    healthy_firing = {
        "funding_rate": 0.08, "signal": "FIRING", "sentiment": "overleveraged_longs",
        "source": "coinalyze", "symbol": "BTC", "timestamp": "2026-07-20T14:05:00Z",
        "health_status": "LIVE",
    }

    async def _run_it():
        with patch("bias_filters.coinalyze_client.get_funding_rate", new=AsyncMock(return_value=healthy_firing)), \
             patch("bias_filters.coinalyze_client.get_open_interest", new=AsyncMock(return_value={"state": "NA", "reason": "t"})), \
             patch("bias_filters.binance_client.get_quarterly_basis", new=AsyncMock(return_value={"state": "NA", "reason": "t"})), \
             patch("config.crypto_gate_loader.get_gate_config", new=AsyncMock(return_value=(1, {"partition_utc": {}}))), \
             patch("utils.crypto_sessions.get_session_state", return_value={"current_session": None, "label": None, "partition": None}), \
             patch("database.postgres_client.get_postgres_client", new=AsyncMock(side_effect=RuntimeError("no db in unit test"))), \
             patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=[])), \
             patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value={"state": "NA", "reason": "t"})):
            return await get_crypto_state("BTC")

    result = asyncio.run(_run_it())
    funding = result["funding"]
    assert funding["degraded"] is False
    assert funding["signal"] == "FIRING"
