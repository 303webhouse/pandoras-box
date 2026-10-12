"""What `log_signal` requires, and what it may legitimately be given as NULL — R-IV.839(b).

THE CLASS OF DEFECT. `log_signal` reached into its argument with brackets for eight fields:
signal_id, strategy, ticker, asset_class, direction, signal_type, entry_price, stop_loss,
target_1. A dict missing any one of them raised KeyError from inside the insert, and every
emitter wraps its call in `except Exception` -- so the row was never written, the exception was
logged at WARNING or swallowed entirely, and the surface showed nothing. A signal type that
never persists looks exactly like a signal type that never fired.

THE DIVIDING LINE IS THE SCHEMA, NOT THE HABIT. Measured against information_schema:

  NOT NULL, no default   timestamp, strategy, ticker, asset_class, direction, signal_type
                         (and signal_id, which this module GENERATES rather than demands)
  NULLABLE               entry_price, stop_loss, target_1, target_2, score, ...

So the three price fields the old code demanded are ones the database has always allowed to be
absent. An ALERT legitimately has no stop and no target -- that is what makes it an alert rather
than a trade setup -- and demanding them is what stopped alert types from ever being stored.
This module hands back NULL for those and raises, by NAME, only for the six the database itself
refuses.

WHY RAISE AT ALL, GIVEN THE POINT IS TO STOP LOSING ROWS. Because a missing `ticker` is not a
row worth storing; it is a broken emitter, and the one thing worse than losing it quietly is
storing something meaningless under a generated id. The difference from before is that the
refusal now names the field and is counted, instead of surfacing as a KeyError nobody reads.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

# The columns the database declares NOT NULL with no default. `timestamp` is included because
# log_signal normalises it to a value -- but a dict with no timestamp at all is still a defect,
# and silently stamping "now" would date a signal to when it was INSERTED rather than when it
# fired, which is the one thing every outcome study depends on.
REQUIRED_FIELDS: Tuple[str, ...] = (
    "timestamp", "strategy", "ticker", "asset_class", "direction", "signal_type",
)

# Nullable in the schema: a type may legitimately lack these, and the old bracket access on the
# first three is exactly what blocked alert types from persisting.
NULLABLE_FIELDS: Tuple[str, ...] = (
    "entry_price", "stop_loss", "target_1", "target_2", "risk_reward", "score",
    "timeframe", "bias_level", "adx", "line_separation", "bias_alignment", "notes",
)

GENERATED_PREFIX = "GEN"


class SignalContractError(ValueError):
    """A dict that cannot become a row. Carries the field names, so the log line is actionable."""

    def __init__(self, missing: List[str], signal_type: Optional[str] = None):
        self.missing = list(missing)
        self.signal_type = signal_type or "UNKNOWN"
        super().__init__(
            "signal of type %s is missing required field(s): %s"
            % (self.signal_type, ", ".join(self.missing))
        )


def missing_required(signal_data: Dict[str, Any]) -> List[str]:
    """Which NOT NULL fields are absent or empty. Order follows REQUIRED_FIELDS, so the message
    reads the same way every time and two reports of one defect are comparable."""
    out = []
    for f in REQUIRED_FIELDS:
        v = signal_data.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            out.append(f)
    return out


def generate_signal_id(signal_data: Dict[str, Any]) -> str:
    """A fresh id for a dict that brought none.

    RANDOM, not derived from the content. A derived id would collide with `ON CONFLICT
    (signal_id) DO NOTHING` -- which is the dedup -- so two genuinely different signals sharing
    a ticker and a minute would silently become one row, and the second would be reported as a
    duplicate rather than lost. An emitter that NEEDS idempotency supplies its own id, as the
    STRIKE converter does with build_signal_id(); this is for the emitter that has no identity
    concept at all, where storing both is the lesser error.
    """
    sym = (signal_data.get("ticker") or "NA").upper()
    kind = (signal_data.get("signal_type") or "NA").upper()
    return "%s_%s_%s_%s" % (GENERATED_PREFIX, kind, sym, uuid.uuid4().hex[:12])


def prepare(signal_data: Dict[str, Any]) -> Tuple[str, bool]:
    """(signal_id, was_generated). Raises SignalContractError when the dict cannot be a row.

    The required check runs BEFORE the id is generated: handing back an id for a dict that is
    about to be refused would invite a caller to log the id as though something had been stored.
    """
    missing = missing_required(signal_data)
    if missing:
        raise SignalContractError(missing, signal_data.get("signal_type"))

    existing = signal_data.get("signal_id")
    if existing is not None and str(existing).strip():
        return str(existing), False
    return generate_signal_id(signal_data), True


def nullable_value(signal_data: Dict[str, Any], field: str) -> Any:
    """What to bind for a nullable column. Absent and explicitly-None are the same thing here,
    and both are NULL rather than 0: a zero stop-loss is a price, and a signal without one has
    no stop at all. The factor-score convention (None, never 0.0) for the same reason."""
    return signal_data.get(field)
