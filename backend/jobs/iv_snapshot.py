"""Daily ATM implied-volatility snapshot (R-IV.866(b)).

WHY. Stage 2 for the registered forward tests (nemesis-long-v1, phoenix-washout-v1) needs the IV at
each fire, and `signals` carries none (`iv_at_fire` exists only on triton_flow_shadow). The
registered files are frozen by their hashes, so the IV is captured HERE, separately, by ticker
and session, and a forward row joins to it on (ticker, session_date). The same rows serve X4's
input -- the ATM IV of a position's own expiry -- through `atm_iv()`.

WHAT. After each close, for the 196 names of the registered universe plus the underlyings of open
positions (capped at the caller's 250/day), one UW call per ticker:
`/api/stock/{ticker}/volatility/term-structure?date=<session>` -- the average of the at-the-money
call and put IV for EVERY expiry. Stored:
  * iv_near   -- ATM IV of the nearest expiry with dte >= 1 (an expiry expiring today is spent);
  * iv_30d    -- ATM IV at 30 days, interpolated in total variance (sigma^2 * t) between the two
                 expiries that bracket 30; NULL with a reason when 30 is not bracketed (never
                 extrapolated);
  * the whole term structure as received, so any expiry's ATM IV can be read later.

WHEN. 16:45 ET on trading days; it also catches up on up to five recent sessions it has not
completed (the endpoint takes a past date). A governor refusal stops the pass as an ERROR, so
the session is retried.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

JOB_NAME = "iv_snapshot"
CALLER = "iv_snapshot"
DAILY_CAP = 250                       # R-IV.866(b); BUILD sets the governor quota
CATCH_UP_SESSIONS = 5
RUN_AFTER = time(16, 45)
TARGET_DTE = 30
PROVIDER = "uw"
_SYMBOL = re.compile(r"^[A-Z]{1,5}$")

DDL = """CREATE TABLE IF NOT EXISTS iv_snapshots (
    ticker TEXT NOT NULL,
    session_date DATE NOT NULL,
    near_expiry DATE,
    near_dte INT,
    iv_near NUMERIC(10,6),
    iv_30d NUMERIC(10,6),
    iv_30d_method TEXT NOT NULL,
    term_structure JSONB NOT NULL,
    provider TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, session_date)
)"""
UPSERT = """
    INSERT INTO iv_snapshots (ticker, session_date, near_expiry, near_dte, iv_near, iv_30d,
                              iv_30d_method, term_structure, provider, fetched_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, NOW())
    ON CONFLICT (ticker, session_date) DO UPDATE SET
        near_expiry = EXCLUDED.near_expiry, near_dte = EXCLUDED.near_dte,
        iv_near = EXCLUDED.iv_near, iv_30d = EXCLUDED.iv_30d,
        iv_30d_method = EXCLUDED.iv_30d_method, term_structure = EXCLUDED.term_structure,
        provider = EXCLUDED.provider, fetched_at = NOW()
"""
OPEN_UNDERLYINGS = "SELECT DISTINCT UPPER(ticker) AS ticker FROM unified_positions WHERE status = 'OPEN'"
READ_ONE = "SELECT term_structure FROM iv_snapshots WHERE ticker = $1 AND session_date = $2"


# ── pure ──────────────────────────────────────────────────────────────────────────────────
def _num(raw: Any) -> Optional[float]:
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def summarize(rows: List[dict], session: date) -> Dict[str, Any]:
    """Nearest live expiry and the 30-day ATM IV from one term structure (pure)."""
    live: List[Tuple[int, date, float]] = []
    for r in rows or []:
        if not isinstance(r, dict) or str(r.get("date") or "")[:10] != session.isoformat():
            continue                                    # another session's row is not this one
        dte, vol = r.get("dte"), _num(r.get("volatility"))
        try:
            dte = int(dte)
            exp = date.fromisoformat(str(r.get("expiry"))[:10])
        except (TypeError, ValueError):
            continue
        if dte >= 1 and vol is not None:
            live.append((dte, exp, vol))
    live.sort()
    out: Dict[str, Any] = {"near_expiry": None, "near_dte": None, "iv_near": None,
                           "iv_30d": None, "iv_30d_method": "no_live_expiry"}
    if not live:
        return out
    out.update(near_dte=live[0][0], near_expiry=live[0][1], iv_near=round(live[0][2], 6))
    exact = [v for d, _, v in live if d == TARGET_DTE]
    if exact:
        out.update(iv_30d=round(exact[0], 6), iv_30d_method="exact")
        return out
    below = [x for x in live if x[0] < TARGET_DTE]
    above = [x for x in live if x[0] > TARGET_DTE]
    if not below or not above:
        out["iv_30d_method"] = "not_bracketed"
        return out
    (t1, _, v1), (t2, _, v2) = below[-1], above[0]
    w = (TARGET_DTE - t1) / (t2 - t1)
    var30 = v1 * v1 * t1 + w * (v2 * v2 * t2 - v1 * v1 * t1)   # total variance, linear in t
    out.update(iv_30d=round(math.sqrt(var30 / TARGET_DTE), 6), iv_30d_method="interpolated")
    return out


def iv_for_expiry(term_structure: Any, expiry: date) -> Optional[float]:
    """ATM IV of one expiry from a stored term structure (X4's input). None if absent."""
    body = json.loads(term_structure) if isinstance(term_structure, str) else term_structure
    for r in (body or {}).get("data", []) if isinstance(body, dict) else []:
        if str(r.get("expiry"))[:10] == expiry.isoformat():
            return _num(r.get("volatility"))
    return None


# ── I/O ───────────────────────────────────────────────────────────────────────────────────
async def universe(conn) -> List[str]:
    """The registered universe first, then open-position underlyings not already in it."""
    from strategies.registered_shadow import UNIVERSE
    out = list(UNIVERSE)
    try:
        rows = await conn.fetch(OPEN_UNDERLYINGS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[iv_snapshot] open underlyings unreadable: %s", exc)
        rows = []
    for r in rows:
        t = (r["ticker"] or "").strip().upper()
        if _SYMBOL.match(t) and t not in out:
            out.append(t)
    return out[:DAILY_CAP]


Fetch = Callable[[str, str], Awaitable[Any]]


async def snapshot_session(conn, session: date, fetch: Fetch) -> Dict[str, Any]:
    from integrations.uw_governor import UWUnavailable

    await conn.execute(DDL)
    tickers = await universe(conn)
    written, empty, failed = 0, 0, 0
    for t in tickers:
        body = await fetch(t, session.isoformat())
        if isinstance(body, UWUnavailable):
            raise RuntimeError("iv_snapshot %s: vendor refused at %s (%s) after %d written"
                               % (session, t, getattr(body, "reason", "?"), written))
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            failed += 1
            continue
        s = summarize(data, session)
        if s["iv_near"] is None:
            empty += 1
        await conn.execute(UPSERT, t, session, s["near_expiry"], s["near_dte"], s["iv_near"],
                           s["iv_30d"], s["iv_30d_method"], json.dumps(body), PROVIDER)
        written += 1
    return {"session": session.isoformat(), "tickers": len(tickers), "rows_touched": written,
            "no_live_iv": empty, "failed": failed}


def sessions_to_run(now_et: datetime) -> List[date]:
    """NEWEST FIRST: tonight's session is always the first spent; older ones only as budget
    allows. Never before the registrations' first forward session (nothing joins to it)."""
    from stable_engine.market_calendar import is_trading_day, previous_trading_day
    from strategies.registered_shadow import REGISTERED_FROM
    today = now_et.date()
    newest = today if (is_trading_day(today) and now_et.time() >= RUN_AFTER) else previous_trading_day(today)
    out, d = [], newest
    while len(out) < CATCH_UP_SESSIONS and d >= REGISTERED_FROM:
        out.append(d)
        d = previous_trading_day(d)
    return out


async def run(now: Optional[datetime] = None, fetch: Optional[Fetch] = None) -> Dict[str, Any]:
    from database.postgres_client import get_postgres_client
    from jobs.job_runs import has_completed
    from jobs.stable_jobs import _record
    from strategies.registered_shadow import UNIVERSE

    floor = len(UNIVERSE)                       # the least a session's pass costs
    if fetch is None:
        from integrations.uw_api import get_iv_term_structure as fetch
    now_et = (now or datetime.now(ET)).astimezone(ET)
    done, calls = [], 0
    for session in sessions_to_run(now_et):
        if await has_completed(JOB_NAME, session) is True:
            continue
        if calls + floor > DAILY_CAP:
            done.append({"session": session.isoformat(), "deferred": "daily cap"})
            continue

        async def _one(session=session):
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                res = await snapshot_session(conn, session, fetch)
            if res["rows_touched"] == 0:
                raise RuntimeError("iv_snapshot %s: nothing written (%s)" % (session, res))
            return res

        out = await _record(JOB_NAME, _one, session_date=session)
        calls += out["tickers"] if out else floor
        done.append(out or {"session": session.isoformat(), "failed": True})
    return {"sessions": done}


async def atm_iv(ticker: str, session: date, expiry: date) -> Optional[float]:
    """X4's read: the ATM IV of `expiry` as of `session` for `ticker`, or None."""
    from database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        ts = await conn.fetchval(READ_ONE, ticker.upper(), session)
    return iv_for_expiry(ts, expiry) if ts is not None else None
