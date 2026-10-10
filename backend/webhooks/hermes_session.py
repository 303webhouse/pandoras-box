"""Hermes phase 2 — the session displacement alarm — R-IV.820(h)2.

WHAT PHASE 1 CANNOT SEE. Phase 1 fires on TradingView's own 30-minute velocity threshold, so it
catches a lurch and misses a grind. The measurement is in its docstring and it is the reason this
module exists: **QQQ closed 2026-10-08 at −1.65% while its largest 30-minute breach all day was
−1.01%.** The principal learned about that selloff from social media. A move can be large and
never fast.

So this alarm asks a different question. Not "how far did it travel in half an hour" but **"how
far is it from where the session started"** — the displacement from the PRIOR SESSION'S CLOSE,
evaluated continuously through regular hours.

THE RE-ALERT LADDER, and why it is signed. "Re-alert only if the move extends another 0.5%" means
extends IN THE SAME DIRECTION. A row that alerts at −1.25%, drifts to −1.30% and back is one
event, not three. But a move that crosses the threshold the OTHER way is a new event, because
"crosses its threshold, in either direction" is the spec and a −1.3% session that turns into a
+1.3% session is genuinely two things worth knowing. So the last alerted value is stored SIGNED,
and the ladder only applies within a sign.

WHAT THIS IS NOT. It never closes anything and never sizes anything; it is a notifier, like phase
1. It shares phase 1's webhook and co-breach logic deliberately — one place to change where these
go, and a reader of either message is seeing the same roster reasoned about the same way.

The carry "degrossing" input is NOT part of phase 2 (R-IV.820(h)2, explicit).

THRESHOLDS ARE PROVISIONAL UNTIL SPINE RATIFIES THEM. The starting figures are the ruling's; the
calibration replay in `scripts/hermes_phase2_calibrate.py` is what earns them, and it must show
no symbol firing on more than one session in five, with QQQ firing on 10-08 as a positive
control. Shipped behind `HERMES_SESSION_ALERT_ENABLED`, default OFF.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, time as dtime
from typing import Dict, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("hermes.session")

ET = ZoneInfo("America/New_York")
MT = ZoneInfo("America/Denver")

# CALIBRATED, not chosen. R-IV.820(h)2 set the starting figures and then required a replay of
# every session since 09-15 to earn them, raising any symbol that fires on more than one session
# in five. Measured over 19 sessions on 5-minute bars:
#
#   SPY  1.00% kept   3/19 = 15.8%
#   QQQ  1.25% -> 1.75%   (1.25% and 1.50% both fired 5/19 = 26.3%)
#   SMH  2.00% -> 3.00%   (2.00% fired 8/19 = 42.1%; 2.25/2.50/2.75 all 4/19 = 21.1%)
#
# Per-symbol because their ranges differ by a factor of three: one shared number would shout
# about semis every week or never mention the index at all.
#
# QQQ's 1.75% IS A KNIFE-EDGE AND SPINE MUST SEE IT. The positive control (QQQ fires on
# 2026-10-08) and the 1-in-5 bar are nearly mutually exclusive for this symbol: 10-08's largest
# session displacement was -1.757929%, so
#     1.50% passes the control by 0.258pp but fires 26.3% of sessions;
#     1.75% passes the control by 0.0079pp and fires 15.8%;
#     2.00% MISSES the control entirely.
# 1.75% is the ONLY value satisfying both, and it admits the control by eight thousandths of a
# point. Ratify it knowing that: a slightly quieter 10-08 would have failed the control at any
# threshold that also passes the noise bar.
SESSION_THRESHOLD_PCT: Dict[str, float] = {"SPY": 1.0, "QQQ": 1.75, "SMH": 3.0}

# What the ruling started from, kept so the calibration's effect stays legible.
STARTING_THRESHOLD_PCT: Dict[str, float] = {"SPY": 1.0, "QQQ": 1.25, "SMH": 2.0}

# A further move of this much, in the SAME direction, re-alerts.
REALERT_STEP_PCT = 0.5

# The step the calibration raises a threshold by when a symbol is too noisy.
CALIBRATION_STEP_PCT = 0.25

# No symbol may fire on more than one session in five.
MAX_FIRE_RATE = 0.2

# Regular hours, in ET. The displacement question is only meaningful inside the session it
# measures: before the open there is no session-to-date move, and after the close the figure stops
# changing, so an alarm that kept evaluating would re-announce a settled fact.
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)

FLAG = "HERMES_SESSION_ALERT_ENABLED"


def is_enabled() -> bool:
    """The push is OFF unless explicitly enabled. Ships dark, as ruled.

    Railway returns '' for an unset reference, so the `or` form is required here -- the
    `os.getenv(k, default)` form would hand back '' and read as a set-but-empty flag.
    """
    return (os.getenv(FLAG) or "").strip().lower() in ("1", "true", "yes", "on")


def tracked(ticker: Optional[str]) -> bool:
    return (ticker or "").strip().upper() in SESSION_THRESHOLD_PCT


def threshold_for(ticker: Optional[str],
                  overrides: Optional[Mapping[str, float]] = None) -> Optional[float]:
    """The symbol's threshold, or None when it is not tracked.

    `overrides` lets the calibration raise a figure without mutating module state, so a replay
    cannot leave a changed threshold behind for the next caller.
    """
    sym = (ticker or "").strip().upper()
    if overrides and sym in overrides:
        return overrides[sym]
    return SESSION_THRESHOLD_PCT.get(sym)


def displacement_pct(prior_close: Optional[float], last: Optional[float]) -> Optional[float]:
    """Signed move from the prior session's close, in percent. None when it cannot be computed.

    None rather than 0.0, always. A missing prior close or a missing mark means "cannot say", and
    0.0 would read as "unchanged" -- the fake-zero this register keeps removing. A prior close of
    zero returns None for the same reason: the ratio is undefined, not flat.
    """
    if prior_close is None or last is None:
        return None
    try:
        pc, lx = float(prior_close), float(last)
    except (TypeError, ValueError):
        return None
    if pc == 0:
        return None
    return (lx - pc) / pc * 100.0


def in_rth(when: datetime) -> bool:
    """Is this instant inside regular hours, on a weekday, in ET.

    A naive datetime is REFUSED rather than assumed to be UTC or local. Guessing a timezone here
    would shift the whole session window by hours, and this file already knows that `TZ=` is
    silently ignored on this machine.
    """
    if when.tzinfo is None:
        return False
    et = when.astimezone(ET)
    if et.weekday() >= 5:
        return False
    return RTH_OPEN <= et.time() <= RTH_CLOSE


def should_alert(ticker: Optional[str], move_pct: Optional[float],
                 last_alerted_pct: Optional[float] = None,
                 overrides: Optional[Mapping[str, float]] = None) -> Tuple[bool, str]:
    """(alert?, reason). PURE — no clock, no network, no module state.

    `last_alerted_pct` is the SIGNED displacement at which this symbol last alerted this session,
    or None if it has not. Every refusal carries a reason, because "did not alert" and "was never
    evaluated" are different facts and only one of them is a defect.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        return False, "no ticker"
    thr = threshold_for(sym, overrides)
    if thr is None:
        return False, "%s is not tracked by the session alarm (%s)" % (
            sym, "/".join(sorted(SESSION_THRESHOLD_PCT)))
    if move_pct is None:
        # NOT EVALUABLE, and said out loud. A missing mark is the one state that must never be
        # silent: it looks identical to "nothing is happening" from the outside.
        return False, "NOT EVALUABLE: no displacement for %s (missing prior close or mark)" % sym

    if abs(move_pct) < thr:
        return False, "%s %+.2f%% is inside its %.2f%% threshold" % (sym, move_pct, thr)

    if last_alerted_pct is None:
        return True, "%s %+.2f%% crossed its %.2f%% threshold" % (sym, move_pct, thr)

    # Same direction: the ladder applies.
    if (move_pct >= 0) == (last_alerted_pct >= 0):
        # ROUNDED BEFORE COMPARING, and it is not cosmetic. `2.30 - 1.80` in binary floating
        # point is 0.4999999999999998, so a move exactly one rung further would fail a bare
        # `>= 0.5` and silently skip the re-alert — the boundary deciding whether a widening
        # selloff gets a second message. These are percentages quoted to two places, so the
        # comparison is made at that precision rather than at the float's.
        extended = round(abs(move_pct) - abs(last_alerted_pct), 6)
        if extended >= REALERT_STEP_PCT:
            return True, "%s extended to %+.2f%% (%.2f%% further than the %+.2f%% already sent)" % (
                sym, move_pct, extended, last_alerted_pct)
        return False, "%s %+.2f%% has not extended %.2f%% beyond the %+.2f%% already sent" % (
            sym, move_pct, REALERT_STEP_PCT, last_alerted_pct)

    # Opposite direction: a fresh crossing the other way is a new event, not a rung.
    return True, "%s reversed to %+.2f%% after alerting at %+.2f%%" % (
        sym, move_pct, last_alerted_pct)


def format_message(ticker: str, move_pct: float, prior_close: float, last: float,
                   now_utc: datetime, co: Optional[list] = None,
                   overrides: Optional[Mapping[str, float]] = None) -> str:
    """The message, in plain words, with the time in MOUNTAIN TIME.

    MT because it is the only timezone the principal thinks in, and the session window this alarm
    reasons about is ET -- so the message states the one he reads and the code keeps the one the
    market runs on. Mixing them in either direction is how an alert arrives describing the wrong
    hour.
    """
    mt = now_utc.astimezone(MT)
    thr = threshold_for(ticker, overrides)
    direction = "down" if move_pct < 0 else "up"
    line = ("%s is %s %+.2f%% on the session (%.2f from %.2f), past its %.2f%% line — %s MT"
            % (ticker.upper(), direction, move_pct, last, prior_close, thr or 0.0,
               mt.strftime("%H:%M")))
    if co:
        others = ", ".join("%s %+.2f%%" % (t, m) for t, m in co)
        line += "\nAlso past its line: %s" % others
    return line
