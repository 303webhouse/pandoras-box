"""FINRA equity short interest, from FINRA's free twice-monthly file. R-IV.1318(a)/(b).

WHAT THE TERMS CHECK FOUND, measured on 2026-10-21 against FINRA's own endpoints rather than
read off a page. R-IV.1318(a) asked which access path needs no paid credential. There are three,
and only one of them is usable:

  1. `api.finra.org/data/group/otcMarket/name/EquityShortInterest`
     NO CREDENTIAL, HTTP 200. But OTC-ONLY (AAPL and SPY both return 204) and IT ENDS AT
     SETTLEMENT 2022-09-15 -- bisected: `> 2022-09-01` returns rows, `> 2022-10-01` returns 204.
     Four years stale, so it cannot back a live panel.
  2. `api.finra.org/data/group/Equity/name/consolidatedShortInterest`
     HTTP 401 "Failed to authenticate". NOTE 401 AND NOT 404 -- the path is real and the
     dataset exists; it is gated behind an OAuth token, which needs an Individual Account.
     (The control that makes this reading sound: `OTCMarket/weeklysummary` returns 200 with
     data and no credential, so the API does serve some datasets anonymously and a 401 here is
     about THIS dataset rather than about the API.)
  3. THIS ONE: `cdn.finra.org/equity/otcmarket/biweekly/shrt<YYYYMMDD>.csv`
     NO CREDENTIAL AND NO ACCOUNT, HTTP 200, 2.7MB, 22,581 rows, pipe-delimited. Covers
     EXCHANGE-LISTED securities -- AAPL (NNM), SPY (ARCA), GME (NYSE), TSLA (NNM) all present.

AND IT CARRIES DAYS TO COVER. `daysToCoverQuantity` and `averageDailyVolumeQuantity` are both
FINRA's own fields. That matters because the row this feeds was held back partly on the finding
that "days to cover is not a documented field in FINRA's own file" (R-IV.1239(d)3's wording
could not be satisfied). THAT FINDING WAS WRONG -- measured AAPL 2026-09-30: short
120,763,539, ADV 39,858,260, daysToCover 3.03. The figure is in the file, from FINRA, not
computed against a volume series from somewhere else.

TERMS (SPINE, read 2026-10-21): the Equity Data terms allow non-commercial personal or
professional use, require FINRA to be identified as owner and source, and forbid charging for
the data. The dataset sits in the Equity group of FINRA's own catalogue, so it is inside the
covered group. Nothing here is redistributed and nothing is charged for; the panel names FINRA
as the source, which `crowd_b6` enforces.

THE PUBLISH DATE IS OBSERVED, NOT COMPUTED. FINRA publishes on about the 7th business day after
settlement, and a rule-of-thumb date would be a guess printed as a fact. The CDN's
`Last-Modified` is the actual instant the file appeared: settlement 2026-09-30 -> published
Mon, 12 Oct 2026 10:00:21 GMT, settlement 2026-09-15 -> Mon, 28 Sep 2026 10:01:36 GMT. Both
dates ride on every value, as R-IV.1318(b) requires.

TWICE MONTHLY, NEVER REAL-TIME. The newest file today is 2026-09-30; 2026-10-15's settlement
returns 403 because it has not been published yet. A reader has to be told that the number is
up to three weeks old by design, which is what `CADENCE_NOTE` is for.

#42: DISPLAY ONLY. Nothing computes from this. It is one line on a positioning tile.
"""
from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("finra_short_interest")

#: The free file. `otcmarket` in the path is FINRA's own spelling and does NOT mean OTC-only:
#: the file carries NYSE, Nasdaq and ARCA listings, measured.
FILE_URL = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt%s.csv"

#: What the panel must say, R-IV.1318(b). Twice monthly, and never presented as a live figure.
CADENCE_NOTE = ("twice-monthly settlement data, published about 7 business days after each "
                "settlement date - not real-time")

#: Required by the Equity Data terms.
ATTRIBUTION = "Source: FINRA"

#: How long a parsed file stays good. The data changes twice a month, so an hour is already
#: far tighter than the publication cadence; it exists to bound a bad fetch, not to chase
#: freshness. A 2.7MB download on every card read would be absurd.
TTL_SECONDS = 3600

#: How many settlement dates back to try before giving up. The newest file is usually the
#: previous settlement, because the current one has not been published yet.
MAX_LOOKBACK = 4

_CACHE: Dict[str, Any] = {"at": 0.0, "settlement": None, "published": None, "rows": {}}


def candidate_settlements(today: Optional[date] = None, n: int = MAX_LOOKBACK) -> List[date]:
    """Settlement dates newest-first: the 15th and the last day of each month.

    FINRA settles mid-month on the 15th (or the previous settlement day) and at month end. The
    exact business-day adjustment is NOT replicated here: a 403 on a date that was adjusted
    costs one extra request, while guessing the adjustment wrong and reporting the shifted date
    as the settlement date would misstate a figure. The file's own `settlementDate` column is
    what gets displayed, so the only job of this list is to find a file.
    """
    import calendar

    d = today or datetime.now(timezone.utc).date()
    out: List[date] = []
    y, m = d.year, d.month
    while len(out) < n + 2:
        last = calendar.monthrange(y, m)[1]
        for day in (last, 15):
            cand = date(y, m, day)
            if cand <= d:
                out.append(cand)
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[:n]


def _parse(text: str) -> Dict[str, Dict[str, Any]]:
    """symbol -> row. Pipe-delimited and quoted; the header is FINRA's own spelling."""
    rows: Dict[str, Dict[str, Any]] = {}
    for r in csv.DictReader(io.StringIO(text), delimiter="|"):
        sym = (r.get("symbolCode") or "").strip().upper()
        if sym:
            rows[sym] = r
    return rows


def _num(v: Any) -> Optional[float]:
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return f if f == f else None


async def _fetch(settlement: date) -> Optional[Dict[str, Any]]:
    """One settlement file, or None when it is not published yet (403) or unreachable."""
    import httpx

    url = FILE_URL % settlement.strftime("%Y%m%d")
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as c:
            resp = await c.get(url)
        if resp.status_code != 200:
            # 403 is FINRA's answer for "not published yet" on a future settlement date. It is
            # an expected, routine state and not an error worth logging loudly.
            return None
        published = resp.headers.get("Last-Modified")
        return {"rows": _parse(resp.text), "published": published, "url": url}
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[finra] %s: %s", type(exc).__name__, exc)
        return None


async def load_latest(force: bool = False) -> Dict[str, Any]:
    """The newest published settlement file, cached. Never raises.

    Returns `{settlement, published, rows, url}` with `rows` empty when nothing could be read --
    an empty result is a STATED absence that the caller turns into "unavailable", never a zero.
    """
    now = time.time()
    if not force and _CACHE["rows"] and (now - _CACHE["at"]) < TTL_SECONDS:
        return dict(_CACHE)

    for cand in candidate_settlements():
        got = await _fetch(cand)
        if got and got["rows"]:
            _CACHE.update({"at": now, "settlement": cand.isoformat(),
                           "published": got["published"], "rows": got["rows"],
                           "url": got["url"]})
            logger.info("[finra] settlement %s published %s, %d symbols",
                        cand.isoformat(), got["published"], len(got["rows"]))
            return dict(_CACHE)
    return {"at": now, "settlement": None, "published": None, "rows": {}, "url": None}


def _publish_date(last_modified: Optional[str]) -> Optional[str]:
    """`Last-Modified` as a plain date. None stays None rather than becoming today."""
    if not last_modified:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            return datetime.strptime(last_modified, fmt).date().isoformat()
        except ValueError:
            continue
    return None


async def short_interest(symbol: str = "SPY") -> Dict[str, Any]:
    """One symbol's short interest, with BOTH dates. Display only (#42).

    `available: False` with a reason whenever anything is missing. A positioning row that
    printed a stale number without its settlement date would be the exact fault this panel's
    siblings were built to avoid.
    """
    sym = (symbol or "").strip().upper()
    got = await load_latest()
    row = (got.get("rows") or {}).get(sym)
    if not row:
        return {"available": False,
                "reason": ("no FINRA row for %s in settlement %s"
                           % (sym, got.get("settlement") or "(no file read)")),
                "attribution": ATTRIBUTION, "cadence": CADENCE_NOTE}

    dtc = _num(row.get("daysToCoverQuantity"))
    return {
        "available": True,
        "symbol": sym,
        "issue_name": (row.get("issueName") or "").strip() or None,
        "days_to_cover": dtc,
        "current_short": _num(row.get("currentShortPositionQuantity")),
        "previous_short": _num(row.get("previousShortPositionQuantity")),
        "average_daily_volume": _num(row.get("averageDailyVolumeQuantity")),
        "change_percent": _num(row.get("changePercent")),
        # BOTH DATES, R-IV.1318(b). The settlement date is the file's own column -- not the
        # date used to find the file, which may differ by a business-day adjustment this module
        # deliberately does not replicate.
        "settlement_date": (row.get("settlementDate") or "").strip() or got.get("settlement"),
        "publish_date": _publish_date(got.get("published")),
        "attribution": ATTRIBUTION,
        "cadence": CADENCE_NOTE,
        "display_only": True,
    }
