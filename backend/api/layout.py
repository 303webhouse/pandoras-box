"""Dashboard v2 layout persistence (GET/POST /api/layout).

Stores the Gridstack layout JSON for the /app/v2 board server-side so tile positions
survive a reload. AEGIS: reuses the existing HttpOnly session cookie — no new secret,
no new auth surface. Single dashboard user, so one row keyed 'default'. Additive table.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Body, HTTPException, Request

from database.postgres_client import get_postgres_client
from utils.session import COOKIE_NAME, verify_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["layout"])

_LAYOUT_KEY = "default"


async def _ensure_table(conn) -> None:
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS v2_dashboard_layout (
               layout_key TEXT PRIMARY KEY,
               layout     JSONB,
               updated_at TIMESTAMPTZ DEFAULT now()
           )"""
    )


@router.get("/layout")
async def get_layout():
    """Return the stored v2 layout (or null if none saved yet)."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await _ensure_table(conn)
        row = await conn.fetchrow(
            "SELECT layout, updated_at FROM v2_dashboard_layout WHERE layout_key=$1", _LAYOUT_KEY
        )
    if not row or row["layout"] is None:
        return {"layout": None, "updated_at": None}
    layout = row["layout"]
    if isinstance(layout, str):
        try:
            layout = json.loads(layout)
        except Exception:
            layout = None
    return {"layout": layout, "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None}


@router.post("/layout")
async def post_layout(request: Request, payload: dict = Body(...)):
    """Persist the v2 layout. Requires the dashboard session (same gate as the UI)."""
    if not verify_session(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="auth required")
    layout = payload.get("layout")
    if layout is None:
        raise HTTPException(status_code=400, detail="missing layout")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await _ensure_table(conn)
        await conn.execute(
            """INSERT INTO v2_dashboard_layout (layout_key, layout, updated_at)
               VALUES ($1, $2::jsonb, now())
               ON CONFLICT (layout_key) DO UPDATE SET layout=EXCLUDED.layout, updated_at=now()""",
            _LAYOUT_KEY, json.dumps(layout),
        )
    return {"ok": True}
