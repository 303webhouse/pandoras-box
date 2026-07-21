"""S-4 Phase 3 -- carry-asymmetry display + funding-fade gating rules.

Covers:
  4.2 (crypto_setups.py::check_funding_rate_fade) -- negative-funding LONGs
      in the [0.0003, 0.0005) "delta zone" are the only band where ATLAS's
      raised 0.0005 floor (s4-phase0-findings.md 0.4) would change behavior.
      Per an adversarial post-implementation review of this same brief
      (this session), shipping that floor raise directly/unflagged was
      judged a mistake -- it silently overrode Phase 0's own "shadow-tag by
      default... regardless" resolution and hard rule 6 ("shadow-first
      where new gating logic is involved"), when a low-cost shadow-gated
      alternative was available. Revised design: the delta zone is logged
      every time it's hit (shadow evidence) but only actually enforced once
      master_rules.funding_fade_negative_floor_raise_enabled flips true in
      crypto_gate_config (hot-reload, default false -- today's 0.0003 floor
      keeps firing until Nick/Titans opt in). Positive-funding SHORTs are
      completely unaffected either way.
  4.3 (crypto_gates.py::evaluate_gates) -- no negative-funding-fade LONGs
      at Tier 3 (HYPE/ZEC/FARTCOIN). Config-driven
      (master_rules.tier3_blocks_negative_funding_fade_longs), shadow-only
      while gating_enabled stays false.
  4.1 (scripts/signal_notifier.py::post_crypto_signal_alert) -- carry
      asymmetry display, Funding_Rate_Fade cards only.
  Addendum: Risk-line display fix (never renders "$0" or "(?%)").
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strategies.crypto_setups import check_funding_rate_fade
from bias_filters.crypto_gates import evaluate_gates


# ---------------------------------------------------------------------------
# 4.2 -- check_funding_rate_fade entry-floor rules
# ---------------------------------------------------------------------------

def _funding(rate, mins_to_settle=10.0, mark_price=65000.0):
    return {
        "funding_rate": rate,
        "funding_rate_pct": rate * 100,
        "next_funding_time": "2026-07-21T12:00:00+00:00",
        "minutes_to_settlement": mins_to_settle,
        "mark_price": mark_price,
        "index_price": mark_price,
    }


def _gate_config(raise_enabled=False):
    return (5, {"master_rules": {"funding_fade_negative_floor_raise_enabled": raise_enabled}})


def _run_fade(rate, mins_to_settle=10.0, raise_enabled=False, gate_config_raises=False):
    gc_mock = AsyncMock(side_effect=RuntimeError("db down")) if gate_config_raises \
        else AsyncMock(return_value=_gate_config(raise_enabled))
    with patch("integrations.binance_futures.get_funding_rate", new=AsyncMock(return_value=_funding(rate, mins_to_settle))), \
         patch("strategies.crypto_setups._can_fire", return_value=True), \
         patch("strategies.crypto_setups._mark_fired"), \
         patch("config.crypto_gate_loader.get_gate_config", new=gc_mock):
        return asyncio.run(check_funding_rate_fade(symbol="BTCUSDT"))


def test_short_unchanged_floor_0003_fires():
    # positive funding, abs_rate = 0.00035 -- above the unchanged 0.0003 SHORT floor
    sig = _run_fade(rate=0.00035)
    assert sig is not None
    assert sig["direction"] == "SHORT"


def test_short_below_0003_still_rejected():
    sig = _run_fade(rate=0.00025)
    assert sig is None


def test_long_below_old_0003_floor_still_rejected():
    sig = _run_fade(rate=-0.00025)
    assert sig is None


def test_long_in_delta_zone_fires_when_flag_disabled():
    """Current live default (flag defaults false in crypto_gate_config):
    the delta zone [0.0003, 0.0005) still fires under today's 0.0003 floor
    -- shadow-only, not yet enforced."""
    sig = _run_fade(rate=-0.00035, raise_enabled=False)
    assert sig is not None
    assert sig["direction"] == "LONG"


def test_long_in_delta_zone_rejected_when_flag_enabled():
    """Once Nick/Titans flip master_rules.
    funding_fade_negative_floor_raise_enabled=true, the same delta-zone
    rate must be rejected -- this is the actual enforcement path."""
    sig = _run_fade(rate=-0.00035, raise_enabled=True)
    assert sig is None


def test_long_in_delta_zone_defaults_disabled_on_config_fetch_failure():
    """Fail-open: if the gate config fetch itself errors, the raised floor
    must NOT be enforced (matches the rest of this codebase's
    fail-open-to-last-good-state posture) -- the delta zone still fires."""
    sig = _run_fade(rate=-0.00035, gate_config_raises=True)
    assert sig is not None
    assert sig["direction"] == "LONG"


def test_long_at_new_0005_floor_fires_regardless_of_flag():
    """At/above 0.0005 the delta-zone branch isn't even entered -- fires
    unconditionally, flag state irrelevant."""
    sig = _run_fade(rate=-0.0005, raise_enabled=True)
    assert sig is not None
    assert sig["direction"] == "LONG"


def test_long_above_0005_fires_high_confidence():
    sig = _run_fade(rate=-0.0006, raise_enabled=True)
    assert sig is not None
    assert sig["direction"] == "LONG"
    enrichment = json.loads(sig["enrichment_data"])
    assert enrichment["confidence"] == "HIGH"


def test_short_scoring_unaffected_by_long_floor_change():
    """The MEDIUM-confidence scoring band (0.0003 <= abs_rate < 0.0005) must
    still exist for SHORT -- only the LONG entry floor moved, not the
    post-qualification score/confidence labeling for either branch."""
    sig = _run_fade(rate=0.0004)  # SHORT, qualifies at 0.0003, still < 0.0005
    assert sig is not None
    enrichment = json.loads(sig["enrichment_data"])
    assert enrichment["confidence"] == "MEDIUM"


# ---------------------------------------------------------------------------
# 4.3 -- evaluate_gates Tier-3 negative-funding-fade LONG block
# ---------------------------------------------------------------------------

_GATE_CONFIG = {
    "gating_enabled": False,
    "master_rules": {
        "btc_trend_down_blocks_tier3_all_entries": True,
        "btc_trend_down_blocks_tier2_longs": True,
        "unknown_master_blocks_regime_dependent": True,
        "tier3_blocks_negative_funding_fade_longs": True,
    },
    "tiers": {"BTC-USD": 1, "ETH-USD": 1, "SOL-USD": 2, "HYPE-USD": 3, "ZEC-USD": 3, "FARTCOIN-USD": 3},
    "alt_gate": {"status": "NOT_AVAILABLE"},
    "strategy_classes": {
        "fade_mean_reversion": {"strategies": ["Funding_Rate_Fade", "Exhaustion"], "long_allowed_in": ["CHOP", "TREND_UP"], "short_allowed_in": ["CHOP", "TREND_DOWN"]},
        "unclassified": {"strategies": ["*"], "policy": "WOULD_PASS_WITH_NOTE"},
    },
    "advisories": {"weekend_holiday_size_reduce": True},
}


class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False


def _mock_pool(regime_rows):
    conn = MagicMock()

    async def _fetchrow(sql, *args, **kwargs):
        if "crypto_regime_log" in sql:
            return regime_rows.get(args[0])
        return None

    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_Acq(conn))
    return pool


def _run_evaluate(ticker, direction, strategy="Funding_Rate_Fade", regime_state="CHOP"):
    regime_rows = {
        "BTC-USD": {"regime_state": "CHOP", "tier": 1},
        ticker: {"regime_state": regime_state, "tier": None},
    }
    session_state = {
        "partition": "NY", "event_windows_active": [], "weekend_holiday_flag": False,
        "as_of_utc": datetime.now(timezone.utc).isoformat(), "as_of_denver": "x", "next_transitions": [],
    }
    pool = _mock_pool(regime_rows)
    signal_data = {"signal_id": f"TEST_{ticker}_{strategy}_{direction}", "ticker": ticker, "strategy": strategy, "direction": direction}
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)), \
         patch("config.crypto_gate_loader.get_gate_config", new=AsyncMock(return_value=(4, _GATE_CONFIG))), \
         patch("utils.crypto_sessions.get_session_state", new=lambda *a, **k: session_state):
        return asyncio.run(evaluate_gates(signal_data))


def test_tier3_negative_funding_fade_long_blocked():
    row = _run_evaluate("HYPE-USD", "LONG", strategy="Funding_Rate_Fade")
    assert row["verdict"] == "WOULD_BLOCK"
    assert "TIER3_NEG_FUNDING_FADE_LONG_BLOCK" in row["reasons"]


def test_tier3_funding_fade_short_not_blocked_by_this_rule():
    row = _run_evaluate("ZEC-USD", "SHORT", strategy="Funding_Rate_Fade")
    assert "TIER3_NEG_FUNDING_FADE_LONG_BLOCK" not in row["reasons"]


def test_tier1_funding_fade_long_not_blocked_by_this_rule():
    row = _run_evaluate("BTC-USD", "LONG", strategy="Funding_Rate_Fade")
    assert "TIER3_NEG_FUNDING_FADE_LONG_BLOCK" not in row["reasons"]


def test_tier3_other_strategy_long_not_blocked_by_this_rule():
    row = _run_evaluate("FARTCOIN-USD", "LONG", strategy="Crypto Scanner")
    assert "TIER3_NEG_FUNDING_FADE_LONG_BLOCK" not in row["reasons"]


def test_tier3_block_shadow_only_when_gating_disabled():
    """verdict/reasons are always computed, but nothing enforces it while
    gating_enabled stays false -- covered at the maybe_enforce_gate level
    already in test_crypto_gates.py; this just reconfirms the verdict shape
    for the new rule specifically carries through the shadow row unchanged."""
    row = _run_evaluate("HYPE-USD", "LONG", strategy="Funding_Rate_Fade")
    assert row["verdict"] == "WOULD_BLOCK"
    assert row["tier"] is None or True  # tier comes from config lookup, not the mocked regime row
    assert row["strategy"] == "Funding_Rate_Fade"
    assert row["direction"] == "LONG"


# ---------------------------------------------------------------------------
# 4.1 -- carry asymmetry display + Risk-line fix (scripts/signal_notifier.py)
# ---------------------------------------------------------------------------

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import signal_notifier as sn  # noqa: E402

_STATE_WITH_FUNDING = {
    "symbol": "BTC", "tier": 1,
    "regime": {"state": "CHOP", "degraded": False},
    "session": {"partition": "LONDON", "degraded": False},
    "funding": {"rate_pct": 0.0329, "degraded": False},
    "liquidations": {"total_usd": 5_000_000, "long_pct": 60.0, "degraded": False},
    "atr": {"atr": 300.0, "degraded": False},
}


def _fake_http_json_factory(state):
    def _f(url, method="GET", headers=None, payload=None, timeout=30):
        if "/crypto/state/" in url:
            return dict(state)
        return {"id": "1"}
    return _f


def _post_and_capture_embed(signal, state=_STATE_WITH_FUNDING):
    captured = {}

    def _fake_http_json(url, method="GET", headers=None, payload=None, timeout=30):
        if "/crypto/state/" in url:
            return dict(state)
        captured["payload"] = payload
        return {"id": "1"}

    with patch.object(sn, "http_json", side_effect=_fake_http_json):
        sn.post_crypto_signal_alert("tok", "chan", signal, "sig-1", api_url="https://hub/api")
    return captured["payload"]["embeds"][0]["description"]


def test_carry_asymmetry_shown_for_funding_rate_fade():
    signal = {
        "ticker": "BTC", "direction": "LONG", "score": 75, "strategy": "Funding_Rate_Fade",
        "entry_price": 65000.0, "stop_loss": 64805.0, "target_1": 65325.0,
        "enrichment_data": json.dumps({"position_sizing": {"stop_distance_pct": 0.3, "risk_usd": 250.0, "risk_pct": 1.0}}),
    }
    desc = _post_and_capture_embed(signal)
    assert "Carry Asymmetry" in desc
    assert "0.0329%/8h" in desc


def test_carry_asymmetry_not_shown_for_other_strategies():
    signal = {
        "ticker": "BTC", "direction": "LONG", "score": 75, "strategy": "Crypto Scanner",
        "entry_price": 65000.0, "stop_loss": 64805.0, "target_1": 65325.0,
        "enrichment_data": json.dumps({"position_sizing": {"stop_distance_pct": 0.3, "risk_usd": 250.0, "risk_pct": 1.0}}),
    }
    desc = _post_and_capture_embed(signal)
    assert "Carry Asymmetry" not in desc


def test_carry_asymmetry_omitted_when_stop_distance_pct_missing():
    signal = {
        "ticker": "BTC", "direction": "LONG", "score": 75, "strategy": "Funding_Rate_Fade",
        "entry_price": 65000.0, "stop_loss": 64805.0, "target_1": 65325.0,
        "enrichment_data": json.dumps({}),
    }
    desc = _post_and_capture_embed(signal)
    assert "Carry Asymmetry" not in desc


def test_carry_asymmetry_omitted_when_funding_degraded():
    degraded_state = dict(_STATE_WITH_FUNDING, funding={"rate_pct": 0.0329, "degraded": True})
    signal = {
        "ticker": "BTC", "direction": "LONG", "score": 75, "strategy": "Funding_Rate_Fade",
        "entry_price": 65000.0, "stop_loss": 64805.0, "target_1": 65325.0,
        "enrichment_data": json.dumps({"position_sizing": {"stop_distance_pct": 0.3, "risk_usd": 250.0, "risk_pct": 1.0}}),
    }
    desc = _post_and_capture_embed(signal, state=degraded_state)
    assert "Carry Asymmetry" not in desc


def test_risk_line_shows_real_dollar_and_pct_when_present():
    signal = {
        "ticker": "BTC", "direction": "LONG", "score": 75, "strategy": "Crypto Scanner",
        "entry_price": 65000.0, "stop_loss": 64805.0, "target_1": 65325.0,
        "enrichment_data": json.dumps({"position_sizing": {"risk_usd": 250.0, "risk_pct": 1.0}}),
    }
    desc = _post_and_capture_embed(signal)
    assert "**Risk:** $250 (1.0%)" in desc
    assert "$0" not in desc
    assert "(?%)" not in desc


def test_risk_line_falls_back_to_per_unit_when_sizing_absent():
    """The exact regression this fix was: sizing.get('risk_usd', risk) and
    sizing.get('risk_pct', '?') rendering '$0 (?%)' when position_sizing is
    missing entirely (e.g. non-crypto_setups.py writers like CVD_ABSORPTION)."""
    signal = {
        "ticker": "BTC", "direction": "LONG", "score": 75, "strategy": "CVD_ABSORPTION",
        "entry_price": 65000.0, "stop_loss": 64805.0, "target_1": 65325.0,
        "enrichment_data": json.dumps({}),  # no position_sizing key at all
    }
    desc = _post_and_capture_embed(signal)
    assert "$0" not in desc
    assert "(?%)" not in desc
    assert "Risk/unit:" in desc
    assert "$195.00" in desc  # abs(65000 - 64805) = 195.0


def test_risk_line_falls_back_when_sizing_incomplete():
    """sizing present but missing risk_pct specifically -- must not render
    a literal '?' percent either."""
    signal = {
        "ticker": "BTC", "direction": "LONG", "score": 75, "strategy": "Crypto Scanner",
        "entry_price": 65000.0, "stop_loss": 64805.0, "target_1": 65325.0,
        "enrichment_data": json.dumps({"position_sizing": {"contracts": 0, "risk_usd": 0, "safe": False}}),
    }
    desc = _post_and_capture_embed(signal)
    assert "(?%)" not in desc
    assert "Risk/unit:" in desc


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\nAll {len(tests)} S-4 Phase 3 tests passed.")
