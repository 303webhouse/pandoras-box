"""Grades. Pure: a row, a series, a session source in -> a grade out.

RETURN-TYPE (the measure CC-QUERY used for R-IV.424): the aligned price return from the
entry to the close of T+n.
  ret_pct     entry = the fire-time price, put on the series' basis (basis.resolve_entry)
  ret_v2_pct  entry = the anchor session's close -- both ends from one series, immune to
              the basis seam, and blind to the fire-day remainder. Recorded beside, never
              instead.
  ret_raw_pct the unaligned return (for excess over drift).

WALK-TYPE (a strategy's own outcome, in R): from the session AFTER the anchor, each bar is
checked against the stop and target, both put on the same basis as the entry.
  * a gap through a level exits at the OPEN -- the price actually available;
  * a bar that touches both levels is booked as the STOP and flagged `ambiguous_bar`: the
    order inside a daily bar is unknown, and the conservative reading is taken;
  * neither by the last session is a time exit at its close, labelled as the population's
    rule names it (EXPIRED for a rule with an expiry -- DEF-SHADOW-EXPIRES-AT-DROPPED).
  An intraday fire's remaining fire-day is not walked; the row says so.

A pending grade (its last session not yet closed) is not a grade and is never written.

SESSIONS. Shadow grading uses the one market calendar (so a vendor hole on a trading day is
seen as a hole). History runs pass a SeriesSessions, and their anchor is the fire's own ET
date, which must be one of the series' dates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from stable_engine.market_calendar import CalendarHorizonError

from . import basis as B
from . import sessions as S

LONG_WORDS = {"LONG", "BUY", "BULL", "BULLISH"}
SHORT_WORDS = {"SHORT", "SELL", "BEAR", "BEARISH"}

GRADED, PENDING, UNGRADED = "graded", "pending", "ungraded"


def direction_sign(direction: Optional[str]) -> Optional[int]:
    d = (direction or "").strip().upper()
    return 1 if d in LONG_WORDS else -1 if d in SHORT_WORDS else None


@dataclass
class ShadowRow:
    signal_id: str
    ticker: str
    direction: str
    fired_at: datetime
    entry_price: Optional[float]
    stop: Optional[float] = None
    target: Optional[float] = None
    entry_kind: str = B.ENTRY_INTRADAY
    tags: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Grade:
    signal_id: str
    method: str                      # return | walk
    horizon: int                     # sessions to exit (return) / maximum hold (walk)
    status: str = UNGRADED
    reason: Optional[str] = None
    anchor_session: Optional[date] = None
    target_session: Optional[date] = None
    entry_raw: Optional[float] = None
    entry_factor: Optional[float] = None
    entry_basis: Optional[float] = None
    anchor_close: Optional[float] = None
    exit_price: Optional[float] = None
    ret_pct: Optional[float] = None
    ret_raw_pct: Optional[float] = None
    ret_v2_pct: Optional[float] = None
    r_multiple: Optional[float] = None
    outcome: Optional[str] = None
    flags: List[str] = field(default_factory=list)
    basis: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _pct(a: float, b: float) -> float:
    return (b / a - 1.0) * 100.0


def _anchor(row: ShadowRow, sessions) -> date:
    if sessions is None:
        return S.anchor_session(row.fired_at)
    return S.as_utc(row.fired_at).astimezone(S.ET).date()


def _start(row: ShadowRow, series, method: str, horizon: int, sessions
           ) -> Tuple[Grade, Optional[int], Optional["B.BasisResolution"]]:
    """The checks every grade shares. The Grade comes back UNGRADED with a reason when the
    row cannot be graded; otherwise with the entry on the series' basis and sign/res set."""
    g = Grade(row.signal_id, method, horizon, entry_raw=row.entry_price)
    sign = direction_sign(row.direction)
    if sign is None:
        g.reason = "direction_unknown"
        return g, None, None
    try:
        g.anchor_session = _anchor(row, sessions)
    except CalendarHorizonError:
        g.reason = "calendar_horizon"
        return g, None, None
    if series is None:
        g.reason = "no_series"
        return g, None, None
    res = B.resolve_entry(row.entry_price, g.anchor_session, series, row.entry_kind)
    g.basis = {**series.basis(), "entry_kind": row.entry_kind, "resolution": res.as_dict()}
    if not res.resolved:
        g.reason = res.reason
        if res.reason == "entry_outside_anchor_session":
            g.flags.append("entry_anomaly")
        return g, None, None
    g.entry_factor = round(res.factor, 8)
    g.entry_basis = res.entry_basis
    g.anchor_close = series.close(g.anchor_session)
    if res.ambiguous:
        g.flags.append("basis_ambiguous")
    if res.events_applied:
        g.flags.append("split_adjusted_entry")
    return g, sign, res


def _window_flags(g: Grade, res, series, start: date, end: date) -> None:
    if res.unapplied_between(start, end):
        g.flags.append("unapplied_event_in_window")
    closes = {d: series.bars[d]["c"] for d in series.dates if start <= d <= end}
    for step in B.find_steps(closes, series.splits):
        # A step that matches a split ratio is two bases inside one series; anything else is
        # a large move, which is information and not a defect.
        flag = "adjustment_seam_in_window" if step.kind == "adjustment_seam" else "large_move_in_window"
        if flag not in g.flags:
            g.flags.append(flag)


def grade_return(row: ShadowRow, series, horizon: int, through: date, sessions=None) -> Grade:
    g, sign, res = _start(row, series, "return", horizon, sessions)
    if sign is None:
        return g
    try:
        target = (sessions or S).nth_session(g.anchor_session, horizon)
    except CalendarHorizonError:
        g.reason = "calendar_horizon"
        return g
    if target is None or target > through:
        g.status, g.reason = PENDING, "not_matured"
        return g
    g.target_session = target
    exit_close = series.close(target)
    if exit_close is None:
        g.reason = "no_target_bar"          # a vendor hole on a trading day, never borrowed
        return g
    raw = _pct(g.entry_basis, exit_close)
    g.exit_price = exit_close
    g.ret_raw_pct = round(raw, 6)
    g.ret_pct = round(sign * raw, 6)
    g.ret_v2_pct = round(sign * _pct(g.anchor_close, exit_close), 6)
    _window_flags(g, res, series, g.anchor_session, target)
    g.status = GRADED
    return g


def grade_walk(row: ShadowRow, series, max_hold: int, through: date, sessions=None,
               time_exit_label: str = "TIME") -> Grade:
    g, sign, res = _start(row, series, "walk", max_hold, sessions)
    if sign is None:
        return g
    if row.entry_kind == B.ENTRY_INTRADAY:
        g.flags.append("fire_day_not_walked")
    if row.stop is None:
        g.reason = "no_stop"
        return g
    entry = g.entry_basis
    stop = row.stop * res.factor
    target = row.target * res.factor if row.target is not None else None
    risk = (entry - stop) * sign
    if risk <= 0 or (target is not None and (target - entry) * sign <= 0):
        g.reason = "levels_invalid"
        return g
    g.basis["levels_on_basis"] = {"stop": stop, "target": target}

    try:
        path = (sessions or S).sessions_after(g.anchor_session, max_hold)
    except CalendarHorizonError:
        g.reason = "calendar_horizon"
        return g
    if len(path) < max_hold:                 # a history series that ends inside the hold
        g.status, g.reason = PENDING, "not_matured"
        return g

    exit_price = outcome = exit_day = None
    for d in path:
        if d > through:
            g.status, g.reason = PENDING, "not_matured"
            return g
        bar = series.bar(d)
        if bar is None:
            g.reason = "no_bar_in_walk"
            return g
        o, h, l = bar["o"], bar["h"], bar["l"]
        if (o - stop) * sign <= 0:
            exit_price, outcome = o, "STOP_GAP"
        elif target is not None and (o - target) * sign >= 0:
            exit_price, outcome = o, "TARGET_GAP"
        else:
            hit_stop = l <= stop if sign > 0 else h >= stop
            hit_target = target is not None and (h >= target if sign > 0 else l <= target)
            if hit_stop:
                exit_price, outcome = stop, "STOP"
                if hit_target:
                    g.flags.append("ambiguous_bar")
            elif hit_target:
                exit_price, outcome = target, "TARGET"
        if outcome:
            exit_day = d
            break
    if outcome is None:
        exit_day = path[-1]
        exit_price, outcome = series.bar(exit_day)["c"], time_exit_label

    raw = _pct(entry, exit_price)
    g.target_session = exit_day
    g.exit_price = exit_price
    g.outcome = outcome
    g.ret_raw_pct = round(raw, 6)
    g.ret_pct = round(sign * raw, 6)
    g.r_multiple = round((exit_price - entry) * sign / risk, 6)
    _window_flags(g, res, series, g.anchor_session, exit_day)
    g.status = GRADED
    return g
