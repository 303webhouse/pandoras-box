"""R-IV.1515(h) — the hook source check, with the switch left at log.

1. The first refusal per hook path per UTC day sends one push naming the path and the address.
2. The address is the entry Railway's edge wrote, never the first forwarded-for entry, which is
   the one value in that header a sender can choose.
3. lab_registered's pass is due the next morning, so Monday evenings stop reading "degraded".
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integrations import ntfy_push
from stable_engine import signals_freshness as sf
from stable_engine.market_calendar import is_trading_day
from utils import write_guard as wg

ET = ZoneInfo("America/New_York")
TV = "52.89.214.238"
EDGE = "84.17.44.221"
ELSEWHERE = "203.0.113.9"
HOOK = "/webhook/tradingview"


# ── (h)2 the address ────────────────────────────────────────────────────────

@pytest.mark.parametrize("headers, expected", [
    ({"x-forwarded-for": "%s, %s" % (TV, EDGE), "x-real-ip": TV}, TV),       # production's shape
    ({"x-forwarded-for": "%s, %s, %s" % (TV, ELSEWHERE, EDGE)}, ELSEWHERE),  # a forged first entry
    ({"x-forwarded-for": "%s, %s" % (ELSEWHERE, EDGE), "x-real-ip": TV}, ELSEWHERE),
    ({"x-forwarded-for": TV, "x-real-ip": ELSEWHERE}, ELSEWHERE),            # too short: fallback
    ({"x-real-ip": ELSEWHERE}, ELSEWHERE),
    ({"x-forwarded-for": TV}, ""),                                           # first entry alone
    ({}, ""),
], ids=["production", "forged-first", "edge-over-real-ip", "short-xff", "real-ip-only",
        "first-entry-alone", "nothing"])
def test_the_address_is_the_entry_the_edge_wrote(headers, expected):
    assert wg.source_address(headers) == expected


def test_a_forged_first_entry_does_not_pass_as_tradingview():
    assert not wg.source_is_tradingview({"x-forwarded-for": "%s, %s, %s" % (TV, ELSEWHERE, EDGE)})
    assert wg.source_is_tradingview({"x-forwarded-for": "%s, %s" % (TV, EDGE)})


# ── (h)1 the middleware calls the alarm only on a real refusal ──────────────

def _tiny():
    a = FastAPI()
    for p in [p for p, (g, _) in wg.ALLOWLIST.items() if g == "hook"]:
        a.add_api_route(p, (lambda: {"ran": True}), methods=["POST"])
    a.add_middleware(wg.WriteGuardMiddleware)
    return a


@pytest.fixture
def alarms(monkeypatch):
    seen = []
    monkeypatch.setattr(wg, "record", lambda ev: None)
    monkeypatch.setattr(wg, "_schedule_refusal_alarm",
                        lambda path, headers: seen.append((path, wg.source_address(headers))))
    return seen


def _post(path=HOOK, sender=ELSEWHERE):
    return TestClient(_tiny()).post(path, headers={"X-Forwarded-For": "%s, %s" % (sender, EDGE)})


def test_a_refusal_raises_the_alarm_with_path_and_address(monkeypatch, alarms):
    monkeypatch.setenv(wg.SOURCE_CHECK_ENV, "enforce")
    assert _post().status_code == 401
    assert alarms == [(HOOK, ELSEWHERE)]


def test_at_log_nothing_is_refused_and_no_alarm_fires(monkeypatch, alarms):
    monkeypatch.delenv(wg.SOURCE_CHECK_ENV, raising=False)
    assert wg.source_mode() == "log"
    assert _post().status_code == 200
    assert alarms == []


def test_tradingview_raises_no_alarm_at_enforce(monkeypatch, alarms):
    monkeypatch.setenv(wg.SOURCE_CHECK_ENV, "enforce")
    assert _post(sender=TV).status_code == 200
    assert alarms == []


def test_the_alarm_is_scheduled_off_the_request(monkeypatch):
    got = []

    async def fake(path, addr, now=None):
        got.append((path, addr))

    monkeypatch.setattr(wg, "_alarm_refusal", fake)
    monkeypatch.setenv("WRITE_GUARD_RECORD", "on")

    async def go():
        wg._schedule_refusal_alarm(HOOK, {"x-forwarded-for": "%s, %s" % (ELSEWHERE, EDGE)})
        await asyncio.sleep(0)
    asyncio.run(go())
    assert got == [(HOOK, ELSEWHERE)]


# ── (h)1 once per path per UTC day ──────────────────────────────────────────

class _Redis:
    def __init__(self):
        self.keys = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    async def delete(self, key):
        self.keys.pop(key, None)


@pytest.fixture
def push(monkeypatch):
    """The real payload guard, a fake transport, a fake Redis."""
    import database.redis_client as rc
    sent, state = [], {"ok": True, "redis": _Redis()}

    async def fake_send(ticker, alert_type, action, *, title=None, priority="default"):
        body = ntfy_push.build_message(ticker, alert_type, action)     # raises on "money"
        ntfy_push._assert_no_money(title or "")
        if state["ok"]:
            sent.append(body)
            return {"sent": True, "status": 200, "body": body}
        return {"sent": False, "reason": "ntfy HTTP 500"}

    async def fake_client():
        if state["redis"] is None:
            raise RuntimeError("redis down")
        return state["redis"]

    monkeypatch.setattr(ntfy_push, "send", fake_send)
    monkeypatch.setattr(rc, "get_redis_client", fake_client)
    wg._refusal_pushed.clear()
    yield sent, state
    wg._refusal_pushed.clear()


NOW = datetime(2026, 11, 24, 15, 0)


def _alarm(path=HOOK, addr=ELSEWHERE, now=NOW):
    asyncio.run(wg._alarm_refusal(path, addr, now=now))


def test_the_first_refusal_pushes_the_path_and_the_address(push):
    sent, _state = push
    _alarm()
    assert len(sent) == 1
    assert HOOK in sent[0] and "203-0-113-9" in sent[0]


def test_an_address_with_a_two_digit_octet_is_not_refused_as_money(push):
    """52.89 reads as money to the cent. Unhandled, the alarm raised on TradingView-like hosts."""
    sent, _state = push
    with pytest.raises(ntfy_push.MoneyInPayload):
        ntfy_push.build_message("HOOK", "source refused", "%s from %s" % (HOOK, "52.89.214.238"))
    _alarm(addr="52.89.214.238")
    assert len(sent) == 1 and "52-89-214-238" in sent[0]


def test_a_second_refusal_the_same_day_is_silent(push):
    sent, _state = push
    _alarm()
    _alarm(addr="198.51.100.7", now=NOW + timedelta(hours=3))
    assert len(sent) == 1


def test_another_path_gets_its_own_push(push):
    sent, _state = push
    _alarm()
    _alarm(path="/webhook/breadth")
    assert len(sent) == 2


def test_the_next_utc_day_pushes_again(push):
    sent, _state = push
    _alarm()
    _alarm(now=NOW + timedelta(days=1))
    assert len(sent) == 2


def test_a_restart_the_same_day_stays_silent(push):
    sent, _state = push
    _alarm()
    wg._refusal_pushed.clear()         # what a restart does to this process's memory
    _alarm()
    assert len(sent) == 1


def test_redis_down_still_pushes_once_from_this_process(push):
    sent, state = push
    state["redis"] = None
    _alarm()
    _alarm()
    assert len(sent) == 1


def test_a_push_that_failed_is_tried_again(push):
    sent, state = push
    state["ok"] = False
    _alarm()
    assert sent == []
    state["ok"] = True
    _alarm()
    assert len(sent) == 1


def test_the_alarm_never_raises(monkeypatch, push):
    async def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(ntfy_push, "send", boom)
    _alarm()
    assert (NOW.strftime("%Y-%m-%d"), HOOK) not in wg._refusal_pushed


@pytest.mark.parametrize("raw, shown", [("not-an-ip", "unknown"), ("", "unknown"),
                                        ("2001:db8::1", "2001:db8::1")])
def test_only_a_real_address_is_put_in_the_push(raw, shown):
    assert wg._push_safe_address(raw) == shown


def test_the_switch_is_still_log_by_default(monkeypatch):
    monkeypatch.delenv(wg.SOURCE_CHECK_ENV, raising=False)
    assert wg.source_mode() == "log"


# ── (h)3 lab_registered is due the next morning ─────────────────────────────

FRI, MON, TUE = date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17)


def _et(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=ET)


@pytest.mark.parametrize("last, now, overdue", [
    (FRI, _et(2026, 11, 16, 17), False),       # Monday evening: not due yet
    (FRI, _et(2026, 11, 17, 8, 59), False),    # Tuesday, just before the due time
    (FRI, _et(2026, 11, 17, 9, 0), True),      # Tuesday's run is missing
    (MON, _et(2026, 11, 17, 9, 0), False),     # Tuesday's run graded Monday
    (date(2026, 11, 19), _et(2026, 11, 21, 8, 59), False),   # Sat before due: Thu is enough
    (date(2026, 11, 19), _et(2026, 11, 21, 9, 0), True),     # Sat: Friday's pass is due
    (date(2026, 11, 25), _et(2026, 11, 27, 10), False),      # Thanksgiving was no session
    (date(2026, 11, 25), _et(2026, 11, 28, 10), True),       # the half day was one
    (None, _et(2026, 11, 17, 9, 0), True),
])
def test_the_next_morning_due_time(last, now, overdue):
    assert sf._pass_overdue(last, now, next_morning=True) is overdue


def _status_at(monkeypatch, cls, last, age_s, now):
    real = _REAL_OVERDUE
    monkeypatch.setattr(sf, "_pass_overdue",
                        lambda l, n=None, next_morning=False: real(l, now, next_morning))
    return sf._class_status(cls, age_s, 0, last)


_REAL_OVERDUE = sf._pass_overdue


def test_monday_evening_is_no_longer_a_flatline(monkeypatch):
    age = 58 * 3600   # Saturday 07:00 -> Monday 17:00
    assert _status_at(monkeypatch, "lab_registered", FRI, age, _et(2026, 11, 16, 17)) == "ok"


def test_the_other_session_classes_keep_their_17_00_rule(monkeypatch):
    age = 58 * 3600
    assert _status_at(monkeypatch, "triton_grader", FRI, age, _et(2026, 11, 16, 17)) == "flatline"


def _replay(monkeypatch, skip=frozenset(), start=date(2026, 10, 19), end=date(2026, 11, 21)):
    """15-minute grid; the job's real schedule (tue-sat 07:00 ET, grading the previous session)."""
    runs = []
    d = start - timedelta(days=4)
    while d <= end:
        if d.weekday() in (1, 2, 3, 4, 5) and d not in skip:
            s = d - timedelta(days=1)
            while not is_trading_day(s):
                s -= timedelta(days=1)
            runs.append((datetime(d.year, d.month, d.day, 7, 0, tzinfo=ET), s))
        d += timedelta(days=1)
    red = []
    t = datetime(start.year, start.month, start.day, 0, 0, tzinfo=ET)
    stop = datetime(end.year, end.month, end.day, 23, 45, tzinfo=ET)
    while t <= stop:
        done = [r for r in runs if r[0] <= t]
        at, sess = done[-1]
        if _status_at(monkeypatch, "lab_registered", sess, (t - at).total_seconds(), t) != "ok":
            red.append(t)
        t += timedelta(minutes=15)
    return red


def test_a_month_of_the_real_schedule_never_reads_red(monkeypatch):
    assert _replay(monkeypatch) == []


def test_the_old_rule_read_red_on_those_same_mondays(monkeypatch):
    """Positive control: the replay can see the fault this repair removes."""
    real = _REAL_OVERDUE
    monkeypatch.setattr(sf, "NEXT_MORNING_CLASSES", frozenset())
    runs_red = []
    d = date(2026, 11, 16)
    at = datetime(2026, 11, 14, 7, 0, tzinfo=ET)
    monkeypatch.setattr(sf, "_pass_overdue",
                        lambda l, n=None, next_morning=False:
                        real(l, datetime(d.year, d.month, d.day, 17, 0, tzinfo=ET), next_morning))
    age = (datetime(d.year, d.month, d.day, 17, 0, tzinfo=ET) - at).total_seconds()
    runs_red.append(sf._class_status("lab_registered", age, 0, FRI))
    assert runs_red == ["flatline"]


def test_a_run_that_really_is_missing_still_goes_red(monkeypatch):
    red = _replay(monkeypatch, skip={date(2026, 11, 17)},
                  start=date(2026, 11, 16), end=date(2026, 11, 18))
    assert red, "a missed Tuesday pass must read red"
    assert red[0] == datetime(2026, 11, 17, 9, 0, tzinfo=ET)
