"""B4's Event Strip: the next ten sessions, with what is scheduled and what is estimated.

PURE. Dates in, strip out, so every rule here is testable without UW, the book or the earnings
table.

THE ONE THING THIS FILE IS CAREFUL ABOUT is the difference between a SCHEDULED date and an
ESTIMATED one. FOMC, CPI, jobs, GDP and PCE are published dates. Monthly OpEx is a rule
(the third Friday). The book's expiries are facts in the book. THE BUYBACK BLACKOUT IS NONE OF
THOSE -- there is no public per-issuer blackout calendar, so it is a window computed from a
heuristic, and the mock already labels it "est." for that reason. It is kept visibly separate
and its rule travels in the payload, because an estimate that looks like a schedule is the
worst of the three.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: The events the strip calls MACRO, and the words it prints for them. A source event whose
#: name matches none of these is still shown, under its own name -- an unrecognised event is
#: not a reason to hide it (R-IV.925(b): do not invent labels, and do not drop what you cannot
#: classify either).
MACRO_KEYS = {
    "fomc": "FOMC",
    # BOTH SPELLINGS, and the long one is the one that matters: a vendor calendar writes
    # "Consumer Price Index", not "CPI", so matching only the acronym would have silently
    # dropped the single most-watched print on the strip. Found by a test over the ruled
    # event set rather than by reading a sample payload.
    "cpi": "CPI",
    "consumer price": "CPI",
    "ppi": "PPI",
    "producer price": "PPI",
    "nonfarm": "JOBS",
    "payroll": "JOBS",
    "unemployment": "JOBS",
    "gdp": "GDP",
    "pce": "PCE",
    "retail sales": "RETAIL",
    "ism": "ISM",
}

#: An FOMC decision day is the loudest thing on the strip, so it gets its own kind.
KIND_TOP = "top"
KIND_MACRO = "macro"
KIND_BOOK = "book"

#: The blackout heuristic, stated as a constant pair so the payload can print the rule rather
#: than a bare flag. From 14 days before a calendar-quarter end to 30 days after it: the window
#: inside which most issuers are closed, which is as precise as a market-wide estimate can
#: honestly be.
BLACKOUT_BEFORE_QUARTER_END_DAYS = 14
BLACKOUT_AFTER_QUARTER_END_DAYS = 30
BLACKOUT_RULE = (
    "ESTIMATE, not a schedule: a session is flagged when it falls within %d days before or %d "
    "days after a calendar-quarter end. There is no public per-issuer blackout calendar, so "
    "this is a market-wide window and is labelled est. wherever it is shown"
    % (BLACKOUT_BEFORE_QUARTER_END_DAYS, BLACKOUT_AFTER_QUARTER_END_DAYS))


def third_friday(year: int, month: int) -> _dt.date:
    """Monthly OpEx: the third Friday of the month.

    Computed, not tabulated, because a table of expiry dates goes stale silently and this rule
    has not changed since listed options began. Holiday shifts are NOT applied here: when the
    third Friday is a holiday, expiry moves to the Thursday, and that is a market-calendar
    question the strip asks `is_trading_day` rather than guessing.
    """
    d = _dt.date(year, month, 1)
    # Friday is weekday 4. The first Friday is 1 + (4 - weekday) mod 7 days in.
    first_friday = 1 + (4 - d.weekday()) % 7
    return _dt.date(year, month, first_friday + 14)


def next_opex(today: _dt.date, *, is_trading_day=None) -> Tuple[_dt.date, int, str]:
    """(date, days away, basis) for the next monthly OpEx at or after `today`.

    `is_trading_day` is optional and, when given, moves a holiday expiry back to the previous
    trading day -- the actual market rule. Without it the raw third Friday is returned AND THE
    BASIS SAYS SO, rather than silently presenting an unadjusted date as adjusted.
    """
    y, m = today.year, today.month
    d = third_friday(y, m)
    if d < today:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        d = third_friday(y, m)
    basis = "the third Friday of %04d-%02d" % (y, m)
    if is_trading_day is not None:
        moved = d
        while is_trading_day(moved) is False:
            moved -= _dt.timedelta(days=1)
        if moved != d:
            basis += ", moved back to %s because the third Friday is not a trading day" % moved
        d = moved
    else:
        basis += " (no holiday adjustment applied: no calendar was supplied)"
    return d, (d - today).days, basis


def quarter_ends(year: int) -> List[_dt.date]:
    return [_dt.date(year, 3, 31), _dt.date(year, 6, 30),
            _dt.date(year, 9, 30), _dt.date(year, 12, 31)]


def in_blackout(day: _dt.date) -> bool:
    """The estimated buyback blackout. See BLACKOUT_RULE -- an estimate, and labelled one."""
    for y in (day.year - 1, day.year, day.year + 1):
        for qe in quarter_ends(y):
            if (qe - _dt.timedelta(days=BLACKOUT_BEFORE_QUARTER_END_DAYS) <= day
                    <= qe + _dt.timedelta(days=BLACKOUT_AFTER_QUARTER_END_DAYS)):
                return True
    return False


def macro_word(name: str) -> Optional[str]:
    """The strip's short word for a calendar event, or None when it is not a macro event."""
    low = str(name or "").lower()
    for needle, word in MACRO_KEYS.items():
        if needle in low:
            return word
    return None


def classify_macro(name: str) -> Tuple[Optional[str], str]:
    """(label, kind). An FOMC decision is KIND_TOP; everything recognised is KIND_MACRO."""
    word = macro_word(name)
    if word is None:
        return None, KIND_MACRO
    low = str(name or "").lower()
    if word == "FOMC" and ("decision" in low or "rate" in low or "statement" in low):
        return "FOMC 2pm", KIND_TOP
    return word, KIND_MACRO


def sessions_ahead(today: _dt.date, count: int, *, is_trading_day) -> List[_dt.date]:
    """The next `count` trading sessions, today included when it is one.

    A calendar-day strip would show a weekend as two quiet days and push real events off the
    end; the strip's promise is "the next ten SESSIONS".
    """
    out: List[_dt.date] = []
    d = today
    guard = 0
    while len(out) < count and guard < count * 5:
        if is_trading_day(d) is not False:
            out.append(d)
        d += _dt.timedelta(days=1)
        guard += 1
    return out


def build_strip(today: _dt.date, *, is_trading_day,
                macro: Sequence[Dict[str, Any]] = (),
                book_expiries: Sequence[Dict[str, Any]] = (),
                earnings: Sequence[Dict[str, Any]] = (),
                sessions: int = 10) -> Dict[str, Any]:
    """The strip. Every input is already-fetched data; nothing here calls out.

    `macro`: [{"date": date, "name": str}]
    `book_expiries`: [{"date": date, "label": str}]
    `earnings`: [{"date": date, "in_book": bool}]
    """
    days = sessions_ahead(today, sessions, is_trading_day=is_trading_day)
    by_day: Dict[_dt.date, Dict[str, Any]] = {
        d: {"dow": d.strftime("%a").upper(), "dd": "%02d" % d.day, "iso": d.isoformat(),
            "events": [], "earn": 0, "book_earn": 0, "blackout": in_blackout(d)}
        for d in days}

    for ev in macro:
        d = ev.get("date")
        if d not in by_day:
            continue
        label, kind = classify_macro(ev.get("name", ""))
        if label is None:
            # Shown under its own name rather than dropped. See MACRO_KEYS.
            label, kind = str(ev.get("name", ""))[:18], KIND_MACRO
        by_day[d]["events"].append({"k": label, "kind": kind})

    for ex in book_expiries:
        d = ex.get("date")
        if d in by_day:
            by_day[d]["events"].append({"k": ex.get("label", "expiry"), "kind": KIND_BOOK})

    for e in earnings:
        d = e.get("date")
        if d not in by_day:
            continue
        by_day[d]["earn"] += 1
        if e.get("in_book"):
            by_day[d]["book_earn"] += 1

    opex, opex_days, opex_basis = next_opex(today, is_trading_day=is_trading_day)
    return {
        "title": "Next %d sessions" % len(days),
        "days": [by_day[d] for d in days],
        "next_opex": "NEXT OPEX %s · %dd" % (opex.strftime("%m-%d"), opex_days),
        "next_opex_date": opex.isoformat(),
        "next_opex_basis": opex_basis,
        "blackout_label": "BUYBACK BLACKOUT est.",
        "blackout_rule": BLACKOUT_RULE,
        "legend": ["MACRO", "YOUR BOOK"],
        "caption": "server calendar · display only",
    }
