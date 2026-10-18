"""R-IV.1220(a): the level break becomes an EVENT, and the delivery limits that follow.

WHY THIS FILE EXISTS, in one paragraph, because the reason is the whole point. QUERY measured
B2's level-break detector in both forms over the same sessions (census report sha12
8514413e1c48). As a STATE test -- "is the newest close beyond the prior-day level" -- it
produced 270 raw fires a day and the 20/day push cap bound on 59 of 59 days. As an EVENT it
produced 22 a day. The state test was not detecting 270 breaks; it was detecting ONE break and
re-reporting it on every subsequent bar of the session. A cap that binds every single day is a
cap that decides which alerts Nick sees by arrival order, which is no decision at all.

So the tests below are mostly about things NOT firing, and every one of them is paired with a
positive control (Convention #30): a test that proves silence has to prove the same input can
speak, or it is only proving the function is broken.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from integrations import ntfy_push
from models import position_watch as pw

H, L = 101.0, 99.0                                   # the prior-day range used throughout
T = _dt.datetime(2026, 10, 19, 14, 0)
TODAY = _dt.date(2026, 10, 19)
YESTERDAY = _dt.date(2026, 10, 16)


# ── 1. the level break is an EVENT ────────────────────────────────────────

def test_A_SECOND_BAR_BEYOND_THE_LEVEL_DOES_NOT_FIRE_AGAIN():
    """THE REGRESSION THIS RULING IS ABOUT, and it holds with NO state passed in.

    Both bars are above the prior-day high. The state test said "break" on both -- that is
    where 270 fires a day came from. The event test says nothing on the second, because the
    bar before it was not inside, and it needs no fired-set to get that right.
    """
    assert pw.level_break([100.2, 101.5, 101.9], H, L) is None
    assert pw.level_break([100.2, 101.5, 101.9, 102.4, 102.1], H, L) is None
    # The series must START INSIDE to test this. Bare [101.5, 101.9] is now a gap-open session
    # whose second bar CONFIRMS the gap (R-IV.1226(b)1), so it fires by design -- see
    # test_A_GAP_THAT_HOLDS_PUSHES_ONCE_AT_BAR_TWO.


def test_THE_TRANSITION_INTO_THE_BREAK_DOES_FIRE():
    """The positive control for the test above: same shape, one bar inside first."""
    got = pw.level_break([100.2, 101.5], H, L)
    assert got is not None and got["event"] == "LEVEL_BREAK"
    assert got["side"] == "above" and got["level"] == H and got["close"] == 101.5
    low = pw.level_break([100.2, 98.4], H, L)
    assert low["side"] == "below" and low["level"] == L


def test_EACH_DIRECTION_FIRES_AT_MOST_ONCE_PER_SESSION():
    """(a)1's second sentence. Price can leave the range, come back in, and leave again -- the
    second departure on the same side is the same break, so it is not re-announced.

    The SIDE is the key and not the ticker, because a session that breaks out above in the
    morning and loses the prior-day low in the afternoon has done two different things.
    """
    series = [100.2, 101.5]
    assert pw.level_break(series, H, L) is not None                      # control
    assert pw.level_break(series, H, L, fired_sides=["above"]) is None
    assert pw.level_break(series, H, L, fired_sides=["below"]) is not None
    assert pw.level_break([100.2, 98.4], H, L, fired_sides=("ABOVE",)) is not None
    assert pw.level_break([100.2, 98.4], H, L, fired_sides=("below",)) is None


def test_gap_open_beyond_IS_the_break_event():
    """R-IV.1224(c), REPLACING test_gap_open_beyond_never_fires.

    Under R-IV.1220(a)1 alone this session fired nothing all day: it opened beyond the
    prior-day high and never closed back inside, so no bar ever had an inside predecessor. The
    gap-and-go is the case most worth knowing about, so the ruling makes the session's FIRST
    closed bar the break event, with the prior session's final close counting as the preceding
    inside bar.

    The deeming is a theorem rather than an assumption: a session's close lies within that
    session's own high and low, and those are exactly `prior_high` / `prior_low`.

    AMENDED BY R-IV.1226(b): the first bar is still the event and still reaches the PANEL, but
    it is no longer pushable on its own -- the push waits for a second bar beyond. What this
    test now pins is the half the later ruling did NOT change: bar 1 produces a real event
    rather than silence. The push side is pinned by
    test_A_GAP_THAT_HOLDS_PUSHES_ONCE_AT_BAR_TWO.
    """
    gap = [101.4, 101.8, 102.2, 102.0]
    first = pw.level_break(gap[:1], H, L)
    assert first is not None and first["event"] == "LEVEL_BREAK"
    assert first["side"] == "above" and first["close"] == 101.4
    # Once per session per direction, held by the fired-set on the CONFIRMED event.
    assert pw.level_break(gap[:1], H, L, fired_sides=["above"]) is None
    # A gap DOWN is the same event on the other side.
    assert pw.level_break([98.2], H, L)["side"] == "below"


def test_A_FIRST_BAR_INSIDE_THE_RANGE_IS_NOT_A_BREAK():
    """The control for the test above: the first-bar path is not "fire on bar one", it is
    "bar one is judged against the prior close like any other bar"."""
    assert pw.level_break([100.3], H, L) is None
    assert pw.level_break([101.0], H, L) is None, "a close AT the high has not gone beyond it"
    assert pw.level_break([99.0], H, L) is None


def test_INSIDE_MEANS_INSIDE_BOTH_BOUNDS():
    """A bar BELOW the prior-day low is not "inside", so it cannot be the inside bar for a
    break above. Reading inside as "not above the high" would make one bar that crossed the
    whole range count as a breakout from within it."""
    assert pw.level_break([98.0, 101.5], H, L) is None
    assert pw.level_break([100.0, 101.5], H, L) is not None               # control
    # With only one bound known, the other cannot disqualify a bar.
    assert pw.level_break([98.0, 101.5], H, None) is not None


def test_NO_BARS_IS_NOT_AN_EVENT():
    """Nothing in, nothing out.

    This test used to assert that ONE bar could not be an event either -- "an event is a change
    between two closed bars". R-IV.1224(c) overrode that reasoning: the session's first closed
    bar has a predecessor, it just isn't in the list. An empty list still has nothing to judge.
    """
    assert pw.level_break([], H, L) is None


# ── 2. the failed breakout fires once per break ───────────────────────────

def test_A_FAILED_BREAKOUT_FIRES_ONCE_PER_BREAK():
    """(a)2. The event is the RETURN, so a second bar inside after the same break is not a
    second failure. This holds BY CONSTRUCTION -- there is no fired-set to forget to pass."""
    broke_and_returned = [100.0, 101.8, 100.4]
    first = pw.failed_breakout(broke_and_returned, H, L)
    assert first["event"] == "FAILED_BREAKOUT" and first["bars_ago"] == 1   # control
    assert pw.failed_breakout(broke_and_returned + [100.3], H, L) is None
    assert pw.failed_breakout(broke_and_returned + [100.3, 100.6], H, L) is None


def test_A_SECOND_BREAK_AND_RETURN_IS_ITS_OWN_FAILURE():
    """Suppressing the re-report must not suppress a genuinely new break. Break, return, break
    again, return again -- that second return is a second failed breakout."""
    got = pw.failed_breakout([100.0, 101.8, 100.4, 100.3, 101.9, 100.2], H, L)
    assert got is not None and got["bars_ago"] == 1 and got["side"] == "above"


def test_THE_RUN_BEYOND_MUST_BE_WITHIN_FOUR_BARS():
    assert pw.failed_breakout([100.0] + [101.8] * 4 + [100.4], H, L)["bars_ago"] == 4
    assert pw.failed_breakout([100.0] + [101.8] * 5 + [100.4], H, L) is None


def test_THE_TWO_LEVEL_EVENTS_ARE_NAMED_AS_A_FAMILY():
    """(a)3 caps them together, so the family is a named constant rather than two string
    literals repeated at each gate. The exit levels and exhaustion are NOT in it."""
    assert set(pw.LEVEL_TYPE_EVENTS) == {"LEVEL_BREAK", "FAILED_BREAKOUT"}
    for e in ("EXHAUSTION", "STOP_LEVEL", "TARGET_LEVEL"):
        assert e not in pw.LEVEL_TYPE_EVENTS


# ── 3. (a)5: B2 ships with the phone OFF ──────────────────────────────────

def _push(**kw):
    base = dict(relation="AGAINST", event="EXHAUSTION", ticker="QQQ", recent=[], now=T,
                pushed_today=0)
    base.update(kw)
    return pw.may_push(**base)


def test_PUSHES_ARE_OFF_BY_DEFAULT():
    """(a)5: the panel is live, the wire is dark. The DEFAULT is the shipped behaviour, so this
    asserts what happens when the caller passes nothing -- a flag that is only correct when
    remembered is not a ship-with-pushes-off."""
    assert pw.PUSHES_ENABLED is False
    ok, why = _push()
    assert ok is False and "OFF" in why and "panel is live" in why
    assert _push(pushes_enabled=True)[0] is True              # control


def test_THE_OFF_SWITCH_IS_THE_FIRST_GATE():
    """It consumes nothing on the way past. With the wire dark, a would-be push must not spend
    a cap slot, leave a cooldown row or record "already pushed this session" -- all three would
    still be there on the day the wire is switched on."""
    ok, why = _push(pushed_today=20, event="LEVEL_BREAK",
                    recent=[{"ticker": "QQQ", "event": "LEVEL_BREAK", "pushed_at": T}])
    assert ok is False
    assert "OFF" in why, "the OFF gate must be reached before the cap and the session limit"


# ── 4. (a)3: one level-type push per ticker per session ───────────────────

def test_ONE_LEVEL_TYPE_PUSH_PER_TICKER_PER_SESSION():
    """A break and then its failure are two readings of the same prior-day level, and that pair
    is the commonest sequence there is. (a)3 gives the pair one slot."""
    sent = [{"ticker": "QQQ", "event": "LEVEL_BREAK", "pushed_at": T - _dt.timedelta(hours=3)}]
    ok, why = pw.may_push(relation="AGAINST", event="FAILED_BREAKOUT", ticker="QQQ",
                          recent=sent, now=T, pushed_today=1, pushes_enabled=True)
    assert ok is False and "level-type push this session" in why
    # The same ticker's EXHAUSTION is untouched by (a)3, and so is another ticker's break.
    assert pw.may_push(relation="AGAINST", event="EXHAUSTION", ticker="QQQ", recent=sent,
                       now=T, pushed_today=1, pushes_enabled=True)[0] is True
    assert pw.may_push(relation="AGAINST", event="LEVEL_BREAK", ticker="IWM", recent=sent,
                       now=T, pushed_today=1, pushes_enabled=True)[0] is True


def test_THE_SESSION_LIMIT_IS_PER_SESSION_NOT_FOREVER():
    """With a session date, yesterday's level push does not silence today's. Without one, the
    caller is declaring `recent` already session-scoped -- and the two readings have to differ,
    or the parameter does nothing."""
    old = [{"ticker": "QQQ", "event": "LEVEL_BREAK",
            "pushed_at": _dt.datetime(2026, 10, 16, 15, 0), "session_date": YESTERDAY}]
    assert pw.may_push(relation="AGAINST", event="LEVEL_BREAK", ticker="QQQ", recent=old,
                       now=T, pushed_today=0, session_date=TODAY,
                       pushes_enabled=True)[0] is True
    assert pw.may_push(relation="AGAINST", event="LEVEL_BREAK", ticker="QQQ", recent=old,
                       now=T, pushed_today=0, session_date=YESTERDAY,
                       pushes_enabled=True)[0] is False


def test_THE_SESSION_LIMIT_COMES_BEFORE_THE_CAP():
    """Same reasoning as the relation gate: a second level alert that was never going to be
    pushed must not consume the slot that silences one that would have been."""
    sent = [{"ticker": "QQQ", "event": "LEVEL_BREAK", "pushed_at": T - _dt.timedelta(hours=3)}]
    ok, why = pw.may_push(relation="AGAINST", event="LEVEL_BREAK", ticker="QQQ", recent=sent,
                          now=T, pushed_today=20, pushes_enabled=True)
    assert ok is False
    assert "level-type" in why and "cap" not in why


# ── 5. (a)4: the cap announces itself ─────────────────────────────────────

def test_THE_CAP_NOTICE_FIRES_ONLY_ONCE_THE_CAP_HAS_ACTUALLY_EATEN_SOMETHING():
    assert pw.cap_notice(pushed_today=20, suppressed_by_cap=True, notice_sent=False,
                         pushes_enabled=True)[0] is True
    # Not at the cap yet.
    assert pw.cap_notice(pushed_today=19, suppressed_by_cap=True, notice_sent=False,
                         pushes_enabled=True)[0] is False
    # At the cap, but nothing has been turned away by it, so there is no loss to report.
    assert pw.cap_notice(pushed_today=20, suppressed_by_cap=False, notice_sent=False,
                         pushes_enabled=True)[0] is False
    # Once per session: a notice that repeats is the flood it reports.
    assert pw.cap_notice(pushed_today=25, suppressed_by_cap=True, notice_sent=True,
                         pushes_enabled=True)[0] is False
    # And the OFF switch covers this wire too.
    assert pw.cap_notice(pushed_today=20, suppressed_by_cap=True, notice_sent=False)[0] is False


def test_THE_CAP_NOTICE_TEXT_IS_THE_RULED_WORDING_AND_CLEARS_THE_MONEY_GUARD():
    """(a)4 gives the words. They are checked against the SAME guard the relay enforces,
    because a notice that cannot be sent is a cap with no announcement at all -- which is the
    silent drop the ruling exists to prevent.

    The control proves the guard is live in this test, not merely imported.
    """
    assert pw.CAP_NOTICE_TEXT == "Alert cap reached: see Position Watch panel"
    ntfy_push._assert_no_money(pw.CAP_NOTICE_TEXT)
    with pytest.raises(ntfy_push.MoneyInPayload):
        ntfy_push._assert_no_money("Alert cap reached at 31.20: see Position Watch panel")


def test_NOTHING_IS_DROPPED_FROM_THE_PANEL():
    """(a)4's other half. Every refusal above is a decision about the PHONE: `may_push` and
    `cap_notice` are the only two functions that gate delivery, and neither is reachable from
    `panel_text`, which has no suppression argument at all.

    Checked structurally rather than by assertion-on-prose: a panel row is assembled from the
    event and the words, and there is no path by which a push limit can reach it.
    """
    import inspect
    sig = inspect.signature(pw.panel_text).parameters
    for banned in ("pushed_today", "pushes_enabled", "relation", "suppressed"):
        assert banned not in sig
    row = pw.panel_text(ticker="QQQ", event="LEVEL_BREAK", close=101.5,
                        basis="closed 101.5000 above the prior-day high 101.0000",
                        action=pw.ACTION_LOGGED, shown_regime="RISK-ON")
    assert "101.50" in row["title"] and "alert, not a signal" in row["tag"]


# ── 6. R-IV.1224(e): the column Position Watch must not read ──────────────

def test_POSITION_WATCH_NEVER_READS_orientation_at_entry():
    """R-IV.1224(e). QUERY found `orientation_at_entry` NULL on EVERY open row, so a detector
    reading it would answer "no orientation" for the whole book and go quiet. Position Watch
    uses the sign of net delta instead, which is computed from the structure and the leverage
    map and cannot be null for a row it watches.

    Scanned on the PARSED source with comments and docstrings removed, not on the raw text --
    the comment explaining why the column is not read contains the column's name, and a plain
    substring scan would fail on its own prose. That trap has been hit eight times in this
    repo; `ast.unparse` drops comments but KEEPS docstrings, so they are stripped by identity.
    """
    import ast
    import pathlib

    src = pathlib.Path(pw.__file__).read_text(encoding="utf-8-sig")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.remove(first)
    code = ast.unparse(tree)
    for col in ("orientation_at_entry", "position_orientation"):
        assert col not in code, "%s is read in executable code, not just explained" % col
    # The positive control: the scan CAN see a name that really is in the executable source,
    # so a pass above is not the scan quietly matching nothing.
    assert "LEVERAGE_MAP" in code


# ── 7. R-IV.1226(b): a gap has to confirm before it can reach the phone ───

def _hold():
    """A gap that HOLDS: opens above, second bar closes above too, then stays out."""
    return [101.4, 101.8, 102.2, 102.0]


def _fade():
    """A gap that FADES: opens above, second bar closes back inside."""
    return [101.4, 100.6, 100.4]


def test_A_GAP_THAT_HOLDS_PUSHES_ONCE_AT_BAR_TWO():
    """(b)1: pushable only if the first TWO closed bars both close beyond, and the event time
    is the SECOND bar's close. QUERY's recount is why: gap-open was supplying 59% of all pushes
    (175 of 295), with MSFT firing on 29 of 59 sessions."""
    s = _hold()
    bar1 = pw.level_break(s[:1], H, L)
    assert bar1["gap_open"] is True and bar1["confirmed"] is False
    assert bar1["pushable"] is False, "bar 1 must not reach the phone"
    assert "unconfirmed" in bar1["basis"]

    bar2 = pw.level_break(s[:2], H, L)
    assert bar2["confirmed"] is True and bar2["pushable"] is True
    assert bar2["close"] == s[1], "the event time is the SECOND bar's close"
    assert "confirming the gap" in bar2["basis"]

    # ONCE. The caller records the side on the CONFIRMED event, and the rest is silent.
    for n in range(3, len(s) + 1):
        assert pw.level_break(s[:n], H, L) is None, "bar %d re-reported the gap" % n
    assert pw.level_break(s[:2], H, L, fired_sides=["above"]) is None


def test_AN_UNCONFIRMED_GAP_CANNOT_PUSH_EVEN_WHEN_EVERYTHING_ELSE_PASSES():
    """The flag has to be enforced, not merely reported. Relation AGAINST, wire on, cap empty,
    no cooldown -- and it still does not push, because bar 2 has not closed."""
    ev = pw.level_break(_hold()[:1], H, L)
    ok, why = pw.may_push_event(ev, relation="AGAINST", ticker="QQQ", recent=[], now=T,
                                pushed_today=0, pushes_enabled=True)
    assert ok is False and "not pushable yet" in why
    # The control: the same call on the CONFIRMED bar-2 event does push.
    ev2 = pw.level_break(_hold()[:2], H, L)
    assert pw.may_push_event(ev2, relation="AGAINST", ticker="QQQ", recent=[], now=T,
                             pushed_today=0, pushes_enabled=True)[0] is True


def test_THE_UNCONFIRMED_GAP_DOES_NOT_SPEND_THE_SESSIONS_ONE_SLOT():
    """Gate order, and it decides whether a confirmed gap can ever push. If the unconfirmed bar
    consumed the one level-type slot, bar 2 would arrive to find it already spent."""
    ev = pw.level_break(_hold()[:1], H, L)
    ok, why = pw.may_push_event(ev, relation="AGAINST", ticker="QQQ", recent=[], now=T,
                                pushed_today=0, pushes_enabled=True)
    assert ok is False
    assert "not pushable yet" in why and "level-type" not in why


def test_A_GAP_THAT_FADES_PRODUCES_ONLY_THE_FAILED_BREAKOUT_PATH():
    """(b)2: no break push, and the failure is the ordinary failed-breakout event, which
    pushes only if AGAINST."""
    s = _fade()
    assert pw.level_break(s[:1], H, L)["pushable"] is False
    # Bar 2 closed back inside, so there is no break event at all on it.
    assert pw.level_break(s[:2], H, L) is None
    # It is a failed breakout, by the ordinary transition rule.
    fb = pw.failed_breakout(s[:2], H, L)
    assert fb["event"] == "FAILED_BREAKOUT" and fb["side"] == "above" and fb["bars_ago"] == 1
    # AGAINST pushes it; WITH does not.
    assert pw.may_push_event(fb, relation="AGAINST", ticker="QQQ", recent=[], now=T,
                             pushed_today=0, pushes_enabled=True)[0] is True
    assert pw.may_push_event(fb, relation="WITH", ticker="QQQ", recent=[], now=T,
                             pushed_today=0, pushes_enabled=True)[0] is False
    # And the rest of the session stays silent on both paths.
    assert pw.level_break(s, H, L) is None
    assert pw.failed_breakout(s, H, L) is None


def test_THE_PANEL_STILL_LOGS_THE_FIRST_BAR_GAP():
    """(b)3. The unconfirmed break is a real event with a real panel row -- it is only the
    PHONE that waits. A detector that returned None on bar 1 would leave the panel blank on
    exactly the session the panel is for."""
    ev = pw.level_break(_hold()[:1], H, L)
    row = pw.panel_text(ticker="QQQ", event=ev["event"], close=ev["close"],
                        basis=ev["basis"], action=pw.ACTION_LOGGED, shown_regime="RISK-OFF")
    assert "QQQ" in row["title"] and "101.40" in row["title"]
    assert "unconfirmed" in row["body"]


def test_CROSSING_THE_WHOLE_RANGE_IN_TWO_BARS_IS_NOT_A_CONFIRMATION():
    """Fail closed rather than pick a side: bar 1 below the low, bar 2 above the high confirms
    neither break and is not a transition from inside."""
    assert pw.level_break([98.0], H, L)["side"] == "below"
    assert pw.level_break([98.0, 101.5], H, L) is None
