"""The five NOTABLES cards, as pure decisions. R-IV.1259(c)-(e), wired under R-IV.1265(g)2.

NO I/O HERE. Every function takes the numbers it needs and returns a card dict or None, so each
trigger can be tested against the exact tape that is supposed to fire it -- which is the only
way to know a detector fires on what the ruling describes rather than on what was convenient to
fetch. The reader that gathers the inputs is a separate module.

DISPLAY ONLY (#42). Nothing here gates, caps, journals or writes `signals`.

THE ONE DETECTOR THAT IS NOT WRITTEN HERE is the failed break. R-IV.1259(c)3 says "Reuse
Position Watch's detector; don't write a second one", and `position_watch.failed_breakout`
already takes an arbitrary pair of levels -- so the three level kinds the ruling lists (a value
edge, the IB edge, the prior-day high/low) are three CALLS to that one function, not three
detectors. A second implementation of "did the break fail" would eventually disagree with the
first, and the surface with the looser one would be the one showing a card that is not true.

WHAT "PRICE ONLY" MEANS ON THE LOUD MOVE (c)1: the trigger reads price and nothing else. Flow is
a confirming chip, never a card, and never part of a trigger -- so no flow argument reaches
`loud_move` at all. A parameter that cannot be passed cannot be used by accident.

EVERY CARD CARRIES ITS COUNTER-EVIDENCE (g). A card built without it is refused by
`finish_card`, not merely rendered without it: counter-evidence is half of what the ruling says
a card IS, and a card missing half of itself should not reach the surface at all.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.position_watch import failed_breakout as _failed_breakout

# ── placement and noise, R-IV.1259(d)-(e) ────────────────────────────────────

#: (d): at most 5 ticker cards a day. LOUD MOVE is uncapped and pinned (c)1.
DAILY_TICKER_CAP = 5

#: (d): hours 09:45-15:30 ET, as (hour, minute) in Eastern.
HOURS_OPEN = (9, 45)
HOURS_CLOSE = (15, 30)

#: (c)2: VALUE MOVED only from 10:30 ET, because the initial balance is not formed before it.
VALUE_MOVED_FROM = (10, 30)

#: (c)2's gate: this ticker's own PYTHIA status ok AND its last update under 90 TRADING minutes
#: old. Trading minutes, not wall minutes: overnight is not staleness.
PYTHIA_MAX_TRADING_MINUTES = 90

#: The regular session, in Eastern, for counting trading minutes.
RTH_OPEN = (9, 30)
RTH_CLOSE = (16, 0)

#: (d): cards go in Watch (ticker) or Context (market-wide), never Actionable.
LANE_WATCH = "WATCH"
LANE_CONTEXT = "CONTEXT"

#: (c)1's line, verbatim. A paraphrase is a different promise about what the hub knows.
NO_CATALYST_LINE = "Hub doesn't know why. Probably news. Go look."

#: (c)2's withheld state.
STRUCTURE_UNVERIFIED = "Structure unverified"

#: (c)1: a sector SPDR must move more than this multiple of its own ATR.
SECTOR_ATR_MULTIPLE = 1.5

#: (c)1: the kill-switch level, in percent.
SPY_BREAKER_PCT = -1.0

#: (c)1: the three tickers the Hermes velocity alarm covers.
HERMES_TICKERS = ("SPY", "QQQ", "SMH")

#: (c)4: ADX crosses this with a direction.
ADX_TREND_LEVEL = 25.0

#: (c)4: a close through the 200-day needs this volume multiple.
BREAK_200_VOLUME_MULTIPLE = 1.5

#: (c)4's stack, in the ruling's order.
STACK_PERIODS = (20, 50, 120)


def _et(h_m: Tuple[int, int]) -> _dt.time:
    return _dt.time(h_m[0], h_m[1])


def in_hours(now_et: _dt.datetime) -> Tuple[bool, Optional[str]]:
    """(d): 09:45-15:30 ET. (allowed, reason when not).

    INCLUSIVE AT BOTH ENDS, stated because "09:45-15:30" leaves both edges nameable twice and a
    card at exactly 15:30 would otherwise depend on which comparison was written.
    """
    t = now_et.time()
    if t < _et(HOURS_OPEN):
        return False, "before 09:45 ET"
    if t > _et(HOURS_CLOSE):
        return False, "after 15:30 ET"
    return True, None


def trading_minutes_between(earlier_et: _dt.datetime, later_et: _dt.datetime,
                            *, session_days: Optional[Sequence[_dt.date]] = None) -> Optional[int]:
    """Minutes of REGULAR SESSION between two Eastern instants, or None if it cannot be counted.

    WHY NOT WALL MINUTES. A PYTHIA update from 15:55 yesterday is 18 hours old by the clock and
    25 trading minutes old by the tape. Judging it on the clock would withhold every structure
    card for the first 90 minutes of every session -- a gate that fires on the calendar rather
    than on staleness.

    `session_days` is the trading calendar for the span, INCLUSIVE of both dates. It is a
    parameter rather than a lookup because this module does no I/O; the caller passes what the
    market calendar says. **None is returned when the span crosses days and no calendar was
    given**, rather than guessing -- a gate that silently assumed every weekday was a session
    would pass a stale reading on the morning after a holiday.
    """
    if later_et < earlier_et:
        return None
    if earlier_et.date() == later_et.date():
        lo = max(earlier_et.time(), _et(RTH_OPEN))
        hi = min(later_et.time(), _et(RTH_CLOSE))
        if hi <= lo:
            return 0
        return int((_dt.datetime.combine(later_et.date(), hi)
                    - _dt.datetime.combine(later_et.date(), lo)).total_seconds() // 60)
    if not session_days:
        return None
    total = 0
    for day in session_days:
        if day < earlier_et.date() or day > later_et.date():
            continue
        lo = _et(RTH_OPEN)
        hi = _et(RTH_CLOSE)
        if day == earlier_et.date():
            lo = max(lo, earlier_et.time())
        if day == later_et.date():
            hi = min(hi, later_et.time())
        if hi > lo:
            total += int((_dt.datetime.combine(day, hi)
                          - _dt.datetime.combine(day, lo)).total_seconds() // 60)
    return total


def pythia_gate(*, status: Optional[str], last_update_et: Optional[_dt.datetime],
                now_et: _dt.datetime,
                session_days: Optional[Sequence[_dt.date]] = None) -> Tuple[bool, Optional[str]]:
    """(c)2's gate, per TICKER. (ok, reason when not).

    THE WHOLE FEED READING "flowing" NEVER STANDS IN FOR ONE TICKER'S OWN LAST UPDATE -- the
    States mock says so in those words, and it is the difference between a card backed by this
    ticker's tape and a card backed by somebody else's.

    An UNCOUNTABLE age is a refusal, not a pass. "Could not tell how stale this is" and "this is
    fresh" must not render alike; failing open on "could not tell" is a fault class already on
    this board's record.
    """
    if (status or "").strip().lower() != "ok":
        return False, "%s: this ticker's PYTHIA status is %r, not ok" % (
            STRUCTURE_UNVERIFIED, status)
    if last_update_et is None:
        return False, "%s: this ticker has no PYTHIA update on record" % STRUCTURE_UNVERIFIED
    age = trading_minutes_between(last_update_et, now_et, session_days=session_days)
    if age is None:
        return False, ("%s: the age of this ticker's PYTHIA update cannot be counted in trading "
                       "minutes without the session calendar" % STRUCTURE_UNVERIFIED)
    if age >= PYTHIA_MAX_TRADING_MINUTES:
        return False, ("%s: this ticker's PYTHIA update is %d trading minutes old (limit %d)"
                       % (STRUCTURE_UNVERIFIED, age, PYTHIA_MAX_TRADING_MINUTES))
    return True, None


# ── (c)1 LOUD MOVE: price only ───────────────────────────────────────────────

def loud_move(*, ticker: str, move_pct: Optional[float],
              hermes_velocity_fired: bool = False,
              atr_pct: Optional[float] = None,
              is_sector_spdr: bool = False,
              catalyst: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """(c)1. Three triggers, any one of which fires; price only, so no flow argument exists.

    The three, in the ruling's order:
      1. the Hermes velocity alarm, which covers SPY/QQQ/SMH and is passed in as a FACT that
         already fired -- this module does not re-derive somebody else's alarm;
      2. the SPY -1% kill-switch;
      3. any sector SPDR moving more than 1.5x its own ATR.

    `atr_pct` IS THE DENOMINATOR AND ITS ABSENCE IS NOT ZERO. With no ATR the multiple cannot be
    computed, so trigger 3 does not fire -- rather than firing on a comparison against nothing.
    """
    reasons: List[str] = []
    if hermes_velocity_fired:
        if ticker.upper() not in HERMES_TICKERS:
            return None
        reasons.append("30-minute velocity alarm")
    if (ticker.upper() == "SPY" and move_pct is not None
            and move_pct <= SPY_BREAKER_PCT):
        reasons.append("SPY %.0f%% breaker" % SPY_BREAKER_PCT)
    multiple = None
    if is_sector_spdr and move_pct is not None and atr_pct:
        multiple = abs(move_pct) / float(atr_pct)
        if multiple > SECTOR_ATR_MULTIPLE:
            reasons.append("%.1fx a normal day" % multiple)
    if not reasons:
        return None
    direction = None if move_pct is None else ("up" if move_pct > 0 else
                                               "down" if move_pct < 0 else "flat")
    why = ({"state": "known", "text": "On file: %s" % catalyst} if catalyst
           else {"state": "unknown", "text": NO_CATALYST_LINE})
    return {
        "card_kind": "LOUD_MOVE",
        "lane": LANE_CONTEXT,
        "pinned": True,
        "counts_against_cap": False,
        "ticker": ticker.upper(),
        "direction": direction,
        "move_pct": move_pct,
        "atr_multiple": (round(multiple, 2) if multiple is not None else None),
        "reasons": reasons,
        "why": why,
        "basis": ("price only (c)1: %s" % " / ".join(reasons)),
    }


# ── (c)2 VALUE MOVED ─────────────────────────────────────────────────────────

def value_moved(*, ticker: str, close: Optional[float],
                prior_value_high: Optional[float], prior_value_low: Optional[float],
                ib_high: Optional[float], ib_low: Optional[float],
                today_value_high: Optional[float], today_value_low: Optional[float],
                now_et: _dt.datetime) -> Optional[Dict[str, Any]]:
    """(c)2. THREE CONDITIONS, ALL REQUIRED, AND ALL IN THE SAME DIRECTION.

    The ruling joins them with AND and with "the same way" twice: a bar closes beyond the prior
    value-area edge, AND price breaks the initial balance the same way, AND today's value builds
    the same way. Any one of the three alone is a different, weaker claim, and the card's word is
    "value MOVED" -- which is the conjunction, not the first clause.

    From 10:30 ET only: before it the initial balance is not formed, so condition 2 would be a
    comparison against a level that does not exist yet.

    A MISSING INPUT IS NOT A FAILED CONDITION -- it is an unanswerable one, and the card does not
    fire. Treating absent as "not beyond" would make a card's non-appearance mean two things.
    """
    if now_et.time() < _et(VALUE_MOVED_FROM):
        return None
    if close is None:
        return None
    for lvl in (prior_value_high, prior_value_low, ib_high, ib_low,
                today_value_high, today_value_low):
        if lvl is None:
            return None
    side = None
    if close > prior_value_high and close > ib_high and today_value_high > prior_value_high:
        side = "above"
    elif close < prior_value_low and close < ib_low and today_value_low < prior_value_low:
        side = "below"
    if side is None:
        return None
    edge = prior_value_high if side == "above" else prior_value_low
    ib = ib_high if side == "above" else ib_low
    return {
        "card_kind": "VALUE_MOVED",
        "lane": LANE_WATCH,
        "pinned": False,
        "counts_against_cap": True,
        "ticker": ticker.upper(),
        "direction": "up" if side == "above" else "down",
        "side": side,
        "close": close,
        "level": edge,
        "reasons": ["STRUCTURE"],
        "basis": ("closed %s the prior value edge %.4f, broke the initial balance %s %.4f, and "
                  "today's value is building %s it" % (side, edge, side, ib, side)),
        "stale_if": ("Stale if back %s %.4f"
                     % ("below" if side == "above" else "above", edge)),
    }


# ── (c)3 FAILED BREAK / FAILED AUCTION: Position Watch's detector, reused ────

#: The three level kinds (c)3 lists, each a pair of (high, low) passed to the SAME detector.
LEVEL_KINDS = ("value", "ib", "prior_day")


def failed_break(*, ticker: str, session_closes: Sequence[float],
                 levels: Dict[str, Tuple[Optional[float], Optional[float]]],
                 daily: bool = False) -> Optional[Dict[str, Any]]:
    """(c)3, by REUSING `position_watch.failed_breakout` once per level kind.

    `levels` maps a kind in LEVEL_KINDS to its (high, low). The kinds are tried in the ruling's
    own order -- value edge, IB edge, prior-day high/low -- and the FIRST that fires is the card,
    because one ticker gets one card and a second level firing on the same bar is the same event
    seen through a different level, not a second notable.

    `daily` selects (c)3's daily version: the same detector over daily closes, which is what
    "plus a daily version" means. The detector is level-agnostic, so nothing about it changes --
    only the series and the levels handed to it. That is the whole reason the ruling says not to
    write a second one.
    """
    closes = [float(c) for c in session_closes if c is not None]
    for kind in LEVEL_KINDS:
        hi, lo = levels.get(kind, (None, None))
        if hi is None and lo is None:
            continue
        ev = _failed_breakout(closes, hi, lo)
        if not ev:
            continue
        return {
            "card_kind": "FAILED_BREAK",
            "lane": LANE_WATCH,
            "pinned": False,
            "counts_against_cap": True,
            "ticker": ticker.upper(),
            # THE CARD'S DIRECTION IS THE FAILURE'S, NOT THE BREAK'S. A break that failed
            # upward is a DOWNWARD event: the same inversion Position Watch's
            # `_alert_direction` makes, and getting it backwards would label the card with the
            # direction of the move that just stopped working.
            "direction": "down" if ev["side"] == "above" else "up",
            "side": ev["side"],
            "level": ev["level"],
            "close": ev["close"],
            "event": ev["event"],
            "level_kind": kind,
            "daily": bool(daily),
            "reasons": ["STRUCTURE"],
            "basis": "%s %s: %s" % ("daily" if daily else "intraday", kind, ev["basis"]),
            "stale_if": ("Stale if a %s closes back %s %.4f"
                         % ("day" if daily else "bar", ev["side"], ev["level"])),
            "detector": "position_watch.failed_breakout",
        }
    return None


# ── (c)4 TREND-STATE CHANGE ──────────────────────────────────────────────────

def stack_class(ma20: Optional[float], ma50: Optional[float],
                ma120: Optional[float]) -> Optional[str]:
    """The 20/50/120 stack's class, or None when any leg is missing.

    Three classes and no fourth: BULLISH when 20 > 50 > 120, BEARISH when 20 < 50 < 120, MIXED
    otherwise. MIXED is a real class, not a failure to classify -- a crossing stack is the thing
    (c)4 is watching for, so collapsing it into "unknown" would hide the transition.
    """
    if ma20 is None or ma50 is None or ma120 is None:
        return None
    if ma20 > ma50 > ma120:
        return "BULLISH"
    if ma20 < ma50 < ma120:
        return "BEARISH"
    return "MIXED"


def trend_change(*, ticker: str,
                 adx: Optional[float] = None, adx_prior: Optional[float] = None,
                 di_plus: Optional[float] = None, di_minus: Optional[float] = None,
                 ma20: Optional[float] = None, ma50: Optional[float] = None,
                 ma120: Optional[float] = None,
                 stack_prior: Optional[str] = None,
                 close: Optional[float] = None, close_prior: Optional[float] = None,
                 ma200: Optional[float] = None, ma200_prior: Optional[float] = None,
                 volume: Optional[float] = None,
                 avg_volume: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """(c)4, after the close and shown at the open. Three triggers, any one of which fires.

    1. ADX CROSSES 25 WITH A DIRECTION. A CROSS, not a level: `adx_prior` below and `adx` at or
       above. A level test would fire every day ADX stayed above 25, which is a state and not a
       change -- the same distinction the regime classifier's `ma20_crossed_above_ma50` had to
       be corrected for. "With a direction" needs DI+ against DI-; without both, the cross has
       no direction and does not fire.
    2. THE 20/50/120 STACK CHANGES CLASS. Needs the prior class; without it there is no change
       to observe, only a current state.
    3. A CLOSE THROUGH THE 200-DAY ON >= 1.5x VOLUME. Through, so the prior close was on the
       other side. `avg_volume` is the denominator and its absence is not zero.
    """
    reasons: List[str] = []
    detail: List[str] = []
    direction = None

    if (adx is not None and adx_prior is not None
            and adx_prior < ADX_TREND_LEVEL <= adx
            and di_plus is not None and di_minus is not None and di_plus != di_minus):
        up = di_plus > di_minus
        direction = "up" if up else "down"
        reasons.append("TREND")
        detail.append("ADX crossed %.0f (%.1f -> %.1f), %s"
                      % (ADX_TREND_LEVEL, adx_prior, adx, "DI+ over DI-" if up else "DI- over DI+"))

    now_class = stack_class(ma20, ma50, ma120)
    if now_class and stack_prior and now_class != stack_prior:
        reasons.append("TREND")
        detail.append("stack %s -> %s" % (stack_prior, now_class))
        if direction is None:
            direction = ("up" if now_class == "BULLISH" else
                         "down" if now_class == "BEARISH" else None)

    if (close is not None and close_prior is not None and ma200 is not None
            and ma200_prior is not None and volume is not None and avg_volume):
        crossed_up = close_prior <= ma200_prior and close > ma200
        crossed_down = close_prior >= ma200_prior and close < ma200
        mult = float(volume) / float(avg_volume)
        if (crossed_up or crossed_down) and mult >= BREAK_200_VOLUME_MULTIPLE:
            reasons.append("TREND")
            detail.append("closed %s the 200-day on %.1fx volume"
                          % ("above" if crossed_up else "below", mult))
            if direction is None:
                direction = "up" if crossed_up else "down"

    if not detail:
        return None
    return {
        "card_kind": "TREND_CHANGE",
        "lane": LANE_WATCH,
        "pinned": False,
        "counts_against_cap": True,
        "ticker": ticker.upper(),
        "direction": direction,
        "reasons": sorted(set(reasons)) or ["TREND"],
        "stack_class": now_class,
        "stack_prior": stack_prior,
        "basis": " · ".join(detail),
        "after_close": True,
    }


# ── (c)5 ROTATION SHIFT: a Context line, never a card ────────────────────────

def rotation_shift(*, rotation_now: Optional[str] = None, rotation_prior: Optional[str] = None,
                   theme_changes: Optional[Iterable[Dict[str, Any]]] = None
                   ) -> Optional[Dict[str, Any]]:
    """(c)5, after the close, AS A CONTEXT LINE. Never a ticker card, so it never meets the cap.

    Two triggers: a sector rotation label flips, or a theme changes status. A theme carrying a
    DATA-QUALITY WARNING IS SUPPRESSED -- the ruling says so, and the reason is that a status
    change driven by a known-bad feed is a change in the feed, not in the market. Suppressed
    themes are RETURNED in `suppressed` rather than dropped, so the line can say how many were
    held back; a silently shortened list is indistinguishable from a quiet day.
    """
    items: List[str] = []
    suppressed: List[str] = []
    if rotation_now and rotation_prior and rotation_now != rotation_prior:
        items.append("rotation %s → %s" % (rotation_prior, rotation_now))
    for th in (theme_changes or []):
        name = str(th.get("theme") or th.get("name") or "?")
        if th.get("data_quality_warning"):
            suppressed.append(name)
            continue
        before, after = th.get("status_prior"), th.get("status")
        if before and after and before != after:
            items.append("%s %s → %s" % (name, before, after))
    if not items:
        return None
    return {
        "card_kind": "ROTATION_SHIFT",
        "lane": LANE_CONTEXT,
        "pinned": False,
        "counts_against_cap": False,
        "ticker": None,
        "direction": None,
        "items": items,
        "suppressed_themes": suppressed,
        "reasons": ["SECTOR"],
        "basis": (" · ".join(items)
                  + ("" if not suppressed
                     else " (%d theme(s) held back for a data-quality warning)"
                     % len(suppressed))),
        "after_close": True,
    }


# ── (d)/(e) may it be SHOWN ──────────────────────────────────────────────────

def may_show(card: Dict[str, Any], *, now_et: _dt.datetime,
             shown_today: int, tickers_shown_today: Iterable[str],
             universe: Iterable[str], no_structure_cards: Iterable[str],
             held_tickers: Iterable[str] = (),
             pythia_ok: bool = True,
             pythia_reason: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """(d) and (e). (shown, drop_reason). Every refusal names itself, for `notables_log`.

    THE ORDER IS DELIBERATE and each step is cheaper or more absolute than the next:
      1. hours -- nothing shows outside them, LOUD MOVE included;
      2. held position -- it belongs in Your book, and showing it twice is the one placement the
         ruling's footer explicitly denies;
      3. universe -- off-universe names are LOGGED ONLY (e);
      4. the structure-card exclusion (QQQ, R-IV.1258(a)4);
      5. the PYTHIA gate, which is the card's own evidence and not a quota;
      6. one card per ticker per day -- a new reason lights another chip on the existing card;
      7. the cap, LAST, because a card refused by the cap WOULD otherwise have been shown, and
         that is the only drop reason that says something about the day rather than the card.
    """
    from models.notables_log import (DROP_ALREADY_TODAY, DROP_CAP_REACHED, DROP_HELD_POSITION,
                                     DROP_NOT_IN_UNIVERSE, DROP_OUT_OF_HOURS,
                                     DROP_PYTHIA_STALE, DROP_STRUCTURE_CARD_EXCLUDED)

    ok, _why = in_hours(now_et)
    if not ok:
        return False, DROP_OUT_OF_HOURS
    ticker = (card.get("ticker") or "").upper()
    kind = card.get("card_kind")
    if ticker:
        if ticker in {t.upper() for t in held_tickers}:
            return False, DROP_HELD_POSITION
        if ticker not in {t.upper() for t in universe}:
            return False, DROP_NOT_IN_UNIVERSE
        if (kind in ("VALUE_MOVED", "FAILED_BREAK")
                and ticker in {t.upper() for t in no_structure_cards}):
            return False, DROP_STRUCTURE_CARD_EXCLUDED
    if kind == "VALUE_MOVED" and not pythia_ok:
        return False, DROP_PYTHIA_STALE
    if not card.get("counts_against_cap"):
        # LOUD MOVE and the Context line: uncapped and not subject to one-per-ticker, because
        # (c)1 pins the loud move and (c)5 is a line rather than a card.
        return True, None
    if ticker and ticker in {t.upper() for t in tickers_shown_today}:
        return False, DROP_ALREADY_TODAY
    if shown_today >= DAILY_TICKER_CAP:
        return False, DROP_CAP_REACHED
    return True, None


def finish_card(card: Dict[str, Any], *, counter_evidence: Sequence[str],
                stale_if: Optional[str] = None) -> Dict[str, Any]:
    """Attach (g)'s required halves, or refuse the card.

    A CARD WITHOUT COUNTER-EVIDENCE IS NOT A CARD. (g) lists reasons as chips, counter-evidence
    from the same data, and the stale fact -- so a card missing the half that argues against it
    is half a card, and rendering it anyway is how a surface that was designed to be even-handed
    becomes a surface that only agrees with itself. Refused here rather than rendered thin.

    The Context line is exempt: (c)5 is a LINE, and counter-evidence for "XLC rotated in" would
    be invented rather than measured (R-IV.925(b)).
    """
    if card.get("card_kind") != "ROTATION_SHIFT" and not counter_evidence:
        raise ValueError("a %s card needs counter-evidence from the same data (R-IV.1259(g))"
                         % card.get("card_kind"))
    out = dict(card)
    out["counter_evidence"] = list(counter_evidence)
    if stale_if:
        out["stale_if"] = stale_if
    if out.get("stale_if"):
        out["stale_note"] = "a fact about this card, not a stop"
    return out
