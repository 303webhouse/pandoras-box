"""B8 section 1: flip conditions with counters, and the two things it must never claim.

R-IV.1243(e) settles what this section is NOT: there is no distance-to-flip, because the v1
classifier takes a label when a SET of conditions holds rather than when one score crosses a
line. The second thing it must not claim was found by looking at the output rather than the
spec, and it has its own test below: section 2's order is a SEQUENCE, not a risk axis.
"""
from __future__ import annotations

from models import regime_flip_triggers_b8 as ft
from models.regime_classifier import load_rules

RULES = load_rules()


def _snap(shown, candidate=None, banked=None, held=None):
    return {"regime_label": shown, "raw_regime_key": candidate,
            "pending_closes": banked, "held_sessions": held}


# ── 1. the counter belongs to the candidate ───────────────────────────────

def test_THE_RULED_SHAPE_IS_A_CONDITION_A_TARGET_AND_A_COUNTER():
    """R-IV.1243(e)'s own example: "2nd SPY close below 50d -> CORRECTION . 1 of 2"."""
    out = ft.flip_triggers(_snap("narrow_uptrend", "correction", 1, 7), RULES)
    head = out["in_progress"]["headline"]
    assert "CORRECTION" in head
    assert "1 of 2" in head
    assert "50d" in head, "the condition, not a score"
    assert out["in_progress"]["counter"] == {"banked": 1, "needed": 2, "text": "1 of 2"}


def test_THE_COUNTER_IS_ONLY_SHOWN_FOR_THE_LABEL_BEING_PROPOSED():
    """`pending_closes` counts closes banked toward the CANDIDATE. Printing it beside a
    neighbour nothing is proposing would attach a real number to the wrong label, which is the
    most convincing kind of wrong figure."""
    out = ft.flip_triggers(_snap("uptrend", "correction", 1, 7), RULES)
    assert out["in_progress"]["counter"] is not None
    assert out["down_order"]["counter"] is None
    assert out["up_order"]["counter"] is None


def test_NO_CANDIDATE_MEANS_NO_IN_PROGRESS_BLOCK():
    """When the classifier proposes the label already shown, nothing is in progress, and the
    section shows the standing conditions only rather than an empty counter."""
    out = ft.flip_triggers(_snap("uptrend", "uptrend", 0, 12), RULES)
    assert out["in_progress"] is None
    assert out["candidate_differs"] is False
    assert out["down_order"]["headline"] and out["up_order"]["headline"]


# ── 2. the two claims this section must not make ──────────────────────────

def test_NO_DISTANCE_TO_FLIP_IS_EVER_PRODUCED():
    """R-IV.1243(e), and v2.js said it first. The payload carries the reason, so the next
    author reads WHY rather than only seeing the absence."""
    out = ft.flip_triggers(_snap("uptrend", "correction", 1, 7), RULES)
    assert "no number whose shrinking means closer" in out["no_distance_estimate"]
    blob = repr(out).lower()
    for banned in ("points away", "distance_to", "pts_to_flip", "% to flip"):
        assert banned not in blob, banned


def test_THE_ORDER_IS_A_SEQUENCE_NOT_A_RISK_AXIS():
    """FOUND BY READING THE OUTPUT, not the spec. The ruling says "both directions", which
    reads naturally as toward risk and toward risk-on -- but one step DOWN section 2's order
    from UPTREND is MELT UP, which is MORE risk-on, not less. R-IV.1198(c) found the same thing
    measuring flips: range_chop and melt_up sit between correction and uptrend.

    So the blocks are named for positions in the published order, never for a risk direction,
    and the payload says why. Shipping "toward risk -> MELT UP" would have been a wrong claim
    in the one place a reader would trust it.
    """
    out = ft.flip_triggers(_snap("uptrend", None, 0, 9), RULES)
    assert out["down_order"]["target"] == "melt_up"
    assert "published order" in out["down_order"]["direction"]
    assert "toward risk" not in out["down_order"]["direction"]
    assert "not a risk axis" in out["order_note"]
    assert "MELT UP" in out["order_note"], "the example is named, so the claim is checkable"


# ── 3. the gates come from the rules file ─────────────────────────────────

def test_THE_CONDITIONS_CARRY_THE_RULES_FILES_OWN_THRESHOLDS():
    """A hard-coded "2 indices" would quietly disagree with the rules file the day someone
    edits it. The numbers are formatted IN from `thresholds`."""
    th = RULES["thresholds"]
    text = ft.condition_text("uptrend", th)
    assert str(int(th["uptrend_sectors_above_50dma_min"])) in text
    assert str(int(th["uptrend_sectors_total"])) in text
    # 20.0 prints as 20: a threshold shown as "20.0%" reads as precision it does not have.
    assert "20.0" not in ft.condition_text("bear_market", th)
    assert "20%" in ft.condition_text("bear_market", th)


def test_A_MISSING_THRESHOLD_IS_REPORTED_NOT_FILLED_IN():
    """A condition sentence with an invented number in it is worse than no sentence."""
    text = ft.condition_text("uptrend", {})
    assert "condition unavailable" in text and "uptrend_sectors" in text


def test_A_LABEL_WITH_NO_PUBLISHED_CONDITION_SAYS_SO():
    """A blank reads as "nothing required"."""
    assert ft.condition_text("not_a_label", RULES["thresholds"]) is None
    out = ft.direction_block("not_a_label", rules=RULES, candidate=None, banked=None,
                             direction="d")
    assert "no condition published" in out["condition"]


def test_THE_TOWARD_RISK_EXEMPTION_IS_NAMED_ON_THE_BLOCK_IT_APPLIES_TO():
    """`breakdown` and `crash_liquidation` skip the minimum-sessions hold but STILL need their
    closes. A reader who does not know that would read "1 of 2" on breakdown as five sessions
    away."""
    n, basis = ft.closes_needed("breakdown", RULES["hysteresis"])
    assert n == RULES["hysteresis"]["toward_risk_still_requires_closes"]
    assert "exempt from" in basis and "minimum hold" in basis
    n2, basis2 = ft.closes_needed("uptrend", RULES["hysteresis"])
    assert "exempt" not in basis2 and "minimum hold" in basis2


# ── 4. the ends of the order ──────────────────────────────────────────────

def test_THE_END_OF_THE_ORDER_HAS_NO_NEIGHBOUR_AND_STILL_HAS_A_HEADLINE():
    """A wrap-around would offer a flip from crash_liquidation straight to narrow_uptrend. And
    a block with no headline made the renderer read a missing key, which is how a section goes
    blank in front of Nick instead of saying there is nothing further this way."""
    order = [str(x).lower() for x in RULES["order"]]
    assert ft.neighbours(order[0], order)[0] is None
    assert ft.neighbours(order[-1], order)[1] is None
    out = ft.flip_triggers(_snap(order[-1], None, 0, 3), RULES)
    assert out["up_order"]["target"] is None
    assert "no further label" in out["up_order"]["headline"]


def test_AN_UNKNOWN_SHOWN_LABEL_HAS_NO_NEIGHBOURS_RATHER_THAN_THE_FIRST_TWO():
    assert ft.neighbours("not_a_label", [str(x).lower() for x in RULES["order"]]) == (None, None)
    assert ft.neighbours(None, ["a", "b"]) == (None, None)
