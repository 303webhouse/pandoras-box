"""L0.4 — strategy alias / codename map tests."""

import pytest

from config.strategy_aliases import (
    codename,
    display_name,
    attach_codename,
    CODENAME_BY_SIGNAL_TYPE,
    CODENAME_BY_STRATEGY,
)


# --- signal_type-keyed mappings ----------------------------------------
@pytest.mark.parametrize("st,expected", [
    ("GOLDEN_TOUCH", "Midas"),
    ("TRAPPED_SHORTS", "Hector"),
    ("APIS_CALL", "Apis"),
    ("KODIAK_CALL", "Kodiak"),
    ("SELL_RIP_EMA", "Achilles"),
    ("SELL_RIP_VWAP", "Achilles"),
    ("SELL_RIP_EARLY", "Achilles"),
    ("NEMESIS_LONG", "Nemesis"),
    ("WHALE_LONG", "Triton"),
])
def test_signal_type_codenames(st, expected):
    assert codename(st) == expected


# --- multi-signal_type family resolves via strategy --------------------
def test_sell_the_rip_strategy_maps_to_achilles():
    # A SELL_RIP_* row whose signal_type isn't individually listed still
    # resolves through the strategy key.
    assert codename("SELL_RIP_SOMETHING_NEW", "sell_the_rip") == "Achilles"
    assert codename(None, "sell_the_rip") == "Achilles"
    assert codename("", "whale_hunter") == "Triton"


# --- precedence: signal_type beats strategy ----------------------------
def test_signal_type_takes_precedence_over_strategy():
    # GOLDEN_TOUCH (Midas) wins even if strategy maps elsewhere
    assert codename("GOLDEN_TOUCH", "sell_the_rip") == "Midas"


# --- case / whitespace insensitivity -----------------------------------
@pytest.mark.parametrize("st", ["golden_touch", " GOLDEN_TOUCH ", "Golden_Touch"])
def test_signal_type_case_insensitive(st):
    assert codename(st) == "Midas"


def test_strategy_case_insensitive():
    assert codename(None, "Sell_The_Rip") == "Achilles"
    assert codename(None, " WHALE_HUNTER ") == "Triton"


# --- unmapped → None (the prefer-pattern relies on this) ---------------
@pytest.mark.parametrize("st,strat", [
    ("ARTEMIS_LONG", "Artemis"),
    ("PULLBACK_ENTRY", "CTA Scanner"),
    ("FOOTPRINT_LONG", "Footprint_Imbalance"),
    ("TOTALLY_UNKNOWN", "mystery"),
])
def test_unmapped_returns_none(st, strat):
    assert codename(st, strat) is None


# --- None / blank safety ------------------------------------------------
def test_none_and_blank_safe():
    assert codename(None) is None
    assert codename(None, None) is None
    assert codename("", "") is None
    assert codename("   ", "   ") is None


# --- display_name: codename or humanized fallback ----------------------
def test_display_name_uses_codename_when_mapped():
    assert display_name("GOLDEN_TOUCH") == "Midas"
    assert display_name("SELL_RIP_EMA", "sell_the_rip") == "Achilles"


def test_display_name_humanizes_unmapped():
    assert display_name("ARTEMIS_LONG") == "Artemis Long"
    assert display_name("PULLBACK_ENTRY") == "Pullback Entry"
    assert display_name(None, "CTA Scanner") == "Cta Scanner"


def test_display_name_blank_is_empty():
    assert display_name(None, None) == ""
    assert display_name("", "") == ""


# --- attach_codename: additive, never mutates raw ----------------------
def test_attach_codename_adds_field_without_mutating_raw():
    sig = {"signal_type": "GOLDEN_TOUCH", "strategy": "CTA Scanner", "score": 80}
    out = attach_codename(sig)
    assert out is sig  # in place
    assert sig["codename"] == "Midas"
    # raw untouched
    assert sig["signal_type"] == "GOLDEN_TOUCH"
    assert sig["strategy"] == "CTA Scanner"
    assert sig["score"] == 80


def test_attach_codename_sets_none_for_unmapped():
    sig = {"signal_type": "ARTEMIS_LONG", "strategy": "Artemis"}
    attach_codename(sig)
    assert sig["codename"] is None


def test_attach_codename_non_dict_safe():
    assert attach_codename(None) is None  # type: ignore[arg-type]


# --- map integrity ------------------------------------------------------
def test_map_keys_are_normalized():
    for k in CODENAME_BY_SIGNAL_TYPE:
        assert k == k.upper(), f"signal_type key {k!r} must be UPPER"
    for k in CODENAME_BY_STRATEGY:
        assert k == k.lower(), f"strategy key {k!r} must be lower"
