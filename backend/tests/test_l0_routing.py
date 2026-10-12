"""L0.1a — suppression gate (SHADOW) tests."""

import importlib

import pytest

import config.l0_routing as l0


def _decide(signal_type, ticker=None):
    return l0.evaluate_l0_gate({"signal_type": signal_type, "ticker": ticker})


# --- unconditional suppress set ----------------------------------------
@pytest.mark.parametrize("st", ["HOLY_GRAIL_1H", "HOLY_GRAIL_15M", "PULLBACK_ENTRY", "TRAPPED_LONGS", "ARTEMIS_LONG"])
def test_unconditional_suppress(st):
    d = _decide(st, ticker="AAPL")  # liquid ticker must not rescue these
    assert d["rule"] == l0.RULE_SUPPRESS
    assert d["would_suppress"] is True


# --- RESISTANCE_REJECTION: liquid-conditional ---------------------------
@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "NVDA", "META"])
def test_resistance_rejection_liquid_kept(ticker):
    d = _decide("RESISTANCE_REJECTION", ticker=ticker)
    assert d["rule"] == l0.RULE_SUPPRESS_IF_NON_LIQUID
    assert d["is_liquid"] is True
    assert d["would_suppress"] is False


@pytest.mark.parametrize("ticker", ["AON", "VRTX", "RIVN", "DOCU"])
def test_resistance_rejection_non_liquid_suppressed(ticker):
    d = _decide("RESISTANCE_REJECTION", ticker=ticker)
    assert d["is_liquid"] is False
    assert d["would_suppress"] is True


# --- keepers untouched --------------------------------------------------
@pytest.mark.parametrize("st", [
    "GOLDEN_TOUCH", "TRAPPED_SHORTS", "TWO_CLOSE_VOLUME", "APIS_CALL",
    "SELL_RIP_EMA", "ARTEMIS_SHORT", "FOOTPRINT_LONG",
    "KODIAK_CALL", "SOME_UNKNOWN_TYPE",
])
def test_keepers_never_suppressed(st):
    # keepers must never be flagged would_suppress, regardless of ticker liquidity
    for ticker in ("AON", "SPY", None):
        d = _decide(st, ticker=ticker)
        assert d["rule"] == l0.RULE_KEEP
        assert d["would_suppress"] is False


# --- robustness ---------------------------------------------------------
def test_blank_signal_type_is_kept():
    d = _decide("", ticker="SPY")
    assert d["would_suppress"] is False
    d2 = l0.evaluate_l0_gate({})
    assert d2["would_suppress"] is False


def test_whitespace_signal_type_normalized():
    d = _decide("  HOLY_GRAIL_1H  ", ticker="AAPL")
    assert d["would_suppress"] is True


def test_does_not_mutate_input():
    sig = {"signal_type": "HOLY_GRAIL_1H", "ticker": "AAPL"}
    before = dict(sig)
    l0.evaluate_l0_gate(sig)
    assert sig == before


def test_decision_shape():
    d = _decide("HOLY_GRAIL_1H", ticker="AAPL")
    assert set(d) == {"v", "mode", "signal_type", "rule", "would_suppress", "is_liquid", "reason"}
    assert d["v"] == l0.L0_SHADOW_VERSION


# --- ENFORCE is the default (2026-07-03 flip); L0_ENFORCE=false is rollback ----
def test_default_mode_is_enforce(monkeypatch):
    monkeypatch.delenv("L0_ENFORCE", raising=False)
    importlib.reload(l0)
    assert l0._enforce_enabled() is True
    d = l0.evaluate_l0_gate({"signal_type": "HOLY_GRAIL_1H", "ticker": "AAPL"})
    assert d["mode"] == "enforce"
    # should_divert is True under the default-enforce for a would-suppress decision
    assert l0.should_divert(d) is True


def test_rollback_to_shadow_via_explicit_false(monkeypatch):
    # The single-flag rollback: L0_ENFORCE=false returns to shadow.
    monkeypatch.setenv("L0_ENFORCE", "false")
    importlib.reload(l0)
    assert l0._enforce_enabled() is False
    d = l0.evaluate_l0_gate({"signal_type": "HOLY_GRAIL_1H", "ticker": "AAPL"})
    assert d["mode"] == "shadow"
    assert l0.should_divert(d) is False
    monkeypatch.delenv("L0_ENFORCE", raising=False)
    importlib.reload(l0)


def test_enforce_flag_parsing(monkeypatch):
    # Enforce-y values AND empty/unset (Railway '' -> default -> ENFORCE).
    for val in ("true", "1", "YES", "on", ""):
        monkeypatch.setenv("L0_ENFORCE", val)
        importlib.reload(l0)
        assert l0._enforce_enabled() is True
    # Explicit rollback values -> shadow.
    for val in ("false", "0", "no", "off"):
        monkeypatch.setenv("L0_ENFORCE", val)
        importlib.reload(l0)
        assert l0._enforce_enabled() is False
    monkeypatch.delenv("L0_ENFORCE", raising=False)
    importlib.reload(l0)


def test_should_divert_true_only_under_enforce(monkeypatch):
    monkeypatch.setenv("L0_ENFORCE", "true")
    importlib.reload(l0)
    d = l0.evaluate_l0_gate({"signal_type": "HOLY_GRAIL_1H", "ticker": "AAPL"})
    assert l0.should_divert(d) is True
    keeper = l0.evaluate_l0_gate({"signal_type": "GOLDEN_TOUCH", "ticker": "AAPL"})
    assert l0.should_divert(keeper) is False
    monkeypatch.delenv("L0_ENFORCE", raising=False)
    importlib.reload(l0)
