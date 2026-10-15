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

# R-IV.1058(b): THIS JOB'S OWN UW CALLER TAG.
#
# It used to spend under `snapshot`, which also funds MTM, quote and the macro strip on a
# 1,100/day quota measured in September, before this job existed. Measured outcome: the tag hit
# 1,106 on 2026-10-13 and pinned at 1,100 on 2026-10-14, where it ran out at 17:47:08Z and this
# job then failed 133 times -- once a minute to the 16:00 ET close -- reporting "alarm is
# blind". UW's own limiter never fired (429s = 0 on every row); the governor was blocking an
# under-funded tag, which is what it is for.
#
# Its own tag does two things: the spend becomes visible per consumer, and this job can no
# longer starve the marks that price positions.
CALLER_TAG = "hermes_session"

# Keyed by ET session date, so a new session starts with an empty ladder.
_session_date: Optional[str] = None
_last_alerted: Dict[str, float] = {}
_prior_close: Dict[str, float] = {}

# R-IV.1058(b): the blind-alarm notice, at most once per ET session. Cleared by _roll_session
# along with the ladder, so each session gets exactly one chance to say it cannot see.
_blind_pushed: Dict[str, bool] = {}


# The running loop, so /health can say whether the alarm is ARMED. R-IV.867(a): "enabled" and
# "recently recorded" are different questions, and before this the first was answerable only by
# reading container logs — so an alarm that failed to start was invisible on the surface we look
# at. It is held here rather than in main.py because this module is what /health can import.
_task = None


def set_task(task) -> None:
    global _task
    _task = task


def armed_status() -> dict:
    """Is the alarm armed? Distinguishes NEVER STARTED from STARTED AND DIED.

    Collapsing those two into one false would hide which of two very different failures
    happened: an import that blew up at boot, or a loop that raised its way out afterwards.
    `run_forever` catches everything, so `died` should be unreachable — which is exactly why it
    is worth reporting if it ever appears.
    """
    from webhooks.hermes_session import FLAG, is_enabled

    t = _task
    out = {"flag": FLAG, "enabled": is_enabled(), "task_started": t is not None,
           "task_alive": bool(t is not None and not t.done())}
    if t is not None and t.done():
        try:
            exc = t.exception()
            out["died"] = type(exc).__name__ if exc else "returned without error"
        except Exception:                                           # noqa: BLE001
            out["died"] = "cancelled"
    return out


def reset_for_tests() -> None:
    global _session_date, _task
    _session_date = None
    _task = None
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
    # R-IV.1058(b): one blind notice per session, so a multi-day outage says so each day
    # rather than once ever -- and a session that recovers can go blind again and be heard.
    _blind_pushed.clear()
    logger.info("[hermes.session] new session %s — ladder cleared", et_date)
    return True


async def _snapshot(ticker: str) -> Optional[dict]:
    """One governed UW read, shared by both price readers below.

    THE LOG LEVEL IS THE POINT OF THIS FUNCTION. This job recorded 389 consecutive failures
    saying "no evaluable displacement for any of 3 symbol(s)" and never once succeeded, because
    the name the mark reader imported -- `get_stock_info` -- did not exist anywhere in the tree.
    The ImportError was swallowed by a broad `except Exception` and written at DEBUG, so the
    single fact that explained every one of those failures was never recorded. A missing name is
    a programming error, not a transient data condition, and it is now reported as one.
    """
    try:
        from integrations.uw_api import get_snapshot
    except ImportError:
        logger.error("[hermes.session] get_snapshot is not importable -- the alarm cannot price "
                     "anything until that is fixed", exc_info=True)
        return None
    try:
        snap = await get_snapshot(ticker, caller=CALLER_TAG)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[hermes.session] %s snapshot unavailable: %s", ticker,
                       type(exc).__name__)
        return None
    if not isinstance(snap, dict) or not snap:
        # The governor's UWUnavailable sentinel is falsy by design and lands here too.
        logger.warning("[hermes.session] %s snapshot empty or blocked by the governor", ticker)
        return None
    return snap


def _as_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _prior_session_close(ticker: str) -> Optional[float]:
    """The PRIOR regular session's closing price. None when it cannot be established.

    Taken from `prevDay.c`, which is the figure P1.10 (2026-04-28) exists to provide:
    /stock-state's own `prev_close` ROLLS FORWARD during post-market to today's regular close,
    so reading that field directly reports a move of about zero on a day the symbol actually
    fell. get_snapshot derives prevDay from regular-session /ohlc/1d bars instead, which is
    correct pre-market, in RTH, post-market and overnight alike.

    The prior CLOSE, never today's open: a gap IS displacement, and on a gap-down morning the
    move from yesterday's close is exactly what the principal wants to be told about. Measuring
    from the open would hide it -- the same reasoning the calibration replay uses, so the live
    alarm and the replay that set its thresholds are answering one question.
    """
    snap = await _snapshot(ticker)
    if not snap:
        return None
    return _as_float((snap.get("prevDay") or {}).get("c"))


async def _mark(ticker: str) -> Optional[float]:
    """The current price, or None. Never a stale fallback.

    A stale mark is worse than no mark here: it would produce a confident displacement from a
    price that is not the price, and `should_alert` has a NOT EVALUABLE branch precisely so this
    can refuse rather than guess.

    `lastTrade.p` is the live last trade, and is aware of the post-market session.
    """
    snap = await _snapshot(ticker)
    if not snap:
        return None
    return _as_float((snap.get("lastTrade") or {}).get("p"))


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
        # R-IV.1058(b): THE ALARM ANNOUNCES ITS OWN BLINDNESS.
        #
        # This raise already counted toward the flatline alert, and on 2026-10-14 it did fire --
        # `stable_job_status.alerted` was TRUE. It reached /health and it did NOT reach the
        # phone, so the alarm was blind for 133 minutes and the one person who needed to know
        # found out the next day from a health read. An alarm that can fail silently is not an
        # alarm, and the escalation has to travel the SAME road as the alerts it is failing to
        # send -- which is the phone, not a dashboard.
        #
        # Once per ET session, before the raise, so a push failure cannot swallow the raise.
        await _push_blind_notice(len(recs))
        raise OutputCheckFailed(
            "no evaluable displacement for any of %d symbol(s) — alarm is blind" % len(recs))
    return {"symbols": len(recs)}


async def _push_blind_notice(n_symbols: int) -> dict:
    """Tell the phone the alarm cannot see. At most once per ET session. NEVER RAISES.

    NEVER RAISES is load-bearing twice over. This is called from inside `_recorded_pass`
    immediately before the `OutputCheckFailed` that records the failure, so an exception here
    would replace a precise "alarm is blind" ledger entry with whatever went wrong in the
    notifier -- the blindness would still exist and would now be mislabelled. And a notifier
    that dies takes the next alert with it (the same reasoning `run_forever` already carries).

    NO MONEY FIGURES, by construction: `ntfy_push.build_message` takes three strings and has no
    amount parameter, and R-IV.901(b)2 is enforced inside it. The ticker field says HERMES
    because the subject is the alarm itself, not any one symbol.
    """
    global _session_date
    key = _session_date or "unknown-session"
    if _blind_pushed.get(key):
        return {"sent": False, "reason": "already notified this session"}
    # Marked BEFORE the await, not after. An await that is cancelled mid-flight would otherwise
    # leave the flag unset and the next pass would push again -- one per minute, 133 times,
    # which is the failure this guard exists to report rather than reproduce.
    _blind_pushed[key] = True
    try:
        from integrations import ntfy_push
        if not ntfy_push.is_configured():
            logger.error("[hermes.session] BLIND and %s is not set -- the notice cannot be "
                         "delivered", ntfy_push.TOPIC_ENV)
            return {"sent": False, "reason": "%s not set" % ntfy_push.TOPIC_ENV}
        res = await ntfy_push.send(
            "HERMES", "session alarm BLIND",
            "no price for any of %d tracked symbols this session; displacement alerts are NOT "
            "being evaluated. Check the UW caller quota for '%s' and /health."
            % (n_symbols, CALLER_TAG),
            title="Pandora: Hermes is blind", priority="high")
        logger.error("[hermes.session] blind notice -> sent=%s", res.get("sent"))
        return res
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[hermes.session] blind notice failed: %s", type(exc).__name__)
        return {"sent": False, "reason": type(exc).__name__}


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
