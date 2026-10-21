"""B8 section 1: what would flip the regime, in both directions, as CONDITIONS WITH COUNTERS.

R-IV.1243(e), and the first thing it settles is what this section must NOT be. v2.js already
carried the note that a "distance to flip" would be a LIE, and the ruling agrees. The reason is
worth keeping in front of whoever edits this next: the v1 classifier does not score a label on
one continuous axis, so there is no scalar whose shrinking means "closer to CORRECTION". It
takes a label when a SET of conditions holds, and then the hysteresis makes it wait. A number
of points would imply a geometry the rules do not have.

WHAT IS HONEST IS A COUNTER, because the hysteresis is literally a count: a new label needs
`enter_requires_settled_closes` settled closes before it is shown, and the snapshot stores how
many have been banked. "1 of 2" is a fact about the record, not an estimate.

PURE. Rules and one snapshot in, conditions out.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: §2's order, bear-to-bull, is the only thing that makes "the next label toward risk" a
#: well-defined phrase. It comes from the rules file so the two cannot drift.
#:
#: NEIGHBOUR, NOT NEAREST-IN-SPIRIT. R-IV.1198(c) already found that `steps` in this order is
#: the WRONG INSTRUMENT for judging whether a flip is chatter, because range_chop and melt_up
#: sit between correction and uptrend. The same caution applies here: the neighbour is named as
#: the next entry in the published order and nothing more is claimed for it.

#: What each label's own entry condition is, in the words the card can show. Taken from
#: `thresholds` by key so a threshold change moves the sentence with it -- a hard-coded "2
#: indices" would quietly disagree with the rules file the day someone edits it.
#
# R-IV.1277(b)/registration §1 / R-IV.1277(b): THREE OF THESE DESCRIBED SOMETHING THE ROWS DO NOT DO, and a
# card that states an entry condition the classifier does not use is worse than one that states
# none -- a reader checks the stated condition against the tape and concludes the label is
# wrong. Each was read off `regime_classifier` rather than off the ruling's prose:
#
#   CORRECTION  the 5%-from-the-high clause is a TAG (`_annotate`, "narrow"), NOT an entry
#               rule. The row has two clauses and neither mentions it, so the old text turned a
#               label's decoration into a condition for having it.
#   UPTREND     the row ALSO requires SPY above a RISING 50dma above the 200dma and IWM above
#               its own 50dma. The sector count was the only part shown, which reads as though
#               five sectors alone could name an uptrend.
#   RECOVERY    the row has TWO entries (a confirmed upside 50dma break with the 20dma crossing
#               above the 50dma, OR a breadth thrust with the close above the 50dma) and a hard
#               precondition the text omitted entirely: the PRIOR label must be one of rows
#               1-4. Without that, Recovery reads as reachable from an uptrend.
ENTRY_CONDITIONS = {
    "correction": ("SPY below its 50d while above its 200d with the 50d above the 200d, or "
                   "SPY ranging or trending while {correction_indices_below_50dma} of 3 "
                   "indices close below their 50d"),
    "breakdown": "a confirmed break of the prior structure",
    "bear_market": ("{bear_pct_below_52w_high}% below the 52-week high, or "
                    "{bear_closes_below_falling_200dma} closes below a falling 200d"),
    "bear_market_rally": ("{bear_rally_closes_above_20_and_50} closes back above the 20d and "
                          "50d inside a bear market"),
    "crash_liquidation": ("{crash_universe_down_3pct_share}% of the universe down 3% with "
                          "{crash_families_required} families confirming"),
    "recovery": ("only from crash / bear market / bear rally / breakdown, and then either a "
                 "confirmed upside 50d break with the 20d crossing above the 50d, or a breadth "
                 "thrust from {recovery_breadth_thrust_from_pct}% to "
                 "{recovery_breadth_thrust_to_pct}% within "
                 "{recovery_breadth_thrust_within_sessions} sessions with the close above the "
                 "50d"),
    "range_chop": ("ADX below {range_adx_below} for {range_min_sessions} sessions, within "
                   "{range_within_pct_of_50dma}% of the 50d"),
    "melt_up": ("{melt_up_pct_above_200dma}% above the 200d with RSI over {melt_up_rsi_min} "
                "on {melt_up_rsi_hits_of_last_5} of the last 5"),
    "uptrend": ("SPY above a rising 50d above the 200d, IWM above its 50d, and "
                "{uptrend_sectors_above_50dma_min} of {uptrend_sectors_total} sectors above "
                "their 50d"),
    "narrow_uptrend": ("{narrow_uptrend_sectors_max} or fewer sectors leading, high-beta "
                       "breadth under {narrow_uptrend_high_beta_breadth_below_pct}%"),
}


def label_words(key: Optional[str]) -> str:
    """A rules key as the card shows it. `narrow_uptrend` -> `NARROW UPTREND`."""
    return str(key or "").replace("_", " ").upper() or "—"


def condition_text(key: Optional[str], thresholds: Dict[str, Any]) -> Optional[str]:
    """The entry condition for a label, with its thresholds filled in from the rules file.

    None for a label this table does not describe -- which is reported as "no condition
    published" rather than left blank, because a blank reads as "nothing required".
    """
    tmpl = ENTRY_CONDITIONS.get(str(key or "").lower())
    if not tmpl:
        return None
    try:
        return tmpl.format(**{k: _trim(v) for k, v in (thresholds or {}).items()})
    except KeyError as missing:
        # A threshold the template names but the rules file does not carry. Reported, never
        # filled with a guess: a condition sentence with an invented number in it is worse
        # than no sentence.
        return "condition unavailable: the rules file has no %s" % missing


def _trim(v: Any) -> Any:
    """20.0 prints as 20, 12.5 stays 12.5. A threshold shown as "20.0%" reads as precision."""
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v


def neighbours(shown: Optional[str], order: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """(the next label DOWN the published order, the next label UP it).

    NOT "toward risk" AND "toward risk-on", and this is a correction I had to make after seeing
    the output: from UPTREND, one step down §2's order is MELT UP, which is MORE risk-on and
    not less. §2's order is a published sequence, not a risk axis -- R-IV.1198(c) already found
    that distance along it is the wrong instrument for judging a flip, because range_chop and
    melt_up sit between correction and uptrend. Labelling melt_up "toward risk" on screen would
    be a wrong claim in the one place a reader would trust it.

    So the directions are named for what they are: positions in the published order. The gates
    are still exact, because the hysteresis genuinely treats `breakdown` and `crash_liquidation`
    differently and that exemption is named on the block it applies to.

    (None, x) at the bear end and (x, None) at the bull end -- an end of the order has no
    neighbour, and inventing a wrap-around would offer a flip from crash_liquidation to
    narrow_uptrend as the next step down.
    """
    try:
        i = order.index(str(shown or "").lower())
    except (ValueError, AttributeError):
        return None, None
    return (order[i - 1] if i > 0 else None,
            order[i + 1] if i + 1 < len(order) else None)


def closes_needed(target: Optional[str], hysteresis: Dict[str, Any]) -> Tuple[int, str]:
    """(settled closes required to SHOW `target`, which rule set that number).

    The toward-risk exemption is named rather than folded in: `breakdown` and
    `crash_liquidation` skip the minimum-sessions hold but STILL need their closes, and a
    reader who does not know that will read a "1 of 2" on breakdown as five sessions away.
    """
    toward_risk = [str(x).lower() for x in (hysteresis.get("toward_risk_regimes") or [])]
    if str(target or "").lower() in toward_risk:
        n = int(hysteresis.get("toward_risk_still_requires_closes")
                or hysteresis.get("enter_requires_settled_closes") or 2)
        return n, ("toward-risk: %d settled closes, and exempt from the %s-session minimum hold"
                   % (n, hysteresis.get("min_sessions_before_change")))
    n = int(hysteresis.get("enter_requires_settled_closes") or 2)
    return n, ("%d settled closes, then the %s-session minimum hold"
               % (n, hysteresis.get("min_sessions_before_change")))


def direction_block(target: Optional[str], *, rules: Dict[str, Any],
                    candidate: Optional[str], banked: Optional[int],
                    direction: str) -> Dict[str, Any]:
    """One direction's condition, with its counter when one applies.

    THE COUNTER IS ONLY SHOWN FOR THE LABEL THE CLASSIFIER IS ACTUALLY PROPOSING. The stored
    `pending_closes` counts closes banked toward the CANDIDATE label; printing it beside the
    other direction would attach a real number to a label nothing is proposing, which is the
    most convincing kind of wrong figure.
    """
    thresholds = rules.get("thresholds") or {}
    hyst = rules.get("hysteresis") or {}
    if not target:
        # The END of the published order has no neighbour, and it still needs a headline: a
        # block without one made the renderer read a missing key, which is how a section goes
        # blank in front of Nick rather than saying "there is nothing further this way".
        return {"direction": direction, "target": None, "counter": None, "proposing": False,
                "condition": None,
                "headline": "no further label in this direction (the order ends here)"}
    need, need_basis = closes_needed(target, hyst)
    cond = condition_text(target, thresholds)
    is_candidate = str(candidate or "").lower() == str(target).lower()
    counter = None
    if is_candidate and banked is not None:
        counter = {"banked": int(banked), "needed": need,
                   "text": "%d of %d" % (int(banked), need)}
    return {
        "direction": direction,
        "target": target,
        "target_words": label_words(target),
        "condition": cond or "no condition published for %s" % label_words(target),
        "closes_needed": need,
        "closes_basis": need_basis,
        "counter": counter,
        "proposing": is_candidate,
        # The sentence the card prints, in the ruling's own shape.
        "headline": ("%s → %s%s"
                     % (cond or "condition unavailable", label_words(target),
                        (" · " + counter["text"]) if counter else "")),
    }


def flip_triggers(snapshot: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
    """Both directions, as conditions with counters. B8 section 1.

    `snapshot` is the regime-strategy payload's own fields: regime_label / raw_regime_key /
    pending_closes / held_sessions.
    """
    order = [str(x).lower() for x in (rules.get("order") or [])]
    shown = str(snapshot.get("regime_label") or "").lower() or None
    candidate = snapshot.get("raw_regime_key")
    banked = snapshot.get("pending_closes")
    down, up = neighbours(shown, order)
    hyst = rules.get("hysteresis") or {}

    # THE CANDIDATE IS NOT ALWAYS THE ORDER-NEIGHBOUR, and the ruling's own example is the
    # proof: it shows "... -> CORRECTION . 1 of 2" while the shown label is a bull one, and
    # CORRECTION is not adjacent to NARROW UPTREND -- range_chop and melt_up sit between them.
    # R-IV.1198(c) already found that distance in this order is the wrong instrument.
    #
    # So the section carries BOTH, and says which is which: the IN-PROGRESS flip, which is the
    # label the classifier is actually proposing and the only one the stored counter belongs
    # to, and the two NEIGHBOURS as the standing conditions in each direction. Showing the
    # counter against a neighbour nothing is proposing would attach a real number to the wrong
    # label, which is the most convincing kind of wrong figure.
    in_progress = None
    if candidate and str(candidate).lower() != (shown or ""):
        in_progress = direction_block(str(candidate).lower(), rules=rules, candidate=candidate,
                                      banked=banked, direction="in progress")
    # R-IV.1252(c)4's bull side: the segmented sector bar and ITS DASHED SEGMENT AT THE RULE'S
    # REAL THRESHOLD. Both numbers come from the rules file and the snapshot rather than from
    # the renderer, so the dash cannot drift from the threshold the classifier actually uses --
    # a bar whose marker is in the wrong segment is worse than a bar with no marker.
    th = rules.get("thresholds") or {}
    breadth = (snapshot.get("breadth") or {}) if isinstance(snapshot.get("breadth"), dict) else {}
    sectors = {
        "above": breadth.get("sectors_above_50dma"),
        "total": breadth.get("sectors_total") or th.get("uptrend_sectors_total"),
        "threshold": th.get("uptrend_sectors_above_50dma_min"),
        "basis": ("sectors above their own 50dma, against the uptrend row's own minimum of %s "
                  "of %s" % (th.get("uptrend_sectors_above_50dma_min"),
                             th.get("uptrend_sectors_total"))),
    }
    # An absent count is NOT zero sectors: `sectors_above_50dma` is omitted entirely when
    # fewer than all eleven series were usable, because a partial count is a smaller sample
    # wearing the same units.
    if sectors["above"] is None:
        sectors["reason"] = ("the sector count is not recorded for this session; it is "
                             "omitted when fewer than all series were usable, so this is not "
                             "a count of zero")
    return {
        "in_progress": in_progress,
        "sectors": sectors,
        "shown": label_words(shown),
        "candidate": label_words(candidate) if candidate else None,
        "candidate_differs": bool(candidate and str(candidate).lower() != (shown or "")),
        "held_sessions": snapshot.get("held_sessions"),
        "min_hold": hyst.get("min_sessions_before_change"),
        "down_order": direction_block(down, rules=rules, candidate=candidate,
                                      banked=banked,
                                      direction="one step down the published order"),
        "up_order": direction_block(up, rules=rules, candidate=candidate, banked=banked,
                                    direction="one step up the published order"),
        "order_note": (
            "The two blocks above are the ADJACENT labels in section 2's published order, "
            "which is a sequence and not a risk axis: one step down from UPTREND is MELT UP, "
            "which is more risk-on and not less. R-IV.1198(c) found the same thing measuring "
            "flips. The in-progress block is the one the classifier is actually proposing."),
        "no_distance_estimate": (
            "No distance-to-flip is shown, and that is deliberate (R-IV.1243(e)): the v1 "
            "classifier takes a label when a SET of conditions holds, not when one score "
            "crosses a line, so there is no number whose shrinking means closer. A points "
            "estimate would imply a geometry the rules do not have."),
        "basis": "conditions from the v1 rules file; counters from the stored snapshot",
    }
