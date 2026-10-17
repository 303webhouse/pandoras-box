"""Hysteresis over a label series — §2's block, as a pure function.

R-IV.1193(d): "Hysteresis needs history." This is what consumes that history.

§2's rules, and each one exists because a label that flips daily is worse than no label:

    entering a regime                    2 settled closes
    a regime holds                       5 sessions before it may change again
    a move TOWARD RISK                   exempt from the 5, still needs the 2 closes
    leaving Crash                        contango on 2 closes (its own test)
    Recovery -> Uptrend                  5 closes above the 200dma
    Range                                10 sessions

THE COST IS STATED, NOT HIDDEN (§2). This makes the module LATE at V-shaped bottoms, and
fast-toward-risk FLATTERS A BEARISH LEAN. Both are consequences of rules that are right on
balance, and the card is required to say so.

PURE, and it takes the whole series rather than one reading. A hysteresis function that held its
own state could not be replayed over history, and replaying it over history is the only way to
test the one property §2 asks about: roughly six or fewer label flips a year.

DISPLAY ONLY (#42). This decides what the card shows. Nothing gates on it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.regime_classifier import load_rules

TOWARD_RISK_DEFAULT = ("breakdown", "crash_liquidation")


def apply_hysteresis(raw: List[Dict[str, Any]],
                     rules: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Turn a per-session series of RAW classifier verdicts into the series the card may show.

    `raw` is oldest-first, one entry per settled session, each with at least `as_of` and
    `regime` (None is allowed and is carried through as "no label", never as the previous one).

    Returns the same length, each entry gaining:

        shown_regime      what the card may display on that session
        pending           the candidate accumulating closes, if any
        pending_closes    how many consecutive closes it has
        held_sessions     how long `shown_regime` has held
        qualified_closes  on a session where the label MOVED, how many consecutive closes
                          the new label had accumulated to earn it; None otherwise
        change            None, or why the label moved on this session
        blocked           None, or why a qualifying candidate was NOT allowed to take effect

    `blocked` is the field worth having. Without it a reader cannot tell "the tape never
    qualified" from "the tape qualified and hysteresis held the label", and those are opposite
    facts about the same screen.
    """
    rules = rules or load_rules()
    h = rules["hysteresis"]
    need_closes = int(h["enter_requires_settled_closes"])
    min_hold = int(h["min_sessions_before_change"])
    toward_risk = tuple(h.get("toward_risk_regimes") or TOWARD_RISK_DEFAULT)
    risk_exempt = bool(h.get("toward_risk_exempt_from_min_sessions"))
    range_sessions = int(h["range_requires_sessions"])

    out: List[Dict[str, Any]] = []
    shown: Optional[str] = None
    held = 0
    pending: Optional[str] = None
    pending_closes = 0

    for i, row in enumerate(raw):
        cand = row.get("regime")
        change = None
        blocked = None
        qualified_closes = None     # set only on the session a change actually fires

        # The candidate's streak. A different candidate restarts the count: two closes of one
        # regime and one of another are not three closes of anything.
        if cand is not None and cand != shown:
            if cand == pending:
                pending_closes += 1
            else:
                pending, pending_closes = cand, 1
        else:
            pending, pending_closes = None, 0

        if shown is None:
            # THE FIRST LABEL STILL NEEDS ITS CLOSES. Seeding the series by accepting whatever
            # the first session said would make the very first label the one reading that never
            # had to qualify.
            if cand is not None and pending_closes >= need_closes:
                qualified_closes = pending_closes
                shown, held, change = cand, 1, "first label after %d closes" % pending_closes
                pending, pending_closes = None, 0
            else:
                held = 0
        elif cand is None or cand == shown:
            held += 1
        else:
            enough_closes = pending_closes >= need_closes
            is_toward_risk = cand in toward_risk
            # Range has its own, longer requirement, and it is a REQUIREMENT TO ENTER, so it is
            # checked against the candidate's own streak.
            needed_here = range_sessions if cand == "range_chop" else need_closes
            enough_closes = pending_closes >= needed_here
            held_long_enough = held >= min_hold or (is_toward_risk and risk_exempt)

            if enough_closes and held_long_enough:
                change = ("%s -> %s after %d closes%s"
                          % (shown, cand, pending_closes,
                             " (toward risk, exempt from the %d-session hold)" % min_hold
                             if is_toward_risk and risk_exempt and held < min_hold else ""))
                # THE QUALIFYING COUNT IS CAPTURED BEFORE THE RESET. Without this the row
                # published `pending_closes` AFTER it had been zeroed, so every flip reported
                # "0 closes" -- a column that is always the same value, which is the vacuous
                # column fault (DEF-EDGE-SPEC-B2) in a new place. R-IV.1198(c) asks for the
                # closes held per flip, and a field that cannot vary cannot answer it.
                qualified_closes = pending_closes
                shown, held = cand, 1
                pending, pending_closes = None, 0
            else:
                reasons = []
                if not enough_closes:
                    reasons.append("%d of %d closes" % (pending_closes, needed_here))
                if not held_long_enough:
                    reasons.append("%s has held %d of %d sessions"
                                   % (shown, held, min_hold))
                blocked = "%s qualifies on the tape but is held back: %s" % (
                    cand, "; ".join(reasons))
                held += 1

        out.append(dict(row,
                        shown_regime=shown,
                        pending=pending,
                        pending_closes=pending_closes,
                        qualified_closes=qualified_closes,
                        held_sessions=held,
                        change=change,
                        blocked=blocked))
    return out


def flip_count(series: List[Dict[str, Any]]) -> int:
    """How many times `shown_regime` changed. §2's only history check: roughly <= 6 a year.

    Never P&L -- §2 is explicit about that, and a hysteresis tuned on P&L would be a fitted
    parameter wearing a rule's name.
    """
    return sum(1 for r in series if r.get("change"))


def cost_statement(rules: Optional[Dict[str, Any]] = None) -> str:
    """The sentence §2 requires on the card. Served from the rules file so it cannot drift from
    the rules it describes."""
    return (rules or load_rules())["hysteresis"]["stated_cost"]
