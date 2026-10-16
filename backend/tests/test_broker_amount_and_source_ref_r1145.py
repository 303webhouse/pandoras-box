"""R-IV.1145(e) — the broker Amount reaches the ledger, and a credit can be matched to its line.

THE TWO FAULTS THIS CLOSES, both of which already cost real work:

1. `qty x exit_price` CANNOT REPRODUCE BROKER PROCEEDS. The broker's Price column is a rounded
   average of the fills; its Amount is the true total. Row 951: 80 x 18.43 = 1,474.40 against a
   broker Amount of 1,474.76, because the real average fill was 18.4345. What makes it dangerous
   is that the same arithmetic was EXACT on the other leg -- row 985's 30 x 27.97 = 839.10 --
   so a two-leg sanity check passes and conceals the error.

2. A CREDIT POSTED THROUGH THE CASH ROUTE WAS UNMATCHABLE TO ITS CLOSE. `source_ref` is written
   by `close_position()` (a position_id) and by the CSV importer (a file path); the route wrote
   neither. An audit keyed on it reported fourteen already-credited closes as "missing", and
   acting on that list would have invented roughly 14,000 of cash.
"""
from __future__ import annotations

import os
import re

import pytest

from tests._srcscan import code_of_file, function_code

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSITIONS = os.path.join(BACKEND, "api", "unified_positions.py")
PORTFOLIO = os.path.join(BACKEND, "api", "portfolio.py")

SRC_RE = r"[0-9a-f]{12}:L\d+"


# ── (e)1 the broker Amount on the close ─────────────────────────────────────

def test_close_request_accepts_proceeds():
    from api.unified_positions import ClosePositionRequest
    assert "proceeds" in ClosePositionRequest.model_fields
    f = ClosePositionRequest.model_fields["proceeds"]
    assert f.default is None, "proceeds must be OPTIONAL; most callers have only a price"


def test_a_close_still_works_with_no_proceeds():
    """The field is additive. An existing caller that sends only exit_price is unchanged."""
    from api.unified_positions import ClosePositionRequest
    r = ClosePositionRequest(exit_price=18.43)
    assert r.proceeds is None


def test_proceeds_is_preferred_over_the_computed_value():
    code = function_code(POSITIONS, "close_position")
    i = code.index("exact_from_broker")
    window = code[max(0, i - 400):i + 400]
    assert "req.proceeds" in window
    assert "abs" in window, "the magnitude must be taken unsigned"


def test_the_SIGN_still_comes_from_the_STRUCTURE_not_the_caller():
    """A credit spread and a short equity pay out on open and COST on close, so the direction is
    the structure's to decide. If the caller's sign were used, passing a negative `proceeds`
    would silently invert a position's cash."""
    code = function_code(POSITIONS, "close_position")
    i = code.index("cash_basis")
    window = code[i:i + 900]
    assert "CREDIT_STRUCTURES" in window
    assert "is_short_equity" in window
    assert "abs(float(req.proceeds))" in code or "abs(float(req.proceeds))" in window


def test_which_source_was_used_is_RECORDED():
    """A 0.36-rounded figure and an exact one are indistinguishable in the ledger unless the row
    says which it is. The basis goes in the description, which is what a reconciliation reads."""
    code = function_code(POSITIONS, "close_position")
    assert "exact_from_broker" in code
    assert "derived_from_exit_price" in code
    assert "closed position (%s)" in code or 'closed position (' in code


def test_a_close_with_ONLY_proceeds_still_moves_cash():
    """`exit_price` is required by the model today, but the cash block must not be gated on it
    alone -- otherwise a caller supplying the exact figure and no price moves no cash."""
    code = function_code(POSITIONS, "close_position")
    assert "req.exit_price is not None or req.proceeds is not None" in code


# ── (e)2 source_ref on the cash route ───────────────────────────────────────

def test_cash_route_accepts_source_ref():
    from api.portfolio import CashFlowCreate
    assert "source_ref" in CashFlowCreate.model_fields
    assert CashFlowCreate.model_fields["source_ref"].default is None


@pytest.mark.parametrize("good", ["d3af6637dc16:L6", "7c6ce1831b13:L45", "b16b0f6df5da:L1037"])
def test_the_convention_44_format_is_accepted(good):
    assert re.fullmatch(SRC_RE, good)


@pytest.mark.parametrize("bad", [
    "d3af6637dc16:L",            # no line number
    "d3af6637dc16",              # no line at all
    "POS_TSLQ_20260930_R635",    # the close path's vocabulary
    "data/imports/Fid.csv",      # the importer's vocabulary
    "D3AF6637DC16:L6",           # upper case
    "d3af6637dc1:L6",            # 11 hex chars
])
def test_the_other_vocabularies_are_REJECTED(bad):
    """THE POINT OF VALIDATING. `source_ref` already holds a position_id and a file path; a
    third free-form value would give the column a FOURTH vocabulary, which is the fault being
    closed rather than a new one to add."""
    assert not re.fullmatch(SRC_RE, bad)


def test_the_route_validates_the_shape_and_says_what_it_wanted():
    code = function_code(PORTFOLIO, "log_cash_flow")
    assert "fullmatch" in code
    assert "Convention #44" in code or "source_ref must be" in code
    assert "400" in code


# ── (e)3 dedup keys on source_ref ───────────────────────────────────────────

def test_a_key_is_computed_ONLY_when_there_is_a_source_ref():
    """Without an attribution the key stays NULL, which sits outside the partial unique index
    and refuses nothing -- losing a real movement is worse than repeating one. That is the
    existing rule in `_adjust_account_cash_with_conn`, kept here."""
    code = function_code(PORTFOLIO, "log_cash_flow")
    assert "dedup_key(" in code
    assert "if src else None" in code


def test_three_same_day_same_amount_lines_stay_DISTINCT():
    """HYG 516's three 24.91 orders are three different broker lines. Keying on <sha12>:L<n>
    makes them three keys; keying on amount+date alone would collapse them to one and lose
    49.82."""
    from services.cash_ledger import dedup_key
    from datetime import date
    keys = {dedup_key("ROBINHOOD", "TRADE_CREDIT", 24.91, date(2026, 10, 15),
                      "7c6ce1831b13:L%d" % n) for n in (8, 10, 12)}
    assert len(keys) == 3, "three distinct broker lines must produce three distinct keys"


def test_the_same_broker_line_twice_produces_ONE_key():
    """The other half: re-posting the same line must dedup, or a retry double-counts."""
    from services.cash_ledger import dedup_key
    from datetime import date
    a = dedup_key("ROBINHOOD", "TRADE_CREDIT", 24.91, date(2026, 10, 15), "7c6ce1831b13:L8")
    b = dedup_key("ROBINHOOD", "TRADE_CREDIT", 24.91, date(2026, 10, 15), "7c6ce1831b13:L8")
    assert a == b


def test_a_conflict_is_reported_as_already_present_not_as_a_failure():
    """An INSERT that conflicts means the line is already in the ledger. Returning a bare error
    would send a caller into a retry loop, or make them conclude the write was lost -- and the
    id-191 gap is what that looks like afterwards."""
    code = function_code(PORTFOLIO, "log_cash_flow")
    assert "already_present" in code
    assert "ON CONFLICT" in code


def test_the_route_still_refuses_to_report_a_write_that_did_not_land():
    """The pre-existing guard: a RETURNING that yields nothing is not a success with an empty
    body. It must survive the new conflict branch."""
    code = function_code(PORTFOLIO, "log_cash_flow")
    assert "was not written" in code


# ── the ledger is not mutated by this route ─────────────────────────────────

def test_the_route_still_does_not_touch_the_stored_total():
    """R-IV.548(c): `account_balances.cash` is under replacement, and a route that both appends
    an event and edits the total leaves two figures free to disagree."""
    code = function_code(PORTFOLIO, "log_cash_flow")
    assert "UPDATE account_balances" not in code
    assert "balance_adjusted" in code


# ── R-IV.1148(d)1: source_ref may be COMPLETED, never REPLACED ──────────────

def test_the_correction_route_accepts_source_ref():
    from api.portfolio import CashFlowCorrection
    assert "source_ref" in CashFlowCorrection.model_fields
    assert CashFlowCorrection.model_fields["source_ref"].default is None


def test_setting_source_ref_over_an_EXISTING_value_is_REFUSED():
    """The identity rule the route's own docstring states, kept. COMPLETING an identity that was
    never written is a different act from REPLACING one; an overwrite would make the row a
    different event wearing this id. Refused with 409, not silently ignored -- a caller who
    believes they relabelled a row and did not carries a wrong belief into the next
    reconciliation."""
    code = function_code(PORTFOLIO, "correct_cash_flow")
    i = code.index("already has a source_ref")
    window = code[max(0, i - 500):i + 200]
    assert "before['source_ref'] is not None" in window or 'before["source_ref"] is not None' in window
    assert "409" in window


def test_filling_source_ref_writes_an_AUDIT_ROW():
    """Every corrected column gets a row in cash_flow_corrections, in the SAME transaction. A
    correction whose audit row could be lost separately is not an audited correction."""
    code = function_code(PORTFOLIO, "correct_cash_flow")
    i = code.index("changes = []")
    window = code[i:i + 500]
    assert "'source_ref'" in window or '"source_ref"' in window
    assert "cash_flow_corrections" in code


def test_filling_source_ref_CREATES_the_dedup_key_the_row_lacked():
    """The key is derived from source_ref, so filling one gives a previously unkeyed row its
    dedup protection. Without this the line stays re-postable forever."""
    code = function_code(PORTFOLIO, "correct_cash_flow")
    assert "src_final" in code
    i = code.index("new_key = dedup_key")
    assert "or new_src" in code[i:i + 320]


def test_the_corrected_row_actually_stores_source_ref():
    code = function_code(PORTFOLIO, "correct_cash_flow")
    assert "source_ref = $5" in code


def test_source_ref_alone_is_enough_to_correct():
    """Previously the route refused unless amount or activity_date was given. Filling only the
    source_ref is a legitimate correction and must not be rejected as "nothing to correct"."""
    code = function_code(PORTFOLIO, "correct_cash_flow")
    assert "body.source_ref is None" in code


# ── R-IV.1148(d)2: the broker Amount on the OPEN ────────────────────────────

def test_create_request_accepts_cost_and_source_ref():
    from api.unified_positions import CreatePositionRequest
    for f in ("cost", "source_ref"):
        assert f in CreatePositionRequest.model_fields, f
        assert CreatePositionRequest.model_fields[f].default is None


def test_an_open_still_works_with_no_cost():
    from api.unified_positions import CreatePositionRequest
    r = CreatePositionRequest(ticker="SPY", entry_price=10.0)
    assert r.cost is None and r.source_ref is None


def test_cost_is_preferred_and_its_SIGN_comes_from_the_STRUCTURE():
    """A credit structure is PAID on open, so the direction is the structure's to decide. Taking
    the caller's sign would let a negative `cost` invert a position's cash."""
    code = function_code(POSITIONS, "create_position")
    i = code.index("exact_from_broker")
    window = code[max(0, i - 500):i + 500]
    assert "req.cost is not None" in window
    assert "abs(float(req.cost))" in window
    assert "CREDIT_STRUCTURES" in window


def test_the_open_records_which_source_it_used():
    code = function_code(POSITIONS, "create_position")
    assert "exact_from_broker" in code
    assert "derived_from_cost_basis" in code


def test_the_open_validates_source_ref_and_keeps_the_position_link():
    """With a broker line supplied it becomes the event's source_ref, so the position_id moves
    into the description -- NEITHER link is lost."""
    code = function_code(POSITIONS, "create_position")
    assert "fullmatch" in code
    assert "_src or position_id" in code
    i = code.index("position opened")
    assert "position_id" in code[i:i + 240]
