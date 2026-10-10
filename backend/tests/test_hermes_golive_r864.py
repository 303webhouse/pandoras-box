"""Hermes phase 2 go-live — registration, blindness, TEST banner — R-IV.864(d).

THE POINT OF THESE TESTS. Switching the alarm on adds three ways to be wrong that the dark
build could not have:

  1. the job runs but `/health` cannot see it, so nobody learns when it stops;
  2. `/health` CAN see it but reports flatline every night, because an RTH-only job was
     registered without saying so — a false alarm about the alarm, which is how a real one gets
     ignored (R-IV.127: a guard must be anchored to the window it guards);
  3. the job records a clean pass every minute while it cannot price anything, so "ok" means
     "the loop is spinning" rather than "the alarm can see".

Convention #30: every "it is visible / it fires" is paired with the case that must not.
"""
from __future__ import annotations

import ast
import asyncio
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from jobs import hermes_session_poll as poll  # noqa: E402
from jobs.stable_jobs import OutputCheckFailed  # noqa: E402
from stable_engine import job_status as js  # noqa: E402
from webhooks import hermes_push as hp  # noqa: E402

ET = ZoneInfo("America/New_York")
IN_SESSION = datetime(2026, 10, 8, 14, 0, tzinfo=ET)       # Thursday, inside RTH
AFTER_CLOSE = datetime(2026, 10, 8, 20, 0, tzinfo=ET)      # same day, session shut
WEEKEND = datetime(2026, 10, 10, 11, 0, tzinfo=ET)         # Saturday


# ── 1. the job is registered, and registered as RTH-only ─────────────────────

def test_job_is_mapped_to_a_feed():
    """Without this mapping the job's feed falls back to its own name, which has no SLO, and
    `feed_flatline` exempts anything it has no SLO for — so it would appear on /health and
    could never be reported stale."""
    assert js.JOB_FEEDS[poll.JOB_NAME] == "hermes_session"


def test_the_feed_has_an_slo():
    assert js.SLO_SECONDS["hermes_session"] == 10 * 60


def test_the_feed_is_declared_rth_only():
    assert "hermes_session" in js.RTH_ONLY_FEEDS


def test_quiet_overnight_is_not_flatline():
    """The pair that matters: the same absence of data is dead inside the session and expected
    outside it. A job registered without the RTH-only declaration would fail this."""
    assert js.feed_flatline("hermes_session", None, AFTER_CLOSE) is False
    assert js.feed_flatline("hermes_session", None, WEEKEND) is False


def test_quiet_during_the_session_IS_flatline():
    assert js.feed_flatline("hermes_session", None, IN_SESSION) is True
    assert js.feed_flatline("hermes_session", 11 * 60, IN_SESSION) is True
    assert js.feed_flatline("hermes_session", 60, IN_SESSION) is False


# ── 2. the loop is actually started ──────────────────────────────────────────

def _main_imports() -> set:
    """Every module named in a real `import`/`from` statement in main.py.

    PARSED, NOT GREPPED. `"hermes_session_poll" in src` would pass on the COMMENT that explains
    the wiring — the trap hit three times in R-IV.820-861 (the windowless get_bars call,
    SUPPRESS_ALWAYS, and _last_push, where the test matched the docstring saying why the thing
    is absent). A test about code must read code.
    """
    src = open(__file__.rsplit("tests", 1)[0] + "main.py", encoding="utf-8").read()
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


def test_main_imports_the_poll():
    assert "jobs.hermes_session_poll" in _main_imports()


def test_the_prose_alone_would_not_satisfy_this():
    """The positive control for the test above: prove the assertion is about parsed imports by
    showing a comment mentioning the module does NOT create one."""
    tree = ast.parse("# jobs.hermes_session_poll is wired in below\nx = 1\n")
    found = {n.module for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) and n.module}
    assert "jobs.hermes_session_poll" not in found


# ── 3. a blind pass is not a success ─────────────────────────────────────────

def test_blind_pass_raises_output_check_failed(monkeypatch):
    async def all_unevaluable():
        return [{"ticker": "SPY", "move_pct": None, "alert": False, "reason": "no mark"},
                {"ticker": "QQQ", "move_pct": None, "alert": False, "reason": "no mark"}]

    monkeypatch.setattr(poll, "evaluate_once", all_unevaluable)
    with pytest.raises(OutputCheckFailed):
        asyncio.run(poll._recorded_pass())


def test_one_evaluable_symbol_is_enough(monkeypatch):
    """The pair: a partial outage is degraded, not blind, and must not fire the alarm-about-the
    -alarm. Only NOTHING priceable counts as a failed pass."""
    async def one_good():
        return [{"ticker": "SPY", "move_pct": None, "alert": False, "reason": "no mark"},
                {"ticker": "QQQ", "move_pct": -0.4, "alert": False, "reason": "below"}]

    monkeypatch.setattr(poll, "evaluate_once", one_good)
    assert asyncio.run(poll._recorded_pass()) == {"symbols": 2}


def test_no_symbols_at_all_is_not_a_failure(monkeypatch):
    """Outside RTH `evaluate_once` returns []. That is not blindness — there is nothing to see —
    and `all()` over an empty list is True, which would have made every off-hours pass a
    failure had the emptiness not been checked first."""
    async def nothing():
        return []

    monkeypatch.setattr(poll, "evaluate_once", nothing)
    assert asyncio.run(poll._recorded_pass()) == {"symbols": 0}


# ── 4. the TEST banner ───────────────────────────────────────────────────────

class _FakeResp:
    status_code = 204


class _FakeClient:
    sent: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        _FakeClient.sent.append(json)
        return _FakeResp()


@pytest.fixture(autouse=True)
def _capture(monkeypatch):
    _FakeClient.sent = []
    monkeypatch.setattr(hp.httpx, "AsyncClient", _FakeClient)


def _push(**kw):
    return asyncio.run(hp.push_session_alert(
        "QQQ", -1.80, 500.0, datetime(2026, 10, 10, 18, 0, tzinfo=ET),
        webhook_url="https://example.invalid/hook", **kw))


def test_banner_is_prepended():
    res = _push(banner="**TEST**")
    assert res["pushed"] is True
    assert _FakeClient.sent[-1]["content"].startswith("**TEST**\n")


def test_without_a_banner_the_message_is_unchanged():
    """The pair, and the one that protects the real alert: the default path must send exactly
    what it sent before the banner existed."""
    plain = _push()["content"]
    assert not plain.startswith("**TEST**")
    labelled = _push(banner="**TEST**")["content"]
    assert labelled == "**TEST**\n" + plain
