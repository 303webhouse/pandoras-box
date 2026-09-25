"""What happened to a signal — ONE fact, in two columns. R-IV.584(e).

THE DEFECT THIS REPLACES. `signals.status` and `signals.user_action` both record what became of
a signal, and five writers each updated the half it happened to care about:

    pipeline._maybe_flag_for_committee   wrote status,      left user_action
    postgres_client.update_signal_action wrote user_action,  left status
    bias_scheduler's hourly 24h sweep    wrote user_action,  left status
    pipeline's conflict-clear            wrote status,       left user_action
    trade_ideas.expire_stale_signals     wrote BOTH -- but only `WHERE status = 'ACTIVE'`

The last line is why nothing ever healed: the only writer that kept the two in step refused to
touch a row that was not ACTIVE, so **a row that drifted out of ACTIVE could never drift back**.
Measured 2026-09-25: 754 rows sat at COMMITTEE_REVIEW, of which 697 the principal had already
dismissed and 53 the age job had already swept — the record of both simply never reached
`status`. Only 4 were genuinely unattended.

So a STATE is written down once here, each state owns BOTH column values, and one writer
(`services.signal_lifecycle`) sets them together with an audit row. Nothing else writes either
column.

WHY NOT COLLAPSE THE TWO COLUMNS. Because 22,000 rows of history are keyed on them and several
readers ask genuinely different questions of each: the legacy feeds' 24-hour ticker hide fires on
`user_action = 'DISMISSED'` and must NOT fire for a system expiry, which is exactly why
R-IV.434(b) had the sweep write 'EXPIRED' rather than 'DISMISSED'. Merging them would either
resurrect that bug or rewrite history. The fix is one AUTHOR, not one column.

WITHHELD IS NEW, and it is the point of R-IV.584(d). When a new signal contradicts a live one on
the same ticker, both sides are withheld from the feed. That was being recorded as a bare
`status = 'DISMISSED'` with no `user_action` at all — indistinguishable from a row the principal
rejected, and invisible to every query keyed on `user_action`, including the hourly sweep that
would later stamp it EXPIRED on top. A withholding is not a dismissal: nobody judged the setup,
the two sides just cannot both be shown. It gets its own state so every query can count it.

HIGH SCORE IS DERIVED, NEVER STORED. R-IV.584(b) retired the auto-promote that moved every
signal scoring 85+ out of ACTIVE into a committee queue nothing drains. The threshold survives as
a FLAG the River can show, computed from the score on read. A stored flag would be a sixth writer
to fall out of step with the column it summarises.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# ── The states ────────────────────────────────────────────────────────────────────────────

ACTIVE = "ACTIVE"
SELECTED = "SELECTED"
DISMISSED = "DISMISSED"
EXPIRED = "EXPIRED"
WITHHELD = "WITHHELD"
ACCEPTED_STOCKS = "ACCEPTED_STOCKS"
ACCEPTED_OPTIONS = "ACCEPTED_OPTIONS"
COMMITTEE_REVIEW = "COMMITTEE_REVIEW"
SHADOW = "SHADOW"

STATES = (ACTIVE, SELECTED, DISMISSED, EXPIRED, WITHHELD, ACCEPTED_STOCKS, ACCEPTED_OPTIONS,
          COMMITTEE_REVIEW, SHADOW)

# ── What each state means in the two columns ──────────────────────────────────────────────
#
# `user_action` answers "did the principal act, and how", and stays NULL when he did not. The
# legacy feeds hide a ticker for 24 hours on `user_action = 'DISMISSED'`, so a state that is not
# his rejection must not write that value (R-IV.434(b)).

_COLUMNS: Dict[str, Tuple[str, Optional[str]]] = {
    ACTIVE:           (ACTIVE, None),
    # The principal said he wants it; no position exists yet. `status` deliberately STAYS
    # ACTIVE -- `api/accept_flow` refuses anything that is not ACTIVE, so moving the status
    # here would block the very next step, creating the position. The state name and the
    # status value are different namespaces on purpose, and this is the case that needs it.
    SELECTED:         (ACTIVE, "SELECTED"),
    DISMISSED:        (DISMISSED, "DISMISSED"),          # the principal rejected it
    EXPIRED:          (EXPIRED, "EXPIRED"),              # nobody acted; the clock ran out
    WITHHELD:         (WITHHELD, "WITHHELD"),            # a same-ticker conflict; nobody judged
    ACCEPTED_STOCKS:  (ACCEPTED_STOCKS, "SELECTED"),
    ACCEPTED_OPTIONS: (ACCEPTED_OPTIONS, "SELECTED"),
    COMMITTEE_REVIEW: (COMMITTEE_REVIEW, None),          # the principal asked for a review
    SHADOW:           (SHADOW, None),                    # never on an actionable surface
}

# Rows the River and the committee may show. Everything else is over, withheld or invisible.
LIVE_STATES = frozenset({ACTIVE})

# Over, one way or another. A reader asking "is this finished" asks HERE rather than writing
# `status != 'ACTIVE'`, which counts SHADOW and WITHHELD rows as outcomes they are not.
TERMINAL_STATES = frozenset({DISMISSED, EXPIRED, WITHHELD, ACCEPTED_STOCKS, ACCEPTED_OPTIONS})

# The values the `status` COLUMN may hold. NOT the same list as STATES: SELECTED is a state whose
# status stays ACTIVE, so generating the database constraint from STATES would permit a status
# value nothing writes. Derived from the pairs, so it cannot drift from them.
STATUS_VALUES = tuple(sorted({s for s, _ in _COLUMNS.values()}))

# The principal decided. Distinct from TERMINAL because EXPIRED and WITHHELD are things that
# happened TO a signal, and counting them as his decisions would misreport every acceptance rate.
DECIDED_STATES = frozenset({SELECTED, DISMISSED, ACCEPTED_STOCKS, ACCEPTED_OPTIONS})

# ── The high-score flag (R-IV.584(b)) ─────────────────────────────────────────────────────

HIGH_SCORE_THRESHOLD = 85.0


def is_high_score(score: Optional[float]) -> bool:
    """True when a signal is one the principal may want reviewed.

    This is the threshold that USED to divert a signal out of the feed entirely. It now only
    marks one, and the row stays ACTIVE. `None` is False, not an error: an unscored signal is not
    a high-scoring one, and raising here would take down a feed over a missing number.
    """
    if score is None:
        return False
    try:
        value = float(score)
    except (TypeError, ValueError):
        return False
    if value != value:                       # NaN, which passes every ordinary guard
        return False
    return value >= HIGH_SCORE_THRESHOLD


def score_of(row) -> Optional[float]:
    """The score a signal is judged on — THE canonical one. R-IV.590(c).

    This used to read `score_v2` then `score`, which is NOT what the feed ranks by. The two
    disagreed on 46 of 54 live rows: DE read 93 by this flag and 85 by the ranking, one card,
    two numbers. It now delegates to `models.signal_score`, which holds the ranking expression
    as one sentence in both SQL and Python, so a flag and an ORDER BY cannot drift again.
    """
    from models.signal_score import canonical_score

    return canonical_score(row)


# ── Reading a state back off a row ────────────────────────────────────────────────────────

def normalize(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def columns_for(state: str) -> Tuple[str, Optional[str]]:
    """The (status, user_action) pair a state writes. Raises on an unknown state."""
    key = normalize(state)
    if key not in _COLUMNS:
        raise ValueError(
            "unknown signal lifecycle state %r; the states are %s" % (state, ", ".join(STATES)))
    return _COLUMNS[key]


def state_of(status: Optional[str], user_action: Optional[str] = None) -> Optional[str]:
    """Which state a stored row is in, or None when the two columns do not agree on one.

    None is a real answer and the reason this exists: 754 rows were in no state at all, and a
    function that guessed from `status` alone would have reported them as awaiting review.
    """
    s, u = normalize(status), normalize(user_action) or None
    for state, (want_s, want_u) in _COLUMNS.items():
        if s == want_s and u == (want_u or None):
            return state
    return None


def is_live(status: Optional[str], user_action: Optional[str] = None) -> bool:
    return state_of(status, user_action) in LIVE_STATES


def is_terminal(status: Optional[str], user_action: Optional[str] = None) -> bool:
    """Deliberately NOT `not is_live(...)`. A row whose columns disagree is in no state, and
    calling that 'terminal' is how 697 dismissed rows stayed parked as though pending."""
    return state_of(status, user_action) in TERMINAL_STATES


# ── The database's own copy of this list ──────────────────────────────────────────────────

def status_check_sql(constraint_name: str = "signals_status_check") -> str:
    """The CHECK constraint, GENERATED from the tuple above rather than retyped.

    A constraint typed by hand is a second author, and the second copy is the one that goes
    stale — a new state would be refused by the database with no hint why.
    """
    values = ", ".join("'" + s + "'" for s in STATUS_VALUES)
    return ("ALTER TABLE signals ADD CONSTRAINT %s CHECK "
            "(status IS NULL OR status IN (%s))" % (constraint_name, values))
