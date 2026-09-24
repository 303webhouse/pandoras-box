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
        elif isinstance(v, (datetime, date)):
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

    for d in rows:
        name = d.get("account_name")
        d["cash_stored"] = d.get("cash")
        d["cash_source"] = "stored"
        try:
            async with pool.acquire() as conn:
                events = await conn.fetch(
                    """SELECT id, flow_type, amount, activity_date
                         FROM cash_flows WHERE account_name = $1
                        ORDER BY activity_date, id""", name)
            derived = balance_from_events([dict(e) for e in events])
            rec = reconcile(derived, d.get("cash_stored"))
            d["cash_derived"] = derived["balance"]
            d["cash_derivable"] = derived["derivable"]
            d["cash_derived_reason"] = derived["reason"]
            d["cash_difference"] = rec["difference"]
            if derived["derivable"]:
                d["cash"] = derived["balance"]
                d["cash_source"] = "derived"
        except Exception as exc:  # noqa: BLE001
            d["cash_derivable"] = None
            d["cash_derived_reason"] = ("the ledger could not be read this cycle (%s)"
                                        % type(exc).__name__)
