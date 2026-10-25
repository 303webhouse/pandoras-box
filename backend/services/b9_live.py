"""B9 · global markets, LIVE: Monday's cut of SPEC-B9.md (R-IV.1431). Pure computation, no I/O.

SCOPE IS THE SPEC'S "MONDAY'S CUT", and nothing after it:
  1. the seven country ETFs as rows, the four commodities as a separate context list;
  2. each row: ratio vs SPY (QQQ served too, for the toggle), a 1-year sparkline of the ratio,
     and 1M (21) / 3M (63) / 12M (252) session changes as arrows;
  3. TREND on the row's own price: UP / DOWN / RANGE;
  4. LEADERSHIP, the same test on the ratio: LEADING / RANGE / LAGGING;
  5. outsized-move flags UNUSUAL (|z| >= 2) / EXTREME (|z| >= 3), on the price and on the
     ratio, each carrying its fires per year -- QUERY's measured range AND the rate measured on
     the history actually served;
  6. one meltdown-mode status line.
The recovery race, currency gap, overnight tape, commodity cross-reads, "A NEW LEADER IS REAL
IF", coupling and acceptance are AFTER Monday and are not computed here.

THE BASIS IS ADJ CLOSE, USD TOTAL RETURN (amendment 2), and every payload says so. The bars come
from yfinance with `auto_adjust=True` (`stable_engine.bars_yf.fetch_batch`), i.e. dividends
included -- which is why this does NOT read `regime_daily_bars` (Polygon, split-only).

DISPLAY ONLY (#42). Nothing here gates anything or computes into a signal, and the payload is run
through B9's own lint (`b9_world.lint_findings`: the no-orders bar and the keep-out list) before
it is served -- a finding refuses the payload rather than shipping it.

ABSENT IS ABSENT. A value that cannot be computed from the history served is None, with the
reason in `why`, never a default. A quiet market and a missing input must not look alike.
"""
from __future__ import annotations

import math
from statistics import stdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services import b9_world as W

EQUITIES = ("EWJ", "FXI", "EWY", "EWT", "INDA", "EEM", "VGK")
COMMODITIES = W.COMMODITIES                                  # ("GLD", "CPER", "USO", "DBA")
BENCHMARKS = ("SPY", "QQQ")
ALL_TICKERS = EQUITIES + COMMODITIES + BENCHMARKS

#: Plain labels. Region names only (keep-out: no thesis words, no narrative).
NAMES = {
    "EWJ": "Japan", "FXI": "China large caps", "EWY": "South Korea", "EWT": "Taiwan",
    "INDA": "India", "EEM": "Emerging markets", "VGK": "Europe",
    "GLD": "Gold", "CPER": "Copper", "USO": "Crude oil", "DBA": "Agriculture",
    "SPY": "S&P 500", "QQQ": "Nasdaq 100",
}

WINDOWS = (("1M", 21), ("3M", 63), ("12M", 252))
SPARK_SESSIONS = 252
SMA_FAST, SMA_SLOW, SLOPE_SESSIONS = 50, 200, 20
MIN_TREND_BARS = SMA_SLOW + SLOPE_SESSIONS                 # 220: the 50d's value 20 sessions ago

TREND_UP, TREND_DOWN, TREND_RANGE = "UP", "DOWN", "RANGE"
LEAD_UP, LEAD_DOWN, LEAD_RANGE = "LEADING", "LAGGING", "RANGE"


# ── primitives ──────────────────────────────────────────────────────────────

def sma_at(xs: Sequence[float], n: int, end: int) -> Optional[float]:
    """The n-session simple mean of xs ending AT index `end` (inclusive), or None."""
    if end < n - 1 or end >= len(xs):
        return None
    return sum(xs[end - n + 1:end + 1]) / n


def trend_state(xs: Sequence[float]) -> Tuple[Optional[str], Optional[str]]:
    """SPEC §3, on a series's latest value. Returns (state, why-if-None).

    UP:    close > 50d AND close > 200d AND 50d > 200d AND 50d above its value 20 sessions ago.
    DOWN:  the mirror image of all four.
    RANGE: anything else.
    """
    if len(xs) < MIN_TREND_BARS:
        return None, "needs %d sessions, has %d" % (MIN_TREND_BARS, len(xs))
    i = len(xs) - 1
    c, f, s = xs[i], sma_at(xs, SMA_FAST, i), sma_at(xs, SMA_SLOW, i)
    f_then = sma_at(xs, SMA_FAST, i - SLOPE_SESSIONS)
    if c > f and c > s and f > s and f > f_then:
        return TREND_UP, None
    if c < f and c < s and f < s and f < f_then:
        return TREND_DOWN, None
    return TREND_RANGE, None


def pct_changes(xs: Sequence[float]) -> List[float]:
    return [(xs[k] / xs[k - 1] - 1.0) * 100.0 for k in range(1, len(xs)) if xs[k - 1]]


def z_at(changes: Sequence[float], k: int) -> Optional[float]:
    """z of changes[k] against the PRIOR Z_WINDOW changes, EXCLUDING changes[k] itself.

    Excluded deliberately (`b9_world.Z_EXCLUDES_TODAY`): included, a big move inflates its own
    denominator and scores lower than it should. A zero-variance window has no z.
    """
    w = W.Z_WINDOW
    if k < w or k >= len(changes):
        return None
    prior = changes[k - w:k]
    sd = stdev(prior)
    if not sd or not math.isfinite(sd):
        return None
    return changes[k] / sd


def move_flag(xs: Sequence[float]) -> Dict[str, Any]:
    """Today's outsized-move test on `xs` (prices or a ratio), plus its MEASURED rate here.

    `measured_fires_per_year` is counted over every session in the history served that has a
    full prior window, so a reader can see how often THIS threshold fired on THIS series --
    beside QUERY's universe-wide range, never instead of it.
    """
    ch = pct_changes(xs)
    out: Dict[str, Any] = {"z": None, "change_pct": None, "flag": None, "tooltip": None,
                           "measured_fires_per_year": None, "measured_sessions": 0,
                           "why": None}
    if len(ch) <= W.Z_WINDOW:
        out["why"] = "needs %d daily changes, has %d" % (W.Z_WINDOW + 1, len(ch))
        return out
    k = len(ch) - 1
    z = z_at(ch, k)
    out["change_pct"] = round(ch[k], 3)
    if z is None:
        out["why"] = "the prior %d changes have no variance" % W.Z_WINDOW
        return out
    out["z"] = round(z, 2)
    out["flag"] = W.label_for(z)
    zs = [z_at(ch, j) for j in range(W.Z_WINDOW, len(ch))]
    zs = [v for v in zs if v is not None]
    if zs:
        fires = {W.UNUSUAL: sum(1 for v in zs if abs(v) >= W.UNUSUAL_Z),
                 W.EXTREME: sum(1 for v in zs if abs(v) >= W.EXTREME_Z)}
        out["measured_sessions"] = len(zs)
        out["measured_fires_per_year"] = {lab: round(n * 252.0 / len(zs), 1)
                                          for lab, n in fires.items()}
    if out["flag"]:
        mine = (out["measured_fires_per_year"] or {}).get(out["flag"])
        out["tooltip"] = "%s; on this series, %s/yr over the %d sessions served" % (
            W.tooltip_for(out["flag"]), mine, out["measured_sessions"])
    return out


def window_changes(xs: Sequence[float]) -> Dict[str, Any]:
    """1M / 3M / 12M % change of `xs`, each with an arrow. None when the history is short."""
    out = {}
    for name, n in WINDOWS:
        if len(xs) <= n or not xs[-1 - n]:
            out[name] = {"pct": None, "arrow": None, "why": "needs %d sessions" % (n + 1)}
            continue
        p = (xs[-1] / xs[-1 - n] - 1.0) * 100.0
        out[name] = {"pct": round(p, 2), "arrow": "up" if p > 0 else ("down" if p < 0 else "flat"),
                     "why": None}
    return out


# ── assembling the section ──────────────────────────────────────────────────

def _aligned(a: Dict[Any, float], b: Dict[Any, float]) -> Tuple[List[Any], List[float]]:
    """Dates both series hold, oldest first, and a/b on those dates."""
    days = sorted(set(a) & set(b))
    return days, [a[d] / b[d] for d in days if b[d]]


def _closes(series: Dict[Any, float]) -> Tuple[List[Any], List[float]]:
    days = sorted(series)
    return days, [series[d] for d in days]


def _price_block(series: Dict[Any, float]) -> Dict[str, Any]:
    days, xs = _closes(series)
    state, why = trend_state(xs)
    return {"close": round(xs[-1], 4) if xs else None,
            "as_of": days[-1].isoformat() if days else None,
            "sessions": len(xs), "trend": state, "trend_why": why,
            "changes": window_changes(xs), "move": move_flag(xs)}


def _ratio_block(series: Dict[Any, float], bench: Dict[Any, float]) -> Dict[str, Any]:
    days, ratio = _aligned(series, bench)
    state, why = trend_state(ratio)
    lead = {TREND_UP: LEAD_UP, TREND_DOWN: LEAD_DOWN, TREND_RANGE: LEAD_RANGE}.get(state)
    spark = ratio[-SPARK_SESSIONS:]
    return {"leadership": lead, "leadership_why": why,
            "ratio": round(ratio[-1], 6) if ratio else None,
            "spark": [round(v, 6) for v in spark],
            "spark_from": days[-len(spark)].isoformat() if spark else None,
            "changes": window_changes(ratio), "move": move_flag(ratio)}


def meltdown_line(spy: Dict[Any, float]) -> Dict[str, Any]:
    """SPEC §6: armed when SPY closes 10% or more below its 252-session high.

    THE HIGH INCLUDES TODAY: a close at a new high is 0% below it, not below yesterday's.
    """
    days, xs = _closes(spy)
    n = W.MELTDOWN_HIGH_SESSIONS
    if len(xs) < n:
        return {"armed": None, "text": "Meltdown mode: — (needs %d SPY sessions, has %d)"
                % (n, len(xs)), "drawdown_pct": None}
    hi = max(xs[-n:])
    dd = (xs[-1] / hi - 1.0) * 100.0
    # ROUNDED BEFORE THE TEST: 90/100 - 1 is -9.999999999999998% in floating point, so "10% or
    # more below" would fail to arm at exactly 10%. Six decimals is far below any real move.
    armed = round(dd, 6) <= -W.MELTDOWN_DRAWDOWN_PCT
    if armed:
        text = ("Meltdown mode ARMED: SPY is %.1f%% below its 252-session high (arms at -%.0f%%)"
                % (-dd, W.MELTDOWN_DRAWDOWN_PCT))
    else:
        text = ("Meltdown mode off: SPY is %.1f%% below its 252-session high; it arms at -%.0f%%, "
                "%.1f points further down" % (-dd, W.MELTDOWN_DRAWDOWN_PCT,
                                               W.MELTDOWN_DRAWDOWN_PCT + dd))
    return {"armed": armed, "text": text, "drawdown_pct": round(dd, 2),
            "high_sessions": n, "as_of": days[-1].isoformat()}


# ── RECOVERY RACE (R-IV.1436(e)3, SPEC-B9.md "RECOVERY RACE") ─────────────────────────
#
# The equity markets plus SPY and QQQ, ranked in R-IV.1224's column order. Commodities are OUT
# (R-IV.1220): `b9_world.race_rows` REFUSES one rather than filtering it. SPY and QQQ are ranked
# and marked exactly like every other row, so the panel is as loud when SPY leads as when any
# other market does (the spec's bias check). Display only (#42).

RACE_ANCHOR_WINDOW = 63          # SPY's lowest close of the last 63 sessions ...
RACE_ANCHOR_MIN_AGE = 10         # ... at least 10 sessions old
RACE_FALL_HIGH_SESSIONS = 252    # "fell least" measures from SPY's 252-session high to the anchor
ACCEPT_RUN, ACCEPT_RANGE = 3, 20

#: SPEC-B9.md's footnote, WORD FOR WORD (R-IV.1436(e)3), and the race footnote's SINGLE source
#: (R-IV.1441(b)2): the older `b9_world.RACE_FOOTNOTE` was read by nothing but its own test and is
#: deleted.
RACE_FOOTNOTE_SPEC = ("QUERY's equity-only figures: the leader in each column was still leading "
                      "SPY 6 months later in 8/9, 6/9, 4/8 and 2/9 of past selloffs respectively "
                      "(QUERY R-IV.1221).")

RACE_COLUMNS = (
    ("gained", "Gained most since SPY's low", False,
     "Change from the anchor date (SPY's low) to the latest close."),
    ("back200", "First back above its 200-day", False,
     "A market still above its own 200-day on the day of SPY's low HELD ABOVE: every such market "
     "shares first place, as a tie. Markets that fell below and came back rank after them, in the "
     "order they came back (first close above the 200-day after the anchor). Any still below: "
     "not yet."),
    ("accept", "First to accept higher prices", True,
     "PROXY: the first run of 3 consecutive closes each above the prior 20 sessions' highest "
     "close, after the anchor (the spec's acceptance test, on closes)."),
    ("fell", "Fell least", False,
     "Change from SPY's highest close in the 252 sessions up to the anchor, to the anchor."),
)


def _on_or_before(series: Dict[Any, float], d):
    """The close on `d`, or on the latest date before it; None if there is none."""
    if d in series:
        return series[d]
    prior = [x for x in series if x <= d]
    return series[max(prior)] if prior else None


def _first_back_above_200(series: Dict[Any, float], anchor):
    days, xs = _closes(series)
    if len(xs) < SMA_SLOW:
        return None, "needs %d sessions" % SMA_SLOW
    for i in range(SMA_SLOW - 1, len(xs)):
        if days[i] < anchor:
            continue
        if xs[i] > sma_at(xs, SMA_SLOW, i):
            note = "held above" if days[i] == anchor else None
            return days[i], note
    return None, "not back above its 200-day yet"


def _first_acceptance(series: Dict[Any, float], anchor):
    days, xs = _closes(series)
    run = 0
    for i in range(ACCEPT_RANGE, len(xs)):
        above = xs[i] > max(xs[i - ACCEPT_RANGE:i])
        run = run + 1 if above else 0
        if run >= ACCEPT_RUN and days[i - ACCEPT_RUN + 1] > anchor:
            return days[i], None
    return None, "no acceptance of higher prices since the anchor"


def recovery_race(series: Dict[str, Dict[Any, float]], *, armed=None) -> Dict[str, Any]:
    """The race payload. A missing anchor is a STATE with its reason, not an empty panel."""
    base = {"title": "RECOVERY RACE", "footnote": RACE_FOOTNOTE_SPEC,
            "columns": [{"key": k, "label": lab, "proxy": proxy, "rule": rule}
                        for k, lab, proxy, rule in RACE_COLUMNS],
            "open_by_default": bool(armed),
            "visibility": "Always shown, collapsed by default; opens by default while meltdown "
                          "mode is armed"}
    spy = series.get("SPY") or {}
    spy_days, spy_xs = _closes(spy)
    if len(spy_xs) < RACE_ANCHOR_WINDOW:
        return dict(base, anchor=None, rows=[],
                    reason="needs %d SPY sessions, has %d" % (RACE_ANCHOR_WINDOW, len(spy_xs)))
    lo = len(spy_xs) - RACE_ANCHOR_WINDOW
    low_i = min(range(lo, len(spy_xs)), key=lambda i: spy_xs[i])
    age = len(spy_xs) - 1 - low_i
    anchor = spy_days[low_i]
    anchor_info = {"date": anchor.isoformat(), "spy_close": round(spy_xs[low_i], 2),
                   "sessions_ago": age, "rule": "SPY's lowest close of the last %d sessions, at "
                   "least %d sessions old" % (RACE_ANCHOR_WINDOW, RACE_ANCHOR_MIN_AGE)}
    if age < RACE_ANCHOR_MIN_AGE:
        return dict(base, anchor=dict(anchor_info, valid=False), rows=[],
                    reason="no anchor yet: SPY's %d-session low (%s) is %d session(s) old, and the "
                           "race needs it at least %d sessions old"
                           % (RACE_ANCHOR_WINDOW, anchor.isoformat(), age, RACE_ANCHOR_MIN_AGE))
    hi_lo = max(0, low_i - RACE_FALL_HIGH_SESSIONS + 1)
    peak_i = max(range(hi_lo, low_i + 1), key=lambda i: spy_xs[i])
    peak = spy_days[peak_i]
    anchor_info.update(valid=True, fall_window_from=peak.isoformat())

    racers = W.race_rows([{"ticker": t} for t in W.RACE_UNIVERSE])     # refuses a commodity
    rows = []
    for r in racers:
        t = r["ticker"]
        s = series.get(t)
        row: Dict[str, Any] = {"ticker": t, "name": NAMES.get(t, t)}
        if not s:
            row["missing"] = "no Adj Close history was served for %s" % t
            rows.append(row)
            continue
        days, xs = _closes(s)
        at_anchor, at_peak = _on_or_before(s, anchor), _on_or_before(s, peak)
        row["gained"] = (round((xs[-1] / at_anchor - 1.0) * 100.0, 2) if at_anchor else None)
        row["fell"] = (round((at_anchor / at_peak - 1.0) * 100.0, 2)
                       if at_anchor and at_peak else None)
        d200, why200 = _first_back_above_200(s, anchor)
        dacc, whyacc = _first_acceptance(s, anchor)
        row["back200"] = d200.isoformat() if d200 else None
        row["back200_note"] = why200
        # held: above its 200-day at SPY's low; back: came back after it; not_yet: still below.
        row["back200_status"] = ("not_yet" if d200 is None else
                                 "held" if why200 == "held above" else "back")
        row["accept"] = dacc.isoformat() if dacc else None
        row["accept_note"] = whyacc
        rows.append(row)

    # R-IV.1441(b)1: EQUAL VALUES ARE A TIE, shown as one. Tied markets share a place (competition
    # ranking: 1, 1, 1, 4), are listed alphabetically inside it -- a neutral order, never a second
    # measure, which would imply a race that did not happen -- and every one of them is marked.
    def rank(key, sort_key):
        keyed = sorted(((sort_key(r), r) for r in rows if sort_key(r) is not None),
                       key=lambda kr: (kr[0], kr[1]["ticker"]))
        places, pos = [], 0
        while pos < len(keyed):
            k = keyed[pos][0]
            group = [r for kk, r in keyed[pos:] if kk == k]
            for r in group:
                r.setdefault("ranks", {})[key] = pos + 1
                if len(group) > 1:
                    r.setdefault("ties", {})[key] = True
            places.append({"rank": pos + 1, "tickers": [r["ticker"] for r in group],
                           "tie": len(group) > 1})
            pos += len(group)
        return [r["ticker"] for _, r in keyed], places

    def back200_key(r):
        st = r.get("back200_status")
        return (0, "") if st == "held" else (1, r["back200"]) if st == "back" else None

    ranked = {
        "gained": rank("gained", lambda r: None if r.get("gained") is None else -r["gained"]),
        "back200": rank("back200", back200_key),
        "accept": rank("accept", lambda r: r.get("accept")),
        "fell": rank("fell", lambda r: None if r.get("fell") is None else -r["fell"]),
    }
    order = {k: v[0] for k, v in ranked.items()}
    places = {k: v[1] for k, v in ranked.items()}
    # Every market in first place, so a tie at the top names all of them.
    leaders = {k: (p[0]["tickers"] if p else []) for k, p in places.items()}
    return dict(base, anchor=anchor_info, rows=rows, order=order, places=places, leaders=leaders,
                reason=None)


def build_world(series: Dict[str, Dict[Any, float]], *, as_of=None) -> Dict[str, Any]:
    """The whole section from `series` = {ticker: {date: adj_close}}. Missing tickers are reported,
    never filled. Raises ValueError if the payload breaks B9's lint (fail closed)."""
    missing = [t for t in ALL_TICKERS if not series.get(t)]
    rows, context = [], []
    for t in EQUITIES:
        s = series.get(t)
        row: Dict[str, Any] = {"ticker": t, "name": NAMES[t]}
        if not s:
            row["missing"] = "no Adj Close history was served for %s" % t
            rows.append(row)
            continue
        row["price"] = _price_block(s)
        row["vs"] = {b: (_ratio_block(s, series[b]) if series.get(b)
                         else {"missing": "no %s history to compare against" % b})
                     for b in BENCHMARKS}
        rows.append(row)
    for t in COMMODITIES:
        s = series.get(t)
        context.append({"ticker": t, "name": NAMES[t], **({"price": _price_block(s)} if s else
                        {"missing": "no Adj Close history was served for %s" % t})})
    payload = {
        "basis": W.RETURN_BASIS, "basis_note": W.RETURN_BASIS_NOTE,
        "basis_label": "Adj Close · USD total return (dividends included)",
        "source": "yfinance daily, auto-adjusted (splits and dividends)",
        "as_of": as_of, "rows": rows, "context": context,
        "meltdown": meltdown_line(series["SPY"]) if series.get("SPY") else
                    {"armed": None, "text": "Meltdown mode: — (no SPY history served)",
                     "drawdown_pct": None},
        "flag_rule": ("UNUSUAL |z| ≥ 2, EXTREME |z| ≥ 3: today's %% change over the "
                      "standard deviation of the prior %d daily %% changes, excluding today. "
                      "QUERY measured %s and %s across the universe."
                      % (W.Z_WINDOW, W.FIRES_PER_YEAR[W.UNUSUAL], W.FIRES_PER_YEAR[W.EXTREME])),
        "trend_rule": ("UP: above the 50d and 200d, 50d above 200d, 50d rising over 20 sessions; "
                       "DOWN: the mirror; RANGE: anything else. LEADING / LAGGING: the same "
                       "test on the ratio."),
        "missing": missing,
        "display_only": True,
    }
    payload["race"] = recovery_race(series, armed=(payload["meltdown"] or {}).get("armed"))
    findings = W.lint_findings(payload)
    if findings:
        raise ValueError("B9 payload refused by its own lint: %s" % "; ".join(findings[:5]))
    return payload
