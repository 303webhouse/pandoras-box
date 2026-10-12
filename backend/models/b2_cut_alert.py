"""The B2 three-day cut alert — TA-141 §3, ruled in R-IV.888(c)1.

A B2 position that is not making money by the close of its third full trading session is
flagged. It is a PROMPT, never an action: it fires once, flags the row, and never closes
anything.

THE CLOCK NEVER RESETS, and that is the rule most easily broken by accident. The cut session is
a function of the ENTRY SESSION ALONE. An add, a partial exit, a re-mark, a status change, a
redeploy — none of them may move it. So nothing in this module takes "now" as an input to the
cut calculation; `cut_session()` sees only the entry date, and `decide()` compares a clock to a
cut it did not help compute.

"THE THIRD FULL TRADING SESSION AFTER THE ENTRY SESSION" means three TRADING days counted from
the session after entry. An entry at 15:58 gets the same three sessions as one at 09:31, because
the entry session is excluded rather than prorated — that is what "after the entry session"
settles, and it is also why no intraday time enters this calculation.

FLAT FIRES. The bar is "total P&L > 0 on the mark", so exactly zero does NOT pass. A position
that has gone nowhere in three sessions is the case the alert is for.

A NULL MARK IS **UNDETERMINED**, NOT A FIRE AND NOT A PASS. Without a mark there is no total,
and guessing in either direction is worse than saying so: a fabricated pass hides a dead
position, a fabricated fire cries wolf about one nobody can price.

EXPIRY-STOPPED WHEN THE THIRD SESSION FALLS ON OR AFTER EXPIRY. On that path the position's own
expiry arrives first and governs; a three-day prompt about something expiring in two days is
noise. `>=` and not `>`: a cut landing exactly on expiry day is the expiry's business.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SESSIONS_TO_CUT = 3
BUCKET = "B2"

# Verdicts.
NOT_YET = "NOT_YET"
EXPIRY_STOPPED = "EXPIRY_STOPPED"
UNDETERMINED = "UNDETERMINED"
PASS = "PASS"
FIRE = "FIRE"
ALREADY_FIRED = "ALREADY_FIRED"

# The close, in ET. The cut is evaluated AT the close of the third session, so a check at 15:00
# on that day is still NOT_YET.
MARKET_CLOSE_ET = (16, 0)


def _as_date(value: Any) -> Optional[date]:
    """A date from a date, a datetime (in ET), or an ISO string. None when unreadable.

    A datetime is converted to its ET calendar date, never its UTC one: `entry_date` is
    TIMESTAMPTZ, and an entry at 21:00 UTC is the SAME session as one at 14:00 UTC, not the next
    one. Using the UTC date would push every late-afternoon entry a day forward and shorten its
    clock by a session.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(ET).date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(ET).date()
    except (ValueError, TypeError):
        return None


def cut_session(entry: Any) -> Optional[date]:
    """The third full trading session AFTER the entry session. None if the calendar cannot say.

    Takes the entry and nothing else. There is deliberately no `now` parameter: a cut that could
    see the current time is a cut that could move, and "the clock never resets" is the rule.
    """
    from stable_engine.market_calendar import CalendarHorizonError, add_trading_days

    d = _as_date(entry)
    if d is None:
        return None
    try:
        return add_trading_days(d, SESSIONS_TO_CUT)
    except CalendarHorizonError:
        return None
    except Exception:                                               # noqa: BLE001
        return None


def total_pnl(realized: Any, unrealized: Any) -> Tuple[Optional[Decimal], Optional[str]]:
    """(total, undetermined_reason). The total is realized + unrealized, to the cent.

    THE TWO NULLS ARE NOT THE SAME, and this is the asymmetry worth stating:

      * `unrealized` NULL means THERE IS NO MARK. Nothing can be totalled, so the verdict is
        UNDETERMINED.
      * `realized` NULL means nothing has been closed yet, which is a known ZERO rather than an
        unknown. A position with no closures has no realized P&L.

    Treating the second as unknown would make every untouched position undeterminable, and
    treating the first as zero would report a dead position as flat and fire on it for the wrong
    reason. Decimal(str(x)) throughout: Decimal(32.99) is 32.98999999999999488, and a total
    compared against zero must not be decided by a float artefact.
    """
    if unrealized is None or (isinstance(unrealized, str) and not unrealized.strip()):
        return None, "no mark on the position"
    try:
        u = Decimal(str(unrealized))
    except Exception:                                               # noqa: BLE001
        return None, "mark unreadable: %r" % (unrealized,)
    try:
        r = Decimal(str(realized)) if realized is not None else Decimal("0")
    except Exception:                                               # noqa: BLE001
        return None, "realized unreadable: %r" % (realized,)
    return (r + u), None


def decide(row: Dict[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The verdict for one position. Pure: no clock of its own beyond the injected `now`.

    `realized` SHOULD be supplied from the closure ledger rather than the row's own column -- a
    partial exit's realized stays on an OPEN row and the row's figure has been seen to
    under-report the book. The caller owns that sourcing; this function totals what it is given.
    """
    now = now or datetime.now(ET)
    out: Dict[str, Any] = {"verdict": NOT_YET, "cut_session": None, "total_pnl": None,
                           "reason": ""}

    if row.get("b2_cut_alerted_at"):
        out["verdict"] = ALREADY_FIRED
        out["reason"] = "already fired at %s; it fires once and then flags" % (
            row.get("b2_cut_alerted_at"),)
        return out

    cut = cut_session(row.get("entry_date"))
    out["cut_session"] = cut.isoformat() if cut else None
    if cut is None:
        out["verdict"] = UNDETERMINED
        out["reason"] = "cut session not computable from entry_date %r" % (row.get("entry_date"),)
        return out

    expiry = _as_date(row.get("expiry"))
    if expiry is not None and cut >= expiry:
        out["verdict"] = EXPIRY_STOPPED
        out["reason"] = ("the 3rd session (%s) falls on or after expiry (%s); expiry governs"
                         % (cut, expiry))
        return out

    # AT the close of the cut session, not during it.
    now_et = now.astimezone(ET) if now.tzinfo else now
    hh, mm = MARKET_CLOSE_ET
    reached = (now_et.date() > cut
               or (now_et.date() == cut and (now_et.hour, now_et.minute) >= (hh, mm)))
    if not reached:
        out["reason"] = "cut is the close of %s; not reached" % cut
        return out

    total, undet = total_pnl(row.get("realized_pnl"), row.get("unrealized_pnl"))
    if total is None:
        out["verdict"] = UNDETERMINED
        out["reason"] = undet or "total not computable"
        return out

    out["total_pnl"] = str(total)
    if total > 0:
        out["verdict"] = PASS
        out["reason"] = "total %s is above zero at the cut" % total
    else:
        out["verdict"] = FIRE
        out["reason"] = ("total %s is not above zero at the close of the 3rd session (%s) — "
                         "flat fires" % (total, cut))
    return out


def is_in_scope(row: Dict[str, Any]) -> bool:
    """B2 only, and open only.

    OPEN is decided by `open_quantity > 0` and never by status or a tag (R-IV.844(d)3): a
    partial exit leaves a row OPEN with real size, and a status string has been the wrong
    question before. The bucket match is case-insensitive -- stored casing is not guaranteed,
    which `Whale_Hunter` taught (R-IV.849(d)).
    """
    if (row.get("bucket") or "").strip().upper() != BUCKET:
        return False
    try:
        return Decimal(str(row.get("open_quantity") or 0)) > 0
    except Exception:                                               # noqa: BLE001
        return False
