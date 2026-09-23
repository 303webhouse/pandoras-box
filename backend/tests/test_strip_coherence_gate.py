"""R-IV.488(d) — two plus two makes four before the dot turns green.

The 2026-09-23 failure passed every check the board had: fresh as_of,
degraded=false, flatline=false, lime dot reading 'fresh 8m' — over QQQ +0.024%
on a -0.69% tape. Every input the dot consumed was healthy, because none of them
was the arithmetic. A served change is only believable if it equals
spot / prior_close - 1, and nothing compared those three numbers.

Run:  PYTHONPATH=backend python -m pytest backend/tests/test_strip_coherence_gate.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.stable import _incoherent_rows


def row(sym, value, extra, prior, reason=None):
    return {"symbol": sym, "kind": "index", "value": value, "extra": extra,
            "prior_close": prior, "reason": reason}


def test_the_2026_09_23_payload_would_now_be_caught():
    """The real served numbers, with the real prior close they claimed to span."""
    bad = _incoherent_rows([row("QQQ", 0.024, 741.65, 747.46)])
    assert bad == ["QQQ"]          # +0.024% against an implied -0.777%


def test_every_wrong_symbol_from_that_payload_is_caught():
    rows = [row("QQQ", 0.024, 741.65, 747.46), row("IWM", -0.632, 283.77, 287.21),
            row("DIA", -0.718, 516.05, 518.00)]
    assert set(_incoherent_rows(rows)) == {"QQQ", "IWM", "DIA"}


def test_spy_which_was_wrong_by_luck_is_still_coherent_against_its_own_base():
    """SPY's served -0.492% DID close against the base it actually used (773.50).

    This is the honest limit of an arithmetic gate: it proves the row is
    self-consistent, not that the base was the right session. The session gate in
    strip.py is what catches that, and both are needed.
    """
    assert _incoherent_rows([row("SPY", -0.492, 769.70, 773.50)]) == []
    # Against the TRUE prior close it does not close — but that is a different check.
    assert _incoherent_rows([row("SPY", -0.492, 769.70, 773.38)]) == []  # within 0.02pp tol


def test_the_fixed_live_values_are_coherent():
    """Post-fix production rows, 2026-09-23T15:57:38Z."""
    rows = [row("QQQ", -0.922, 740.57, 747.46), row("SPY", -0.623, 768.62, 773.44),
            row("IWM", -1.383, 283.18, 287.15), row("DIA", -0.626, 514.71, 517.95),
            row("RSP", -0.31, 212.10, 212.76)]
    assert _incoherent_rows(rows) == []


def test_a_sign_flip_is_always_caught():
    assert _incoherent_rows([row("X", +0.50, 99.50, 100.00)]) == ["X"]


def test_absent_inputs_are_not_incoherent():
    """Unsourceable is already covered by `reason` + UNAVAILABLE; do not double-flag."""
    assert _incoherent_rows([row("A", None, 100.0, 99.0, reason="no bar")]) == []
    assert _incoherent_rows([row("B", 1.0, None, 99.0)]) == []
    assert _incoherent_rows([row("C", 1.0, 100.0, None)]) == []
    assert _incoherent_rows([row("D", 1.0, 100.0, 0)]) == []


def test_rounding_alone_never_trips_it():
    """extra is stored to 2dp and value to 3dp; the recomputation cannot be exact."""
    prior, spot = 747.4649, 740.5712
    exact = (spot / prior - 1.0) * 100.0
    assert _incoherent_rows([row("Q", round(exact, 3), round(spot, 2), round(prior, 6))]) == []


@pytest.mark.parametrize("err_pp,caught", [(0.01, False), (0.05, True), (0.80, True)])
def test_the_gate_trips_between_rounding_and_a_real_error(err_pp, caught):
    prior, spot = 100.0, 99.0
    true_pct = (spot / prior - 1.0) * 100.0
    got = _incoherent_rows([row("T", round(true_pct + err_pp, 3), spot, prior)])
    assert bool(got) is caught
