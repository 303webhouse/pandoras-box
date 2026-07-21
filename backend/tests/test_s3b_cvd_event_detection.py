"""S-3b Item 2 -- CVD event detection tests (bias_filters/
crypto_tape_health_engine.py: _detect_cvd_events, _build_cvd_event_signal,
_check_cvd_cooldown, _fire_cvd_events).

No live API calls or database access -- fetch_crypto_ohlc, compute_volume_
profile, and DB/pipeline calls are all mocked. compute_volume_profile is
mocked directly (rather than threading real bars through it) so anchor
levels (POC/VAH/VAL) are deterministic and don't depend on the histogram
math -- that function has its own coverage elsewhere.
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bias_filters.crypto_tape_health_engine import (
    _detect_cvd_events,
    _build_cvd_event_signal,
    _check_cvd_cooldown,
    _fire_cvd_events,
)

_CONFIG = {
    "cvd_events": {
        "level_proximity_pct": 0.3,
        "absorption_cvd_threshold_usd": 50_000.0,
        "local_extreme_lookback_bars": 12,
        "stop_buffer_pct": 0.5,
        "target_rr": 1.5,
        "divergence_cooldown_seconds": 900,
        "absorption_cooldown_seconds": 900,
        "divergence_signal_expiry_hours": 24,
        "absorption_signal_expiry_hours": 24,
    }
}

_NOW = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


def _bars(closes, lows=None, highs=None):
    """n synthetic (ts, open, high, low, close) bars from a list of closes."""
    n = len(closes)
    lows = lows or [c - 0.5 for c in closes]
    highs = highs or [c + 0.5 for c in closes]
    ts0 = datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc)
    return [
        (ts0, closes[i], highs[i], lows[i], closes[i])
        for i in range(n)
    ]


def _detect_with(bars, vp, cell):
    p1 = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=bars))
    p2 = patch("strategies.btc_market_structure.compute_volume_profile", return_value=vp)
    with p1, p2:
        return _run(_detect_cvd_events("BTC", cell, _CONFIG, _NOW))


# ---------------------------------------------------------------------------
# _detect_cvd_events
# ---------------------------------------------------------------------------

def test_divergence_long_at_local_low_near_val():
    closes = [100.0] * 11 + [95.0]  # last bar is a fresh local low
    # Last bar's own low == its close (95.0) so current_price actually
    # reaches the window minimum; the other 11 bars' lows stay well above it.
    lows = [99.8] * 11 + [95.0]
    bars = _bars(closes, lows=lows)
    vp = {"poc": 105.0, "vah": 108.0, "val": 95.1}  # VAL close to 95 (within 0.3%)
    cell = {"value": 5_000.0}  # net CVD buying despite the new low
    events = _detect_with(bars, vp, cell)
    assert len(events) == 1
    assert events[0]["signal_type"] == "CVD_DIVERGENCE"
    assert events[0]["direction"] == "LONG"
    enrichment = json.loads(events[0]["enrichment_data"])
    assert enrichment["cvd_level"] == "VAL"


def test_divergence_short_at_local_high_near_vah():
    closes = [100.0] * 11 + [105.0]  # fresh local high
    highs = [100.5] * 11 + [105.0]  # last bar's own high == its close
    bars = _bars(closes, highs=highs)
    vp = {"poc": 95.0, "vah": 105.05, "val": 90.0}
    cell = {"value": -5_000.0}  # net CVD selling despite the new high
    events = _detect_with(bars, vp, cell)
    assert len(events) == 1
    assert events[0]["signal_type"] == "CVD_DIVERGENCE"
    assert events[0]["direction"] == "SHORT"


def test_absorption_large_flow_no_price_follow_through():
    # Price oscillates and ends mid-range -- current_price is neither the
    # window's max high nor min low, so neither divergence branch fires.
    closes = [95.0, 100.0, 105.0, 100.0, 95.0, 100.0, 105.0, 100.0, 95.0, 100.0, 105.0, 100.0]
    bars = _bars(closes)  # default lows/highs = close +/- 0.5
    vp = {"poc": 100.05, "vah": 108.0, "val": 88.0}
    cell = {"value": 80_000.0}  # exceeds absorption_cvd_threshold_usd
    events = _detect_with(bars, vp, cell)
    assert len(events) == 1
    assert events[0]["signal_type"] == "CVD_ABSORPTION"
    assert events[0]["direction"] == "LONG"


def test_no_event_when_not_near_any_level():
    closes = [100.0] * 12
    bars = _bars(closes)
    vp = {"poc": 200.0, "vah": 210.0, "val": 190.0}  # far from 100
    cell = {"value": 100_000.0}
    events = _detect_with(bars, vp, cell)
    assert events == []


def test_no_event_when_insufficient_bars():
    bars = _bars([100.0, 101.0])  # fewer than lookback_bars=12
    vp = {"poc": 100.0, "vah": 105.0, "val": 95.0}
    events = _detect_with(bars, vp, {"value": 100_000.0})
    assert events == []


def test_no_event_when_cell_has_no_cvd_value():
    closes = [100.0] * 12
    bars = _bars(closes)
    vp = {"poc": 100.05, "vah": 105.0, "val": 95.0}
    events = _detect_with(bars, vp, {})  # no "value" key -- honest skip
    assert events == []


def test_no_event_when_volume_profile_errors():
    closes = [100.0] * 12
    bars = _bars(closes)
    events = _detect_with(bars, {"error": "insufficient kline data"}, {"value": 100_000.0})
    assert events == []


# ---------------------------------------------------------------------------
# _build_cvd_event_signal -- FA-2 BAR_WALK field set
# ---------------------------------------------------------------------------

def test_build_signal_long_has_bar_walk_fields_and_correct_risk_math():
    sig = _build_cvd_event_signal(
        "BTC", "CVD_DIVERGENCE", "LONG", 100.0, "VAL", 99.5, 5000.0,
        _CONFIG, _NOW, "test reason",
    )
    for field in ("signal_id", "ticker", "direction", "asset_class", "entry_price",
                  "stop_loss", "target_1", "timestamp", "expires_at"):
        assert field in sig, f"missing BAR_WALK-required field: {field}"
    assert sig["asset_class"] == "CRYPTO"
    assert sig["ticker"] == "BTC"
    assert sig["direction"] == "LONG"
    assert sig["entry_price"] == 100.0
    assert sig["stop_loss"] < sig["entry_price"] < sig["target_1"]
    assert sig["stop_loss"] is not None and sig["target_1"] is not None


def test_build_signal_short_risk_math_inverted():
    sig = _build_cvd_event_signal(
        "ETH", "CVD_ABSORPTION", "SHORT", 100.0, "VAH", 100.5, -80000.0,
        _CONFIG, _NOW, "test reason",
    )
    assert sig["target_1"] < sig["entry_price"] < sig["stop_loss"]


def test_build_signal_enrichment_carries_level_and_reason():
    sig = _build_cvd_event_signal(
        "BTC", "CVD_DIVERGENCE", "LONG", 100.0, "POC", 100.1, 1000.0,
        _CONFIG, _NOW, "some reason string",
    )
    enrichment = json.loads(sig["enrichment_data"])
    assert enrichment["cvd_level"] == "POC"
    assert enrichment["event_reason"] == "some reason string"


def test_build_signal_id_embeds_level_name():
    """Live production check (2026-07-18): enrich_signal() unconditionally
    overwrites enrichment_data for every signal (pipeline.py:1447, no
    asset_class gate), so cooldown/dedup cannot rely on enrichment_data
    surviving to a later lookback query. signal_id must carry the level so
    the cooldown check has something durable to key off."""
    sig = _build_cvd_event_signal(
        "BTC", "CVD_ABSORPTION", "SHORT", 100.0, "VAH", 100.5, -80000.0,
        _CONFIG, _NOW, "test reason",
    )
    assert "_VAH_" in sig["signal_id"]
    assert sig["signal_id"].startswith("CRYPTO_CVD_CVD_ABSORPTION_BTC_VAH_")


# ---------------------------------------------------------------------------
# _check_cvd_cooldown
# ---------------------------------------------------------------------------

class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _mock_pool(fetchrow_result):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool


def test_cooldown_clear_when_no_recent_row():
    pool = _mock_pool(None)
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
        result = _run(_check_cvd_cooldown("BTC", "CVD_DIVERGENCE", "VAL", 900))
    assert result is True


def test_cooldown_blocks_when_recent_row_exists():
    pool = _mock_pool({"?column?": 1})
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
        result = _run(_check_cvd_cooldown("BTC", "CVD_DIVERGENCE", "VAL", 900))
    assert result is False


def test_cooldown_fails_closed_on_db_error():
    async def _raise(*a, **k):
        raise RuntimeError("db down")
    with patch("database.postgres_client.get_postgres_client", new=_raise):
        result = _run(_check_cvd_cooldown("BTC", "CVD_DIVERGENCE", "VAL", 900))
    assert result is False  # fail-closed, never fires on an uncertain state


def test_cooldown_query_keys_on_signal_id_not_enrichment_data():
    """Must key off signal_id (survives enrich_signal()'s clobbering), never
    enrichment_data->>'cvd_level' (confirmed unreliable in live production,
    2026-07-18 -- see _build_cvd_event_signal()'s signal_id comment)."""
    pool = _mock_pool(None)
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
        _run(_check_cvd_cooldown("BTC", "CVD_DIVERGENCE", "VAL", 900))
    query_arg = pool.acquire._c.fetchrow.call_args.args[0]
    assert "signal_id LIKE" in query_arg
    assert "enrichment_data" not in query_arg
    bind_args = pool.acquire._c.fetchrow.call_args.args[1:]
    assert any("CRYPTO_CVD_CVD_DIVERGENCE_BTC_VAL_" in str(a) for a in bind_args)


# ---------------------------------------------------------------------------
# _fire_cvd_events -- orchestration + cooldown/dedup proof (Done item 4)
# ---------------------------------------------------------------------------

def test_fire_events_calls_pipeline_once_when_clear():
    closes = [100.0] * 11 + [95.0]
    bars = _bars(closes, lows=[99.8] * 11 + [95.0])
    vp = {"poc": 105.0, "vah": 108.0, "val": 95.1}
    cell = {"value": 5_000.0}

    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=bars))
    p_vp = patch("strategies.btc_market_structure.compute_volume_profile", return_value=vp)
    p_cooldown = patch(
        "bias_filters.crypto_tape_health_engine._check_cvd_cooldown",
        new=AsyncMock(return_value=True),
    )
    p_pipeline = patch("signals.pipeline.process_signal_unified", new=AsyncMock(return_value={}))

    with p_bars, p_vp, p_cooldown, p_pipeline as mock_pipeline:
        _run(_fire_cvd_events("BTC", cell, _CONFIG, _NOW))

    mock_pipeline.assert_awaited_once()


def test_fire_events_second_trigger_in_cooldown_does_not_double_fire():
    """Done Definition item 4: a second synthetic trigger within the
    cooldown window must not fire a duplicate signal."""
    closes = [100.0] * 11 + [95.0]
    bars = _bars(closes, lows=[99.8] * 11 + [95.0])
    vp = {"poc": 105.0, "vah": 108.0, "val": 95.1}
    cell = {"value": 5_000.0}

    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=bars))
    p_vp = patch("strategies.btc_market_structure.compute_volume_profile", return_value=vp)
    p_cooldown = patch(
        "bias_filters.crypto_tape_health_engine._check_cvd_cooldown",
        new=AsyncMock(return_value=False),  # still in cooldown -- a dup was just recorded
    )
    p_pipeline = patch("signals.pipeline.process_signal_unified", new=AsyncMock(return_value={}))

    with p_bars, p_vp, p_cooldown, p_pipeline as mock_pipeline:
        _run(_fire_cvd_events("BTC", cell, _CONFIG, _NOW))

    mock_pipeline.assert_not_awaited()


def test_fire_events_no_detection_no_pipeline_call():
    bars = _bars([100.0] * 12)
    vp = {"poc": 200.0, "vah": 210.0, "val": 190.0}  # nothing near a level
    cell = {"value": 100_000.0}

    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=bars))
    p_vp = patch("strategies.btc_market_structure.compute_volume_profile", return_value=vp)
    p_pipeline = patch("signals.pipeline.process_signal_unified", new=AsyncMock(return_value={}))

    with p_bars, p_vp, p_pipeline as mock_pipeline:
        _run(_fire_cvd_events("BTC", cell, _CONFIG, _NOW))

    mock_pipeline.assert_not_awaited()


def test_fire_events_never_raises_on_internal_failure():
    """A detection/firing failure must never propagate -- compute_tape_health
    already returned its cell by the time this runs."""
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(side_effect=RuntimeError("boom")))
    with p_bars:
        _run(_fire_cvd_events("BTC", {"value": 1.0}, _CONFIG, _NOW))  # must not raise


# ---------------------------------------------------------------------------
# DEF-CVD-DEDUP (2026-07-21) -- cooldown window must have real margin over
# the tape-health job's own 15-min polling interval. Root cause: the old
# 900s cooldown was EXACTLY equal to the 900s (15-min) polling cadence, so
# ordinary scheduler jitter (execution latency, bar-fetch time, DB
# round-trips) pushed the real elapsed gap between ticks above or below
# 900s essentially at random -- the cooldown only suppressed on the ticks
# where jitter happened to land under it. Confirmed live: 3 fires ever
# (as of 2026-07-19) -> 57+ in two days once D3 enabled the 15-min
# schedule, with observed inter-fire gaps clustering right at 898-902s.
# Fix widens both cooldowns to 1800s (2x the 15-min interval) via
# crypto_cycle_config (hot-reload, no code change to the query itself --
# it already correctly reads cooldown_seconds from config).
#
# Note: the per-level (POC/VAH/VAL) keying was investigated and is NOT
# the defect -- _build_cvd_event_signal's signal_id already embeds the
# level NAME (a stable 3-way category), not the drifting numeric level
# price, so "tolerate small anchor-level drift" is already satisfied by
# the existing design. No key-structure change needed.
# ---------------------------------------------------------------------------

_TAPE_HEALTH_JOB_INTERVAL_SECONDS = 15 * 60  # bias_scheduler.py's crypto_tape_health job


def test_seed_cooldowns_have_real_margin_over_polling_interval():
    """Regression guard: this exact test, if it had existed before
    DEF-CVD-DEDUP, would have caught the original bug (900 has zero
    margin over a 900-second interval)."""
    import importlib
    seed = importlib.import_module("config.crypto_cycle_config_seed")
    cvd_cfg = seed.SEED_CONFIG_V1["cvd_events"]
    assert cvd_cfg["absorption_cooldown_seconds"] >= 2 * _TAPE_HEALTH_JOB_INTERVAL_SECONDS
    assert cvd_cfg["divergence_cooldown_seconds"] >= 2 * _TAPE_HEALTH_JOB_INTERVAL_SECONDS


def test_fire_events_passes_widened_cooldown_seconds_to_check():
    """Confirms _fire_cvd_events threads the widened config value through to
    _check_cvd_cooldown -- not silently stuck on the old 900s default."""
    closes = [100.0] * 11 + [95.0]
    bars = _bars(closes, lows=[99.8] * 11 + [95.0])
    vp = {"poc": 105.0, "vah": 108.0, "val": 95.1}
    cell = {"value": 5_000.0}
    widened_config = {"cvd_events": {**_CONFIG["cvd_events"], "divergence_cooldown_seconds": 1800}}

    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=bars))
    p_vp = patch("strategies.btc_market_structure.compute_volume_profile", return_value=vp)
    p_cooldown = patch(
        "bias_filters.crypto_tape_health_engine._check_cvd_cooldown",
        new=AsyncMock(return_value=True),
    )
    p_pipeline = patch("signals.pipeline.process_signal_unified", new=AsyncMock(return_value={}))

    with p_bars, p_vp, p_cooldown as mock_cooldown, p_pipeline:
        _run(_fire_cvd_events("BTC", cell, widened_config, _NOW))

    mock_cooldown.assert_awaited_once()
    call_args = mock_cooldown.await_args.args
    assert call_args[-1] == 1800  # cooldown_seconds is the last positional arg


def test_fire_events_falls_back_to_widened_default_when_config_key_missing():
    """If cvd_events lacks the cooldown key entirely (e.g. a stale cached
    config), the code-level fallback must be the widened 1800s, not the
    old buggy 900s default."""
    closes = [100.0] * 11 + [95.0]
    bars = _bars(closes, lows=[99.8] * 11 + [95.0])
    vp = {"poc": 105.0, "vah": 108.0, "val": 95.1}
    cell = {"value": 5_000.0}
    bare_config = {"cvd_events": {}}  # no cooldown keys at all

    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=bars))
    p_vp = patch("strategies.btc_market_structure.compute_volume_profile", return_value=vp)
    p_cooldown = patch(
        "bias_filters.crypto_tape_health_engine._check_cvd_cooldown",
        new=AsyncMock(return_value=True),
    )
    p_pipeline = patch("signals.pipeline.process_signal_unified", new=AsyncMock(return_value={}))

    with p_bars, p_vp, p_cooldown as mock_cooldown, p_pipeline:
        _run(_fire_cvd_events("BTC", cell, bare_config, _NOW))

    call_args = mock_cooldown.await_args.args
    assert call_args[-1] == 1800


def test_cooldown_key_is_level_name_not_numeric_price():
    """Confirms the investigated-and-ruled-out hypothesis: the dedup key
    (via signal_id's LIKE prefix) is the level NAME (POC/VAH/VAL), a
    stable category -- not the drifting numeric level_price. Small price
    drift at the same structural level therefore already can't defeat the
    cooldown; this was never the defect."""
    sig_a = _build_cvd_event_signal("BTC", "CVD_ABSORPTION", "LONG", 100.0, "POC", 100.05, 60_000.0, _CONFIG, _NOW, "r")
    sig_b = _build_cvd_event_signal("BTC", "CVD_ABSORPTION", "LONG", 100.3, "POC", 100.31, 60_000.0, _CONFIG, _NOW, "r")
    prefix_a = sig_a["signal_id"].rsplit("_", 1)[0]
    prefix_b = sig_b["signal_id"].rsplit("_", 1)[0]
    assert prefix_a == prefix_b == "CRYPTO_CVD_CVD_ABSORPTION_BTC_POC"
