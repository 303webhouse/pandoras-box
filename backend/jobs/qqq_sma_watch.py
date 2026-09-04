"""R-IV.193 — QQQ daily close vs its COMPUTED 200-SMA. D1 pause-rule wiring.

The book's D1 pause rule keys on QQQ crossing its 200-day simple moving average.
This watches for that cross in either direction and alerts, latched.

WHY THE SMA IS COMPUTED, NEVER FROZEN
--------------------------------------
R-IV.193 states 656.59 as an AS-OF REFERENCE, not a constant. The SMA moves every
session; a frozen threshold would be correct on the day it was written and wrong
every day after, and it would drift toward the price rather than tracking it. This
module recomputes from daily closes on every evaluation. Independent computation on
2026-09-03 returned 655.64 against that 656.59 reference — a 0.15% agreement, which
is what confirmed the reference was a real measurement rather than a placeholder.

SECTION 1.1 REGISTRATION (verification-laws.md)
-----------------------------------------------
A registered predicate declares its expected satisfaction rate, is measured against
the registered population, HALTs on mismatch, and where declared and measured agree
at 0% it states the state-change that would move it AND demonstrates that state is
reachable.

  1. DECLARED expected satisfaction: ~0% per evaluation. A 200-SMA cross is a rare
     event; most sessions produce no cross by construction.

  2. MEASURED at registration, 2026-09-03: last close 709.24, 200-SMA 655.64.
     QQQ sits 8.2% ABOVE. Zero crosses in the observation. Declared 0%, measured 0%
     — they AGREE, so clause 4 applies and carries the whole load.

  3. STATE-CHANGE that would move it: QQQ's daily close crossing the 200-SMA in
     either direction. Not a threshold breach — a TRANSITION between sides.

  4. REACHABILITY, DEMONSTRATED not asserted: the SMA recomputes from a rolling
     200-session window every evaluation, so the gap closes from both ends — price
     moves toward the average and the average moves toward price. 224 daily closes
     were confirmed available from the bars path on 2026-09-03, so the computation
     is not blocked. The alarm fires on the transition, and the transition is a
     state this population can actually enter.

     THIS IS THE CLAUSE THAT MAKES IT NOT A NULL TRIGGER. An 8.2% gap is large but
     finite and shrinking or growing daily; contrast a predicate on a 100%-NULL
     column, where no sequence of market events can satisfy it.

WHAT THIS INSTRUMENT DOES WHEN IT CANNOT SEE
---------------------------------------------
It says so. Three states, never two:

  ARMED         a prior side is on record and a cross would be detected
  INSUFFICIENT  no prior side yet, or too few closes — a cross CANNOT be detected
  ERROR         the bars path failed

A cross is a TRANSITION, so a single observation cannot detect one: the first
evaluation has nothing to compare against and must report INSUFFICIENT rather than
silently arming. This is the same discipline as the STRIKE watermark's
INSUFFICIENT n=<k> rendering — silence and health must not look alike, and an
instrument that cannot yet do its job says so on /health rather than returning
nothing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

TICKER = "QQQ"
SMA_PERIOD = 200

# Calendar days to request. The bars path maps days -> from_date via
# today - (days * 1.6 + 5), so 200 yields ~224 trading closes: enough for the
# window plus headroom for holidays and the odd missing bar.
BARS_DAYS = 200

CYCLE_SECONDS = 3600          # hourly; the input is a DAILY close
BOOT_DELAY_SECONDS = 420      # after the other loops settle
SIDE_KEY = "qqq_sma:side"     # durable side-of-record, NOT a latch
COOLDOWN_KEY = "qqq_sma:cross_cooldown"
COOLDOWN_TTL = 86400          # one alert per cross, not per cycle near the line


# ---------------------------------------------------------------------------
# Pure functions — unit-tested without network, redis, or a clock.
# ---------------------------------------------------------------------------

def compute_sma(closes: List[float], period: int = SMA_PERIOD) -> Optional[float]:
    """Simple moving average of the LAST `period` closes.

    Returns None when there are too few closes. Never returns a partial-window
    average: a 47-close '200-SMA' is a different statistic wearing the same name,
    and it would put the cross line in the wrong place while looking valid.
    """
    if closes is None or len(closes) < period:
        return None
    window = closes[-period:]
    return sum(window) / float(period)


def classify_side(close: float, sma: float) -> str:
    """Which side of the average the close sits on.

    A close exactly EQUAL to the SMA is 'below' by convention: the rule is a
    strict above, so equality is not above. Stated because a boundary left to
    float comparison is a boundary nobody chose.
    """
    return "above" if close > sma else "below"


def detect_cross(prior_side: Optional[str], current_side: str) -> Optional[str]:
    """A cross is a TRANSITION between sides, not a position.

    Returns 'up' (below -> above), 'down' (above -> below), or None.
    A missing prior side returns None: with one observation there is nothing to
    have crossed, and reporting a cross from a single reading would manufacture
    an event out of an initial condition.
    """
    if prior_side is None or prior_side == current_side:
        return None
    return "up" if current_side == "above" else "down"


def evaluate(closes: List[float], prior_side: Optional[str]) -> Dict[str, Any]:
    """Full evaluation from closes + prior state. No I/O."""
    sma = compute_sma(closes)
    if sma is None:
        have = 0 if not closes else len(closes)
        return {
            "state": "INSUFFICIENT",
            "reason": "need %d closes, have %d" % (SMA_PERIOD, have),
            "sma": None, "close": None, "side": None, "cross": None,
        }

    close = closes[-1]
    side = classify_side(close, sma)
    cross = detect_cross(prior_side, side)
    state = "ARMED" if prior_side is not None else "INSUFFICIENT"
    reason = None if prior_side is not None else "no prior side on record; a cross needs two observations"

    return {
        "state": state,
        "reason": reason,
        "sma": round(sma, 2),
        "close": round(close, 2),
        "side": side,
        "prior_side": prior_side,
        "cross": cross,
        "distance_pct": round((close - sma) / sma * 100.0, 2),
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

async def _fetch_closes() -> Optional[List[float]]:
    from datetime import date, timedelta
    from integrations.uw_api import get_bars

    today = date.today()
    from_date = (today - timedelta(days=int(BARS_DAYS * 1.6) + 5)).isoformat()
    bars = await get_bars(TICKER, 1, "day", from_date, today.isoformat())
    if not bars:
        return None
    return [b["c"] for b in bars if b.get("c") is not None]


async def qqq_sma_status() -> Dict[str, Any]:
    """Read-only render for /health. Never raises."""
    try:
        from database.redis_client import get_redis_client

        closes = await _fetch_closes()
        if closes is None:
            return {"state": "ERROR", "reason": "bars unavailable", "ticker": TICKER}

        prior = None
        redis = await get_redis_client()
        if redis is not None:
            raw = await redis.get(SIDE_KEY)
            if raw is not None:
                prior = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)

        out = evaluate(closes, prior)
        out["ticker"] = TICKER
        out["closes_available"] = len(closes)
        return out
    except Exception as e:  # noqa: BLE001 -- /health must never 500 on this block
        return {"state": "ERROR", "reason": str(e), "ticker": TICKER}


async def qqq_sma_watch_loop() -> None:
    """R-IV.193 D1 pause-rule watch. Hourly; the input is a daily close."""
    from database.redis_client import get_redis_client

    await asyncio.sleep(BOOT_DELAY_SECONDS)
    logger.info("R-IV.193 QQQ 200-SMA watch started (period=%d, cycle=%ds)",
                SMA_PERIOD, CYCLE_SECONDS)

    while True:
        try:
            closes = await _fetch_closes()
            redis = await get_redis_client()

            if closes is None:
                # An instrument that cannot see says so. Silence here would be
                # indistinguishable from "no cross", which is the failure this
                # whole class of defect is about.
                logger.warning("R-IV.193 QQQ SMA watch: bars unavailable, cannot evaluate")
            elif redis is None:
                logger.warning("R-IV.193 QQQ SMA watch: no redis, cannot hold side-of-record")
            else:
                raw = await redis.get(SIDE_KEY)
                prior = raw.decode() if isinstance(raw, (bytes, bytearray)) else (str(raw) if raw else None)
                r = evaluate(closes, prior)

                if r["state"] == "INSUFFICIENT" and r["sma"] is None:
                    logger.warning("R-IV.193 QQQ SMA watch INSUFFICIENT: %s", r["reason"])
                else:
                    if prior is None:
                        # First observation: record the side, alarm nothing.
                        await redis.set(SIDE_KEY, r["side"])
                        logger.info(
                            "R-IV.193 QQQ SMA watch: side-of-record initialised %s "
                            "(close %.2f vs SMA %.2f, %.2f%%). No cross detectable "
                            "until the next evaluation.",
                            r["side"], r["close"], r["sma"], r["distance_pct"],
                        )
                    elif r["cross"]:
                        cooled = await redis.get(COOLDOWN_KEY)
                        await redis.set(SIDE_KEY, r["side"])
                        if not cooled:
                            from bias_engine.anomaly_alerts import send_alert
                            arrow = "ABOVE" if r["cross"] == "up" else "BELOW"
                            await send_alert(
                                "\U0001F6A8 QQQ crossed its 200-SMA — D1 pause rule",
                                "QQQ daily close %.2f crossed %s the computed 200-SMA %.2f "
                                "(%.2f%%). Prior side %s, now %s. The SMA is recomputed each "
                                "evaluation, not a frozen level. D1 pause rule applies."
                                % (r["close"], arrow, r["sma"], r["distance_pct"],
                                   r["prior_side"], r["side"]),
                                severity="warning",
                            )
                            await redis.set(COOLDOWN_KEY, "1", ex=COOLDOWN_TTL)
                            logger.warning("R-IV.193 QQQ 200-SMA CROSS %s: %s", r["cross"], r)
        except Exception as e:  # noqa: BLE001 -- a fault must not kill the loop
            logger.warning("R-IV.193 QQQ SMA watch error: %s", e)
        await asyncio.sleep(CYCLE_SECONDS)
