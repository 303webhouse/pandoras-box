"""R-IV.1469: the Event Strip's earnings chips must be visible in a 4-row desktop tile.

Measured on production 10-31 (4783239f): the tile shows ~74px under the date; UW's economic
calendar listed every 11-02..11-06 event twice, and the chips were pinned to the foot of a
column the tallest day stretched -- so no chip was visible without scrolling.

The fix: duplicate macro events are dropped server-side; each day reads FOMC / book expiries,
then the earnings chips, then the rest of the macro calendar; the chips are not pinned down.
`?earn=off` keeps the old markup exactly.
"""
import datetime as dt
import pathlib
import re

from models import event_strip_b4 as es

ROOT = pathlib.Path(__file__).resolve().parents[2]
MON = dt.date(2026, 11, 2)
TUE = dt.date(2026, 11, 3)


def _weekday(d):
    return d.weekday() < 5


def _strip(macro, **kw):
    return es.build_strip(dt.date(2026, 11, 1), is_trading_day=_weekday, macro=macro,
                          next_session=MON, **kw)


def test_a_macro_event_listed_twice_shows_once():
    macro = [{"date": MON, "name": "ISM Manufacturing PMI"},
             {"date": MON, "name": "Construction Spending"},
             {"date": MON, "name": "ISM Manufacturing PMI"},
             {"date": MON, "name": "Construction Spending"}]
    ks = [e["k"] for e in _strip(macro)["days"][0]["events"]]
    assert len(ks) == 2 and len(set(ks)) == 2


def test_the_same_event_on_two_days_stays_on_both():
    macro = [{"date": MON, "name": "ISM Manufacturing PMI"},
             {"date": TUE, "name": "ISM Manufacturing PMI"}]
    days = _strip(macro)["days"]
    assert len(days[0]["events"]) == 1 and len(days[1]["events"]) == 1


def test_book_expiries_are_not_deduped_against_macro():
    out = _strip([{"date": MON, "name": "ISM Manufacturing PMI"}],
                 book_expiries=[{"date": MON, "label": "HYG exp"}, {"date": MON, "label": "XLF exp"}])
    kinds = [e["kind"] for e in out["days"][0]["events"]]
    assert kinds.count("book") == 2


def _render_fn():
    src = (ROOT / "frontend" / "v2.js").read_text(encoding="utf-8")
    start = src.index("function renderEventStrip()")
    end = src.index("\n  function ", start + 10)
    return src[start:end]


def test_day_column_order_lead_then_chips_then_rest():
    fn = _render_fn()
    lead = fn.index("'<div class=\"ev-evs ev-lead\">' + evsLead")
    chips = fn.index("+ earnCell", lead)
    rest = fn.index("'<div class=\"ev-evs\">' + evsRest", chips)
    assert lead < chips < rest
    # lead = an FOMC decision ('top') or the book's own expiry ('book')
    assert re.search(r"const lead = \(e\) => e\.kind === 'top' \|\| e\.kind === 'book';", fn)


def test_earn_off_keeps_the_old_column_exactly():
    fn = _render_fn()
    assert "? '<div class=\"ev-evs\">' + evs + '</div>' + earnCell" in fn


def test_chips_are_not_pinned_to_the_column_foot():
    css = (ROOT / "frontend" / "assets" / "event-strip-earn.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rule = re.search(r"\.ev-earnlist\s*\{([^}]*)\}", css).group(1)
    assert "margin-top" not in rule
