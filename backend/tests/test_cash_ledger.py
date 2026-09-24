"""Money integrity — cash is a ledger of events, and a balance is what they add to.

R-IV.493(f) / R-IV.497(c), with R-IV.539(d)'s rule that the Roth's transfers and
dividend are EVENTS, not trades.

Convention #30: every refusal is paired with a case that must succeed. A ledger that
returned None for every balance would satisfy each "it does not invent a figure"
test and be useless.
"""

from datetime import date

import pytest

from services import cash_ledger as cl


def ev(kind, amount, day, eid=None, **kw):
    return dict({"id": eid, "flow_type": kind, "amount": amount,
                 "activity_date": date(2026, 9, day)}, **kw)


# -- the vocabulary ----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("TRANSFER_IN", cl.TRANSFER_IN),
    ("transfer_in", cl.TRANSFER_IN),
    ("DEPOSIT", cl.TRANSFER_IN),          # the vocabulary already in the table
    ("WITHDRAWAL", cl.TRANSFER_OUT),
    ("DIV", cl.DIVIDEND),
    ("TRADE_DEBIT", cl.TRADE_DEBIT),
])
def test_the_legacy_vocabulary_maps_onto_one_reader(raw, expected):
    """One reader over the whole history, rather than two disagreeing about it."""
    assert cl.normalise_type(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "REBATE", "MYSTERY", "journal"])
def test_a_type_the_ledger_does_not_know_is_not_quietly_a_transfer(raw):
    assert cl.normalise_type(raw) is None


def test_a_transfer_is_external_and_a_dividend_is_not():
    """R-IV.539(d): money moved in is not money earned. A dividend IS earned, so it
    is typed apart from both a transfer and a trade rather than folded into either."""
    assert cl.is_external(ev(cl.TRANSFER_IN, 88.15, 14)) is True
    assert cl.is_external(ev(cl.DIVIDEND, 0.64, 14)) is False
    assert cl.is_external(ev(cl.TRADE_DEBIT, -40.00, 14)) is False


# -- idempotency -------------------------------------------------------------

def test_the_same_movement_makes_the_same_key():
    a = cl.dedup_key("FIDELITY_ROTH", cl.TRANSFER_IN, "88.15", date(2026, 8, 31), "hist.csv")
    b = cl.dedup_key("FIDELITY_ROTH", cl.TRANSFER_IN, 88.15, date(2026, 8, 31), "hist.csv")
    assert a == b


@pytest.mark.parametrize("change", [
    {"account": "ROBINHOOD"}, {"event_type": cl.TRANSFER_OUT}, {"amount": "88.16"},
    {"event_date": date(2026, 9, 1)}, {"source_ref": "other.csv"}, {"occurrence": 1},
])
def test_a_different_movement_makes_a_different_key(change):
    base = dict(account="FIDELITY_ROTH", event_type=cl.TRANSFER_IN, amount="88.15",
                event_date=date(2026, 8, 31), source_ref="hist.csv", occurrence=0)
    assert cl.dedup_key(**base) != cl.dedup_key(**dict(base, **change))


def test_two_real_same_day_same_amount_events_stay_distinct():
    """The transfers are both 88.15. Occurrence is the last resort that keeps the
    second one from being read as a re-import of the first."""
    a = cl.dedup_key("R", cl.TRANSFER_IN, "88.15", date(2026, 8, 31), None, 0)
    b = cl.dedup_key("R", cl.TRANSFER_IN, "88.15", date(2026, 8, 31), None, 1)
    assert a != b


# -- the derived balance -----------------------------------------------------

def test_without_an_anchor_no_balance_is_stated():
    """Inventing zero as the opening figure is the quiet assumption this removes."""
    out = cl.balance_from_events([ev(cl.TRANSFER_IN, 88.15, 14)])
    assert out["balance"] is None
    assert out["derivable"] is False
    assert "no OPENING_BALANCE" in out["reason"]


def test_an_anchor_plus_its_events_gives_a_balance():
    """POSITIVE CONTROL, on R-IV.539(d)'s own figures."""
    events = [
        ev(cl.ANCHOR, "11000.00", 1, 1),
        ev(cl.TRANSFER_IN, "60.93", 4, 2),
        ev(cl.TRANSFER_IN, "88.15", 14, 3),
        ev(cl.DIVIDEND, "0.64", 15, 4),
    ]
    out = cl.balance_from_events(events)
    assert out["opening_balance"] == 11000.00
    assert out["movement_since_opening"] == 149.72
    assert out["balance"] == 11149.72
    assert out["events_counted"] == 3
    assert out["external_flow_since_opening"] == 149.08      # the dividend is not
    assert out["by_type"][cl.DIVIDEND] == 0.64


def test_the_anchor_is_a_starting_point_not_an_addition():
    out = cl.balance_from_events([ev(cl.ANCHOR, "100.00", 1, 1),
                                  ev(cl.TRANSFER_IN, "10.00", 2, 2)])
    assert out["balance"] == 110.00      # not 210.00


def test_only_the_latest_anchor_counts_and_what_precedes_it_is_dropped():
    """Re-anchoring from a fresh statement starts again FROM that statement. Adding
    the earlier anchor plus everything since would double every event between."""
    events = [
        ev(cl.ANCHOR, "100.00", 1, 1),
        ev(cl.TRANSFER_IN, "50.00", 2, 2),      # already inside the second statement
        ev(cl.ANCHOR, "150.00", 3, 3),
        ev(cl.TRANSFER_IN, "10.00", 4, 4),
    ]
    out = cl.balance_from_events(events)
    assert out["opening_balance"] == 150.00
    assert out["opening_date"] == "2026-09-03"
    assert out["balance"] == 160.00
    assert out["events_counted"] == 1


def test_an_as_of_date_stops_the_ledger_where_it_is_asked_to():
    events = [ev(cl.ANCHOR, "100.00", 1, 1), ev(cl.TRANSFER_IN, "10.00", 5, 2),
              ev(cl.TRANSFER_IN, "20.00", 9, 3)]
    assert cl.balance_from_events(events, as_of=date(2026, 9, 6))["balance"] == 110.00
    assert cl.balance_from_events(events, as_of=date(2026, 9, 30))["balance"] == 130.00


def test_an_undated_event_is_reported_never_quietly_summed():
    """It cannot be placed before or after the anchor, so it cannot be counted."""
    events = [ev(cl.ANCHOR, "100.00", 1, 1),
              {"id": 7, "flow_type": cl.TRANSFER_IN, "amount": "999.00",
               "activity_date": None}]
    out = cl.balance_from_events(events)
    assert out["balance"] == 100.00
    assert out["undated_events"] == [7]


def test_an_unknown_type_is_reported_never_quietly_summed():
    events = [ev(cl.ANCHOR, "100.00", 1, 1), ev("REBATE", "5.00", 2, 8)]
    out = cl.balance_from_events(events)
    assert out["balance"] == 100.00
    assert out["unknown_types"] == [{"id": 8, "flow_type": "REBATE"}]
    # Positive control: a type it DOES know is counted.
    assert cl.balance_from_events(
        [ev(cl.ANCHOR, "100.00", 1, 1), ev(cl.FEE, "-5.00", 2, 8)])["balance"] == 95.00


def test_a_trade_debit_reduces_cash_and_a_credit_raises_it():
    events = [ev(cl.ANCHOR, "1000.00", 1, 1), ev(cl.TRADE_DEBIT, "-40.00", 2, 2),
              ev(cl.TRADE_CREDIT, "65.00", 3, 3)]
    out = cl.balance_from_events(events)
    assert out["balance"] == 1025.00
    assert out["by_type"][cl.TRADE_DEBIT] == -40.00


def test_money_rounds_half_up_through_the_same_helper_as_the_positions():
    out = cl.balance_from_events([ev(cl.ANCHOR, "0.00", 1, 1),
                                  ev(cl.DIVIDEND, "0.005", 2, 2)])
    assert out["balance"] == 0.01           # banker's rounding would give 0.00


# -- reconciliation ----------------------------------------------------------

def test_a_ledger_that_matches_the_stored_total_says_so():
    """POSITIVE CONTROL for the reconciler."""
    d = cl.balance_from_events([ev(cl.ANCHOR, "100.00", 1, 1)])
    out = cl.reconcile(d, "100.00")
    assert out["agrees"] is True and out["difference"] == 0.0 and out["reason"] is None


def test_a_disagreement_states_both_numbers_and_the_gap():
    """Neither figure is quietly preferred: the stored one cannot be reconstructed,
    the derived one is only as complete as the events written down."""
    d = cl.balance_from_events([ev(cl.ANCHOR, "100.00", 1, 1)])
    out = cl.reconcile(d, "250.00")
    assert out["derived"] == 100.00 and out["stored"] == 250.00
    assert out["difference"] == -150.00
    assert out["agrees"] is False
    assert "never written down" in out["reason"]


def test_with_no_anchor_the_reconciler_does_not_pretend_to_compare():
    d = cl.balance_from_events([ev(cl.TRANSFER_IN, "10.00", 1, 1)])
    out = cl.reconcile(d, "250.00")
    assert out["agrees"] is None and out["difference"] is None
    assert "cannot state a balance" in out["reason"]


def test_with_no_stored_figure_it_says_that_instead():
    d = cl.balance_from_events([ev(cl.ANCHOR, "100.00", 1, 1)])
    out = cl.reconcile(d, None)
    assert out["agrees"] is None and "no stored cash figure" in out["reason"]


# -- performance: a deposit is not a gain ------------------------------------

def test_external_flow_is_separated_from_income_and_from_trades():
    """R-IV.539(d)'s events, by their real figures: three transfers in and a 0.64
    dividend. An account that grew by 237.23 because 237.23 walked in has returned
    0.64, not 237.87."""
    events = [
        ev(cl.TRANSFER_IN, "88.15", 1, 1, activity_date=date(2026, 8, 31)),
        ev(cl.TRANSFER_IN, "60.93", 4, 2),
        ev(cl.TRANSFER_IN, "88.15", 14, 3),
        ev(cl.DIVIDEND, "0.64", 15, 4),
        ev(cl.TRADE_DEBIT, "-40.00", 16, 5),
    ]
    out = cl.performance_inputs(events)
    assert out["external_flow"] == 237.23
    assert out["income"] == 0.64
    assert out["trade_flow"] == -40.00


def test_the_period_bounds_are_honoured():
    events = [ev(cl.TRANSFER_IN, "10.00", 1, 1), ev(cl.TRANSFER_IN, "20.00", 20, 2)]
    assert cl.performance_inputs(events, start=date(2026, 9, 10))["external_flow"] == 20.0
    assert cl.performance_inputs(events, end=date(2026, 9, 10))["external_flow"] == 10.0
    # Positive control: unbounded sees both.
    assert cl.performance_inputs(events)["external_flow"] == 30.0


# -- a mechanism is not a direction ------------------------------------------
#
# ACH is 22 of the 31 rows in the live table: all positive on the Roth, all but one
# negative on Robinhood. The same word for money arriving and money leaving.

@pytest.mark.parametrize("raw", ["ACH", "TRANSFER", "JOURNAL", "WIRE", "EFT"])
def test_a_mechanism_type_takes_its_direction_from_the_sign(raw):
    assert cl.normalise_type(raw, "88.15") == cl.TRANSFER_IN
    assert cl.normalise_type(raw, "-88.15") == cl.TRANSFER_OUT


@pytest.mark.parametrize("raw", ["ACH", "TRANSFER", "WIRE"])
def test_a_mechanism_with_no_amount_is_unknown_not_a_deposit(raw):
    """A withdrawal mistaken for a deposit is wrong by twice itself."""
    assert cl.normalise_type(raw) is None
    assert cl.normalise_type(raw, "not a number") is None


def test_the_live_shape_of_the_roth_ledger_reads_end_to_end():
    """The four ACH rows, three dividends and six transfers actually in the table,
    with an anchor put in front of them. Without the sign rule the four ACH rows
    would have been unknown types and silently uncounted."""
    events = [
        ev(cl.ANCHOR, "0.00", 1, 1, activity_date=date(2026, 4, 1)),
        ev("ACH", "255.97", 10, 11, activity_date=date(2026, 4, 10)),
        ev("ACH", "88.15", 23, 14, activity_date=date(2026, 4, 23)),
        ev("ACH", "176.30", 26, 18, activity_date=date(2026, 5, 26)),
        ev("ACH", "88.15", 9, 74, activity_date=date(2026, 6, 9)),
        ev("DIVIDEND", "17.03", 30, 82, activity_date=date(2026, 6, 30)),
        ev("DEPOSIT", "60.92", 7, 80, activity_date=date(2026, 7, 7)),
    ]
    out = cl.balance_from_events(events)
    assert out["unknown_types"] == []                     # the ACH rows are read
    assert out["balance"] == 686.52
    assert out["external_flow_since_opening"] == 669.49   # the dividend is excluded
    assert out["by_type"][cl.TRANSFER_IN] == 669.49


# -- R-IV.542(b): the anchor, and what sits either side of it ----------------

def test_pre_anchor_events_are_written_for_the_record_and_ignored_by_the_reader():
    """They are already inside the statement the anchor came from. Counting them
    again would add the same money twice."""
    events = [
        ev(cl.TRANSFER_IN, "88.15", 1, 1),          # before
        ev(cl.DIVIDEND, "17.03", 5, 2),             # before
        ev(cl.ANCHOR, "6007.29", 24, 3),
        ev(cl.DIVIDEND, "0.64", 25, 4),             # after
    ]
    out = cl.balance_from_events(events)
    assert out["balance"] == 6007.93
    assert out["events_counted"] == 1


def test_the_roth_anchor_with_its_pending_dividend():
    """POSITIVE CONTROL on R-IV.542(b)'s own figures: cash 6,007.29 as of 09-24,
    with the 0.64 pending dividend as an event after it."""
    events = [ev(cl.ANCHOR, "6007.29", 24, 1), ev(cl.DIVIDEND, "0.64", 25, 2)]
    out = cl.balance_from_events(events)
    assert out["opening_balance"] == 6007.29
    assert out["balance"] == 6007.93
    assert out["external_flow_since_opening"] == 0.0     # a dividend is not a transfer


def test_a_same_day_event_is_counted_and_flagged():
    """The anchor is an instant (11:09 ET); an event carries only a date. So a
    same-day event cannot be ordered against it by its own data. R-IV.542(b) puts
    the pending dividend after the anchor, so it counts -- and it is named, because
    the one thing worse than counting it would be counting it silently."""
    events = [ev(cl.ANCHOR, "6007.29", 24, 1), ev(cl.DIVIDEND, "0.64", 24, 2)]
    out = cl.balance_from_events(events)
    assert out["balance"] == 6007.93
    assert out["same_day_as_anchor"] == [2]


def test_on_the_anchors_date_the_recording_order_decides():
    """R-IV.559(b)3 REVERSED an earlier reading of this. The principal reads his
    broker figure and types it, so everything already in the ledger at that moment is
    INSIDE the figure and everything entered afterwards is not. Recording order is
    the only thing that can tell them apart -- the date cannot.

    This test previously asserted the opposite, that insertion order must not matter.
    That was right about WHICH anchor wins (a question about dates) and wrong about
    which same-day events count (a question about who was recorded first)."""
    recorded_before = [ev(cl.DIVIDEND, "0.64", 24, 1), ev(cl.ANCHOR, "6007.29", 24, 2)]
    recorded_after = [ev(cl.ANCHOR, "6007.29", 24, 1), ev(cl.DIVIDEND, "0.64", 24, 2)]
    assert cl.balance_from_events(recorded_before)["balance"] == 6007.29   # inside it
    assert cl.balance_from_events(recorded_after)["balance"] == 6007.93    # after it


def test_a_created_at_beats_the_row_id_when_both_rows_carry_one():
    """A backfill can insert an old movement with a new id, so a timestamp wins
    where both rows have one."""
    from datetime import datetime as _dt, timezone as _tz

    anchor = dict(ev(cl.ANCHOR, "100.00", 24, 2),
                  created_at=_dt(2026, 9, 24, 20, 16, tzinfo=_tz.utc))
    early = dict(ev(cl.TRANSFER_IN, "10.00", 24, 9),        # higher id...
                 created_at=_dt(2026, 9, 24, 18, 30, tzinfo=_tz.utc))  # ...earlier write
    assert cl.balance_from_events([anchor, early])["balance"] == 100.00


def test_an_event_that_cannot_be_placed_is_counted_and_flagged():
    """Unknown reads as NOT before: dropping a real movement is worse than
    double-counting one the next re-anchor will correct."""
    anchor = {"id": None, "flow_type": cl.ANCHOR, "amount": "100.00",
              "activity_date": ev(cl.FEE, 0, 24)["activity_date"]}
    e = {"id": None, "flow_type": cl.TRANSFER_IN, "amount": "10.00",
         "activity_date": anchor["activity_date"]}
    out = cl.balance_from_events([anchor, e])
    assert out["balance"] == 110.00
    assert out["same_day_as_anchor"] == [None]


def test_nothing_is_flagged_same_day_when_nothing_is():
    out = cl.balance_from_events([ev(cl.ANCHOR, "100.00", 1, 1),
                                  ev(cl.DIVIDEND, "1.00", 2, 2)])
    assert out["same_day_as_anchor"] == []


def test_robinhood_stays_underivable_on_its_april_ledger():
    """R-IV.542(c): no anchor from the April events, and no zero. Seventeen real
    movements still produce no balance, which is the correct answer."""
    events = [ev("ACH", "-500.00", 20, i) for i in range(1, 18)]
    out = cl.balance_from_events(events)
    assert out["balance"] is None and out["derivable"] is False
    assert out["by_type"] == {}          # nothing counted without a starting point


# -- the anchor route's contract ---------------------------------------------

def _portfolio_source():
    import inspect

    from api import portfolio

    return inspect.getsource(portfolio.write_cash_anchor)


def _portfolio_live_strings():
    """Only the strings the route actually executes with. Its docstring names
    `account_balances` on purpose -- to say it does not touch it -- so a text scan
    cannot tell the promise apart from a breach of it."""
    import ast
    import inspect

    from api import portfolio

    tree = ast.parse(inspect.getsource(portfolio.write_cash_anchor).lstrip())
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docs.add(id(first.value))
    return " ".join(n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docs).upper()


def test_the_anchor_route_refuses_without_evidence_and_without_a_ruling():
    """An opening balance with no statement behind it is a guess with a timestamp."""
    src = _portfolio_source()
    assert "evidence_ref is required" in src
    assert "ruling is required" in src


def test_the_anchor_route_touches_no_stored_balance():
    """Writing both would leave two figures free to disagree, which is the fault."""
    live = _portfolio_live_strings()
    assert "ACCOUNT_BALANCES" not in live
    assert "UPDATE " not in live
    # Positive control: it DOES write the ledger, so the scan is reading real SQL.
    assert "INSERT INTO CASH_FLOWS" in live


def test_the_anchor_route_is_idempotent():
    live = _portfolio_live_strings()
    assert "ON CONFLICT" in live and "DO NOTHING" in live


# -- R-IV.553(a) / R-IV.557(b): an anchor is never a movement ----------------
#
# The Robinhood double count, reproduced. The principal re-anchored twice, two
# minutes apart (ids 96 and 97, both 491.49 on 2026-09-24, distinct idempotency keys
# so both landed). The reader took 97 as the opening and walked 96 as an ordinary
# same-day event: 491.49 + 491.49 - 16.00 = 966.98, exactly what was served.

def test_a_superseded_anchor_is_not_counted_as_cash():
    """THE DEFECT, by its real figures. 475.49 is the answer; 966.98 was served."""
    events = [
        ev(cl.TRADE_DEBIT, "-16.00", 24, 84),
        ev(cl.ANCHOR, "491.49", 24, 96),
        ev(cl.ANCHOR, "491.49", 24, 97),
    ]
    out = cl.balance_from_events(events)
    assert out["opening_balance"] == 491.49        # the later anchor
    assert out["balance"] == 491.49                # not 966.98
    # The trade was recorded BEFORE the anchor (id 84 < 97), so it is already inside
    # the principal's typed figure -- R-IV.559(b)3. Neither anchor is summed, which
    # is what this test is named for, and the trade is not double-counted either.
    assert out["events_counted"] == 0
    assert 491.49 + 491.49 - 16.00 == 966.98       # the figure that was served


def test_the_double_count_is_not_merely_hidden_by_ordering():
    """Whichever order they arrive in, and whichever is chosen as the opening, no
    anchor row is ever summed."""
    a = [ev(cl.ANCHOR, "491.49", 24, 97), ev(cl.ANCHOR, "491.49", 24, 96),
         ev(cl.TRADE_DEBIT, "-16.00", 24, 84)]
    assert cl.balance_from_events(a)["balance"] == 491.49
    # POSITIVE CONTROL: a trade recorded AFTER the anchor does count, so the 491.49
    # above is the rule working rather than every same-day row being dropped.
    b = a + [ev(cl.TRADE_CREDIT, "90.00", 24, 98)]
    assert cl.balance_from_events(b)["balance"] == 581.49


def test_three_anchors_still_leave_one_opening_and_no_movement():
    events = [ev(cl.ANCHOR, "100.00", 1, 1), ev(cl.ANCHOR, "200.00", 2, 2),
              ev(cl.ANCHOR, "300.00", 3, 3), ev(cl.DIVIDEND, "1.00", 4, 4)]
    out = cl.balance_from_events(events)
    assert out["opening_balance"] == 300.00
    assert out["balance"] == 301.00
    assert out["events_counted"] == 1


def test_an_earlier_dated_anchor_is_still_not_a_movement():
    """A superseded anchor BEFORE the chosen one was already skipped as pre-anchor;
    this keeps it skipped for the right reason rather than by accident of date."""
    events = [ev(cl.ANCHOR, "100.00", 1, 1), ev(cl.ANCHOR, "150.00", 3, 2),
              ev(cl.TRANSFER_IN, "10.00", 4, 3)]
    out = cl.balance_from_events(events)
    assert out["balance"] == 160.00
    assert out["events_counted"] == 1


def test_a_single_anchor_still_behaves_exactly_as_before():
    """POSITIVE CONTROL: the ordinary one-anchor case is untouched."""
    out = cl.balance_from_events([ev(cl.ANCHOR, "6007.29", 24, 1),
                                  ev(cl.DIVIDEND, "0.64", 24, 2)])
    assert out["balance"] == 6007.93


# -- R-IV.557(c): the key must not depend on how the amount was typed --------

@pytest.mark.parametrize("a,b", [
    (-16.0, "-16.00"), (88.15, "88.1500"), ("0.64", 0.64), (60.93, "60.930"),
])
def test_the_same_movement_keys_the_same_however_the_amount_arrives(a, b):
    """A form sends the float -16.0; the same row read back from NUMERIC(10,2) is
    Decimal('-16.00'); a CSV sends "-16.00". Three keys for one movement meant a
    re-imported file would not dedup against what was already there."""
    from datetime import date as _date

    ka = cl.dedup_key("R", cl.TRADE_DEBIT, a, _date(2026, 9, 24), "POS")
    kb = cl.dedup_key("R", cl.TRADE_DEBIT, b, _date(2026, 9, 24), "POS")
    assert ka == kb


def test_two_genuinely_different_amounts_still_key_apart():
    """POSITIVE CONTROL: normalising must not collapse real differences."""
    from datetime import date as _date

    assert cl.dedup_key("R", cl.TRADE_DEBIT, -16.00, _date(2026, 9, 24), "P") != \
        cl.dedup_key("R", cl.TRADE_DEBIT, -16.01, _date(2026, 9, 24), "P")


def test_a_sub_cent_difference_inside_the_scale_still_keys_apart():
    from datetime import date as _date

    assert cl.dedup_key("R", cl.FEE, "0.0001", _date(2026, 9, 24), "P") != \
        cl.dedup_key("R", cl.FEE, "0.0002", _date(2026, 9, 24), "P")


def test_an_unreadable_amount_does_not_raise():
    from datetime import date as _date

    assert cl.dedup_key("R", cl.FEE, "not a number", _date(2026, 9, 24), "P")
