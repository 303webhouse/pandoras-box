"""L0.2 — liquid-ticker allowlist tests."""

import pytest

from config.liquid_universe import (
    INDEX_MACRO,
    SEMIS_AI_TECH,
    LIQUID_UNIVERSE,
    is_liquid,
    normalize_ticker,
)


# --- membership: known liquid names pass --------------------------------
@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "IWM", "HYG", "TLT", "FXI"])
def test_index_macro_members_are_liquid(ticker):
    assert is_liquid(ticker)


@pytest.mark.parametrize("ticker", ["NVDA", "SMH", "XLK", "MSFT", "META", "ZS"])
def test_semis_tech_members_are_liquid(ticker):
    assert is_liquid(ticker)


# --- membership: single-name long tail fails ----------------------------
@pytest.mark.parametrize("ticker", ["AON", "VRTX", "NEM", "RIVN", "DOCU", "LCID", "BA", "F"])
def test_single_names_are_not_liquid(ticker):
    assert not is_liquid(ticker)


# --- case + whitespace handling -----------------------------------------
@pytest.mark.parametrize("raw", ["spy", "Spy", " SPY ", "nvda", "  msft"])
def test_case_and_whitespace_insensitive(raw):
    assert is_liquid(raw)


def test_normalize_ticker():
    assert normalize_ticker("  spy ") == "SPY"
    assert normalize_ticker("NvDa") == "NVDA"
    assert normalize_ticker(None) == ""
    assert normalize_ticker("") == ""
    assert normalize_ticker("   ") == ""


# --- None / blank are non-liquid (deterministic miss, no raise) ----------
@pytest.mark.parametrize("bad", [None, "", "   "])
def test_blank_is_not_liquid(bad):
    assert is_liquid(bad) is False


# --- set integrity ------------------------------------------------------
def test_universe_is_union_of_buckets():
    assert LIQUID_UNIVERSE == (INDEX_MACRO | SEMIS_AI_TECH)


def test_index_macro_is_exhaustive_doc_set():
    # Doc-exhaustive (signal-edge-validation T10). Guard against accidental drift.
    assert INDEX_MACRO == frozenset({"SPY", "QQQ", "IWM", "HYG", "TLT", "FXI"})


def test_no_lowercase_leaked_into_sets():
    for t in LIQUID_UNIVERSE:
        assert t == t.upper(), f"{t!r} is not upper-cased in the allowlist"
