"""A pure strategy over history, bar by bar (Titans review §11.1).

The strategy function sees ONLY bars up to and including the bar being decided -- it is
handed a slice that ends there, so a lookahead cannot be written by accident. Each trigger
becomes a ShadowRow whose entry is that bar's close (on the series' own basis), and is then
walked forward on the full series with the same grader the shadows use.

The shared-code rule holds by construction: CIRCE'S STEW's `detect` is the function the live
job calls.

WHAT A HISTORY RUN CANNOT INCLUDE, stated so a result is not read as more than it is:
  * CIRCE'S STEW's location gate -- there is no historical prior-session VA (PYTHIA's events
    begin with its live alerts). A history run is the VANILLA trigger.
  * The sector-rotation regime -- not stored historically; not reconstructed here.
  * Flow -- UW history is capped at ~30 trading days (Phase 0 findings); forward only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List

import pandas as pd

from . import basis as B
from . import grade as G
from . import sessions as S


def frame_of(series) -> pd.DataFrame:
    return pd.DataFrame([{"date": d, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
                         for d, b in sorted(series.bars.items())])


def circe_lookback() -> int:
    from scanners import circes_stew as cs
    return cs.N_BARS + cs.CONFIRM_BARS + 2


def circe_triggers(window: pd.DataFrame) -> List[Dict[str, Any]]:
    from scanners import circes_stew as cs
    out = []
    for t in cs.detect(window):
        lv = cs.levels(t)
        out.append({"direction": t.direction, "stop": lv["stop"], "target": lv["target_1"],
                    "tags": {"bars_to_confirm": t.bars_to_confirm, "level": t.level}})
    return out


def run_history(series, triggers_fn: Callable[[pd.DataFrame], List[Dict[str, Any]]],
                lookback_bars: int, max_hold: int, strategy: str) -> List[G.Grade]:
    frame = frame_of(series)
    sessions = S.SeriesSessions(series.dates)
    through = series.last
    grades: List[G.Grade] = []
    for i in range(lookback_bars - 1, len(frame)):
        window = frame.iloc[i - lookback_bars + 1:i + 1]         # ends at the decided bar
        d = window["date"].iloc[-1]
        for trig in triggers_fn(window):
            fired = datetime.combine(d, S.SESSION_CLOSE, tzinfo=S.ET)
            row = G.ShadowRow(f"{strategy}:{series.ticker}:{d.isoformat()}:{trig['direction']}",
                              series.ticker, trig["direction"], fired,
                              float(window["c"].iloc[-1]), trig["stop"], trig["target"],
                              B.ENTRY_SERIES_CLOSE, dict(trig.get("tags") or {}))
            g = G.grade_walk(row, series, max_hold, through, sessions=sessions)
            grades.append(g)
    return grades
