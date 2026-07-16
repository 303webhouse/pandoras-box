"""
Unit + integration tests for bias_filters/crypto_gates.py (S-2, R-1 shadow
gate evaluator).

Covers: master-rule blocks, strategy-class regime mismatches, the
requires_event_window rule, the never-blocking weekend advisory, the
unclassified-strategy fallback, the dormant enforcement branch (proven both
inert-when-disabled and correct-when-forced -- "unit-tested behind the
flag" per the brief), and Done item 10's failure-injection proof: an
evaluator exception must never affect the real signal write.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bias_filters.crypto_gates import evaluate_gates, maybe_enforce_gate


TEST_CONFIG = {
    "gating_enabled": False,
    "master_rules": {
        "btc_trend_down_blocks_tier3_all_entries": True,
        "btc_trend_down_blocks_tier2_longs": True,
        "unknown_master_blocks_regime_dependent": True,
    },
    "tiers": {"BTC-USD": 1, "ETH-USD": 1, "SOL-USD": 2, "HYPE-USD": 3, "ZEC-USD": 3, "FARTCOIN-USD": 3},
    "alt_gate": {"status": "NOT_AVAILABLE"},
    "strategy_classes": {
        "momentum_continuation": {"strategies": ["Crypto Scanner", "Holy_Grail"], "long_allowed_in": ["TREND_UP"], "short_allowed_in": ["TREND_DOWN"]},
        "sweep_reclaim": {"strategies": ["Session_Sweep"], "long_allowed_in": ["CHOP", "TREND_UP"], "short_allowed_in": ["CHOP", "TREND_DOWN"], "requires_event_window": True},
        "unclassified": {"strategies": ["*"], "policy": "WOULD_PASS_WITH_NOTE"},
    },
    "advisories": {"weekend_holiday_size_reduce": True},
}


class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _mock_pool(regime_rows: dict):
    """regime_rows: {"BTC-USD": {"regime_state": ..., "tier": ...}, ...}"""
    conn = MagicMock()

    async def _fetchrow(sql, *args, **kwargs):
        if "crypto_regime_log" in sql:
            symbol = args[0]
            return regime_rows.get(symbol)
        return None

    async def _execute(sql, *args, **kwargs):
        return "UPDATE 1"

    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    conn.execute = AsyncMock(side_effect=_execute)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_Acq(conn))
    return pool, conn


def _signal(ticker="BTC-USD", strategy="Crypto Scanner", direction="LONG"):
    return {"signal_id": f"TEST_{ticker}_{strategy}", "ticker": ticker, "strategy": strategy, "direction": direction}


def _run_evaluate(signal_data, regime_rows, config=None):
    pool, conn = _mock_pool(regime_rows)
    session_state = {
        "partition": "NY", "event_windows_active": [], "weekend_holiday_flag": False,
        "as_of_utc": datetime.now(timezone.utc).isoformat(), "as_of_denver": "x", "next_transitions": [],
    }
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)), \
         patch("config.crypto_gate_loader.get_gate_config", new=AsyncMock(return_value=(1, config or TEST_CONFIG))), \
         patch("utils.crypto_sessions.get_session_state", new=lambda *a, **k: session_state):
        return asyncio.run(evaluate_gates(signal_data)), conn


# ── Unresolved ticker ─────────────────────────────────────────────────────

def test_unresolved_ticker_returns_none():
    row, _ = _run_evaluate(_signal(ticker="AAPL"), {})
    assert row is None


# ── Master rules ──────────────────────────────────────────────────────────

def test_unknown_master_blocks():
    row, _ = _run_evaluate(_signal(), {})  # no regime rows at all -> UNKNOWN
    assert row["verdict"] == "WOULD_BLOCK"
    assert "REGIME_UNKNOWN" in row["reasons"]


def test_btc_trend_down_blocks_tier3():
    regime_rows = {
        "BTC-USD": {"regime_state": "TREND_DOWN", "tier": 1},
        "FARTCOIN-USD": {"regime_state": "CHOP", "tier": 3},
    }
    row, _ = _run_evaluate(_signal(ticker="FARTCOIN-USD", strategy="Crypto Scanner"), regime_rows)
    assert row["verdict"] == "WOULD_BLOCK"
    assert "BTC_TREND_DOWN_T3_BLOCK" in row["reasons"]


def test_btc_trend_down_blocks_tier2_long_only():
    regime_rows = {
        "BTC-USD": {"regime_state": "TREND_DOWN", "tier": 1},
        "SOL-USD": {"regime_state": "CHOP", "tier": 2},
    }
    long_row, _ = _run_evaluate(_signal(ticker="SOL-USD", strategy="Crypto Scanner", direction="LONG"), regime_rows)
    short_row, _ = _run_evaluate(_signal(ticker="SOL-USD", strategy="Crypto Scanner", direction="SHORT"), regime_rows)
    assert long_row["verdict"] == "WOULD_BLOCK"
    assert "BTC_TREND_DOWN_T2_LONG_BLOCK" in long_row["reasons"]
    # SHORT isn't gated by this specific rule; master rule doesn't fire for it.
    assert "BTC_TREND_DOWN_T2_LONG_BLOCK" not in short_row["reasons"]


# ── Strategy-class rules ──────────────────────────────────────────────────

def test_strategy_class_regime_mismatch():
    regime_rows = {
        "BTC-USD": {"regime_state": "TREND_DOWN", "tier": 1},
    }
    # momentum_continuation LONG only allowed in TREND_UP -> mismatch vs TREND_DOWN.
    # (BTC is both master and symbol here, so the T3/T2 master rules don't apply -- tier 1.)
    row, _ = _run_evaluate(_signal(ticker="BTC-USD", strategy="Crypto Scanner", direction="LONG"), regime_rows)
    assert row["verdict"] == "WOULD_BLOCK"
    assert any("STRATEGY_CLASS_REGIME_MISMATCH" in r for r in row["reasons"])


def test_unclassified_strategy_would_pass_with_note():
    regime_rows = {"BTC-USD": {"regime_state": "CHOP", "tier": 1}}
    row, _ = _run_evaluate(_signal(ticker="BTC-USD", strategy="Some_New_Strategy"), regime_rows)
    assert row["verdict"] == "WOULD_PASS"
    assert "UNCLASSIFIED_STRATEGY" in row["reasons"]


def test_session_window_required_but_absent():
    regime_rows = {
        "BTC-USD": {"regime_state": "CHOP", "tier": 1},
        "ETH-USD": {"regime_state": "CHOP", "tier": 1},
    }
    row, _ = _run_evaluate(_signal(ticker="ETH-USD", strategy="Session_Sweep", direction="LONG"), regime_rows)
    assert row["verdict"] == "WOULD_BLOCK"
    assert "SESSION_WINDOW" in row["reasons"]


def test_weekend_holiday_advisory_never_blocks():
    regime_rows = {"BTC-USD": {"regime_state": "CHOP", "tier": 1}}
    session_state = {
        "partition": "NY", "event_windows_active": [], "weekend_holiday_flag": True,
        "as_of_utc": "x", "as_of_denver": "x", "next_transitions": [],
    }
    pool, conn = _mock_pool(regime_rows)
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)), \
         patch("config.crypto_gate_loader.get_gate_config", new=AsyncMock(return_value=(1, TEST_CONFIG))), \
         patch("utils.crypto_sessions.get_session_state", new=lambda *a, **k: session_state):
        row = asyncio.run(evaluate_gates(_signal(ticker="BTC-USD", strategy="Some_New_Strategy")))
    assert row["verdict"] == "WOULD_PASS"
    assert "SIZE_REDUCE_WEEKEND" in row["reasons"]


# ── Dormant enforcement branch — "unit-tested behind the flag" ───────────

def test_maybe_enforce_gate_dormant_when_disabled():
    config = {**TEST_CONFIG, "gating_enabled": False}
    gate_row = {"verdict": "WOULD_BLOCK", "reasons": ["REGIME_UNKNOWN"]}
    result = asyncio.run(maybe_enforce_gate(_signal(), gate_row, config))
    assert result is False


def test_maybe_enforce_gate_would_pass_never_dismisses_even_if_enabled():
    config = {**TEST_CONFIG, "gating_enabled": True}
    gate_row = {"verdict": "WOULD_PASS", "reasons": []}
    result = asyncio.run(maybe_enforce_gate(_signal(), gate_row, config))
    assert result is False


def test_maybe_enforce_gate_dismisses_when_forced_enabled_and_blocked():
    """Proves the code path is correct even though it never runs for real in
    S-2 -- the seeded config keeps gating_enabled=false (hard rule 1)."""
    config = {**TEST_CONFIG, "gating_enabled": True}
    gate_row = {"verdict": "WOULD_BLOCK", "reasons": ["BTC_TREND_DOWN_T3_BLOCK"]}
    pool, conn = _mock_pool({})
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)), \
         patch("database.redis_client.get_redis_client", new=AsyncMock(return_value=None)):
        result = asyncio.run(maybe_enforce_gate(_signal(), gate_row, config))
    assert result is True
    conn.execute.assert_awaited_once()
    args = conn.execute.await_args.args
    assert "DISMISSED" in args[0]
    assert "REGIME_GATE:BTC_TREND_DOWN_T3_BLOCK" in args[1]


# ── Done item 10: failure-injection proof (full pipeline level) ──────────

def _mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.setex = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=True)
    return r


def _crypto_signal(signal_id):
    return {
        "signal_id": signal_id, "ticker": "BTC-USD", "direction": "LONG",
        "strategy": "S2_Phase4_FailureInjectionTest", "signal_type": "TEST",
        "asset_class": "CRYPTO", "entry_price": 65000.0, "stop_loss": 63000.0,
        "target_1": 68000.0, "timeframe": "DAILY",
    }


def test_evaluator_exception_never_breaks_the_real_signal_write():
    """Force evaluate_gates() to raise. The signal write (log_signal) must
    still succeed and process_signal_unified must return normally -- no
    exception propagates past the try/except wrapping the gate hook."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_Acq(conn))
    redis = _mock_redis()

    log_signal_mock = AsyncMock()

    async def _passthrough(signal_data, *a, **k):
        return signal_data

    with patch("database.redis_client.get_redis_client", new=AsyncMock(return_value=redis)), \
         patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)), \
         patch("signals.pipeline.log_signal", new=log_signal_mock), \
         patch("signals.price_enrichment.enrich_price_range", new=_passthrough), \
         patch("signals.flow_enrichment.enrich_flow_data", new=_passthrough), \
         patch("bias_filters.crypto_gates.evaluate_gates", new=AsyncMock(side_effect=RuntimeError("injected failure"))):
        from signals.pipeline import process_signal_unified
        out = asyncio.run(process_signal_unified(_crypto_signal("TEST_S2_FAILURE_INJECTION"), source="test"))

    # The real signal write happened despite the injected evaluator exception.
    log_signal_mock.assert_awaited()
    assert out.get("signal_id") == "TEST_S2_FAILURE_INJECTION"
    assert out.get("status") != "REJECTED"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\nAll {len(tests)} crypto_gates tests passed.")
