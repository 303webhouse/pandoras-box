"""Hermes push, phase 1 — velocity breaches reach the phone — R-IV.775(d) / R-IV.780(d).

WHY THIS EXISTS. Hermes Flash's ingest has always worked: 13 velocity_breach rows on 2026-10-08
and about 1,270 since April. What never worked is anything downstream. Enrichment is refused by
design (R-IV.498(a)1, the deleted HERMES_VPS_KEY), `lightning_cards` holds ONE row ever — created
2026-04-01, the day Hermes was built — and the handler's only outbound was
`broadcast_event("hermes_flash", …)`, a websocket event with **zero consumers** across the
frontend. So a breach landed in a table nobody is shown. That is why the principal caught the
10-08 AI-led selloff from social media and not from the hub, and it is the second miss of that
kind.

Nothing here needs building to reach the phone — only connecting. `DISCORD_WEBHOOK_ALERTS` is
already configured and already proven by two other producers.

PHASE 1 IS DELIBERATELY NARROW. Only SPY, QQQ and SMH push: equity beta, which is what the
principal's book is exposed to. USO, IBIT, TLT, GLD, HYG, XLF and IYR are ingested and stored
exactly as before and do NOT push. The reason is measured, not aesthetic: on 10-08 the largest
moves of the day were USO's (+3.03, +3.36, +3.26, −2.52), and a size-ranked alarm would have
spent the whole session shouting about oil while the equity selloff that mattered — QQQ −1.01
with SMH −2.37 at 13:02 ET — ranked below all of them.

WHAT IS NOT CLAIMED. This is a NOTIFIER, not the shock alarm. It fires once per breach per
ticker, on TradingView's own 30-minute velocity threshold. It cannot see a grind: QQQ closed
10-08 at −1.65% cumulative while its largest 30-minute breach all day was −1.01%. Catching that
needs the session-to-date displacement check, which is phase 2's job and is a proposal, not this.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger("hermes.push")

# Equity beta only, phase 1. A frozenset so a caller cannot mutate the roster at runtime.
PUSH_TICKERS = frozenset({"SPY", "QQQ", "SMH"})

# Per-ticker, so one ticker breaching repeatedly cannot crowd out another's first breach.
PUSH_COOLDOWN_MINUTES = 15

# The window a co-breach is looked for in. Same 15 minutes the cooldown uses, deliberately: the
# message's "and X also breached" line and the suppression decision then describe one window, and
# a reader of the message is seeing the same span the code reasoned about.
CO_BREACH_WINDOW_MINUTES = 15

MT = ZoneInfo("America/Denver")

# In-process, like the handler's own `recent_breaches`. A restart therefore clears it, and the
# first breach after a restart pushes. That is the SAFE direction for an alarm -- a duplicate
# message costs a glance, a suppressed one costs the miss this module exists to fix -- but it is
# a real limitation and not a design: a durable cooldown wants a row, which phase 2 can carry.
_last_push: Dict[str, datetime] = {}


def reset_for_tests() -> None:
    _last_push.clear()


def is_pushable(ticker: Optional[str]) -> bool:
    """Phase 1's roster. Case-folded, because TradingView's payloads are not guaranteed upper."""
    return (ticker or "").strip().upper() in PUSH_TICKERS


def should_push(ticker: Optional[str], now: datetime,
                last_push_at: Optional[datetime],
                has_co_breach: bool = False) -> Tuple[bool, str]:
    """(push?, reason). PURE — no clock, no network, no module state.

    `now` and `last_push_at` are arguments so the decision can be tested at a chosen instant.
    Every refusal carries a reason, because "did not push" and "was never asked" are different
    facts and only one of them is a defect.

    A CO-BREACH OVERRIDES THE COOLDOWN, and 10-08 is why. QQQ's webhook landed at 17:02:02 and
    SMH's at 17:02:03 — ONE SECOND apart. Whichever arrives first cannot name the other, because
    the other has not breached yet; co-breach detection can only look backwards. And SMH's own
    message was inside its cooldown from 16:53. So with a strict cooldown the pair would have
    reached the phone as a single message naming NEITHER ticker — the exact event the principal
    missed, announced as a lone 1% move.

    The cooldown exists to stop ONE ticker repeating itself, not to suppress a second ticker
    joining it. Two equity-beta names inside fifteen minutes is the signal, so it is let through.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        return False, "no ticker"
    if sym not in PUSH_TICKERS:
        return False, "phase 1 pushes equity beta only (%s); %s ingested, not pushed" % (
            "/".join(sorted(PUSH_TICKERS)), sym)
    if last_push_at is None:
        return True, "first push for %s" % sym
    age = (now - last_push_at).total_seconds() / 60.0
    if age < PUSH_COOLDOWN_MINUTES:
        if has_co_breach:
            return True, ("%s pushed %.0f min ago, but an equity-beta co-breach overrides the "
                          "cooldown" % (sym, age))
        return False, "%s pushed %.0f min ago (cooldown %d min)" % (
            sym, age, PUSH_COOLDOWN_MINUTES)
    return True, "%s last pushed %.0f min ago" % (sym, age)


def co_breaches(ticker: str, now: datetime,
                recent: Iterable[Tuple[str, datetime, float]]) -> List[Tuple[str, float]]:
    """Other EQUITY-BETA tickers that breached within the window, newest first.

    Only the push roster counts as a co-breach. An oil move alongside a QQQ move is not breadth
    in any sense the book cares about -- measured on 10-08, the morning's "three ticker" cluster
    was IBIT + SMH + USO, three unrelated complexes, while the pair that mattered was QQQ + SMH.
    """
    sym = (ticker or "").strip().upper()
    cutoff = now - timedelta(minutes=CO_BREACH_WINDOW_MINUTES)
    out = [(t.strip().upper(), mv) for (t, ts, mv) in recent
           if t and t.strip().upper() != sym
           and t.strip().upper() in PUSH_TICKERS
           and cutoff <= ts <= now]
    seen, uniq = set(), []
    for t, mv in out:
        if t not in seen:
            seen.add(t)
            uniq.append((t, mv))
    return uniq


def format_message(ticker: str, move_pct: float, timeframe_min: int, now_utc: datetime,
                   co: Optional[List[Tuple[str, float]]] = None) -> str:
    """The message, in plain words, with the time in MOUNTAIN TIME.

    MT via `zoneinfo`, never `TZ=` in a shell: this machine's Git Bash ships no tzdata, so `TZ=`
    is silently ignored and every zone returns UTC labelled GMT -- wrong by six hours and a day
    boundary, with no error raised. The whole point of the line is when it happened.
    """
    sym = (ticker or "").upper()
    mt = now_utc.astimezone(MT)
    sign = "+" if move_pct >= 0 else ""
    head = "**%s %s%.2f%%** in %d min — %s" % (
        sym, sign, move_pct, timeframe_min, mt.strftime("%-I:%M %p %Z").lstrip("0")
        if os.name != "nt" else mt.strftime("%I:%M %p %Z").lstrip("0"))
    if co:
        head += "\nAlso breached within %d min: %s" % (
            CO_BREACH_WINDOW_MINUTES,
            ", ".join("%s %s%.2f%%" % (t, "+" if m >= 0 else "", m) for t, m in co))
    return head


async def push_breach(ticker: str, move_pct: float, timeframe_min: int,
                      now: Optional[datetime] = None,
                      recent: Optional[Iterable[Tuple[str, datetime, float]]] = None,
                      webhook_url: Optional[str] = None) -> dict:
    """Push one breach if phase 1 says so. NEVER RAISES.

    A notifier that can fail the webhook it notifies about would turn a missed message into a
    missed INGEST, which is strictly worse: the row is the evidence and the message is a
    convenience. Every outcome is returned so the caller can log one line.
    """
    now = now or datetime.now(timezone.utc)
    sym = (ticker or "").strip().upper()
    # The co-breach is computed BEFORE the decision, because it can override the cooldown.
    co = co_breaches(sym, now, recent or []) if is_pushable(sym) else []
    ok, reason = should_push(sym, now, _last_push.get(sym), has_co_breach=bool(co))
    if not ok:
        return {"pushed": False, "reason": reason}

    url = webhook_url if webhook_url is not None else (os.getenv("DISCORD_WEBHOOK_ALERTS") or "")
    if not url:
        # Honest absence, and NOT recorded as a push: marking the cooldown here would suppress
        # the next real one on the strength of a message that never left.
        return {"pushed": False, "reason": "DISCORD_WEBHOOK_ALERTS not set"}

    content = format_message(sym, move_pct, timeframe_min, now, co)
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, json={"content": content})
        if resp.status_code >= 300:
            return {"pushed": False, "reason": "discord HTTP %d" % resp.status_code}
    except Exception as exc:
        logger.warning("[hermes.push] %s failed: %s", sym, exc)
        return {"pushed": False, "reason": "%s: %s" % (type(exc).__name__, exc)}

    # Only a DELIVERED message starts the cooldown.
    _last_push[sym] = now
    return {"pushed": True, "reason": reason, "co_breaches": [t for t, _ in co],
            "content": content}


async def push_session_alert(ticker: str, move_pct: Optional[float],
                             prior_close: Optional[float],
                             now: Optional[datetime] = None,
                             co: Optional[List[Tuple[str, float]]] = None,
                             webhook_url: Optional[str] = None,
                             banner: Optional[str] = None) -> dict:
    """Phase 2's push — the SESSION displacement alarm. NEVER RAISES.

    Deliberately in phase 1's module and on phase 1's webhook (R-IV.820(h)2: "same webhook and
    co-breach logic"). One place decides where a Hermes message goes, so a reader of either
    message is seeing the same roster reasoned about the same way, and a change of destination
    cannot move one phase and leave the other behind.

    IT HAS ITS OWN COOLDOWN STATE, AND NOT PHASE 1'S. The two alarms answer different questions
    on different clocks -- phase 1 a 30-minute velocity breach, phase 2 a session-to-date
    displacement -- so sharing `_last_push` would let a velocity breach suppress the session
    alert that finally explains it, which is the exact miss phase 2 exists to fix. Phase 2's
    ladder lives in the poll, keyed by session date.

    `banner` prepends a line to the message and defaults to None, which is byte-for-byte the
    message a real alert sends. It exists for R-IV.864(d)'s go-live test: a test alert that the
    principal cannot tell apart from a real one is a liability, not a test, and the alternative
    — a second delivery path used only for testing — would prove the wrong path works.
    """
    from webhooks.hermes_session import format_message as session_message

    now = now or datetime.now(timezone.utc)
    sym = (ticker or "").strip().upper()
    if move_pct is None or prior_close is None:
        # NOT EVALUABLE, and not recorded as anything: a push marked as sent on a figure that
        # could not be computed would suppress the next real one.
        return {"pushed": False, "reason": "no displacement for %s" % (sym or "?")}

    url = webhook_url if webhook_url is not None else (os.getenv("DISCORD_WEBHOOK_ALERTS") or "")
    if not url:
        return {"pushed": False, "reason": "DISCORD_WEBHOOK_ALERTS not set"}

    last = prior_close * (1 + move_pct / 100.0)
    content = session_message(sym, move_pct, prior_close, last, now, co)
    if banner:
        content = "%s\n%s" % (banner, content)
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, json={"content": content})
        if resp.status_code >= 300:
            return {"pushed": False, "reason": "discord HTTP %d" % resp.status_code}
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[hermes.session] %s failed: %s", sym, exc)
        return {"pushed": False, "reason": "%s: %s" % (type(exc).__name__, exc)}
    return {"pushed": True, "reason": "session displacement %+.2f%%" % move_pct,
            "content": content}
