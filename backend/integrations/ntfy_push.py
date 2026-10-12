"""Phone alerts via ntfy.sh — R-IV.901(b).

WHY THIS EXISTS. The principal did not receive Saturday's Discord TEST and prefers not to use
Discord. ntfy is a push relay: the phone app subscribes to a topic and anything POSTed to that
topic arrives as a notification.

THE TOPIC IS A CREDENTIAL IN BOTH DIRECTIONS, and that is the fact this module is built around.
Anyone who knows it can READ every alert the principal receives AND PUBLISH to his phone — on
ntfy.sh's free tier, obscurity is the only control there is. So:

  * it is never logged, never echoed, never put in an error message;
  * it lives in Railway (`NTFY_TOPIC`) and, for the principal only, in
    `C:\\lane-state\\NTFY-TOPIC.txt`;
  * `_endpoint()` returns the URL but every log line names the TOPIC LENGTH, never the topic.

**A SPOOF IS POSSIBLE AND IS NOT SOLVED HERE.** Because publishing needs only the topic, anyone
who learns it can send the principal a convincing fake — "SPY -5%, close everything". Flagged
rather than fixed: ntfy's answer is an access token with publish ACLs, which needs an account.
Every message this module sends therefore carries a fixed `PROVENANCE` marker, so a message
WITHOUT it is not from the hub. That is a check the principal can make, not a control that stops
the send.

PAYLOAD DISCIPLINE IS STRUCTURAL, NOT A CONVENTION. R-IV.901(b)2 forbids dollar amounts, account
values and position sizes — this is a third-party relay, so the payload transits and is stored by
a service we do not control. `build_message()` therefore accepts ONLY ticker, alert type and
action, and `_assert_no_money()` refuses a string carrying a currency figure. A rule enforced by
a reviewer's attention is a rule that lapses; one enforced by a signature does not.

A PERCENTAGE IS NOT A DOLLAR AMOUNT. "QQQ down 1.95% on the session" names no money, no account
value and no size, so it is allowed — the ban is on figures that disclose the book.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger("ntfy.push")

BASE = "https://ntfy.sh"
TOPIC_ENV = "NTFY_TOPIC"

# Every hub message carries this. Its ABSENCE is the signal that a notification did not come
# from here; its presence proves nothing, since a spoofer could copy it.
PROVENANCE = "pandora"

# Figures that would disclose the book. Deliberately crude and deliberately refusing rather than
# scrubbing: a silently stripped amount is a message whose meaning changed without anyone
# noticing, and the caller should be fixed instead.
_MONEY = re.compile(r"""(?x)
      [\$£€]\s*\d                 # $12, £ 12
    | \b\d[\d,]*\.\d{2}\b(?!\s*%)  # 1,234.56 and 12.00 -- money to the cent, NOT a percentage
    | \b(?:USD|usd)\s*\d
""")
# THE PERCENTAGE EXCLUSION ABOVE IS LOAD-BEARING. Without it, this matched "1.95" inside
# "-1.95%" and refused every Hermes alert — a session move IS a percentage to two places, so the
# guard would have silenced the phone entirely, which is the exact failure R-IV.901(b) exists to
# end. The test for the ALLOWED case caught it, not the test for the banned ones. A guard that
# refuses legitimate traffic is as much a defect as one that lets bad traffic through, and this
# one failed in the direction nobody notices: no alerts at all.


class MoneyInPayload(ValueError):
    """A caller tried to send a figure that discloses the book."""


def _assert_no_money(text: str) -> None:
    m = _MONEY.search(text or "")
    if m:
        raise MoneyInPayload(
            "refusing to send %r: it carries %r, and R-IV.901(b)2 bars dollar amounts, account "
            "values and position sizes from this relay" % (text[:60], m.group(0)))


def topic() -> str:
    """The topic, or "" when unset. NEVER logged by any caller."""
    return (os.getenv(TOPIC_ENV) or "").strip()


def is_configured() -> bool:
    return bool(topic())


def _endpoint() -> Optional[str]:
    t = topic()
    return "%s/%s" % (BASE, t) if t else None


def build_message(ticker: str, alert_type: str, action: str) -> str:
    """The whole payload: ticker, alert type, action needed. Nothing else is accepted.

    There is no `amount` parameter and no `**kwargs`, so a caller cannot pass a dollar figure
    even by accident -- which is the point. The result is still checked, because the three
    strings could themselves carry one.
    """
    sym = (ticker or "?").strip().upper()
    kind = (alert_type or "alert").strip()
    act = (action or "").strip()
    text = "%s — %s\n%s\n[%s]" % (sym, kind, act, PROVENANCE)
    _assert_no_money(text)
    return text


async def send(ticker: str, alert_type: str, action: str, *,
               title: Optional[str] = None, priority: str = "default") -> dict:
    """POST one notification. NEVER RAISES except on a money violation, which is a caller bug.

    A money violation is deliberately NOT swallowed: silently dropping it would hide a payload
    rule being broken, and silently sending it would break the rule.
    """
    import httpx

    url = _endpoint()
    if not url:
        # The topic's LENGTH, never the topic.
        logger.error("[ntfy] %s not set; %s %s not sent", TOPIC_ENV, ticker, alert_type)
        return {"sent": False, "reason": "%s not set" % TOPIC_ENV}

    body = build_message(ticker, alert_type, action)       # raises on money
    headers = {"Title": (title or "Pandora: %s" % (ticker or "alert"))[:120],
               "Priority": priority, "Tags": "chart_with_downwards_trend"}
    _assert_no_money(headers["Title"])

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, content=body.encode("utf-8"), headers=headers)
        if resp.status_code >= 300:
            logger.error("[ntfy] HTTP %d for %s %s (topic len %d)",
                         resp.status_code, ticker, alert_type, len(topic()))
            return {"sent": False, "reason": "ntfy HTTP %d" % resp.status_code}
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[ntfy] send failed for %s %s: %s", ticker, alert_type, type(exc).__name__)
        return {"sent": False, "reason": "%s" % type(exc).__name__}

    logger.info("[ntfy] sent %s %s (topic len %d)", ticker, alert_type, len(topic()))
    return {"sent": True, "body": body}
