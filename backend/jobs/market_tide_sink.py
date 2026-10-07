"""`market_tide_history` — every market-tide reading UW returns, kept (R-IV.675(b)).

WHY THIS EXISTS. The principal's Triton gates its direction through confluence: flow AND dark
pool AND market tide. The forward window tests the sweep leg alone because tide and dark pool had
never persisted a row (2026-09-03 rescope, §3 Q1). Tide has been fetched every five minutes for
months and thrown away: `stable_jobs._warm_tide` took `series[-1]`, cached three scalars in Redis
under a 1,800 s TTL, and dropped the rest. Until it is saved, nothing the principal designed can
be tested.

WHAT UW SERVES, measured 2026-10-06 before this was written:

  * one call returns the WHOLE session series -- 81 rows, 09:30 -> 16:10 ET, at a single
    distinct interval of 300 s, no gaps;
  * fields `timestamp` (ET with offset), `date`, `net_call_premium`, `net_put_premium`,
    `net_volume`;
  * **the premiums arrive as STRINGS** (`"20650902.0000"`). They are stored NUMERIC. A float
    cast here would be a silent precision loss on money, and this is the only place the raw
    string is still available to cast from;
  * `?date=YYYY-MM-DD` serves PAST sessions, so a backfill is ONE CALL PER SESSION.

KEYED BY UW'S OWN TICK TIMESTAMP, never the hub's fetch time (R-IV.675(b)). Two fetches of the
same session must converge on the same rows, so the whole series is upserted on every call and
re-reading a session is idempotent. `fetched_at` rides along as provenance, not as identity --
a key built from it would make every poll a new row and the 5-minute cadence would mint 81
duplicates an hour.

COLLECTOR DESIGN LAW (2026-09-03 rescope §5), item by item:

  1. LIVENESS -- the writer runs under `stable_jobs._run_job("market_tide")`, so a dark
     collector shows as a flatlined job in `/health` rather than as an empty table nobody
     queried. Item 6 (cost at print time) does not apply: a tide tick is a market-wide
     aggregate, not a print, and carries no bid/ask of its own.
  3. FIELD LIVENESS is DECLARED here, not discovered later -- see `FIELD_LIVENESS`. A session
     that satisfies none of it HALTS the write with its reason rather than storing a shape
     nobody has agreed to.
  4. EVERY SKIP RECORDS ITS REASON, from the enumerated taxonomy in `SKIP`. An unenumerated
     condition is `SKIP_UNCLASSIFIED`, which is a defect to be named, not a catch-all to rest on.
  5. UNGRADEABLE-BY-CONSTRUCTION: a tide tick has no outcome to grade, so there is no
     gradeable subpopulation to monitor. Stated so the omission is deliberate.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── §5.4 · the skip taxonomy, enumerated at design time ────────────────────────────────────
SKIP_PAUSED = "paused: R-IV.273(c) tide spend pause is on"
SKIP_NO_PAYLOAD = "no payload: the vendor returned nothing"
SKIP_MALFORMED = "malformed: payload is not a list of readings"
SKIP_NO_ROWS = "no rows: the series came back empty"
SKIP_NO_USABLE_ROW = "no usable row: every reading lacked a parseable tick timestamp"
SKIP_UNCLASSIFIED = "unclassified: a condition this taxonomy does not name (defect)"

SKIP = (SKIP_PAUSED, SKIP_NO_PAYLOAD, SKIP_MALFORMED, SKIP_NO_ROWS,
        SKIP_NO_USABLE_ROW, SKIP_UNCLASSIFIED)

# ── §5.3 · field liveness, DECLARED ────────────────────────────────────────────────────────
# Measured on 2026-10-05 and 2026-10-06: 81 readings per complete session at a 300 s interval,
# every one carrying all three fields. A full session below the floor is a defect, not noise.
FIELD_LIVENESS: Dict[str, Any] = {
    "expected_interval_s": 300,
    "expected_rows_per_complete_session": 81,
    "min_rows_for_a_complete_session": 70,
    "fields": {
        # field -> the satisfaction rate a complete session must clear
        "net_call_premium": 0.95,
        "net_put_premium": 0.95,
        "net_volume": 0.95,
    },
    "measured_on": "2026-10-05 and 2026-10-06, 81/81 rows on both",
}


def _num(raw: Any) -> Optional[Decimal]:
    """A premium as the number it is. The vendor sends `"20650902.0000"`; `float()` on that is
    a lossy cast of money, and this is the last point the exact string exists."""
    if raw is None:
        return None
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None


def _int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(Decimal(str(raw).strip()))
    except (InvalidOperation, ValueError):
        return None


def parse_tick(row: Any) -> Optional[Dict[str, Any]]:
    """One reading -> a storable row, or None when it carries no usable tick timestamp.

    The timestamp is UW's, with its own offset (`2026-10-06T09:30:00-04:00`). It is converted
    to UTC for storage so one instant has one representation, and `session_date` is kept as UW
    sent it rather than re-derived from the instant -- re-deriving would put a 16:10 ET tick on
    the next UTC day.
    """
    if not isinstance(row, dict):
        return None
    raw_ts = row.get("timestamp")
    if raw_ts is None:
        return None
    try:
        ts = datetime.fromisoformat(str(raw_ts).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)

    sess = row.get("date")
    try:
        session_date = date.fromisoformat(str(sess)[:10]) if sess else None
    except ValueError:
        session_date = None

    return {
        "tick_at": ts,
        "session_date": session_date,
        "net_call_premium": _num(row.get("net_call_premium")),
        "net_put_premium": _num(row.get("net_put_premium")),
        "net_volume": _int(row.get("net_volume")),
    }


def series_of(payload: Any) -> Tuple[Optional[List[Any]], Optional[str]]:
    """(rows, skip_reason). The vendor wraps the series in `data` on some routes and not others."""
    if payload is None:
        return None, SKIP_NO_PAYLOAD
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if rows is None and isinstance(payload, dict):
        rows = payload.get("market_tide")
    if not isinstance(rows, list):
        return None, SKIP_MALFORMED
    if not rows:
        return None, SKIP_NO_ROWS
    return rows, None


def liveness_report(ticks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """§5.3. What this series actually satisfies, against what was declared.

    `complete` is NOT a claim that the session is over -- a mid-session read is short by
    construction. It says whether this read covers a whole session, so a reader can tell a
    partial poll from a session the vendor served badly.
    """
    n = len(ticks)
    out: Dict[str, Any] = {"rows": n, "complete": n >= FIELD_LIVENESS[
        "min_rows_for_a_complete_session"], "fields": {}, "below_floor": []}
    for field, floor in FIELD_LIVENESS["fields"].items():
        present = sum(1 for t in ticks if t.get(field) is not None)
        rate = (present / n) if n else 0.0
        out["fields"][field] = {"present": present, "rate": round(rate, 4), "floor": floor}
        if out["complete"] and rate < floor:
            out["below_floor"].append(field)
    intervals = sorted({int((b["tick_at"] - a["tick_at"]).total_seconds())
                        for a, b in zip(ticks, ticks[1:])}) if n >= 2 else []
    out["distinct_intervals_s"] = intervals[:8]
    out["interval_as_declared"] = (intervals == [FIELD_LIVENESS["expected_interval_s"]]
                                   if intervals else None)
    return out


UPSERT = """
INSERT INTO market_tide_history
       (tick_at, session_date, net_call_premium, net_put_premium, net_volume, fetched_at, source)
VALUES ($1, $2, $3, $4, $5, NOW(), $6)
ON CONFLICT (tick_at) DO UPDATE SET
       session_date     = EXCLUDED.session_date,
       net_call_premium = EXCLUDED.net_call_premium,
       net_put_premium  = EXCLUDED.net_put_premium,
       net_volume       = EXCLUDED.net_volume,
       fetched_at       = NOW(),
       source           = EXCLUDED.source
"""


async def persist_series(conn, payload: Any, *, source: str) -> Dict[str, Any]:
    """Upsert every reading in `payload`. Returns a result that always names what happened.

    `source` is REQUIRED keyword-only: a row that cannot say whether it came from the live
    5-minute warmer or from a dated backfill cannot be audited, and a default here would let a
    caller inherit the other one's answer by silence.
    """
    rows, skip = series_of(payload)
    if skip:
        return {"written": 0, "skipped": True, "skip_reason": skip, "rows_touched": 0}

    ticks = [t for t in (parse_tick(r) for r in rows) if t]
    if not ticks:
        return {"written": 0, "skipped": True, "skip_reason": SKIP_NO_USABLE_ROW,
                "rows_touched": 0, "offered": len(rows)}

    ticks.sort(key=lambda t: t["tick_at"])
    live = liveness_report(ticks)

    # §5.3 HALT on a declared-field mismatch -- but only for a series long enough for the rate
    # to mean anything. Halting on a 2-row mid-session poll would make the floor unsatisfiable
    # by construction, which is the defect the law is written against, not an application of it.
    if live["below_floor"]:
        return {"written": 0, "skipped": True, "rows_touched": 0,
                "skip_reason": "HALT: declared field liveness not met for %s"
                               % ", ".join(live["below_floor"]),
                "liveness": live}

    written = 0
    for t in ticks:
        await conn.execute(UPSERT, t["tick_at"], t["session_date"], t["net_call_premium"],
                           t["net_put_premium"], t["net_volume"], source)
        written += 1

    return {"written": written, "skipped": False, "skip_reason": None,
            "rows_touched": written, "liveness": live,
            "span": [ticks[0]["tick_at"].isoformat(), ticks[-1]["tick_at"].isoformat()],
            "sessions": sorted({str(t["session_date"]) for t in ticks if t["session_date"]})}
