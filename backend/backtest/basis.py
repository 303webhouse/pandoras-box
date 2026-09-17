"""Putting a raw fire-time price on a fetched series' basis -- and proving it landed there.

WHY NOT JUST APPLY THE VENDOR'S CALENDAR. The calendar and the adjusted bars are the same
vendor's domain (Law 2), and they disagree at least once: HON lists a 0.9535 factor on
2026-06-29 that its stored closes do not carry (CC-QUERY, R-IV.425(a) scope read). Applying
it blindly would put a 4.9% error into every HON grade. So the calendar only PROPOSES
factors; the fire session's own bar decides between them.

THE EVIDENCE (a different quantity from the calendar):
  * an entry that IS a session close (a daily-close signal) must equal that close on the
    same basis, to within CLOSE_TOL;
  * an intraday entry must lie inside the anchor session's range -- widened to take in the
    prior close (pre-open fires, weekend/holiday fires) -- to within RANGE_TOL.
A split-type factor of 1.5x moves a price far outside any daily range. A small factor
(SPGI 1.057, HON 0.9535) can leave more than one candidate inside; then the one nearest the
reference close is taken and the row is flagged `basis_ambiguous`.

EXPOSURE (CC-QUERY's rule): only ex-dates AFTER the anchor session matter. An action on the
anchor date is already in the fire-time price.

The vendor ratio is new-shares-per-old (4.0 for a 4-for-1, 1/12 for a 1-for-12). A split-
adjusted series divides every pre-ex price by it, so the factor for a pre-ex raw price is
1 / (product of ratios).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations
from typing import Dict, List, Optional, Tuple

CLOSE_TOL = 0.005
RANGE_TOL = 0.02
MAX_ENUMERATED_EVENTS = 4

ENTRY_SESSION_CLOSE = "session_close"    # a raw close recorded at fire (CIRCE'S STEW)
ENTRY_INTRADAY = "intraday"              # a raw price seen during/around the session
ENTRY_SERIES_CLOSE = "series_close"      # a close read from THIS series (history runs)


@dataclass
class BasisResolution:
    resolved: bool
    factor: Optional[float]
    entry_basis: Optional[float]
    events_considered: List[Tuple[str, float]] = field(default_factory=list)
    events_applied: List[Tuple[str, float]] = field(default_factory=list)
    fitting_candidates: int = 0
    ambiguous: bool = False
    reason: Optional[str] = None

    def as_dict(self) -> Dict[str, object]:
        return {"resolved": self.resolved, "factor": self.factor,
                "events_considered": self.events_considered,
                "events_applied": self.events_applied,
                "fitting_candidates": self.fitting_candidates,
                "ambiguous": self.ambiguous, "reason": self.reason}

    def unapplied_between(self, start: date, end: date) -> List[Tuple[str, float]]:
        """Calendar events in (start, end] that the series evidently does NOT carry."""
        applied = set(self.events_applied)
        return [e for e in self.events_considered
                if e not in applied and start < date.fromisoformat(e[0]) <= end]


def _subsets(events):
    if len(events) > MAX_ENUMERATED_EVENTS:
        return [(), tuple(events)]
    return [c for k in range(len(events) + 1) for c in combinations(events, k)]


def resolve_entry(entry: float, anchor: date, series, entry_kind: str) -> BasisResolution:
    """Convert a raw entry onto `series`' basis, verified against the anchor bar."""
    events = sorted((d.isoformat(), r) for d, r in series.splits.items() if d > anchor)
    bar = series.bar(anchor)
    if entry is None or entry <= 0:
        return BasisResolution(False, None, None, events, reason="entry_missing")
    if bar is None:
        return BasisResolution(False, None, None, events, reason="no_anchor_bar")

    if entry_kind == ENTRY_SERIES_CLOSE:
        # Already on the series' basis by construction: every later event is in it.
        return BasisResolution(True, 1.0, entry, events, list(events))

    prior = series.prior_close(anchor)
    if entry_kind == ENTRY_SESSION_CLOSE:
        refs = [bar["c"]]
        lo, hi = bar["c"] * (1 - CLOSE_TOL), bar["c"] * (1 + CLOSE_TOL)
    else:
        refs = [bar["c"]] + ([prior] if prior else [])
        lo = min([bar["l"]] + ([prior] if prior else [])) * (1 - RANGE_TOL)
        hi = max([bar["h"]] + ([prior] if prior else [])) * (1 + RANGE_TOL)

    fits = []
    for subset in _subsets(events):
        product = math.prod(r for _, r in subset) if subset else 1.0
        factor = 1.0 / product
        adj = entry * factor
        if lo <= adj <= hi:
            score = min(abs(adj / ref - 1) for ref in refs)
            fits.append((score, len(subset), subset, factor, adj))
    if not fits:
        return BasisResolution(False, None, None, events, reason="entry_outside_anchor_session")
    fits.sort(key=lambda f: (f[0], -f[1]))
    _, _, subset, factor, adj = fits[0]
    return BasisResolution(True, factor, adj, events, list(subset),
                           fitting_candidates=len(fits), ambiguous=len(fits) > 1)


# ── the seam detector (R-IV.428(a)(2); the APH known answer) ────────────────────

SEAM_STEP = 0.25            # a one-day close ratio beyond 1.25 or below 0.80
SEAM_MATCH_TOL = 0.03       # the step equals a split ratio (or its inverse) to within 3%
SEAM_EVENT_WINDOW = (timedelta(days=-7), timedelta(days=45))


@dataclass
class Step:
    before: date
    after: date
    ratio: float
    kind: str                         # adjustment_seam | unexplained_step
    event: Optional[Tuple[str, float]] = None


def find_steps(closes: Dict[date, float], splits: Dict[date, float]) -> List[Step]:
    """One-day steps beyond SEAM_STEP. A step whose size matches a split ratio with an ex-date
    near it is an ADJUSTMENT SEAM -- two adjustment bases meeting inside one stored series,
    which is what a partial refresh after a corporate action produces (APH: the nightly
    rewrote only the last 15 days, so the seam sits ~2 weeks BEFORE the ex-date). Anything
    else is reported as unexplained: large real moves exist, and this does not judge them."""
    out: List[Step] = []
    days = sorted(closes)
    lo_w, hi_w = SEAM_EVENT_WINDOW
    for a, b in zip(days, days[1:]):
        ca, cb = closes[a], closes[b]
        if not ca or not cb:
            continue
        r = cb / ca
        if (1 - SEAM_STEP / (1 + SEAM_STEP)) <= r <= 1 + SEAM_STEP:
            continue
        match = None
        for ex, q in sorted(splits.items()):
            if not (b + lo_w <= ex <= b + hi_w):
                continue
            if abs(r / q - 1) <= SEAM_MATCH_TOL or abs(r * q - 1) <= SEAM_MATCH_TOL:
                match = (ex.isoformat(), q)
                break
        out.append(Step(a, b, round(r, 4), "adjustment_seam" if match else "unexplained_step", match))
    return out
