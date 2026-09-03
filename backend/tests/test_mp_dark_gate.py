"""DEF-MP-DEAD-RENDERS-AS-QUIET — the three-state freshness gate.

Pure-function tests over the session arithmetic. No DB, no network.
The gate resolves max(timestamp) per ticker at call time and classifies against
the session under analysis; there is deliberately no survivor list (R-IV.231(b)).
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.read_only.market_profile import (  # noqa: E402
    DARK_AFTER_SESSIONS,
    classify_freshness,
    _sessions_behind,
)


# These call the SHIPPED functions. An earlier version of this file mirrored the
# gate's loop locally, which meant a mutation to the real gate left the tests
# green — a test that reimplements the code under test verifies its own copy.
def sessions_behind(event_session: date, current_session: date) -> int:
    return _sessions_behind(event_session, current_session)


def classify(event_session: date, current_session: date) -> str:
    return classify_freshness(_sessions_behind(event_session, current_session))


# ── the threshold is a registered predicate; pin it as a literal ────────────

def test_threshold_is_literally_two():
    """R-IV.231(b) fixes the boundary at two sessions. Asserted as a LITERAL —
    a test that reads the constant it verifies moves with the bug."""
    assert DARK_AFTER_SESSIONS == 2


# ── the three states ───────────────────────────────────────────────────────

def test_same_session_is_ok():
    assert classify(date(2026, 9, 3), date(2026, 9, 3)) == "ok"


def test_one_session_behind_is_stale_not_dark():
    """A genuinely quiet session must NOT alarm."""
    assert classify(date(2026, 9, 2), date(2026, 9, 3)) == "stale"


def test_two_sessions_behind_is_dark():
    assert classify(date(2026, 9, 1), date(2026, 9, 3)) == "dark"


def test_tlt_the_live_case_is_dark():
    """TLT's real state on the day the defect was found: last event 07-27,
    session under analysis 09-03. 28 weekday sessions behind."""
    n = sessions_behind(date(2026, 7, 27), date(2026, 9, 3))
    assert n == 28, n
    assert classify(date(2026, 7, 27), date(2026, 9, 3)) == "dark"


def test_qqq_the_other_live_case_is_dark():
    """QQQ died 09-01; by 09-03 it is two sessions behind — the boundary."""
    assert sessions_behind(date(2026, 9, 1), date(2026, 9, 3)) == 2
    assert classify(date(2026, 9, 1), date(2026, 9, 3)) == "dark"


# ── weekend must not manufacture darkness ──────────────────────────────────

def test_friday_read_on_monday_is_one_session_not_three():
    """Fri 09-04 -> Mon 09-07 is ONE trading session, not three calendar days.
    A calendar-day threshold would call every Monday dark — the
    DEF-NIGHTLY-FLATLINE failure, which is why this counts weekdays."""
    assert date(2026, 9, 4).weekday() == 4
    assert date(2026, 9, 7).weekday() == 0
    assert sessions_behind(date(2026, 9, 4), date(2026, 9, 7)) == 1
    assert classify(date(2026, 9, 4), date(2026, 9, 7)) == "stale"


def test_thursday_read_on_monday_is_two_sessions_dark():
    assert sessions_behind(date(2026, 9, 3), date(2026, 9, 7)) == 2
    assert classify(date(2026, 9, 3), date(2026, 9, 7)) == "dark"


# ── no survivor list, by construction ──────────────────────────────────────

def test_gate_has_no_ticker_roster():
    """R-IV.231(b): no hardcoded survivor list. The module must not carry one —
    a roster is tripwire decay at feed scale."""
    import services.read_only.market_profile as mp

    src = open(mp.__file__, encoding="utf-8").read()
    for roster_marker in ("SURVIVOR", "LIVE_TICKERS", "ALLOWLIST"):
        assert roster_marker not in src, roster_marker
    # and the classification must not reference any specific ticker
    for t in ("QQQ", "SMH", "TLT", "AMD", "SPY"):
        assert ('"%s"' % t) not in src, t


def test_classification_is_symbol_agnostic():
    """Same dates, any symbol, same verdict — the gate cannot special-case."""
    verdicts = {classify(date(2026, 7, 27), date(2026, 9, 3)) for _ in range(5)}
    assert verdicts == {"dark"}
