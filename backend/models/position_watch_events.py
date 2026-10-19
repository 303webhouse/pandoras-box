"""`position_watch_events`: the log QUERY's 10-session live check reads. R-IV.1233(b).

AN EVENT LOG, NOT A PUSH LOG. Every detected event gets a row whether or not it was pushed,
because otherwise the DENOMINATOR of "what share was pushed" is unknowable and QUERY would have
to reconstruct it -- which R-IV.1233(b) forbids. A suppressed alert is a row with `pushed`
false and the suppression reason `may_push` itself returned.

THE THREE FIELDS WHOSE DOMAIN HAD TO BE STATED, from this lane's report under R-IV.1233(b):

  1. THE PUSH TIMESTAMP IS NOT THE EVENT TIMESTAMP. A suppressed event has no push instant, so
     one column would make NULL mean two different things. `detected_at` is on every row;
     `pushed_at` is NULL unless something was actually sent.

  2. `relation` HAS THREE VALUES, not the two the ruling lists. `classify_relation` answers
     UNKNOWN for a structure it does not know, deliberately (R-IV.1209(f)3: unknown is its own
     answer and is never pushed). UNKNOWN is stored as a literal string, so a NULL in that
     column can only ever mean "not written" and the three-way domain is visible to anyone who
     groups by it.

  3. `gap_held` IS NOT KNOWABLE WHEN THE BAR-1 ROW IS WRITTEN. At the first bar the gap has not
     resolved; whether it holds is bar 2's fact. The bar-1 row carries NULL plus a paired
     reason, and the BAR-2 row carries the resolution. THE FIRST ROW IS NEVER UPDATED: an event
     log that rewrites its own history cannot be audited, and QUERY's check would be reading a
     record of what we believe now rather than of what we sent then.

Every NULL above is paired with a reason, because a bare NULL is indistinguishable from a
writer that failed -- and QUERY reports UNAVAILABLE rather than inferring.

DISPLAY ONLY (#42). Nothing gates, grades or feeds Kairos from this table.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("position_watch_events")

TABLE = "position_watch_events"

#: Created AT STARTUP by main.py, not by this writer. A read path that waits on a writer having
#: run is a fault this repo has filed four times; `api/position_watch` SELECTs this table.
DDL = """
CREATE TABLE IF NOT EXISTS position_watch_events (
    id                SERIAL PRIMARY KEY,
    detected_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bar_close_at      TIMESTAMPTZ NOT NULL,
    session_date      DATE NOT NULL,
    pushed_at         TIMESTAMPTZ,
    ticker            TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    relation          TEXT,
    pushed            BOOLEAN NOT NULL DEFAULT FALSE,
    suppression_reason TEXT,
    gap_open          BOOLEAN NOT NULL DEFAULT FALSE,
    gap_held          BOOLEAN,
    gap_held_reason   TEXT,
    side              TEXT,
    level             NUMERIC,
    close_price       NUMERIC,
    action            TEXT,
    shown_regime      TEXT,
    basis             TEXT,
    revised_of        INTEGER REFERENCES position_watch_events(id)
)
"""

DDL_INDEX = ("CREATE INDEX IF NOT EXISTS position_watch_events_session_idx "
             "ON position_watch_events (session_date, ticker, event_type)")

#: The three-valued domain of `relation`, stored as literals (see note 2 above).
RELATION_UNKNOWN = "UNKNOWN"

GAP_HELD_PENDING = "not yet known: the second bar had not closed"
GAP_HELD_NOT_APPLICABLE = "not a gap-open session"


def relation_value(relation: Optional[str]) -> str:
    """The stored form of a relation. None becomes the LITERAL 'UNKNOWN', never NULL."""
    r = str(relation or "").strip().upper()
    return r if r in ("AGAINST", "WITH") else RELATION_UNKNOWN


def gap_fields(event: Dict[str, Any]) -> Dict[str, Any]:
    """(gap_open, gap_held, gap_held_reason) for one detector dict.

    THE ONLY PLACE THAT DECIDES THIS, so the pending case and the not-applicable case cannot be
    collapsed into one NULL by a second author. A STRUCTURAL null and a PENDING null are
    different facts (Convention #41), and here they are told apart by their reason, not by the
    value.
    """
    kind = str(event.get("event", "")).upper()
    if kind == "GAP_FADED":
        return {"gap_open": True, "gap_held": False, "gap_held_reason": None}
    if not event.get("gap_open"):
        return {"gap_open": False, "gap_held": None,
                "gap_held_reason": GAP_HELD_NOT_APPLICABLE}
    if event.get("confirmed"):
        return {"gap_open": True, "gap_held": True, "gap_held_reason": None}
    return {"gap_open": True, "gap_held": None, "gap_held_reason": GAP_HELD_PENDING}


def row_for(event: Dict[str, Any], *, ticker: str, session_date: _dt.date,
            bar_close_at: _dt.datetime, relation: Optional[str], action: str,
            pushed: bool, suppression_reason: Optional[str],
            shown_regime: Optional[str], pushed_at: Optional[_dt.datetime] = None,
            revised_of: Optional[int] = None) -> Dict[str, Any]:
    """The full row, assembled in ONE place so no caller can omit a paired reason.

    `suppression_reason` is required when `pushed` is false and refused when it is true -- a
    row that says "not pushed" with no reason is the silence this table exists to remove.
    """
    if not pushed and not suppression_reason:
        raise ValueError("a not-pushed row needs the reason may_push returned")
    if pushed and suppression_reason:
        raise ValueError("a pushed row cannot also carry a suppression reason")
    if pushed and pushed_at is None:
        raise ValueError("a pushed row needs its push instant")
    row = {
        "bar_close_at": bar_close_at,
        "session_date": session_date,
        "pushed_at": pushed_at if pushed else None,
        "ticker": str(ticker).upper(),
        "event_type": str(event.get("event", "")).upper(),
        "relation": relation_value(relation),
        "pushed": bool(pushed),
        "suppression_reason": suppression_reason,
        "side": event.get("side"),
        "level": event.get("level"),
        "close_price": event.get("close"),
        "action": action,
        "shown_regime": shown_regime,
        "basis": event.get("basis"),
        "revised_of": revised_of,
    }
    row.update(gap_fields(event))
    return row


_COLS = ("bar_close_at", "session_date", "pushed_at", "ticker", "event_type", "relation",
         "pushed", "suppression_reason", "gap_open", "gap_held", "gap_held_reason", "side",
         "level", "close_price", "action", "shown_regime", "basis", "revised_of")


async def insert(conn, row: Dict[str, Any]) -> Optional[int]:
    """One row, returning its id. Numerics are passed as float, which asyncpg accepts."""
    vals = [row.get(c) for c in _COLS]
    for i, c in enumerate(_COLS):
        if c in ("level", "close_price") and vals[i] is not None:
            vals[i] = float(vals[i])
    sql = ("INSERT INTO position_watch_events (%s) VALUES (%s) RETURNING id"
           % (", ".join(_COLS), ", ".join("$%d" % (i + 1) for i in range(len(_COLS)))))
    return await conn.fetchval(sql, *vals)


async def already_logged(conn, *, session_date: _dt.date, ticker: str,
                         event_type: str) -> bool:
    """Has this ticker already logged this event type this session?

    The detector is idempotent by construction for the SAME bar, but the job runs every 15
    minutes and a restart re-reads the session, so without this a restart would re-log (and
    on a restart with the wire live, re-push) events already recorded.
    """
    got = await conn.fetchval(
        "SELECT 1 FROM position_watch_events "
        " WHERE session_date = $1 AND ticker = $2 AND event_type = $3 LIMIT 1",
        session_date, str(ticker).upper(), str(event_type).upper())
    return got is not None


async def fired_sides(conn, *, session_date: _dt.date, ticker: str) -> List[str]:
    """The directions whose break has been logged as CONFIRMED this session.

    CONFIRMED ONLY, which is R-IV.1226(b)'s rule carried into storage: an unconfirmed gap row
    must not count, or the bar-2 confirmation would be suppressed and a gap would never reach
    the phone. `gap_held IS NOT FALSE` keeps the ordinary (non-gap) break, whose `gap_held` is
    NULL-with-a-reason, and drops the faded gap.
    """
    rows = await conn.fetch(
        "SELECT DISTINCT side FROM position_watch_events "
        " WHERE session_date = $1 AND ticker = $2 AND event_type = 'LEVEL_BREAK' "
        "   AND side IS NOT NULL "
        "   AND (gap_open = FALSE OR gap_held IS TRUE)",
        session_date, str(ticker).upper())
    return [r["side"] for r in rows]


async def pushes_today(conn, session_date: _dt.date) -> int:
    return int(await conn.fetchval(
        "SELECT COUNT(*) FROM position_watch_events "
        " WHERE session_date = $1 AND pushed IS TRUE", session_date) or 0)


async def recent_pushes(conn, session_date: _dt.date) -> List[Dict[str, Any]]:
    """This session's pushes in the shape `may_push` expects for its cooldown and (a)3 gate."""
    rows = await conn.fetch(
        "SELECT ticker, event_type, pushed_at, session_date FROM position_watch_events "
        " WHERE session_date = $1 AND pushed IS TRUE ORDER BY pushed_at DESC",
        session_date)
    return [{"ticker": r["ticker"], "event": r["event_type"], "pushed_at": r["pushed_at"],
             "session_date": r["session_date"]} for r in rows]


async def session_rows(conn, session_date: _dt.date, limit: int = 200) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT * FROM position_watch_events WHERE session_date = $1 "
        " ORDER BY bar_close_at DESC, id DESC LIMIT $2", session_date, limit)
    return [dict(r) for r in rows]


async def cap_notice_sent(conn, session_date: _dt.date) -> bool:
    """R-IV.1220(a)4's once-per-session notice, recorded as its own event type."""
    got = await conn.fetchval(
        "SELECT 1 FROM position_watch_events "
        " WHERE session_date = $1 AND event_type = 'CAP_NOTICE' LIMIT 1", session_date)
    return got is not None


async def unconfirmed_gap_id(conn, *, session_date: _dt.date, ticker: str,
                             side: Optional[str]) -> Optional[int]:
    """The id of this session's UNCONFIRMED gap-open break row, if there is one.

    R-IV.1215(b)5's REVISED marking, applied to the one restatement that actually happens in
    B2. THE RULING'S OWN TEXT FOR (b)5 IS NOT IN BUILD'S LANE RECORD -- only the words "REVISED
    marking" survive in it -- so rather than reconstruct the rule (R-IV.1226(e)'s principle),
    this implements the single case where a panel row Nick has already seen stops being true,
    and the report says so for correction:

      a gap-open break logs "opened above the prior-day high" on bar 1, which is a real event
      at the time. If bar 2 closes back inside, that row's reading is SUPERSEDED -- the level
      did not hold. The GAP_FADED row points at it with `revised_of`, and the panel marks the
      earlier row REVISED rather than deleting it or leaving it reading as current.

    Nothing is mutated: the superseded row stays exactly as written, which is the same reason
    the bar-1 row's `gap_held` is never updated in place.
    """
    return await conn.fetchval(
        "SELECT id FROM position_watch_events "
        " WHERE session_date = $1 AND ticker = $2 AND event_type = 'LEVEL_BREAK' "
        "   AND gap_open IS TRUE AND gap_held IS NULL "
        "   AND ($3::text IS NULL OR side = $3) "
        " ORDER BY id DESC LIMIT 1",
        session_date, str(ticker).upper(), (str(side).lower() if side else None))


async def revised_ids(conn, session_date: _dt.date) -> List[int]:
    """The ids this session's rows have superseded, for the panel's REVISED tag."""
    rows = await conn.fetch(
        "SELECT DISTINCT revised_of FROM position_watch_events "
        " WHERE session_date = $1 AND revised_of IS NOT NULL", session_date)
    return [int(r["revised_of"]) for r in rows]
