"""HECTOR (TRAPPED_SHORTS) moved to SHADOW — R-IV.878(e).

The same mechanism PHAETHON used: L0 suppression is a SURFACE verdict, not a kill. The row is
still WRITTEN and still GRADED; it just does not reach an actionable feed. A type that stopped
persisting would stop accumulating the record the review needs, which is the whole point of a
shadow.

Both halves are asserted, because "suppressed" and "still stored" are different claims and only
testing the first would pass on a change that killed the type outright.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

TYPE = "TRAPPED_SHORTS"


def _src(rel):
    return open(__file__.rsplit("tests", 1)[0] + rel, encoding="utf-8").read()


def test_it_is_suppressed_at_the_surface():
    from config.l0_routing import SUPPRESS_ALWAYS

    assert TYPE in SUPPRESS_ALWAYS


def test_the_routing_verdict_is_SUPPRESS():
    """Through the real decision function, not by reading the set."""
    from config import l0_routing as l0

    decided = l0.evaluate_l0_gate({"signal_type": TYPE, "ticker": "SPY"})
    assert decided["would_suppress"] is True, decided
    assert decided["rule"] == "SUPPRESS", decided


def test_suppression_does_not_stop_the_row_being_written():
    """THE OTHER HALF. l0_routing computes and TAGS; it never drops or alters persistence. If
    this module ever gained a write-path veto, a shadow would silently become a kill and the
    review it exists to feed would have nothing to read."""
    src = _src(os.path.join("config", "l0_routing.py"))
    assert "NEVER drops or alters persistence" in src
    # The enforce path is SURFACE suppression: a WHERE fragment on read, not a write gate.
    from config.l0_routing import l0_enforce_where_clause

    assert "would_suppress" in l0_enforce_where_clause()


def test_it_is_no_longer_claimed_as_kept_live():
    """The move had to edit FOUR places that named this type as kept: l0_routing's trailing
    comment and the keeper lists in test_nemesis_wiring_r809, test_shadow_and_cohort_r857 and
    test_l0_routing. R-IV.861(c) gave the suppressed SET one author and left its COMPLEMENT with
    four; the suite found the fourth after I thought I had them all. An inverse list is as much
    a copy as the list, and nobody consolidated this half."""
    import re

    src = _src(os.path.join("config", "l0_routing.py"))
    tail = src.split("# Everything not named above is KEPT untouched", 1)[1]
    # ONLY the parenthesised enumeration, not the paragraph around it. A fixed character window
    # swallowed the very line added to RECORD this move ("TRAPPED_SHORTS was on this list
    # until R-IV.878(e)...") and failed on it -- the prose trap, in a test written minutes after
    # filing the lesson. A historical note is not a claim, so the assertion reads the LIST.
    m = re.search(r"\(([^)]*)\)", tail, re.S)
    assert m, "the kept-live enumeration could not be found"
    kept = [x.strip().strip(",") for x in m.group(1).replace("#", " ").split()]
    assert TYPE not in kept, "l0_routing still lists %s as kept live: %s" % (TYPE, kept)
    assert "GOLDEN_TOUCH" in kept, "the enumeration was not parsed: %s" % kept


def test_the_reason_is_recorded_as_a_surface_verdict():
    src = _src(os.path.join("config", "l0_routing.py"))
    assert "R-IV.878(e) shadow" in src
    assert "still WRITTEN and still GRADED" in src


def test_the_pair_a_live_type_is_still_live():
    """CONTROL (#30): a change that suppressed everything would pass every test above."""
    from config import l0_routing as l0

    decided = l0.evaluate_l0_gate({"signal_type": "GOLDEN_TOUCH", "ticker": "SPY"})
    assert decided["would_suppress"] is False, decided
