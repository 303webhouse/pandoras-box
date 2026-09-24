"""R-IV.517(d) + R-IV.526(c) -- the FIDELITY_ROTH loss alert.

Three triggers, all pushed to Discord through the hub's alert webhook:

  T1  UNSTOPPED_LOSS   a FIDELITY_ROTH position with no live broker stop whose
                       open loss reaches LOSS_FRACTION of the account value.
  T2  CLOSE_STOP       a written daily-close stop in the notes, breached AT THE
                       CLOSE (never intraday -- that is a different instrument).
  T3  COST_RECOVERY    any long-premium position of COST_RECOVERY_MIN_CONTRACTS
                       or more contracts whose mark reaches COST_RECOVERY_MULTIPLE
                       times its cost. Book-wide: FIDELITY_ROTH holds no options,
                       so scoping this one to that account would make it dead code.

R-IV.526(c) -- WHAT THIS JOB IS NOT ALLOWED TO READ.

Trade Analysis found `max_loss`, `unrealized_pnl` and anything summed from them
carrying the wrong contract scope: WEAT 367's max_loss is six-lot on a three-lot
remainder, ABNB 379's unrealized_pnl is one contract of two. An alert built on
those columns would inherit the exact fault it exists to catch -- a loss alert
that under-reads a loss by half is worse than no alert, because it is trusted.

So every figure here comes from the position's LOTS -- open remainder = SUM(qty)
(convention #29), cost = SUM(qty x price) -- and from a live mark. The SELECT
names none of `max_loss`, `unrealized_pnl`, `cost_basis`, and the test module
asserts that by reading this module's own source.

A row with no lots therefore has no remainder and no cost, and NOTHING is
substituted for them: it is reported unmeasurable, once per session, on the same
webhook. Falling back to `quantity` and `entry_price` there would reintroduce the
scope the ruling just removed.

THE MARK. The alert does not re-price anything. It takes the hub's own marked
price, which the mark-to-market job writes through the payoff-bound and T1 guards,
and only when that mark is FRESH (`mark_status='OK'` and `mark_checked_at` inside
MARK_MAX_AGE_S). A stale or refused mark fires nothing and is named. Re-pricing
here would mean a second set of UW calls per cycle against a 17,000/day shed
threshold, and two independently-guarded marks that can disagree.

LOGS. R-IV.517(d): status codes and figures only. Rows are named by integer id;
no ticker, no note text, and never the webhook URL.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("loss_alert")

ACCOUNT = "FIDELITY_ROTH"

# The principal's latest broker figure, ~$11,200 on 2026-09-24 (R-IV.517(d)). It is a
# CONSTANT on purpose: the hub's own account_balances row for this account is what
# money integrity is being built to make trustworthy, and sizing off an untrusted
# aggregate is the failure that ruling exists to stop. Money integrity replaces this
# read; the env var is the principal's lever until then.
DEFAULT_ACCOUNT_VALUE_USD = 11_200.00
ACCOUNT_VALUE_AS_OF = date(2026, 9, 24)

LOSS_FRACTION = 0.02                  # 2% of account value -> $224.00 at $11,200
COST_RECOVERY_MULTIPLE = 2.0          # X7, principal's call: 2x-3x cost
COST_RECOVERY_MIN_CONTRACTS = 2       # one contract cannot be half-sold

OPTION_MULTIPLIER = 100.0
MARK_MAX_AGE_S = 30 * 60              # a mark older than this is not a live mark

TICK_SECONDS = 15 * 60
CLOSE_STOP_FROM_HOUR_ET = 16          # the close exists from here...
CLOSE_STOP_UNTIL_HOUR_ET = 20         # ...and the verdict stops being asked for here

TRIGGER_UNSTOPPED_LOSS = "UNSTOPPED_LOSS"
TRIGGER_CLOSE_STOP = "CLOSE_STOP"
TRIGGER_COST_RECOVERY = "COST_RECOVERY"
NOTICE_UNMEASURABLE = "UNMEASURABLE"

_COLOR = {
    TRIGGER_UNSTOPPED_LOSS: 0xFF4444,
    TRIGGER_CLOSE_STOP: 0xFF8800,
    TRIGGER_COST_RECOVERY: 0x33CC77,
    NOTICE_UNMEASURABLE: 0x888888,
}

# Sent-this-session memory, so a Redis outage degrades to per-process dedupe rather
# than to no dedupe at all. Keyed (session, trigger, position_id).
_SENT_IN_PROCESS: set = set()


def account_value_usd() -> float:
    """Railway hands back '' for an unset reference, so `or` is the required idiom."""
    raw = (os.getenv("LOSS_ALERT_ACCOUNT_VALUE") or "").strip()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
            logger.warning("LOSS_ALERT_ACCOUNT_VALUE is not positive -- using the ruling's figure")
        except ValueError:
            logger.warning("LOSS_ALERT_ACCOUNT_VALUE is not a number -- using the ruling's figure")
    return DEFAULT_ACCOUNT_VALUE_USD


def loss_threshold_usd() -> float:
    return round(account_value_usd() * LOSS_FRACTION, 2)


# -- the stop the hub cannot see ---------------------------------------------

def has_live_broker_stop(row: Dict[str, Any]) -> Optional[bool]:
    """Is a stop actually WORKING at the broker for this row? Returns None: unknown.

    The hub has no field that records it. `stop_loss` is a number the principal
    wrote down; it says nothing about whether an order exists at Fidelity. Stop TYPE
    is one of the positions-screen gaps (gap 3) and lands with it -- until then this
    function is honest about not knowing, rather than reading `stop_loss` as proof.

    The caller treats None as NOT stopped, which is the direction that fails toward
    an alert. An unstopped loss read as stopped is silence on the case the trigger
    was built for; a stopped loss read as unstopped is one Discord line.
    """
    return None


# -- the daily-close stop written in the notes -------------------------------

# "daily close below 43", "stop: close under $43.10", "daily-close stop 43".
# The word "close" is REQUIRED: a bare "stop 43" is the stop_loss column's job, and
# reading it as a close stop would invent an instrument the principal did not write.
_CLOSE_STOP_WITH_STOP_FIRST = re.compile(
    r"stop[\s:]*(?:on|at)?[\s:]*(?:a[\s]*)?(?:daily[\s-]*)?clos(?:e|ing)[\s:]*"
    r"(?P<dir>below|under|beneath|above|over|through)?[\s:]*"
    r"\$?(?P<level>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_CLOSE_STOP = re.compile(
    r"(?:daily[\s-]*)?clos(?:e|ing)[\s-]*(?:stop)?[\s:]*"
    r"(?P<dir>below|under|beneath|above|over|through)?[\s:]*"
    r"\$?(?P<level>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def parse_daily_close_stop(notes: Optional[str],
                           direction: Optional[str]) -> Optional[Tuple[float, str]]:
    """(level, side) for a written daily-close stop, or None.

    `side` is "below" for a long (breached when the close is at or under the level)
    and "above" for a short. An explicit word in the text wins over the position's
    direction, because the principal writing "close above 43" on a long means it.
    """
    if not notes:
        return None
    m = _CLOSE_STOP_WITH_STOP_FIRST.search(notes) or _CLOSE_STOP.search(notes)
    if not m:
        return None
    try:
        level = float(m.group("level"))
    except (TypeError, ValueError):
        return None
    if level <= 0:
        return None
    word = (m.group("dir") or "").lower()
    if word in ("below", "under", "beneath"):
        side = "below"
    elif word in ("above", "over"):
        side = "above"
    else:
        side = "above" if (direction or "").upper() == "SHORT" else "below"
    return level, side


def close_stop_breached(close_price: float, level: float, side: str) -> bool:
    """At or through the level. A close exactly ON a stop is a breach, not a hold."""
    return close_price <= level if side == "below" else close_price >= level


# -- the arithmetic, from lots and a mark only -------------------------------

def _f(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, Decimal):
        return float(x)
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def position_economics(remainder: Optional[float], lot_cost: Optional[float],
                       mark: Optional[float], is_option: bool) -> Optional[Dict[str, float]]:
    """{remainder, cost, value, pnl, unit_cost, multiple} from lots and a mark, or None.

    `lot_cost` is SUM(qty x price) in PRICE units -- dollars for a share, dollars per
    contract for an option -- so the multiplier is applied here, once, in the one
    place that knows the asset type.
    """
    if remainder is None or lot_cost is None or mark is None:
        return None
    if remainder <= 0:
        return None
    mult = OPTION_MULTIPLIER if is_option else 1.0
    cost = lot_cost * mult
    value = mark * remainder * mult
    unit_cost = lot_cost / remainder          # per share / per contract
    return {
        "remainder": remainder,
        "cost": round(cost, 2),
        "value": round(value, 2),
        "pnl": round(value - cost, 2),
        "unit_cost": unit_cost,
        "multiple": (mark / unit_cost) if unit_cost > 0 else 0.0,
    }


def mark_is_live(mark_status: Optional[str], mark_checked_at: Optional[datetime],
                 now: Optional[datetime] = None) -> Tuple[bool, str]:
    """A mark this job may use, or the reason it may not."""
    if (mark_status or "").upper() != "OK":
        return False, "mark_status is %s" % (mark_status or "unset")
    if mark_checked_at is None:
        return False, "the mark carries no check time"
    now = now or datetime.now(timezone.utc)
    if mark_checked_at.tzinfo is None:
        return False, "the mark's check time carries no timezone"
    age = (now - mark_checked_at).total_seconds()
    if age > MARK_MAX_AGE_S:
        return False, "the mark is %d minutes old" % int(age // 60)
    return True, "marked %d minutes ago" % int(max(age, 0) // 60)


# -- evaluation --------------------------------------------------------------

# Named here so the module's own test can assert the SELECT reads none of them.
FORBIDDEN_COLUMNS = ("max_loss", "unrealized_pnl", "cost_basis", "realized_pnl")

POSITION_SQL = """
    SELECT p.id, p.position_id, p.ticker, p.account, p.asset_type, p.structure,
           p.direction, p.notes, p.stop_loss, p.current_price, p.mark_status,
           p.mark_checked_at,
           l.remainder, l.lot_cost
      FROM unified_positions p
      LEFT JOIN (SELECT position_id,
                        SUM(qty)         AS remainder,
                        SUM(qty * price) AS lot_cost
                   FROM position_lots
                  GROUP BY position_id) l
        ON l.position_id = p.position_id
     WHERE p.status = 'OPEN'
"""


def evaluate_rows(rows: List[Dict[str, Any]], *, now: Optional[datetime] = None,
                  session_closes: Optional[Dict[str, float]] = None,
                  after_close: bool = False,
                  expect_live_mark: bool = True) -> List[Dict[str, Any]]:
    """Every alert the book earns right now. Pure: no I/O, so the tests can drive it.

    `expect_live_mark` is False outside the hours when the mark job runs. A mark that
    is hours old at 02:00 ET is the market being shut, not a fault, and reporting it
    as one every night would train the principal to ignore the channel.
    """
    out: List[Dict[str, Any]] = []
    threshold = loss_threshold_usd()
    session_closes = session_closes or {}

    for r in rows:
        pid = r.get("position_id")
        rid = r.get("id")
        ticker = r.get("ticker")
        is_option = (r.get("asset_type") or "").upper() == "OPTION"
        remainder = _f(r.get("remainder"))
        lot_cost = _f(r.get("lot_cost"))
        mark = _f(r.get("current_price"))
        in_account = (r.get("account") or "").upper() == ACCOUNT

        live, why = mark_is_live(r.get("mark_status"), r.get("mark_checked_at"), now)

        if remainder is None or lot_cost is None:
            # R-IV.526(b): no lots, no remainder, and nothing stands in for one.
            if in_account:
                out.append({
                    "trigger": NOTICE_UNMEASURABLE, "id": rid, "position_id": pid,
                    "ticker": ticker, "account": r.get("account"),
                    "reason": "it holds no lots, so it has no open remainder and no "
                              "lot cost -- the loss cannot be measured without "
                              "substituting the figures R-IV.526(b) removed",
                })
            continue

        if not live:
            if in_account and expect_live_mark:
                out.append({
                    "trigger": NOTICE_UNMEASURABLE, "id": rid, "position_id": pid,
                    "ticker": ticker, "account": r.get("account"),
                    "reason": "there is no live mark for it: %s" % why,
                })
            continue

        econ = position_economics(remainder, lot_cost, mark, is_option)
        if econ is None:
            continue

        # T1 -- unstopped loss, this account only.
        if in_account and econ["pnl"] <= -threshold and not has_live_broker_stop(r):
            out.append({
                "trigger": TRIGGER_UNSTOPPED_LOSS, "id": rid, "position_id": pid,
                "ticker": ticker, "account": r.get("account"),
                "loss": econ["pnl"], "threshold": -threshold,
                "remainder": econ["remainder"], "cost": econ["cost"],
                "value": econ["value"], "mark": mark,
                "written_stop": _f(r.get("stop_loss")),
            })

        # T2 -- a written daily-close stop, breached at the close.
        if after_close:
            parsed = parse_daily_close_stop(r.get("notes"), r.get("direction"))
            close_px = session_closes.get(ticker)
            if parsed and close_px is not None:
                level, side = parsed
                if close_stop_breached(close_px, level, side):
                    out.append({
                        "trigger": TRIGGER_CLOSE_STOP, "id": rid, "position_id": pid,
                        "ticker": ticker, "account": r.get("account"),
                        "close": close_px, "level": level, "side": side,
                        "remainder": econ["remainder"], "pnl": econ["pnl"],
                    })

        # T3 -- long premium, 2+ contracts, at the cost-recovery multiple. Book-wide.
        if (is_option and remainder >= COST_RECOVERY_MIN_CONTRACTS
                and econ["unit_cost"] > 0 and lot_cost > 0
                and econ["multiple"] >= COST_RECOVERY_MULTIPLE):
            out.append({
                "trigger": TRIGGER_COST_RECOVERY, "id": rid, "position_id": pid,
                "ticker": ticker, "account": r.get("account"),
                "multiple": round(econ["multiple"], 2), "mark": mark,
                "unit_cost": round(econ["unit_cost"], 4),
                "remainder": econ["remainder"], "cost": econ["cost"],
                "value": econ["value"], "pnl": econ["pnl"],
            })

    return out


# -- the push ----------------------------------------------------------------

def _body(a: Dict[str, Any]) -> Tuple[str, str]:
    t = a["trigger"]
    tk = a.get("ticker") or "?"
    if t == TRIGGER_UNSTOPPED_LOSS:
        stop_line = ("No field in the hub records whether a stop is live at the broker, "
                     "so this fires as unstopped. Written stop: %s."
                     % ("none" if a.get("written_stop") is None
                        else format(a["written_stop"], "g")))
        return (
            "Unstopped loss - %s" % tk,
            "**%s** (%s) is down **$%s** on %g held, at or past %d%% of the account "
            "($%s of $%s).\nCost $%s -> value $%s at %g.\n%s\nLoss measured from the "
            "lots (open remainder) and the live mark, never from the row's stored "
            "P&L figures (R-IV.526(c))."
            % (tk, a.get("account"), format(abs(a["loss"]), ",.2f"), a["remainder"],
               int(LOSS_FRACTION * 100), format(abs(a["threshold"]), ",.2f"),
               format(account_value_usd(), ",.0f"), format(a["cost"], ",.2f"),
               format(a["value"], ",.2f"), a["mark"], stop_line)
        )
    if t == TRIGGER_CLOSE_STOP:
        word = "at or below" if a["side"] == "below" else "at or above"
        return (
            "Daily-close stop breached - %s" % tk,
            "**%s** (%s) closed at **%g**, %s the written daily-close stop **%g**.\n"
            "%g held; open P&L $%s from lots and the close."
            % (tk, a.get("account"), a["close"], word, a["level"],
               a["remainder"], format(a["pnl"], ",.2f"))
        )
    if t == TRIGGER_COST_RECOVERY:
        return (
            "Cost recovery available - %s" % tk,
            "**%s** (%s) marks **%.2fx** cost (%g against %g paid) on %g contracts.\n"
            "Cost $%s -> value $%s (+$%s). Selling to recover cost leaves the rest free."
            % (tk, a.get("account"), a["multiple"], a["mark"], a["unit_cost"],
               a["remainder"], format(a["cost"], ",.2f"), format(a["value"], ",.2f"),
               format(a["pnl"], ",.2f"))
        )
    return (
        "Loss alert cannot measure %s" % tk,
        "**%s** (%s) is in scope for the loss alert but %s.\nNo trigger can fire on "
        "this row until that is fixed." % (tk, a.get("account"), a["reason"])
    )


def _digest_body(notices: List[Dict[str, Any]]) -> Tuple[str, str]:
    """One line per unmeasurable row, in ONE push.

    These do not resolve on their own -- a row with no lots stays lot-less until
    someone lots it -- so a message per row per session would arrive every day for
    each of them and become the noise the channel is worst at carrying.
    """
    lines = "\n".join(
        "- **%s** (%s): %s" % (n.get("ticker") or "?", n.get("account"), n["reason"])
        for n in notices
    )
    return (
        "Loss alert is blind on %d %s position%s"
        % (len(notices), ACCOUNT, "" if len(notices) == 1 else "s"),
        "The loss alert cannot measure these, so no trigger can fire on them:\n%s"
        % lines
    )


async def _post(title: str, description: str, color: int) -> Optional[int]:
    """One webhook post. Returns the HTTP status code, or None if it never left.

    AEGIS: the URL is never logged, and neither is the body -- the body names a
    ticker and can quote the principal's notes.
    """
    url = os.getenv("DISCORD_WEBHOOK_ALERTS") or os.getenv("DISCORD_WEBHOOK_CB") or ""
    if not url:
        logger.warning("no alert webhook configured -- push suppressed")
        return None
    import httpx
    payload = {"embeds": [{
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "Pandora's Box - position risk"},
    }]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code
    except Exception as e:
        logger.error("alert post failed: %s", type(e).__name__)
        return None


def _seconds_to_utc_rollover() -> int:
    now = datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((nxt - now).total_seconds()))


async def _claim(session: date, trigger: str, position_id: str) -> bool:
    """True if this (session, trigger, row) has not been pushed yet.

    Redis first, so the claim survives a redeploy. When Redis cannot answer, the
    in-process set still holds -- a duplicate line is a nuisance, a missed loss is
    the defect this job exists to remove, so an unreadable Redis must not silence it.
    """
    key = (str(session), trigger, position_id)
    if key in _SENT_IN_PROCESS:
        return False
    _SENT_IN_PROCESS.add(key)
    try:
        from database.redis_client import get_redis_client
        r = await get_redis_client()
        if r:
            ok = await r.set("loss_alert:%s:%s:%s" % (trigger, position_id, session),
                             "1", ex=_seconds_to_utc_rollover(), nx=True)
            return bool(ok)
    except Exception:
        logger.warning("dedupe store unreadable -- falling back to in-process memory")
    return True


# -- the tick ----------------------------------------------------------------

def marks_expected(et: datetime) -> bool:
    """Are the mark job's writes due right now? Trading day, 09:30 ET to 17:00 ET.

    The calendar answers whether the day is a session; a holiday it cannot answer for
    is treated as NOT a session here, because the cost of being wrong is a missing
    notice, not a missing alert -- the triggers themselves do not consult this.
    """
    try:
        from stable_engine.market_calendar import is_trading_day_or_none
        if is_trading_day_or_none(et.date()) is not True:
            return False
    except Exception:
        return False
    minutes = et.hour * 60 + et.minute
    return (9 * 60 + 30) <= minutes <= (17 * 60)


async def _session_closes(tickers: List[str], session: date) -> Dict[str, float]:
    """The session's CLOSING price per ticker, from a bar that IS that session.

    R-IV.487's rule: a bar is never named a session it was not stamped with. A
    ticker whose frame holds no bar dated `session` is simply absent here, and T2
    does not fire for it -- yesterday's close compared against today's stop is the
    defect, not a fallback.
    """
    if not tickers:
        return {}
    try:
        from stable_engine.bars_yf import fetch_batch
    except Exception:
        logger.warning("daily bars unavailable -- no close-stop evaluation this tick")
        return {}
    out: Dict[str, float] = {}
    try:
        frames = fetch_batch(sorted(set(tickers)), session - timedelta(days=7), session)
    except Exception as e:
        logger.warning("daily bar fetch failed: %s", type(e).__name__)
        return {}
    for tk, frame in (frames or {}).items():
        if frame is None or getattr(frame, "empty", True):
            continue
        try:
            for idx, row in frame.iterrows():
                d = idx.date() if hasattr(idx, "date") else idx
                if d == session:
                    out[tk] = float(row["Close"])
                    break
        except Exception:
            continue
    return out


async def run_loss_alert(*, injected_rows: Optional[List[Dict[str, Any]]] = None,
                         now: Optional[datetime] = None) -> Dict[str, Any]:
    """One pass. Never raises.

    `injected_rows` is an acceptance-test seam (convention #30 wants a positive
    control that actually fires); production always passes None.
    """
    result: Dict[str, Any] = {"evaluated": 0, "alerts": 0, "pushed": 0,
                              "suppressed": 0, "statuses": {}}
    try:
        import pytz
        now = now or datetime.now(timezone.utc)
        et = now.astimezone(pytz.timezone("America/New_York"))
        session = et.date()
        # The close-stop verdict is only asked for in a bounded evening window. It is
        # settled once the session's close exists, and the daily-bar fetch behind it
        # is not free -- leaving it open to midnight would re-fetch every 15 minutes
        # all evening for an answer that cannot change.
        after_close = CLOSE_STOP_FROM_HOUR_ET <= et.hour <= CLOSE_STOP_UNTIL_HOUR_ET

        if injected_rows is not None:
            rows = injected_rows
        else:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                rows = [dict(r) for r in await conn.fetch(POSITION_SQL)]
        result["evaluated"] = len(rows)

        closes: Dict[str, float] = {}
        if after_close:
            want = [r.get("ticker") for r in rows
                    if r.get("ticker") and parse_daily_close_stop(r.get("notes"),
                                                                  r.get("direction"))]
            if want:
                closes = await _session_closes(want, session)

        alerts = evaluate_rows(rows, now=now, session_closes=closes,
                               after_close=after_close,
                               expect_live_mark=marks_expected(et))
        result["alerts"] = len(alerts)

        async def _send(title: str, description: str, trigger: str,
                        claim_id: str, row_id: Any) -> None:
            if not await _claim(session, trigger, claim_id):
                result["suppressed"] += 1
                return
            code = await _post(title, description, _COLOR.get(trigger, 0xFF4444))
            result["statuses"].setdefault(str(code), 0)
            result["statuses"][str(code)] += 1
            if code in (200, 204):
                result["pushed"] += 1
            # R-IV.517(d): status codes and figures only. The row is its integer id.
            logger.info("loss_alert %s id=%s http=%s", trigger, row_id, code)

        notices = [a for a in alerts if a["trigger"] == NOTICE_UNMEASURABLE]
        for a in (a for a in alerts if a["trigger"] != NOTICE_UNMEASURABLE):
            title, description = _body(a)
            await _send(title, description, a["trigger"], a["position_id"], a.get("id"))

        if notices:
            # One digest, claimed against the SET of blind rows: the same set stays
            # quiet, and a row joining or leaving it is news and re-fires.
            ids = ",".join(str(n.get("id")) for n in sorted(
                notices, key=lambda n: str(n.get("id"))))
            title, description = _digest_body(notices)
            await _send(title, description, NOTICE_UNMEASURABLE, ids, ids)

        logger.info("loss_alert pass: evaluated=%d alerts=%d pushed=%d suppressed=%d",
                    result["evaluated"], result["alerts"], result["pushed"],
                    result["suppressed"])
    except Exception as e:
        logger.error("loss_alert pass failed: %s", type(e).__name__)
        result["error"] = type(e).__name__
    return result
