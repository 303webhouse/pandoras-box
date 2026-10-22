"""Lint for the ?card=v21 preview fixture. R-IV.1309(b).

WHY A BACKEND LINT FOR A FRONTEND FILE. The pattern is `services/b9_world.py`'s, and the reason
is the same: a mock fixture is read by a renderer and by nothing else, so a typo in it fails in
a browser, silently, in front of Nick -- and only on the state he happens to open. Linting it
from the suite moves that failure to the commit.

WHAT IT CHECKS, and the one thing it deliberately does not. It checks the SHAPE AGAINST THE
LIVE PAYLOAD'S FIELD NAMES, because the whole value of a mock-first build is that the renderer
exercised on the fixture is the same code reading the same keys as the live read. A fixture with
`heldNoMatch` instead of `held_no_match` would render perfectly in preview and show nothing at
all once it went live, which is the fault mock-first exists to prevent.

It does NOT check the NUMBERS. They are fake by design and stated as such; asserting a fake
figure would only pin the fixture to itself.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "frontend", "assets", "regime", "card_v21_mock.v1.json")

#: Design board 13's three states. All three must be present: the fixture exists precisely
#: because they cannot all occur on one day.
STATES = ("A", "B", "C")

#: Keys every state must carry, spelled as the LIVE payload spells them.
REQUIRED = ("regime_label", "regime_key", "rules_version", "held_no_match",
            "data_freshness", "costs", "ma200_row")

#: R-IV.1309(b)3/4, verbatim. A fixture that paraphrases either would show Nick a layout for a
#: sentence the live card will not print.
COST_LINE = ("SPY 1999-2026, 24 declines: all-clear a median 81.5 sessions after the low, "
             "never on 11; 200d line 38. (R-IV.1301)")
CAVEAT = ("45% of up-crosses since 1999 were followed by a new 60-session low within "
          "60 sessions (LAB R-IV.1279)")


def load_fixture(path: str = FIXTURE) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def lint_card_mock(obj: Any) -> List[str]:
    """Every problem found, as sentences. Empty list means the fixture is well-formed."""
    bad: List[str] = []
    if not isinstance(obj, dict):
        return ["the fixture is not an object"]
    if obj.get("_mock") is not True:
        bad.append("`_mock` must be true: the card badges a fixture off this flag, and a mock "
                   "that does not announce itself is a fake number wearing a real one's clothes")

    states = obj.get("states")
    if not isinstance(states, dict):
        return bad + ["`states` must be an object keyed by A, B and C"]
    for key in STATES:
        if key not in states:
            bad.append("state %s is missing; all three are required because they cannot occur "
                       "on one day" % key)
            continue
        st = states[key]
        if not isinstance(st, dict):
            bad.append("state %s is not an object" % key)
            continue
        for field in REQUIRED:
            if field not in st:
                bad.append("state %s has no `%s` (the live payload's own key)" % (key, field))

        costs = st.get("costs")
        if not isinstance(costs, list) or not costs:
            bad.append("state %s must carry the cost line as a non-empty list" % key)
        elif COST_LINE not in costs:
            bad.append("state %s's cost line is not R-IV.1307(b)'s sentence verbatim" % key)

        row = st.get("ma200_row") or {}
        if not isinstance(row, dict) or not row.get("available"):
            bad.append("state %s must carry an available `ma200_row`: R-IV.1309(b)3 puts the "
                       "200-day row on EVERY state" % key)
        else:
            if row.get("side") not in ("ABOVE", "BELOW"):
                bad.append("state %s's ma200_row.side must be ABOVE or BELOW" % key)
            if row.get("display_only") is not True:
                bad.append("state %s's ma200_row must say `display_only` (#42)" % key)
            if row.get("caveat") != CAVEAT:
                bad.append("state %s's ma200_row.caveat is not LAB's sentence verbatim" % key)
            if not row.get("text"):
                bad.append("state %s's ma200_row needs the `text` the card prints" % key)

    bad.extend(_lint_state_b(states.get("B") or {}))
    bad.extend(_lint_state_c(states.get("C") or {}))
    return bad


def _lint_state_b(st: Dict[str, Any]) -> List[str]:
    """B is STALE: no rule matched, a label is held, and a decay bar says when it gives up."""
    bad: List[str] = []
    held = st.get("held_no_match") or {}
    if not held.get("stale"):
        return ["state B must have `held_no_match.stale` true -- that is what makes it state B"]
    for field in ("sessions", "last_match_as_of", "group", "group_word", "chip"):
        if not held.get(field):
            bad.append("state B's held_no_match needs `%s`" % field)
    decay = held.get("decay") or {}
    if not decay:
        bad.append("state B needs `held_no_match.decay`: board 13 asks for a 10-step bar")
        return bad
    if decay.get("steps") != 10:
        bad.append("the decay bar is 10 steps (board 13)")
    elapsed = decay.get("elapsed")
    if not isinstance(elapsed, int) or not 0 <= elapsed <= 10:
        bad.append("state B's decay.elapsed must be an int within the 10 steps")
    if not decay.get("falls_back_to"):
        bad.append("the decay bar must name what it falls back TO")
    if decay.get("falls_back_on_day") != 11:
        bad.append("board 13's bar ends on day 11")
    # THE CHIP AND THE COUNT MUST AGREE. Two places state the same number, which is how a
    # fixture comes to show "no rule matched 7 sessions" over a bar drawn at 4.
    if isinstance(elapsed, int) and held.get("sessions") != elapsed:
        bad.append("state B's held_no_match.sessions (%r) and decay.elapsed (%r) disagree; the "
                   "chip and the bar would show different numbers"
                   % (held.get("sessions"), elapsed))
    if isinstance(held.get("sessions"), int) and str(held["sessions"]) not in str(held.get("chip")):
        bad.append("state B's chip does not contain its own session count")
    return bad


def _lint_state_c(st: Dict[str, Any]) -> List[str]:
    """C is DATA STALE: the bars stopped, so the card dims and the header chip says so."""
    bad: List[str] = []
    fresh = st.get("data_freshness") or {}
    if not fresh.get("stale"):
        return ["state C must have `data_freshness.stale` true -- that is what makes it state C"]
    for field in ("last_settled", "headline", "chip", "reason"):
        if not fresh.get(field):
            bad.append("state C's data_freshness needs `%s`" % field)
    lag = fresh.get("lag_sessions")
    if not isinstance(lag, int) or lag < 2:
        bad.append("state C is "
                   "\"more than 1 session old\", so lag_sessions must be an int above 1")
    last = fresh.get("last_settled")
    if last and last not in str(fresh.get("headline") or ""):
        bad.append("state C's headline must name the last settled session, as board 13 writes it")
    # A DATA-STALE card must not ALSO claim no rule matched: they are different faults and the
    # headline can only be one of them.
    if (st.get("held_no_match") or {}).get("stale"):
        bad.append("state C must not also be held_no_match.stale: the two are distinct states "
                   "and the headline would have to choose")
    return bad
