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

FLAT IS NOT PROFITABLE. The bar is "cut P&L > 0 on the gated mark", so exactly zero lands on
NOT_PROFITABLE. A position that has gone nowhere in three sessions is the case the alert is for.

A NULL MARK IS **UNDETERMINED**, NEITHER NOT_PROFITABLE NOR PROFITABLE. Without a mark there is
no figure, and guessing in either direction is worse than saying so: a fabricated PROFITABLE
hides a dead position, a fabricated NOT_PROFITABLE cries wolf about one nobody can price.

THE VERDICT DESCRIBES THE POSITION; ALERTING IS AN ACTION TAKEN ON IT (R-IV.1005(b)). This
module decides, and never alerts. `already_alerted` says whether the action has been taken.

EXPIRY-STOPPED WHEN THE THIRD SESSION FALLS ON OR AFTER EXPIRY. On that path the position's own
expiry arrives first and governs; a three-day prompt about something expiring in two days is
noise. `>=` and not `>`: a cut landing exactly on expiry day is the expiry's business.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SESSIONS_TO_CUT = 3
BUCKET = "B2"

# ── Verdicts — TA-161's set, EXACTLY, and no other labels (R-IV.1005(b)) ──────────────
#
# A VERDICT DESCRIBES THE POSITION. "Fire" is the action taken on a verdict, not a verdict,
# so `ALREADY_FIRED` is gone: it made a position report its ALERT HISTORY where its P&L
# belonged, and IBIT 980 read `ALREADY_FIRED` when the true answer was NOT_PROFITABLE.
# Whether we have already alerted is `already_alerted`, a separate field.
NOT_YET = "NOT_YET"
NOT_EVALUABLE = "NOT_EVALUABLE"
UNDETERMINED = "UNDETERMINED"
EXPIRY_STOPPED = "EXPIRY_STOPPED"
#: Promoted from a `stop_code` riding on NOT_EVALUABLE to a verdict of its own: "I cannot
#: evaluate this" and "this predates the alert" are different answers and were reported as one.
CUT_SESSION_PRECEDES_DEPLOY = "CUT_SESSION_PRECEDES_DEPLOY"
NOT_PROFITABLE = "NOT_PROFITABLE"
PROFITABLE = "PROFITABLE"
#: NOT_EVALUABLE is DISTINCT FROM UNDETERMINED on purpose: UNDETERMINED means the inputs were
#: not good enough THIS run and the row should be retried; NOT_EVALUABLE means the row cannot
#: be evaluated under this definition at all, so retrying it every day is noise.
VERDICTS = (NOT_YET, NOT_EVALUABLE, UNDETERMINED, EXPIRY_STOPPED,
            CUT_SESSION_PRECEDES_DEPLOY, NOT_PROFITABLE, PROFITABLE)

#: THE ALERT'S FIRST PRODUCTION DEPLOY. Recorded ONCE here and NEVER advanced by a later
#: deploy -- that is the whole point of the field. The previous anchor was the day TA-161
#: shipped (2026-10-13), which moved with the work and so would have re-excluded another day's
#: cuts on every subsequent deploy.
#:
#: EVIDENCE: the RAILWAY DEPLOYMENT RECORD, not the commit's authored time -- R-IV.1005(c).
#: An authored time is not a deploy time; the previous value (07:32:37Z) was when 022d1c07 was
#: written, and a commit can sit unpushed for any length of time.
#:
#:   deployment  67faa057-391d-4d20-af05-dea1d23ac24b
#:   commit      022d1c078eea38d5a8f1436642e02c68c6566f23  (created the job AND wired main.py)
#:   createdAt   2026-10-12T07:35:50.673Z  =  2026-10-12T03:35:50.673-04:00
#:
#: `createdAt` is when Railway CREATED the deployment; the record carries no "became live"
#: stamp, so the process went live some minutes later. That does not move the ET DATE -- which
#: is all the comparison uses -- because 03:35 ET is nowhere near a day boundary. Corroborated
#: independently: the alert's first observed production run was TSLQ's own
#: `b2_cut_alerted_at` = 2026-10-12T20:15:00Z (16:15 ET), the same ET session.
#:
#: Kept as a UTC instant ON THE WIRE, per R-IV.1001(c)1; the comparison converts.
ALERT_FIRST_DEPLOY_UTC = datetime(2026, 10, 12, 7, 35, 50, 673000, tzinfo=timezone.utc)


def alert_first_deploy_session() -> date:
    """The anchor as an EXCHANGE SESSION DATE — America/New_York. Convention #39.

    A comparison between two fields states their common basis, and for sessions that basis is
    the exchange's clock. Taking `.date()` off the UTC instant instead would be wrong for any
    deploy between 20:00 and 24:00 ET; four of this register's five deploys on 2026-10-13
    landed inside that window, so the difference is not hypothetical.
    """
    return ALERT_FIRST_DEPLOY_UTC.astimezone(ET).date()

#: The contract record, as this book actually holds it. There is NO multiplier column on
#: `unified_positions`, so `structure` is the contract record and this map is the reading of
#: it. Verified against `max_loss`, which is computed by a different writer:
#:   IBIT  put_debit_spread  0.19       x 2  x 100 = 38.00     == max_loss 38
#:   TSLQ  stock             18.968875  x 80 x   1 = 1517.51   == max_loss 1517.51
#: An unrecognised structure is NOT given a default: it returns None and the row is
#: NOT_EVALUABLE, because a guessed multiplier is wrong by 100x in one direction or the other.
STOCK_MULTIPLIER = 1
OPTION_MULTIPLIER = 100
#: TA-168 / R-IV.1017(d): THE one named constant. Orientation may be read from `structure`
#: only by EXACT match of the WHOLE value against this set, until `position_orientation`
#: exists. Everything else -- including every composite -- is UNDETERMINED and held.
#:
#: NO `+` SPLITTING (TA-161 §1.6). An earlier version of this matched each part of a composite
#: and called the whole DEBIT when every part passed, which classified five rows that way
#: (`put_debit_spread+call_debit_spread` x4, `put_debit_spread+put_debit_spread` x1). A
#: composite's orientation is not the conjunction of its legs' orientations -- a spread
#: against a long put is a different position from either -- so the whole value is matched and
#: any `+` falls outside the set by construction.
DEBIT_WHITELIST = frozenset({
    "put_debit_spread", "call_debit_spread", "long_put", "long_call",
})

#: Recorded for the REASON STRING only -- never to decide an orientation. A row whose structure
#: is a known credit shape is held for the same reason as an unknown one, but a reader is owed
#: the difference between "this is credit-opened" and "nobody knows what this is".
_KNOWN_CREDIT_SHAPES = frozenset({
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

    FROM AN EXPLICIT FIELD, NEVER FROM THE SIGN OF A PRICE. R-IV.983(b) allowed only
    DEBIT-opened rows to be evaluated until a column existed, because inferring "we paid for
    this" from a positive entry price is exactly the sort of default that turns "I was not
    told" into a confident claim.

    THE COLUMN NOW EXISTS. Sources in order, and the order is the ruling's:

      1. `orientation_at_entry` (R-IV.1043(f)) -- the recorded value, +1 or -1;
      2. `position_orientation` -- the name this module ANTICIPATED while it had no column.
         **No migration creates it**, so it never arrives from the database; the branch is
         kept only because callers that build a row dict by hand may still set it, and
         removing it would change their behaviour silently. `orientation_at_entry` is the
         column that actually arrived. Do not add it to a SELECT: it would fail the query
         with UndefinedColumn;
      3. `DEBIT_WHITELIST` -- the FALLBACK, which R-IV.1043(f) explicitly preserved, for
         option structures whose shape states the orientation by construction.

    **A STOCK ROW IS EVALUATED ONLY WITH `orientation_at_entry` RECORDED.** Shares carry no
    debit/credit shape -- long and short stock are the same structure string -- so for stock
    there is nothing for the fallback to read and it is not consulted.
    """
    # R-IV.1043(f): `orientation_at_entry` IS THE COLUMN, and it is read FIRST. It arrived in
    # the R-IV.1043(e) migration as a nullable SMALLINT holding +1 or -1, which is why it is
    # read as a number rather than by name: a row either recorded the orientation at entry or
    # it did not, and nothing here reconstructs it.
    recorded = row.get("orientation_at_entry")
    if recorded is not None and str(recorded).strip() != "":
        try:
            dec = Decimal(str(recorded).strip())
        except Exception:                                           # noqa: BLE001
            return None, "orientation_at_entry %r is unreadable" % (recorded,)
        # NOT int(Decimal(...)). That TRUNCATES, so "1.5" came back as +1 -- a value the
        # column does not admit, read as a confident orientation. The column is a SMALLINT so
        # Postgres will never hand us a fraction, but a hand-built row or a JSON round trip
        # can, and truncating is how an unreadable value becomes an answer.
        if dec != dec.to_integral_value():
            return None, ("orientation_at_entry %r is not a whole number; it admits only "
                          "+1 or -1" % (recorded,))
        sign = int(dec)
        if sign == 1:
            return 1, "orientation_at_entry = +1 (recorded at entry)"
        if sign == -1:
            return -1, "orientation_at_entry = -1 (recorded at entry)"
        return None, ("orientation_at_entry %r is neither +1 nor -1; the column admits no "
                      "other value" % (recorded,))

    explicit = (row.get("position_orientation") or "").strip().upper()
    if explicit in ("DEBIT", "LONG"):
        return 1, "position_orientation = %s" % explicit
    if explicit in ("CREDIT", "SHORT"):
        return -1, "position_orientation = %s" % explicit
    if explicit:
        return None, "position_orientation %r is not a known orientation" % explicit

    # THE WHOLE VALUE, normalised for case and surrounding space and nothing else. No `+`
    # split: a composite is held by TA-161 §1.6, and matching the whole string is how that
    # happens by construction rather than by a separate rule someone can forget.
    whole = (row.get("structure") or "").strip().lower()
    if not whole:
        return None, ("no structure recorded, and neither orientation_at_entry nor "
                      "position_orientation is set")

    # R-IV.1043(f), the second half: **A STOCK ROW IS EVALUATED ONLY WITH
    # `orientation_at_entry` RECORDED.** Checked BEFORE the whitelist, not after, so the rule
    # holds even if a share shape is ever added to DEBIT_WHITELIST by someone who did not read
    # this ruling. Shares have no debit/credit shape to read an orientation out of -- long and
    # short stock are the same structure string -- so for stock the column is not a preference
    # over the fallback, it is the only admissible source.
    if whole in _STOCK_STRUCTURES or all(p in _STOCK_STRUCTURES
                                         for p in whole.split("+") if p):
        return None, ("structure %r is SHARES, and a stock row is evaluated only with "
                      "orientation_at_entry recorded (R-IV.1043(f)); it is not recorded, so "
                      "orientation is UNDETERMINED and the row is held" % whole)

    if whole in DEBIT_WHITELIST:
        return 1, "structure %r is on DEBIT_WHITELIST (exact match, whole value)" % whole
    if "+" in whole:
        return None, ("structure %r is a COMPOSITE, held by TA-161 §1.6 whatever its legs are; "
                      "orientation is UNDETERMINED" % whole)
    if whole in _KNOWN_CREDIT_SHAPES:
        return None, ("structure %r is credit-opened and so is not on DEBIT_WHITELIST; held "
                      "until position_orientation exists" % whole)
    return None, ("structure %r is not on DEBIT_WHITELIST %s; orientation is UNDETERMINED and "
                  "the row is held (TA-168)" % (whole, sorted(DEBIT_WHITELIST)))


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
    # The multiplier map is SEPARATE from the orientation whitelist: `long_put` is a contract
    # whose multiplier is perfectly knowable even though its orientation is now held. Collapsing
    # the two would have made "I cannot say which way this points" mean "I cannot price it".
    _PRICEABLE = (DEBIT_WHITELIST | _KNOWN_CREDIT_SHAPES | _STOCK_STRUCTURES)
    unknown = [p for p in parts if p not in _PRICEABLE]
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
                           "pnl_divergence": None,
                           "workings": None,
                           # R-IV.1005(b): alert HISTORY, not a verdict. The verdict describes
                           # the position; this says whether we have already acted on it, and
                           # the JOB decides what to do with the pair. Previously an alerted
                           # row returned ALREADY_FIRED *instead of* its P&L verdict, so IBIT
                           # 980 reported its history where NOT_PROFITABLE belonged.
                           "already_alerted": bool(row.get("b2_cut_alerted_at")),
                           "b2_cut_alerted_at": row.get("b2_cut_alerted_at")}

    cut = cut_session(row.get("entry_date"))
    out["cut_session"] = cut.isoformat() if cut else None
    if cut is None:
        # NOT_EVALUABLE, not UNDETERMINED: a cut session that cannot be computed from the
        # entry date will not become computable tomorrow, so retrying it daily is noise.
        out["verdict"] = NOT_EVALUABLE
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
    anchor = alert_first_deploy_session()
    if cut < anchor:
        out["verdict"] = CUT_SESSION_PRECEDES_DEPLOY
        out["reason"] = ("%s: the cut session %s precedes the alert's first production deploy "
                         "(%s America/New_York), so it was never evaluated by this alert and "
                         "will not be fired on now — both dates are exchange sessions in "
                         "America/New_York (convention #39)"
                         % (CUT_SESSION_PRECEDES_DEPLOY, cut, anchor))
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
        out["verdict"] = PROFITABLE
        out["reason"] = ("cut P&L %s is above zero on the gated mark %s at the close of the "
                         "3rd session (%s)" % (pnl, workings.get("mark_gated"), cut))
    else:
        # FLAT IS NOT PROFITABLE. The bar is "> 0", so exactly zero lands here -- a position
        # that has gone nowhere in three sessions is the case the alert exists for.
        out["verdict"] = NOT_PROFITABLE
        out["reason"] = ("cut P&L %s is not above zero on the gated mark %s at the close of "
                         "the 3rd session (%s) — flat is not profitable"
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
