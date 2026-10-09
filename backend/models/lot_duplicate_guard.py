"""R-IV.767(c) — a double-submitted entry is refused, and only the second one.

THE DEFECT. The principal's UI entry wrote SOXS 15 @ 32.99 twice, at 17:21:03 and 17:21:13,
identical in every field, putting 494.85 of basis on the row that no broker ever charged.
`cash_flows` already had a duplicate guard and refused the matching movement; `position_lots`
had none, so the two halves of one entry disagreed — the money was protected and the position
was not.

WHY THE WINDOW IS MEASURED ON `created_at`, NEVER ON `fill_time`. Both SOXS lots carry
`fill_time` 2026-10-08T06:00:00Z — the trade DATE widened to an instant, which is what the form
sends. `fill_time` is principal-reported, so it is IDENTICAL for every same-day add: a window
measured on it would refuse a legitimate second buy made six hours later, and it could not
distinguish the double-submit at all, because both copies sit at the same point. `created_at` is
when the row was WRITTEN, and being written twice is the thing that actually happened.

WHY IMPORTS ARE OUT OF SCOPE. Two identical fills seconds apart are NORMAL in a broker export —
one order filled in two parts at one price. For an import the broker is the authority and the hub
is copying it, so refusing the second would corrupt the book in order to protect it. The guard is
anchored to the window it guards (R-IV.127): principal entries, where the only thing that can
produce two identical fills inside a minute is one form submitted twice.

WHAT THIS CANNOT DO. The two writes were TEN SECONDS apart. Disabling the submit button while a
save is in flight — also ruled, and also built — would not have stopped them, because the first
save had long since returned. That guard stops a double-click; this one stops a double-entry.
Of the two, only this half would have prevented the defect on the record.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Optional

# One minute, as ruled. Named once, so the refusal message, the SQL window and the tests cannot
# drift apart into three different minutes.
GUARD_WINDOW_SECONDS = 60

# The five fields that make an entry the same entry, in the ruled order. Stated as data so the
# comparison, the message and the tests all read from one list.
IDENTITY_FIELDS = ("account", "ticker", "side", "qty", "price")

# The lot sources this guard speaks for. A principal entry is a human filling in a form; an
# IMPORT is a broker export being copied, where identical fills are legitimate.
GUARDED_SOURCES = ("MANUAL", "PRINCIPAL-ENTRY")


def _dec(value: Any) -> Optional[Decimal]:
    """A Decimal carrying the value as WRITTEN, not a float's tail (#27).

    `Decimal(str(32.99))` is exactly 32.99. `Decimal(32.99)` is
    32.9899999999999948840923025272786617279052734375, and comparing THAT to the NUMERIC the
    database hands back would never be equal — a guard that silently never fires, which is worse
    than no guard at all, because it also reports that it is protecting you.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip().upper() or None


def _same_text(a: Any, b: Any) -> bool:
    """Two names are the same name.

    Case-insensitive because the book stores `fidelity_roth` while the form sends
    `FIDELITY_ROTH` — the scope-must-not-depend-on-case lesson, applied to a comparison rather
    than to an identity test.
    """
    return _text(a) == _text(b)


def _same_num(a: Any, b: Any) -> bool:
    """Equal by VALUE, so 32.99 and Decimal('32.990') are the same price.

    Normalised through `_dec` and deliberately NOT quantized: rounding to the cent would make
    32.990 and 32.994 the same price, and those are two different trades.
    """
    da, db = _dec(a), _dec(b)
    if da is None or db is None:
        return False            # an unstated figure is not a match for anything
    return da == db


def is_twin(candidate: Mapping[str, Any], existing: Mapping[str, Any]) -> bool:
    """Identical in all five ruled fields. Says nothing about WHEN — that is the caller's."""
    return (_same_text(candidate.get("account"), existing.get("account"))
            and _same_text(candidate.get("ticker"), existing.get("ticker"))
            and _same_text(candidate.get("side"), existing.get("side"))
            and _same_num(candidate.get("qty"), existing.get("qty"))
            and _same_num(candidate.get("price"), existing.get("price")))


def within_window(created_at: Any, now: Any,
                  window_seconds: int = GUARD_WINDOW_SECONDS) -> bool:
    """Was it written inside the window, counted backwards from `now`.

    A row with no instant is NOT in the window. Reading an absent fact as a satisfied condition
    is this register's recurring failure, and here it would refuse a good entry on the strength
    of a row nobody can place in time.
    """
    if created_at is None or now is None:
        return False
    try:
        elapsed = (now - created_at).total_seconds()
    except TypeError:
        # A naive timestamp against an aware one. Refusing to guess is the point: this module
        # never adjudicates clocks, because reading one through the wrong offset invents six
        # hours and a day boundary.
        return False
    return 0 <= elapsed <= window_seconds


def find_twin(candidate: Mapping[str, Any], recent: Iterable[Mapping[str, Any]], *, now: Any,
              window_seconds: int = GUARD_WINDOW_SECONDS) -> Optional[Mapping[str, Any]]:
    """The most recently written identical entry inside the window, or None.

    `now` is keyword-only and passed in: the decision is reproducible in a test and reads no
    clock of its own.
    """
    hits = [r for r in recent
            if within_window(r.get("created_at"), now, window_seconds)
            and is_twin(candidate, r)]
    if not hits:
        return None
    return max(hits, key=lambda r: r["created_at"])


def is_guarded_source(source: Any) -> bool:
    """MANUAL and principal entries are guarded; IMPORT and the legacy single lot are not."""
    s = _text(source) or ""
    return any(s.startswith(g) for g in GUARDED_SOURCES)


def _num_str(value: Any) -> str:
    d = _dec(value)
    if d is None:
        return "?"
    n = d.normalize()
    # `normalize()` renders a whole number as 1.5E+1, which is not how anyone writes 15 shares.
    return format(n.quantize(Decimal(1)) if n == n.to_integral_value() else n, "f")


def refusal_detail(twin: Mapping[str, Any], candidate: Mapping[str, Any], *, now: Any,
                   confirm_field: str = "confirm_duplicate") -> str:
    """The sentence the UI shows. Plain language, and it names the way through.

    It states what was NOT written, because a refusal that only says "duplicate" leaves the
    principal unsure whether the book now holds this entry once or twice — which is the
    uncertainty the whole guard exists to end.
    """
    elapsed = ""
    try:
        secs = int(round((now - twin["created_at"]).total_seconds()))
        elapsed = " %d second%s ago" % (secs, "" if secs == 1 else "s")
    except (TypeError, KeyError):
        pass
    lot, where = twin.get("id"), twin.get("position_id")
    return (
        "This is the same entry twice: %s %s @ %s in %s was already saved%s%s%s. "
        "Nothing was saved this time, so the book holds it once. "
        "If you really made this trade twice, tick the confirm box (%s) and submit again."
        % (_num_str(candidate.get("qty")), _text(candidate.get("ticker")) or "?",
           _num_str(candidate.get("price")), candidate.get("account") or "?", elapsed,
           (" as lot %s" % lot) if lot is not None else "",
           (" on %s" % where) if where else "",
           confirm_field))
