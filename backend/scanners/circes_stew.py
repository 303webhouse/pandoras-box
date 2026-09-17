"""CIRCE'S STEW | Fade the Breakout — the trigger (R-IV.421, R-IV.429(b)).

Internal id `circes_stew`. Lineage only: Larry Williams' Turtle Soup, Linda Raschke's
close-back-inside refinement (Olympus review 2026-04-22 §2.1). Every new artifact uses the
new name.

SHADOW. Not tradeable, not scored, not sized — surfaced. Promotion is gated on the April
review's bar (Sharpe > 0.8, PF > 1.4, >= 100 trades, VA-edge >= 60% of winners, positive
expectancy in BOTH sector regimes). Shadow visibility is not promotion.

This module is PURE: no I/O. `jobs/circes_stew_job.py` feeds it bars and context.

THE TRIGGER (B2 daily, canonical N = 20, confirmation window 1-4 bars)
    SHORT — a failed breakout UP:
        breach bar B:   high[B] > max(high over the N bars before B)       (level)
        confirmation:   the FIRST close back below `level` lands on the evaluated bar L,
                        with L - B in 0..3 (1-4 bars, the breach bar itself counting as 1)
        fresh breach:   bar B-1 was not itself a breach that closed outside its own level
                        -- otherwise the breakout started before the window and a close
                        back inside after it is not a 1-4 bar failure
    LONG — a failed breakdown: the mirror image on lows.

    Only the LAST bar of the frame is evaluated as the confirmation bar, so a daily run
    fires each failure once, on the day it confirms. Where several breach bars in the
    window qualify, the EARLIEST wins -- "back inside" means inside the range the
    breakout first left.

LOCATION IS PART OF THE TRIGGER (PYTHIA, review consensus item 6)
    The failed extension's extreme is located against the PRIOR session's developing VA
    as it stood before this session opened -- never the current session's, never a
    cumulative one (lookahead). `outside` and `edge` pass the location gate; `mid` does
    not; an unknown location does not pass. Every geometric trigger is persisted either
    way, so the location-quality test can be graded later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

STRATEGY_ID = "circes_stew"
DISPLAY_NAME = "CIRCE'S STEW | Fade the Breakout"
SIGNAL_TYPE = "CIRCES_STEW"          # what the v2 River keys on (SETUP_MAP.CIRCES_STEW)
BANNER = "CIRCE'S STEW · SHADOW — unbacktested, no expectancy measured, do not size."
LINEAGE = "Turtle Soup (Williams; Raschke's close-back-inside refinement)"

N_BARS = 20
CONFIRM_BARS = 4                     # 1-4 bars, the breach bar itself counting as 1
DAILY_CEILING = 10                   # R-IV.421(d): above this the trigger is too loose
VA_EDGE_FRACTION = 0.25              # outer quarter of the VA on each side = "edge";
                                     # PROVISIONAL until 30 fires show its distribution (R-IV.430(a))
LOCATION_GATE = frozenset({"outside", "edge"})
TARGET_R_MULTIPLE = 2.0              # review: "structural ... or fixed R-multiple"

# `source` on the signal row. The River reads SURFACED only; the backtest reads both.
SOURCE_SURFACED = STRATEGY_ID
SOURCE_UNSURFACED = STRATEGY_ID + "_unsurfaced"


@dataclass(frozen=True)
class Trigger:
    direction: str            # SHORT (failed breakout up) | LONG (failed breakdown)
    level: float              # the prior N-bar extreme that was breached
    level_set_date: date      # the bar that set that extreme
    breach_date: date
    fire_date: date           # the close-back-inside bar
    bars_to_confirm: int      # 1..CONFIRM_BARS
    extreme: float            # the failed extension: max high (SHORT) / min low (LONG), breach..fire
    close: float              # close of the fire bar

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("level_set_date", "breach_date", "fire_date"):
            d[k] = d[k].isoformat()
        return d


def _series(frame) -> Tuple[List[date], List[float], List[float], List[float]]:
    """(dates, highs, lows, closes) from a frame with date/h/l/c columns, ascending."""
    rows = frame.sort_values("date")
    return (list(rows["date"]), [float(x) for x in rows["h"]],
            [float(x) for x in rows["l"]], [float(x) for x in rows["c"]])


def _one_direction(dates, highs, lows, closes, n: int, window: int, short: bool) -> Optional[Trigger]:
    last = len(closes) - 1
    ext = highs if short else lows
    for k in range(window - 1, -1, -1):              # earliest breach bar first
        b = last - k
        if b - n - 1 < 0:                            # need B-1's own lookback too
            continue
        prior = ext[b - n:b]
        level = max(prior) if short else min(prior)
        breached = ext[b] > level if short else ext[b] < level
        if not breached:
            continue
        # fresh: bar B-1 must not be a breach that closed outside its own level
        prev_prior = ext[b - 1 - n:b - 1]
        prev_level = max(prev_prior) if short else min(prev_prior)
        prev_breach = ext[b - 1] > prev_level if short else ext[b - 1] < prev_level
        prev_outside = closes[b - 1] >= prev_level if short else closes[b - 1] <= prev_level
        if prev_breach and prev_outside:
            continue
        # every close before the evaluated bar stayed outside; the evaluated bar closes back in
        outside_until_last = all((closes[i] >= level) if short else (closes[i] <= level)
                                 for i in range(b, last))
        back_inside = closes[last] < level if short else closes[last] > level
        if not (outside_until_last and back_inside):
            continue
        span = ext[b:last + 1]
        set_idx = (b - n) + (prior.index(level))
        return Trigger(
            direction="SHORT" if short else "LONG",
            level=level,
            level_set_date=dates[set_idx],
            breach_date=dates[b],
            fire_date=dates[last],
            bars_to_confirm=k + 1,
            extreme=max(span) if short else min(span),
            close=closes[last],
        )
    return None


def detect(frame, n: int = N_BARS, window: int = CONFIRM_BARS) -> List[Trigger]:
    """Triggers confirming on the frame's LAST bar. Empty when there are too few bars."""
    if frame is None or len(frame) < n + window + 1:
        return []
    dates, highs, lows, closes = _series(frame)
    out = []
    for short in (True, False):
        t = _one_direction(dates, highs, lows, closes, n, window, short)
        if t is not None:
            out.append(t)
    return out


def va_location(price: Optional[float], vah: Optional[float], val: Optional[float],
                edge_fraction: float = VA_EDGE_FRACTION) -> Optional[str]:
    """outside | edge | mid, or None when the VA is unusable. Never guessed."""
    if price is None or vah is None or val is None or vah <= val:
        return None
    if price > vah or price < val:
        return "outside"
    band = (vah - val) * edge_fraction
    if price >= vah - band or price <= val + band:
        return "edge"
    return "mid"


def passes_location_gate(location: Optional[str]) -> bool:
    return location in LOCATION_GATE


def structure_hint(iv_rank: Optional[float], direction: str) -> Optional[str]:
    """DAEDALUS: IV rank shapes STRUCTURE, never the trigger. Never a filter."""
    if iv_rank is None:
        return None
    leg = "put" if direction == "SHORT" else "call"
    if iv_rank > 80:
        return f"debit {leg} spread (IV rank {iv_rank:.0f} > 80: contain premium)"
    if iv_rank < 40:
        return f"long {leg} acceptable (IV rank {iv_rank:.0f} < 40)"
    return f"either structure (IV rank {iv_rank:.0f}, 40-80)"


def levels(t: Trigger) -> Dict[str, float]:
    """Entry at the fire close, stop beyond the failed extension, fixed-R target."""
    entry, stop = t.close, t.extreme
    risk = abs(stop - entry)
    target = entry - TARGET_R_MULTIPLE * risk if t.direction == "SHORT" else entry + TARGET_R_MULTIPLE * risk
    return {"entry": round(entry, 4), "stop": round(stop, 4),
            "target_1": round(target, 4), "risk_per_share": round(risk, 4)}


def apply_ceiling(passing: Sequence[Any], ceiling: int = DAILY_CEILING) -> Tuple[List[Any], bool]:
    """R-IV.421(d). Above the ceiling the trigger is too loose: surface NONE that day and
    report the firehose, rather than pick an arbitrary ten. Everything is still persisted."""
    if len(passing) > ceiling:
        return [], True
    return list(passing), False


def signal_id(ticker: str, t: Trigger) -> str:
    """Deterministic, so a re-run of the same day cannot fire twice."""
    return f"CIRCE_{ticker.upper()}_{t.fire_date:%Y%m%d}_{t.direction}"
