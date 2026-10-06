"""Which way a position is pointed, and whether a signal agrees. R-IV.568 / R-IV.599(e)1.

ONE AUTHOR, because this was about to become a fourth copy. The direction of a position is
already inferred in `position_risk`, in `leg_payoff`'s structure recogniser and in the committee
prompts, each from its own reading of `structure`. The River's "Your book" lane needs it too, and
a fourth reading would be a fourth chance to disagree about the same row.

THE MAP, from R-IV.599(e)1 verbatim:

    long stock or ETF          bullish
    long call, call debit      bullish
    put credit                 bullish
    long put, put debit        bearish
    call credit                bearish

AN INVERSE ETF IS NOT SPECIAL-CASED, and that is deliberate rather than an oversight. Long SRTY
is a bearish bet on the Russell, but it is a LONG position in SRTY, and the relation is computed
against a signal on the SAME TICKER (R-IV.599(e)1: "Same ticker only for now"). So the
instrument's own direction is the right frame: a LONG signal on SRTY confirms a long SRTY
position, whatever the Russell is doing. Underlying exposure comes later, and it is the only
thing that would want the inverse unwound.

A COMPOSITE STRUCTURE IS READ COMPONENT BY COMPONENT. The book holds
`put_debit_spread+long_put` and `put_debit_spread+put_debit_spread`, joined by `+`. Where every
component agrees, that is the direction. Where they disagree the answer is None -- a hedged or
two-sided position has no single direction, and picking the first component's would state
something nobody chose.

NONE IS A REAL ANSWER throughout. An unrecognised structure yields None and the page says
nothing, rather than a relation computed from a guess. A CONTRADICTS badge on the principal's own
book is not a claim to make on an unread structure.
"""

from __future__ import annotations

from typing import Optional

BULLISH = "bullish"
BEARISH = "bearish"

DIRECTIONS = (BULLISH, BEARISH)

CONFIRMS = "CONFIRMS"
CONTRADICTS = "CONTRADICTS"

RELATIONS = (CONFIRMS, CONTRADICTS)

# Structure component -> direction. Keys are compared lower-cased and stripped.
_COMPONENT: dict = {
    # long the instrument
    "stock": BULLISH,
    "equity": BULLISH,
    "etf": BULLISH,
    "shares": BULLISH,
    "long_stock": BULLISH,
    # long premium, bullish
    "long_call": BULLISH,
    "call_debit_spread": BULLISH,
    "bull_call_spread": BULLISH,
    # short premium, bullish
    "put_credit_spread": BULLISH,
    "bull_put_spread": BULLISH,
    "short_put": BULLISH,
    # long premium, bearish
    "long_put": BEARISH,
    "put_debit_spread": BEARISH,
    "bear_put_spread": BEARISH,
    # short premium, bearish
    "call_credit_spread": BEARISH,
    "bear_call_spread": BEARISH,
    "short_call": BEARISH,
}

# Signal direction words seen in `signals.direction`, both spellings of each side.
_SIGNAL_BULLISH = frozenset({"long", "buy", "bullish", "call"})
_SIGNAL_BEARISH = frozenset({"short", "sell", "bearish", "put"})


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def direction_of_structure(structure: Optional[str]) -> Optional[str]:
    """`bullish`, `bearish`, or None when the structure is unreadable or two-sided."""
    text = _norm(structure)
    if not text:
        return None
    parts = [p.strip() for p in text.split("+") if p.strip()]
    if not parts:
        return None
    seen = set()
    for part in parts:
        found = _COMPONENT.get(part)
        if found is None:
            return None                     # one unreadable component makes the whole unread
        seen.add(found)
    if len(seen) != 1:
        return None                         # two-sided: no single direction
    return seen.pop()


def direction_of_signal(direction: Optional[str]) -> Optional[str]:
    """A signal's side as the same vocabulary, or None."""
    text = _norm(direction)
    if text in _SIGNAL_BULLISH:
        return BULLISH
    if text in _SIGNAL_BEARISH:
        return BEARISH
    return None


def relation(position_structure: Optional[str],
             signal_direction: Optional[str]) -> Optional[str]:
    """`CONFIRMS`, `CONTRADICTS`, or None when either side cannot be read.

    None is returned rather than a default, because both badges are assertions about the
    principal's own book and neither is safe to make on an unread structure.
    """
    pos = direction_of_structure(position_structure)
    sig = direction_of_signal(signal_direction)
    if pos is None or sig is None:
        return None
    return CONFIRMS if pos == sig else CONTRADICTS


def touches_block(position: dict, signal_direction: Optional[str]) -> dict:
    """The `touches` block for one (signal, open position) pair. R-IV.599(e)1.

    `position_direction` is served beside the relation so the page can say WHY a row contradicts,
    and so a null relation is distinguishable from a null direction -- the first means the signal
    was unreadable, the second means the structure was.
    """
    from models.accounts import account_envelope

    structure = position.get("structure")
    return {
        "position_id": position.get("position_id"),
        "structure": structure,
        "position_direction": direction_of_structure(structure),
        "relation": relation(structure, signal_direction),
        # R-IV.660(b)2: HOW MUCH of the book this touches. `open_quantity` is the open
        # remainder, never `quantity` -- a signal contradicting a position the principal has
        # already half sold is a smaller problem than one contradicting the whole of it, and
        # the size opened cannot tell the River which it is. `_basis` travels with it so an
        # unknown remainder is distinguishable from a flat one.
        "open_quantity": position.get("open_quantity"),
        "open_quantity_basis": position.get("open_quantity_basis"),
        # R-IV.632(c)3 / R-IV.633: the account travels with the touch, key AND display
        # name. A touches block that names only the position_id makes ABACUS join back to
        # the book to answer "which account contradicts this signal" -- and with three
        # accounts that question now has three possible answers.
        **account_envelope(position.get("account")),
    }


def exit_block(position: dict) -> dict:
    """The `exit` block for one OPEN position. R-IV.599(e)2.

    `stop` is the `stop_loss` column, which per TA-025 is a LIVE BROKER ORDER, not a mental
    level -- `stop_type` says which kind the written plan calls for, and the two can disagree,
    which is worth seeing rather than reconciling here.

    `written` is False when every field is null, so the page has one thing to test for its
    "No exit written" state instead of testing four.
    """
    fields = {
        "stop": position.get("stop_loss"),
        "stop_type": position.get("stop_type"),
        "invalidation": position.get("invalidation"),
        "time_stop": position.get("time_stop"),
    }
    fields["written"] = any(v is not None for v in fields.values())
    return fields
