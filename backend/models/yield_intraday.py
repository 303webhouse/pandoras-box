"""The intraday overlay on the yield-curve box. R-IV.1257(c).

WHAT THIS IS AND IS NOT. FRED STAYS OFFICIAL -- every level, change, z-score, label and fire
rate in `/api/yield-curve` keeps coming from the FRED daily series, unchanged. This module adds
an OVERLAY: today's 15-minute ticks for four tenors, so the box has something to show while the
session is open and FRED still carries yesterday's close. The overlay never replaces a FRED
figure and never feeds a label; a reader comparing the two is comparing a settled close with an
unsettled tick, and the payload says so in those words.

THE FOUR SYMBOLS ARE THE RULING'S (c), and so is "verify each symbol, no substitution":

    ^IRX  13-week bill   beside FRED's DGS3MO
    ^FVX  5-year         beside DGS5
    ^TNX  10-year        beside DGS10
    ^TYX  30-year        beside DGS30

VERIFIED BY THE VENDOR'S OWN NAME, not by assuming a ticker means what it looks like. Each
response's `meta.shortName` must contain the tenor marker below, and a symbol whose name does
not match is DROPPED with the name it actually returned. This is the same check that caught
`VIX3M` not existing on FRED while `VXVCLS` did, and the reason it matters here is specific: a
mislabelled leg would put a 5-year yield on the 10-year row, where it would read as a 20bp move
rather than as a wrong series.

2Y HAS NO INTRADAY LEG, DELIBERATELY. There is no Yahoo index for the 2-year, and the nearest
candidates are the 5-year (^FVX) and the 13-week bill (^IRX) -- so filling the 2Y row from
either is exactly the substitution (c) forbids. The 2Y therefore reports `intraday: null` with
`reason` naming the absence, which is a fact the reader can act on; a 2Y row quietly carrying
^FVX's number is not.

NO CACHED TICK IS EVER SERVED AS CURRENT. A failed fetch returns an empty overlay with its
reason. The box's own rule (R-IV.1251(b)) is that it is never blank, and FRED is what keeps it
filled; the overlay going quiet costs the box its intraday line and nothing else.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("yield_intraday")

SOURCE = "Yahoo Finance chart API, 15-minute bars, CBOE/Yahoo Treasury yield indices"

#: tenor -> (symbol, a marker that MUST appear in the vendor's own short name)
SYMBOLS: Dict[str, Tuple[str, str]] = {
    "3M": ("^IRX", "13 WEEK"),
    "5Y": ("^FVX", "5"),
    "10Y": ("^TNX", "10"),
    "30Y": ("^TYX", "30"),
}

#: The tenor the box shows that has no intraday leg, with the reason stated once.
NO_INTRADAY = {
    "2Y": ("there is no Yahoo index for the 2-year; the nearest symbols are the 5-year and "
           "the 13-week bill, and filling this row from either would be the substitution "
           "R-IV.1257(c) forbids"),
}

RANGE = "1d"
INTERVAL = "15m"
TIMEOUT = 20

#: Cached for the length of one bar, not for the day: these are INTRADAY ticks, so a day-long
#: cache would serve the open all afternoon -- the exact "stale presented as current" fault the
#: module's own docstring rules out.
CACHE_SECONDS = 15 * 60

_cache: Dict[str, Tuple[_dt.datetime, Dict[str, Any]]] = {}


def _url(symbol: str) -> str:
    return ("https://query1.finance.yahoo.com/v8/finance/chart/"
            + urllib.parse.quote(symbol)
            + "?range=%s&interval=%s" % (RANGE, INTERVAL))


def fetch_one(tenor: str, symbol: str, marker: str) -> Dict[str, Any]:
    """One tenor's intraday series, or an explained absence. Never raises."""
    out: Dict[str, Any] = {"tenor": tenor, "symbol": symbol, "verified": False,
                           "vendor_name": None, "bars": [], "last_pct": None,
                           "session_open_pct": None, "change_bp": None, "as_of": None,
                           "reason": None}
    req = urllib.request.Request(_url(symbol), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        # A STATUS IS AN ANSWER, not an outage. Yahoo returns 404 for a symbol that does not
        # exist, and reporting that as "fetch failed" makes the vendor's correct refusal look
        # like the vendor being unreachable -- which is the difference between a control that
        # fired and a control that was skipped. The status is kept so a caller can tell.
        out["http_status"] = int(getattr(exc, "code", 0) or 0)
        out["reason"] = ("%s was refused by the vendor: HTTP %s%s"
                         % (symbol, out["http_status"],
                            " (no such symbol)" if out["http_status"] == 404 else ""))
        return out
    except Exception as exc:                                        # noqa: BLE001
        out["reason"] = "%s fetch failed: %s" % (symbol, type(exc).__name__)
        return out

    results = ((body.get("chart") or {}).get("result") or [])
    if not results:
        err = (body.get("chart") or {}).get("error")
        out["reason"] = "%s returned no result (%s)" % (symbol, (err or {}).get("code", "none"))
        return out

    meta = results[0].get("meta") or {}
    name = meta.get("shortName") or meta.get("longName") or ""
    out["vendor_name"] = name
    # THE VERIFICATION, BEFORE ANY NUMBER IS READ. A symbol that answers with the wrong
    # instrument is worse than one that does not answer: its numbers are plausible.
    if marker.upper() not in (name or "").upper():
        out["reason"] = ("%s answered as %r, which does not carry %r -- dropped rather than "
                         "placed on the %s row" % (symbol, name, marker, tenor))
        return out
    out["verified"] = True

    stamps = results[0].get("timestamp") or []
    quote = ((results[0].get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    bars: List[Dict[str, Any]] = []
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        bars.append({"t": int(ts), "pct": float(close)})
    if not bars:
        out["reason"] = "%s returned %d bar(s), none with a close" % (symbol, len(stamps))
        return out

    out["bars"] = bars
    out["last_pct"] = bars[-1]["pct"]
    out["session_open_pct"] = bars[0]["pct"]
    # In PERCENTAGE POINTS, like the FRED series, so the change is x100 for basis points. The
    # unit is stated because mixing the two is how a 0.42 move gets displayed as 0.4bp.
    out["change_bp"] = round((bars[-1]["pct"] - bars[0]["pct"]) * 100.0, 1)
    out["as_of"] = _dt.datetime.fromtimestamp(
        bars[-1]["t"], _dt.timezone.utc).isoformat()
    out["exchange_timezone"] = meta.get("exchangeTimezoneName")
    return out


def overlay(*, now: Optional[_dt.datetime] = None) -> Dict[str, Any]:
    """{tenor: block} for the four verified tenors, plus the stated absences and a report.

    Cached for one bar's length. The cache is keyed on the interval so a change to INTERVAL
    cannot silently keep serving the old cadence's bars.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    key = "overlay:%s:%s" % (RANGE, INTERVAL)
    hit = _cache.get(key)
    if hit and (now - hit[0]).total_seconds() < CACHE_SECONDS:
        return dict(hit[1], cached=True,
                    cache_age_seconds=int((now - hit[0]).total_seconds()))

    tenors: Dict[str, Any] = {}
    for tenor, (symbol, marker) in SYMBOLS.items():
        tenors[tenor] = fetch_one(tenor, symbol, marker)
    for tenor, reason in NO_INTRADAY.items():
        tenors[tenor] = {"tenor": tenor, "symbol": None, "verified": False, "bars": [],
                         "last_pct": None, "change_bp": None, "as_of": None, "reason": reason}

    verified = [t for t, b in tenors.items() if b.get("verified")]
    out = {
        "source": SOURCE,
        "interval": INTERVAL,
        "range": RANGE,
        "fetched_at": now.isoformat(),
        "tenors": tenors,
        "verified_tenors": sorted(verified),
        "unavailable": {t: b["reason"] for t, b in tenors.items()
                        if not b.get("verified") and b.get("reason")},
        # CONVENTION #37, as clarified by R-IV.1224(g): source, universe and as-of in the same
        # sentence as the figure, because these are the numbers that get quoted onward without
        # their caption.
        "basis": ("Yahoo 15-minute bars for %s, today's session only, each symbol verified "
                  "against the vendor's own instrument name before any number is read; FRED's "
                  "daily series remains the official level and this overlay never replaces it "
                  "or feeds a label" % ", ".join("%s=%s" % (t, s)
                                                 for t, (s, _m) in SYMBOLS.items())),
        "not_a_close": ("an intraday tick is NOT a settled close: comparing it with the FRED "
                        "row beside it compares an unsettled reading with a settled one"),
        "field_origin": {"bars": "derived", "last_pct": "stored", "change_bp": "derived",
                         "verified": "derived"},
        "cached": False,
        "cache_age_seconds": 0,
    }
    _cache[key] = (now, out)
    return out
