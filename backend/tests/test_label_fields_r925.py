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


# ── upgrade_tag: NOTHING carries one, per R-IV.935(e)2 ────────────────────
#
# R-IV.925(b) gave the tag to APIS_*/KODIAK_* types. R-IV.935(e)2 reverses exactly that:
# those rows carry NO tag, because for them APIS *is* the strategy and its codename is already
# the label ("APIS_CALL" -> "Apis"), so a tag would only restate it. That prefix was the only
# rule granting a tag, so today nothing earns one -- and these tests say so out loud rather
# than being deleted, so the reversal is visible to the next reader.

@pytest.mark.parametrize("t", [
    "APIS_CALL", "KODIAK_CALL", "apis_call", "KODIAK_PUT",
    "GOLDEN_TOUCH", "TRAPPED_SHORTS", "BEARISH_BREAKDOWN", "SELL_RIP_EMA", "WHALE_LONG",
    "NEMESIS_LONG", "WRR_LONG", "RAPIS_CALL", "MY_APIS_THING", "", None,
])
def test_no_type_carries_an_upgrade_tag(t):
    assert sa.upgrade_tag(t) is None


def test_the_APIS_and_KODIAK_rule_is_GONE_not_merely_unreachable():
    """The reversal is in the FUNCTION, not in a caller that happens not to ask. Read from the
    parsed source so the docstring explaining the old rule cannot satisfy this."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(sa.upgrade_tag)))
    fn = tree.body[0]
    body = [n for n in fn.body if not (isinstance(n, ast.Expr)
                                       and isinstance(n.value, ast.Constant))]
    assert len(body) == 1 and isinstance(body[0], ast.Return), ast.dump(fn)
    assert body[0].value.value is None


def test_the_tag_is_still_SERVED_as_a_present_null():
    """"No tag" and "no such field" are different facts; ABACUS reads `s.upgrade_tag` and a
    present null is a different contract from a missing key."""
    sig = sa.attach_label_fields({"signal_type": "APIS_CALL"})
    assert "upgrade_tag" in sig and sig["upgrade_tag"] is None


def test_the_tag_never_stands_in_for_the_label():
    """R-IV.935(e)2's words. APIS_CALL's label is its own codename, with no tag beside it."""
    assert sa.display_label("APIS_CALL") == "Apis"
    assert sa.upgrade_tag("APIS_CALL") is None


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


def test_the_two_cardless_types_are_a_bare_codename_and_nothing_else():
    """APIS and KODIAK have no card, so their label is the codename alone -- and under
    R-IV.935(e)2 there is no tag beside it either."""
    for t, name in (("APIS_CALL", "Apis"), ("KODIAK_CALL", "Kodiak")):
        assert sa.display_label(t) == name
        assert "|" not in sa.display_label(t)
        assert sa.upgrade_tag(t) is None


def test_a_card_whose_codename_is_in_no_map_still_supplies_the_label():
    """Seven of eleven cards name a codename `CODENAME_BY_SIGNAL_TYPE` maps nothing to, so their
    types produced "Bearish Breakdown" instead of "PHAETHON | Bearish Breakdown". The card's own
    title states the pairing, so it is READ, not invented."""
    # TITLE CASE, per R-IV.935(e)3: the card titles are ALL CAPS, the DATA is not, and the
    # page styles the capitals. A codename shouting in the payload cannot be un-shouted by CSS.
    assert sa.display_label("BEARISH_BREAKDOWN") == "Phaethon | Bearish Breakdown"
    assert sa.display_label("ARTEMIS_SHORT").startswith("Artemis | ")
    assert sa.display_label("TWO_CLOSE_VOLUME").startswith("Persephone | ")


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
    assert sig["upgrade_tag"] is None            # R-IV.935(e)2
    assert sig["signal_type"] == "APIS_CALL" and sig["strategy"] == "Apis Scanner"


def test_attach_sets_upgrade_tag_to_None_rather_than_omitting_it():
    """The frontend reads `s.upgrade_tag`; a present null is a different contract from a missing
    key, and PR #65's fallback is written against a present field."""
    sig = sa.attach_label_fields({"signal_type": "GOLDEN_TOUCH"})
    assert "upgrade_tag" in sig
    assert sig["upgrade_tag"] is None


def test_attach_tolerates_a_non_dict():
    assert sa.attach_label_fields(None) is None
