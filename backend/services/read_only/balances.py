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
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning("balances read failed: %s", exc)
        return None
