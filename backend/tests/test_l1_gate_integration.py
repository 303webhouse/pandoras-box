"""L1a gate — INTEGRATION test on REAL process_signal_unified output (ATLAS mandate).

The gate's pass/flow_unavailable decision is asserted against the triggering_factors
that the REAL pipeline (apply_scoring → P4A flow block) produces from a routed
`flow_events` DB row — NOT a hand-fabricated triggering_factors["flow"] dict. The
_flow_aligned bug survived 2 months because its test fabricated the input shape; this
test feeds DB INPUT (real columns) and lets real code build the shape.

External boundaries (redis, postgres, yfinance enrichers, MP read, alarm) are mocked;
the SCORING + FLOW + GATE code paths are real.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _mock_pool(flow_row):
    conn = MagicMock()

    async def _fetchrow(sql, *a, **k):
        return flow_row if "from flow_events" in sql.lower() else None

    async def _fetch(sql, *a, **k):
        return []

    async def _execute(sql, *a, **k):
        return "INSERT 0 1"

    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    conn.fetch = AsyncMock(side_effect=_fetch)
    conn.execute = AsyncMock(side_effect=_execute)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_Acq(conn))
    return pool


def _mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.setex = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=True)
    r.scan = AsyncMock(return_value=(b"0", []))
    r.mget = AsyncMock(return_value=[])
    r.keys = AsyncMock(return_value=[])
    return r


_FRESH_ACCEPTED_MP = {
    "status": "ok",
    "data": {
        "interpretation": "IB breakout to upside - initiative buying",
        "va_migration": "higher", "poor_high": False, "poor_low": False,
        "event_age_seconds": 120,
    },
    "staleness_seconds": 120,
}


def _spy_signal(signal_id):
    return {
        "signal_id": signal_id, "ticker": "SPY", "direction": "LONG",
        "strategy": "CTA Scanner", "signal_type": "PULLBACK_ENTRY", "asset_class": "EQUITY",
        "entry_price": 600.0, "stop_loss": 595.0, "target_1": 610.0, "target_2": 620.0,
        "risk_reward": 2.0, "timeframe": "DAILY",
    }


def _run_pipeline(signal_id, flow_row, monkeypatch):
    monkeypatch.setenv("L1_GATE_SHADOW", "true")
    redis = _mock_redis()
    pool = _mock_pool(flow_row)

    async def _passthrough(signal_data, *a, **k):
        return signal_data

    with patch("database.redis_client.get_redis_client", new=AsyncMock(return_value=redis)), \
         patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)), \
         patch("signals.price_enrichment.enrich_price_range", new=_passthrough), \
         patch("signals.flow_enrichment.enrich_flow_data", new=_passthrough), \
         patch("services.read_only.market_profile.get_market_profile",
               new=AsyncMock(return_value=_FRESH_ACCEPTED_MP)), \
         patch("config.l1_gate._in_rth", new=lambda: True), \
         patch("bias_engine.anomaly_alerts.send_alert", new=AsyncMock()):
        from signals.pipeline import process_signal_unified
        out = asyncio.run(process_signal_unified(_spy_signal(signal_id), source="test"))
    return out


# --- flow PRESENT (routed flow_events row) → real flow dict → gate decision ----
def test_l1_shadow_tag_on_real_pipeline_output_flow_present(monkeypatch):
    flow_row = {"total_premium": 9_000_000, "call_premium": 8_000_000,
                "put_premium": 1_000_000, "flow_sentiment": "BULLISH", "pc_ratio": 0.5}
    out = _run_pipeline("TEST_SPY_L1A_PASS", flow_row, monkeypatch)

    tf = out.get("triggering_factors") or {}
    assert "l1_shadow" in tf, "gate must tag triggering_factors['l1_shadow'] in shadow mode"
    l1 = tf["l1_shadow"]

    # The flow vector must be derived from the REAL triggering_factors['flow'] the
    # scorer produced — not a fabricated dict. Assert consistency with it.
    assert "flow" in tf, "apply_scoring P4A should have populated the real flow dict"
    real_call = tf["flow"]["call_premium"]
    real_put = tf["flow"]["put_premium"]
    assert l1["flow"]["net"] == real_call - real_put
    assert l1["flow"]["state"] == "fresh"
    assert l1["flow"]["aligned"] is True            # LONG + premium-bullish
    assert l1["auction"]["state"] == "fresh_accepted"
    assert l1["gate"] == "pass"
    assert l1["regime_conditioning"] == "deferred_sb3_null"


# --- flow ABSENT (no flow_events row) → honest flow_unavailable ----------------
def test_l1_shadow_flow_unavailable_when_no_flow(monkeypatch):
    out = _run_pipeline("TEST_SPY_L1A_NOFLOW", None, monkeypatch)
    tf = out.get("triggering_factors") or {}
    assert "l1_shadow" in tf
    l1 = tf["l1_shadow"]
    assert l1["flow"]["state"] == "missing"
    assert l1["gate"] == "flow_unavailable"   # never confirm on absent flow


# --- flag OFF → no tag (inert) ------------------------------------------------
def test_no_l1_tag_when_flag_off(monkeypatch):
    monkeypatch.delenv("L1_GATE_SHADOW", raising=False)
    redis = _mock_redis()
    pool = _mock_pool({"total_premium": 9_000_000, "call_premium": 8_000_000,
                       "put_premium": 1_000_000, "flow_sentiment": "BULLISH", "pc_ratio": 0.5})

    async def _passthrough(signal_data, *a, **k):
        return signal_data

    with patch("database.redis_client.get_redis_client", new=AsyncMock(return_value=redis)), \
         patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)), \
         patch("signals.price_enrichment.enrich_price_range", new=_passthrough), \
         patch("signals.flow_enrichment.enrich_flow_data", new=_passthrough), \
         patch("bias_engine.anomaly_alerts.send_alert", new=AsyncMock()):
        from signals.pipeline import process_signal_unified
        out = asyncio.run(process_signal_unified(_spy_signal("TEST_SPY_L1A_OFF"), source="test"))
    tf = out.get("triggering_factors") or {}
    assert "l1_shadow" not in tf
