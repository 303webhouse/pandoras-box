"""Cell reports from graded rows. Pure.

For every (method, horizon) and every cell a population names:
  ALL        rows without an excluding flag
  EXCLUDED   the rows an excluding flag kept out, summarised on their OWN line with the flag
             counts -- counted, never silently dropped (R-IV.432(c))
  HELD       rows the second vendor disagreed with: counted by reason, never graded
             (R-IV.432(e))
Each ALL line also carries the v2 (series-internal entry) variant and the largest fire day's
share of the cell's summed result.

Population extras:
  three_ten    A (rsi U both) vs B (both U 3-10): the 04-22 bar -- +3pp win rate OR +0.1 PF --
               with day-block and week-block intervals (R-IV.424's method)
  circes_stew  strata by sector_rotation_state; the HOLD_CURVE (every walk hold side by side,
               R-IV.432(a)); and the promotion gates REPORTED on the primary hold
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Sequence

from . import metrics as M
from .populations import Population

BAR_WIN_RATE_PP = 3.0
BAR_PF = 0.1


def _day(r):
    return r["anchor_session"]


def _week(r):
    return M.week_of(r["anchor_session"])


def _span(rows):
    days = [r["anchor_session"] for r in rows]
    return (min(days), max(days)) if days else (None, None)


def _summarize(method: str, rows):
    return M.summarize_returns(rows) if method == "return" else M.summarize_r(rows)


def _line(cell, method, horizon, summary, rows, stratum="ALL"):
    first, last = _span(rows)
    return {"cell": cell, "method": method, "horizon": horizon, "stratum": stratum,
            "first_anchor": first, "last_anchor": last, "summary": summary}


def build(pop: Population, rows: List[Dict[str, Any]], holds: Sequence[Dict[str, Any]] = (),
          reps: int = 5000) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["method"], r["horizon"])].append(r)
    held = defaultdict(Counter)
    for h in holds:
        for c in pop.cells(h.get("tags") or {}):
            held[(h["method"], h["horizon"], c)][h["reason"]] += 1

    kept_walk: Dict[int, Dict[str, list]] = defaultdict(dict)
    for (method, horizon), grp in sorted(groups.items()):
        cells = defaultdict(list)
        for r in grp:
            for c in pop.cells(r.get("tags") or {}):
                cells[c].append(r)
        kept_by_cell = {}
        for cell, crows in sorted(cells.items()):
            kept, excluded_counts = M.split_by_exclusion(crows)
            kept_ids = {id(r) for r in kept}
            excluded = [r for r in crows if id(r) not in kept_ids]
            kept_by_cell[cell] = kept
            if method == "walk":
                kept_walk[horizon][cell] = kept
            metric = "ret_pct" if method == "return" else "r_multiple"
            summary = _summarize(method, kept)
            if method == "return":
                summary["v2"] = M.summarize_returns(kept, "ret_v2_pct")
            summary.update({"graded_rows": len(crows), "excluded_rows": len(excluded),
                            "held_rows": sum(held[(method, horizon, cell)].values()),
                            "fire_days": len({_day(r) for r in kept}),
                            "concentration_day": M.concentration(kept, _day, metric)})
            out.append(_line(cell, method, horizon, summary, kept))
            if excluded:
                ex = _summarize(method, excluded)
                ex["excluded_by_flag"] = excluded_counts
                out.append(_line(cell, method, horizon, ex, excluded, "EXCLUDED"))
            if held[(method, horizon, cell)]:
                out.append(_line(cell, method, horizon,
                                 {"n": 0, "held_by_reason": dict(held[(method, horizon, cell)])},
                                 [], "HELD"))
            if pop.name == "circes_stew":
                for label, s in M.by_stratum(kept, M.regime_label,
                                             lambda v, m=method: _summarize(m, v)).items():
                    out.append(_line(cell, method, horizon, s, kept, label))
                if method == "walk" and cell == "surfaced" and horizon == pop.primary_hold:
                    out.append(_line(cell, method, horizon, M.circe_promotion_check(kept), kept,
                                     "PROMOTION_GATES"))

        if pop.name == "three_ten" and method == "return" and {"A", "B"} <= set(kept_by_cell):
            out.append(_promotion_question(kept_by_cell, method, horizon, reps))

    if pop.walk_holds and len(pop.walk_holds) > 1:
        for cell in sorted({c for per in kept_walk.values() for c in per}):
            curve = {str(h): M.summarize_r(kept_walk.get(h, {}).get(cell, []))
                     for h in sorted(pop.walk_holds)}
            rows_primary = kept_walk.get(pop.primary_hold, {}).get(cell, [])
            out.append(_line(cell, "walk", pop.primary_hold,
                             {"primary_hold": pop.primary_hold, "by_hold": curve},
                             rows_primary, "HOLD_CURVE"))
    return out


def _promotion_question(kept_by_cell, method, horizon, reps):
    a, b = kept_by_cell["A"], kept_by_cell["B"]
    sa, sb = M.summarize_returns(a), M.summarize_returns(b)
    d_wr = (sb.get("hit") or 0) - (sa.get("hit") or 0)
    d_pf = None if sa.get("pf") is None or sb.get("pf") is None else sb["pf"] - sa["pf"]
    summary = {
        "A": sa, "B": sb,
        "delta_win_rate_pp": round(d_wr, 4),
        "delta_pf": None if d_pf is None else round(d_pf, 4),
        "bar": {"win_rate_pp": BAR_WIN_RATE_PP, "pf": BAR_PF},
        "bar_met": d_wr >= BAR_WIN_RATE_PP or (d_pf is not None and d_pf >= BAR_PF),
        "win_rate_day_block": M.block_bootstrap_delta(a, b, M.hit_stat, _day, reps, bar=BAR_WIN_RATE_PP),
        "win_rate_week_block": M.block_bootstrap_delta(a, b, M.hit_stat, _week, reps, bar=BAR_WIN_RATE_PP),
        "pf_day_block": M.block_bootstrap_delta(a, b, M.pf_stat, _day, reps, bar=BAR_PF),
        "pf_week_block": M.block_bootstrap_delta(a, b, M.pf_stat, _week, reps, bar=BAR_PF),
        "b_share_both": round(100 * len(kept_by_cell.get("both", [])) / len(b), 2) if b else None,
    }
    return _line("B_minus_A", method, horizon, summary, a + b, "PROMOTION_QUESTION")
