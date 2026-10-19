"""`GET /api/position-watch` — the live Position Watch panel. B2, R-IV.1209(f).

SERVES THE SAME SHAPE AS A3'S MOCK FIXTURE, deliberately, so the frontend's live path is the
mock's renderer with a different source rather than a second renderer that can drift from it.

AND IT NEVER FALLS BACK TO THE MOCK. If the live read fails, this returns the failure with
`live: true` and an empty row list; the panel then says so. A mock served through the live route
is the fake-healthy fault this repo has filed against `/api/crypto/market`, where a sibling
symbol's price was served as the one asked for and looked perfectly well.

DISPLAY ONLY (#42), and every served field declares its origin.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from utils.pivot_auth import require_api_key

from models import position_watch as pw
from models import position_watch_events as pwe
from stable_engine import sessions as _sessions

logger = logging.getLogger("api_position_watch")

router = APIRouter(prefix="/position-watch", tags=["position-watch"])
# Included with prefix="/api" in main.py, like every other router here -- declaring
# "/api/position-watch" HERE would serve it at /api/api/position-watch.

#: (f)5's standing caption, and the phone line R-IV.1228(d) rules verbatim.
CAPTION = "alerts, not signals · bar-close only · never graded"

_GLYPH = {
    ("LEVEL_BREAK", "above"): ("↑", "bull"),
    ("LEVEL_BREAK", "below"): ("↓", "bear"),
    ("FAILED_BREAKOUT", "above"): ("↺", "bear"),
    ("FAILED_BREAKOUT", "below"): ("↺", "bull"),
    ("GAP_FADED", "above"): ("⇣", "bear"),
    ("GAP_FADED", "below"): ("⇡", "bull"),
}


def _glyph(event: str, side: Optional[str]) -> tuple:
    return _GLYPH.get((str(event).upper(), str(side or "").lower()), ("•", "neutral"))


def row_view(r: Dict[str, Any], *, revised: set) -> Dict[str, Any]:
    """One stored event as the panel's row.

    `REVISED` is a TAG ON THE SUPERSEDED ROW, not an edit of it (R-IV.1215(b)5 as implemented
    under `position_watch_events.unconfirmed_gap_id`). The row keeps the words it was written
    with, and the tag says a later bar changed what they mean -- a number that silently becomes
    a different number is the thing a log is supposed to prevent.
    """
    glyph, lean = _glyph(r.get("event_type"), r.get("side"))
    at = r.get("bar_close_at")
    return {
        "id": r.get("id"),
        "time": at.astimezone(_sessions.ET).strftime("%H:%M") if at else "—",
        "source": "YF 15m",
        "glyph": glyph,
        "glyph_lean": lean,
        "ticker": r.get("ticker"),
        "event": str(r.get("event_type", "")).replace("_", " "),
        "tf": "15m · close",
        "detail": r.get("basis") or "",
        "against": str(r.get("relation", "")).upper() == "AGAINST",
        "relation": r.get("relation"),
        "shown_regime": r.get("shown_regime"),
        "action": r.get("action") or pw.ACTION_LOGGED,
        "pushed": bool(r.get("pushed")),
        "suppression_reason": r.get("suppression_reason"),
        "revised": r.get("id") in revised,
        "gap_open": bool(r.get("gap_open")),
        "gap_held": r.get("gap_held"),
        "gap_held_reason": r.get("gap_held_reason"),
    }


async def payload(conn, *, now: Optional[_dt.datetime] = None) -> Dict[str, Any]:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    today = _sessions.to_et(now).date()

    from jobs.position_watch_job import load_book

    book = await load_book(conn)
    sb = pw.set_b(book)
    rows = await pwe.session_rows(conn, today)
    revised = set(await pwe.revised_ids(conn, today))
    views = [row_view(r, revised=revised) for r in rows]
    held = [v for v in views if v["ticker"] in sb["watch"] or v["ticker"] == "PANDORA"]
    pushes = [{"ago": v["time"], "title": "%s · %s" % (v["ticker"], v["event"].lower()),
               "body": v["detail"], "tag": "alert, not a signal"}
              for v in views if v["pushed"]]

    return {
        "live": True,
        "session_date": today.isoformat(),
        "rows": held,
        "held_count": len(held),
        "quiet_count": 0,
        "quiet_note": "B2 watches only tickers in the open book, so there is no quiet list",
        "caption": CAPTION,
        # R-IV.1215(b)3 + R-IV.1228(d): the footer, built from the SAME resolution the detector
        # ran on, so the panel cannot claim to watch something the job skipped.
        "footer": {
            "watched": sb["watch"],
            "watched_via": sb["via"],
            "not_watched": sb["not_watched"],
            "phone": pw.PANEL_FOOTER_PHONE_LINE,
            "pushes_enabled": pw.PUSHES_ENABLED,
        },
        "push_rule": pw.PANEL_FOOTER_PHONE_LINE,
        "pushes": pushes,
        "field_origin": {
            "rows": "stored", "footer.watched": "derived",
            "footer.not_watched": "derived", "footer.phone": "stored",
            "revised": "derived", "pushes": "stored",
        },
    }


@router.get("")
async def get_position_watch(_: str = Depends(require_api_key)) -> Dict[str, Any]:
    """The panel. On failure it says so; it never serves the mock.

    THE IMPORT IS INSIDE THE TRY, and that is the fix for a real outage this route had on its
    first deploy: it read `database.connection`, which does not exist (the module is
    `database.postgres_client`). A deferred import that cannot resolve raises at REQUEST time,
    not at boot -- so the app was healthy, every other route worked, and this one returned a
    bare 500 with no log line of its own, because the failing line was the one line OUTSIDE
    the handler's own error path. Inside the try, the same mistake returns the honest payload
    below and names the exception.
    """
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            return await payload(conn)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[pw-api] failed: %s", type(exc).__name__)
        return {"live": True, "rows": [], "held_count": 0, "quiet_count": 0,
                "caption": CAPTION, "error": "%s" % type(exc).__name__,
                "note": "the live Position Watch read failed; no mock is substituted"}
