"""What each shadow collected, and how its cells are named.

Each population reads its rows from `signals` and says, on its face, which price its entry
is, which horizons it is graded at, and what a time exit is called. Cells are computed from
the tags each row carried at grade time -- never from the grade.

  three_ten   Holy_Grail rows tagged by the 3-10 dual gate (R-IV.423(c)): cells rsi / both /
              3-10; A = rsi U both (production), B = both U 3-10 (the candidate).
  pass9       Holy_Grail rows carrying the Pass 9 evidence columns (R-IV.423(b)), written from
              commit 3a79e8d onward. Classes come from the persisted decisions. Earlier rows
              carry none; a reconstruction is not a record and is not read here.
  circes_stew R-IV.421: every geometric trigger, surfaced or not, with the join columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, Optional, Tuple

from . import basis as B
from .grade import ShadowRow

# signals.timestamp is TIMESTAMP NOT NULL, naive UTC (log_signal normalises it); the
# `since` parameter is therefore a naive UTC datetime.
_BASE = """signal_id, ticker, direction, timestamp AS fired_at,
           entry_price, stop_loss, target_1"""


def _three_ten_cells(tags: Dict[str, Any]) -> Tuple[str, ...]:
    g = tags.get("gate_type")
    return {"rsi": ("rsi", "A"), "both": ("both", "A", "B"), "3-10": ("3-10", "B")}.get(g, ())


def pass9_class(v1: Optional[str], v2: Optional[str]) -> Optional[str]:
    if v1 is None or v2 is None:
        return None
    if v1 == v2:
        return "agree_" + v1
    return "v1_suppress_v2_allow" if v1 == "suppress" else "v1_allow_v2_suppress"


def _pass9_cells(tags: Dict[str, Any]) -> Tuple[str, ...]:
    c = pass9_class(tags.get("v1_decision"), tags.get("v2_decision"))
    return (c,) if c else ()


def _circe_cells(tags: Dict[str, Any]) -> Tuple[str, ...]:
    cells = ["surfaced" if tags.get("source") == "circes_stew" else "unsurfaced", "all_triggers"]
    if tags.get("gate_pass") in (True, "true"):
        cells.append("gate_pass")
    return tuple(cells)


@dataclass(frozen=True)
class Population:
    name: str
    select: str                       # WHERE ... (after FROM signals)
    tag_columns: str                  # extra SELECT expressions, aliased
    tag_names: Tuple[str, ...]
    entry_kind: str
    horizons: Tuple[int, ...]
    since: date
    cells: Callable[[Dict[str, Any]], Tuple[str, ...]]
    walk_hold: Optional[int] = None
    time_exit_label: str = "TIME"
    note: str = ""

    def sql(self) -> str:
        return (f"SELECT {_BASE}, {self.tag_columns} FROM signals "
                f"WHERE {self.select} AND timestamp >= $1 ORDER BY timestamp")

    def to_row(self, rec: Dict[str, Any]) -> ShadowRow:
        f = lambda v: float(v) if v is not None else None
        tags = {k: rec.get(k) for k in self.tag_names}
        return ShadowRow(rec["signal_id"], (rec["ticker"] or "").upper(), rec["direction"],
                         rec["fired_at"], f(rec["entry_price"]), f(rec["stop_loss"]),
                         f(rec["target_1"]), self.entry_kind, tags)


THREE_TEN = Population(
    name="three_ten",
    select="strategy = 'Holy_Grail' AND gate_type IN ('rsi', 'both', '3-10') "
           "AND COALESCE(asset_class, 'EQUITY') <> 'CRYPTO'",
    tag_columns="gate_type, signal_type",
    tag_names=("gate_type", "signal_type"),
    entry_kind=B.ENTRY_INTRADAY,
    horizons=(1, 3, 5),
    since=date(2026, 4, 23),
    cells=_three_ten_cells,
    note="R-IV.424 measured 3d and 5d on this population; 1d is added.",
)

PASS9 = Population(
    name="pass9",
    select="strategy = 'Holy_Grail' AND iv_regime_v2 IS NOT NULL "
           "AND COALESCE(asset_class, 'EQUITY') <> 'CRYPTO'",
    tag_columns=("iv_regime_legacy ->> 'decision' AS v1_decision, "
                 "iv_regime_v2 ->> 'decision' AS v2_decision, "
                 "iv_regime_v2 ->> 'mode' AS v2_mode, "
                 "iv_regime_v2 ->> 'gate_version' AS v2_gate_version, "
                 "iv_regime_diverged, gate_type"),
    tag_names=("v1_decision", "v2_decision", "v2_mode", "v2_gate_version",
               "iv_regime_diverged", "gate_type"),
    entry_kind=B.ENTRY_INTRADAY,
    horizons=(1, 3, 5),
    since=date(2026, 9, 17),
    cells=_pass9_cells,
    note="Persisted decisions only (R-IV.423(a)). The 60-day review clock starts at the "
         "first populated row.",
)

CIRCES_STEW = Population(
    name="circes_stew",
    select="strategy = 'circes_stew'",
    tag_columns=("source, va_location, sector_rotation_state, "
                 "(triggering_factors -> 'circes_stew' ->> 'gate_pass')::boolean AS gate_pass, "
                 "triggering_factors -> 'circes_stew' -> 'va' ->> 'zone' AS va_zone, "
                 "triggering_factors -> 'circes_stew' ->> 'gate_version' AS gate_version, "
                 "triggering_factors -> 'circes_stew' -> 'trigger' ->> 'bars_to_confirm' AS bars_to_confirm"),
    tag_names=("source", "va_location", "sector_rotation_state", "gate_pass", "va_zone",
               "gate_version", "bars_to_confirm"),
    entry_kind=B.ENTRY_SESSION_CLOSE,
    horizons=(1, 3, 5, 10),
    since=date(2026, 9, 17),
    cells=_circe_cells,
    walk_hold=10,
    note="Walk hold of 10 sessions is BUILD's proposal, not ruled.",
)

POPULATIONS: Dict[str, Population] = {p.name: p for p in (THREE_TEN, PASS9, CIRCES_STEW)}
