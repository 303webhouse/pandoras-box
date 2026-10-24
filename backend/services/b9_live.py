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
    findings = W.lint_findings(payload)
    if findings:
        raise ValueError("B9 payload refused by its own lint: %s" % "; ".join(findings[:5]))
    return payload
