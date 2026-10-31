"""R-IV.1461(f)5: the Event Strip's earnings chips.

Up to 3 chips a day, held names first then S&P 500 members by market cap, "+N more"; a YOURS
flag; "earnings feed empty" when the table has no rows for the next session (and never when
the table could not be read); the day-after reaction row; and nothing but dates, times and the
market's own numbers.
"""
import datetime as dt

from models import event_strip_b4 as es

MON = dt.date(2026, 11, 2)
TUE = dt.date(2026, 11, 3)
FRI = dt.date(2026, 10, 30)
THU = dt.date(2026, 10, 29)


def _weekday(d):
    return d.weekday() < 5


def _e(t, d, *, timing="AMC", imp=4.8, rx=None, yours=False, sp=True, cap=100):
    return {"ticker": t, "date": d, "in_book": yours, "timing": timing,
            "implied_move_pct": imp, "reaction_pct": rx, "yours": yours, "sp500": sp,
            "market_cap": cap}


def _strip(earnings, **kw):
    kw.setdefault("next_session", MON)
    kw.setdefault("reaction_dates", [THU, FRI])
    return es.build_strip(dt.date(2026, 11, 1), is_trading_day=_weekday, earnings=earnings, **kw)


def test_three_chips_held_first_then_sp500_by_market_cap_then_more():
    rows = [_e("SMALL", MON, sp=False, cap=10**12),     # biggest cap but not in the S&P 500
            _e("AAPL", MON, cap=3 * 10**12), _e("MSFT", MON, cap=2 * 10**12),
            _e("PLTR", MON, cap=10**11), _e("HYG", MON, yours=True, cap=1)]
    day = _strip(rows)["days"][0]
    assert day["iso"] == "2026-11-02"
    assert [c["t"] for c in day["earn_chips"]] == ["HYG", "AAPL", "MSFT"]
    assert day["earn_chips"][0]["yours"] is True and day["earn_more"] == 2
    assert day["earn_chips"][1] == {"t": "AAPL", "timing": "AMC", "implied": 4.8, "yours": False}
    assert day["earn"] == 5


def test_feed_empty_only_when_the_next_session_has_no_rows():
    assert _strip([_e("AAPL", TUE)])["earn_feed_empty"] is True
    assert _strip([_e("AAPL", TUE)])["earn_feed_note"] == "earnings feed empty"
    assert _strip([_e("AAPL", MON)])["earn_feed_empty"] is False
    # a failed read is degraded, never "empty"
    assert _strip([], earnings_read=False)["earn_feed_empty"] is False


def test_the_reaction_row_is_the_markets_move_against_its_priced_move():
    rows = [_e("INTC", THU, rx=-30.0, imp=8.5), _e("AMZN", FRI, rx=None, imp=6.0),
            _e("OLD", dt.date(2026, 10, 28), rx=5.0)]
    s = _strip(rows)
    assert s["reactions"] == [{"t": "INTC", "date": "2026-10-29", "timing": "AMC",
                               "reaction": -30.0, "implied": 8.5, "yours": False}]
    assert s["reactions_more"] == 0


def test_no_beat_miss_or_trade_language_anywhere_in_the_strip():
    import json
    import re
    s = json.dumps(_strip([_e("AAPL", MON), _e("INTC", THU, rx=-30.0)])).lower()
    for word in ("beat", "miss", "buy", "sell", "entry", "target", "bullish", "bearish"):
        assert not re.search(r"\b%s\b" % word, s), word     # "buyback" is the blackout label


def test_days_without_earnings_still_carry_the_fields():
    day = _strip([])["days"][1]
    assert day["earn_chips"] == [] and day["earn_more"] == 0
