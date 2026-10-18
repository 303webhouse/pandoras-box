"""B2 — Position Watch: the pure decisions. R-IV.1209(f), source ruled by R-IV.1215(b).

THE THREE THINGS HERE THAT CAN DO REAL HARM, and they get almost all of this file:

  1. AGAINST or WITH, because it decides whether Nick's phone buzzes while the market is open.
     It is the alert's direction against the SIGN OF THE POSITION'S NET DELTA ON THE UNDERLYING
     (f)3 -- not against the ticker he holds. A long SQQQ position is SHORT QQQ, so a bullish
     QQQ alert is AGAINST it. Reading the holding's direction instead gets that backwards, and
     backwards here means silence when the phone should ring.

  2. THE WORDING, which is run through the EXISTING no-orders lint -- the same
     `regime_playbook.order_findings` that guards the playbooks and the A3 fixture.

  3. THE CLOSED-BAR RULE. A bar is finished only when a later bar exists or the session has
     closed plus five minutes. An event off a forming bar is an event off a number that is
     still moving, and this repo's own landmine is Yahoo's /1d dropping a session /1h still has.

AND ONE RULE THAT IS NOT NEGOTIABLE: the push carries ticker / alert type / action and NO PRICE
LEVEL. R-IV.901(b)1 limits the relay, and `_assert_no_money` enforces it by refusing any figure
written to the cent. Board 6's mock shows a price in the push; the mock is layout only and the
money rule governs the wire.
"""
from __future__ import annotations

import datetime as _dt

import pytest

import services.regime_playbook as rp
from models import position_watch as pw


def _pos(ticker, structure, **kw):
    d = {"ticker": ticker, "structure": structure}
    d.update(kw)
    return d


# ── 1. AGAINST / WITH, via the delta sign ─────────────────────────────────

def test_A_LONG_INVERSE_ETF_IS_SHORT_ITS_UNDERLYING():
    """THE CRUX. `stock` is +1 on the instrument; SQQQ is inverted; so the net on QQQ is -1."""
    assert pw.structure_sign("stock") == 1
    assert pw.underlying_of("SQQQ") == "QQQ"
    assert pw.delta_sign(_pos("SQQQ", "stock")) == -1


def test_A_BULLISH_QQQ_ALERT_IS_AGAINST_A_LONG_SQQQ():
    """The whole reason the delta sign exists. Reading SQQQ's own direction would call this
    WITH and the phone would stay silent."""
    rel, why = pw.classify_relation("LONG", _pos("SQQQ", "stock"))
    assert rel == "AGAINST"
    assert "QQQ" in why


def test_A_BULLISH_QQQ_ALERT_IS_ALSO_AGAINST_A_QQQ_PUT_SPREAD():
    rel, _ = pw.classify_relation("LONG", _pos("QQQ", "put_debit_spread"))
    assert rel == "AGAINST"


def test_A_NON_INVERTED_LEVERAGED_ETF_KEEPS_ITS_SIGN():
    """GUSH is 2x LONG energy, so a bullish XOP alert is WITH it. The map carries `inverted`
    per ticker precisely so 'leveraged' is not read as 'inverse'."""
    assert pw.underlying_of("GUSH") == "XOP"
    assert pw.delta_sign(_pos("GUSH", "stock")) == 1
    assert pw.classify_relation("LONG", _pos("GUSH", "stock"))[0] == "WITH"
    assert pw.classify_relation("SHORT", _pos("GUSH", "stock"))[0] == "AGAINST"


def test_A_COMPOUND_STRUCTURE_resolves_when_its_parts_AGREE():
    assert pw.delta_sign(_pos("NVDA", "put_debit_spread+long_put")) == -1


def test_AN_UNKNOWN_STRUCTURE_IS_NONE_NOT_NEUTRAL():
    """None means "not knowable". Zero would mean "neither way", which makes the relation WITH
    and the alert silent -- a guess dressed as a measurement."""
    assert pw.structure_sign("iron_condor") is None
    assert pw.delta_sign(_pos("XYZ", "iron_condor")) is None
    rel, why = pw.classify_relation("LONG", _pos("XYZ", "iron_condor"))
    assert rel is None
    assert "not knowable" in why


def test_A_MIXED_COMPOUND_IS_NOT_GUESSED():
    """A spread whose legs point opposite ways has no net sign readable from the LABEL, and the
    label is all this function has."""
    assert pw.delta_sign(_pos("X", "long_call+long_put")) is None


def test_AN_UNREADABLE_ALERT_DIRECTION_IS_NONE():
    for d in (None, "", "sideways", "???"):
        assert pw.alert_sign(d) is None
        assert pw.classify_relation(d, _pos("QQQ", "put_debit_spread"))[0] is None


def test_UNKNOWN_IS_NOT_WITH_AND_IS_NOT_PUSHED():
    """A push fires only on AGAINST (f)4. Collapsing "could not tell" into WITH silences an
    alert that might have mattered; into AGAINST pushes on a guess. It is its own answer."""
    ok, why = pw.may_push(relation=None, event="LEVEL_BREAK", ticker="X", recent=[],
                          now=_dt.datetime(2026, 10, 19, 14, 0), pushed_today=0)
    assert ok is False
    assert "not AGAINST" in why


# ── 2. Set B, read from the live book ─────────────────────────────────────

LIVE_BOOK = [
    _pos("QQQ", "put_debit_spread"),
    _pos("IWM", "put_debit_spread"),
    _pos("VIX", "call_debit_spread"),
    _pos("SQQQ", "stock", classification="TACTICAL"),
    _pos("GUSH", "stock", classification="TACTICAL"),
    _pos("VTI", "stock", classification="STRATEGIC"),
    _pos("SHV", "stock", classification="STRATEGIC"),
    _pos("XLU", "stock", classification="STRATEGIC"),
]


def test_SET_B_IS_THE_TRADED_SLEEVES_THROUGH_THEIR_UNDERLYINGS():
    s = pw.set_b(LIVE_BOOK)
    assert s["watch"] == ["IWM", "QQQ", "XOP"]
    # SQQQ is watched THROUGH QQQ, and the panel can say so.
    assert s["via"]["QQQ"] == ["QQQ", "SQQQ"]
    assert s["via"]["XOP"] == ["GUSH"]


def test_EVERY_EXCLUSION_CARRIES_THE_RULED_REASON():
    """R-IV.1215(b)3 gives the three wordings. A ticker missing from a watch list with no reason
    reads as an oversight."""
    s = pw.set_b(LIVE_BOOK)
    nw = s["not_watched"]
    assert nw["VIX"] == "options on VIX futures, no usable underlying series"
    assert nw["SHV"] == "T-bill fund"
    assert nw["VTI"] == "long-term sleeve, not watched"
    assert nw["XLU"] == "long-term sleeve, not watched"


def test_SET_B_IS_NEVER_HARDCODED():
    """R-IV.1215(b)2: read from the live book each session. A frozen list would watch a closed
    position and miss a new one -- and the second failure is silent."""
    assert pw.set_b([])["watch"] == []
    assert pw.set_b([_pos("AAPL", "long_put")])["watch"] == ["AAPL"]
    import inspect
    src = inspect.getsource(pw.set_b)
    for hard in ("'QQQ'", '"QQQ"', "'IWM'", '"IWM"'):
        assert hard not in src, hard


def test_a_ticker_held_BOTH_tactically_and_in_core_IS_watched():
    """The tactical row is the one that can need a stop reviewed, so the exclusion must not win
    just because a core row shares the ticker."""
    book = [_pos("XLE", "stock", classification="STRATEGIC"),
            _pos("XLE", "stock", classification="TACTICAL")]
    s = pw.set_b(book)
    assert s["watch"] == ["XLE"]
    assert "XLE" not in s["not_watched"]


# ── 3. the closed-bar rule ────────────────────────────────────────────────

T = _dt.datetime(2026, 10, 19, 14, 0)


def test_A_BAR_IS_CLOSED_WHEN_A_LATER_BAR_EXISTS():
    ok, why = pw.bar_is_closed(T, newest_bar_start=T + _dt.timedelta(minutes=15),
                               session_closed=False, now=T + _dt.timedelta(minutes=20))
    assert ok is True
    assert "a later bar exists" in why


def test_THE_NEWEST_BAR_IS_NEVER_TREATED_AS_COMPLETE():
    """R-IV.1215(b)4, and the reason is this repo's own landmine: a vendor can be missing a bar
    it will have later, so "the clock says the window elapsed" is an assumption about a feed."""
    ok, why = pw.bar_is_closed(T, newest_bar_start=T, session_closed=False,
                               now=T + _dt.timedelta(hours=3))
    assert ok is False
    assert "still forming" in why


def test_THE_LAST_BAR_OF_THE_SESSION_CLOSES_AFTER_THE_GRACE():
    assert pw.CLOSE_GRACE_MIN == 5
    early = pw.bar_is_closed(T, newest_bar_start=T, session_closed=True,
                             now=T + _dt.timedelta(minutes=15))
    assert early[0] is False and "grace" in early[1]
    late = pw.bar_is_closed(T, newest_bar_start=T, session_closed=True,
                            now=T + _dt.timedelta(minutes=21))
    assert late[0] is True


# ── 4. the detectors ──────────────────────────────────────────────────────

def test_a_LEVEL_BREAK_needs_a_CLOSE_beyond_the_prior_day_range():
    assert pw.level_break([100.0, 101.5], prior_high=101.0, prior_low=99.0)["side"] == "above"
    assert pw.level_break([100.0, 98.5], prior_high=101.0, prior_low=99.0)["side"] == "below"
    assert pw.level_break([100.0, 100.5], prior_high=101.0, prior_low=99.0) is None


def test_an_ABSENT_prior_level_is_not_an_intact_one():
    """None in, None out -- not a cheerful "no break". A missing prior-day high and an unbroken
    one are different facts."""
    assert pw.level_break([100.0], prior_high=None, prior_low=None) is None
    assert pw.level_break([], prior_high=1.0, prior_low=0.5) is None


def test_a_FAILED_BREAKOUT_is_a_break_THEN_a_close_back_inside():
    """(f)1, within four bars."""
    got = pw.failed_breakout([100.0, 101.8, 100.4], prior_high=101.0, prior_low=99.0)
    assert got["event"] == "FAILED_BREAKOUT"
    assert got["side"] == "above" and got["bars_ago"] == 1


def test_a_failed_breakout_EXPIRES_after_four_bars():
    closes = [101.8] + [100.4] * 5          # the break is 5 bars back
    assert pw.failed_breakout(closes, prior_high=101.0, prior_low=99.0) is None


def test_a_close_still_OUTSIDE_is_not_a_failed_breakout():
    assert pw.failed_breakout([100.0, 101.8, 101.9], prior_high=101.0, prior_low=99.0) is None


def test_the_position_STOP_fires_on_the_right_side_for_its_delta():
    """A short-delta position's stop is ABOVE it. Using the long rule for both would fire on
    the wrong side -- which reads as a stop hit when price moved in Nick's favour."""
    short = _pos("QQQ", "put_debit_spread", stop_loss=705.0)
    assert pw.stop_or_target(706.0, short)["event"] == "STOP_LEVEL"
    assert pw.stop_or_target(700.0, short) is None
    long_ = _pos("GUSH", "stock", stop_loss=30.0)
    assert pw.stop_or_target(29.0, long_)["event"] == "STOP_LEVEL"
    assert pw.stop_or_target(31.0, long_) is None


def test_a_NULL_stop_is_not_a_stop_at_zero():
    assert pw.stop_or_target(1.0, _pos("QQQ", "put_debit_spread")) is None


# ── 5. the wording (f)5 ───────────────────────────────────────────────────

def test_THE_VERB_MATCHES_THE_EVENT():
    """(f)5 pairs them. Giving the wrong one of the two is advice about the wrong thing --
    subtler than an order and just as wrong."""
    assert pw.action_for("LEVEL_BREAK", "AGAINST") == pw.ACTION_REVIEW_STOP
    assert pw.action_for("STOP_LEVEL", "AGAINST") == pw.ACTION_REVIEW_STOP
    assert pw.action_for("FAILED_BREAKOUT", "AGAINST") == pw.ACTION_TIGHTEN
    assert pw.action_for("EXHAUSTION", "AGAINST") == pw.ACTION_TIGHTEN


def test_ANYTHING_NOT_AGAINST_IS_LOGGED_NOT_ADVISED():
    for rel in ("WITH", None, "UNKNOWN"):
        assert pw.action_for("LEVEL_BREAK", rel) == pw.ACTION_LOGGED


def test_AN_UNPAIRED_EVENT_GETS_NO_ACTION_RATHER_THAN_A_PLAUSIBLE_ONE():
    assert pw.action_for("SOMETHING_NEW", "AGAINST") == pw.ACTION_LOGGED


def test_THE_NO_ORDERS_LINT_PASSES_OVER_EVERY_STRING_THAT_REACHES_NICK():
    """The EXISTING lint, not a second one: a second implementation of "is this an order?"
    would eventually disagree, and the surface with the looser one ships the instruction."""
    texts = []
    for ev, rel in (("LEVEL_BREAK", "AGAINST"), ("FAILED_BREAKOUT", "AGAINST"),
                    ("EXHAUSTION", "AGAINST"), ("STOP_LEVEL", "AGAINST"),
                    ("TARGET_LEVEL", "AGAINST"), ("LEVEL_BREAK", "WITH")):
        act = pw.action_for(ev, rel)
        p = pw.panel_text(ticker="QQQ", event=ev, close=702.1, basis="closed beyond the level",
                          action=act, shown_regime="NARROW UPTREND")
        texts += [p["title"], p["body"], p["tag"]]
        f = pw.push_fields(ticker="QQQ", event=ev, action=act, shown_regime="NARROW UPTREND")
        texts += [f["ticker"], f["alert_type"], f["action"]]
    findings = []
    for t in texts:
        findings.extend(rp.lint_text(t, "position_watch wording"))
    assert findings == [], findings


def test_POSITIVE_CONTROL_the_lint_still_catches_an_order():
    assert rp.lint_text("Sell the QQQ spread now.", "x")
    assert rp.lint_text("Reverse the position.", "x")


def test_EVERY_ALERT_CARRIES_ITS_REGIME_AND_SAYS_IT_IS_NOT_A_SIGNAL():
    """(f)5, on both surfaces -- the panel row and the phone."""
    p = pw.panel_text(ticker="IWM", event="EXHAUSTION", close=268.4, basis="b",
                      action=pw.ACTION_TIGHTEN, shown_regime="NARROW UPTREND")
    assert "NARROW UPTREND" in p["tag"] and "alert, not a signal" in p["tag"]
    f = pw.push_fields(ticker="IWM", event="EXHAUSTION", action=pw.ACTION_TIGHTEN,
                       shown_regime="NARROW UPTREND")
    assert "NARROW UPTREND" in f["alert_type"]
    assert "alert, not a signal" in f["action"]


# ── 6. the push carries NO price level ────────────────────────────────────

def test_THE_PUSH_PAYLOAD_PASSES_THE_MONEY_GUARD():
    """R-IV.901(b)1 limits this relay to ticker / alert type / action, and
    `_assert_no_money` enforces it by refusing any figure written to the cent. `send` does NOT
    swallow that, so a push carrying a level would not be sent at all."""
    from integrations.ntfy_push import build_message
    f = pw.push_fields(ticker="GUSH", event="LEVEL_BREAK", action=pw.ACTION_REVIEW_STOP,
                       shown_regime="NARROW UPTREND")
    msg = build_message(f["ticker"], f["alert_type"], f["action"])     # raises if it carries one
    assert "GUSH" in msg and "REVIEW STOP" in msg
    assert "31.20" not in msg


def test_THE_GUARD_REALLY_WOULD_REFUSE_A_PRICE_so_this_is_not_a_vacuous_pass():
    """Board 6's mock shows a price in the push. Measured here: it would be refused, which is
    why the level lives on the panel instead. Without this control the test above proves only
    that my strings happen not to contain a number."""
    from integrations.ntfy_push import MoneyInPayload, _assert_no_money
    with pytest.raises(MoneyInPayload):
        _assert_no_money("closed 31.20 below the prior-day low")


def test_THE_PANEL_KEEPS_THE_LEVEL():
    """It discloses nothing the hub does not already show Nick, and the level is the whole
    point of a level break."""
    p = pw.panel_text(ticker="GUSH", event="LEVEL_BREAK", close=31.2,
                      basis="closed 31.2000 below the prior-day low 31.4000",
                      action=pw.ACTION_REVIEW_STOP, shown_regime="NARROW UP")
    assert "31.20" in p["title"]
    assert "31.4000" in p["body"]


# ── 7. the delivery limits (f)4 ───────────────────────────────────────────

def test_THE_COOLDOWN_IS_PER_TICKER_AND_PER_EVENT_TYPE():
    recent = [{"ticker": "QQQ", "event": "LEVEL_BREAK",
               "pushed_at": T - _dt.timedelta(minutes=10)}]
    assert pw.may_push(relation="AGAINST", event="LEVEL_BREAK", ticker="QQQ", recent=recent,
                       now=T, pushed_today=0)[0] is False
    # A DIFFERENT event on the same ticker is not throttled by it.
    assert pw.may_push(relation="AGAINST", event="EXHAUSTION", ticker="QQQ", recent=recent,
                       now=T, pushed_today=0)[0] is True
    # Nor the same event on a different ticker.
    assert pw.may_push(relation="AGAINST", event="LEVEL_BREAK", ticker="IWM", recent=recent,
                       now=T, pushed_today=0)[0] is True


def test_THE_COOLDOWN_EXPIRES():
    recent = [{"ticker": "QQQ", "event": "LEVEL_BREAK",
               "pushed_at": T - _dt.timedelta(minutes=31)}]
    assert pw.may_push(relation="AGAINST", event="LEVEL_BREAK", ticker="QQQ", recent=recent,
                       now=T, pushed_today=0)[0] is True


def test_THE_DAILY_CAP_IS_TWENTY():
    assert pw.PUSH_DAILY_CAP == 20
    assert pw.may_push(relation="AGAINST", event="X", ticker="Q", recent=[], now=T,
                       pushed_today=20)[0] is False
    assert pw.may_push(relation="AGAINST", event="X", ticker="Q", recent=[], now=T,
                       pushed_today=19)[0] is True


def test_A_NON_AGAINST_ALERT_DOES_NOT_CONSUME_A_CAP_SLOT():
    """Order matters. A cap spent on alerts that were never going to be pushed is a cap that
    silences the ones that would have been."""
    ok, why = pw.may_push(relation="WITH", event="X", ticker="Q", recent=[], now=T,
                          pushed_today=20)
    assert ok is False
    assert "not AGAINST" in why, "the relation gate must be reached before the cap"


# ── 8. the exhaustion profit gate (f)4 ────────────────────────────────────

def test_EXHAUSTION_NEEDS_HALF_AN_IMPLIED_MOVE_OF_PROFIT():
    assert pw.exhaustion_push_gate({}, 10.0, 6.0)[0] is True
    assert pw.exhaustion_push_gate({}, 10.0, 4.0)[0] is False
    assert "0.5x gate" in pw.exhaustion_push_gate({}, 10.0, 4.0)[1]


def test_AN_UNAVAILABLE_IV_PUSHES_AND_SAYS_SO():
    """(f)4 names this case and chooses to push. An exhaustion against a profitable position is
    worth saying even without the yardstick, and the label says the yardstick is missing rather
    than implying a measurement."""
    ok, note = pw.exhaustion_push_gate({}, None, 4.0)
    assert ok is True
    assert note == "vs implied: n/a"


def test_an_unknown_PROFIT_with_a_known_implied_move_does_NOT_push():
    """The gate is about profit. With a yardstick present and the measurement missing, the
    honest answer is to hold, not to assume the position is far enough ahead."""
    ok, why = pw.exhaustion_push_gate({}, 10.0, None)
    assert ok is False
    assert "not known" in why


# ── 9. nothing here is a signal (f)6 ──────────────────────────────────────

def test_THE_MODULE_CANNOT_WRITE_A_SIGNAL_OR_SEND_A_PUSH():
    """(f)6, and a module with a connection in it is one edit from gating something. Everything
    here is a pure decision; the job layer owns the IO."""
    import inspect
    src = inspect.getsource(pw)
    for banned in ("INSERT", "UPDATE", "DELETE", "get_postgres_client", "httpx", "requests",
                   "ntfy_push.send", "asyncio"):
        assert banned not in src, banned
