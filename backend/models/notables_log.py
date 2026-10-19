"""`notables_log` and `notables_outcomes`. R-IV.1259(h), wired under R-IV.1265(g)2.

TWO TABLES, AND THE SPLIT IS THE POINT.

`notables_log` IS APPEND-ONLY AND LOGS EVERY CANDIDATE, INCLUDING THE DROPPED ONES WITH THEIR
REASON. Without the drops the denominator of "what share of candidates was shown" is
unknowable, and the cap, the per-ticker rule and the PYTHIA gate would each be invisible in the
record -- a surface that logged only what it displayed would make its own filters unauditable.
The same finding as `position_watch_events`: an event log that records only the events it acted
on cannot answer the question it exists for.

NOTHING IS EVER UPDATED. A card that ages, or gains a second reason, gets a NEW ROW referring to
the first (`supersedes`). A log that rewrites its own history is a record of what we believe
now, not of what we showed then -- and the taps below are read against what was shown.

INPUTS ARE FROZEN AT THE MOMENT OF THE DECISION (`inputs` JSONB) and the 1x rung's mid is its
own column, because that is the number a later reader will want to compare against and it must
not have to be re-derived from a chain that has since moved.

`notables_outcomes` IS SEPARATE, AND CARRIES NO OPTION P&L. (h) is explicit: the stock's move at
+1 / +3 / +5 days, expressed in EM units. Option P&L would be a claim about a trade nobody
placed -- the strip shows rungs and highlights none of them (R-IV.1259(f)), so there is no
position whose P&L could be computed. The EM denominator is stored BESIDE the move so a reader
can see what the move was divided by; a ratio without its denominator is the fault class this
board files as "a caption that lies about its field".

THE TAPS ARE THREE AND THEY ARE NOT A VERDICT. looked / useful / noise (h) record what Nick did
with a card, not whether the card was right. Nothing gates on them (#42).

DATES ARE SESSIONS (Convention #39). `session_date` is a DATE in the market's own calendar, and
`created_at` is the write instant -- the two are never conflated, which is the fault
`position_lot_closures.trade_date` was created to fix one table over.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("notables_log")

TABLE = "notables_log"
OUTCOMES_TABLE = "notables_outcomes"

#: The five card kinds of R-IV.1259(c), stored as literals. A candidate that is dropped still
#: carries the kind it would have been, or the drop reasons cannot be read per card type.
CARD_KINDS = ("LOUD_MOVE", "VALUE_MOVED", "FAILED_BREAK", "TREND_CHANGE", "ROTATION_SHIFT")

#: R-IV.1259(d)'s taps. Three values, and a NULL means "no tap", which is its own fact.
TAPS = ("looked", "useful", "noise")

#: Why a candidate was not shown. Every drop writes ONE of these, never NULL: a dropped row with
#: no reason is indistinguishable from a writer that failed halfway.
DROP_CAP_REACHED = "cap reached: 5 ticker cards already shown today"
DROP_ALREADY_TODAY = "this ticker already has a card today; the new reason lit a chip on it"
DROP_PYTHIA_STALE = "this ticker's PYTHIA status is not ok, or its last update is over 90 trading minutes old"
DROP_OUT_OF_HOURS = "outside 09:45-15:30 ET"
DROP_NOT_IN_UNIVERSE = "not in the on-screen universe; logged only"
DROP_STRUCTURE_CARD_EXCLUDED = "this ticker is excluded from the structure cards (R-IV.1258(a)4)"
DROP_HELD_POSITION = "held position: it belongs in Your book, not here"

DROP_REASONS = (DROP_CAP_REACHED, DROP_ALREADY_TODAY, DROP_PYTHIA_STALE, DROP_OUT_OF_HOURS,
                DROP_NOT_IN_UNIVERSE, DROP_STRUCTURE_CARD_EXCLUDED, DROP_HELD_POSITION)

DDL = """
CREATE TABLE IF NOT EXISTS notables_log (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_date    DATE        NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL,
    ticker          TEXT,
    card_kind       TEXT        NOT NULL,
    shown           BOOLEAN     NOT NULL,
    drop_reason     TEXT,
    direction       TEXT,
    reasons         TEXT,
    counter_evidence TEXT,
    stale_if        TEXT,
    inputs          JSONB,
    rung_1x_mid     NUMERIC,
    em_dollars      NUMERIC,
    expiry          DATE,
    iv_rank         NUMERIC,
    iv_band         TEXT,
    spread_pct      NUMERIC,
    strip_state     TEXT,
    tap             TEXT,
    tapped_at       TIMESTAMPTZ,
    supersedes      BIGINT REFERENCES notables_log(id)
)
"""

DDL_INDEX = ("CREATE INDEX IF NOT EXISTS notables_log_session_idx "
             "ON notables_log (session_date, ticker, card_kind)")

#: A shown row must not carry a drop reason and a dropped row must carry one. Enforced in the
#: DATABASE as well as in `row_for`, because the writer is not the only thing that can insert:
#: a backfill, a repair script or a future caller all bypass Python validation, and the one
#: invariant this table has is that `shown` and `drop_reason` agree.
DDL_CHECK = (
    "ALTER TABLE notables_log ADD CONSTRAINT notables_log_drop_reason_agrees "
    "CHECK ((shown IS TRUE AND drop_reason IS NULL) "
    "    OR (shown IS FALSE AND drop_reason IS NOT NULL))")

OUTCOMES_DDL = """
CREATE TABLE IF NOT EXISTS notables_outcomes (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    log_id          BIGINT      NOT NULL REFERENCES notables_log(id) ON DELETE CASCADE,
    horizon_days    SMALLINT    NOT NULL,
    graded_at       TIMESTAMPTZ,
    move_pct        NUMERIC,
    em_pct          NUMERIC,
    move_in_em      NUMERIC,
    basis           TEXT,
    unavailable_reason TEXT,
    UNIQUE (log_id, horizon_days)
)
"""

OUTCOMES_DDL_INDEX = ("CREATE INDEX IF NOT EXISTS notables_outcomes_log_idx "
                      "ON notables_outcomes (log_id, horizon_days)")

#: (h)'s horizons. Stored per row rather than as three columns, so a horizon that cannot be
#: graded yet is an ABSENT ROW rather than a NULL in a row that claims to be complete.
HORIZONS = (1, 3, 5)


async def migrate(conn) -> Dict[str, Any]:
    """Create both tables, their indexes and the check constraint. Idempotent.

    R-IV.1259(h): "Both tables are created in the deploy that writes to them." This runs at
    startup in the same deploy as the writer below, and never earlier -- an empty table that
    predates its writer is the state a later reader mistakes for a quiet day.
    """
    out: Dict[str, Any] = {}
    await conn.execute(DDL)
    await conn.execute(DDL_INDEX)
    await conn.execute(OUTCOMES_DDL)
    await conn.execute(OUTCOMES_DDL_INDEX)
    # ADD CONSTRAINT has no IF NOT EXISTS before PG 17, so a second run raises
    # DuplicateObject. Caught by name rather than swallowed wholesale, so a DIFFERENT failure
    # here is still reported.
    try:
        await conn.execute(DDL_CHECK)
        out["check_added"] = True
    except Exception as exc:                                        # noqa: BLE001
        name = type(exc).__name__
        out["check_added"] = False
        out["check_note"] = name
        if "Duplicate" not in name and "duplicate" not in str(exc).lower():
            logger.warning("[notables_log] check constraint not added: %s", name)
    out["tables"] = [TABLE, OUTCOMES_TABLE]
    return out


def row_for(*, session_date: _dt.date, detected_at: _dt.datetime, card_kind: str,
            ticker: Optional[str], shown: bool, drop_reason: Optional[str] = None,
            direction: Optional[str] = None, reasons: Optional[List[str]] = None,
            counter_evidence: Optional[List[str]] = None, stale_if: Optional[str] = None,
            inputs: Optional[Dict[str, Any]] = None, rung_1x_mid: Optional[float] = None,
            em_dollars: Optional[float] = None, expiry: Optional[_dt.date] = None,
            iv_rank: Optional[float] = None, iv_band: Optional[str] = None,
            spread_pct: Optional[float] = None, strip_state: Optional[str] = None,
            supersedes: Optional[int] = None) -> Dict[str, Any]:
    """One row, validated. Raises rather than writing a row that cannot be read back.

    THE TWO REFUSALS, both of which would otherwise produce a row nobody can interpret:
      * a DROPPED candidate with no reason -- indistinguishable from a writer that failed;
      * a SHOWN candidate carrying a drop reason -- two contradictory facts in one row.
    `card_kind` is checked against the five of (c) for the same reason R-IV.925(b) gives: an
    invented label is worse than a refusal, because it will be grouped by.
    """
    kind = str(card_kind or "").strip().upper()
    if kind not in CARD_KINDS:
        raise ValueError("card_kind %r is not one of %s" % (card_kind, CARD_KINDS))
    if shown and drop_reason:
        raise ValueError("a shown card cannot carry a drop reason: %r" % drop_reason)
    if not shown and not drop_reason:
        raise ValueError("a dropped candidate must say why; a bare NULL reads as a failed write")
    if iv_band is not None:
        from models.notables_strip import IV_LABELS

        if iv_band not in IV_LABELS:
            raise ValueError("iv_band %r is not one of %s (R-IV.1265(c))" % (iv_band, IV_LABELS))
    return {
        "session_date": session_date,
        "detected_at": detected_at,
        "ticker": (ticker or None),
        "card_kind": kind,
        "shown": bool(shown),
        "drop_reason": drop_reason or None,
        "direction": direction,
        # Joined for storage and kept as a list by the caller: the log is read by a person, and
        # a JSONB array of three strings reads worse than three strings in a line.
        "reasons": (" · ".join(reasons) if reasons else None),
        "counter_evidence": (" · ".join(counter_evidence) if counter_evidence else None),
        "stale_if": stale_if,
        "inputs": (json.dumps(inputs, default=str) if inputs is not None else None),
        "rung_1x_mid": rung_1x_mid,
        "em_dollars": em_dollars,
        "expiry": expiry,
        "iv_rank": iv_rank,
        "iv_band": iv_band,
        "spread_pct": spread_pct,
        "strip_state": strip_state,
        "tap": None,
        "tapped_at": None,
        "supersedes": supersedes,
    }


_INSERT = """
INSERT INTO notables_log
    (session_date, detected_at, ticker, card_kind, shown, drop_reason, direction, reasons,
     counter_evidence, stale_if, inputs, rung_1x_mid, em_dollars, expiry, iv_rank, iv_band,
     spread_pct, strip_state, tap, tapped_at, supersedes)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, $14, $15, $16, $17, $18,
        $19, $20, $21)
RETURNING id
"""

_COLS = ("session_date", "detected_at", "ticker", "card_kind", "shown", "drop_reason",
         "direction", "reasons", "counter_evidence", "stale_if", "inputs", "rung_1x_mid",
         "em_dollars", "expiry", "iv_rank", "iv_band", "spread_pct", "strip_state", "tap",
         "tapped_at", "supersedes")


async def insert(conn, row: Dict[str, Any]) -> Optional[int]:
    """Append one row and return its id. Never raises into the caller's render path.

    A LOG THAT CANNOT WRITE MUST NOT BLANK THE SURFACE. The card is already decided by the time
    this runs; a failed append costs the record, not the display, and it is logged at WARNING so
    the loss is visible rather than silent.
    """
    try:
        return await conn.fetchval(_INSERT, *[row.get(c) for c in _COLS])
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[notables_log] append failed (%s): %s card for %s",
                       type(exc).__name__, row.get("card_kind"), row.get("ticker"))
        return None


async def record_tap(conn, log_id: int, tap: str) -> bool:
    """Record what Nick did with a card. The ONE field this table updates, and it is not history.

    `tap` is not a verdict and nothing gates on it (#42). It is also the only mutation allowed
    here: a tap is a fact about the READER, acquired after the row was written, and it cannot be
    expressed as a new row without duplicating a card that was shown once.
    """
    if tap not in TAPS:
        raise ValueError("tap %r is not one of %s" % (tap, TAPS))
    try:
        await conn.execute(
            "UPDATE notables_log SET tap = $2, tapped_at = NOW() WHERE id = $1", log_id, tap)
        return True
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[notables_log] tap not recorded (%s)", type(exc).__name__)
        return False


async def session_counts(conn, session_date: _dt.date) -> Dict[str, Any]:
    """Shown and dropped counts for a session, with the drops broken out by reason.

    THE DENOMINATOR, which is the whole reason the drops are logged. A surface that reported
    only "3 shown today" could not say whether 3 or 300 candidates were considered.
    """
    rows = await conn.fetch(
        "SELECT card_kind, shown, drop_reason, COUNT(*) AS n "
        "  FROM notables_log WHERE session_date = $1 "
        " GROUP BY card_kind, shown, drop_reason", session_date)
    shown = sum(int(r["n"]) for r in rows if r["shown"])
    dropped = sum(int(r["n"]) for r in rows if not r["shown"])
    by_reason: Dict[str, int] = {}
    for r in rows:
        if not r["shown"]:
            by_reason[r["drop_reason"] or "(none)"] = (
                by_reason.get(r["drop_reason"] or "(none)", 0) + int(r["n"]))
    return {"session_date": session_date.isoformat(), "shown": shown, "dropped": dropped,
            "candidates": shown + dropped, "dropped_by_reason": by_reason,
            "basis": ("notables_log for this session; every candidate is logged, shown or not, "
                      "so `candidates` is the denominator of what was displayed")}


def outcome_row(*, log_id: int, horizon_days: int, move_pct: Optional[float],
                em_pct: Optional[float], basis: str,
                unavailable_reason: Optional[str] = None) -> Dict[str, Any]:
    """One graded horizon, in EM units, with its denominator stored beside it.

    `move_in_em` IS DERIVED AND THE DENOMINATOR IS KEPT. A move of "1.4 EM" means nothing
    without the EM it was divided by, and a reader who has only the ratio cannot tell a big move
    in a quiet name from a small one in a volatile one. An EM of zero or None yields NULL with a
    reason, never a division.
    """
    if horizon_days not in HORIZONS:
        raise ValueError("horizon %r is not one of %s" % (horizon_days, HORIZONS))
    in_em = None
    reason = unavailable_reason
    if move_pct is None:
        reason = reason or "no close for this horizon yet"
    elif not em_pct:
        reason = reason or ("the expected move was zero or unavailable, so a move in EM units "
                            "cannot be computed")
    else:
        in_em = round(float(move_pct) / float(em_pct), 3)
    return {"log_id": int(log_id), "horizon_days": int(horizon_days),
            "move_pct": move_pct, "em_pct": em_pct, "move_in_em": in_em,
            "basis": basis, "unavailable_reason": reason}


_OUTCOME_INSERT = """
INSERT INTO notables_outcomes
    (log_id, horizon_days, graded_at, move_pct, em_pct, move_in_em, basis, unavailable_reason)
VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7)
ON CONFLICT (log_id, horizon_days) DO UPDATE
    SET graded_at = NOW(), move_pct = EXCLUDED.move_pct, em_pct = EXCLUDED.em_pct,
        move_in_em = EXCLUDED.move_in_em, basis = EXCLUDED.basis,
        unavailable_reason = EXCLUDED.unavailable_reason
RETURNING id
"""


async def record_outcome(conn, row: Dict[str, Any]) -> Optional[int]:
    """Upsert one graded horizon. Idempotent on (log_id, horizon_days).

    THE UPSERT IS DELIBERATE AND IS NOT THE LOG REWRITING ITSELF: an outcome is a MEASUREMENT of
    a later session, and re-running the grader on a corrected bar must correct the measurement.
    `notables_log` itself is still append-only -- the record of what was SHOWN never changes.
    """
    try:
        return await conn.fetchval(
            _OUTCOME_INSERT, row["log_id"], row["horizon_days"], row.get("move_pct"),
            row.get("em_pct"), row.get("move_in_em"), row.get("basis"),
            row.get("unavailable_reason"))
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[notables_outcomes] write failed (%s) for log %s +%sd",
                       type(exc).__name__, row.get("log_id"), row.get("horizon_days"))
        return None
