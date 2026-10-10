"""Hermes phase 2's RTH poll — the part that makes the session alarm live.

`webhooks/hermes_session.py` holds the DECISION (pure, tested, calibrated). This holds the
clock, the marks and the state, and is the only piece with a network or a wall-clock in it. The
split is deliberate: the ruling's thresholds were earned by a replay against that pure function,
and a replay cannot drive a module that reads a clock of its own.

STATE IS SESSION-SCOPED, AND THAT IS THE WHOLE DESIGN. The re-alert ladder compares against the
displacement this symbol last alerted at TODAY. Carrying yesterday's figure across the boundary
would silence this morning's first crossing — a −2% Monday after a −2% Friday would be read as
"already told you". So the store is keyed by ET session date and anything from another date is
discarded rather than compared.

ONLY A DELIVERED MESSAGE UPDATES THE LADDER. Phase 1's own rule, for its own reason: recording
an alert that never left would suppress the next real one on the strength of a message nobody
received. A webhook failure therefore leaves the ladder exactly where it was, and the next tick
tries again.

IT SHIPS DARK. `HERMES_SESSION_ALERT_ENABLED` gates the PUSH, not the evaluation: with the flag
off the loop still computes and logs every decision, so the thresholds can be watched against a
live session before anything reaches the phone. That is the useful order — an alarm whose first
real test is its first real alert has never been tested.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("hermes.session.poll")

# Every 60s. The alarm measures a session-to-date figure that moves slowly by construction, so a
# tighter loop would buy nothing and spend quotes; a looser one risks reporting a 2% move several
# minutes after the principal could have acted on it.
POLL_SECONDS = 60

# The name this job records under, so `/health` can show that the alarm is actually running.
# R-IV.864(d) applies gate item 5 to this job: /health's job list is not a registry but whatever
# has RECORDED, so appearing there is earned by a completed pass and cannot be declared.
JOB_NAME = "hermes_session_poll"

# Keyed by ET session date, so a new session starts with an empty ladder.
_session_date: Optional[str] = None
_last_alerted: Dict[str, float] = {}
_prior_close: Dict[str, float] = {}


def reset_for_tests() -> None:
    global _session_date
    _session_date = None
    _last_alerted.clear()
    _prior_close.clear()


def _roll_session(et_date: str) -> bool:
    """Clear the ladder when the session changes. Returns True if it rolled."""
    global _session_date
    if _session_date == et_date:
        return False
    _session_date = et_date
    _last_alerted.clear()
    _prior_close.clear()
    logger.info("[hermes.session] new session %s — ladder cleared", et_date)
    return True


async def _prior_session_close(ticker: str) -> Optional[float]:
    """The PRIOR session's closing price. None when it cannot be established.

    The prior CLOSE, never today's open: a gap IS displacement, and on a gap-down morning the
    move from yesterday's close is exactly what the principal wants to be told about. Measuring
    from the open would hide it — the same reasoning the calibration replay uses, so the live
    alarm and the replay that set its thresholds are answering one question.
    """
    from integrations.uw_api import get_bars

    try:
        bars = await get_bars(ticker, 1, "day")
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[hermes.session] %s prior close unavailable: %s", ticker,
                       type(exc).__name__)
        return None
    closes = [b.get("c") for b in (bars or []) if b.get("c") is not None]
    if len(closes) < 2:
        return None
    # The last bar is today once the session is open, so the prior session is the one before it.
    return float(closes[-2])


async def _mark(ticker: str) -> Optional[float]:
    """The current price, or None. Never a stale fallback.

    A stale mark is worse than no mark here: it would produce a confident displacement from a
    price that is not the price, and `should_alert` has a NOT EVALUABLE branch precisely so this
    can refuse rather than guess.
    """
    try:
        from integrations.uw_api import get_stock_info

        info = await get_stock_info(ticker)
        for key in ("last", "price", "close", "mark"):
            v = (info or {}).get(key)
            if v is not None:
                return float(v)
    except Exception as exc:                                        # noqa: BLE001
        logger.debug("[hermes.session] %s mark unavailable: %s", ticker, type(exc).__name__)
    return None


async def evaluate_once(now: Optional[datetime] = None) -> List[dict]:
    """One pass. Returns a decision per tracked symbol; NEVER RAISES.

    `now` is injectable so a test can place the pass inside or outside a session without
    touching a clock.
    """
    from webhooks.hermes_push import push_session_alert
    from webhooks.hermes_session import (
        SESSION_THRESHOLD_PCT, displacement_pct, in_rth, is_enabled, should_alert,
    )

    now = now or datetime.now(timezone.utc)
    out: List[dict] = []
    if not in_rth(now):
        return out

    from zoneinfo import ZoneInfo
    _roll_session(now.astimezone(ZoneInfo("America/New_York")).date().isoformat())

    # Computed for every symbol BEFORE any push, so a co-breach line can name a symbol whose own
    # message has not been sent yet. Phase 1 learned this the hard way: on 10-08 QQQ's and SMH's
    # webhooks landed ONE SECOND apart, and a backwards-only co-breach lookup meant whichever
    # arrived first could not name the other.
    moves: Dict[str, Optional[float]] = {}
    for sym in sorted(SESSION_THRESHOLD_PCT):
        if sym not in _prior_close:
            pc = await _prior_session_close(sym)
            if pc is not None:
                _prior_close[sym] = pc
        moves[sym] = displacement_pct(_prior_close.get(sym), await _mark(sym))

    for sym, move in moves.items():
        ok, reason = should_alert(sym, move, _last_alerted.get(sym))
        rec = {"ticker": sym, "move_pct": move, "alert": ok, "reason": reason,
               "pushed": False, "enabled": is_enabled()}
        if ok and is_enabled():
            co = [(t, m) for t, m in moves.items()
                  if t != sym and m is not None
                  and abs(m) >= SESSION_THRESHOLD_PCT[t]]
            res = await push_session_alert(sym, move, _prior_close.get(sym), now, co)
            rec["pushed"] = bool(res.get("pushed"))
            rec["push_reason"] = res.get("reason")
            # ONLY a delivered message advances the ladder.
            if rec["pushed"] and move is not None:
                _last_alerted[sym] = move
        elif ok:
            # The flag is off: say what WOULD have gone, so a live session can be watched
            # against the calibrated thresholds before anything reaches the phone.
            logger.info("[hermes.session] WOULD ALERT (flag off): %s", reason)
        out.append(rec)
    return out


async def _recorded_pass() -> dict:
    """One pass, with its result expressed so the job ledger can tell working from blind.

    A pass that ran but could not price ANY symbol is not a success. `evaluate_once` never
    raises, so without this check a UW outage would record a clean pass every minute while the
    alarm saw nothing — /health would read `ok` and the next real displacement would go
    unannounced. That is the failure shape this whole session has been removing: a silence that
    looks like health. `OutputCheckFailed` is the existing word for "the pass completed and
    produced nothing", and it counts toward the flatline alert.
    """
    from jobs.stable_jobs import OutputCheckFailed

    recs = await evaluate_once()
    for rec in recs:
        if rec["alert"]:
            logger.info("[hermes.session] %s", rec)
    if recs and all(r.get("move_pct") is None for r in recs):
        raise OutputCheckFailed(
            "no evaluable displacement for any of %d symbol(s) — alarm is blind" % len(recs))
    return {"symbols": len(recs)}


async def run_forever() -> None:
    """The loop. Catches everything: a notifier that dies takes the next alert with it.

    ONLY AN RTH PASS IS RECORDED. Marking a success at 03:00 would keep the feed looking fresh
    all night on passes that evaluated nothing, so "fresh" would stop meaning "the alarm works".
    The feed is registered RTH-only, so its quiet outside the session is expected rather than
    read as dead.
    """
    from datetime import datetime as _dt

    await asyncio.sleep(45)
    while True:
        try:
            from webhooks.hermes_session import in_rth
            if in_rth(_dt.now(timezone.utc)):
                from jobs import stable_jobs
                await stable_jobs._record(JOB_NAME, _recorded_pass)
            else:
                await evaluate_once()      # a no-op outside RTH; kept so the path stays warm
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[hermes.session] poll error: %s", exc)
        await asyncio.sleep(POLL_SECONDS)
