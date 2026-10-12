"""Phone alerts via ntfy — R-IV.901(b).

Two things are being held here, and they are different kinds of rule.

**THE TOPIC IS A CREDENTIAL IN BOTH DIRECTIONS.** Anyone who knows it can read every alert the
principal gets AND publish to his phone. So it must appear in no log line, no error message and
no returned reason — tested by driving every failure path and inspecting what came out.

**THE PAYLOAD CARRIES NO MONEY.** R-IV.901(b)2 bars dollar amounts, account values and position
sizes from a relay we do not control. That is enforced by a signature that accepts no amount and
a guard that REFUSES rather than scrubs — a silently stripped figure is a message whose meaning
changed with nobody noticing.
"""
from __future__ import annotations

import asyncio
import logging
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from integrations import ntfy_push as n  # noqa: E402
from integrations.ntfy_push import MoneyInPayload, build_message  # noqa: E402

TOPIC = "abcdefghijklmnopqrstuvwxyz0123456789ABCD"     # 40 chars, same shape as the real one


@pytest.fixture(autouse=True)
def _topic(monkeypatch):
    monkeypatch.setenv(n.TOPIC_ENV, TOPIC)


# ── the payload carries no money ────────────────────────────────────────────

def test_a_clean_alert_builds():
    msg = build_message("QQQ", "session move -1.95%", "look at the session")
    assert "QQQ" in msg and "-1.95%" in msg


def test_a_percentage_is_allowed():
    """The ban is on figures that disclose the BOOK. A percentage move names no money, no
    account value and no size."""
    assert "1.95%" in build_message("QQQ", "session move -1.95%", "look")


@pytest.mark.parametrize("bad", [
    "Total P&L -12.00",
    "down $1,240 today",
    "account at 12,217.86",
    "USD 500 at risk",
    "£300 daily cap hit",
])
def test_money_is_REFUSED_not_scrubbed(bad):
    """Refused, not stripped: a silently scrubbed figure is a message whose meaning changed and
    a caller that goes on breaking the rule."""
    with pytest.raises(MoneyInPayload):
        build_message("KNX", "B2 three-day cut", bad)


def test_the_B2_DISCORD_TEXT_WOULD_BE_REFUSED():
    """The case that made this guard necessary. The Discord B2 line reads "Total P&L -12.00 at
    the close…", so forwarding the Discord text to ntfy would have shipped a dollar figure to a
    third-party relay. The job therefore REBUILDS the payload, and this proves the old text
    could not have gone through by accident."""
    with pytest.raises(MoneyInPayload):
        build_message("KNX", "B2 three-day cut",
                      "Total P&L -12.00 at the close of the 3rd full trading session")


def test_there_is_no_amount_parameter_to_pass_one_through():
    """Structural: the signature accepts ticker/type/action and nothing else, so a caller cannot
    hand over a dollar figure even by accident."""
    import inspect

    params = list(inspect.signature(build_message).parameters)
    assert params == ["ticker", "alert_type", "action"], params


def test_every_message_carries_the_provenance_marker():
    """Its ABSENCE is what the principal can check. Its presence proves nothing — a spoofer
    with the topic could copy it — and the module says so."""
    assert "[%s]" % n.PROVENANCE in build_message("SPY", "velocity breach", "check the chart")


# ── the topic never leaks ───────────────────────────────────────────────────

def test_an_unset_topic_is_reported_without_inventing_one(monkeypatch, caplog):
    monkeypatch.delenv(n.TOPIC_ENV, raising=False)
    with caplog.at_level(logging.ERROR, logger="ntfy.push"):
        out = asyncio.run(n.send("SPY", "velocity breach", "check"))
    assert out["sent"] is False
    assert n.TOPIC_ENV in out["reason"]


def test_the_topic_is_absent_from_every_failure_path(monkeypatch, caplog):
    """Driven, not asserted in prose: force an exception and a bad status, then inspect every log
    record and every returned reason for the topic."""
    class _Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(n.httpx if hasattr(n, "httpx") else __import__("httpx"),
                        "AsyncClient", _Boom, raising=False)
    import httpx as _h
    monkeypatch.setattr(_h, "AsyncClient", _Boom)

    with caplog.at_level(logging.DEBUG, logger="ntfy.push"):
        out = asyncio.run(n.send("SPY", "velocity breach", "check"))
    assert out["sent"] is False
    blob = " ".join([r.getMessage() for r in caplog.records]) + " " + str(out)
    assert TOPIC not in blob, "the topic leaked into a log line or a returned reason"


def test_the_log_names_the_topic_LENGTH_not_the_topic(monkeypatch, caplog):
    class _Resp:
        status_code = 500

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    import httpx as _h
    monkeypatch.setattr(_h, "AsyncClient", _Client)
    with caplog.at_level(logging.ERROR, logger="ntfy.push"):
        out = asyncio.run(n.send("SPY", "velocity breach", "check"))
    assert out["sent"] is False
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert TOPIC not in blob
    assert "topic len 40" in blob, blob


def test_the_endpoint_is_built_from_the_topic_but_never_logged():
    assert n._endpoint().endswith("/" + TOPIC)
    assert n._endpoint().startswith("https://ntfy.sh/")


# ── it is additive: Discord's verdict is never affected ─────────────────────

def test_the_hermes_ntfy_leg_cannot_un_deliver_discord(monkeypatch):
    """R-IV.901(b)3 runs both relays in parallel. The ntfy leg is called AFTER Discord has been
    recorded as delivered, and a failure in it must not turn a delivered alert into a failed
    one -- a second channel able to un-deliver the first would be worse than either alone."""
    from webhooks import hermes_push as hp

    async def boom(*a, **k):
        raise RuntimeError("ntfy down")

    monkeypatch.setattr("integrations.ntfy_push.send", boom)
    out = asyncio.run(hp._also_ntfy("SPY", "velocity breach", "check"))
    assert out["sent"] is False          # reported...
    assert "reason" in out               # ...with a reason, and no exception escaped
