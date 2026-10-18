"""Position Watch: the pure decisions. R-IV.1209(f), source ruled by R-IV.1215(b).

ALERTS, NOT SIGNALS. Nothing here is graded, nothing reaches Kairos or the River's actionable
lanes, and nothing is written to `signals` (f)6. Every decision below is a pure function so the
ones that can do harm are testable without a vendor, a database or a push.

THE THREE THAT CAN DO HARM, and they get the most care:

  1. AGAINST or WITH. This decides whether Nick's phone buzzes. It is the alert's direction
     against the SIGN OF THE POSITION'S NET DELTA ON THE UNDERLYING (f)3 -- not against the
     ticker he holds. A long SQQQ position is SHORT QQQ, so a bullish QQQ alert is AGAINST it.
     Reading the holding's direction instead of its delta gets that exactly backwards, and
     backwards here means silence when the phone should ring.

  2. THE WORDING. "tighten / trim" and "review stop", never buy, sell or reverse (f)5. This is
     the one surface that speaks to Nick about a live position during the session.

  3. THE CLOSED-BAR RULE. R-IV.1215(b)4: a 15-minute bar counts only once the next bar exists
     or the session has closed plus five minutes. An event fired off a forming bar is an event
     off a number that is still moving.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ── (f)2's hand-kept map ────────────────────────────────────────────────────
#
# A leveraged or inverse ETF is watched through its UNDERLYING, because that is where the level
# and the exhaustion live. `inverted` means the position's delta on that underlying flips sign.
# Hand-kept BY DESIGN: a factor inferred from a name ("3x" in a description) is a guess, and a
# guess here inverts an alert.
LEVERAGE_MAP: Dict[str, Tuple[str, bool]] = {
    "SQQQ": ("QQQ", True),
    "SRTY": ("IWM", True),
    "TSLQ": ("TSLA", True),
    "GUSH": ("XOP", False),
}

#: Held instruments with no usable intraday series, each with the reason the panel shows
#: (R-IV.1215(b)3). Stated rather than silently skipped: a ticker missing from a watch list
#: with no reason reads as an oversight.
NOT_WATCHED: Dict[str, str] = {
    "VIX": "options on VIX futures, no usable underlying series",
    "SHV": "T-bill fund",
}

#: Why a core holding is out of Set B.
CORE_REASON = "long-term sleeve, not watched"

#: Structures and the sign of their delta on the underlying, before leverage.
#: A structure this does not know returns None -- NOT zero, and not a guess. An unknown
#: structure must not be silently called neutral, because neutral means "never AGAINST".
_BEARISH = ("put_debit_spread", "long_put", "put_credit_spread_short", "bear_call_spread")
_BULLISH = ("call_debit_spread", "long_call", "stock", "call_credit_spread_short",
            "bull_put_spread")


def structure_sign(structure: Optional[str]) -> Optional[int]:
    """+1 if the structure is long the underlying, -1 if short, None if unrecognised."""
    if not structure:
        return None
    s = str(structure).strip().lower()
    # A compound structure ("put_debit_spread+long_put") is the sign of its parts, which must
    # agree; if they do not, the net is not knowable from the label alone.
    parts = [p for p in s.replace(" ", "").split("+") if p]
    signs = set()
    for p in parts:
        if p in _BEARISH:
            signs.add(-1)
        elif p in _BULLISH:
            signs.add(1)
        else:
            return None
    if len(signs) != 1:
        return None
    return signs.pop()


def underlying_of(ticker: str) -> str:
    """The ticker whose bars carry this position's levels."""
    t = str(ticker or "").upper()
    return LEVERAGE_MAP[t][0] if t in LEVERAGE_MAP else t


def delta_sign(position: Dict[str, Any]) -> Optional[int]:
    """The sign of the position's net delta ON THE UNDERLYING. (f)3's input.

    THE INVERSION IS THE WHOLE POINT. A long SQQQ holding is SHORT QQQ:

        structure `stock`  -> +1 (long the instrument)
        SQQQ is inverted   -> x -1
        net on QQQ         -> -1

    Returns None when the structure is unrecognised or the inversion is not recorded, and a
    None must never be treated as neutral -- see `classify_relation`.
    """
    sign = structure_sign(position.get("structure"))
    if sign is None:
        return None
    t = str(position.get("ticker") or "").upper()
    if t in LEVERAGE_MAP and LEVERAGE_MAP[t][1]:
        sign = -sign
    return sign


def alert_sign(direction: Optional[str]) -> Optional[int]:
    """+1 for a bullish alert, -1 for bearish, None if the direction is unreadable."""
    d = str(direction or "").strip().upper()
    if d in ("LONG", "BUY", "BULL", "BULLISH", "UP"):
        return 1
    if d in ("SHORT", "SELL", "BEAR", "BEARISH", "DOWN"):
        return -1
    return None


def classify_relation(alert_direction: Optional[str],
                      position: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """AGAINST, WITH, or UNKNOWN with a reason. (f)3.

    UNKNOWN IS NOT 'WITH'. A push fires only on AGAINST (f)4, so collapsing "I could not tell"
    into WITH would silence an alert that might have mattered, and collapsing it into AGAINST
    would push on a guess. It is its own answer and goes to the panel log unpushed.
    """
    a = alert_sign(alert_direction)
    d = delta_sign(position)
    if a is None:
        return None, "the alert's direction could not be read (%r)" % (alert_direction,)
    if d is None:
        return None, ("the position's delta sign is not knowable from structure %r"
                      % (position.get("structure"),))
    if a == d:
        return "WITH", "the alert points the same way as the position's delta on %s" % (
            underlying_of(position.get("ticker")),)
    return "AGAINST", "the alert points against the position's delta on %s" % (
        underlying_of(position.get("ticker")),)


# ── Set B, read from the live book every session (R-IV.1215(b)2) ───────────

def set_b(positions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """The watch set and, just as importantly, what is NOT watched and why.

    NEVER HARDCODED (R-IV.1215(b)2). The book changes; a frozen list would watch a position
    Nick has closed and miss one he has opened, and the second failure is silent.

    TRADED SLEEVES ONLY. A strategic core holding is target mix: a 15-minute level break on VTI
    is not an event Nick acts on, and pushing one teaches him to ignore the channel -- the only
    real failure mode an alert feed has.
    """
    watched: Dict[str, List[str]] = {}
    excluded: Dict[str, str] = {}
    for p in positions or []:
        t = str(p.get("ticker") or "").upper()
        if not t:
            continue
        if t in NOT_WATCHED:
            excluded.setdefault(t, NOT_WATCHED[t])
            continue
        if str(p.get("classification") or "").upper() == "STRATEGIC":
            excluded.setdefault(t, CORE_REASON)
            continue
        u = underlying_of(t)
        if u in NOT_WATCHED:
            excluded.setdefault(t, NOT_WATCHED[u])
            continue
        watched.setdefault(u, [])
        if t not in watched[u]:
            watched[u].append(t)
    # A ticker that is BOTH held tactically and held in the core is watched: the tactical row
    # is the one that can need a stop reviewed.
    for u in watched:
        excluded.pop(u, None)
    return {
        "watch": sorted(watched),
        "via": {u: sorted(v) for u, v in watched.items()},
        "not_watched": dict(sorted(excluded.items())),
        "basis": ("traded sleeves only, read from the live book; leveraged and inverse ETFs "
                  "watched through their underlying (R-IV.1209(f)2, R-IV.1215(b)2-3)"),
    }


# ── the closed-bar rule (R-IV.1215(b)4) ───────────────────────────────────

BAR_MINUTES = 15
#: Minutes after the close before the final bar of the session counts.
CLOSE_GRACE_MIN = 5


def bar_is_closed(bar_start: _dt.datetime, *, newest_bar_start: Optional[_dt.datetime],
                  session_closed: bool, now: _dt.datetime) -> Tuple[bool, str]:
    """Is this 15-minute bar finished? R-IV.1215(b)4, and it says WHY.

    Two ways to know, and only two: a LATER bar exists, or the session has closed and five
    minutes have passed. Anything else -- including "the clock says the bar's window has
    elapsed" -- is an assumption about a feed, and this repo's own landmine is Yahoo's /1d
    dropping a session that /1h still has. The newest bar is never treated as complete.
    """
    if newest_bar_start is not None and newest_bar_start > bar_start:
        return True, "a later bar exists (%s)" % newest_bar_start.isoformat()
    if session_closed:
        end = bar_start + _dt.timedelta(minutes=BAR_MINUTES + CLOSE_GRACE_MIN)
        if now >= end:
            return True, "the session is closed and %d min have passed" % CLOSE_GRACE_MIN
        return False, "the session is closed but the %d-minute grace has not elapsed" % (
            CLOSE_GRACE_MIN,)
    return False, "it is the newest bar and the session is open, so it is still forming"


# ── the detectors, as pure tests over closed bars ─────────────────────────

#: (f)1: a failed breakout is a break, then a close back inside WITHIN 4 BARS.
FAILED_BREAKOUT_BARS = 4

#: The prior-day-level family. R-IV.1220(a)3 caps these TWO TOGETHER at one push per ticker per
#: session. The exit levels (STOP_LEVEL / TARGET_LEVEL) and EXHAUSTION are not in this family
#: and are explicitly unchanged by that ruling.
LEVEL_TYPE_EVENTS = ("LEVEL_BREAK", "FAILED_BREAKOUT")


def _beyond(c: float, prior_high: Optional[float],
            prior_low: Optional[float]) -> Optional[str]:
    """Which side of the prior-day range this close is beyond, or None for inside."""
    if prior_high is not None and c > prior_high:
        return "above"
    if prior_low is not None and c < prior_low:
        return "below"
    return None


def _is_inside(c: float, prior_high: Optional[float],
               prior_low: Optional[float]) -> bool:
    """Within BOTH known bounds.

    "Inside" means inside the range, not merely "not above the high". A bar below the prior-day
    low is not inside, so it cannot serve as the inside bar a break event requires.
    """
    return ((prior_high is None or c <= prior_high)
            and (prior_low is None or c >= prior_low))


def level_break(session_closes: List[float], prior_high: Optional[float],
                prior_low: Optional[float], *,
                fired_sides: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """AN EVENT, NOT A STATE: the FIRST closed 15m bar beyond the prior-day level AFTER a
    closed bar inside it. R-IV.1220(a)1, which replaces the state test this function was.

    WHY IT CHANGED, measured rather than argued. QUERY's census (report sha12 8514413e1c48)
    ran both forms over the same sessions: as a STATE test -- "is the newest close beyond the
    level" -- it produced 270 raw fires a day and the 20/day cap bound on 59 of 59 days,
    because one break re-reported itself on every remaining bar of the session. The same
    detector as an EVENT produced 22 a day. A state test asked once a bar is a counter of bars,
    not of breaks.

    `session_closes` is THIS SESSION's closed bars, oldest first. The scoping is load-bearing
    twice over: "at most once per session per direction" is meaningless against a list that
    spans sessions, and a bar from yesterday could otherwise supply the "inside" bar for a
    level that was already broken before today opened.

    `fired_sides` is the directions already fired this session ("above" / "below"). The side is
    the key, not the ticker: a session can legitimately break out above AND lose the low later
    the same day, and those are two different things to know about.

    A HOLE THIS LEAVES, STATED RATHER THAN PAPERED OVER: a session that gaps beyond the level
    on its first bar and never closes back inside produces NO level-break event at all, because
    the ruled definition requires a closed inside bar first. That is the ruling as written and
    it is implemented as written; the gap-and-go case is reported to SPINE under R-IV.1220
    rather than quietly widened here, and `test_gap_open_beyond_never_fires` pins the behaviour
    so it cannot drift either way unnoticed.
    """
    if len(session_closes) < 2:
        return None
    already = {str(s).lower() for s in (fired_sides or ())}
    c = session_closes[-1]
    side = _beyond(c, prior_high, prior_low)
    if side is None or side in already:
        return None
    if not _is_inside(session_closes[-2], prior_high, prior_low):
        return None
    level = prior_high if side == "above" else prior_low
    word = "high" if side == "above" else "low"
    return {"event": "LEVEL_BREAK", "side": side, "level": level, "close": c,
            "basis": "closed %.4f %s the prior-day %s %.4f" % (c, side, word, level)}


def failed_breakout(session_closes: List[float], prior_high: Optional[float],
                    prior_low: Optional[float],
                    within: int = FAILED_BREAKOUT_BARS) -> Optional[Dict[str, Any]]:
    """ONCE PER BREAK, R-IV.1220(a)2 -- and once per break BY CONSTRUCTION, not by bookkeeping.

    The event is the RETURN: the bar immediately before this one was beyond the level and this
    one closed back inside. Because the test is that transition, a second inside bar after the
    same break is not a transition and cannot re-fire. The alternative -- "a break happened
    within 4 bars and we are inside now" -- is true on up to four bars in a row and needs a
    fired-set to hold it to one. A rule that cannot double-fire beats a rule plus a guard
    against its double-firing.

    The break bar is then found by walking back over the CONSECUTIVE run of bars beyond that
    same side, and the run must be no longer than `within` bars: a break that held for five
    bars before failing is not this event.

    `session_closes` is session-scoped and oldest-first, as in `level_break`.
    """
    if len(session_closes) < 2:
        return None
    last = session_closes[-1]
    if not _is_inside(last, prior_high, prior_low):
        return None
    side = _beyond(session_closes[-2], prior_high, prior_low)
    if side is None:
        # The bar before was inside too, so nothing returned from anywhere.
        return None
    run = 1
    while (run < len(session_closes) - 1
           and _beyond(session_closes[-1 - (run + 1)], prior_high, prior_low) == side):
        run += 1
    if run > within:
        return None
    level = prior_high if side == "above" else prior_low
    return {"event": "FAILED_BREAKOUT", "side": side, "level": level, "close": last,
            "bars_ago": run,
            "basis": ("broke %s %.4f %d bar(s) ago and closed back inside at %.4f"
                      % (side, level, run, last))}


def stop_or_target(close: Optional[float], position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The position's OWN stop or target from its EXIT line. (f)1.

    Only fires when the row actually carries one. A null stop is not a stop at zero, and this
    repo has a standing rule about exactly that.
    """
    if close is None:
        return None
    sign = delta_sign(position)
    if sign is None:
        return None
    stop = position.get("stop_loss")
    target = position.get("target")
    if stop is not None:
        hit = close <= float(stop) if sign > 0 else close >= float(stop)
        if hit:
            return {"event": "STOP_LEVEL", "level": float(stop), "close": close,
                    "basis": "closed %.4f through the position's own stop %.4f"
                             % (close, float(stop))}
    if target is not None:
        hit = close >= float(target) if sign > 0 else close <= float(target)
        if hit:
            return {"event": "TARGET_LEVEL", "level": float(target), "close": close,
                    "basis": "closed %.4f through the position's own target %.4f"
                             % (close, float(target))}
    return None


# ── wording (f)5 ───────────────────────────────────────────────────────────

#: The only two actions, and the events each belongs to. "LOGGED" is not an action -- it is
#: what a WITH or UNKNOWN alert gets INSTEAD of one.
ACTION_TIGHTEN = "TIGHTEN / TRIM"
ACTION_REVIEW_STOP = "REVIEW STOP"
ACTION_LOGGED = "LOGGED"

_TIGHTEN_EVENTS = ("EXHAUSTION", "FAILED_BREAKOUT", "TARGET_LEVEL")
_REVIEW_EVENTS = ("LEVEL_BREAK", "STOP_LEVEL")


def action_for(event: str, relation: Optional[str]) -> str:
    """(f)5's pairing, not just its vocabulary.

    "review stop" for a level break against you, "tighten / trim" for exhaustion or a failed
    breakout against you. Giving the wrong one of the two is advice about the wrong thing --
    subtler than an order and just as wrong. Anything not AGAINST is LOGGED.
    """
    if relation != "AGAINST":
        return ACTION_LOGGED
    e = str(event or "").upper()
    if any(k in e for k in _TIGHTEN_EVENTS):
        return ACTION_TIGHTEN
    if any(k in e for k in _REVIEW_EVENTS):
        return ACTION_REVIEW_STOP
    # An event with no ruled pairing gets NO action rather than a plausible one.
    return ACTION_LOGGED


# ── delivery limits (f)4 ───────────────────────────────────────────────────

PUSH_COOLDOWN_MIN = 30
PUSH_DAILY_CAP = 20

#: R-IV.1220(a)5: B2 SHIPS WITH PHONE PUSHES OFF. The panel is live from the first deploy; the
#: wire stays dark until SPINE rules on QUERY's re-run of the census against the event
#: detector. This is a constant and not an env read on purpose -- flipping it is a code change
#: that goes through a review, which is what "only after SPINE rules" means in practice.
PUSHES_ENABLED = False

#: R-IV.1220(a)4: the one push sent when the cap binds. It names no ticker, no level and no
#: figure -- it points at the panel, which has every alert, because NOTHING is dropped from the
#: panel. A cap that silently swallows the 21st alert is a cap that hides its own existence.
CAP_NOTICE_TEXT = "Alert cap reached: see Position Watch panel"


def _level_push_this_session(recent: Iterable[Dict[str, Any]], ticker: str,
                             session_date: Optional[_dt.date]) -> Optional[Dict[str, Any]]:
    """The level-type push already sent for this ticker this session, if there is one.

    With `session_date` None, every row in `recent` is treated as in-session -- which is right
    only if the caller passed a session-scoped list, and is documented on `may_push`.
    """
    want = str(ticker).upper()
    for r in recent or []:
        if str(r.get("ticker", "")).upper() != want:
            continue
        if str(r.get("event", "")).upper() not in LEVEL_TYPE_EVENTS:
            continue
        if session_date is not None:
            at = r.get("pushed_at")
            day = r.get("session_date") or (at.date() if at is not None else None)
            if day != session_date:
                continue
        return r
    return None


def may_push(*, relation: Optional[str], event: str, ticker: str,
             recent: Iterable[Dict[str, Any]], now: _dt.datetime,
             pushed_today: int, session_date: Optional[_dt.date] = None,
             pushes_enabled: bool = PUSHES_ENABLED) -> Tuple[bool, str]:
    """(f)4 as amended by R-IV.1220(a)3 and (a)5, with the reason -- because a suppressed push
    that says nothing is indistinguishable from a detector that never fired.

    THE ORDER OF THESE GATES IS THE DESIGN.

      1. The OFF switch (a)5, first, so a dark wire consumes nothing: no cap slot, no cooldown
         row, no "already pushed" state that would still be there when the wire is switched on.
      2. The relation gate (f)4, so a WITH alert never consumes a cap slot. A cap spent on
         alerts that were never going to be pushed is a cap that silences the ones that would.
      3. ONE LEVEL-TYPE PUSH PER TICKER PER SESSION (a)3, before the cap for the same reason.
         LEVEL_BREAK and FAILED_BREAKOUT share this one slot: they are two readings of the same
         prior-day level, and a break followed by its failure is the commonest pair there is.
      4. Then the daily cap, then the per-event cooldown.

    The alert still reaches the PANEL in every one of these cases. This function decides the
    phone, nothing else.
    """
    if not pushes_enabled:
        return False, "phone pushes are OFF for B2's ship (R-IV.1220(a)5); the panel is live"
    if relation != "AGAINST":
        return False, "not AGAINST, so it goes to the panel log (f)4"
    if str(event).upper() in LEVEL_TYPE_EVENTS:
        prior = _level_push_this_session(recent, ticker, session_date)
        if prior is not None:
            return False, ("%s already had a level-type push this session (%s), and (a)3 allows"
                           " one" % (str(ticker).upper(), str(prior.get("event", "?")).upper()))
    if pushed_today >= PUSH_DAILY_CAP:
        return False, "the daily cap of %d is reached" % PUSH_DAILY_CAP
    cutoff = now - _dt.timedelta(minutes=PUSH_COOLDOWN_MIN)
    for r in recent or []:
        if str(r.get("ticker", "")).upper() != str(ticker).upper():
            continue
        if str(r.get("event", "")).upper() != str(event).upper():
            continue
        at = r.get("pushed_at")
        if at is not None and at > cutoff:
            return False, ("%s %s was pushed at %s, inside the %d-minute window"
                           % (ticker, event, at.isoformat(), PUSH_COOLDOWN_MIN))
    return True, "AGAINST, within the cap and outside the cooldown"


def cap_notice(*, pushed_today: int, suppressed_by_cap: bool, notice_sent: bool,
               pushes_enabled: bool = PUSHES_ENABLED) -> Tuple[bool, str]:
    """R-IV.1220(a)4: ONE final push when the cap binds, and only then.

    Three conditions, each there for its own reason:

      * `suppressed_by_cap` -- the notice announces a cap that actually silenced something.
        Firing it the moment the 20th push goes out would announce a loss that had not happened.
        Note this must be a suppression BY THE CAP: an alert held back by the relation gate or
        the cooldown is not an alert the cap ate.
      * `notice_sent` -- once per session. A notice that repeats is itself the flood it reports.
      * `pushes_enabled` -- the OFF switch covers this wire too, or B2 would ship dark except
        for one message a day about a cap on messages that are not being sent.

    The notice is EXTRA: it does not consume a cap slot, because it is the one message that
    cannot be the thing the cap was protecting Nick from.
    """
    if not pushes_enabled:
        return False, "phone pushes are OFF for B2's ship (R-IV.1220(a)5)"
    if notice_sent:
        return False, "the cap notice has already been sent this session"
    if pushed_today < PUSH_DAILY_CAP:
        return False, "the cap of %d is not reached (%d sent)" % (PUSH_DAILY_CAP, pushed_today)
    if not suppressed_by_cap:
        return False, "the cap is reached but nothing has been suppressed by it yet"
    return True, "the cap is reached and at least one alert was suppressed by it"


def exhaustion_push_gate(position: Dict[str, Any],
                         implied_move: Optional[float],
                         open_profit: Optional[float]) -> Tuple[bool, str]:
    """(f)4: an exhaustion pushes only once the position is at least 0.5x its implied move in
    profit. If IV is unavailable, push WITH "vs implied: n/a".

    THE UNAVAILABLE CASE PUSHES. That is the ruling and it is the right way round: an exhaustion
    against a profitable position is worth saying even when the yardstick is missing, and the
    label says the yardstick is missing rather than implying a measurement.
    """
    if implied_move is None or implied_move <= 0:
        return True, "vs implied: n/a"
    if open_profit is None:
        return False, "the position's open profit is not known, so the gate cannot be applied"
    ratio = open_profit / implied_move
    if ratio >= 0.5:
        return True, "+%.1fx implied move in profit" % ratio
    return False, "only +%.1fx implied move in profit, under the 0.5x gate" % ratio


# ── the wording that reaches the phone ────────────────────────────────────

def panel_text(*, ticker: str, event: str, close: Optional[float], basis: str,
               action: str, shown_regime: Optional[str],
               implied_note: Optional[str] = None) -> Dict[str, str]:
    """The PANEL row's words. (f)5: tagged with shown_regime and labelled an alert, not a signal.

    FOR THE PANEL, NOT THE PUSH -- and the difference is a rule, not a preference. See
    `push_fields` below.

    Assembled here, in one place, so the no-orders lint has one surface to police rather than a
    dozen f-strings scattered through a job.
    """
    head = "%s · %s" % (str(ticker).upper(), str(event).replace("_", " ").lower())
    if close is not None:
        head += " · %.2f" % close
    body = basis
    if implied_note:
        body += " (%s)" % implied_note
    body += ". %s." % action.replace(" / ", " or ").title()
    tag = "alert, not a signal"
    if shown_regime:
        tag = "%s · %s" % (shown_regime, tag)
    return {"title": head, "body": body, "tag": tag}


def push_fields(*, ticker: str, event: str, action: str,
                shown_regime: Optional[str]) -> Dict[str, str]:
    """EXACTLY the three strings the ntfy relay accepts: ticker, alert type, action.

    NO PRICE LEVEL, AND THAT IS A RULE RATHER THAN A CHOICE. R-IV.901(b)1 limits this relay to
    ticker / alert type / action, and `integrations.ntfy_push._assert_no_money` enforces it by
    REFUSING any figure written to the cent -- which a price level is. Measured: "closed 31.20
    below the prior-day low" raises MoneyInPayload, and `send` deliberately does not swallow
    that, so a push carrying a level would not be sent at all.

    BOARD 6'S MOCK SHOWS PRICES IN THE PUSH ("IWM · exhaustion ▲ · 268.40"). The mock is layout
    and visual language only (R-IV.1214(a), and the same clause in R-IV.1194(b)); the money rule
    governs the wire. So the LEVEL stays on the panel row, where it discloses nothing the hub
    does not already show Nick, and the push says what happened and what to look at.

    The regime tag rides along inside the alert type, because the relay has no field for it and
    (f)5 requires every alert to carry it.
    """
    kind = str(event or "alert").replace("_", " ").lower()
    if shown_regime:
        kind = "%s · %s" % (kind, shown_regime)
    return {
        "ticker": str(ticker or "?").upper(),
        "alert_type": kind,
        # The action already carries the only two verbs (f)5 allows; "alert, not a signal" is
        # appended so the phone itself says what it is.
        "action": "%s · alert, not a signal" % (action or ACTION_LOGGED),
    }
