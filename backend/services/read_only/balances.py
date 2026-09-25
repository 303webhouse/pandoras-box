"""Read-only account balance accessor.

Direct SELECT from account_balances. We do NOT import api.portfolio
because that module contains write endpoints (update_balance, etc.).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> Dict[str, Any]:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, datetime):
            # RV1 (R-IV.566(e)1): through the one helper, so a naive value carries
            # its UTC offset. A bare isoformat() emits none, and the page reads an
            # offset-less string as LOCAL -- six hours late in Mountain Time.
            from database.postgres_client import iso_utc

            d[k] = iso_utc(v)
        elif isinstance(v, date):
            d[k] = v.isoformat()
    return d


async def get_account_balances(
    account: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Return account balance rows or None on failure."""
    try:
        pool = await get_postgres_client()
        if account:
            rows = await pool.fetch(
                """SELECT account_name, broker, balance, cash, buying_power,
                          margin_total, updated_at, updated_by
                   FROM account_balances
                   WHERE account_name = $1""",
                account.upper(),
            )
        else:
            rows = await pool.fetch(
                """SELECT account_name, broker, balance, cash, buying_power,
                          margin_total, updated_at, updated_by
                   FROM account_balances
                   ORDER BY CASE broker WHEN 'robinhood' THEN 0 ELSE 1 END,
                            account_name"""
            )
        out = [_row_to_dict(r) for r in rows]
        await _attach_derived_cash(pool, out)
        return out
    except Exception as exc:
        logger.warning("balances read failed: %s", exc)
        return None


async def _attach_derived_cash(pool, rows: List[Dict[str, Any]]) -> None:
    """R-IV.551(b)1: serve the DERIVED cash where the stored figure was served.

    In the read layer, so the MCP tool and every other reader of this accessor get
    the same answer as the REST route. A second place deciding which cash figure to
    show is how two surfaces come to disagree about the same account.

    `cash` carries the derived figure once an account is ANCHORED; the stored number
    moves to `cash_stored` as history. An unanchored account is left exactly as it
    was, because the alternative there is no figure at all.

    Never raises: a ledger read that fails leaves the stored figure in place and says
    so on the row, rather than blanking a balances screen.
    """
    from services.cash_ledger import balance_from_events, reconcile
    from services.position_economics import account_value

    for d in rows:
        d["cash_stored"] = d.get("cash")
        d["cash_source"] = "stored"
        d["balance_stored"] = d.get("balance")

    # ONE ROUND TRIP FOR EVERY ACCOUNT, not one per account (R-IV.559(c)1).
    #
    # This loop used to acquire a pool connection inside it, so an unfiltered call
    # made N+1 acquisitions while the mark job and the strip job were holding the
    # same small pool. That is the shape of the intermittent failure SPINE measured:
    # unfiltered errored twice and filtered answered, then the other way round
    # earlier the same day -- which is contention, not a bug in either path. Two
    # queries now, whatever the account count, and the committee calls it unfiltered.
    names = [d.get("account_name") for d in rows if d.get("account_name")]
    events_by: Dict[str, List[Dict[str, Any]]] = {}
    positions: List[Dict[str, Any]] = []
    ledger_error = None
    try:
        async with pool.acquire() as conn:
            evs = await conn.fetch(
                """SELECT id, account_name, flow_type, amount, activity_date,
                          imported_from, source_ref, meta
                     FROM cash_flows WHERE account_name = ANY($1::text[])
                    ORDER BY account_name, activity_date, id""", names)
        for e in evs:
            events_by.setdefault(e["account_name"], []).append(dict(e))
    except Exception as exc:  # noqa: BLE001
        ledger_error = type(exc).__name__

    try:
        from services.read_only.positions import list_positions

        positions = await list_positions(status="OPEN") or []
    except Exception as exc:  # noqa: BLE001
        positions = []
        logger.warning("balances: open positions unavailable (%s)", type(exc).__name__)

    for d in rows:
        name = d.get("account_name")
        if ledger_error:
            d["cash_derivable"] = None
            d["cash_derived_reason"] = ("the ledger could not be read this cycle (%s)"
                                        % ledger_error)
            d["balance"] = None
            d["balance_reason"] = "the cash ledger could not be read this cycle"
        else:
            derived = balance_from_events(events_by.get(name) or [])
            rec = reconcile(derived, d.get("cash_stored"))
            d["cash_derived"] = derived["balance"]
            d["cash_derivable"] = derived["derivable"]
            d["cash_derived_reason"] = derived["reason"]
            # R-IV.566(d): the source line ABACUS's card needs.
            d["cash_anchor"] = derived.get("anchor")
            # R-IV.567(c): NAMED FOR WHAT IT COMPARES AGAINST. Served as
            # `cash_difference` a committee seat reads it as a live discrepancy in the
            # cash figure, when it is the gap against a total that has been RETIRED --
            # the Roth's stored cash is -1,229.51, which a Roth cannot hold. It is the
            # broker-CSV cleanup's target, not a fault in the number beside it.
            d["cash_vs_retired_stored"] = rec["difference"]
            if derived["derivable"]:
                d["cash"] = derived["balance"]
                d["cash_source"] = "derived"

            # R-IV.559(c)2: `balance` is derived cash plus this account's open
            # positions at their marks -- through the SAME arithmetic the loss
            # alert's threshold uses, so a committee sizing off one and an alert
            # firing off the other cannot disagree about the account.
            av = account_value(derived["balance"], positions, account=name,
                               cash_reason=derived["reason"])
            d["balance"] = av["value"]
            d["balance_source"] = "derived" if av["value"] is not None else None
            d["balance_partial"] = av["partial"]
            d["balance_reason"] = av["reason"]
            d["balance_cash"] = av["cash"]
            d["balance_positions_value"] = av["positions_value"]
            d["balance_positions_counted"] = av["positions_counted"]
            d["balance_positions_unvalued"] = av["positions_unvalued"]

        # R-IV.559(c)3: buying power is a BROKER figure. The hub cannot derive it --
        # it depends on margin rules, settlement and the broker's own haircuts --
        # so it serves null with the reason rather than a stored number that was
        # true on whatever day it was last typed in.
        d["buying_power_stored"] = d.get("buying_power")
        d["buying_power"] = None
        d["buying_power_reason"] = (
            "buying power is the broker's own figure and the hub cannot derive it: "
            "it depends on margin rules, settlement and the broker's haircuts. The "
            "last stored value is kept as `buying_power_stored` and is not served "
            "as current.")
