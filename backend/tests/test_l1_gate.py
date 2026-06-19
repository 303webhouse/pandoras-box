"""L1a gate — unit tests for the pure decision logic.

These cover the pure helpers (evaluate_flow / acceptance / _decide) with
REAL-shaped flow sub-dicts (the actual P4A keys). The writer↔reader integration
(real pipeline output) is in test_l1_gate_integration.py — per the ATLAS mandate,
the gate's pass/asterisk/fail is asserted there against real process output, not a
fabricated dict.
"""

import importlib

import pytest

import config.l1_gate as l1


def _flow(call, put, total=None, **extra):
    d = {"call_premium": call, "put_premium": put,
         "total_premium": total if total is not None else call + put}
    d.update(extra)   # e.g. the sentiment/bonus we must IGNORE
    return d


# --- evaluate_flow: ignores sentiment/bonus, premium-based, ratio-gated --------
def test_flow_confirms_premium_bullish_ignoring_stale_sentiment():
    # The recorded sub-dict says BEARISH (old volume logic); premium is bullish.
    f = l1.evaluate_flow(_flow(8_000_000, 1_000_000, sentiment="BEARISH", bonus=6), "LONG")
    assert f["aligned"] is True and f["confirms"] is True and f["contradicts"] is False
    assert f["net"] == 7_000_000 and f["ratio"] == pytest.approx(0.7778, abs=1e-3)
    assert f["state"] == "fresh"


def test_flow_contradicts_when_dominant_opposite():
    f = l1.evaluate_flow(_flow(8_000_000, 1_000_000), "SHORT")
    assert f["aligned"] is False and f["contradicts"] is True and f["confirms"] is False


def test_flow_inconclusive_below_ratio():
    f = l1.evaluate_flow(_flow(5_100_000, 4_900_000), "LONG")
    assert f["confirms"] is False and f["contradicts"] is False  # ratio 0.02 < 0.15


def test_flow_missing_never_confirms():
    f = l1.evaluate_flow(None, "LONG")
    assert f["state"] == "missing" and f["confirms"] is False
    f2 = l1.evaluate_flow({}, "LONG")
    assert f2["state"] == "missing"


def test_flow_dominance_threshold_env(monkeypatch):
    # ratio = 0.20 → confirms at default 0.15, NOT at 0.30
    monkeypatch.setenv("L1_FLOW_DOMINANCE_RATIO", "0.30")
    importlib.reload(l1)
    f = l1.evaluate_flow(_flow(6_000_000, 4_000_000), "LONG")  # net 2M / 10M = 0.20
    assert f["confirms"] is False
    monkeypatch.setenv("L1_FLOW_DOMINANCE_RATIO", "0.15")
    importlib.reload(l1)
    f2 = l1.evaluate_flow(_flow(6_000_000, 4_000_000), "LONG")
    assert f2["confirms"] is True
    monkeypatch.delenv("L1_FLOW_DOMINANCE_RATIO", raising=False)
    importlib.reload(l1)


def test_flow_zero_total_no_divide_error():
    f = l1.evaluate_flow(_flow(0, 0, total=0), "LONG")
    assert f["ratio"] is None and f["confirms"] is False


# --- acceptance heuristic over the live interpretation strings -----------------
def test_acceptance_initiative_buying_long():
    assert l1.acceptance_from_interpretation("IB breakout to upside - initiative buying", "LONG", False, False) is True


def test_acceptance_caution_is_rejection():
    assert l1.acceptance_from_interpretation("Price above VAH in thin extension - caution", "LONG", False, False) is False


def test_acceptance_poor_high_blocks_long():
    assert l1.acceptance_from_interpretation("IB breakout to upside - initiative buying", "LONG", True, False) is False


def test_acceptance_none_when_no_interp():
    assert l1.acceptance_from_interpretation(None, "LONG", False, False) is None


# --- _decide: pass / asterisk / flow_unavailable / fail -----------------------
def test_decide_pass():
    flow = l1.evaluate_flow(_flow(8_000_000, 1_000_000), "LONG")
    assert l1._decide(flow, {"state": "fresh_accepted"}) == "pass"


def test_decide_asterisk_when_auction_not_fresh():
    flow = l1.evaluate_flow(_flow(8_000_000, 1_000_000), "LONG")
    for st in ("asterisk", "closed", "feed_down"):
        assert l1._decide(flow, {"state": st}) == "asterisk"


def test_decide_fail_on_contradiction():
    flow = l1.evaluate_flow(_flow(8_000_000, 1_000_000), "SHORT")
    assert l1._decide(flow, {"state": "fresh_accepted"}) == "fail"


def test_decide_flow_unavailable_overrides_auction():
    flow = l1.evaluate_flow(None, "LONG")
    assert l1._decide(flow, {"state": "fresh_accepted"}) == "flow_unavailable"


def test_decide_inconclusive_flow_is_asterisk():
    flow = l1.evaluate_flow(_flow(5_100_000, 4_900_000), "LONG")
    assert l1._decide(flow, {"state": "fresh_accepted"}) == "asterisk"


# --- flag gating + scope ------------------------------------------------------
def test_gate_returns_none_when_flag_off(monkeypatch):
    monkeypatch.delenv("L1_GATE_SHADOW", raising=False)
    importlib.reload(l1)
    import asyncio
    assert asyncio.run(l1.evaluate_l1_gate({"ticker": "SPY", "direction": "LONG"})) is None


def test_gate_out_of_scope_for_non_liquid(monkeypatch):
    monkeypatch.setenv("L1_GATE_SHADOW", "true")
    importlib.reload(l1)
    import asyncio
    tag = asyncio.run(l1.evaluate_l1_gate({"ticker": "RIVN", "direction": "LONG", "triggering_factors": {}}))
    assert tag["gate"] == "out_of_scope"
    monkeypatch.delenv("L1_GATE_SHADOW", raising=False)
    importlib.reload(l1)
