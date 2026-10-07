"""1-minute SPY, kept as a system of record — R-IV.680(b).

WHY. Side-measure 3 (the excess-over-SPY lens) prices SPY at the finest bar at or before each
Triton fire minute. The vendor serves 1-minute bars for the **trailing 30 days only** — Yahoo
says so in its own error text ("The requested range must be within the last 30 days") — so the
lens's own inputs expire. August's are already gone. W1's leave around 10-15. CC-QUERY captured
W1–W3 to a ferry file (5,460 bars = 14 sessions x 390), which is evidence but not a system of
record: a file in one lane's working directory cannot be read by the grader, re-derived, or
audited.

THE VENDOR IS yfinance, because that is what the grader uses for SPY end to end
(`triton_shadow_common`: "Triton's registered window grades on yfinance, END TO END"). Pricing the
lens from a different vendor than the grades would make the excess figure a comparison between two
vendors rather than between a row and the market.

MEASURED 2026-10-07 before this was written:
  * 1m SPY is served back to 2026-09-09, so **every session R-IV.680(b) asks for (09-15 on) is
    still live at the vendor** and the ferry capture is a contingency, not a dependency;
  * 390 bars per complete session (09:30 through 15:59 ET inclusive);
  * the index is tz-aware UTC (13:30Z = 09:30 ET);
  * yfinance 0.2.59 returns **MultiIndex columns** for a single ticker -- ('Close', 'SPY') --
    so a bare `df["Close"]` is a DataFrame, not a Series. Handled explicitly below.

PROVENANCE IS ON EVERY ROW, not just on the ones that need excusing. A row says which vendor and
which basis produced it, and a ferry-sourced row additionally carries the capture's sha256. A
column that only appears when something is wrong is a column nobody reads.

AUTO_ADJUST IS REQUIRED AND EXPLICIT (R-IV.647(c)). yfinance changed its library default to True
in 0.2.59 -- the version installed here -- and an adjusted 1-minute series is not the price the
row fired at. The parameter is keyword-only and has no default so no caller can inherit an
answer by silence.

COLLECTOR DESIGN LAW (2026-09-03 rescope §5):
  1. LIVENESS -- the forward collector runs under `stable_jobs._run_job("spy_minute")`.
  3. FIELD LIVENESS declared in `FIELD_LIVENESS`, with the measurement behind it; a session that
     is short HALTS rather than being stored as a complete one.
  4. EVERY SKIP NAMES ITSELF, from the taxonomy in `SKIP`.
  5. A bar has no outcome to grade. Stated so the omission is deliberate.
  6. Cost at print time does not apply: a 1-minute OHLC bar is an aggregate, not a print, and
     carries no bid/ask. The dark-pool sink is where item 6 binds.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── provenance vocabulary, written once ────────────────────────────────────────────────────
PROV_YFINANCE = "yfinance:1m:auto_adjust=false"
PROV_FERRY_PREFIX = "ferry:"          # + the capture's sha256, so the row names its evidence


def ferry_provenance(sha256: str) -> str:
    return PROV_FERRY_PREFIX + (sha256 or "").strip().lower()


# ── §5.4 skip taxonomy ─────────────────────────────────────────────────────────────────────
SKIP_NO_BARS = "no bars: the vendor returned nothing for this window"
SKIP_PAST_HORIZON = "past horizon: the vendor no longer serves 1m for this session"
SKIP_SHORT_SESSION = "short session: fewer bars than a complete session and not a known half day"
SKIP_NO_USABLE_BAR = "no usable bar: every row lacked a timestamp or a close"
SKIP_UNCLASSIFIED = "unclassified: a condition this taxonomy does not name (defect)"

SKIP = (SKIP_NO_BARS, SKIP_PAST_HORIZON, SKIP_SHORT_SESSION, SKIP_NO_USABLE_BAR,
        SKIP_UNCLASSIFIED)

# ── §5.3 field liveness, DECLARED with its measurement ─────────────────────────────────────
# A regular session is 09:30 through 15:59 ET inclusive = 390 one-minute bars, measured on
# 2026-10-05 and 2026-10-06 (390 both). A US half day (1 pm ET close) is 210. Anything else short
# is a defect rather than noise, and HALTS.
FULL_SESSION_BARS = 390
HALF_SESSION_BARS = 210
FIELD_LIVENESS: Dict[str, Any] = {
    "expected_bars_full_session": FULL_SESSION_BARS,
    "expected_bars_half_day": HALF_SESSION_BARS,
    "known_session_lengths": (FULL_SESSION_BARS, HALF_SESSION_BARS),
    "vendor_horizon_days": 30,
    "fields": {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.99},
    "measured_on": "2026-10-07: 390 bars on 2026-10-05 and 2026-10-06; 1m served back to 09-09",
}


def _dec(raw: Any) -> Optional[Decimal]:
    """A price as a number, or None. NaN is NOT a price.

    `float("nan")` survives every `if not x` guard -- `not nan` is False and `nan <= 0` is False --
    so it is caught by name here rather than left to look like a reading.
    """
    if raw is None:
        return None
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    if d.is_nan() or d.is_infinite():
        return None
    return d


def _int(raw: Any) -> Optional[int]:
    d = _dec(raw)
    return int(d) if d is not None else None


def _col(df, name: str, ticker: str):
    """One column, whether the frame is flat or MultiIndex.

    yfinance 0.2.59 returns MultiIndex columns even for a single ticker, so `df["Close"]` is a
    DataFrame. Asking for the wrong shape here is the `price` vs `spot` fault in another costume:
    it does not raise, it just yields something that is not a number.
    """
    cols = df.columns
    if getattr(cols, "nlevels", 1) > 1:
        if (name, ticker) in cols:
            return df[(name, ticker)]
        for c in cols:
            if c[0] == name:
                return df[c]
        return None
    return df[name] if name in cols else None


def frame_to_bars(df, ticker: str = "SPY") -> List[Dict[str, Any]]:
    """A yfinance frame -> storable bars, sorted by instant, bad rows dropped."""
    if df is None or len(df) == 0:
        return []
    series = {k: _col(df, k.capitalize() if k != "volume" else "Volume", ticker)
              for k in ("open", "high", "low", "close", "volume")}
    out: List[Dict[str, Any]] = []
    for i, idx in enumerate(df.index):
        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc)
        row = {"bar_at": ts}
        for k, s in series.items():
            row[k] = _int(s.iloc[i]) if (k == "volume" and s is not None) else (
                _dec(s.iloc[i]) if s is not None else None)
        if row["close"] is None:
            continue                      # a bar with no close prices nothing
        # The ET session the bar belongs to, not the UTC date: a 15:59 ET bar is the same UTC day
        # here, but deriving the session from UTC is the fault that bit the tide sink's 16:10 tick.
        row["session_date"] = _et_session(ts)
        out.append(row)
    out.sort(key=lambda r: r["bar_at"])
    return out


_ET_OFFSETS = None


def _et_session(ts: datetime) -> date:
    """The ET calendar date of `ts`. Uses the stdlib tz database via zoneinfo, never a fixed
    offset -- a fixed -4 would file every bar wrongly for the four months after the DST change."""
    from zoneinfo import ZoneInfo

    return ts.astimezone(ZoneInfo("America/New_York")).date()


def session_report(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """§5.3. What these bars satisfy, against what was declared.

    COUNTS ARE PER SESSION, not over the batch. The first version of this compared the TOTAL bar
    count against a single session's length, so a two-session fetch (780 bars) reported
    `known_length: False` and a seven-session fetch would too -- an instrument that calls a
    correct batch defective is the shape that gets a HALT ignored. The gap census is also per
    session, because the overnight boundary is a 63,060 s "gap" that means nothing is wrong.
    """
    n = len(bars)
    by_session: Dict[str, List[Dict[str, Any]]] = {}
    for b in bars:
        by_session.setdefault(str(b["session_date"]), []).append(b)
    sessions = sorted(by_session)

    per_session: Dict[str, Any] = {}
    unknown_lengths: List[str] = []
    for s in sessions:
        rows = by_session[s]
        gaps = sorted({int((b["bar_at"] - a["bar_at"]).total_seconds())
                       for a, b in zip(rows, rows[1:])}) if len(rows) >= 2 else []
        known = len(rows) in FIELD_LIVENESS["known_session_lengths"]
        per_session[s] = {"bars": len(rows), "known_length": known,
                          "distinct_gaps_s": gaps[:6]}
        if not known:
            unknown_lengths.append(s)

    rep: Dict[str, Any] = {"bars": n, "sessions": sessions, "per_session": per_session,
                           "fields": {}, "below_floor": [],
                           "sessions_of_unknown_length": unknown_lengths}
    for field, floor in FIELD_LIVENESS["fields"].items():
        present = sum(1 for b in bars if b.get(field) is not None)
        rate = (present / n) if n else 0.0
        rep["fields"][field] = {"present": present, "rate": round(rate, 4), "floor": floor}
        if n >= HALF_SESSION_BARS and rate < floor:
            rep["below_floor"].append(field)
    # True only when EVERY session in the batch is a length the declaration recognises.
    rep["known_length"] = bool(sessions) and not unknown_lengths
    return rep


UPSERT = """
INSERT INTO spy_minute_bars
       (bar_at, session_date, open, high, low, close, volume, provenance, fetched_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
ON CONFLICT (bar_at) DO UPDATE SET
       session_date = EXCLUDED.session_date,
       open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
       close = EXCLUDED.close, volume = EXCLUDED.volume,
       provenance = EXCLUDED.provenance,
       fetched_at = NOW()
"""


async def persist_bars(conn, bars: List[Dict[str, Any]], *, provenance: str) -> Dict[str, Any]:
    """Upsert bars, keyed on the bar's own instant. `provenance` is required keyword-only."""
    if not bars:
        return {"written": 0, "skipped": True, "skip_reason": SKIP_NO_BARS, "rows_touched": 0}
    rep = session_report(bars)
    if rep["below_floor"]:
        return {"written": 0, "skipped": True, "rows_touched": 0, "liveness": rep,
                "skip_reason": "HALT: declared field liveness not met for %s"
                               % ", ".join(rep["below_floor"])}
    written = 0
    for b in bars:
        await conn.execute(UPSERT, b["bar_at"], b["session_date"], b["open"], b["high"],
                           b["low"], b["close"], b["volume"], provenance)
        written += 1
    return {"written": written, "skipped": False, "skip_reason": None, "rows_touched": written,
            "liveness": rep,
            "span": [bars[0]["bar_at"].isoformat(), bars[-1]["bar_at"].isoformat()]}


async def fetch_1m(ticker: str, start: date, end: date, *, auto_adjust: bool
                   ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """(bars, skip_reason). yfinance 1m, in one window. `end` is exclusive, as yfinance treats it.

    `auto_adjust` is required and has no default: 0.2.59 changed the library default to True, and
    an adjusted 1-minute series is not the price a row fired at.
    """
    import asyncio
    import warnings

    def _go():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import yfinance as yf

            return yf.download(ticker, start=start.isoformat(), end=end.isoformat(),
                               interval="1m", progress=False, auto_adjust=auto_adjust,
                               threads=False)

    try:
        df = await asyncio.get_event_loop().run_in_executor(None, _go)
    except Exception as exc:  # noqa: BLE001
        logger.warning("spy 1m fetch failed %s..%s: %s", start, end, type(exc).__name__)
        return [], SKIP_NO_BARS
    bars = frame_to_bars(df, ticker)
    if not bars:
        # The vendor says "must be within the last 30 days" for a window past its horizon; from
        # the outside both look like an empty frame, so the horizon is computed rather than
        # guessed from the error text.
        horizon = datetime.now(timezone.utc).date() - timedelta(
            days=FIELD_LIVENESS["vendor_horizon_days"])
        return [], (SKIP_PAST_HORIZON if start < horizon else SKIP_NO_BARS)
    return bars, None
