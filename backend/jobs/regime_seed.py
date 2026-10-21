"""Seed the regime label history by replaying the classifier over settled closes.

R-IV.1193(d): "Hysteresis needs history. Seed it from a backfill of market_state closes."

WHY A REPLAY AND NOT A TABLE OF GUESSES. The hysteresis rules are about label TRANSITIONS, so
the history they need is a label series. The honest way to produce one for sessions that have
already closed is to compute each session's inputs from bars that existed then and run the same
classifier over them -- not to assert what the label "was".

WHAT BOUNDS THE DEPTH, measured rather than assumed. §2's rows need a 200-day average, so a
session can only be classified if 200 sessions precede it. SPY and IWM each carry 252 daily bars
(read live from hub_get_chart_indicators on 2026-10-17: `bar_count: 252` for both), so

    252 bars - 200 for the 200dma = 52 classifiable sessions

and 52 comfortably covers every hysteresis lookback: 2 closes to enter, 5 to hold, 10 for Range,
15 for Bear's second condition.

NO LOOKAHEAD. Each session is classified from the series UP TO AND INCLUDING that session.
Computing a 200dma over the whole window and reusing it for every session would let a
February label be decided partly by October's prices, which is the quiet form of the mistake
this whole module exists to avoid.

APPEND-ONLY, per §8. A seeded row is never rewritten: a re-run that disagreed with an earlier
one would overwrite the evidence of the disagreement.

#42: the seeded labels drive the card. Nothing gates on them.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from typing import Any, Dict, List, Optional

logger = logging.getLogger("regime_seed")

#: The 200dma is the deepest input any §2 row needs, so it sets the floor.
MIN_BARS_FOR_A_LABEL = 200

#: Which close series a snapshot was computed from. Part of the unique key since R-IV.1203(b)2,
#: because the ruling keeps the old seed and adds a new one: without the source in the key, a
#: re-seed could only happen by deleting, which the ruling forbids.
DEFAULT_CLOSE_SOURCE = "polygon"

#: What the hysteresis needs behind the newest session. The widest lookback in §2's block is
#: Bear's "15 closes below a falling 200dma"; Range's 10 and the 5-session hold sit inside it.
MIN_SEEDED_SESSIONS = 15


def classifiable_sessions(bar_count: int) -> int:
    """How many of `bar_count` sessions can carry a label at all.

    Stated as its own function because it is the number R-IV.1193(d) asks to be reported, and a
    number that is computed inline in a loop is one nobody can quote.

    OFF BY ONE UNTIL THE FIRST LIVE SEED, which reported "seeded 321 of 320 classifiable
    session(s)" -- absurd on its face, and the written count was the correct one. `n - 200`
    assumes the 200th bar cannot carry a label. It can: `latest_moving_averages` returns a
    200dma from EXACTLY 200 closes (measured: 200 closes -> 199.5, 199 closes -> None). So the
    first classifiable session is the 200th, and the count is inclusive.

    The lesson is the same one twice over in this build: the arithmetic and the loop were two
    implementations of one question, and only the loop was right.
    """
    return max(0, int(bar_count) - MIN_BARS_FOR_A_LABEL + 1)


def seed_depth_report(bar_counts: Dict[str, int]) -> Dict[str, Any]:
    """`{sessions, limited_by, sufficient, reason}` for a set of per-ticker bar counts.

    The depth is the MINIMUM across the tickers, because a session the classifier cannot build
    inputs for on every index is not a session it can label.
    """
    if not bar_counts:
        return {"sessions": 0, "limited_by": None, "sufficient": False,
                "reason": "no bar counts supplied"}
    per = {t: classifiable_sessions(n) for t, n in bar_counts.items()}
    worst = min(per, key=lambda t: per[t])
    n = per[worst]
    return {
        "sessions": n,
        "per_ticker": per,
        "limited_by": worst,
        "sufficient": n >= MIN_SEEDED_SESSIONS,
        "reason": ("%d classifiable session(s); the 200dma consumes the first %d bars and %s "
                   "is the shortest series. The hysteresis needs %d."
                   % (n, MIN_BARS_FOR_A_LABEL, worst, MIN_SEEDED_SESSIONS)),
    }


def replay(sessions: List[Dict[str, Any]],
           rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Classify each settled session, then apply hysteresis over the whole series.

    `sessions` is oldest-first; each entry is a complete `inputs` dict for
    `regime_classifier.classify` (its own `as_of`, its own `settled`, and inputs built from bars
    up to that session only).

    Returns `{raw, shown, flips, depth}`. `flips` is §2's only history check -- roughly six or
    fewer label changes a year, and never P&L.
    """
    from models.regime_classifier import classify
    from models.regime_hysteresis import apply_hysteresis, flip_count

    # The inputs ride along with the verdict so a stored row can be re-derived later. A label
    # without the numbers behind it is a claim a reader has to take on trust, and six months from
    # now nobody can rebuild the bar slice that produced it.
    # R-IV.1260(c)2: THE PRIOR LABEL IS INJECTED AS THIS WALK GOES, which the comment in
    # `sessions_from_series` has always claimed happened and which no code did. The builder
    # cannot do it -- it must not import the classifier, because the classifier reads its
    # output -- so it left `prior_regime` None on every row, and `_row_recovery`'s first test
    # ("the prior regime is one of rows 1-4") was therefore False on EVERY session. RECOVERY
    # and BEAR_MARKET_RALLY could not match even with every other input present.
    #
    # THE PRIOR LABEL IS THE PREVIOUSLY *SHOWN* ONE, not the previous raw verdict: "coming out
    # of rows 1-4" means the regime the card was displaying, which is what hysteresis decides.
    # So the hysteresis is re-applied over the rows classified so far at each step -- 302
    # cheap passes -- rather than once at the end, which is also exactly what a live nightly
    # job does one session at a time.
    raw = []
    for s_in in sessions:
        settled_so_far = [r for r in raw if r.get("settled")]
        shown_so_far = apply_hysteresis(settled_so_far, rules) if settled_so_far else []
        prior = shown_so_far[-1].get("shown_regime") if shown_so_far else None
        if s_in.get("prior_regime") is None:
            s_in["prior_regime"] = prior
        if s_in.get("sessions_since_crash") is None:
            # Counted back over the SHOWN series to the last crash label. None when there has
            # never been one in the window: the Bear-rally row reads "within N sessions after a
            # crash", and 0 would read as "a crash today".
            since = None
            for k in range(len(shown_so_far) - 1, -1, -1):
                if shown_so_far[k].get("shown_regime") == "crash_liquidation":
                    since = len(shown_so_far) - 1 - k
                    break
            s_in["sessions_since_crash"] = since
        raw.append(dict(classify(s_in, rules), inputs=s_in))
    # An unsettled session produces no label and must not occupy a slot in the series: the
    # hysteresis counts CLOSES, and a refused session is not one.
    settled = [r for r in raw if r.get("settled")]
    shown = apply_hysteresis(settled, rules)
    return {"raw": raw, "shown": shown, "flips": flip_count(shown), "depth": len(settled)}


async def seed(conn, sessions: List[Dict[str, Any]],
               rules: Optional[Dict[str, Any]] = None, *,
               seeded: bool = True,
               close_source: str = DEFAULT_CLOSE_SOURCE) -> Dict[str, Any]:
    """Write the replayed series to `regime_snapshots`, append-only.

    DELIBERATELY SEPARATE FROM `replay`. The replay is pure and testable; this is the only part
    that touches a database, so a test can exercise every rule in §2 without one -- and the
    dry run R-IV.1193(d) asks for is a `replay` call with no writer attached.

    Returns the depth report plus how many rows were written. `ON CONFLICT DO NOTHING` makes a
    re-run idempotent without rewriting a seeded row (§8: append-only).
    """
    out = replay(sessions, rules)
    written = 0
    conflicts = 0
    for row in out["shown"]:
        # A session before the first label qualified is still WRITTEN, with shown_regime NULL.
        # Skipping it would leave a hole indistinguishable from a session the job never ran on,
        # and that ambiguity is the R-IV.1175 fault.
        r = await _write_snapshot(conn, row, seeded=seeded, close_source=close_source)
        if r is None:
            conflicts += 1
        else:
            written += 1
    out["written"] = written
    out["conflicts"] = conflicts
    logger.info("[regime_seed] replayed %d session(s), wrote %d, %d already present, %d flip(s)",
                out["depth"], written, conflicts, out["flips"])
    return out


def as_date(v):
    """A `datetime.date` for a DATE column, from a date or an ISO string. None stays None.

    THE BOUNDARY NEEDS THIS. Every `as_of` inside the classifier is an ISO STRING, deliberately:
    the verdicts are compared, keyed and replayed as text, and a string cannot be a date object
    that silently carries a timezone. But asyncpg wants a `date` for a DATE column, and handed a
    string it raises `invalid input for query argument $1: '2025-07-10' ('str' object has no
    attribute 'toordinal')` -- which is what the first live seed did, writing nothing.

    This is the exact mirror of the `cut_due` crash in hub_mcp/tools/positions.py, where an
    already-stringified date met `.isoformat()`. Same seam, opposite direction. One conversion
    function at the boundary is the fix in both directions.
    """
    if v is None or isinstance(v, _date):
        return v
    try:
        return _date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


async def _write_snapshot(conn, row: Dict[str, Any], *, seeded: bool,
                          close_source: str = DEFAULT_CLOSE_SOURCE):
    """One append-only snapshot row, or None when (as_of, rules_version) is already present.

    `ON CONFLICT DO NOTHING` makes a re-run idempotent WITHOUT rewriting a row (section 8). A
    re-run that disagrees with an earlier one therefore leaves both the original row and -- via
    the caller's audit entry -- the fact that it disagreed. Overwriting would destroy exactly
    the evidence a disagreement is worth having.

    THE CONFLICT TARGET IS PARTIAL, over CURRENT rows only (R-IV.1288(b)2). The unique index it
    infers became `WHERE superseded = FALSE`, because the unqualified form made the table's own
    supersession mechanism unusable for one (as_of, rules_version, close_source): a superseded
    row still occupied the key, so a corrected label could only be written by UPDATEing the row
    it was correcting -- which is the one thing this function exists not to do. The clause here
    has to match the index or Postgres cannot infer it at all: it raised
    `InvalidColumnReferenceError: there is no unique or exclusion constraint matching the ON
    CONFLICT specification` the first time the index was made partial without it, which is the
    honest failure mode and is why the repair ran in a transaction.
    """
    import json as _json

    return await conn.fetchrow(
        """INSERT INTO regime_snapshots
               (as_of, rules_version, regime, shown_regime, label, tags, basis,
                not_evaluable, settled, pending, pending_closes, held_sessions,
                change, blocked, inputs_json, seeded, close_source)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb,
                   $16, $17)
           ON CONFLICT (as_of, rules_version, close_source) WHERE superseded = FALSE
               DO NOTHING
           RETURNING as_of""",
        as_date(row.get("as_of")), row.get("rules_version"), row.get("regime"),
        row.get("shown_regime"), row.get("label"), list(row.get("tags") or []),
        row.get("basis"), list(row.get("not_evaluable_rows") or []),
        bool(row.get("settled")), row.get("pending"), row.get("pending_closes"),
        row.get("held_sessions"), row.get("change"), row.get("blocked"),
        _json.dumps(row.get("inputs") or {}, default=str), bool(seeded), close_source)
