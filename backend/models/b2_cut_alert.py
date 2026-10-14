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
from decimal import ROUND_HALF_UP, Decimal
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
#: TA-161's 7th verdict. DISTINCT FROM UNDETERMINED ON PURPOSE: UNDETERMINED means the inputs
#: were not good enough THIS run and the row should be retried; NOT_EVALUABLE means the row
#: cannot be evaluated under this definition at all, so retrying it every day is noise.
NOT_EVALUABLE = "NOT_EVALUABLE"

VERDICTS = (NOT_YET, EXPIRY_STOPPED, UNDETERMINED, NOT_EVALUABLE, PASS, FIRE, ALREADY_FIRED)

#: S10 (R-IV.983(b)). A cut session that fell BEFORE this definition was deployed was never
#: evaluated under it, and firing on it now would alert on a three-session verdict reached by
#: arithmetic nobody reviewed. TSLQ is the case: its cut session was 2026-10-05 and the stale
#: path fired it on 2026-10-12.
S10_CUT_SESSION_PRECEDES_DEPLOY = "CUT_SESSION_PRECEDES_DEPLOY"
TA161_DEPLOYED_ON = date(2026, 10, 13)

#: The contract record, as this book actually holds it. There is NO multiplier column on
#: `unified_positions`, so `structure` is the contract record and this map is the reading of
#: it. Verified against `max_loss`, which is computed by a different writer:
#:   IBIT  put_debit_spread  0.19       x 2  x 100 = 38.00     == max_loss 38
#:   TSLQ  stock             18.968875  x 80 x   1 = 1517.51   == max_loss 1517.51
#: An unrecognised structure is NOT given a default: it returns None and the row is
#: NOT_EVALUABLE, because a guessed multiplier is wrong by 100x in one direction or the other.
STOCK_MULTIPLIER = 1
OPTION_MULTIPLIER = 100
_DEBIT_STRUCTURES = frozenset({
    "stock", "long_call", "long_put", "call_debit_spread", "put_debit_spread",
})
_CREDIT_STRUCTURES = frozenset({
    "call_credit_spread", "put_credit_spread", "short_call", "short_put",
})
_STOCK_STRUCTURES = frozenset({"stock"})

#: Beyond a cent, the two writers disagree and the verdict says so (R-IV.983(b)).
DIVERGENCE_TOLERANCE = Decimal("0.01")

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


NO_POST_CLOSE_MARK = "no post-close mark"


def post_close_mark(cut: date, mark_as_of: Any, mark_integrity: Any,
                    mark: Any = None) -> Tuple[bool, str]:
    """May the cut be evaluated on this mark? (ok, reason) — TA-152, amending TA-141 §7.

    TWO REQUIREMENTS, AND THE FIRST IS NOT "WITHIN 26 HOURS". TA's words: the mark must be
    "TIMESTAMPED AT OR AFTER THE CUT SESSION'S CLOSE. Not 'within 26 hours,' not 'flagged ok' --
    at or after the close." A mark taken at 09:17 ET on the cut day is a few hours old and
    perfectly fresh by any display bound, and it still says nothing about where the position
    closed. The 26-hour verdict is for display; this is the decision's own requirement
    (Convention #38).

    WHY THIS IS LOAD-BEARING RATHER THAN BELT-AND-BRACES: the stored mark is written by a
    different job on its own schedule, so at alert time it may predate the cut close by hours.
    The alert therefore reads its own mark at run time and gates on THAT.

    (An earlier version of this docstring said the refreshes run "at 09:17 and 16:47 ET", and
    concluded every B2 row would read UNDETERMINED every day. That was wrong: `main.py:158`
    fires at :02/:17/:32/:47 from 09:00-17:00 ET plus a forced 16:17 ET closing-bell run, so
    16:02 ET is already post-close. The schedule had been generalised from a sample of two
    timestamps. The gate is still load-bearing, but not for that reason.)

    The second requirement is TA-151's: a `wide` or `unknown` mark is not evidence. `stale` is
    not consulted, because the first requirement already subsumes it -- a mark at or after
    today's close cannot be 26 hours old.
    """
    if mark is None:
        return False, "%s: no mark was read for the cut session %s" % (NO_POST_CLOSE_MARK, cut)
    if mark_as_of is None:
        return False, "%s: the mark carries no timestamp, so it cannot be placed relative to "                       "the %s close" % (NO_POST_CLOSE_MARK, cut)
    ts = mark_as_of
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return False, "%s: mark timestamp %r is not a timestamp" % (NO_POST_CLOSE_MARK, ts)
    if not isinstance(ts, datetime):
        return False, "%s: mark timestamp %r is not a timestamp" % (NO_POST_CLOSE_MARK, ts)
    if ts.tzinfo is None:
        return False, "%s: mark timestamp %s has no timezone -- refusing to assume one" % (
            NO_POST_CLOSE_MARK, ts.isoformat())

    ts_et = ts.astimezone(ET)
    hh, mm = MARKET_CLOSE_ET
    close_et = datetime(cut.year, cut.month, cut.day, hh, mm, tzinfo=ET)
    if ts_et < close_et:
        return False, ("%s: the mark is from %s, BEFORE the %s close at %02d:%02d ET"
                       % (NO_POST_CLOSE_MARK, ts_et.isoformat(), cut, hh, mm))

    from models.mark_integrity import is_gateable
    if not is_gateable(mark_integrity):
        return False, ("mark or basis under integrity repair: the mark is flagged %r"
                       % (mark_integrity,))
    return True, "mark is from %s, at or after the %s close" % (ts_et.isoformat(), cut)


def _structure_parts(row: Dict[str, Any]) -> Tuple[str, ...]:
    """The structure, split on `+`. A composite row stores "a+b" in one column."""
    raw = (row.get("structure") or "").strip().lower()
    if not raw:
        return ()
    return tuple(p.strip() for p in raw.split("+") if p.strip())


def orientation(row: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """(+1 for a DEBIT-opened position, -1 for CREDIT, None if not stated) + the reason.

    FROM AN EXPLICIT FIELD, NEVER FROM THE SIGN OF A PRICE. R-IV.983(b) allows only
    DEBIT-opened rows to be evaluated until a `position_orientation` column exists, because
    inferring "we paid for this" from a positive entry price is exactly the sort of default
    that turns "I was not told" into a confident claim. `position_orientation` is honoured
    first so this function stops being the author the moment the column arrives.
    """
    explicit = (row.get("position_orientation") or "").strip().upper()
    if explicit in ("DEBIT", "LONG"):
        return 1, "position_orientation = %s" % explicit
    if explicit in ("CREDIT", "SHORT"):
        return -1, "position_orientation = %s" % explicit
    if explicit:
        return None, "position_orientation %r is not a known orientation" % explicit

    parts = _structure_parts(row)
    if not parts:
        return None, "no structure recorded, and no position_orientation column to fall back on"
    if all(p in _DEBIT_STRUCTURES for p in parts):
        return 1, "structure %s is debit-opened" % "+".join(parts)
    if any(p in _CREDIT_STRUCTURES for p in parts):
        return None, ("structure %s is credit-opened; R-IV.983(b) evaluates DEBIT-opened rows "
                      "only until a position_orientation column exists" % "+".join(parts))
    return None, "structure %s is not a known orientation" % "+".join(parts)


def contract_multiplier(row: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """(multiplier, reason). None when the contract record does not say -- NOT a default."""
    explicit = row.get("multiplier")
    if explicit is not None and str(explicit).strip() != "":
        try:
            m = int(Decimal(str(explicit)))
        except Exception:                                           # noqa: BLE001
            return None, "multiplier %r is unreadable" % (explicit,)
        if m <= 0:
            return None, "multiplier %r is not positive" % (explicit,)
        return m, "multiplier column = %d" % m

    parts = _structure_parts(row)
    if not parts:
        return None, "no structure and no multiplier recorded"
    if all(p in _STOCK_STRUCTURES for p in parts):
        return STOCK_MULTIPLIER, "structure %s: shares" % "+".join(parts)
    unknown = [p for p in parts if p not in _DEBIT_STRUCTURES and p not in _CREDIT_STRUCTURES]
    if unknown:
        return None, "structure %s is not in the contract map" % "+".join(unknown)
    if any(p in _STOCK_STRUCTURES for p in parts):
        return None, ("structure %s mixes shares and contracts, which have different "
                      "multipliers" % "+".join(parts))
    return OPTION_MULTIPLIER, "structure %s: option contracts" % "+".join(parts)


def _decimal(value: Any) -> Optional[Decimal]:
    """Decimal(str(x)), or None. Decimal(0.19) is 0.1900000000000000078..."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return Decimal(str(value))
    except Exception:                                               # noqa: BLE001
        return None


def cut_pnl(row: Dict[str, Any], mark: Any) -> Tuple[Optional[Decimal], Optional[str], Dict]:
    """(pnl, not_evaluable_reason, workings) -- R-IV.983(b)'s definition, and nothing else.

        cut_pnl = orientation x (mark_gated - entry_basis_per_unit) x multiplier x open_quantity

    `unrealized_pnl` IS NOT READ HERE AND MUST NOT BE. It is a different writer's figure; the
    whole point of TA-161 is that the verdict owns its own arithmetic.

    `open_quantity`, NEVER `quantity` (convention #29). `quantity` is the size the position was
    OPENED at and does not shrink on a partial exit, so a cut verdict computed from it would
    size the P&L to a position that is no longer held. A NULL `open_quantity` is UNKNOWN, not
    zero, and returns NOT_EVALUABLE rather than a flat verdict.

    The basis is GROSS OF FEES, as ruled: `entry_price` is the per-unit price paid.
    """
    w: Dict[str, Any] = {}

    parts = _structure_parts(row)
    if len(parts) > 1:
        # Composites are evaluable only on ONE NET MARK for the whole structure. A single
        # `mark` column cannot be attributed to two legs, and halving it is not a measurement.
        w["structure_parts"] = list(parts)
        if not (row.get("net_mark") or row.get("mark_is_net")):
            return None, ("composite structure %s: evaluable only on a single net mark, and "
                          "this row carries a per-leg mark" % "+".join(parts)), w

    sign, why_sign = orientation(row)
    w["orientation"] = sign
    w["orientation_basis"] = why_sign
    if sign is None:
        return None, "orientation not established: %s" % why_sign, w

    mult, why_mult = contract_multiplier(row)
    w["multiplier"] = mult
    w["multiplier_basis"] = why_mult
    if mult is None:
        return None, "multiplier not established: %s" % why_mult, w

    basis = _decimal(row.get("entry_price"))
    w["entry_basis_per_unit"] = str(basis) if basis is not None else None
    if basis is None:
        return None, "entry basis per unit is not readable from entry_price %r" % (
            row.get("entry_price"),), w

    qty = _decimal(row.get("open_quantity"))
    w["open_quantity"] = str(qty) if qty is not None else None
    if qty is None:
        return None, ("open_quantity is NULL, which is unknown size rather than a flat "
                      "position -- convention #29"), w
    if qty <= 0:
        return None, "open_quantity %s is not positive; nothing is held" % qty, w

    m = _decimal(mark)
    w["mark_gated"] = str(m) if m is not None else None
    if m is None:
        return None, "the gated mark %r is not readable" % (mark,), w

    pnl = (Decimal(sign) * (m - basis) * Decimal(mult) * qty).quantize(Decimal("0.01"),
                                                                      rounding=ROUND_HALF_UP)
    w["cut_pnl"] = str(pnl)
    return pnl, None, w


def pnl_divergence(computed: Decimal, stored: Any, mark_as_of: Any,
                   stored_as_of: Any) -> Optional[Dict[str, Any]]:
    """BOTH figures and BOTH timestamps when the two writers disagree beyond a cent.

    Recorded rather than reconciled: which is right is not this function's call, and a verdict
    that silently preferred one would hide exactly the disagreement worth seeing.
    """
    s = _decimal(stored)
    if s is None:
        return None
    if abs(computed - s) <= DIVERGENCE_TOLERANCE:
        return None
    return {"cut_pnl": str(computed),
            "cut_pnl_as_of": mark_as_of.isoformat() if hasattr(mark_as_of, "isoformat")
                             else (str(mark_as_of) if mark_as_of is not None else None),
            "unrealized_pnl": str(s),
            "unrealized_pnl_as_of": stored_as_of.isoformat()
                                    if hasattr(stored_as_of, "isoformat")
                                    else (str(stored_as_of) if stored_as_of is not None
                                          else None),
            "difference": str((computed - s).quantize(Decimal("0.01"),
                                                      rounding=ROUND_HALF_UP)),
            "note": "two writers of the same fact disagree; neither is preferred here"}


def decide(row: Dict[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The verdict for one position. Pure: no clock of its own beyond the injected `now`.

    `realized` SHOULD be supplied from the closure ledger rather than the row's own column -- a
    partial exit's realized stays on an OPEN row and the row's figure has been seen to
    under-report the book. The caller owns that sourcing; this function totals what it is given.
    """
    now = now or datetime.now(ET)
    # The mark trio is attached UP FRONT, so every path carries it -- not only the ones that
    # happen to reach the gate. A verdict a reader cannot audit against its own mark is the
    # thing TA-152 is closing, and NOT_YET and EXPIRY_STOPPED are read by people too.
    out: Dict[str, Any] = {"verdict": NOT_YET, "cut_session": None, "total_pnl": None,
                           "reason": "",
                           "mark": row.get("mark"),
                           "mark_as_of": row.get("mark_as_of"),
                           "mark_integrity": row.get("mark_integrity"),
                           # TA-161 keys, attached UP FRONT for the same reason the mark trio
                           # is: a verdict a reader cannot audit against its own arithmetic is
                           # the thing being closed, and NOT_YET is read by people too.
                           "cut_pnl": None,
                           "stop_code": None,
                           "pnl_divergence": None,
                           "workings": None}

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

    # TA-152: the mark gates the evaluation, BEFORE any P&L is totalled. A verdict computed
    # from a mark that predates the cut close is not a weaker answer -- it is an answer to a
    # different question, and it would fire or spare a position on the wrong number.
    ok, why = post_close_mark(cut, row.get("mark_as_of"), row.get("mark_integrity"),
                              row.get("mark"))
    if not ok:
        out["verdict"] = UNDETERMINED
        out["reason"] = "%s (position %s)" % (why, row.get("position_id") or "unnamed")
        out["mark"] = row.get("mark")
        out["mark_as_of"] = row.get("mark_as_of")
        out["mark_integrity"] = row.get("mark_integrity")
        return out

    # ── S10 (R-IV.983(b)): a cut that fell before this definition shipped ──────────────
    # Checked AFTER the mark gate so the payload still carries the mark and the workings: a
    # row held back by S10 is exactly the row someone will want to audit.
    if cut < TA161_DEPLOYED_ON:
        out["verdict"] = NOT_EVALUABLE
        out["stop_code"] = S10_CUT_SESSION_PRECEDES_DEPLOY
        out["reason"] = ("%s: the cut session %s precedes the TA-161 deploy (%s), so it was "
                         "never evaluated under this definition and will not be fired on now"
                         % (S10_CUT_SESSION_PRECEDES_DEPLOY, cut, TA161_DEPLOYED_ON))
        return out

    # ── TA-161: the verdict's OWN arithmetic, from the mark that passed the gate ───────
    pnl, not_evaluable, workings = cut_pnl(row, row.get("mark"))
    out["workings"] = workings
    if pnl is None:
        out["verdict"] = NOT_EVALUABLE
        out["reason"] = not_evaluable or "cut P&L not computable"
        return out

    out["cut_pnl"] = str(pnl)
    # `total_pnl` is still reported, because a reader wants the booked figure beside the
    # verdict -- but it does NOT decide anything any more.
    total, _ = total_pnl(row.get("realized_pnl"), row.get("unrealized_pnl"))
    out["total_pnl"] = str(total) if total is not None else None
    out["pnl_divergence"] = pnl_divergence(pnl, row.get("unrealized_pnl"),
                                           row.get("mark_as_of"),
                                           row.get("unrealized_pnl_as_of"))

    if pnl > 0:
        out["verdict"] = PASS
        out["reason"] = ("cut P&L %s is above zero on the gated mark %s at the close of the "
                         "3rd session (%s)" % (pnl, workings.get("mark_gated"), cut))
    else:
        out["verdict"] = FIRE
        out["reason"] = ("cut P&L %s is not above zero on the gated mark %s at the close of "
                         "the 3rd session (%s) — flat fires"
                         % (pnl, workings.get("mark_gated"), cut))
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
