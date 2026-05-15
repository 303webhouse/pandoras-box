"""Read-only positions accessor.

Direct SELECT from unified_positions. We do NOT import api.unified_positions
or api.portfolio because both contain write endpoints (close_position,
update_balance, etc.). The route handler list_positions also has a write
side-effect (auto-expiring stale positions) which we explicitly skip here.
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


async def list_positions(
    status: str = "OPEN",
    ticker: Optional[str] = None,
    account: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Return matching rows from unified_positions, or None on failure.

    No mutations. status filter accepts OPEN / CLOSED / EXPIRED / ALL.
    """
    try:
        pool = await get_postgres_client()
        conditions: List[str] = []
        params: List[Any] = []
        idx = 1

        if status.upper() != "ALL":
            conditions.append(f"status = ${idx}")
            params.append(status.upper())
            idx += 1

        if ticker:
            conditions.append(f"ticker = ${idx}")
            params.append(ticker.upper())
            idx += 1

        if account:
            account_upper = account.upper()
            if account_upper == "FIDELITY_ROTH":
                conditions.append("account = 'FIDELITY_ROTH'")
            elif account_upper == "BROKERAGE_LINK_401K":
                conditions.append("account = 'BROKERAGE_LINK_401K'")
            elif account_upper == "BREAKOUT_PROP":
                conditions.append("account = 'BREAKOUT_PROP'")
            elif account_upper == "ROBINHOOD":
                conditions.append("account = 'ROBINHOOD'")
            else:
                conditions.append(f"account = ${idx}")
                params.append(account_upper)
                idx += 1

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT * FROM unified_positions {where}
                    ORDER BY
                        CASE WHEN status = 'OPEN' THEN 0 ELSE 1 END,
                        COALESCE(expiry, '2099-12-31'::date) ASC,
                        created_at DESC""",
                *params,
            )
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning("positions read failed: %s", exc)
        return None
