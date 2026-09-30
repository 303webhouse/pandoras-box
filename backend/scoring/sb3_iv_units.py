"""Sub-brief 3 — iv_rank unit conversion (Chunk 1b).

THE MODULE BUILT TO PREVENT A UNIT TRAP ENCODED ONE. Its first line asserted that UW's iv_rank
endpoint returns `iv_rank_1y` as a 0–1 FRACTION, and it multiplied by 100 and CLAMPED the result
to [0, 100]. It was unit-tested against that assumption rather than against the payload.

MEASURED 2026-09-30 on `signals.enrichment_data.iv_rank_uw_shadow`, which this function
produced: **7,553 of 7,606 rows are exactly 100.0**, and 35 more are exactly 0.0 — the two clamp
bounds. Nineteen distinct values in 7,606 readings, since 2026-06-11. The unrelated PROXY rank in
the same column family has 711 distinct values and not one at 100, so the constant is this
conversion and not the market.

A quantity defined on [0, 1] cannot exceed 1 in 99.3% of observations. So `iv_rank_1y` is not a
fraction as it arrives, the x100 is wrong as applied, and the seventeen readings that look
plausible (41.7, 83.6, 55.2 …) are the most misleading of all: each is a raw value BELOW 1
multiplied up, so it reads as a mid-range rank when the raw number was under one percent.

AND THE UNITS ARE NOW SETTLED. Storing the raw value for one session showed 58 of 58 readings
above 1 (4.09 to 100.00, mean 35.06), so `iv_rank_1y` is a PERCENT and the conversion is
identity. The payload's keys, read from the same log, are
`['close', 'date', 'iv_rank_1y', 'updated_at', 'volatility']`.

SO IT REFUSES INSTEAD OF CLAMPING. A clamp turns "this input is not what I was told" into "IV is
at its one-year high", which is a claim, on 7,553 rows. None is the absence of one. The raw value
is stored alongside by callers that can (`triton_flow_shadow.iv_rank_raw`), so the units get
settled by data rather than by this docstring — which is how the original assertion should have
been checked.

Nothing live reads this. `score_v2` computes the shadow bonus under `sb3_shadow` and explicitly
does not add it. But the one-week proxy-vs-true review that this shadow exists to inform — the
one that decides whether the LIVE scorer adopts the UW rank — would have been decided on a
constant.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def iv_rank_1y_to_100(raw) -> Optional[float]:
    """`iv_rank_1y` as a 0–100 rank. IT ARRIVES AS A PERCENT, so this validates rather than scales.

    SETTLED BY MEASUREMENT, 2026-09-30 (R-IV.599(b)2). Storing the raw value for one session
    answered the question the docstring had only asserted: **58 of 58 readings were above 1**,
    ranging 4.09 to 100.00 with a mean of 35.06 — a percent distribution, and a healthy spread
    the clamped column never showed in 7,606 rows.

    So the x100 was wrong, not merely misapplied, and the correct conversion is identity. A value
    outside [0, 100] is still refused: it is not a rank, and the nearest bound is the answer that
    produced the constant.

    A value at or below 1 is taken as a genuine sub-one-percent rank, not as a fraction. The two
    are indistinguishable in a single reading, and the measured floor is 4.09 — so treating 0.5
    as "50%" would be re-introducing the same guess in the other direction.
    """
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v != v:                          # NaN passes every ordinary comparison
        return None
    if not (0.0 <= v <= 100.0):
        logger.warning("iv_rank_1y=%r is outside [0, 100]; refusing it rather than clamping "
                       "(R-IV.599(b))", raw)
        return None
    return round(v, 1)


def iv_bonus_from_rank(iv_rank: Optional[float]) -> int:
    """The scorer's iv_rank banding (0–100). None → 0 (caller labels reason).

    Mirrors score_v2's existing thresholds so the shadow computes the SAME
    bonus the live scorer would, on the new (UW true-rank) value.
    """
    if iv_rank is None:
        return 0
    try:
        v = float(iv_rank)
    except (TypeError, ValueError):
        return 0
    if v <= 20:
        return 3
    elif v <= 40:
        return 1
    elif v <= 60:
        return 0
    elif v <= 80:
        return -2
    return -5
