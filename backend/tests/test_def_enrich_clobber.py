"""DEF-ENRICH-CLOBBER fix tests (backend/enrichment/signal_enricher.py).

enrich_signal() previously ran unconditionally for every signal and
wholesale-replaced enrichment_data, destroying producer-built keys
(cvd_*, market_structure) and routing CRYPTO tickers through the equity
lookup stack. Fixed: CRYPTO early-return before any fetch (Task 1.1),
merge-don't-clobber at the write site (Task 1.2), DB-side merge +
str-safe payload in persist_enrichment (Task 1.3).

No live API calls or database access -- all fetch helpers and the DB pool
are mocked.
"""

import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from enrichment.signal_enricher import enrich_signal, persist_enrichment

# The exact 14 enricher-owned keys (from enrich_signal()'s local `enrichment` dict).
_ENRICHER_OWNED_KEYS = {
    "ticker", "enriched_at", "atr_14", "avg_volume_20d", "iv_rank",
    "iv_rank_uw_shadow", "current_price", "today_volume", "prev_close",
    "change_pct", "rvol", "atr_pct", "risk_in_atr", "sector_3_10",
}


def _run(coro):
    return asyncio.run(coro)


def _equity_fetch_mocks():
    """Patch every fetch dependency enrich_signal() touches for an equity
    ticker, deterministic no-op returns -- isolates the merge/gate logic
    from live network behavior."""
    return (
        patch("enrichment.universe_cache.get_universe_data", new=AsyncMock(return_value=None)),
        patch("enrichment.signal_enricher._fetch_uw_iv_rank_shadow", new=AsyncMock(return_value=None)),
        patch("enrichment.signal_enricher._fetch_snapshot", new=AsyncMock(return_value=None)),
        patch("indicators.sector_rotation_3_10.get_sector_3_10_for_ticker", new=AsyncMock(return_value=None)),
    )


# ---------------------------------------------------------------------------
# (a) CRYPTO early-return
# ---------------------------------------------------------------------------

def test_crypto_early_return_unchanged_and_no_fetch():
    signal_data = {
        "ticker": "BTC",
        "asset_class": "CRYPTO",
        "enrichment_data": {"cvd_level": "POC", "cvd_net": 5000.0},
    }
    p_universe, p_iv, p_snap, p_sector = _equity_fetch_mocks()
    with p_universe as m_universe, p_iv as m_iv, p_snap as m_snap, p_sector as m_sector:
        result = _run(enrich_signal(dict(signal_data)))

    assert result["enrichment_data"] == {"cvd_level": "POC", "cvd_net": 5000.0}
    assert "enriched_at" not in result
    m_universe.assert_not_called()
    m_iv.assert_not_called()
    m_snap.assert_not_called()
    m_sector.assert_not_called()


def test_crypto_early_return_no_enricher_keys_added():
    signal_data = {"ticker": "ETH", "asset_class": "CRYPTO", "enrichment_data": {}}
    p_universe, p_iv, p_snap, p_sector = _equity_fetch_mocks()
    with p_universe, p_iv, p_snap, p_sector:
        result = _run(enrich_signal(dict(signal_data)))
    assert not (_ENRICHER_OWNED_KEYS & set(result["enrichment_data"].keys()))


# ---------------------------------------------------------------------------
# (b) Equity merge preserves producer/pipeline keys
# ---------------------------------------------------------------------------

def test_equity_merge_preserves_producer_and_pipeline_flags():
    signal_data = {
        "ticker": "AAPL",
        "asset_class": "EQUITY",
        "score": 60,
        "enrichment_data": {"needs_structural_review": True, "custom_x": 1},
    }
    p_universe, p_iv, p_snap, p_sector = _equity_fetch_mocks()
    with p_universe, p_iv, p_snap, p_sector:
        result = _run(enrich_signal(dict(signal_data)))

    enrichment = result["enrichment_data"]
    assert enrichment["needs_structural_review"] is True
    assert enrichment["custom_x"] == 1
    assert enrichment["ticker"] == "AAPL"
    assert "enriched_at" in enrichment


# ---------------------------------------------------------------------------
# (c) Str-form producer enrichment is parsed and preserved
# ---------------------------------------------------------------------------

def test_str_form_enrichment_data_parsed_and_preserved():
    signal_data = {
        "ticker": "MSFT",
        "asset_class": "EQUITY",
        "enrichment_data": json.dumps({"iv_regime_extreme": True, "vix_at_signal": 22.5}),
    }
    p_universe, p_iv, p_snap, p_sector = _equity_fetch_mocks()
    with p_universe, p_iv, p_snap, p_sector:
        result = _run(enrich_signal(dict(signal_data)))

    enrichment = result["enrichment_data"]
    assert isinstance(enrichment, dict)
    assert enrichment["iv_regime_extreme"] is True
    assert enrichment["vix_at_signal"] == 22.5
    assert enrichment["ticker"] == "MSFT"


def test_malformed_str_enrichment_data_does_not_crash():
    """Unparseable JSON string falls back to an empty base dict, not a raise."""
    signal_data = {"ticker": "NVDA", "asset_class": "EQUITY", "enrichment_data": "not json"}
    p_universe, p_iv, p_snap, p_sector = _equity_fetch_mocks()
    with p_universe, p_iv, p_snap, p_sector:
        result = _run(enrich_signal(dict(signal_data)))
    assert result["enrichment_data"]["ticker"] == "NVDA"


# ---------------------------------------------------------------------------
# (d) persist_enrichment: DB-side merge + str-safe payload
# ---------------------------------------------------------------------------

class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _mock_pool():
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


def test_persist_enrichment_sql_has_coalesce_merge():
    pool, conn = _mock_pool()
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
        _run(persist_enrichment("SIG1", {"a": 1}))
    query = conn.execute.call_args.args[0]
    assert "COALESCE(enrichment_data, '{}'::jsonb)" in query
    assert "||" in query


def test_persist_enrichment_dict_input_json_encoded_once():
    pool, conn = _mock_pool()
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
        _run(persist_enrichment("SIG2", {"a": 1}))
    bound_payload = conn.execute.call_args.args[2]
    assert bound_payload == json.dumps({"a": 1})
    assert json.loads(bound_payload) == {"a": 1}


def test_persist_enrichment_str_input_not_double_encoded():
    already_json = json.dumps({"cvd_level": "VAL"})
    pool, conn = _mock_pool()
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
        _run(persist_enrichment("SIG3", already_json))
    bound_payload = conn.execute.call_args.args[2]
    assert bound_payload == already_json  # unchanged, not re-wrapped in quotes
    assert json.loads(bound_payload) == {"cvd_level": "VAL"}


# ---------------------------------------------------------------------------
# (e) score_v2 / feed_tier_classifier_v2 tolerate enricher-keyless dicts
# ---------------------------------------------------------------------------

def test_score_v2_tolerates_enricher_keyless_enrichment():
    from scoring.score_v2 import compute_score_v2
    signal_data = {
        "score": 55,
        "enrichment_data": {"cvd_level": "POC", "cvd_net": 1000.0},  # no rvol/risk_in_atr
    }
    score_v2, factors = compute_score_v2(signal_data)
    assert score_v2 is not None  # does not crash / bail out
    assert factors["rvol"] == {"value": None, "bonus": 0, "note": "enrichment unavailable"}


def test_feed_tier_classifier_v2_tolerates_enricher_keyless_enrichment():
    from scoring.feed_tier_classifier_v2 import _sector_regime_for_signal, _iv_regime
    signal_data = {"enrichment_data": {"cvd_level": "VAH", "event_reason": "test"}}
    assert _sector_regime_for_signal(signal_data) is None
    assert _iv_regime(signal_data) == ""


# ---------------------------------------------------------------------------
# (f) Equity regression: enricher-owned key set unchanged pre/post-fix
# ---------------------------------------------------------------------------

def test_equity_fixture_enricher_owned_key_set_unchanged():
    signal_data = {"ticker": "SPY", "asset_class": "EQUITY"}  # no pre-existing enrichment_data
    p_universe, p_iv, p_snap, p_sector = _equity_fetch_mocks()
    with p_universe, p_iv, p_snap, p_sector:
        result = _run(enrich_signal(dict(signal_data)))
    assert set(result["enrichment_data"].keys()) == _ENRICHER_OWNED_KEYS
    assert len(_ENRICHER_OWNED_KEYS) == 14
