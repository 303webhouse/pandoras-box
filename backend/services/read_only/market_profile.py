"""Read-only Market Profile accessor — backs the hub_get_market_profile MCP tool (B4 Chunk A).

Reads the latest `pythia_events` row for a ticker. pythia_events is an event log
(one row per PYTHIA Pine alert); the latest row carries the current session's
levels in its columns + raw_payload.

Session-based staleness (B4 Q-A1 resolution):
  - "ok"          : latest event is from the CURRENT session
  - "stale"       : latest event is from a PRIOR session (data still returned,
                    with session_date + event_age_seconds so the caller sees how old)
  - "unavailable" : no row for the ticker

Field locations (verified 2026-06-09 against a live SPY row — Q-A2):
  - vah/val/poc, ib_high/ib_low, va_migration, poor_high/poor_low,
    volume_quality, interpretation, price, alert_type, timestamp → COLUMNS
  - prev_poc/prev_vah/prev_val → ONLY in raw_payload (jsonb), not columns

AEGIS (B4 amendment 2): this layer selects explicit fields only and NEVER
returns raw_payload verbatim. single_prints / day_type are not computed by
Pine v2.3 → always None (never fabricated — GEX lesson).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytz

logger = logging.getLogger(__name__)

_ET = pytz.timezone("America/New_York")


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _num_or_none(v: Any) -> Optional[float]:
    """Float, but 0/0.0 → None. Pine v2.4 serializes missing levels as nz(x,0);
    a confident zero is not data (B4 amendment — never surface fake levels)."""
    f = _safe_float(v)
    return f if (f is not None and f != 0) else None


def _prev_weekday(d: date) -> date:
    """Most recent weekday strictly before d (skips Sat/Sun). Holidays not handled."""
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5:  # Mon=0 … Fri=4, Sat=5, Sun=6
        cur -= timedelta(days=1)
    return cur


def _current_session_date(now_et: datetime) -> date:
    """The trading date whose RTH session is current/most-recent as of now_et.

    Weekday at/after 09:30 ET → today (developing session).
    Weekday before 09:30 ET, or weekend → the last completed weekday session.
    Holiday calendar not modeled (approximation; acceptable — a holiday just
    means the "current" session label may lead by one day, which surfaces as
    'stale', the safe direction).
    """
    d = now_et.date()
    after_open = (now_et.hour, now_et.minute) >= (9, 30)
    if now_et.weekday() < 5 and after_open:
        return d
    return _prev_weekday(d) if now_et.weekday() >= 5 or not after_open else d


async def get_market_profile(ticker: str) -> Optional[Dict[str, Any]]:
    """Return the latest MP snapshot for a ticker, or None if no row exists.

    Returns a dict {status, data, staleness_seconds} for the tool layer to wrap.
    None signals 'unavailable' (no row) to the caller.
    """
    tkr = (ticker or "").upper().strip()
    if not tkr:
        return None

    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ticker, alert_type, price, direction, vah, val, poc,
                   ib_high, ib_low, va_migration, poor_high, poor_low,
                   volume_quality, interpretation, raw_payload, timestamp
            FROM pythia_events
            WHERE ticker = $1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            tkr,
        )

    if row is None:
        return None  # caller → status="unavailable"

    rp = row["raw_payload"] or {}
    if isinstance(rp, str):
        try:
            rp = json.loads(rp)
        except (ValueError, TypeError):
            rp = {}

    ts = row["timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(_ET)
    event_session = ts.astimezone(_ET).date()
    current_session = _current_session_date(now_et)

    status = "ok" if event_session >= current_session else "stale"
    age_seconds = int((now_utc - ts).total_seconds())

    data = {
        "ticker": tkr,
        "poc": _safe_float(row["poc"]),
        "vah": _safe_float(row["vah"]),
        "val": _safe_float(row["val"]),
        # prev_* live in raw_payload only (Q-A2 verified). 0.0 → None (nz-zero scrub).
        "prev_poc": _num_or_none(rp.get("prev_poc")),
        "prev_vah": _num_or_none(rp.get("prev_vah")),
        "prev_val": _num_or_none(rp.get("prev_val")),
        "ib_high": _num_or_none(row["ib_high"]),
        "ib_low": _num_or_none(row["ib_low"]),
        "poor_high": bool(row["poor_high"]) if row["poor_high"] is not None else None,
        "poor_low": bool(row["poor_low"]) if row["poor_low"] is not None else None,
        "va_migration": row["va_migration"],
        "volume_quality": row["volume_quality"],
        "last_event": row["alert_type"],
        "interpretation": row["interpretation"],
        "price_at_event": _safe_float(row["price"]),
        "session_date": event_session.isoformat(),
        "as_of": ts.astimezone(timezone.utc).isoformat(),
        "event_age_seconds": age_seconds,
        "source": "pythia_webhook_v2.3",
        # Not computed by Pine v2.3 — explicit null, never fabricated
        "single_prints": None,
        "day_type": None,
        "note": "single_prints and day_type are not computed by Pine v2.3",
    }

    return {"status": status, "data": data, "staleness_seconds": age_seconds}
