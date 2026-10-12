"""Price plausibility on an incoming signal — R-IV.935(b). LOG-AND-FLAG, NEVER REJECT.

THE DEFECT THIS ANSWERS. ARTEMIS's HAL rows carried entry prices of 3,568–5,088 while every
other strategy on HAL read 31–43, all of them at 04:00 UTC — 09:30 IST, the NSE open. HAL is
also the Indian ticker for Hindustan Aeronautics. The alert was sending a CORRECT price for the
WRONG INSTRUMENT, and the hub accepted it, scored it, and stored it, 46 times over seven months.
CBRE is the same at 02:00–03:00 UTC, 58 rows.

WHY FLAG AND NOT REJECT (R-IV.935(b)1). A reference price is itself a measurement and can be
absent, cached or stale. A gate that drops a signal on a bad reference loses real trades on a
money path — strictly worse than the defect it closes. So nothing here drops anything: the row
is stored exactly as it arrived, with a verdict attached, and only its ACTIONABLE visibility is
withdrawn through the existing `would_suppress` tag.

THE BAND IS 25%. Chosen, not inherited, and the reasoning is that this compares two prices for
the SAME INSTANT — the alert fires now and the reference is read now — so it is not a question
of how far a stock can travel. A same-instant gap of 25% is not a price move; it is a different
instrument. It sits far above any real quote noise, delayed feed or bid/ask straddle, and far
below the 7x (CBRE) and 150x (HAL) this exists to catch. A split cannot trip it either: at fire
time the alert and the reference are on the same side of the split.

NOT A SECOND AUTHOR OF `would_suppress`. The verdict is handed to `evaluate_l0_gate`, which
remains the one function that decides that field. A fact with two writers is the defect this
register keeps finding; this module measures, and the gate decides.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger("pipeline")

#: Same-instant tolerance, as a percentage of the reference price.
BAND_PCT = 25.0

OK = "ok"
IMPLAUSIBLE = "implausible"
UNKNOWN = "unknown"
NOT_CHECKED = "not_checked"

#: Prefixes in scope tonight (R-IV.935(b)1 names the ARTEMIS path). Widening is this list.
IN_SCOPE_PREFIXES = ("ARTEMIS",)


def is_in_scope(signal_type: Optional[str]) -> bool:
    t = (signal_type or "").strip().upper()
    return any(t.startswith(p) for p in IN_SCOPE_PREFIXES)


def evaluate(ticker: Optional[str], incoming: Any, reference: Any) -> Tuple[str, str]:
    """(status, reason). Pure, and NEVER raises.

    An absent reference is `unknown`, never `ok`: "I could not check" and "I checked and it is
    fine" are different facts, and collapsing them is how a blind alarm reports health.
    """
    tkr = (ticker or "?").upper()
    try:
        inc = float(incoming)
    except (TypeError, ValueError):
        return UNKNOWN, "incoming price is not a number (%r)" % (incoming,)
    if inc <= 0:
        return UNKNOWN, "incoming price is not positive (%s)" % inc
    try:
        ref = float(reference)
    except (TypeError, ValueError):
        return UNKNOWN, "no reference price available for %s" % tkr
    if ref <= 0:
        return UNKNOWN, "reference price for %s is not positive (%s)" % (tkr, ref)

    off_pct = abs(inc - ref) / ref * 100.0
    if off_pct > BAND_PCT:
        return IMPLAUSIBLE, (
            "%s price %.4f is %.1f%% from the hub's reference %.4f (band %.0f%%) — "
            "likely a different instrument" % (tkr, inc, off_pct, ref, BAND_PCT))
    return OK, "%s price %.4f within %.1f%% of reference %.4f" % (tkr, inc, off_pct, ref)


async def reference_price(ticker: Optional[str]) -> Optional[float]:
    """The hub's own price reader for this ticker, or None. NEVER raises.

    `get_snapshot` is the hub's governed, cached reader — the same one the Hermes alarm now
    uses. Order: the live last trade, else today's regular-session close, else the prior
    session's. Any of the three answers "what is this ticker worth", which is all that is being
    asked; none of them is allowed to be a guess.
    """
    tkr = (ticker or "").strip().upper()
    if not tkr:
        return None
    try:
        from integrations.uw_api import get_snapshot
    except ImportError:
        logger.error("[price-integrity] get_snapshot is not importable — cannot check prices",
                     exc_info=True)
        return None
    try:
        snap = await get_snapshot(tkr)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[price-integrity] %s reference unavailable: %s", tkr,
                       type(exc).__name__)
        return None
    if not isinstance(snap, dict) or not snap:
        return None
    for path in (("lastTrade", "p"), ("day", "c"), ("prevDay", "c")):
        v = (snap.get(path[0]) or {}).get(path[1])
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


async def check(signal_data: dict) -> Optional[dict]:
    """The verdict for one signal, or None when out of scope. NEVER raises.

    Returns {"status", "reason", "incoming", "reference", "band_pct"} so a later count can be
    taken per ticker without re-deriving anything (R-IV.935(b)3).
    """
    try:
        st = signal_data.get("signal_type")
        if not is_in_scope(st):
            return None
        tkr = signal_data.get("ticker")
        inc = signal_data.get("entry_price")
        ref = await reference_price(tkr)
        status, reason = evaluate(tkr, inc, ref)
        out = {"status": status, "reason": reason, "incoming": inc, "reference": ref,
               "band_pct": BAND_PCT, "signal_type": st, "ticker": tkr}
        if status != OK:
            # LOUD: this is the line that would have made 46 HAL rows visible in March.
            logger.error("[price-integrity] %s %s -> %s: %s", tkr, st, status.upper(), reason)
        return out
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[price-integrity] check failed, treating as unknown: %s",
                       type(exc).__name__)
        return {"status": UNKNOWN, "reason": "check raised %s" % type(exc).__name__,
                "incoming": signal_data.get("entry_price"), "reference": None,
                "band_pct": BAND_PCT, "signal_type": signal_data.get("signal_type"),
                "ticker": signal_data.get("ticker")}
