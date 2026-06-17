"""L0.3 — APIS gating tests (apis_eligible + flag-gated apply_apis_label)."""

import importlib

import pytest

from config.liquid_universe import apis_eligible
import config.l0_apis as l0_apis


# --- apis_eligible = not is_liquid -------------------------------------
@pytest.mark.parametrize("liquid_ticker", ["SPY", "QQQ", "NVDA", "GOOGL", "MSFT", "nvda", " spy "])
def test_liquid_tickers_not_eligible(liquid_ticker):
    assert apis_eligible(liquid_ticker) is False


@pytest.mark.parametrize("nonliquid_ticker", ["AON", "RIVN", "DOCU", "PLTR", "F", "SOFI"])
def test_non_liquid_tickers_eligible(nonliquid_ticker):
    assert apis_eligible(nonliquid_ticker) is True


def test_blank_ticker_eligible():
    # blank/None is treated as non-liquid → eligible (no false-withhold)
    assert apis_eligible(None) is True
    assert apis_eligible("") is True


# --- shadow default: behavior UNCHANGED (the key regression) ----------
def test_shadow_default_always_applies(monkeypatch):
    monkeypatch.delenv("L0_APIS_ENFORCE", raising=False)
    importlib.reload(l0_apis)
    assert l0_apis._apis_enforce_enabled() is False
    # flag off → APIS applies for EVERY ticker, liquid or not (unchanged)
    for t in ("NVDA", "SPY", "AON", "RIVN", None, ""):
        assert l0_apis.apply_apis_label(t) is True


# --- enforce: withhold on liquid, apply on non-liquid -----------------
def test_enforce_withholds_on_liquid(monkeypatch):
    monkeypatch.setenv("L0_APIS_ENFORCE", "true")
    importlib.reload(l0_apis)
    assert l0_apis._apis_enforce_enabled() is True
    # liquid → withheld
    for t in ("NVDA", "GOOGL", "SPY", "MSFT"):
        assert l0_apis.apply_apis_label(t) is False
    # non-liquid → applied
    for t in ("AON", "RIVN", "DOCU", "PLTR"):
        assert l0_apis.apply_apis_label(t) is True
    monkeypatch.delenv("L0_APIS_ENFORCE", raising=False)
    importlib.reload(l0_apis)


# --- flag parsing -----------------------------------------------------
def test_flag_parsing(monkeypatch):
    for val in ("true", "1", "YES", "on"):
        monkeypatch.setenv("L0_APIS_ENFORCE", val)
        importlib.reload(l0_apis)
        assert l0_apis._apis_enforce_enabled() is True
    for val in ("false", "0", "", "no"):
        monkeypatch.setenv("L0_APIS_ENFORCE", val)
        importlib.reload(l0_apis)
        assert l0_apis._apis_enforce_enabled() is False
    monkeypatch.delenv("L0_APIS_ENFORCE", raising=False)
    importlib.reload(l0_apis)
