"""The name registry and the APIS / KODIAK tags (R-IV.843(e)).

The first two tests run a REAL scoring cycle: a signal goes through `apply_scoring` with only
the scorer pinned to a score of 85 or more. The pipeline's own relabel must keep the stored
`signal_type` APIS_CALL / KODIAK_CALL (frozen), record `upgraded_from` before the overwrite,
and serve the BASE type's display_label with the tag beside it.
"""

import json

import pytest

from config import strategy_aliases as sa
from config.strategy_class import ROSTER, SHADOW, strategy_class


def _pin_score(monkeypatch, score=95):
    import signals.pipeline as pl

    def _score(signal_data, current_bias, **_):
        return score, "ALIGNED", {"calculation": {"raw_score": score}}

    monkeypatch.setattr(pl, "calculate_signal_score", _score)
    monkeypatch.delenv("L0_APIS_ENFORCE", raising=False)   # shadow = label always applies


def _sig(signal_type, direction, strategy="CTA Scanner"):
    return {"signal_id": "t-1", "ticker": "AAPL", "strategy": strategy, "direction": direction,
            "signal_type": signal_type, "entry_price": 100.0, "timeframe": "D"}


@pytest.mark.asyncio
async def test_a_long_upgraded_to_apis_keeps_its_name(monkeypatch):
    from signals.pipeline import apply_scoring
    _pin_score(monkeypatch)
    out = await apply_scoring(_sig("GOLDEN_TOUCH", "LONG"))

    assert out["score"] >= 85
    assert out["signal_type"] == "APIS_CALL"                      # stored type: unchanged rule
    assert out["triggering_factors"]["upgraded_from"] == "GOLDEN_TOUCH"
    sa.attach_codename(out)
    assert out["display_label"] == "MIDAS | Golden Touch"
    assert out["upgrade_tag"] == "APIS"
    assert out["codename"] == "Apis"                               # legacy field, for its readers


@pytest.mark.asyncio
async def test_a_short_upgraded_to_kodiak_keeps_its_name(monkeypatch):
    from signals.pipeline import apply_scoring
    _pin_score(monkeypatch)
    out = await apply_scoring(_sig("BEARISH_BREAKDOWN", "SHORT"))

    assert out["signal_type"] == "KODIAK_CALL"
    assert out["triggering_factors"]["upgraded_from"] == "BEARISH_BREAKDOWN"
    sa.attach_codename(out)
    assert out["display_label"] == "PHAETHON | Bearish Breakdown"
    assert out["upgrade_tag"] == "KODIAK"


@pytest.mark.asyncio
async def test_below_85_there_is_no_upgrade_and_no_record(monkeypatch):
    from signals.pipeline import apply_scoring
    _pin_score(monkeypatch, score=60)
    out = await apply_scoring(_sig("GOLDEN_TOUCH", "LONG"))
    assert out["signal_type"] == "GOLDEN_TOUCH"
    assert "upgraded_from" not in out["triggering_factors"]
    assert sa.attach_codename(out)["upgrade_tag"] is None


def test_a_historical_row_with_only_l0_shadow_recovers_its_base():
    """Rows written before upgraded_from existed: the L0 gate recorded the type before scoring.
    Served from the DB, triggering_factors may arrive as JSON text."""
    row = {"signal_type": "APIS_CALL", "strategy": "CTA Scanner",
           "triggering_factors": json.dumps({"l0_shadow": {"signal_type": "TWO_CLOSE_VOLUME",
                                                            "would_suppress": False}})}
    sa.attach_codename(row)
    assert row["display_label"] == "PERSEPHONE | Two-Close Turn"
    assert row["upgrade_tag"] == "APIS"
    assert row["signal_type"] == "APIS_CALL"


def test_upgraded_from_wins_over_l0_shadow():
    tf = {"upgraded_from": "GOLDEN_TOUCH", "l0_shadow": {"signal_type": "PULLBACK_ENTRY"}}
    assert sa.display_label("APIS_CALL", "CTA Scanner", tf) == "MIDAS | Golden Touch"


@pytest.mark.parametrize("st, expected", [
    ("APIS_CALL", "APIS | Upgraded Long (type not recorded)"),
    ("KODIAK_CALL", "KODIAK | Upgraded Short (type not recorded)"),
])
def test_a_row_with_neither_says_so(st, expected):
    assert sa.display_label(st, "CTA Scanner", {"score": 90}) == expected
    assert sa.display_label(st, "CTA Scanner", None) == expected


def test_an_upgraded_base_with_no_name_falls_back_not_blank():
    tf = {"l0_shadow": {"signal_type": "PULLBACK_ENTRY"}}           # suppressed, unnamed
    assert sa.display_label("APIS_CALL", "CTA Scanner", tf) == "Pullback Entry"


def test_a_rescore_of_an_upgraded_row_keeps_the_first_base():
    sig = {"signal_type": "APIS_CALL", "triggering_factors": {"upgraded_from": "GOLDEN_TOUCH"}}
    sa.record_upgraded_from(sig)
    assert sig["triggering_factors"]["upgraded_from"] == "GOLDEN_TOUCH"
    fresh = {"signal_type": "APIS_CALL", "triggering_factors": {}}
    sa.record_upgraded_from(fresh)                                   # never records a tag as base
    assert "upgraded_from" not in fresh["triggering_factors"]


@pytest.mark.parametrize("st, strat, expected", [
    ("SELL_RIP_EARLY", "sell_the_rip", "ACHILLES | Sell the Rip"),
    (None, "sell_the_rip", "ACHILLES | Sell the Rip"),
    ("TRAPPED_SHORTS", "CTA Scanner", "HECTOR | Trapped Shorts"),
    ("NEMESIS_LONG", "nemesis_wrr", "PHOENIX | Uptrend Dip-Buy"),
    ("WRR_SHORT", None, "NEMESIS | Washout Reversal"),
    ("TWO_CLOSE_VOLUME", "Crypto Scanner", "PERSEPHONE | Two-Close Turn"),
    ("RESISTANCE_REJECTION", "CTA Scanner", "SISYPHUS | Resistance Rejection"),
    ("DEATH_CROSS", None, "HADES | Death Cross"),
    ("ARTEMIS_SHORT", "Artemis", "ARTEMIS | VWAP Band Short"),
    ("EXHAUSTION_BEAR", "Exhaustion", "HYPNOS | Exhaustion Reversal"),
    ("SCOUT_ALERT", "Scout Sniper", "ORION | Scout Sniper"),
    ("PHALANX_BULL", "Phalanx", "AJAX | Absorption Wall"),
    ("FOOTPRINT_SHORT", "Footprint_Imbalance", "CYCLOPS | Footprint"),
    ("WH_REVERSAL", "WH-REVERSAL", "PROTEUS | Whale Reversal"),
    ("WHALE_LONG", "Whale_Hunter", "TRITON | Whale Hunting"),
    ("CIRCES_STEW", "circes_stew", "CIRCE'S STEW | Fade the Breakout"),
    ("ICARUS", None, "ICARUS | Fade VAH"),
    ("HERA", None, "HERA | 3-10 Oscillator Cross"),
])
def test_the_approved_names(st, strat, expected):
    assert sa.display_label(st, strat) == expected


def test_a_suppressed_long_is_not_named_by_its_shorts_strategy():
    assert sa.display_label("ARTEMIS_LONG", "Artemis") == "Artemis Long"


@pytest.mark.parametrize("st, strat, expected", [
    ("WH_ACCUMULATION", "WH-ACCUMULATION", "Wh Accumulation"),
    ("DARK_POOL", "UW_FLOW", "Dark Pool"),
    (None, None, sa.UNNAMED),
    ("", "", sa.UNNAMED),
])
def test_unnamed_types_get_a_fallback_never_blank(st, strat, expected):
    assert sa.display_label(st, strat) == expected


def test_odysseus_is_used_nowhere():
    names = {name for name, *_ in sa.REGISTRY}
    assert "ODYSSEUS" not in names
    assert all("ODYSSEUS" not in v.upper() for v in sa.CODENAME_BY_SIGNAL_TYPE.values())


def test_the_legacy_codename_map_agrees_with_the_registry():
    """One author: every legacy codename that names the same identifier as the registry must be
    the registry's name. APIS / KODIAK are tags, not registry names, and are exempt."""
    for st, legacy in sa.CODENAME_BY_SIGNAL_TYPE.items():
        if st in sa.UPGRADE_TAGS:
            continue
        label = sa.display_label(st)
        assert label.split(" | ")[0] == legacy.upper(), (st, legacy, label)
    for strat, legacy in sa.CODENAME_BY_STRATEGY.items():
        label = sa.display_label(None, strat)
        assert label.split(" | ")[0] == legacy.upper(), (strat, legacy, label)


def test_the_class_readers_still_place_rows_as_before():
    assert strategy_class("APIS_CALL", "CTA Scanner") == ROSTER     # "Apis" readers unchanged
    assert strategy_class("KODIAK_CALL", "CTA Scanner") == ROSTER
    assert strategy_class("GOLDEN_TOUCH", "CTA Scanner") == ROSTER
    assert strategy_class("NEMESIS_LONG", "nemesis_wrr") == SHADOW  # suppressed, as L0 says
