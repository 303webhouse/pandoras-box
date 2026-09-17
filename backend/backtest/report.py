"""Cell reports from graded rows. Pure.

For every (method, horizon) and every cell a population names:
  primary     rows without an excluding flag; the excluded counts are stated beside it
  v2          the series-internal entry variant, same rows (return grades only)
  concentration  the largest fire day's share of the cell's summed return

Population extras:
  three_ten    A (rsi U both) vs B (both U 3-10): the 04-22 bar -- +3pp win rate OR +0.1 PF --
               with day-block and week-block intervals (R-IV.424's method)
  circes_stew  strata by sector_rotation_state, and the promotion gates reported (walk)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

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


def build(pop: Population, rows: List[Dict[str, Any]], reps: int = 5000) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["method"], r["horizon"])].append(r)

    for (method, horizon), grp in sorted(groups.items()):
        cells = defaultdict(list)
        for r in grp:
            for c in pop.cells(r.get("tags") or {}):
                cells[c].append(r)
        kept_by_cell = {}
        for cell, crows in sorted(cells.items()):
            kept, excluded = M.split_by_exclusion(crows)
            kept_by_cell[cell] = kept
            first, last = _span(kept)
            if method == "return":
                summary = M.summarize_returns(kept)
                summary["v2"] = M.summarize_returns(kept, "ret_v2_pct")
            else:
                summary = M.summarize_r(kept)
            summary.update({"excluded": excluded, "graded_rows": len(crows),
                            "fire_days": len({_day(r) for r in kept}),
                            "concentration_day": M.concentration(kept, _day,
                                                                 "ret_pct" if method == "return" else "r_multiple")})
            out.append({"cell": cell, "method": method, "horizon": horizon,
                        "first_anchor": first, "last_anchor": last, "summary": summary})
            if pop.name == "circes_stew":
                strata = M.by_stratum(kept, M.regime_label,
                                      M.summarize_returns if method == "return" else M.summarize_r)
                for label, s in strata.items():
                    out.append({"cell": cell, "method": method, "horizon": horizon,
                                "stratum": label, "first_anchor": first, "last_anchor": last,
                                "summary": s})
                if method == "walk" and cell == "surfaced":
                    out.append({"cell": "surfaced", "method": method, "horizon": horizon,
                                "stratum": "PROMOTION_GATES", "first_anchor": first,
                                "last_anchor": last, "summary": M.circe_promotion_check(kept)})

        if pop.name == "three_ten" and method == "return" and {"A", "B"} <= set(kept_by_cell):
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
            first, last = _span(a + b)
            out.append({"cell": "B_minus_A", "method": method, "horizon": horizon,
                        "stratum": "PROMOTION_QUESTION", "first_anchor": first,
                        "last_anchor": last, "summary": summary})
    return out
