"""Hermes phase 2's RTH poll — the live half — R-IV.861(d).

The DECISION is pure and already tested (test_hermes_session_r820.py, 71 tests, thresholds
calibrated over 19 sessions). This covers the part with a clock, a network and state in it, which
is where the failures that matter live: a ladder that survives a session boundary, an alert
recorded as sent when the webhook failed, a mark that is stale rather than absent.

Convention #30: each "it alerts" is paired with a case that must not, and each state write with a
case where state must NOT move.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from jobs import hermes_session_poll as poll  # noqa: E402
from webhooks import hermes_session as hs  # noqa: E402

ET = ZoneInfo("America/New_York")
MID_SESSION = datetime(2026, 10, 8, 14, 0, tzinfo=ET)       # a Thursday, inside RTH
NEXT_SESSION = datetime(2026, 10, 9, 14, 0, tzinfo=ET)
AFTER_CLOSE = datetime(2026, 10, 8, 17, 0, tzinfo=ET)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    poll.reset_for_tests()
    monkeypatch.delenv(hs.FLAG, raising=False)
    yield
    poll.reset_for_tests()


def _wire(monkeypatch, marks, prior=600.0, pushed=True, record=None):
    """Fake the two vendor reads and the push. Returns the list of pushes attempted."""
    attempts = record if record is not None else []

    async def _prior(ticker):
        return prior

    async def _mark(ticker):
        return marks.get(ticker)

    async def _push(sym, move, pc, now, co=None, **_):
        attempts.append({"ticker": sym, "move": move, "co": list(co or [])})
        return {"pushed": pushed, "reason": "test"}

    monkeypatch.setattr(poll, "_prior_session_close", _prior)
    monkeypatch.setattr(poll, "_mark", _mark)
    import webhooks.hermes_push as hp
    monkeypatch.setattr(hp, "push_session_alert", _push)
    return attempts


class TestTheSessionWindowGatesTheWholePass:
    def test_outside_regular_hours_it_does_nothing_at_all(self, monkeypatch):
        _wire(monkeypatch, {"QQQ": 580.0})
        assert _run(poll.evaluate_once(AFTER_CLOSE)) == []

    def test_inside_regular_hours_it_evaluates_every_tracked_symbol(self, monkeypatch):
        _wire(monkeypatch, {"SPY": 600.0, "QQQ": 600.0, "SMH": 600.0})
        out = _run(poll.evaluate_once(MID_SESSION))
        assert sorted(r["ticker"] for r in out) == ["QQQ", "SMH", "SPY"]
        assert all(r["alert"] is False for r in out), out


class TestTheLadderIsSessionScoped:
    def test_a_new_session_clears_it_so_the_first_crossing_still_alerts(self, monkeypatch):
        """THE DESIGN POINT. A −2% Monday after a −2% Friday must not read as "already told
        you" — carrying the figure across the boundary would silence the morning's first
        crossing."""
        monkeypatch.setenv(hs.FLAG, "1")
        a = _wire(monkeypatch, {"QQQ": 588.0})          # −2.0% on a 600 prior close
        first = _run(poll.evaluate_once(MID_SESSION))
        assert any(r["ticker"] == "QQQ" and r["pushed"] for r in first), first
        assert len(a) == 1

        # Same displacement again, same session: the ladder holds it.
        again = _run(poll.evaluate_once(MID_SESSION))
        assert not any(r["pushed"] for r in again)
        assert len(a) == 1

        # Next session: it alerts again.
        nxt = _run(poll.evaluate_once(NEXT_SESSION))
        assert any(r["ticker"] == "QQQ" and r["pushed"] for r in nxt), nxt
        assert len(a) == 2

    def test_the_roll_is_keyed_on_the_ET_DATE_not_a_UTC_one(self, monkeypatch):
        """20:00Z on 10-08 and 01:00Z on 10-09 are the SAME ET session afternoon/evening; a
        UTC-keyed roll would clear the ladder mid-session."""
        et_evening = datetime(2026, 10, 8, 15, 59, tzinfo=ET)
        assert poll._roll_session(et_evening.astimezone(ET).date().isoformat()) is True
        assert poll._roll_session(et_evening.astimezone(ET).date().isoformat()) is False

    def test_rolling_clears_the_prior_close_too(self, monkeypatch):
        """Yesterday's prior close is not today's. Keeping it would measure Tuesday's
        displacement from Sunday's base."""
        poll._prior_close["QQQ"] = 123.0
        poll._last_alerted["QQQ"] = -2.0
        poll._roll_session("2026-10-09")
        assert poll._prior_close == {} and poll._last_alerted == {}


class TestOnlyADeliveredMessageAdvancesTheLadder:
    def test_a_failed_push_leaves_the_ladder_alone_so_the_next_tick_retries(self, monkeypatch):
        """Phase 1's rule, for phase 1's reason: recording an alert that never left would
        suppress the next real one on the strength of a message nobody received."""
        monkeypatch.setenv(hs.FLAG, "1")
        a = _wire(monkeypatch, {"QQQ": 588.0}, pushed=False)
        first = _run(poll.evaluate_once(MID_SESSION))
        assert any(r["alert"] and not r["pushed"] for r in first), first
        assert poll._last_alerted == {}, "a failed push must not advance the ladder"

        second = _run(poll.evaluate_once(MID_SESSION))
        assert any(r["alert"] for r in second), "it must try again"
        assert len(a) == 2

    def test_a_delivered_push_does_advance_it(self, monkeypatch):
        monkeypatch.setenv(hs.FLAG, "1")
        _wire(monkeypatch, {"QQQ": 588.0}, pushed=True)
        _run(poll.evaluate_once(MID_SESSION))
        assert poll._last_alerted.get("QQQ") == pytest.approx(-2.0)


class TestItShipsDark:
    def test_with_the_flag_off_it_evaluates_but_never_pushes(self, monkeypatch):
        """The flag gates the PUSH, not the evaluation — so a live session can be watched
        against the calibrated thresholds before anything reaches the phone. An alarm whose
        first real test is its first real alert has never been tested."""
        a = _wire(monkeypatch, {"QQQ": 588.0})
        out = _run(poll.evaluate_once(MID_SESSION))
        qqq = [r for r in out if r["ticker"] == "QQQ"][0]
        assert qqq["alert"] is True, "it still DECIDES"
        assert qqq["pushed"] is False and qqq["enabled"] is False
        assert a == [], "nothing was sent"
        assert poll._last_alerted == {}, "and the ladder did not move"

    def test_with_the_flag_on_it_pushes(self, monkeypatch):
        monkeypatch.setenv(hs.FLAG, "1")
        a = _wire(monkeypatch, {"QQQ": 588.0})
        _run(poll.evaluate_once(MID_SESSION))
        assert len(a) == 1 and a[0]["ticker"] == "QQQ"


class TestAMissingMarkRefusesRatherThanGuesses:
    def test_no_mark_is_NOT_EVALUABLE_and_never_an_alert(self, monkeypatch):
        monkeypatch.setenv(hs.FLAG, "1")
        a = _wire(monkeypatch, {})                      # every mark absent
        out = _run(poll.evaluate_once(MID_SESSION))
        assert all(r["alert"] is False for r in out)
        assert all("NOT EVALUABLE" in r["reason"] for r in out), out
        assert a == []

    def test_no_prior_close_is_also_NOT_EVALUABLE(self, monkeypatch):
        monkeypatch.setenv(hs.FLAG, "1")
        a = _wire(monkeypatch, {"QQQ": 588.0}, prior=None)
        out = _run(poll.evaluate_once(MID_SESSION))
        assert all(r["alert"] is False for r in out)
        assert a == []

    def test_the_mark_reader_has_no_stale_fallback(self):
        """A stale mark is worse than none: it produces a confident displacement from a price
        that is not the price, and the NOT EVALUABLE branch exists so this can refuse."""
        import inspect

        src = inspect.getsource(poll._mark)
        assert "return None" in src
        assert "last_good" not in src and "_cache" not in src


class TestCoBreachesAreComputedBeforeAnyPush:
    def test_a_symbol_can_name_one_whose_message_has_not_been_sent(self, monkeypatch):
        """Phase 1 learned this on 10-08: QQQ's and SMH's webhooks landed ONE SECOND apart, so
        a backwards-only lookup meant whichever arrived first could not name the other. Phase 2
        computes every displacement first, so the pair is visible to both."""
        monkeypatch.setenv(hs.FLAG, "1")
        # QQQ −2.0% (line 1.75) and SMH −4.0% (line 3.0): both over.
        a = _wire(monkeypatch, {"QQQ": 588.0, "SMH": 576.0})
        _run(poll.evaluate_once(MID_SESSION))
        by = {x["ticker"]: x for x in a}
        assert set(by) == {"QQQ", "SMH"}
        assert [t for t, _ in by["QQQ"]["co"]] == ["SMH"]
        assert [t for t, _ in by["SMH"]["co"]] == ["QQQ"]

    def test_a_symbol_inside_its_line_is_not_a_co_breach(self, monkeypatch):
        """CONTROL. SPY at −1.2% is over ITS 1.0% line; QQQ at −1.2% is inside its 1.75%, so
        QQQ must not appear beside SPY."""
        monkeypatch.setenv(hs.FLAG, "1")
        a = _wire(monkeypatch, {"SPY": 592.8, "QQQ": 592.8})
        _run(poll.evaluate_once(MID_SESSION))
        by = {x["ticker"]: x for x in a}
        assert "SPY" in by and "QQQ" not in by
        assert by["SPY"]["co"] == []


class TestTheTwoPhasesShareAWebhookButNotAState:
    def test_phase_2_pushes_through_phase_1s_module(self):
        """R-IV.820(h)2: same webhook. One place decides where a Hermes message goes, so a
        change of destination cannot move one phase and leave the other behind."""
        from webhooks import hermes_push

        assert hasattr(hermes_push, "push_session_alert")

    def test_phase_2_does_NOT_share_phase_1s_cooldown(self):
        """Sharing `_last_push` would let a 30-minute velocity breach suppress the session alert
        that finally explains it — the exact miss phase 2 exists to fix."""
        import inspect

        from webhooks import hermes_push

        # PROSE STRIPPED FIRST — docstring and comments. This is the THIRD time in this
        # register that a "X must not appear in the code" test has failed on the comment
        # explaining why X is wrong (the windowless `get_bars` call, `SUPPRESS_ALWAYS`, and now
        # `_last_push`). The rule the three of them teach: such a test asserts about CODE, so it
        # has to remove the writing first, every time.
        import ast

        tree = ast.parse(inspect.getsource(hermes_push.push_session_alert).lstrip())
        fn = tree.body[0]
        if (fn.body and isinstance(fn.body[0], ast.Expr)
                and isinstance(fn.body[0].value, ast.Constant)
                and isinstance(fn.body[0].value.value, str)):
            fn.body = fn.body[1:]                       # drop the docstring
        code = ast.unparse(fn)                           # comments do not survive unparse
        assert "_last_push" not in code, code

    def test_an_uncomputable_displacement_is_not_recorded_as_a_push(self):
        from webhooks.hermes_push import push_session_alert

        res = _run(push_session_alert("QQQ", None, 600.0))
        assert res["pushed"] is False
        res2 = _run(push_session_alert("QQQ", -2.0, None))
        assert res2["pushed"] is False

    def test_a_missing_webhook_is_an_honest_absence(self, monkeypatch):
        monkeypatch.delenv("DISCORD_WEBHOOK_ALERTS", raising=False)
        from webhooks.hermes_push import push_session_alert

        res = _run(push_session_alert("QQQ", -2.0, 600.0, webhook_url=""))
        assert res["pushed"] is False and "not set" in res["reason"]


class TestTheLoopCannotDie:
    def test_run_forever_catches_everything(self):
        import inspect

        src = inspect.getsource(poll.run_forever)
        assert "except Exception" in src
        assert "await asyncio.sleep(POLL_SECONDS)" in src

    def test_evaluate_once_takes_an_injectable_now(self):
        """So a test can place a pass inside or outside a session without touching a clock —
        and so the thresholds' replay and the live alarm answer one question."""
        import inspect

        assert "now" in inspect.signature(poll.evaluate_once).parameters
