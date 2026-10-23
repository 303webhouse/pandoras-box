"""The designated settled-close series: Polygon daily aggregates, for the regime classifier.

R-IV.1203(b). Polygon is the designated source because it is the one that matched on 2026-10-16
(SPY 763.25, QQQ 709.80, IWM 270.44) where `stable_daily_bars` did not.

THE BASIS, as ruled: SPLIT-ADJUSTED AND NOT DIVIDEND-ADJUSTED. Polygon's `adjusted=true` means
split-adjusted only -- it does not adjust for dividends -- so `adjusted=true` IS the ruled basis
and no second flag is needed. Measured on 2026-10-16: adjusted true and false returned identical
closes on all three (no split in the window), so the two agree today and the flag is set for
what it will mean across the next one.

THE SESSION DATE IS READ IN UTC, EXPLICITLY. Polygon stamps a daily aggregate at UTC midnight,
and `datetime.fromtimestamp(ms/1000)` converts through the LOCAL zone -- so on a UTC-6 machine
every bar comes back labelled one session EARLY. That is not hypothetical: the first probe for
this ruling reported the 763.25 close as 2026-10-15, and it is Convention #39's finding (a
UTC-midnight stamp misread by a session) reproduced in a fresh place. Every conversion here goes
through `_session_date`.

THE ENTITLEMENT EDGE, measured 2026-10-17: 501 sessions, 2024-10-17 to 2026-10-16. The current
session is withheld. That is ~2 years, which is this plan's documented edge, and it gives the
seed a depth of 302 after the 200-day warm-up.

THE RATE LIMIT IS REAL. The first probe hit HTTP 429 after about a dozen calls in quick
succession. A backfill is three calls (one range per ticker) and a nightly is three, so the
spacing here is generous rather than tight.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("bars_polygon")

#: The name this source records itself under, in `regime_daily_bars.close_source` and in
#: `regime_snapshots.close_source`. One string, so a reader of either table can tell which
#: series produced a row.
SOURCE = "polygon"

#: Seconds between calls. The plan's limit is 5 a minute; a backfill needs three.
CALL_GAP_S = 13.0

#: How far back `capture_session`'s range starts from the session it wants. A week covers a
#: holiday weekend, and only the bar for the requested session is ever used -- the window exists
#: so the request is a RANGE rather than a single session, which is what the plan refuses.
RANGE_LOOKBACK_DAYS = 7

#: What the plan says when it withholds a session. Matched on the BODY, not only the status:
#: a 403 can also mean a bad key, and reporting "the session is not released yet" for a dead
#: credential would send the next reader looking at the calendar instead of the key.
NOT_AUTHORIZED = "NOT_AUTHORIZED"

#: How far a Polygon close may sit from the UW chart close and still be called the same number.
#: Half a cent: these are 2-decimal quotes, so anything beyond rounding is a real disagreement.
CLOSE_TOLERANCE = 0.005

API = "https://api.polygon.io/v2/aggs/ticker"


class PolygonUnavailable(RuntimeError):
    """Polygon would not answer. Never a reason to substitute another source (R-IV.1198(d))."""


def _key() -> str:
    k = os.getenv("POLYGON_API_KEY") or ""
    if not k:
        raise PolygonUnavailable("POLYGON_API_KEY is missing")
    return k


def _session_date(ms: int) -> _dt.date:
    """The session a daily aggregate belongs to. UTC, EXPLICITLY -- see the module docstring."""
    return _dt.datetime.fromtimestamp(ms / 1000.0, tz=_dt.timezone.utc).date()


def _get(url: str, timeout: int = 45) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_sync(ticker: str, start: str, end: str) -> List[Dict[str, Any]]:
    """Daily aggregates for `ticker` over [start, end], oldest-first.

    The URL carries the key and is never logged. A 429 is retried once after a wait; anything
    else is raised as PolygonUnavailable so the caller can decline rather than guess.
    """
    qs = urllib.parse.urlencode({
        "adjusted": "true",          # split-adjusted, dividend-UNadjusted: the ruled basis
        "sort": "asc",
        "limit": 50000,
        "apiKey": _key(),
    })
    url = "%s/%s/range/1/day/%s/%s?%s" % (API, ticker, start, end, qs)
    for attempt in (1, 2):
        try:
            body = _get(url)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                logger.warning("[bars_polygon] 429 for %s, waiting", ticker)
                import time
                time.sleep(CALL_GAP_S * 2)
                continue
            # THE 403 CARRIES ITS OWN REASON, and the two it can mean are days apart in what
            # they ask of a reader: an entitlement edge ("this session is not yours yet") and a
            # dead credential. The body says which, so it is read rather than inferred from the
            # status -- "SPY: HTTP 403" is what the nightly audited for two nights, and it sent
            # the diagnosis towards the v2 cut-over instead of towards the plan.
            detail = ""
            try:
                body_txt = (e.read() or b"").decode("utf-8", "replace")
                if NOT_AUTHORIZED in body_txt:
                    detail = (" NOT_AUTHORIZED -- this plan withholds the data for that window; "
                              "for a daily bar that usually means the session is still current")
                elif body_txt:
                    detail = " " + body_txt[:120]
            except Exception:                                    # noqa: BLE001
                pass
            raise PolygonUnavailable("%s: HTTP %s%s" % (ticker, e.code, detail))
        except Exception as e:                                   # noqa: BLE001
            raise PolygonUnavailable("%s: %s" % (ticker, type(e).__name__))
    else:
        raise PolygonUnavailable("%s: retries exhausted" % ticker)

    out = []
    for r in body.get("results") or []:
        try:
            out.append({
                "date": _session_date(r["t"]),
                "o": float(r["o"]), "h": float(r["h"]),
                "l": float(r["l"]), "c": float(r["c"]),
                "v": int(float(r.get("v") or 0)),
            })
        except (KeyError, TypeError, ValueError):
            # A malformed bar is DROPPED, not defaulted. A zero close would be a price.
            logger.warning("[bars_polygon] unreadable bar for %s dropped", ticker)
    return out


async def fetch_daily(ticker: str, start: _dt.date, end: _dt.date) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_fetch_sync, ticker, start.isoformat(), end.isoformat())


async def uw_chart_close(ticker: str) -> Tuple[Optional[_dt.date], Optional[float]]:
    """The UW chart's newest daily close and the session it belongs to.

    This is the number Polygon agreed with on 2026-10-16, so it is what the nightly checks
    against. Returns (None, None) when the chart read is unavailable -- which the caller must
    treat as "could not verify", never as "verified".
    """
    try:
        from services.read_only.chart_indicators import get_chart_indicators
        got = await get_chart_indicators(ticker, "daily")
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[bars_polygon] UW chart read failed for %s: %s",
                       ticker, type(exc).__name__)
        return None, None
    data = (got or {}).get("data") or got or {}
    spot = data.get("spot")
    as_of = data.get("as_of")
    day = None
    if as_of:
        try:
            day = _dt.date.fromisoformat(str(as_of)[:10])
        except ValueError:
            day = None
    try:
        spot = float(spot) if spot is not None else None
    except (TypeError, ValueError):
        spot = None
    return day, spot


async def verify_close(ticker: str, session: _dt.date, close: float) -> Tuple[bool, str]:
    """Does the UW chart agree with this Polygon close for this session?

    THREE OUTCOMES, NOT TWO. Agreement, disagreement, and "the chart could not answer for this
    session" -- and the third is not agreement. R-IV.1203(b)1 says a mismatch writes nothing and
    raises health to DEGRADED; an unverifiable session is treated the same way, because writing
    an unchecked close would make the check decorative.
    """
    day, spot = await uw_chart_close(ticker)
    if day is None or spot is None:
        return False, ("UW chart unavailable for %s, so the close could not be verified"
                       % ticker)
    if day != session:
        return False, ("UW chart is at %s, not the session being written (%s), so the close "
                       "could not be verified" % (day, session))
    if abs(spot - close) > CLOSE_TOLERANCE:
        return False, ("close MISMATCH for %s on %s: polygon %.4f vs UW chart %.4f"
                       % (ticker, session, close, spot))
    return True, ("polygon %.2f == UW chart %.2f for %s on %s"
                  % (close, spot, ticker, session))


async def store(conn, ticker: str, bars: List[Dict[str, Any]], *, verified: bool) -> int:
    """Upsert bars into `regime_daily_bars`. Returns rows written.

    UPSERT, NOT APPEND-ONLY, and the difference from `regime_snapshots` is deliberate: a bar is
    a measurement of a session that has one correct value, so a corrected vendor figure SHOULD
    replace a wrong one. A label is a judgement about a session, and replacing one destroys the
    evidence that it changed.
    """
    written = 0
    for b in bars:
        await conn.execute(
            """INSERT INTO regime_daily_bars
                   (ticker, date, o, h, l, c, v, close_source, uw_verified, fetched_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
               ON CONFLICT (ticker, date) DO UPDATE SET
                   o = EXCLUDED.o, h = EXCLUDED.h, l = EXCLUDED.l, c = EXCLUDED.c,
                   v = EXCLUDED.v, close_source = EXCLUDED.close_source,
                   uw_verified = EXCLUDED.uw_verified, fetched_at = now()""",
            ticker, b["date"], b["o"], b["h"], b["l"], b["c"], b["v"], SOURCE, bool(verified))
        written += 1
    return written


async def load_series(conn, tickers, limit: int = 600) -> Dict[str, List[Any]]:
    """Oldest-first bars per ticker from `regime_daily_bars`, as `regime_inputs.Bar`.

    Same shape the classifier already consumes, so switching the source is a change of table
    and not a change of classifier.
    """
    from models.regime_inputs import Bar

    out: Dict[str, List[Any]] = {}
    for t in tickers:
        rows = await conn.fetch(
            """SELECT date, o, h, l, c, v FROM regime_daily_bars
                WHERE ticker = $1 AND close_source = $2
                ORDER BY date DESC LIMIT $3""", t, SOURCE, int(limit))
        out[t] = [Bar.from_row(r) for r in reversed(rows)]
    return out


async def backfill(conn, tickers, years: int = 2) -> Dict[str, Any]:
    """Fetch and store the full available history. One range call per ticker.

    No UW cross-check on the backfill: the chart route serves only the NEWEST reading, so there
    is nothing to check a two-year history against. The rows are stored with uw_verified FALSE,
    which is the honest record -- they were not checked, and a TRUE there would be a claim.
    """
    today = _dt.date.today()
    start = today - _dt.timedelta(days=int(years * 366))
    report: Dict[str, Any] = {"source": SOURCE, "per_ticker": {}, "written": 0}
    first = True
    for t in tickers:
        if not first:
            await asyncio.sleep(CALL_GAP_S)
        first = False
        try:
            bars = await fetch_daily(t, start, today)
        except PolygonUnavailable as exc:
            report["per_ticker"][t] = {"error": str(exc)}
            continue
        n = await store(conn, t, bars, verified=False)
        report["written"] += n
        report["per_ticker"][t] = {
            "bars": n,
            "first": bars[0]["date"].isoformat() if bars else None,
            "last": bars[-1]["date"].isoformat() if bars else None,
        }
    return report


async def sessions_with_stored_bars(conn, tickers, since):
    """Dates that already hold a bar for EVERY ticker, or None when the table cannot be read.

    EVERY TICKER, because `capture_session` writes a session all-or-nothing: a date holding SPY
    but not IWM was never written by this path, and treating it as present would leave a hole
    the classifier reads as data.

    NONE IS A THIRD ANSWER, not an empty set. Empty means "nothing stored, consider the whole
    range"; None means "I could not find out", and the caller then processes its target only AND
    SAYS SO in its result. Collapsing the two would make an unreadable table look like an empty
    one and send the UW verifier across the entire range every night.
    """
    try:
        rows = await conn.fetch(
            """SELECT date, COUNT(DISTINCT ticker) AS n
                 FROM regime_daily_bars
                WHERE date >= $1 AND ticker = ANY($2::text[])
                GROUP BY date""", since, list(tickers))
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[bars_polygon] cannot read stored bar dates (%s); only the target "
                     "session will be considered", type(exc).__name__)
        return None
    need = len(set(tickers))
    return set(r["date"] for r in rows if (r["n"] or 0) >= need)


async def capture_session(conn, session: _dt.date, tickers) -> Dict[str, Any]:
    """The nightly read: settled sessions only, and verified before anything is written.

    R-IV.1203(b)1, in order:
      1. the session must be SETTLED (the calendar decides, three-state, and UNKNOWN is not YES);
      2. Polygon must have a bar FOR THAT SESSION -- not its newest bar, that session's;
      3. the close must agree with the UW chart close.
    A failure at any step writes NOTHING for that ticker and reports DEGRADED. Partial writes are
    what make a series you cannot trust: one verified ticker beside one unverified one is a
    series with a hole that reads as data.
    """
    from stable_engine.market_calendar import is_session_settled, settlement_reason

    settled = is_session_settled(session)
    if settled is not True:
        return {"degraded": False, "written": 0, "skipped": True,
                "reason": "not settled: %s (is_session_settled=%r)"
                          % (settlement_reason(session), settled)}

    # -- R-IV.1357(a)1: EVERY VERIFIED BAR IN THE RANGE, not only the target's ----------
    #
    # WHAT THIS FIXES, measured rather than reasoned about. The range was ALREADY being fetched
    # (RANGE_LOOKBACK_DAYS = 7) and every bar but the target's was thrown away. Asked directly
    # on 2026-10-23 at 02:08:40Z, Polygon served SPY/QQQ/IWM for 10-15, 10-16, 10-19, 10-20 and
    # 10-21 and withheld 10-22. The night of 10-21 had asked for 10-21 at +5.6h after its close
    # and been refused. So 10-21's bar sat in every later response and was discarded each time,
    # and nothing ever asked for that session again: this function is the ONLY writer of
    # `regime_daily_bars` and it is called once a night with that night's own target. The bar
    # was unreachable forever, and the lag could only grow.
    #
    # ALL-OR-NOTHING IS PER SESSION, AND STAYS THAT WAY. A session is written only if EVERY
    # ticker verified for it. One session present for SPY and absent for IWM is a hole that
    # reads as data, and the classifier slices all three by the same session date -- so staging
    # below is per session, and a session with any problem is dropped WHOLE while its
    # neighbours still go in. That is the one behaviour this restructure must not lose.
    fetched: Dict[str, List[Dict[str, Any]]] = {}
    fetch_problems: List[str] = []
    tick = [str(t) for t in tickers]
    first = True
    for t in tick:
        if not first:
            await asyncio.sleep(CALL_GAP_S)
        first = False
        try:
            # A RANGE, NOT A SINGLE SESSION. R-IV.1278(b)1: asking for exactly one session is
            # what broke the nightly on two consecutive nights. MEASURED, both ways:
            #
            #   /range/1/day/2026-10-21/2026-10-21   HTTP 403 NOT_AUTHORIZED
            #                                        "Your plan doesn't include this data"
            #   /range/1/day/2026-10-15/2026-10-21   HTTP 200, n=4, and it simply OMITS 10-21
            #
            # On this plan a session that is still current is withheld, and a request for ONLY
            # that session is refused outright -- so a withheld session arrived as a hard
            # vendor error instead of as an absence. A range that merely includes it answers
            # 200 and leaves the bar out, which is the same fact in a form the caller can read.
            fetched[t] = await fetch_daily(
                t, session - _dt.timedelta(days=RANGE_LOOKBACK_DAYS), session)
        except PolygonUnavailable as exc:
            fetch_problems.append(str(exc))

    start = session - _dt.timedelta(days=RANGE_LOOKBACK_DAYS)
    stored = await sessions_with_stored_bars(conn, tick, start)
    backfill_blind = stored is None            # reported, never silent -- see the helper

    # Sessions EVERY ticker served. An intersection, because a session one ticker is missing
    # cannot be written under the rule above, and treating it as a candidate would only produce
    # the same problem row for it every night.
    common = set()
    if tick and len(fetched) == len(tick):
        common = set.intersection(*[set(b["date"] for b in fetched[t]) for t in tick])

    candidates = []
    for d in sorted(common):
        if d != session and (backfill_blind or d in (stored or set())):
            continue                           # already stored, or we cannot tell
        if is_session_settled(d) is not True:
            continue                           # UNKNOWN is not YES (R-IV.1176)
        candidates.append(d)

    written = 0
    backfilled = []
    problems: List[str] = list(fetch_problems)
    target_problems: List[str] = list(fetch_problems)
    target_written = False

    for d in candidates:                       # OLDEST FIRST: a partial run leaves a prefix,
        staged: Dict[str, Dict[str, Any]] = {}  # never a gap in the middle of the series.
        trouble: List[str] = []
        for t in tick:
            bar = next((b for b in fetched[t] if b["date"] == d), None)
            if bar is None:
                # NOT YET RELEASED is a different fact from NOT A TRADING DAY and from a vendor
                # outage, and the caller (and the audit row) must be able to tell them apart.
                served = fetched[t][-1]["date"].isoformat() if fetched[t] else "none"
                trouble.append(
                    "%s: polygon has no bar for %s yet -- this plan withholds a session that "
                    "is still current, and the newest it served in this range is %s"
                    % (t, d, served))
                continue
            ok, why = await verify_close(t, d, bar["c"])
            if not ok:
                trouble.append(why)
                continue
            staged[t] = bar

        if trouble or len(staged) != len(tick):
            problems.extend(trouble)
            if d == session:
                target_problems.extend(trouble)
            logger.error("[bars_polygon] %s DEGRADED, nothing written for it: %s",
                         d, "; ".join(trouble))
            continue

        for t, bar in staged.items():
            written += await store(conn, t, [bar], verified=True)
        if d == session:
            target_written = True
        else:
            backfilled.append(d.isoformat())
            logger.info("[bars_polygon] backfilled %s for %d ticker(s): it had no stored bar",
                        d, len(staged))

    out: Dict[str, Any] = {"written": written, "backfilled": backfilled,
                           "candidates": [d.isoformat() for d in candidates]}
    if backfill_blind:
        # NOT SILENT. A run that cannot read the bar table still captures its target, but it
        # cannot know which earlier sessions are missing -- and a backfill that quietly stopped
        # happening is the fault this change exists to end.
        out["backfill_blind"] = ("the stored-bar dates could not be read, so only the target "
                                 "session was considered")
    if target_written:
        return dict(out, degraded=False,
                    reason="verified against the UW chart close for %d ticker(s)" % len(tick))
    return dict(out, degraded=True, problems=problems,
                reason=("; ".join(target_problems)
                        or "polygon served no bar for %s in the range" % session))
