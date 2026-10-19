"""B8's FRED-backed and ratio-backed drawer sections. R-IV.1246(b).

§2 CREDIT (HY OAS), §5 RATES AND CROSS-ASSET, §4 LEADERSHIP RATIOS, §3's ZWEIG PROXY.

PURE, except where noted: series in, reads out. The fetching lives in the API layer, which
already owns the one FRED client and the one batched yfinance call.

ONE RULE RUNS THROUGH ALL OF THEM: A SOURCE THAT FAILS SHOWS "unavailable", NEVER A MOCK VALUE
(R-IV.1246(b)). So every builder here returns an `available` flag and a reason, and no builder
has a default. The drawer prints the reason.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── §2 credit ─────────────────────────────────────────────────────────────

HY_SERIES = "BAMLH0A0HYM2"
#: ICE BofA US High Yield index option-adjusted spread, in PERCENTAGE POINTS on FRED. A reader
#: who assumes basis points is out by a factor of 100, so the unit is converted once, here,
#: and the payload states it.
HY_WIDE_BP = 500.0
HY_CALM_BP = 300.0
#: The percentile window, in observations. One year of daily data.
CREDIT_WINDOW = 252


def credit_block(points: Sequence[Tuple[Any, Optional[float]]]) -> Dict[str, Any]:
    """HY OAS now, its 20-day change, its one-year percentile, and a word.

    The WORD is about the level, and the CHANGE is the thing that moves first: credit usually
    widens before equities break, so a tight-but-widening read is a different fact from a
    tight-and-flat one, and both are shown rather than collapsed into one label.
    """
    vals = [v for _, v in points if v is not None]
    if not vals:
        return {"available": False, "reason": "FRED returned no %s observation" % HY_SERIES}
    now_pct = vals[-1]
    bp = now_pct * 100.0
    window = vals[-CREDIT_WINDOW:]
    below = sum(1 for v in window if v < now_pct)
    pct_rank = int(round(100.0 * below / len(window))) if len(window) > 1 else None
    chg = None
    if len(vals) > 21:
        chg = (now_pct - vals[-22]) * 100.0
    word = "WIDE" if bp >= HY_WIDE_BP else ("CALM" if bp <= HY_CALM_BP else "MIDDLING")
    as_of = next((d for d, v in reversed(points) if v is not None), None)
    # R-IV.1252(c)5: the 1-year line and the shaded TOP-5% BAND. The band is a quantile of
    # this series' OWN year, not a fixed level: "the widest 5% of the last year" is a
    # statement about the distribution on screen, where a hard-coded 600bp would be a
    # statement about a different decade.
    spark = [round(v * 100.0, 1) for v in window]
    top5 = None
    if len(window) >= 20:
        ranked = sorted(window)
        top5 = round(ranked[int(round(0.95 * (len(ranked) - 1)))] * 100.0, 1)
    return {
        "available": True,
        "bp": round(bp, 0),
        "word": word,
        "change_20d_bp": None if chg is None else round(chg, 0),
        "pct_rank": pct_rank,
        "as_of": as_of.isoformat() if hasattr(as_of, "isoformat") else as_of,
        "spark": spark,
        "top5_bp": top5,
        "series": HY_SERIES,
        "basis": ("ICE BofA US High Yield option-adjusted spread, FRED %s, published in "
                  "percentage points and shown here in BASIS POINTS; percentile over the last "
                  "%d observations" % (HY_SERIES, len(window))),
        "thresholds": {"wide_at_bp": HY_WIDE_BP, "calm_at_bp": HY_CALM_BP},
    }


# ── §5 rates and cross-asset ──────────────────────────────────────────────

#: DFII10 is the 10-year TIPS yield (the real rate); T10YIE is the 10-year breakeven. Both FRED,
#: both in percentage points. MOVE has no free series this lane could verify.
RATES_SERIES = {"real_10y": "DFII10", "breakeven_10y": "T10YIE"}
MOVE_UNAVAILABLE = ("MOVE: no free source this lane could verify returns it, so it is shown "
                    "unavailable rather than substituted (R-IV.1246(b)3)")


def rates_block(series: Dict[str, Sequence[Tuple[Any, Optional[float]]]],
                move: Optional[float] = None) -> Dict[str, Any]:
    """The real rate, the breakeven, their 20-day changes, and MOVE or its absence.

    A RISING REAL RATE AND A RISING BREAKEVEN ARE DIFFERENT NEWS -- one is tightening, the
    other is inflation expectation - so they are never summed or averaged into a single
    "rates" number.
    """
    out: Dict[str, Any] = {"available": False, "rows": [], "move": None}
    for key, sid in RATES_SERIES.items():
        pts = series.get(sid) or []
        vals = [v for _, v in pts if v is not None]
        if not vals:
            out["rows"].append({"key": key, "series": sid, "available": False,
                                "reason": "FRED returned no %s observation" % sid})
            continue
        as_of = next((d for d, v in reversed(pts) if v is not None), None)
        chg = (vals[-1] - vals[-22]) * 100.0 if len(vals) > 21 else None
        out["rows"].append({
            "key": key, "series": sid, "available": True,
            "pct": round(vals[-1], 2),
            # R-IV.1252(c)8's sparkline. 21 points for a 20-session change, so the line and
            # the number beside it describe the same window.
            "spark": [round(v, 3) for v in vals[-21:]],
            "change_20d_bp": None if chg is None else round(chg, 0),
            "as_of": as_of.isoformat() if hasattr(as_of, "isoformat") else as_of,
        })
    out["available"] = any(r.get("available") for r in out["rows"])
    out["move"] = ({"available": True, "value": round(move, 1)} if move is not None
                   else {"available": False, "reason": MOVE_UNAVAILABLE})
    out["basis"] = ("DFII10 is the 10-year TIPS (real) yield and T10YIE the 10-year breakeven, "
                    "both FRED, both percentage points. They are reported separately because a "
                    "rising real rate and a rising breakeven are different news")
    return out


# ── §4 leadership ratios ──────────────────────────────────────────────────

#: Each ratio and what a RISING value means, in the words the card shows. The pair is named so
#: nobody has to remember which way up it is: "RSP/SPY rising" is breadth improving.
LEADERSHIP = (
    ("RSP/SPY", "RSP", "SPY", "equal-weight leading: breadth improving"),
    ("IWM/SPY", "IWM", "SPY", "small caps leading"),
    ("XLY/XLP", "XLY", "XLP", "discretionary over staples: risk appetite"),
    ("SMH/SPY", "SMH", "SPY", "semis leading"),
    ("COPPER/GOLD", "CPER", "GLD", "copper over gold: growth over fear"),
)
#: The lookback for "is this ratio rising", in sessions.
LEADERSHIP_LOOKBACK = 20


def ratio_row(name: str, a: Sequence[Optional[float]], b: Sequence[Optional[float]],
              rising_means: str, lookback: int = LEADERSHIP_LOOKBACK) -> Dict[str, Any]:
    """One ratio, its change over `lookback` sessions, and which way it points.

    PAIRED AT THE SAME INDEX, so a missing session in one leg cannot silently shift the other
    by a day: both series are trimmed to their common length from the RIGHT (the newest end).
    """
    av = [v for v in a if v is not None]
    bv = [v for v in b if v is not None]
    n = min(len(av), len(bv))
    if n < lookback + 1:
        return {"name": name, "available": False,
                "reason": "fewer than %d paired sessions (%d)" % (lookback + 1, n)}
    av, bv = av[-n:], bv[-n:]
    if bv[-1] == 0 or bv[-1 - lookback] == 0:
        return {"name": name, "available": False, "reason": "the denominator is zero"}
    now = av[-1] / bv[-1]
    then = av[-1 - lookback] / bv[-1 - lookback]
    pct = 100.0 * (now / then - 1.0) if then else None
    # (c)7's sparkline: the RATIO's own 20-session path, not either leg's. A leg's line would
    # move with the market and hide the relative story the bar is about.
    spark = [round(av[i] / bv[i], 4) for i in range(-min(21, n), 0) if bv[i]]
    return {
        "name": name, "available": True,
        "ratio": round(now, 4),
        "spark": spark,
        "change_pct": None if pct is None else round(pct, 1),
        "direction": None if pct is None else ("rising" if pct > 0 else
                                               ("flat" if abs(pct) < 0.25 else "falling")),
        "rising_means": rising_means,
        "lookback": lookback,
    }


def leadership_block(closes: Dict[str, List[Optional[float]]]) -> Dict[str, Any]:
    rows = [ratio_row(name, closes.get(a) or [], closes.get(b) or [], means)
            for name, a, b, means in LEADERSHIP]
    live = [r for r in rows if r.get("available")]
    rising = [r for r in live if r.get("direction") == "rising"]
    return {
        "available": bool(live),
        "rows": rows,
        "headline": (None if not live else
                     "%d of %d ratios rising" % (len(rising), len(live))),
        "basis": ("%d-session change in each ratio. COPPER/GOLD uses the CPER and GLD ETFs as "
                  "the tradable proxies for the metals" % LEADERSHIP_LOOKBACK),
    }


# ── §3's Zweig flag, as a PROXY ───────────────────────────────────────────

#: Zweig's breadth thrust: the 10-day EMA of advances / (advances + declines) going from under
#: 40% to over 61.5% within 10 sessions.
ZWEIG_FROM_PCT = 40.0
ZWEIG_TO_PCT = 61.5
ZWEIG_WINDOW = 10

ZWEIG_PROXY_NOTE = (
    "PROXY, not Zweig's own measure (R-IV.1246(b)7). The real thrust is the 10-day EMA of "
    "NYSE advances / (advances + declines) crossing from under 40% to over 61.5% in 10 "
    "sessions. The hub stores no advance/decline line, so this substitutes the share of "
    "sectors above their 50-day average, which is a slower and broader series: it will miss a "
    "fast thrust and can register one the real measure would not. Labelled a proxy wherever it "
    "is shown")


def zweig_proxy(breadth_pct: Sequence[Optional[float]],
                window: int = ZWEIG_WINDOW) -> Dict[str, Any]:
    """(fired, basis) for the proxy thrust over `window` observations.

    Returns `fired: False` with a reason when there is history and no thrust, and
    `available: False` when there is not enough history -- which are different facts and must
    not share a rendering.
    """
    vals = [v for v in breadth_pct if v is not None]
    if len(vals) < window + 1:
        return {"available": False, "fired": None,
                "reason": "fewer than %d breadth observations (%d)" % (window + 1, len(vals)),
                "note": ZWEIG_PROXY_NOTE}
    recent = vals[-(window + 1):]
    low = min(recent)
    fired = low < ZWEIG_FROM_PCT and recent[-1] > ZWEIG_TO_PCT
    return {
        "available": True,
        "fired": bool(fired),
        "from_pct": ZWEIG_FROM_PCT,
        "to_pct": ZWEIG_TO_PCT,
        "low_in_window": round(low, 1),
        "now_pct": round(recent[-1], 1),
        "window": window,
        "reason": (None if fired else
                   "no thrust: the window's low was %.1f%% and it is %.1f%% now"
                   % (low, recent[-1])),
        "note": ZWEIG_PROXY_NOTE,
    }


# ── §6 auction state (PYTHIA) ─────────────────────────────────────────────

#: Where price sits against the prior session's value area. The words are the market-profile
#: vocabulary the PYTHIA feed already uses, not new ones.
def auction_block(mp: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """SPY's auction state from the PYTHIA market-profile snapshot.

    THE BRACKET COUNTER IS WITHHELD, not estimated. Board 8 asked for it greyed under 10
    sessions; the hub stores the LATEST snapshot per ticker and no per-session bracket history,
    so there is no count to grey -- a "1 of 10" built from one row would be a number about
    nothing. Reported as unavailable with that reason.
    """
    if not mp:
        return {"available": False,
                "reason": "no PYTHIA market-profile snapshot is stored for SPY"}
    d = mp.get("data") if isinstance(mp.get("data"), dict) else mp
    price = _f(d.get("price"))
    vah, val, poc = _f(d.get("vah")), _f(d.get("val")), _f(d.get("poc"))
    where, basis = _where_in_value(price, vah, val, poc)
    # THE AUCTION STATE *IS* THE SECTION, so a row that cannot produce one is not "available".
    # Measured live: the stored PYTHIA snapshot for SPY exists but carries no price, VAH or
    # VAL, so the first version of this returned `available: True` with a blank headline — a
    # section reporting itself present while having nothing to say, which is the
    # caption-lies-about-its-field fault at the level of a whole block. Whatever IS recorded
    # is still returned below, so a partial snapshot is not hidden either.
    return {
        "available": where is not None,
        "reason": None if where is not None else basis,
        "where": where,
        "where_basis": basis,
        "price": price, "vah": vah, "val": val, "poc": poc,
        "ib_high": _f(d.get("ib_high")), "ib_low": _f(d.get("ib_low")),
        "va_migration": d.get("va_migration"),
        "poor_high": d.get("poor_high"), "poor_low": d.get("poor_low"),
        "volume_quality": d.get("volume_quality"),
        "interpretation": d.get("interpretation"),
        "as_of": d.get("timestamp"),
        "staleness_seconds": mp.get("staleness_seconds"),
        "bracket_counter": {
            "available": False,
            "reason": ("the hub stores the latest market-profile snapshot per ticker and no "
                       "per-session bracket history, so there is no count to show -- a "
                       "figure built from one row would be a number about nothing"),
        },
        "basis": "PYTHIA market-profile snapshot for SPY, as stored",
    }


def _where_in_value(price, vah, val, poc) -> Tuple[Optional[str], str]:
    """ABOVE / INSIDE / BELOW the value area, with the levels that decided it.

    None when any of the three levels is missing: "inside value" computed against a missing
    edge is the kind of confident wrong answer this card exists not to give.
    """
    if price is None or vah is None or val is None:
        return None, "price, VAH or VAL is not recorded on the snapshot"
    if price > vah:
        return "ABOVE VALUE", "price %.2f over VAH %.2f" % (price, vah)
    if price < val:
        return "BELOW VALUE", "price %.2f under VAL %.2f" % (price, val)
    side = ""
    if poc is not None:
        side = ", %s the POC %.2f" % ("above" if price >= poc else "below", poc)
    return "INSIDE VALUE", "price %.2f between VAL %.2f and VAH %.2f%s" % (price, val, vah, side)


def _f(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


# ── §8 lamps ──────────────────────────────────────────────────────────────

#: The rules file's OWN words for why overlays are not computed in v1. Quoted rather than
#: paraphrased: the reason a lamp is dark is part of the card's record.
OVERLAYS_REASON = "overlays are a judgement input, not computed in v1"


def lamps_block(kill_state: Optional[str] = None) -> Dict[str, Any]:
    """§8's lamps: the overlay lamps and the kill-switch lamp.

    THE OVERLAY LAMPS HAVE NO FEED, and that is the rules file's own position, not a gap I
    found: `NO_FEED_IN_V1` says overlays are a judgement input. So they are shown UNAVAILABLE
    with that sentence, never as dark lamps -- a dark lamp reads as "checked, nothing firing",
    which is a claim, where "no feed" is the truth.

    The kill-switch lamp is the one that can light, and it comes from the regime payload the
    card already reads rather than from a second source.
    """
    return {
        "overlays": {"available": False, "reason": OVERLAYS_REASON},
        "kill": {"available": kill_state is not None, "state": kill_state,
                 "reason": None if kill_state is not None
                 else "the kill-switch state was not readable on this payload"},
        "basis": ("a lamp is shown only where a feed exists. An unlit lamp would read as "
                  "'checked, nothing firing'; 'no feed' is the honest display")
    }
