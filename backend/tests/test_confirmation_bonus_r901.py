"""The confirmation bonus counts TYPES, not rows — R-IV.901(e).

LAB's finding: the bonus was `min(5, max(0, (signal_count - 1) * 2))`, and `signal_count` is
`1 + len(related_signals)` — a count of ROWS. So one signal re-firing inside the grouping window
earned +2 for confirming itself, and a thesis supported by one scanner twice scored the same as
one supported by two independent scanners. That difference is the entire point of the bonus.

The same expression lived in TWO files, so a fix to one would have left the other paying the old
figure and the two surfaces disagreeing about the same idea's score.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from scoring.confirmation_bonus import (  # noqa: E402
    MAX_BONUS, POINTS_PER_EXTRA_TYPE, VERSION, compute, distinct_supporting_types, legacy_v1,
)


def _s(t):
    return {"signal_type": t}


# ── THE DEFECT: a same-type re-fire must never count ───────────────────────

def test_a_same_type_refire_earns_NOTHING():
    """The whole ruling. Two rows, one type: the signal confirming itself is not confirmation."""
    bonus, prov = compute(_s("TRAPPED_SHORTS"), [_s("TRAPPED_SHORTS")])
    assert bonus == 0, prov
    assert prov["distinct_type_count"] == 1
    assert prov["rows_considered"] == 2


def test_the_old_rule_WOULD_have_paid_for_that():
    """Pinned so the change is legible: the same shape scored +2 before. Without this, "the
    bonus changed" has no number it changed from."""
    assert legacy_v1(2) == 2
    assert compute(_s("TRAPPED_SHORTS"), [_s("TRAPPED_SHORTS")])[0] == 0


def test_three_refires_of_one_type_still_earn_nothing():
    bonus, _ = compute(_s("GOLDEN_TOUCH"), [_s("GOLDEN_TOUCH"), _s("GOLDEN_TOUCH")])
    assert bonus == 0
    assert legacy_v1(3) == 4, "the old rule paid 4 for this"


# ── THE PAIR: genuine confirmation still pays ─────────────────────────────

def test_two_distinct_types_pay_the_first_step():
    bonus, prov = compute(_s("TRAPPED_SHORTS"), [_s("GOLDEN_TOUCH")])
    assert bonus == POINTS_PER_EXTRA_TYPE
    assert prov["distinct_type_count"] == 2


def test_three_distinct_types_pay_two_steps():
    bonus, _ = compute(_s("A_TYPE"), [_s("B_TYPE"), _s("C_TYPE")])
    assert bonus == 2 * POINTS_PER_EXTRA_TYPE


def test_the_cap_still_holds():
    many = [_s("T%d" % i) for i in range(10)]
    bonus, _ = compute(_s("PRIMARY"), many)
    assert bonus == MAX_BONUS


def test_a_lone_signal_earns_nothing():
    assert compute(_s("ONLY"), [])[0] == 0
    assert compute(_s("ONLY"), None)[0] == 0


# ── casing: the Whale_Hunter lesson ───────────────────────────────────────

@pytest.mark.parametrize("second", ["trapped_shorts", "Trapped_Shorts", " TRAPPED_SHORTS "])
def test_casing_and_whitespace_do_not_fake_a_second_type(second):
    """Stored casing is not guaranteed — the strategy column holds `Whale_Hunter`, not
    `whale_hunter` (R-IV.849(d)). Without folding, TRAPPED_SHORTS and Trapped_Shorts would
    count as independent confirmations of each other and the defect would return by a
    different door."""
    bonus, prov = compute(_s("TRAPPED_SHORTS"), [_s(second)])
    assert bonus == 0, prov
    assert prov["distinct_type_count"] == 1


# ── rows without a type ───────────────────────────────────────────────────

def test_a_row_with_no_type_is_not_counted_as_a_type():
    """A missing type is not a confirmation. Counting it would pay for the absence of
    information."""
    bonus, prov = compute(_s("REAL"), [{"ticker": "SPY"}, {"signal_type": None},
                                       {"signal_type": "  "}])
    assert bonus == 0
    assert prov["distinct_type_count"] == 1


def test_a_primary_with_no_type_does_not_crash():
    bonus, prov = compute({}, [_s("B_TYPE")])
    assert bonus == 0          # one usable type only
    assert prov["distinct_type_count"] == 1


def test_types_are_reported_in_first_seen_order():
    """So two logs of the same group read the same way."""
    assert distinct_supporting_types(_s("Z"), [_s("A"), _s("M")]) == ["Z", "A", "M"]


# ── it is versioned, and single-authored ──────────────────────────────────

def test_the_version_travels_with_the_result():
    _, prov = compute(_s("A"), [_s("B")])
    assert prov["confirmation_bonus_version"] == VERSION == 2


def test_both_surfaces_call_the_SAME_author():
    """PARSED, not grepped — and this matters here, because my own grep check matched the
    COMMENT that quotes the old expression. The assertion is that each file's assignment to
    `confirmation_bonus` is a call to the shared module, not an inline formula."""
    import ast

    root = __file__.rsplit("tests", 1)[0]
    for rel in ("api/trade_ideas.py", "signals/feed_service.py"):
        tree = ast.parse(open(root + rel, encoding="utf-8").read())
        calls = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple):
                names = [getattr(e, "id", None) for e in n.targets[0].elts]
                if "confirmation_bonus" in names:
                    calls.append(ast.unparse(n.value))
            elif isinstance(n, ast.Assign):
                if any(getattr(t, "id", None) == "confirmation_bonus" for t in n.targets):
                    calls.append(ast.unparse(n.value))
        assert calls, rel
        for c in calls:
            assert "_conf_compute" in c, (rel, c)
            assert "signal_count" not in c, (rel, "still computing from a ROW count")
