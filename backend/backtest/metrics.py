"""Summaries. Pure functions over graded rows (dicts with the Grade fields + tags).

DEFINITIONS, stated because a number without one gets compared with a different number:
  hit        share of rows with ret_pct > 0 (a zero return is not a hit)
  PF         sum of positive ret_pct / |sum of negative ret_pct|; None when there are no losses
  excess     mean aligned return - mean long-side (raw) return of the SAME rows; None for a
             direction-pure cell, where it is identically zero
  R metrics  over walk grades: win = r_multiple > 0
  Sharpe     annualised from DAILY R: R summed by exit session over every trading session from
             the first exit to the last (zeros included), mean / sd * sqrt(252)
  max DD     largest peak-to-trough fall of cumulative R, rows in exit order

DEPENDENCE. Rows that fire on the same day are not independent (R-IV.424: 4,982 rows, 102 fire
days). Every interval on a DELTA is a block bootstrap over fire days or fire weeks -- never
over rows.

STRATA (R-IV.430(b)). Promotion regimes: concentrated = CONCENTRATED_LEADERSHIP, rotating =
BROAD_ROTATION. ACTIVE_DISTRIBUTION and REGIME_AGNOSTIC are their own strata, never folded in;
a row with no label is UNLABELLED (BUILD's reading, not ruled).
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

PROMOTION_REGIMES = {"concentrated": "CONCENTRATED_LEADERSHIP", "rotating": "BROAD_ROTATION"}
OWN_STRATA = ("ACTIVE_DISTRIBUTION", "REGIME_AGNOSTIC")
UNLABELLED = "UNLABELLED"

# Flags that keep a row out of the primary aggregates. Counted and reported, never dropped
# silently -- the excluded rows are still in shadow_grades.
EXCLUDING_FLAGS = frozenset({"unapplied_event_in_window", "adjustment_seam_in_window", "quarantined"})


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(100 * (centre - half), 2), round(100 * (centre + half), 2)


def split_by_exclusion(rows: Iterable[Dict[str, Any]]):
    kept, excluded = [], defaultdict(int)
    for r in rows:
        bad = [f for f in (r.get("flags") or []) if f in EXCLUDING_FLAGS]
        if bad:
            for f in bad:
                excluded[f] += 1
        else:
            kept.append(r)
    return kept, dict(excluded)


def profit_factor(values: Sequence[float]) -> Optional[float]:
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    return round(gains / losses, 4) if losses > 0 else None


def summarize_returns(rows: Sequence[Dict[str, Any]], field: str = "ret_pct") -> Dict[str, Any]:
    vals = [r[field] for r in rows if r.get(field) is not None]
    n = len(vals)
    if n == 0:
        return {"n": 0}
    k = sum(1 for v in vals if v > 0)
    lo, hi = wilson(k, n)
    out = {"n": n, "hit": round(100 * k / n, 2), "hit_ci": [lo, hi],
           "mean": round(statistics.fmean(vals), 4), "median": round(statistics.median(vals), 4),
           "pf": profit_factor(vals)}
    signs = {r.get("direction_sign") for r in rows}
    raws = [r["ret_raw_pct"] for r in rows if r.get("ret_raw_pct") is not None]
    out["excess"] = (round(out["mean"] - statistics.fmean(raws), 4)
                     if len(signs) > 1 and len(raws) == n else None)
    return out


def _sessions_between(first: date, last: date, sessions: Optional[Sequence[date]]) -> List[date]:
    """Trading sessions in [first, last]: from the calendar (which raises past its range --
    never a weekday guess), or from a history run's own vendor dates."""
    if sessions is not None:
        return [d for d in sessions if first <= d <= last]
    from stable_engine.market_calendar import is_trading_day
    out, d = [], first
    while d <= last:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def summarize_r(rows: Sequence[Dict[str, Any]], sessions: Optional[Sequence[date]] = None
                ) -> Dict[str, Any]:
    rs = [(r["target_session"], r["r_multiple"]) for r in rows
          if r.get("r_multiple") is not None and r.get("target_session") is not None]
    n = len(rs)
    if n == 0:
        return {"n": 0}
    rs.sort(key=lambda x: x[0])
    vals = [v for _, v in rs]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    peak = cum = mdd = 0.0
    for v in vals:
        cum += v
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    daily = defaultdict(float)
    for d, v in rs:
        daily[d] += v
    series = [daily.get(d, 0.0) for d in _sessions_between(rs[0][0], rs[-1][0], sessions)]
    sharpe = None
    if len(series) > 1 and statistics.pstdev(series) > 0:
        sharpe = round(statistics.fmean(series) / statistics.pstdev(series) * math.sqrt(252), 4)
    return {"n": n, "win_rate": round(100 * len(wins) / n, 2),
            "avg_win_r": round(statistics.fmean(wins), 4) if wins else None,
            "avg_loss_r": round(statistics.fmean(losses), 4) if losses else None,
            "expectancy_r": round(statistics.fmean(vals), 4),
            "pf_r": profit_factor(vals), "max_dd_r": round(mdd, 4), "sharpe": sharpe,
            "sharpe_definition": "daily R over trading sessions first..last exit, sqrt(252)"}


def week_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def block_bootstrap_delta(a: Sequence[Dict[str, Any]], b: Sequence[Dict[str, Any]],
                          stat: Callable[[Sequence[Dict[str, Any]]], Optional[float]],
                          block: Callable[[Dict[str, Any]], Any],
                          reps: int = 5000, seed: int = 424, bar: Optional[float] = None
                          ) -> Dict[str, Any]:
    """stat(b) - stat(a), with blocks resampled jointly for both cells."""
    by_a, by_b = defaultdict(list), defaultdict(list)
    for r in a:
        by_a[block(r)].append(r)
    for r in b:
        by_b[block(r)].append(r)
    keys = sorted(set(by_a) | set(by_b))
    point_a, point_b = stat(a), stat(b)
    point = None if point_a is None or point_b is None else point_b - point_a
    rng = random.Random(seed)
    deltas = []
    agg = getattr(stat, "agg", None)
    if agg is not None:
        # A decomposable statistic: sum each block once, then each rep adds block totals.
        # Same picks, same values as the row path below (tested) -- O(blocks) per rep.
        contrib, finish = agg

        def totals(rows):
            acc = [0.0, 0.0]
            for r in rows:
                x, y = contrib(r)
                acc[0] += x
                acc[1] += y
            return acc

        ta = {k: totals(v) for k, v in by_a.items()}
        tb = {k: totals(v) for k, v in by_b.items()}
        zero = (0.0, 0.0)
    for _ in range(reps):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        if agg is not None:
            sa = finish([sum(ta.get(k, zero)[i] for k in pick) for i in (0, 1)])
            sb = finish([sum(tb.get(k, zero)[i] for k in pick) for i in (0, 1)])
        else:
            sa = stat([r for k in pick for r in by_a.get(k, ())])
            sb = stat([r for k in pick for r in by_b.get(k, ())])
        if sa is not None and sb is not None:
            deltas.append(sb - sa)
    if not deltas:
        return {"delta": point, "ci": None, "blocks": len(keys)}
    deltas.sort()
    lo = deltas[int(0.025 * (len(deltas) - 1))]
    hi = deltas[int(0.975 * (len(deltas) - 1))]
    out = {"delta": None if point is None else round(point, 4),
           "ci": [round(lo, 4), round(hi, 4)], "blocks": len(keys), "reps": len(deltas),
           "seed": seed}
    if bar is not None:
        out["p_at_or_above_bar"] = round(sum(1 for d in deltas if d >= bar) / len(deltas), 4)
    return out


def hit_stat(rows):
    vals = [r["ret_pct"] for r in rows if r.get("ret_pct") is not None]
    return 100 * sum(1 for v in vals if v > 0) / len(vals) if vals else None


def pf_stat(rows):
    return profit_factor([r["ret_pct"] for r in rows if r.get("ret_pct") is not None])


def _hit_contrib(r):
    v = r.get("ret_pct")
    return (0.0, 0.0) if v is None else (1.0, 1.0 if v > 0 else 0.0)


def _pf_contrib(r):
    v = r.get("ret_pct")
    return (0.0, 0.0) if v is None else (max(v, 0.0), max(-v, 0.0))


hit_stat.agg = (_hit_contrib, lambda s: 100 * s[1] / s[0] if s[0] else None)
pf_stat.agg = (_pf_contrib, lambda s: round(s[0] / s[1], 4) if s[1] > 0 else None)


def concentration(rows: Sequence[Dict[str, Any]], block: Callable, field: str = "ret_pct"):
    """The largest block's share of the cell's summed return (can exceed 100%)."""
    total = sum(r[field] for r in rows if r.get(field) is not None)
    per = defaultdict(float)
    counts = defaultdict(int)
    for r in rows:
        if r.get(field) is not None:
            per[block(r)] += r[field]
            counts[block(r)] += 1
    if not per or total == 0:
        return None
    k = max(per, key=lambda x: abs(per[x]))
    return {"block": str(k), "n": counts[k], "sum": round(per[k], 4),
            "share_pct": round(100 * per[k] / total, 1)}


def regime_label(row: Dict[str, Any]) -> str:
    return (row.get("tags") or {}).get("sector_rotation_state") or UNLABELLED


def by_stratum(rows: Sequence[Dict[str, Any]], key: Callable[[Dict[str, Any]], str],
               summarize: Callable) -> Dict[str, Any]:
    groups = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}


CIRCE_GATES = {"sharpe_gt": 0.8, "pf_gt": 1.4, "min_trades": 100, "va_edge_share_of_winners": 60.0}


def circe_promotion_check(walk_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """R-IV.421(f), with R-IV.430(b)'s labels stated on the face. This REPORTS the gates; it
    promotes nothing. "VA edge" means EDGE + OUTSIDE (R-IV.432(b)) -- both are the extension
    case the review meant; mid was the reject. The split is reported beside it."""
    overall = summarize_r(walk_rows)
    winners = [r for r in walk_rows if (r.get("r_multiple") or 0) > 0]
    loc = lambda r: (r.get("tags") or {}).get("va_location")
    edge = sum(1 for r in winners if loc(r) == "edge")
    outside = sum(1 for r in winners if loc(r) == "outside")
    share = lambda k: round(100 * k / len(winners), 2) if winners else None
    regimes = {name: summarize_r([r for r in walk_rows if regime_label(r) == label])
               for name, label in PROMOTION_REGIMES.items()}
    others = {label: summarize_r([r for r in walk_rows if regime_label(r) == label])
              for label in OWN_STRATA + (UNLABELLED,)}
    checks = {
        "sharpe": overall.get("sharpe") is not None and overall["sharpe"] > CIRCE_GATES["sharpe_gt"],
        "pf": overall.get("pf_r") is not None and overall["pf_r"] > CIRCE_GATES["pf_gt"],
        "trades": overall.get("n", 0) >= CIRCE_GATES["min_trades"],
        "va_edge": bool(winners) and share(edge + outside) >= CIRCE_GATES["va_edge_share_of_winners"],
        "both_regimes_positive": all((regimes[k].get("expectancy_r") or 0) > 0 and regimes[k].get("n")
                                     for k in PROMOTION_REGIMES),
    }
    return {"overall": overall, "checks": checks, "all_met": all(checks.values()),
            "va_edge_share_of_winners": share(edge + outside),
            "va_edge_definition": "edge + outside (R-IV.432(b))",
            "va_split_of_winners": {"edge": share(edge), "outside": share(outside),
                                    "other_or_unknown": share(len(winners) - edge - outside)},
            "regimes": regimes, "regime_labels": PROMOTION_REGIMES, "other_strata": others}
