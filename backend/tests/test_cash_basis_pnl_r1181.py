"""R-IV.1181 — unrealized P&L on ONE basis (cash), and the display states around it.

THE DEFECT, pinned to the cent before anything was changed. Row 978 displayed +24.00 / +270.9%.

    numerator    `unrealized_pnl` <- economics() <- surviving_cost() = SUM(qty x price) x 100.
                 Lot `fees` were summed separately and never entered it, so the figure was GROSS.
    denominator  `pnlPct` divided by |row.cost_basis|, and the row's cost_basis is the CASH
                 figure with fees in it.

A gross numerator over a cash denominator. Solving the two displayed numbers against the two
ruled ones recovers the whole row, and it reconciles exactly:

    gross basis   -10.00   (1 contract at a signed price of -0.10)
    fees           +1.14
    cash basis     -8.86   == the stored cost_basis, per position_economics' own comment
    market value  +14.00   (mark 0.14 x 1 x 100)
    gross P&L  14.00 - (-10.00) = +24.00   <- was shown
    cash  P&L  14.00 -  (-8.86) = +22.86   <- ruled
    percent    22.86 / 8.86     =  258.0%  <- ruled

A SECOND ROW CONFIRMS THE RULE AND WAS NOT USED TO DERIVE IT. `_credit_max_loss`'s comment
records SOUN 234: "surviving_cost returns +96.00, while the ROW's cost_basis is -95.82". The
difference, 0.18, is its fees. Signed gross -96.00 plus 0.18 is -95.82 exactly. One rule, two
rows, both to the cent, and the second one a credit structure rather than a debit.

TWO SIGN ERRORS WERE MADE WRITING THIS, and both were caught by a control rather than by a
test I had thought to write:

  1. The P&L read the local `cost_total` while the payload published a flipped
     `cost_at_remainder`. A credit spread 18.00 up reported -78.00. Two representations of one
     value, and the arithmetic took the one that was not published.
  2. Fees were added to the unsigned gross BEFORE the credit flip, so negating the sum negated
     the fees too and a credit's own costs made the credit look bigger: -48.52 where the truth
     is -47.48.

Both are fixed, and both have a test below, because the controls that caught them were ad hoc.
"""
from __future__ import annotations

import datetime as dt
import io
import os
import re
from decimal import Decimal

import pytest

from services.position_economics import economics, surviving_cost, surviving_cost_and_fees

FRONTEND = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")

SPREAD = {"long_strike": Decimal("4"), "short_strike": Decimal("5")}


def lot(qty, price, fees="0", lot_id=1, day=1):
    return {"id": lot_id, "qty": Decimal(str(qty)), "price": Decimal(str(price)),
            "fees": Decimal(str(fees)), "fill_time": dt.datetime(2026, 10, day, 14, 0)}


def row(structure, asset_type="OPTION", **extra):
    return {"position_id": "t", "asset_type": asset_type, "status": "OPEN",
            "structure": structure, **extra}


# ── the two real rows ────────────────────────────────────────────────────────

def test_row_978_reproduces_the_ruled_figures_exactly():
    """THE RULING'S OWN NUMBERS. A put_debit_spread opened for a net credit by penny-inverted
    fills: signed lot price -0.10, fees 1.14, mark 0.14."""
    e = economics(row("put_debit_spread"), [lot(1, "-0.10", "1.14")], "0.14")
    assert e["cost_at_remainder_gross"] == -10.00
    assert e["fees_at_remainder"] == 1.14
    assert e["cost_at_remainder"] == -8.86
    assert e["market_value"] == 14.00
    assert e["unrealized_pnl"] == 22.86
    assert e["unrealized_pnl_pct"] == 258.0


def test_soun_234s_recorded_basis_reproduces_too():
    """A CREDIT structure, and a row this module documents independently: its lots hold +96.00
    gross and its stored cost_basis is -95.82. The 0.18 difference is its fees."""
    e = economics(row("put_credit_spread", **SPREAD), [lot(2, "0.48", "0.18")], "0.30")
    assert e["cost_at_remainder_gross"] == -96.00
    assert e["cost_at_remainder"] == -95.82


# ── fees always push toward debit ────────────────────────────────────────────

def test_fees_make_a_debit_cost_more():
    e = economics(row("long_call"), [lot(2, "1.00", "1.30")], "1.50")
    assert e["cost_at_remainder"] == 201.30
    assert e["unrealized_pnl"] == 98.70, "gross would be +100.00"


def test_fees_make_a_credit_net_LESS():
    """SIGN ERROR 2. Adding fees to the unsigned gross and flipping afterwards negated the fees
    with it, so a credit's own costs made the credit larger: -48.52 instead of -47.48, and a
    P&L of +18.52 instead of +17.48."""
    e = economics(row("put_credit_spread", **SPREAD), [lot(1, "0.48", "0.52")], "0.30")
    assert e["cost_at_remainder"] == -47.48
    assert e["unrealized_pnl"] == 17.48


def test_a_fee_never_moves_the_basis_in_the_negative_direction():
    """The property behind both cases above, asserted as a property. Whatever the structure,
    adding a fee moves the signed basis UP -- money left the account."""
    for structure, price in (("long_call", "1.00"), ("put_credit_spread", "0.48"),
                             ("put_debit_spread", "-0.10"), ("stock", "10")):
        at = "EQUITY" if structure == "stock" else "OPTION"
        r = row(structure, at, **(SPREAD if "credit" in structure else {}))
        no_fee = economics(r, [lot(1, price, "0")], "0.50")["cost_at_remainder"]
        with_fee = economics(r, [lot(1, price, "0.75")], "0.50")["cost_at_remainder"]
        assert with_fee > no_fee, structure
        assert round(with_fee - no_fee, 2) == 0.75, structure


# ── one signed basis, one rule ───────────────────────────────────────────────

def test_a_credit_structures_market_value_is_a_LIABILITY():
    """Signed like the cost it is compared against: what it would cost to buy back is money
    owed, so it is negative. That is what lets one subtraction serve every structure."""
    e = economics(row("put_credit_spread", **SPREAD), [lot(1, "0.48")], "0.30")
    assert e["market_value"] == -30.00
    assert "liability" in e["market_value_direction"]


def test_an_owned_structures_market_value_is_an_ASSET():
    e = economics(row("long_call"), [lot(1, "1.00")], "1.50")
    assert e["market_value"] == 150.00
    assert "asset" in e["market_value_direction"]


def test_the_credit_case_the_OLD_two_branch_code_existed_for_still_works():
    """SIGN ERROR 1, and the regression it would have been. The old arithmetic was
    `abs(cost) - value`, written for SOUN 234's shape: sold at 0.48 with a mark of 0.30 is
    +18.00 up. My single rule first read the unflipped local cost and reported -78.00."""
    e = economics(row("put_credit_spread", **SPREAD), [lot(1, "0.48", "0")], "0.30")
    assert e["unrealized_pnl"] == 18.00


def test_the_pnl_is_exactly_market_value_minus_the_published_cost():
    """ONE RULE, and it must hold against the figures the payload itself serves -- not against
    an internal variable. That gap is precisely what produced the -78.00."""
    for structure, price, fees, mark, at in (
            ("long_call", "1.00", "1.30", "1.50", "OPTION"),
            ("put_credit_spread", "0.48", "0.52", "0.30", "OPTION"),
            ("put_debit_spread", "-0.10", "1.14", "0.14", "OPTION"),
            ("stock", "10", "0", "11", "EQUITY")):
        r = row(structure, at, **(SPREAD if "credit" in structure else {}))
        e = economics(r, [lot(1, price, fees)], mark)
        assert e["unrealized_pnl"] == pytest.approx(
            round(e["market_value"] - e["cost_at_remainder"], 2), abs=0.005), structure


def test_the_percent_uses_THE_SAME_basis_as_the_numerator():
    for structure, price, fees, mark, at in (
            ("long_call", "1.00", "1.30", "1.50", "OPTION"),
            ("put_credit_spread", "0.48", "0.52", "0.30", "OPTION"),
            ("put_debit_spread", "-0.10", "1.14", "0.14", "OPTION")):
        r = row(structure, at, **(SPREAD if "credit" in structure else {}))
        e = economics(r, [lot(1, price, fees)], mark)
        want = round(e["unrealized_pnl"] / abs(e["cost_at_remainder"]) * 100, 1)
        assert e["unrealized_pnl_pct"] == pytest.approx(want, abs=0.05), structure


def test_a_zero_cost_has_no_percent_and_says_so():
    """A return on nothing has no denominator. None with a reason, never a zero or an inf."""
    e = economics(row("long_call"), [lot(1, "0", "0")], "1.50")
    assert e["unrealized_pnl_pct"] is None
    assert "denominator" in e["unrealized_pnl_pct_reason"]


# ── fee pro-rating over the open remainder, FIFO ─────────────────────────────

def test_fees_are_pro_rated_over_the_surviving_fraction_of_a_lot():
    """A fee is paid on a fill, so the part still held carries the matching part of it.
    Charging the remainder a half-sold lot's WHOLE fee would make a position read worse the
    more of it had been closed, and would count the fee twice across the realized side."""
    lots = [lot(4, "1.00", "2.00", lot_id=1, day=1), lot(-2, "1.20", "0", lot_id=2, day=2)]
    cost, fees = surviving_cost_and_fees(lots)
    assert cost == Decimal("2.00")
    assert fees == Decimal("1.00"), "half the lot survives, so half its fee does"


def test_the_gross_half_still_agrees_with_the_older_function():
    """`surviving_cost` keeps its meaning and a dozen callers read it. The new function must
    not quietly disagree with it about the cost."""
    for lots in ([lot(1, "0.48")],
                 [lot(4, "1.00", "2.00", lot_id=1, day=1), lot(-2, "1.20", lot_id=2, day=2)],
                 [lot(3, "-0.10", "1.00")]):
        assert surviving_cost_and_fees(lots)[0] == surviving_cost(lots)


@pytest.mark.parametrize("lots", [
    [],
    [{"id": 1, "qty": Decimal("1"), "price": None, "fees": Decimal("0"),
      "fill_time": dt.datetime(2026, 10, 1)}],
    [{"id": 1, "qty": None, "price": Decimal("1"), "fees": Decimal("0"),
      "fill_time": dt.datetime(2026, 10, 1)}],
    [lot(1, "1.00", "0", lot_id=1, day=1), lot(-3, "1.20", "0", lot_id=2, day=2)],
])
def test_what_it_cannot_state_it_refuses(lots):
    """No lots, an unpriced lot, a missing quantity, or more sold than acquired. Nothing is
    substituted -- a stand-in figure is the fault this module exists to remove."""
    assert surviving_cost_and_fees(lots) == (None, None)


def test_a_missing_fee_is_read_as_zero_but_a_missing_PRICE_is_not():
    """Different unknowns. On this book an older lot routinely carries no recorded fee, so
    treating that as zero is the ordinary case; a missing PRICE makes the whole basis unknown
    and must refuse."""
    cost, fees = surviving_cost_and_fees(
        [{"id": 1, "qty": Decimal("1"), "price": Decimal("1.00"), "fees": None,
          "fill_time": dt.datetime(2026, 10, 1)}])
    assert (cost, fees) == (Decimal("1.00"), Decimal("0"))


# ── the fields exist on every path ───────────────────────────────────────────

@pytest.mark.parametrize("lots,mark", [
    ([], "1.00"),                                      # no lots
    ([lot(1, "1.00")], None),                          # no mark
])
def test_the_new_keys_are_present_even_when_there_is_no_figure(lots, mark):
    """Missing a VALUE, never missing a FIELD. `_feed_health` returned a different shape from
    its failure branch and its new fields vanished exactly when they mattered."""
    e = economics(row("long_call"), lots, mark)
    for k in ("unrealized_pnl_pct", "cost_at_remainder_gross", "fees_at_remainder"):
        assert k in e, k
    assert e["basis_reason"]


def test_a_closed_row_still_publishes_no_unrealized_figure():
    """The positive control for the refusals above: a status that has no open remainder must
    not acquire one just because new fields were added."""
    e = economics(row("long_call") | {"status": "CLOSED"}, [lot(1, "1.00")], "1.50")
    assert e["unrealized_pnl"] is None
    assert e["unrealized_pnl_pct"] is None


def test_max_loss_for_a_debit_now_includes_the_fees_paid():
    """A debit's worst case is the money that left the account, which is premium plus fees."""
    e = economics(row("long_call"), [lot(2, "1.00", "1.30")], "1.50")
    assert e["max_loss"] == 201.30


def test_max_loss_is_still_floored_at_zero_for_a_credit_opened_debit():
    """R-IV.761(c) survives the change: row 978's worst case is a REAL zero, not a negative,
    and the reason travels with it. This zero is a measurement and renders as $0.00."""
    e = economics(row("put_debit_spread"), [lot(1, "-0.10", "1.14")], "0.14")
    assert e["max_loss"] == 0.0
    assert "net credit" in e["max_loss_basis"]


def test_a_credit_structures_max_loss_uses_the_NET_credit_kept():
    """Width less the credit kept, and the credit kept is what was actually received -- the net
    after fees, not the gross."""
    e = economics(row("put_credit_spread", **SPREAD), [lot(1, "0.48", "0.52")], "0.30")
    assert e["max_loss"] == 52.52, "100.00 width less the 47.48 net credit"


# ── the row carries the figure to the screen ─────────────────────────────────

def test_attach_economics_stamps_the_percent_and_the_cost():
    import inspect

    from services.read_only import positions as ro

    src = inspect.getsource(ro.attach_economics)
    assert 'p["unrealized_pnl_pct"]' in src
    assert 'p["cost_at_remainder"]' in src


# ── the display ──────────────────────────────────────────────────────────────

def _read(name: str) -> str:
    return io.open(os.path.join(FRONTEND, name), encoding="utf-8", errors="replace").read()


def _code(js: str) -> str:
    """JS with its `//` comments removed.

    INSTANCE NINE AND TEN of a trap already recorded eight times: `"X" not in src` fails on the
    comment explaining why X is wrong, and the better the comment the more certain the false
    failure. Both assertions in this file broke on their own explanations. `_srcscan` does this
    for Python; JS needs its own, and it lives here rather than being re-derived per test.

    Line comments only, and a `//` inside a quoted string is left alone so an https:// URL does
    not eat the rest of its line. Crude on purpose: every use here is a presence or ordering
    claim about code, not an attempt to parse JS.
    """
    out = []
    for line in js.split(chr(10)):
        i = line.find("//")
        if i > 0:
            before = line[:i]
            if (before.count("'") % 2 or before.count('"') % 2
                    or before.count(chr(96)) % 2):
                i = -1
        out.append(line if i < 0 else line[:i])
    return chr(10).join(out)


def test_the_frontend_prefers_the_served_percent():
    src = _read("v2.js")
    i = src.index("function pnlPct")
    body = _code(src[i:src.index("\n  }", i)])
    assert "p.unrealized_pnl_pct != null" in body
    assert body.index("unrealized_pnl_pct") < body.index("cost_basis"), (
        "the served figure must be preferred, not used as a fallback")


def test_a_null_max_loss_renders_an_em_dash_not_a_zero():
    """R-IV.1181(c)1. Zero is a measurement -- it says the worst case IS nothing, true of a
    credit-opened debit structure and false of a row whose lots never arrived."""
    src = _read("v2.js")
    assert "notSet(p, 'max_loss')" in src
    i = src.index("function notSet")
    body = src[i:src.index("\n  }", i)]
    assert "\\u2014" in body, "an em dash"
    assert "title=" in body, "the reason must survive as a tooltip"


def test_the_entry_line_reads_its_direction_from_cost_basis():
    """R-IV.1181(b)+(c)3: `entry_price` is an unsigned magnitude and cannot say which way the
    money went. A bare 'Entry 0.10' reads as a cost on a position that was PAID 0.10."""
    src = _read("v2.js")
    i = src.index("function entryLine")
    body = src[i:src.index("\n  }", i)]
    assert "cost_basis" in body or "cost_at_remainder" in body
    assert "'credit '" in body
    assert "entry_price" in body
    assert "< 0" in body


def test_the_entry_line_never_signs_from_entry_price():
    src = _read("v2.js")
    i = src.index("function entryLine")
    body = src[i:src.index("\n  }", i)]
    assert "Number(p.entry_price) < 0" not in body
    assert "entry_price < 0" not in body


def test_the_legacy_max_loss_bar_says_not_set_instead_of_vanishing():
    src = _read("app.js")
    i = src.index("// Max loss bar")
    body = src[i:i + 900]
    assert "pos.max_loss == null" in body
    assert "&mdash;" in body
    assert "max-loss-why" in body


@pytest.mark.parametrize("page,asset,floor", [
    ("v2.html", "v2.js", 60),
    ("v2.html", "v2.css", 48),
    ("stater.html", "v2.css", 44),
    ("abacus.html", "v2.css", 43),
    ("index.html", "app.js", 180),
    ("index.html", "styles.css", 156),
    ("knowledgebase.html", "styles.css", 31),
])
def test_every_page_pinning_a_changed_asset_was_bumped(page, asset, floor):
    """Four assets changed and five pages pin them, at values that have already diverged. A
    page missed keeps serving whatever was cached under its unchanged pin."""
    m = re.search(re.escape(asset) + r"\?v=(\d+)", _read(page))
    assert m, "%s does not pin %s" % (page, asset)
    assert int(m.group(1)) >= floor, "%s pins %s at %s, expected >= %d" % (
        page, asset, m.group(1), floor)


def test_the_styles_for_both_new_states_exist():
    assert ".not-set" in _read("v2.css")
    assert ".max-loss-why" in _read("styles.css")


# ── the P1 found on the way: the canonical book read was down ────────────────

def test_cut_due_survives_a_string_which_is_what_it_actually_receives():
    """hub_get_positions -- the canonical route to unified_positions -- died with `'str' object
    has no attribute 'isoformat'` for any row with a non-null `cut_due`. `_row_to_dict` is the
    one serialiser every position row passes through and it has always stringified dates, so
    calling `.isoformat()` downstream could only ever work on a value that had bypassed it.

    Dormant while every `cut_due` was NULL, because the guard skips a null. The same file
    already read `expiry` with `isinstance(expiry, str)` a hundred lines earlier.
    """
    from hub_mcp.tools.positions import _iso_day

    assert _iso_day("2026-10-24") == "2026-10-24"
    assert _iso_day("2026-10-24T13:05:00+00:00") == "2026-10-24"
    assert _iso_day(dt.date(2026, 10, 24)) == "2026-10-24"
    assert _iso_day(dt.datetime(2026, 10, 24, 13, 5)) == "2026-10-24"
    assert _iso_day(None) is None
    assert _iso_day("") is None


def test_the_tool_no_longer_calls_isoformat_on_a_row_field():
    import inspect

    from hub_mcp.tools import positions as t

    # Through `function_code`, which strips comments AND docstrings: this assertion failed on
    # the comment that explains the very pattern it forbids.
    from tests._srcscan import function_code

    code = function_code(t.__file__, "_build_position")
    assert ".isoformat()" not in code, (
        "a row field reaching this function has already been stringified by _row_to_dict")
