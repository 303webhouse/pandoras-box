"""B2's live run: read Set B's 15m bars, decide, log every event, push the few that qualify.

THE PURE DECISIONS ARE NOT HERE. `models.position_watch` owns every one that can do harm and is
testable without a vendor, a database or a push; this file is the plumbing that feeds it and the
one place that talks to yfinance, Postgres and ntfy. That split is why four rulings have been
able to change the rules without touching the plumbing.

WHAT THIS JOB WILL NOT DO, each because the alternative has already cost something:

  * IT NEVER BUILDS A BAR WINDOW. `yf_15m.session_bars` refuses a list that does not start at
    the session open, because R-IV.1224(c) makes a one-element list a gap-open break -- so a
    truncated window would MANUFACTURE an alert. The refusal is logged and the ticker is
    skipped for that cycle; a skipped ticker is visible, a phantom break is not.

  * IT NEVER RE-LOGS AN EVENT. The job runs every 15 minutes and a restart re-reads the whole
    session, so `already_logged` is checked before anything is written or sent. Without it a
    redeploy mid-session would re-push what it had already pushed.

  * IT NEVER DECIDES "AGAINST" FROM THE HELD TICKER. `classify_relation` reads the sign of the
    position's net delta ON THE UNDERLYING (R-IV.1209(f)3, reaffirmed as EXPOSURE by
    R-IV.1233(d)): a long SQQQ is short QQQ, so a bullish QQQ alert is AGAINST it.

  * IT NEVER SENDS A PRICE. `push_fields` limits the wire to ticker / alert type / action
    (R-IV.901(b)1), and ntfy's own money guard refuses a figure written to the cent. The level
    stays on the panel row.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Any, Dict, List, Optional, Tuple

from integrations import yf_15m
from models import position_watch as pw
from models import position_watch_events as pwe
from stable_engine import sessions as _sessions

logger = logging.getLogger("position_watch_job")

#: One cycle per 15-minute bar, which is the ruled 26 batched calls a session.
CYCLE_SECONDS = 15 * 60
#: After the close the final bar needs the grace period from R-IV.1215(b)4 before it counts.
POST_CLOSE_WAIT_S = (pw.CLOSE_GRACE_MIN + 1) * 60

SET_B_SQL = """
SELECT ticker, structure, classification, bucket, stop_loss, target, quantity,
       entry_price, current_price, unrealized_pnl, account
  FROM unified_positions
 WHERE UPPER(COALESCE(status, '')) = 'OPEN'
   AND UPPER(COALESCE(status, '')) <> 'DUPLICATE_OF'
"""


async def load_book(conn) -> List[Dict[str, Any]]:
    """The open book, as row dicts. Set B is DERIVED from this every cycle, never stored.

    R-IV.1215(b)2: a frozen ticker list would watch a closed position and miss a new one, and
    the second failure is silent.
    """
    rows = await conn.fetch(SET_B_SQL)
    return [dict(r) for r in rows]


def _shown_regime(regime: Optional[Dict[str, Any]]) -> Optional[str]:
    if not regime:
        return None
    for k in ("label", "regime", "shown_regime"):
        v = regime.get(k)
        if v:
            return str(v)
    return None


async def _current_regime(conn) -> Optional[Dict[str, Any]]:
    """The regime label to tag alerts with (R-IV.1209(f)5). None rather than a guess."""
    try:
        from jobs.regime_job import latest_with_diff

        got = await latest_with_diff(conn)
        return got if isinstance(got, dict) else None
    except Exception as exc:                                        # noqa: BLE001
        logger.debug("[pw] regime label unavailable: %s", type(exc).__name__)
        return None


def _positions_for(book: List[Dict[str, Any]], underlying: str,
                   via: List[str]) -> List[Dict[str, Any]]:
    """The rows this underlying is being watched FOR, held tickers included.

    A ticker held both tactically and in core is watched (R-IV.1215(b)3's reading), and the
    TACTICAL row is the one that can need a stop reviewed, so it is first.
    """
    want = {str(v).upper() for v in via} | {underlying}
    mine = [r for r in book if str(r.get("ticker", "")).upper() in want]
    mine.sort(key=lambda r: 0 if str(r.get("classification", "")).upper() == "TACTICAL" else 1)
    return mine


def detect(session_closes: List[float], prior_high: Optional[float],
           prior_low: Optional[float], *, fired: List[str],
           position: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every event this ticker's closed bars produce, in the order they are reported.

    Pure, so the whole decision set for a session can be replayed from a list of closes.
    """
    out: List[Dict[str, Any]] = []
    brk = pw.level_break(session_closes, prior_high, prior_low, fired_sides=fired)
    if brk:
        out.append(brk)
    fade = pw.failed_breakout(session_closes, prior_high, prior_low)
    if fade:
        out.append(fade)
    if session_closes:
        exit_ev = pw.stop_or_target(session_closes[-1], position)
        if exit_ev:
            out.append(exit_ev)
    return out


async def run_cycle(conn, *, now: Optional[_dt.datetime] = None,
                    send: bool = True) -> Dict[str, Any]:
    """One pass over Set B. Returns a report; writes rows; sends the pushes that qualify.

    `send=False` runs everything except the wire, which is how the job is exercised without a
    topic configured.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    et = _sessions.to_et(now)
    today = et.date()
    rth = _sessions.is_rth(now)
    session_closed = rth is False and et.time() >= yf_15m.RTH_CLOSE

    book = await load_book(conn)
    sb = pw.set_b(book)
    watch = sb["watch"]
    report: Dict[str, Any] = {"session_date": today.isoformat(), "set_b": watch,
                              "not_watched": sb["not_watched"], "events": 0, "pushed": 0,
                              "skipped": {}, "calls": 0}
    if not watch:
        report["skipped"]["*"] = "Set B is empty: no traded sleeve is open"
        return report

    bars = await asyncio.to_thread(yf_15m.fetch, watch)
    report["calls"] = 1
    regime = await _current_regime(conn)
    shown = _shown_regime(regime)
    pushed_today = await pwe.pushes_today(conn, today)
    recent = await pwe.recent_pushes(conn, today)
    suppressed_by_cap = False

    for under in watch:
        series = bars.get(under)
        if not series:
            report["skipped"][under] = "no 15m bars returned for it this cycle"
            continue
        try:
            session = yf_15m.session_bars(series, today)
        except yf_15m.SessionTruncated as exc:
            # Logged and skipped, never patched up. See the module docstring.
            logger.warning("[pw] %s skipped: %s", under, exc)
            report["skipped"][under] = str(exc)
            continue
        closed, closed_why = yf_15m.closed_bars(session, now=now,
                                                session_closed=bool(session_closed))
        if not closed:
            report["skipped"][under] = "no closed bar yet (%s)" % closed_why
            continue
        prior_high, prior_low, level_basis = yf_15m.prior_day_level(series, today)
        if prior_high is None or prior_low is None:
            report["skipped"][under] = level_basis
            continue

        closes = [b["close"] for b in closed]
        bar_close_at = closed[-1]["start"] + _dt.timedelta(minutes=yf_15m.BAR_MINUTES)
        positions = _positions_for(book, under, sb["via"].get(under, [under]))
        if not positions:
            report["skipped"][under] = "no open row maps to it any more"
            continue
        position = positions[0]
        fired = await pwe.fired_sides(conn, session_date=today, ticker=under)

        for ev in detect(closes, prior_high, prior_low, fired=fired, position=position):
            kind = str(ev.get("event", "")).upper()
            if await pwe.already_logged(conn, session_date=today, ticker=under,
                                        event_type=kind):
                continue
            direction = _alert_direction(ev)
            relation, rel_why = pw.classify_relation(direction, position)
            action = pw.action_for(kind, relation)
            implied_note = None
            if kind == "EXHAUSTION":
                ok_gate, implied_note = pw.exhaustion_push_gate(
                    position, _implied_move(position), _open_profit(position))
                if not ok_gate:
                    ev = dict(ev, pushable=False)
            ok, why = pw.may_push_event(
                ev, relation=relation, ticker=under, recent=recent, now=now,
                pushed_today=pushed_today, session_date=today)
            if not ok and "daily cap" in why:
                suppressed_by_cap = True
            sent_at = None
            if ok and send:
                fields = pw.push_fields(ticker=under, event=kind, action=action,
                                        shown_regime=shown)
                res = await _send(fields)
                if res.get("sent"):
                    sent_at = _dt.datetime.now(_dt.timezone.utc)
                else:
                    ok, why = False, "the push was not sent: %s" % res.get("reason", "unknown")
            elif ok and not send:
                ok, why = False, "the wire is not being used on this run (send=False)"

            # R-IV.1215(b)5's REVISED marking: a faded gap SUPERSEDES the unconfirmed
            # bar-1 row Nick has already seen, so the new row points at the old one and the
            # panel marks that one REVISED. Nothing is mutated -- see `unconfirmed_gap_id`.
            revised_of = None
            if kind == "GAP_FADED":
                revised_of = await pwe.unconfirmed_gap_id(
                    conn, session_date=today, ticker=under, side=ev.get("side"))
            row = pwe.row_for(ev, ticker=under, session_date=today,
                              bar_close_at=bar_close_at, relation=relation, action=action,
                              pushed=bool(ok), suppression_reason=None if ok else why,
                              shown_regime=shown, pushed_at=sent_at, revised_of=revised_of)
            row["basis"] = _basis_with_notes(ev, level_basis, rel_why, implied_note)
            await pwe.insert(conn, row)
            report["events"] += 1
            if ok:
                report["pushed"] += 1
                pushed_today += 1
                recent = await pwe.recent_pushes(conn, today)

    await _maybe_cap_notice(conn, today, pushed_today=pushed_today,
                            suppressed_by_cap=suppressed_by_cap, send=send,
                            shown_regime=shown, report=report)
    return report


def _basis_with_notes(ev: Dict[str, Any], level_basis: str, rel_why: Optional[str],
                      implied_note: Optional[str]) -> str:
    """The panel row's sentence, with WHERE THE LEVEL CAME FROM attached.

    The level's provenance travels with the claim rather than living in a job log, because a
    level break is only as good as the session it was measured against -- and Yahoo's daily
    endpoint dropping a session is a filed landmine in this repo.
    """
    parts = [str(ev.get("basis", ""))]
    if level_basis:
        parts.append("level from: %s" % level_basis)
    if rel_why:
        parts.append(str(rel_why))
    if implied_note:
        parts.append(str(implied_note))
    return " · ".join(p for p in parts if p)


def _alert_direction(ev: Dict[str, Any]) -> Optional[str]:
    """The alert's own direction, which `classify_relation` compares to the net delta.

    A break ABOVE is a bullish alert; a break BELOW is bearish. A failed breakout INVERTS that:
    a failed break above is a bearish event. Getting this backwards silences exactly the alerts
    that matter, which is why it is one function and not an inline expression at three sites.
    """
    kind = str(ev.get("event", "")).upper()
    side = str(ev.get("side", "")).lower()
    if kind in ("FAILED_BREAKOUT", "GAP_FADED"):
        return "bearish" if side == "above" else "bullish"
    if kind == "STOP_LEVEL":
        return None
    if kind == "TARGET_LEVEL":
        return None
    if side == "above":
        return "bullish"
    if side == "below":
        return "bearish"
    return None


def _implied_move(position: Dict[str, Any]) -> Optional[float]:
    """Not available from the book alone, so it is None and the gate says "n/a".

    R-IV.1209(f)4 rules that the unavailable case PUSHES with "vs implied: n/a", so a missing
    yardstick does not silence an exhaustion against a profitable position. Stated here rather
    than quietly returning None from nowhere.
    """
    return None


def _open_profit(position: Dict[str, Any]) -> Optional[float]:
    v = position.get("unrealized_pnl")
    try:
        return None if v is None else float(v)
    except Exception:                                               # noqa: BLE001
        return None


async def _send(fields: Dict[str, str]) -> Dict[str, Any]:
    from integrations import ntfy_push

    return await ntfy_push.send(fields["ticker"], fields["alert_type"], fields["action"])


async def _maybe_cap_notice(conn, today: _dt.date, *, pushed_today: int,
                            suppressed_by_cap: bool, send: bool,
                            shown_regime: Optional[str], report: Dict[str, Any]) -> None:
    """R-IV.1220(a)4: one final push when the cap has actually turned something away."""
    sent_already = await pwe.cap_notice_sent(conn, today)
    due, why = pw.cap_notice(pushed_today=pushed_today, suppressed_by_cap=suppressed_by_cap,
                             notice_sent=sent_already)
    if not due:
        return
    sent_at = None
    pushed = False
    if send:
        from integrations import ntfy_push

        res = await ntfy_push.send("PANDORA", "alert cap", pw.CAP_NOTICE_TEXT)
        pushed = bool(res.get("sent"))
        sent_at = _dt.datetime.now(_dt.timezone.utc) if pushed else None
        if not pushed:
            why = "the cap notice was not sent: %s" % res.get("reason", "unknown")
    else:
        why = "the wire is not being used on this run (send=False)"
    notice = {"event": "CAP_NOTICE", "basis": pw.CAP_NOTICE_TEXT}
    row = pwe.row_for(notice, ticker="PANDORA", session_date=today,
                      bar_close_at=_dt.datetime.now(_dt.timezone.utc),
                      relation=None, action=pw.ACTION_LOGGED, pushed=pushed,
                      suppression_reason=None if pushed else why,
                      shown_regime=shown_regime, pushed_at=sent_at)
    await pwe.insert(conn, row)
    report["cap_notice"] = "sent" if pushed else why


async def position_watch_loop() -> None:
    """One cycle per 15-minute bar during RTH, plus one after the close.

    QUIET OUTSIDE RTH, and the calendar's third state is respected: `is_rth` returns None when
    it cannot answer, and None is treated as "do not run" rather than as open. A watcher that
    ran on a holiday would compare today's absent bars against a stale prior day.
    """
    from database.postgres_client import get_postgres_client

    logger.info("[pw] position watch loop started; pushes %s",
                "ON" if pw.PUSHES_ENABLED else "OFF")
    post_close_done: Optional[_dt.date] = None
    while True:
        try:
            now = _dt.datetime.now(_dt.timezone.utc)
            et = _sessions.to_et(now)
            rth = _sessions.is_rth(now)
            after_close = (rth is False and et.time() >= yf_15m.RTH_CLOSE
                           and post_close_done != et.date())
            if rth is True or after_close:
                pool = await get_postgres_client()
                async with pool.acquire() as conn:
                    rep = await run_cycle(conn, now=now)
                logger.info("[pw] %s: %d events, %d pushed, %d skipped",
                            rep["session_date"], rep["events"], rep["pushed"],
                            len(rep["skipped"]))
                if after_close:
                    post_close_done = et.date()
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[pw] cycle failed: %s: %s", type(exc).__name__, exc)
        await asyncio.sleep(CYCLE_SECONDS)
