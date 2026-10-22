"""SPY against its 200-day average, as a DISPLAY ROW. R-IV.1309(b)3.

WHAT IT IS AND WHAT IT IS NOT. Nick's decision (2026-10-21 17:25 MT, via TA): no v3b. The card
stays on v2.1 and gains a row that says where SPY sits relative to its 200-day line, how long it
has been there, and by how much. Convention #42: NOTHING COMPUTES FROM THIS. It never changes
the label, never feeds a row of section 2, and never touches the kill switch. It is a sentence a
reader gets to see, which is the whole of its job.

THE DEFINITION IS THE PR-6 BASELINE, STATED EXACTLY, because "above the 200-day" has three
plausible readings and they disagree on the day that matters:

    strict close vs the SMA200 INCLUDING THAT DAY     <- this one
    close vs an SMA200 of the PRIOR 200 sessions      (excludes today, shifts every crossing)
    close vs the 200-day line as of the prior session (the same shift, one day of lag)

They differ by a day at every crossing, and a row that says "ABOVE since 2026-04-14" is wrong if
the comparison it used was not the one named. So the basis is returned beside the figures and
printed in the title, never left to be inferred.

WHY THE RUN IS WALKED RATHER THAN READ OFF A FLAG. "Since when" is a question about history, and
the only honest answer recomputes the relation at each session: the SMA200 moves every day, so a
close that was above the line in April can be below the line that the SAME DAY's average would
now be -- which is exactly why the average is recomputed per session here rather than taken
once from the newest window and applied backwards. That shortcut is the lookahead fault the seed
module warns about in its own docstring, pointed the other way.

NONE RATHER THAN A NUMBER, as everywhere else in this lane. Fewer than 200 closes cannot answer
the question, and a row that reported "BELOW" on a short series would be a claim built from
nothing. A crossing older than the loaded window is reported as such ("at least as long as the
window") instead of being dated to the window's first bar, which would be a fabricated date.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

#: The SMA the row is about. Written once; every reader below uses it.
WINDOW = 200

ABOVE, BELOW = "ABOVE", "BELOW"

#: The comparison, in words, carried on every payload so the figure cannot be read against a
#: definition it did not use.
BASIS = ("strict close vs the SMA%d including that day (the PR-6 baseline definition)" % WINDOW)

#: QUERY's whipsaw line, R-IV.1311(b), verbatim. Small grey text under the row.
#:
#: BOTH ERAS, WHICH IS THE POINT. R-IV.1310 measured 50.00% (19 of 38) since 2013 against
#: 44.79% (43 of 96) since 1999, so the single "45% since 1999" figure this replaces
#: UNDERSTATED the era Nick actually trades -- by five points, on the half of the record that
#: is his. One number over a span that straddles a regime change is an average of two
#: different things, and the reader cannot recover either from it. Conventions #37/#38: the
#: universe and the span travel with the figure, and here there are two of each.
#:
#: NOT a prediction and not a gate -- it is the base rate of what followed an up-cross.
DRIFT_CAVEAT = ("Whipsaw: 50% of up-crosses since 2013 (45% since 1999) hit a new 60-session "
                "low within 60 sessions. (LAB R-IV.1279)")


def _closes(bars: Sequence[Any]) -> List[float]:
    out = []
    for b in bars:
        c = getattr(b, "c", None)
        if c is None:
            continue
        try:
            out.append(float(c))
        except (TypeError, ValueError):
            continue
    return out


def _date_of(bar: Any) -> Optional[str]:
    d = getattr(bar, "date", None)
    return None if d is None else str(d)[:10]


def sides(bars: Sequence[Any], window: int = WINDOW) -> List[Optional[str]]:
    """ABOVE / BELOW / None for each session, oldest-first, aligned with `bars`.

    None for every session before the average can be formed. The SMA is computed over the
    trailing `window` closes INCLUDING the session itself, which is the basis this module
    declares; a rolling sum rather than a re-sum per session, because 503 bars times 200 closes
    is work nobody needs.
    """
    cs = _closes(bars)
    out: List[Optional[str]] = [None] * len(cs)
    if len(cs) < window:
        return out
    run = sum(cs[:window])
    for i in range(window - 1, len(cs)):
        if i >= window:
            run += cs[i] - cs[i - window]
        ma = run / float(window)
        # STRICT. A close exactly ON the average is not above it; `>` is the comparison the
        # baseline names, and `>=` would flip the side on a tie.
        out[i] = ABOVE if cs[i] > ma else BELOW
    return out


def ma200_row(bars: Sequence[Any], window: int = WINDOW) -> Dict[str, Any]:
    """`{available, side, since, sessions, pct, close, ma, basis, caveat}` or a stated refusal.

    `since` is the date of the FIRST session of the current run -- the session on which the
    current side began, not the last session of the previous one. `window_bounded` says the run
    reaches the oldest session the loaded series has, so "since" is a floor rather than the
    crossing date.
    """
    cs = _closes(bars)
    if len(cs) < window:
        return {"available": False,
                "reason": ("%d closes loaded; the SMA%d needs %d"
                           % (len(cs), window, window)),
                "basis": BASIS}

    sd = sides(bars, window)
    side = sd[-1]
    if side is None:                                                # pragma: no cover - guarded above
        return {"available": False, "reason": "the newest session has no side", "basis": BASIS}

    # Walk back while the side is unchanged. `i` lands on the first session OF THIS RUN.
    i = len(sd) - 1
    while i - 1 >= 0 and sd[i - 1] == side:
        i -= 1
    bounded = sd[i - 1] is None if i - 1 >= 0 else True

    run = sum(cs[-window:]) / float(window)
    close = cs[-1]
    pct = ((close - run) / run * 100.0) if run else None

    return {
        "available": True,
        "side": side,
        "since": _date_of(bars[i]),
        "sessions": len(sd) - i,
        "pct": None if pct is None else round(pct, 1),
        "close": round(close, 2),
        "ma": round(run, 2),
        "basis": BASIS,
        "caveat": DRIFT_CAVEAT,
        # The crossing is older than the series this card loads, so the date is a FLOOR. Said
        # out loud rather than dating the run to the window's first bar, which would read as a
        # crossing that did not happen there.
        "window_bounded": bool(bounded),
        "display_only": True,
    }


def row_text(row: Dict[str, Any], ticker: str = "SPY") -> Optional[str]:
    """The sentence the card prints, or None when there is nothing to say.

    Built here rather than in the renderer so the words and the numbers cannot drift apart, and
    so a test can read the exact string a reader sees.
    """
    if not (row or {}).get("available"):
        return None
    pct = row.get("pct")
    sign = "" if pct is None else ("+" if pct >= 0 else "")
    since = row.get("since") or "?"
    return ("%s vs %d-day: %s since %s%s · %s%s%%"
            % (ticker, WINDOW, row.get("side"), "at least " if row.get("window_bounded") else "",
               since, sign, "?" if pct is None else ("%.1f" % pct)))
