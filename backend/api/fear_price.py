"""`GET /api/fear-price` — B5's Fear Price tile, live.

SOURCES, each named in the payload beside what it produced:
  * ^VIX / ^VXN / ^RVX / ^VIX9D / ^VIX3M / ^VIX6M / ^SKEW and SPY / QQQ / IWM daily closes --
    ONE batched yfinance call. No key, no spend.
  * the ATM straddle -- the hub's existing options-chain service (Unusual Whales), one cached
    call for one SPY expiry. No new spend; UW is already the hub's chain source.

NO BOOK TABLE IS READ HERE, so this route is not gated: every figure on it is public market
data. /api/event-strip and /api/position-watch read `unified_positions` and ARE gated.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from models import fear_price_b5 as fp

logger = logging.getLogger("api_fear_price")

router = APIRouter(prefix="/fear-price", tags=["fear-price"])

#: Enough history for SKEW's five-year percentile, in calendar days.
HISTORY_DAYS = 365 * 6


_LAST_DATES: Dict[str, str] = {}


def _series() -> Dict[str, List[Optional[float]]]:
    """One batched yfinance download of every symbol B5 needs. Ascending, always sorted.

    Each symbol's last observation DATE is recorded too: the tile's "close <date>" line must
    state the date of the reading, not the date it was read. A figure stamped with today when
    its source last printed on Friday is the stale-looks-fresh fault.
    """
    import yfinance as yf

    syms = ([s for _, s in fp.PAIRS] + [s for _, s in fp.CURVE] + ["^SKEW"]
            + [u for u, _ in fp.PAIRS])
    syms = list(dict.fromkeys(syms))                       # de-dupe, order preserved
    frame = yf.download(syms, period="%dd" % HISTORY_DAYS, interval="1d",
                        auto_adjust=False, progress=False, threads=False, group_by="ticker")
    out: Dict[str, List[Optional[float]]] = {}
    if frame is None or getattr(frame, "empty", True):
        return out
    for sym in syms:
        try:
            sub = frame[sym] if len(syms) > 1 else frame
        except Exception:                                           # noqa: BLE001
            continue
        if sub is None or getattr(sub, "empty", True):
            continue
        sub = sub.sort_index()
        try:
            _LAST_DATES[sym] = sub.index[-1].date().isoformat()
        except Exception:                                           # noqa: BLE001
            pass
        vals: List[Optional[float]] = []
        for _, row in sub.iterrows():
            try:
                v = float(row["Close"])
                vals.append(None if v != v else v)
            except Exception:                                       # noqa: BLE001
                vals.append(None)
        out[sym] = vals
    return out


def _last(vals: Optional[List[Optional[float]]]) -> Optional[float]:
    for v in reversed(vals or []):
        if v is not None:
            return v
    return None


async def _straddle(spy_spot: Optional[float]) -> Dict[str, Any]:
    """The ATM straddle for the first SPY expiry at or after the next macro event.

    THE EXPIRY IS CHOSEN BY THE CALENDAR, NOT BY A FIXED NUMBER OF DAYS, which is the whole
    point of the mock's "SPY MOVE -> FOMC" label: the useful question is what the market has
    priced into the next catalyst, and B4's own macro list already knows when that is. If the
    calendar is unavailable the label says "next weekly" instead of naming an event it did not
    actually read.
    """
    label = "SPY MOVE"
    target: Optional[_dt.date] = None
    try:
        from api.event_strip import _macro

        macro, _err = await _macro()
        upcoming = sorted(m["date"] for m in macro if m["date"] >= _dt.date.today())
        if upcoming:
            from models import event_strip_b4 as es

            nxt = [m for m in macro if m["date"] == upcoming[0]]
            word = es.macro_word(nxt[0]["name"]) if nxt else None
            target = upcoming[0]
            label = "SPY MOVE → %s" % (word or "next event")
    except Exception as exc:                                        # noqa: BLE001
        logger.debug("[fear] macro unavailable for the expected move: %s", type(exc).__name__)
    if target is None:
        target = _dt.date.today() + _dt.timedelta(days=7)
        label = "SPY MOVE → next week"

    try:
        from services.read_only import options_chain as oc

        expiry = _next_friday_on_or_after(target)
        chain = await oc.get_options_chain("SPY", expiry.isoformat(), "both")
    except Exception as exc:                                        # noqa: BLE001
        return fp.expected_move(spy_spot, None, None, label=label) | {
            "reason": "the options chain call failed: %s" % type(exc).__name__}
    if not chain:
        return fp.expected_move(spy_spot, None, None, label=label) | {
            "reason": "no options chain was returned for SPY %s" % expiry.isoformat()}

    call_mid, put_mid = _atm_mids(chain, spy_spot)
    days = (expiry - _dt.date.today()).days
    out = fp.expected_move(spy_spot, call_mid, put_mid, days=days, label=label)
    out["expiry"] = expiry.isoformat()
    return out


def _next_friday_on_or_after(d: _dt.date) -> _dt.date:
    """SPY has daily expiries, but a Friday is the one every chain reliably carries."""
    return d + _dt.timedelta(days=(4 - d.weekday()) % 7)


def _atm_mids(chain: Dict[str, Any], spot: Optional[float]):
    """(call mid, put mid) for the strike nearest spot. (None, None) when it cannot be found."""
    if spot is None:
        return None, None
    rows = chain.get("contracts") or chain.get("options") or chain.get("chain") or []
    best: Dict[str, Any] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            strike = float(r.get("strike") or r.get("strike_price"))
        except Exception:                                           # noqa: BLE001
            continue
        kind = str(r.get("type") or r.get("option_type") or "").lower()
        kind = "call" if kind.startswith("c") else ("put" if kind.startswith("p") else "")
        if not kind:
            continue
        mid = _mid(r)
        if mid is None:
            continue
        key = kind
        if key not in best or abs(strike - spot) < abs(best[key]["strike"] - spot):
            best[key] = {"strike": strike, "mid": mid}
    if "call" in best and "put" in best:
        return best["call"]["mid"], best["put"]["mid"]
    return None, None


def _mid(r: Dict[str, Any]) -> Optional[float]:
    bid, ask = r.get("bid"), r.get("ask")
    try:
        b, a = float(bid), float(ask)
        if b > 0 and a > 0:
            return (b + a) / 2.0
    except Exception:                                               # noqa: BLE001
        pass
    for k in ("mid", "last", "last_price", "close"):
        try:
            v = float(r.get(k))
            if v > 0:
                return v
        except Exception:                                           # noqa: BLE001
            continue
    return None


@router.get("")
async def get_fear_price() -> Dict[str, Any]:
    try:
        series = await asyncio.to_thread(_series)
        if not series:
            return {"live": True, "error": "NoSeries", "gaps": [],
                    "note": "yfinance returned nothing; no cached figure is substituted"}
        gaps, gap_vals = [], []
        for under, idx in fp.PAIRS:
            implied = _last(series.get(idx))
            g, basis = fp.gap(implied, series.get(under, []))
            gap_vals.append(g)
            gaps.append({"ticker": under, "index": idx,
                         "pts": None if g is None else round(g, 1), "basis": basis})
        word, lean, hbasis = fp.headline(gap_vals)
        curve_vals = [_last(series.get(s)) for _, s in fp.CURVE]
        clabel, cbasis = fp.curve_label(curve_vals)
        skew_hist = (series.get("^SKEW") or [])[-fp.SKEW_WINDOW:]
        skew_now = _last(series.get("^SKEW"))
        pct = fp.percentile(skew_now, skew_hist)
        spy_spot = _last(series.get("SPY"))
        em = await _straddle(spy_spot)
        return {
            "live": True,
            "headline": word,
            "headline_lean": lean,
            "headline_basis": hbasis,
            "gaps": gaps,
            "curve": {"label": clabel, "basis": cbasis,
                      "tenors": [t for t, _ in fp.CURVE],
                      "values": [None if v is None else round(v, 2) for v in curve_vals]},
            "skew": {"value": None if skew_now is None else round(skew_now, 2),
                     "pct": pct, "pct_label": fp.ordinal(pct),
                     "left": "CHEAP HEDGES", "right": "CROWDED HEDGES",
                     "basis": ("percentile rank within %d sessions of ^SKEW's own history"
                               % len(skew_hist))},
            "expected_move": em,
            "settled_close": _LAST_DATES.get("^VIX"),
            "caption": "implied minus 20d realized · display only",
            "sources": {
                "implied": "yfinance ^VIX / ^VXN / ^RVX, one batched daily call",
                "realized": "%d-day annualised close-to-close, from the same call"
                            % fp.REALIZED_DAYS,
                "curve": "yfinance ^VIX9D / ^VIX / ^VIX3M / ^VIX6M",
                "skew": "yfinance ^SKEW, percentile over its own history",
                "expected_move": "the hub's options-chain service (Unusual Whales), ATM "
                                 "straddle mids, one cached call",
            },
            "as_of": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "field_origin": {"gaps": "derived", "headline": "derived", "curve": "derived",
                             "skew": "derived", "expected_move": "derived"},
        }
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[fear-price] failed: %s", type(exc).__name__)
        return {"live": True, "error": "%s" % type(exc).__name__, "gaps": [],
                "note": "the Fear Price read failed; no mock is substituted"}
