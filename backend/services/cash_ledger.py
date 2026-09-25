"""Money integrity — cash is a ledger of events, and a balance is what they add to.

R-IV.493(f) / R-IV.497(c): an audited cash path, the balance DERIVED AT READ TIME,
and the trade-entry path fixed first.

WHAT IS WRONG TODAY. `account_balances.cash` is a stored running total, mutated in
place by at least six writers — `auto` from trade entry, `dashboard`, `cash_reconcile`,
the cash-flow logger, the adjustment endpoint, and the startup seed. Each does
`cash = cash + delta`. A running total maintained by many hands can only be as
correct as the least careful of them, and nothing records how it reached the number
it holds. That is not a balance; it is the sum of everything nobody noticed.

Worse, the largest mover of cash — entering and closing a trade — wrote NO event at
all. `_adjust_account_cash_with_conn` moved money with a log line. So the ledger
could never have reconstructed the balance even in principle, because most of the
movements were never written down.

WHAT THIS MODULE DOES.

  * `cash_flows` becomes THE ledger. Not a rival table: a second ledger is the
    two-authors failure this codebase keeps paying for.
  * Every movement is an EVENT with a type, a signed amount, a date, a source and a
    dedup key. Trade debits and credits included — that is the fix ordered first.
  * A balance is derived: an ANCHOR the principal's own statement supports, plus the
    events after it. Never a figure carried forward by addition.
  * The derived figure is reconciled against the stored one and the difference is
    STATED. Not silently preferred, not silently ignored: two numbers that disagree
    about money are a finding, and the finding is the product.

EXTERNAL FLOW IS NOT PERFORMANCE. R-IV.539(d) names the Roth's events — transfers in
of 88.15 (08-31), 60.93 (09-04) and 88.15 (09-14), and a 0.64 dividend — and says to
take them as events, not as trades. That distinction is load-bearing: money walking
in the door is not a gain, and an account value that grew by a deposit has not
performed. `EXTERNAL_TYPES` is what keeps them out of any return.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

from services.position_economics import money

# ── the event vocabulary ─────────────────────────────────────────────────────

ANCHOR = "OPENING_BALANCE"        # an audited starting point, from a statement

TRANSFER_IN = "TRANSFER_IN"
TRANSFER_OUT = "TRANSFER_OUT"
DIVIDEND = "DIVIDEND"
INTEREST = "INTEREST"
FEE = "FEE"
TRADE_DEBIT = "TRADE_DEBIT"       # cash leaving to open, or to close a short
TRADE_CREDIT = "TRADE_CREDIT"     # cash arriving from a sale
ADJUSTMENT = "ADJUSTMENT"         # a correction, and it cites what authorised it

# Money that walked in or out of the account rather than being earned or lost in it.
# A return computed over a period must EXCLUDE these or it credits the principal's
# own deposit as performance.
EXTERNAL_TYPES = frozenset({TRANSFER_IN, TRANSFER_OUT})

# Money earned by holding, not by trading. Not external — it is real return — but it
# is not a trade result either, so it is typed apart rather than folded into one.
INCOME_TYPES = frozenset({DIVIDEND, INTEREST})

TRADE_TYPES = frozenset({TRADE_DEBIT, TRADE_CREDIT})

# A real movement of cash the principal could not classify (R-IV.546(a)1's "other").
# It counts toward the balance and belongs to NONE of the three buckets above -- not
# external, not income, not a trade. That is the point: we do not know what it is, so
# nothing claims to. Filing it under TRANSFER would wrongly exclude it from every
# return; filing it under ADJUSTMENT would call it a correction of an error. It is
# neither, and it stays visible as its own line until someone says what it was.
OTHER = "OTHER"

ALL_TYPES = (frozenset({ANCHOR, OTHER}) | EXTERNAL_TYPES | INCOME_TYPES | TRADE_TYPES
             | {FEE, ADJUSTMENT})

# The legacy vocabulary `cash_flows` already holds, mapped onto the above so one
# reader covers the whole history instead of two readers disagreeing about it.
_LEGACY = {
    "DEPOSIT": TRANSFER_IN,
    "WITHDRAWAL": TRANSFER_OUT,
    "DIV": DIVIDEND,
    "INT": INTEREST,
}

# Types that name a MECHANISM rather than a direction. `ACH` is 22 of the 31 rows in
# this table, all positive on the Roth and all but one negative on Robinhood -- the
# same word for money arriving and money leaving. The sign decides, and with no
# amount to read the answer is "unknown", never a guess: a withdrawal mistaken for a
# deposit is wrong by twice itself.
_LEGACY_SIGNED = {"ACH", "TRANSFER", "JOURNAL", "WIRE", "EFT"}


def normalise_type(flow_type: Optional[str], amount: Any = None) -> Optional[str]:
    """A ledger type, or None when the row names something this does not know.

    None is deliberate and is NOT silently treated as a transfer: an unrecognised
    type in a money ledger is a finding, and `balance_from_events` counts it.
    """
    t = (flow_type or "").strip().upper()
    if t in ALL_TYPES:
        return t
    if t in _LEGACY:
        return _LEGACY[t]
    if t in _LEGACY_SIGNED:
        if amount is None:
            return None
        try:
            v = Decimal(str(amount))
        except Exception:
            return None
        return TRANSFER_OUT if v < 0 else TRANSFER_IN
    return None


def is_external(event: Dict[str, Any]) -> bool:
    return normalise_type(event.get("flow_type"), event.get("amount")) in EXTERNAL_TYPES


# ── idempotency ──────────────────────────────────────────────────────────────

def dedup_key(account: str, event_type: str, amount: Any, event_date: Any,
              source_ref: Optional[str] = None, occurrence: int = 0) -> str:
    """A stable key for one movement, so re-importing a file cannot double-count it.

    `source_ref` is what makes two genuinely different movements distinct when they
    look alike — a broker reference, or the position they belong to. `occurrence` is
    the last resort for the case the import path already met: two real same-day,
    same-amount events with nothing to tell them apart (Phase-1 D4).
    """
    d = event_date.isoformat() if hasattr(event_date, "isoformat") else str(event_date)
    # NORMALISED TO A FIXED SCALE, because the same movement arrives typed two ways.
    # A form sends the float -16.0; the same row read back from NUMERIC(10,2) is
    # Decimal('-16.00'); a CSV sends the string "-16.00". Formatting each as written
    # gave three different keys for one movement, so a re-imported file would not
    # have deduped against what was already there -- the exact failure the key
    # exists to prevent. Four places is past the two the column stores and short of
    # any float noise.
    try:
        amt = format(Decimal(str(amount or 0)).quantize(Decimal("0.0001")), "f")
    except Exception:
        amt = format(Decimal(0), "f")
    raw = "|".join([str(account or ""), str(event_type or ""), amt, d,
                    str(source_ref or ""), str(occurrence or 0)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ── the derived balance ──────────────────────────────────────────────────────

# ── R-IV.566(d): WHAT KIND OF ANCHOR IT IS ─────────────────────────────────────
#
# Two routes write one. `/cash-reanchor` is the principal typing what his broker
# shows him right now; `/cash-anchor` is a figure read out of a statement file. The
# card needs to say "set from your broker figure - 4:16 PM" or "from your statement -
# 24 Sep", and it cannot tell them apart from the amount.
#
# Derived from `imported_from`, which is what each route stamps, rather than parsed
# out of the description -- a sentence is not a field, and reading one back is how a
# reworded log line becomes a wrong label.
ANCHOR_KIND_BROKER = "broker_figure"
ANCHOR_KIND_STATEMENT = "statement"

_ANCHOR_KIND_BY_SOURCE = {
    "PRINCIPAL_ANCHOR": ANCHOR_KIND_BROKER,
    "ANCHOR": ANCHOR_KIND_STATEMENT,
}


def anchor_kind(imported_from: Optional[str]) -> Optional[str]:
    """`broker_figure`, `statement`, or None when the row does not say.

    None is deliberate: an anchor whose origin is unrecorded must not be labelled as
    either, because the card would then state something nobody wrote down.
    """
    return _ANCHOR_KIND_BY_SOURCE.get((imported_from or "").strip().upper())


def _anchor_block(anchor: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """{kind, as_of, evidence_ref} for the anchor in force, or None."""
    if anchor is None:
        return None
    meta = anchor.get("meta")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:  # noqa: BLE001
            meta = None
    meta = meta or {}
    d = anchor.get("_d")
    return {
        "kind": anchor_kind(anchor.get("imported_from")),
        # The INSTANT where one was recorded; the date otherwise, because the anchor
        # rows written before `meta` existed have only that. Never invented.
        "as_of": meta.get("as_of") or (d.isoformat() if d else None),
        "as_of_is_instant": bool(meta.get("as_of")),
        "evidence_ref": anchor.get("source_ref"),
        "cash_flow_id": anchor.get("id"),
    }


def _recorded_before(event: Dict[str, Any], anchor: Optional[Dict[str, Any]]) -> bool:
    """Was this row written before the anchor row was? R-IV.559(b)3.

    `id` is a serial assigned at insert, so it IS the recording order, and it answers
    the question for every row in the table including those written before any
    timestamp column existed. `created_at` is preferred when both rows carry one,
    because a backfill can insert an old movement with a new id.

    Unknown reads as NOT before: an event that cannot be placed is counted and
    flagged, because dropping a real movement is worse than double-counting one that
    the next re-anchor will correct anyway.
    """
    if anchor is None:
        return False
    ea, aa = event.get("created_at"), anchor.get("created_at")
    if ea is not None and aa is not None:
        try:
            return ea < aa
        except TypeError:
            pass
    ei, ai = event.get("id"), anchor.get("id")
    if isinstance(ei, int) and isinstance(ai, int):
        return ei < ai
    return False


def balance_from_events(events: Sequence[Dict[str, Any]],
                        as_of: Optional[date] = None) -> Dict[str, Any]:
    """The balance those events add to, plus everything needed to audit it.

    The ANCHOR is not added to the running sum — it IS the starting point, and only
    the LATEST anchor at or before `as_of` counts. An account re-anchored from a
    fresh statement starts again from that statement rather than from the first one
    plus everything since, which would double every event between them.

    Returns `balance: None` when there is no anchor. A ledger with no audited
    starting point cannot state a balance, and inventing zero as the opening figure
    is exactly the kind of quiet assumption money integrity exists to remove.
    """
    cutoff = as_of
    rows: List[Dict[str, Any]] = []
    for e in events:
        d = e.get("activity_date") or e.get("event_date")
        d = d.date() if isinstance(d, datetime) else d
        if d is None:
            rows.append(dict(e, _d=None,
                             _t=normalise_type(e.get("flow_type"), e.get("amount"))))
            continue
        if cutoff is not None and d > cutoff:
            continue
        rows.append(dict(e, _d=d,
                         _t=normalise_type(e.get("flow_type"), e.get("amount"))))

    def order(r):
        return (r["_d"] is None, r["_d"] or date.min, r.get("id") or 0)

    rows.sort(key=order)

    anchor = None
    for r in rows:
        if r["_t"] == ANCHOR:
            anchor = r

    total = Decimal("0")
    counted = 0
    by_type: Dict[str, Decimal] = {}
    external = Decimal("0")
    unknown: List[Any] = []
    undated: List[Any] = []
    same_day: List[Any] = []
    anchor_day = anchor["_d"] if anchor is not None else None

    for r in rows:
        # AN ANCHOR IS NEVER A MOVEMENT. Not the chosen one, and not a superseded
        # one either -- an opening balance is a statement of position, never cash
        # crossing a boundary.
        #
        # This was the Robinhood double count. The principal re-anchored twice, two
        # minutes apart (ids 96 and 97, both 491.49 on 2026-09-24, distinct
        # idempotency keys so both landed). The reader took 97 as the opening and
        # then walked 96 as an ordinary same-day event: 491.49 + 491.49 - 16.00 =
        # 966.98, which is exactly what was served. The right answer is 475.49.
        #
        # Skipping only `r is anchor` was the bug: it assumed one anchor per account,
        # and the route that writes them is deliberately idempotent-per-key rather
        # than one-per-account, because re-anchoring is the normal workflow.
        if r["_t"] == ANCHOR:
            continue
        if r["_d"] is None:
            # A movement with no date cannot be placed before or after the anchor.
            # It is reported, never quietly summed in.
            undated.append(r.get("id"))
            continue
        if anchor_day is None:
            # No opening point, so nothing is "since" one. The totals below all say
            # `since_opening`, and populating them without an opening would make
            # every one of those names a lie. What is IN the ledger regardless of an
            # anchor is `performance_inputs`' question, and it answers it separately.
            continue
        if anchor_day is not None:
            if r["_d"] < anchor_day:
                # Pre-anchor. Written for the record, ignored by the reader
                # (R-IV.542(b)) -- the statement already contains it.
                continue
            if r["_d"] == anchor_day:
                # R-IV.559(b)3: ON THE ANCHOR'S DATE, RECORDING ORDER DECIDES.
                #
                # The anchor is an instant and an event carries only a date, so the
                # date alone cannot order them. What can is WHEN THE ROW WAS
                # RECORDED: the principal reads his broker figure and types it, so
                # everything already in the ledger at that moment is inside the
                # figure, and everything entered afterwards is not.
                #
                # This was the remaining Robinhood gap. His anchor went in at 20:16Z,
                # after the close, so the day's trades were already inside his 491.49
                # -- but they had been recorded BEFORE it, and counting every
                # same-day event added them a second time: 491.49 + 74.00 = 565.49
                # against a broker figure of 491.49.
                #
                # `id` is the recording order. It is a serial assigned at insert, so
                # it answers exactly the question the rule asks -- which row was
                # written first -- and it answers it for rows written before any
                # timestamp column existed. An earlier form of this reader ordered
                # same-day rows by id to decide which anchor won, and that was wrong
                # for a different reason: WHICH anchor is a question about dates, not
                # about who typed faster. This is the other question.
                if _recorded_before(r, anchor):
                    continue
                same_day.append(r.get("id"))
        t = r["_t"]
        if t is None:
            unknown.append({"id": r.get("id"), "flow_type": r.get("flow_type")})
            continue
        amt = Decimal(str(r.get("amount") or 0))
        total += amt
        counted += 1
        by_type[t] = by_type.get(t, Decimal("0")) + amt
        if t in EXTERNAL_TYPES:
            external += amt

    opening = Decimal(str(anchor.get("amount") or 0)) if anchor is not None else None
    balance = None if opening is None else opening + total

    return {
        "balance": money(balance),
        "opening_balance": money(opening),
        "opening_date": (anchor["_d"].isoformat()
                         if anchor is not None and anchor["_d"] else None),
        "movement_since_opening": money(total),
        "external_flow_since_opening": money(external),
        "events_counted": counted,
        "by_type": {k: money(v) for k, v in sorted(by_type.items())},
        "unknown_types": unknown,
        "undated_events": undated,
        "same_day_as_anchor": same_day,
        "as_of": as_of.isoformat() if as_of else None,
        "anchor": _anchor_block(anchor),
        "derivable": balance is not None,
        "reason": None if balance is not None else
                  "no OPENING_BALANCE event — this ledger has no audited starting point",
    }


async def stored_cash_is_retired(conn, account_name: str) -> bool:
    """True once this account has an anchor. R-IV.551(b).

    An anchor is the moment the derived figure becomes answerable, so it is also the
    moment the stored running total stops being the answer. After it the column is
    READ-ONLY HISTORY: no writer touches it, and every reader is served the derived
    figure instead.

    Why an anchor and not a hard-coded account name: R-IV.551(b)2 says Robinhood
    follows "the moment its first anchor lands", and a list of account names would
    have to be edited on the day that happens. The condition IS the anchor.

    Fail-closed toward the old behaviour: if the ledger cannot be read, the stored
    total keeps being maintained. A write that silently stops is worse than one that
    continues, because the figure then drifts with nothing recording that it did.
    """
    try:
        found = await conn.fetchval(
            """SELECT 1 FROM cash_flows
                WHERE account_name = $1 AND flow_type = $2 LIMIT 1""",
            account_name, ANCHOR)
        return bool(found)
    except Exception:
        return False


def reconcile(derived: Dict[str, Any], stored_cash: Any) -> Dict[str, Any]:
    """Derived against stored, with the difference STATED.

    Neither figure is quietly preferred. The stored one is a running total nobody
    can reconstruct; the derived one is only as complete as the events written down.
    When they disagree the honest output is both numbers and the gap between them,
    which is what tells whoever reads it how much of the history is missing.
    """
    s = None if stored_cash is None else Decimal(str(stored_cash))
    d = None if derived.get("balance") is None else Decimal(str(derived["balance"]))
    if s is None or d is None:
        return {
            "derived": money(d), "stored": money(s), "difference": None,
            "agrees": None,
            "reason": ("the ledger cannot state a balance" if d is None
                       else "there is no stored cash figure to compare against"),
        }
    diff = d - s
    return {
        "derived": money(d), "stored": money(s), "difference": money(diff),
        "agrees": diff == 0,
        "reason": None if diff == 0 else
                  "the ledger and the stored total disagree; the difference is "
                  "movement that was never written down as an event",
    }


# ── what the events say about performance ────────────────────────────────────

def performance_inputs(events: Sequence[Dict[str, Any]],
                       start: Optional[date] = None,
                       end: Optional[date] = None) -> Dict[str, Any]:
    """External flow in a period, kept OUT of any return (R-IV.539(d)).

    A deposit is not a gain. An account that ended the month $88.15 larger because
    the principal moved $88.15 into it has returned nothing, and a figure that says
    otherwise is worse than no figure.
    """
    ext = Decimal("0")
    income = Decimal("0")
    trade = Decimal("0")
    for e in events:
        d = e.get("activity_date") or e.get("event_date")
        d = d.date() if isinstance(d, datetime) else d
        if d is None:
            continue
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue
        amt = Decimal(str(e.get("amount") or 0))
        t = normalise_type(e.get("flow_type"), amt)
        if t in EXTERNAL_TYPES:
            ext += amt
        elif t in INCOME_TYPES:
            income += amt
        elif t in TRADE_TYPES:
            trade += amt
    return {
        "external_flow": money(ext),
        "income": money(income),
        "trade_flow": money(trade),
        "note": "external flow is excluded from any return: money moved in is not "
                "money earned (R-IV.539(d))",
    }
