"""
Trade Watchlist API — Long/Short idea staging area
Separate from the RADAR ticker screener (api/watchlist.py)

Endpoints:
- GET    /trade-watchlist              — List all active watchlist entries
- POST   /trade-watchlist              — Add a new ticker
- PATCH  /trade-watchlist/{id}         — Update entry (grade, target, thesis, etc.)
- DELETE /trade-watchlist/{id}         — Soft-delete (set is_active = FALSE)
- POST   /trade-watchlist/{id}/reactivate — Reactivate a soft-deleted entry
- GET    /trade-watchlist/alerts       — Get entries where alert has fired
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.postgres_client import get_postgres_client

logger = logging.getLogger("trade_watchlist")
router = APIRouter(prefix="/trade-watchlist", tags=["trade-watchlist"])

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY") or ""

TRADE_WATCHLIST_DDL = """
CREATE TABLE IF NOT EXISTS trade_watchlist (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_target NUMERIC(10,2),
    current_price NUMERIC(10,2),
    distance_to_target_pct NUMERIC(6,2),
    thesis_note TEXT,
    committee_grade TEXT CHECK (committee_grade IN ('A', 'A-', 'B+', 'B', 'B-', 'C', NULL)),
    source TEXT DEFAULT 'MANUAL' CHECK (source IN ('MANUAL', 'UW_FLOW', 'SCANNER', 'COMMITTEE')),
    bucket TEXT CHECK (bucket IN ('THESIS', 'TACTICAL', NULL)),
    next_earnings_date DATE,
    earnings_timing TEXT CHECK (earnings_timing IN ('BMO', 'AMC', 'TNS', NULL)),
    alert_fired BOOLEAN DEFAULT FALSE,
    alert_fired_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_watchlist_ticker UNIQUE (ticker)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_active ON trade_watchlist (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_watchlist_direction ON trade_watchlist (direction);
"""


async def init_trade_watchlist_table():
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute(TRADE_WATCHLIST_DDL)


# --- Pydantic Models ---

class WatchlistEntry(BaseModel):
    ticker: str
    direction: str
    entry_target: Optional[float] = None
    thesis_note: Optional[str] = None
    committee_grade: Optional[str] = None
    source: str = "MANUAL"
    bucket: Optional[str] = None


class WatchlistUpdate(BaseModel):
    entry_target: Optional[float] = None
    thesis_note: Optional[str] = None
    committee_grade: Optional[str] = None
    source: Optional[str] = None
    bucket: Optional[str] = None
    direction: Optional[str] = None
    next_earnings_date: Optional[str] = None
    earnings_timing: Optional[str] = None


# --- Helpers ---

async def _fetch_polygon_price(ticker: str) -> Optional[float]:
    if not POLYGON_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
                params={"apiKey": POLYGON_API_KEY},
            )
            if resp.status_code == 200:
                snap = resp.json()
                price = (
                    snap.get("ticker", {}).get("day", {}).get("c", 0)
                    or snap.get("ticker", {}).get("lastTrade", {}).get("p", 0)
                    or snap.get("ticker", {}).get("prevDay", {}).get("c", 0)
                )
                return float(price) if price else None
    except Exception as e:
        logger.debug("Polygon price fetch failed for %s: %s", ticker, e)
    return None


def _compute_distance(direction: str, current_price: float, entry_target: float) -> float:
    if not entry_target or entry_target == 0:
        return 0.0
    if direction == "LONG":
        return round(((current_price - entry_target) / entry_target) * 100, 2)
    else:  # SHORT
        return round(((entry_target - current_price) / current_price) * 100, 2)


def _row_to_dict(row) -> dict:
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif not isinstance(v, (int, float, str, bool, type(None), list, dict)):
            d[k] = float(v) if v is not None else None
    return d


# --- Routes ---

@router.get("")
async def list_watchlist(
    direction: Optional[str] = None,
    active_only: bool = True,
):
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if direction:
            rows = await conn.fetch(
                """SELECT * FROM trade_watchlist
                   WHERE ($1::bool IS FALSE OR is_active = TRUE) AND direction = $2
                   ORDER BY distance_to_target_pct ASC NULLS LAST""",
                active_only, direction.upper(),
            )
        else:
            rows = await conn.fetch(
                """SELECT * FROM trade_watchlist
                   WHERE ($1::bool IS FALSE OR is_active = TRUE)
                   ORDER BY direction, distance_to_target_pct ASC NULLS LAST""",
                active_only,
            )

    entries = [_row_to_dict(r) for r in rows]
    long_ideas = [e for e in entries if e["direction"] == "LONG"]
    short_ideas = [e for e in entries if e["direction"] == "SHORT"]
    alerts_pending = sum(1 for e in entries if e.get("alert_fired"))

    return {
        "long_ideas": long_ideas,
        "short_ideas": short_ideas,
        "total": len(entries),
        "alerts_pending": alerts_pending,
    }


@router.post("")
async def add_watchlist_entry(entry: WatchlistEntry):
    ticker = entry.ticker.upper().strip()
    direction = entry.direction.upper().strip()
    if direction not in ("LONG", "SHORT"):
        raise HTTPException(status_code=400, detail="direction must be LONG or SHORT")

    current_price = await _fetch_polygon_price(ticker)
    distance = None
    if current_price and entry.entry_target:
        distance = _compute_distance(direction, current_price, entry.entry_target)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Check if ticker already exists (maybe inactive)
        existing = await conn.fetchrow(
            "SELECT id, is_active FROM trade_watchlist WHERE ticker = $1", ticker
        )

        if existing:
            # Reactivate with new values
            row = await conn.fetchrow(
                """UPDATE trade_watchlist SET
                    direction = $1, entry_target = $2, current_price = $3,
                    distance_to_target_pct = $4, thesis_note = $5,
                    committee_grade = $6, source = $7, bucket = $8,
                    is_active = TRUE, alert_fired = FALSE, alert_fired_at = NULL,
                    updated_at = NOW()
                   WHERE ticker = $9 RETURNING *""",
                direction, entry.entry_target, current_price,
                distance, entry.thesis_note,
                entry.committee_grade, entry.source, entry.bucket,
                ticker,
            )
        else:
            row = await conn.fetchrow(
                """INSERT INTO trade_watchlist
                    (ticker, direction, entry_target, current_price,
                     distance_to_target_pct, thesis_note,
                     committee_grade, source, bucket)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
                ticker, direction, entry.entry_target, current_price,
                distance, entry.thesis_note,
                entry.committee_grade, entry.source, entry.bucket,
            )

    return _row_to_dict(row)


@router.patch("/{entry_id}")
async def update_watchlist_entry(entry_id: str, update: WatchlistUpdate):
    try:
        eid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry ID")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM trade_watchlist WHERE id = $1", eid
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Entry not found")

        # Build update fields
        fields = {}
        if update.entry_target is not None:
            fields["entry_target"] = update.entry_target
        if update.thesis_note is not None:
            fields["thesis_note"] = update.thesis_note
        if update.committee_grade is not None:
            fields["committee_grade"] = update.committee_grade
        if update.source is not None:
            fields["source"] = update.source
        if update.bucket is not None:
            fields["bucket"] = update.bucket
        if update.direction is not None:
            fields["direction"] = update.direction.upper()
        if update.next_earnings_date is not None:
            fields["next_earnings_date"] = update.next_earnings_date
        if update.earnings_timing is not None:
            fields["earnings_timing"] = update.earnings_timing

        if not fields:
            return _row_to_dict(existing)

        # Recalculate distance if target or direction changed
        direction = fields.get("direction", existing["direction"])
        entry_target = fields.get("entry_target", existing["entry_target"])
        current_price = existing["current_price"]

        if "entry_target" in fields or "direction" in fields:
            if current_price and entry_target:
                fields["distance_to_target_pct"] = _compute_distance(
                    direction, float(current_price), float(entry_target)
                )

        # Dynamic SQL
        set_parts = []
        params = []
        for i, (k, v) in enumerate(fields.items(), start=1):
            set_parts.append(f"{k} = ${i}")
            params.append(v)
        params.append(eid)
        set_clause = ", ".join(set_parts)

        row = await conn.fetchrow(
            f"UPDATE trade_watchlist SET {set_clause}, updated_at = NOW() WHERE id = ${len(params)} RETURNING *",
            *params,
        )

    return _row_to_dict(row)


@router.delete("/{entry_id}")
async def delete_watchlist_entry(entry_id: str):
    try:
        eid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry ID")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE trade_watchlist SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
            eid,
        )
    return {"status": "deactivated", "id": entry_id}


@router.post("/{entry_id}/reactivate")
async def reactivate_watchlist_entry(entry_id: str):
    try:
        eid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry ID")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE trade_watchlist SET is_active = TRUE, alert_fired = FALSE,
               alert_fired_at = NULL, updated_at = NOW()
               WHERE id = $1 RETURNING *""",
            eid,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    return _row_to_dict(row)


@router.get("/alerts")
async def get_watchlist_alerts():
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM trade_watchlist
               WHERE alert_fired = TRUE AND is_active = TRUE
               ORDER BY alert_fired_at DESC"""
        )
    return {"alerts": [_row_to_dict(r) for r in rows]}


# --- Background Price Alert Check ---

async def check_watchlist_price_alerts():
    """
    For each active watchlist entry where alert_fired = FALSE:
    1. Fetch current price from Polygon
    2. Update current_price and distance_to_target_pct
    3. If price crossed entry target, fire alert
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM trade_watchlist
               WHERE is_active = TRUE AND alert_fired = FALSE AND entry_target IS NOT NULL"""
        )

    if not rows:
        return

    logger.info("Watchlist price check: %d entries", len(rows))

    for row in rows:
        ticker = row["ticker"]
        direction = row["direction"]
        entry_target = float(row["entry_target"])

        current_price = await _fetch_polygon_price(ticker)
        if not current_price:
            continue

        distance = _compute_distance(direction, current_price, entry_target)

        # Check for target crossing
        target_hit = False
        if direction == "LONG" and current_price <= entry_target:
            target_hit = True
        elif direction == "SHORT" and current_price >= entry_target:
            target_hit = True

        async with pool.acquire() as conn:
            if target_hit:
                await conn.execute(
                    """UPDATE trade_watchlist SET
                        current_price = $1, distance_to_target_pct = $2,
                        alert_fired = TRUE, alert_fired_at = NOW(), updated_at = NOW()
                       WHERE id = $3""",
                    current_price, distance, row["id"],
                )
                logger.info("WATCHLIST ALERT: %s hit target $%.2f (current $%.2f, direction %s)",
                            ticker, entry_target, current_price, direction)
                await _fire_watchlist_alert(dict(row) | {
                    "current_price": current_price,
                    "alert_fired_at": datetime.now(timezone.utc),
                })
            else:
                await conn.execute(
                    """UPDATE trade_watchlist SET
                        current_price = $1, distance_to_target_pct = $2, updated_at = NOW()
                       WHERE id = $3""",
                    current_price, distance, row["id"],
                )


async def _fire_watchlist_alert(entry: dict):
    """Push watchlist target hit to all connected clients via WebSocket."""
    try:
        from api.websocket_manager import broadcast_event
        await broadcast_event("watchlist_alert", {
            "ticker": entry["ticker"],
            "direction": entry["direction"],
            "entry_target": float(entry["entry_target"]),
            "current_price": float(entry["current_price"]),
            "thesis_note": entry.get("thesis_note", ""),
            "committee_grade": entry.get("committee_grade"),
            "bucket": entry.get("bucket"),
            "fired_at": entry["alert_fired_at"].isoformat() if entry.get("alert_fired_at") else None,
        })
    except Exception as e:
        logger.debug("Watchlist WebSocket broadcast failed: %s", e)
