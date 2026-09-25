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
        elif isinstance(v, datetime):
            # RV1 (R-IV.566(e)1): through the one helper, so a naive value carries
            # its UTC offset. A bare isoformat() emits none, and the page reads an
            # offset-less string as LOCAL -- six hours late in Mountain Time.
            from database.postgres_client import iso_utc

            d[k] = iso_utc(v)
        elif isinstance(v, date):
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
        out = [_row_to_dict(r) for r in rows]
        # Gap 1 (R-IV.526(b)): the money comes back derived from the lots, in the
        # same read, so no caller can serve the stored scope by forgetting to ask.
        async with pool.acquire() as conn:
            lots = await fetch_lots_by_position(
                conn, [r.get("position_id") for r in rows])
        attach_economics(out, lots)
        return out
    except Exception as exc:
        logger.warning("positions read failed: %s", exc)
        return None


def attach_economics(positions: List[Dict[str, Any]],
                     lots_by_position: Dict[str, List[Dict[str, Any]]]) -> None:
    """Replace each row's derived money with the figure its lots support. In place.

    `max_loss` and `unrealized_pnl` become the LOT-DERIVED figures; the values the
    table holds move to `max_loss_stored` and `unrealized_pnl_stored` so the
    divergence stays auditable rather than being overwritten in flight. Where a row
    has no lots both read `None` and `basis_reason` says why — nothing stands in.

    The mark is the row's own `current_price`, and `mark_status` / `mark_checked_at`
    ride along in the derived block. Staleness is NOT re-litigated here: the mark
    job already decides what to keep and labels it, and gap 1 is about scope.
    """
    from services.position_economics import close_date_from_lots, economics

    for p in positions:
        lots = lots_by_position.get(p.get("position_id")) or []
        e = economics(p, lots, p.get("current_price"))
        e["mark_status"] = p.get("mark_status")
        e["mark_checked_at"] = p.get("mark_checked_at")
        p["max_loss_stored"] = p.get("max_loss")
        p["unrealized_pnl_stored"] = p.get("unrealized_pnl")
        p["max_loss"] = e["max_loss"]
        p["unrealized_pnl"] = e["unrealized_pnl"]
        p["open_remainder"] = e["open_remainder"]
        # R-IV.517(e): a closure's close date is its disposal lot's fill_time,
        # never `created_at`. Derived on read; no new column.
        if (p.get("status") or "").upper() in ("CLOSED", "EXPIRED"):
            d, lot_id, why = close_date_from_lots(lots)
            e["close_date"] = d.isoformat() if d else None
            e["close_date_lot_id"] = lot_id
            e["close_date_reason"] = why
        p["derived"] = e


async def fetch_lots_by_position(conn, position_ids) -> Dict[str, List[Dict[str, Any]]]:
    """{position_id: [lot, ...]} for the ids given. One author for this fetch.

    Gap 1 needs the lots wherever a money figure is served, and two copies of the
    query would be two chances for one of them to forget a column the economics
    depends on — `fill_time` decides FIFO order and the close date, `qty` the open
    remainder, `price` the cost. Raw rows, not `_row_to_dict`: the economics wants
    `Decimal` and real datetimes, and stringifying them here would force it to
    parse its own input back.
    """
    ids = [p for p in (position_ids or []) if p]
    if not ids:
        return {}
    rows = await conn.fetch(
        """SELECT id, position_id, fill_time, qty, price, fees, source
             FROM position_lots
            WHERE position_id = ANY($1::text[])
            ORDER BY position_id, fill_time, id""",
        ids,
    )
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["position_id"], []).append(dict(r))
    return out
