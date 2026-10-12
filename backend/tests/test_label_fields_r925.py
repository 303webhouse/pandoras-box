"""display_label and upgrade_tag — R-IV.833, authored under R-IV.925(b).

THE DESCRIPTION IS READ FROM THE CARD, NOT COPIED. `docs/strategies/*.md` already opens with
exactly the ruled shape — "# HECTOR | Trapped Shorts (`TRAPPED_SHORTS`)" — so the card is the one
author of a strategy's name, description AND which types it covers. Keeping a second copy in
Python would drift the first time a card is reworded, which is the failure this codebase keeps
finding. It is also why the ruling specifies a no-card fallback: with no card there is nothing to
read.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from config import strategy_aliases as sa  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    sa.reset_card_cache_for_tests()
    yield
    sa.reset_card_cache_for_tests()


# ── upgrade_tag: exactly two prefixes, nothing else ────────────────────────

def test_APIS_prefix_tags_APIS():
    assert sa.upgrade_tag("APIS_CALL") == "APIS"


def test_KODIAK_prefix_tags_KODIAK():
    assert sa.upgrade_tag("KODIAK_CALL") == "KODIAK"


@pytest.mark.parametrize("t", [
    "GOLDEN_TOUCH", "TRAPPED_SHORTS", "BEARISH_BREAKDOWN", "SELL_RIP_EMA", "WHALE_LONG",
    "NEMESIS_LONG", "WRR_LONG", "", None,
])
def test_everything_else_has_NO_tag(t):
    """Absent, not an empty string: "no tag" and "a tag that is blank" are different facts and
    the frontend tests truthiness."""
    assert sa.upgrade_tag(t) is None


def test_the_tag_is_a_bare_upper_case_word():
    for t in ("APIS_CALL", "KODIAK_CALL"):
        tag = sa.upgrade_tag(t)
        assert tag and tag.isupper() and tag.isalpha(), tag


def test_a_type_merely_CONTAINING_apis_is_not_tagged():
    """Keyed on the PREFIX as ruled. "RAPIS_CALL" or "MY_APIS_THING" must not tag."""
    assert sa.upgrade_tag("RAPIS_CALL") is None
    assert sa.upgrade_tag("MY_APIS_THING") is None


def test_the_tag_keys_on_the_TYPE_not_the_strategy():
    """So a strategy that happens to emit an APIS_ type cannot tag its other types too."""
    assert sa.upgrade_tag("GOLDEN_TOUCH", "apis_scanner") is None


def test_casing_of_the_input_does_not_matter():
    assert sa.upgrade_tag("apis_call") == "APIS"


# ── display_label: "CODENAME | Description", or the codename alone ─────────

def test_a_mapped_type_with_a_card_gets_both_parts():
    label = sa.display_label("TRAPPED_SHORTS")
    assert label.startswith("Hector | ")
    assert "Trapped Shorts" in label


def test_the_backticked_type_list_is_stripped_from_the_description():
    """The card title ends "(`TRAPPED_SHORTS`)"; that is a reference, not description."""
    assert "`" not in sa.display_label("TRAPPED_SHORTS")
    assert "TRAPPED_SHORTS" not in sa.display_label("TRAPPED_SHORTS").split("|")[1]


def test_a_codename_with_NO_card_is_returned_ALONE_with_no_pipe():
    """The ruled fallback. A dangling separator would read as a missing value rather than an
    absent one — and this is not hypothetical: APIS and KODIAK have no cards."""
    for t in ("APIS_CALL", "KODIAK_CALL", "WHALE_LONG"):
        label = sa.display_label(t)
        assert "|" not in label, (t, label)
        assert label


def test_the_two_TAGGED_types_are_exactly_the_two_with_no_card():
    """Worth pinning because it is surprising: the only types that earn an upgrade tag are the
    only two whose label is a bare codename."""
    assert sa.upgrade_tag("APIS_CALL") == "APIS"
    assert "|" not in sa.display_label("APIS_CALL")
    assert sa.upgrade_tag("KODIAK_CALL") == "KODIAK"
    assert "|" not in sa.display_label("KODIAK_CALL")


def test_a_card_whose_codename_is_in_no_map_still_supplies_the_label():
    """Seven of eleven cards name a codename `CODENAME_BY_SIGNAL_TYPE` maps nothing to, so their
    types produced "Bearish Breakdown" instead of "PHAETHON | Bearish Breakdown". The card's own
    title states the pairing, so it is READ, not invented."""
    assert sa.display_label("BEARISH_BREAKDOWN") == "PHAETHON | Bearish Breakdown"
    assert sa.display_label("ARTEMIS_SHORT").startswith("ARTEMIS | ")
    assert sa.display_label("TWO_CLOSE_VOLUME").startswith("PERSEPHONE | ")


def test_the_hardcoded_map_still_WINS_over_the_card():
    """Order matters: the existing map stays authoritative, so nothing that works today moves."""
    assert sa.display_label("TRAPPED_SHORTS").startswith("Hector")   # the map's casing, not the card's


def test_an_unknown_type_falls_back_to_a_humanised_name():
    label = sa.display_label("SOME_NEW_THING")
    assert label and "|" not in label


def test_blank_input_gives_an_empty_string():
    assert sa.display_label(None) == ""
    assert sa.display_label("") == ""


# ── it degrades, rather than failing, with no cards present ───────────────

def test_with_no_cards_directory_every_label_is_the_codename_alone(monkeypatch):
    """The ruled fallback IS the failure mode, so a slimmer image or a different working
    directory degrades predictably instead of raising."""
    monkeypatch.setattr(sa, "_CARDS_DIR", r"C:\no\such\directory")
    sa.reset_card_cache_for_tests()
    assert sa.card_descriptions() == {}
    assert sa.display_label("TRAPPED_SHORTS") == "Hector"
    assert "|" not in sa.display_label("TRAPPED_SHORTS")


# ── attach_label_fields is additive ───────────────────────────────────────

def test_attach_sets_both_fields_without_touching_the_originals():
    sig = {"signal_type": "APIS_CALL", "strategy": "Apis Scanner", "score": 70}
    out = sa.attach_label_fields(sig)
    assert out is sig
    assert sig["display_label"] == "Apis"
    assert sig["upgrade_tag"] == "APIS"
    assert sig["signal_type"] == "APIS_CALL" and sig["strategy"] == "Apis Scanner"


def test_attach_sets_upgrade_tag_to_None_rather_than_omitting_it():
    """The frontend reads `s.upgrade_tag`; a present null is a different contract from a missing
    key, and PR #65's fallback is written against a present field."""
    sig = sa.attach_label_fields({"signal_type": "GOLDEN_TOUCH"})
    assert "upgrade_tag" in sig
    assert sig["upgrade_tag"] is None


def test_attach_tolerates_a_non_dict():
    assert sa.attach_label_fields(None) is None
