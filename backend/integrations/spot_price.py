"""The current spot, sourced the way `hub_get_quote` sources it — one author.

WHY THIS MODULE EXISTS. Three places need nothing but "what is this ticker worth right now", and
all three reached for `get_snapshot()`:

    services/read_only/options_chain.py   the chain's spot (TA-160 §2)
    jobs/b2_cut_alert_job.py              the B2 cut's mark for a stock row
    jobs/hermes_session_poll.py           the session alarm's mark

`get_snapshot()` cannot answer that question reliably, and the reason is structural rather than
occasional: it makes a SECOND UW call -- `/ohlc/1d` under caller `ohlc_bars`, for the
regular-session change -- and that caller has been observed governor-BLOCKED at 625/625. So a
request for one number depended on two calls, one of which is refused. Measured consequences,
both on 2026-10-13:

  * the options chain returned `spot: null` and therefore EVERY greek null, on KRE and HYG,
    while `hub_get_quote` returned a live spot in the same minute;
  * the B2 cut's run-time read returned NO mark for TSLQ (`mark_integrity = "unknown"`), which
    under TA-161 means the cut cannot be evaluated at all.

`/api/stock/{t}/stock-state` answers it in ONE call -- field `close`, which is exactly the spot
`hub_get_quote` serves -- and the same response carries `tape_time`, the vendor's own stamp. One
response, so a price and its timestamp can never come from different moments.

THE POINT OF PUTTING IT HERE: I fixed the chain first and left the other two, which is how one
root cause becomes three bugs with three different fixes. The question has one author now.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

#: Source labels, returned beside the price so a caller can be honest about provenance.
SRC_STOCK_STATE = "stock_state"
SRC_SNAPSHOT = "snapshot_fallback"
SRC_NONE = "unavailable: /stock-state and snapshot both gave no price"


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


async def spot_now(ticker: str, *, caller: str = "snapshot") -> Tuple[Optional[float], str, Optional[str]]:
    """(price, source, vendor_timestamp). NEVER raises.

    `vendor_timestamp` is the vendor's own `tape_time` when one came back, and None otherwise --
    never a server clock dressed as a vendor reading.

    Order: /stock-state (one call, what hub_get_quote serves) then get_snapshot (two calls, and
    the second is frequently blocked). The fallback is kept rather than dropped because when it
    DOES answer it answers with a real price, and a caller with a price beats a caller with none.
    """
    tkr = (ticker or "").strip().upper()
    if not tkr:
        return None, SRC_NONE, None

    try:
        from integrations.uw_api import _uw_request
        resp = await _uw_request("/api/stock/%s/stock-state" % tkr, caller=caller)
        if isinstance(resp, dict) and isinstance(resp.get("data"), dict):
            state = resp["data"]
            px = _num(state.get("close"))
            if px is not None:
                ts = state.get("tape_time")
                return px, SRC_STOCK_STATE, (str(ts) if ts else None)
    except Exception as exc:                                        # noqa: BLE001
        logger.debug("spot_now: /stock-state unavailable for %s: %s", tkr, type(exc).__name__)

    try:
        from integrations.uw_api import get_snapshot
        snap = await get_snapshot(tkr)
        if isinstance(snap, dict) and snap:
            px = _num((snap.get("lastTrade") or {}).get("p"))
            if px is not None:
                return px, SRC_SNAPSHOT, None
    except Exception as exc:                                        # noqa: BLE001
        logger.debug("spot_now: snapshot fallback failed for %s: %s", tkr, type(exc).__name__)

    logger.warning("spot_now: NO spot for %s — both sources gave nothing", tkr)
    return None, SRC_NONE, None
