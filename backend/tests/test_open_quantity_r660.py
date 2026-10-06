"""#29 everywhere: `quantity` is the size opened, `open_quantity` is what is still open.

R-IV.660(b). Convention #29 names two figures and the payload served only one of them, so every
consumer asking "how big is this position right now" was answered with the size it had been
OPENED at. While a partial close shrank `quantity`, that answer was right by accident.
R-IV.657(c) correctly stopped the shrinking -- and in doing so turned a latent ambiguity into a
live overstatement on every partially-closed row, plus one outright regression in the close path
itself (see TestTheCloseDecisionIsAgainstWhatIsHeld).

Measured on the live book 2026-10-06: all 28 open rows have lots, exactly ONE open row
(`POS_HYG_20260922_203634_L2`, HYG: 5 opened, 2 closed, 3 held) has a remainder below its opened
size, and 519 of 519 closed rows already agree with #29.
"""

import ast
import io
import os

from models.position_lots import open_remainder, size_opened
from services.open_quantity import (BASIS_LOTS, BASIS_NO_LOTS, BASIS_NOT_OPEN,
                                    open_quantity_of)
from services.position_economics import open_remainder as policy_remainder

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# HYG L2 and NVDA 702, exactly as the principal traded them.
HYG_LOTS = [{"qty": 5.0, "price": 1.0}, {"qty": -2.0, "price": 1.2}]
NVDA_702_LOTS = [{"qty": 5.0}, {"qty": -2.0}, {"qty": -1.0}, {"qty": -2.0}]
ADD_THEN_PARTIAL = [{"qty": 3.0}, {"qty": 2.0}, {"qty": -1.0}]


def _code(rel):
    """Live code only: docstrings and comment lines removed, so a structural assertion
    cannot be satisfied by a comment that merely mentions the right words."""
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "".join(l for l in src.splitlines(keepends=True)
                   if not l.strip().startswith("#"))


# --------------------------------------------- the two figures, and that they differ

class TestTheTwoFigures:
    def test_the_size_opened_excludes_disposals(self):
        assert size_opened(NVDA_702_LOTS) == 5.0
        assert size_opened(HYG_LOTS) == 5.0

    def test_the_remainder_subtracts_them(self):
        assert open_remainder(NVDA_702_LOTS) == 0.0
        assert open_remainder(HYG_LOTS) == 3.0

    def test_an_add_counts_toward_the_size_opened(self):
        """#29 says "adds included": 3 opened, 2 added, 1 closed is a 5-contract position."""
        assert size_opened(ADD_THEN_PARTIAL) == 5.0
        assert open_remainder(ADD_THEN_PARTIAL) == 4.0

    def test_the_figures_actually_differ_on_a_live_row(self):
        """POSITIVE CONTROL. A field that always equalled `quantity` would be
        indistinguishable from it, and every test here would pass against a payload that
        simply served the wrong figure twice. HYG L2 is the live row where they diverge."""
        assert size_opened(HYG_LOTS) != open_remainder(HYG_LOTS)


class TestOneArithmeticAuthor:
    """The addition exists ONCE. It had three expressions and two of them disagreed."""

    def test_the_policy_layer_delegates_the_addition(self):
        src = _code("services/position_economics.py")
        i = src.index("def open_remainder")
        j = src.index("\ndef ", i + 10)
        body = src[i:j]
        assert "_sum_qty(lots)" in body, (
            "the policy layer must delegate the addition, not perform its own")
        assert "total += q" not in body, "a second summation loop is a second author"

    def test_derive_aggregate_does_not_sum_qty_itself(self):
        src = _code("models/position_lots.py")
        i = src.index("def derive_aggregate")
        j = src.index("\ndef ", i + 10)
        body = src[i:j]
        assert "qty = open_remainder(lots)" in body

    def test_the_two_agree_wherever_a_figure_exists(self):
        for lots in (NVDA_702_LOTS, HYG_LOTS, ADD_THEN_PARTIAL):
            assert float(policy_remainder(lots)) == open_remainder(lots)

    def test_and_differ_only_where_the_policy_refuses_a_figure(self):
        """The disagreement that mattered: the primitive answers 0 for an empty lot set, the
        policy answers None. Zero is a FLAT position; None is an UNKNOWN one, and they license
        opposite decisions. Both answers are kept, each in the layer that should give it."""
        assert open_remainder([]) == 0
        assert policy_remainder([]) is None
        assert policy_remainder([{"qty": 5.0}, {"qty": None}]) is None


# --------------------------------------------- the served field

class TestOpenQuantityOf:
    def test_lots_present_serves_the_remainder(self):
        assert open_quantity_of({"status": "OPEN"}, HYG_LOTS) == {
            "open_quantity": 3.0, "open_quantity_basis": BASIS_LOTS}

    def test_no_lots_on_an_open_row_is_unknown_not_the_stored_quantity(self):
        """Substituting `quantity` would assert a remainder the book has no record of, and a
        never-lotted row is exactly the row whose size is least trustworthy. Zero would be
        worse still: it reads as a flat position, which is the opposite fact."""
        got = open_quantity_of({"status": "OPEN", "quantity": 5.0}, [])
        assert got["open_quantity"] is None
        assert got["open_quantity_basis"] == BASIS_NO_LOTS

    def test_a_closed_row_holds_nothing(self):
        got = open_quantity_of({"status": "CLOSED"}, NVDA_702_LOTS)
        assert got["open_quantity"] == 0.0
        assert got["open_quantity_basis"] == BASIS_NOT_OPEN

    def test_a_terminal_row_whose_lots_disagree_says_so(self):
        """POSITIVE CONTROL for the contradiction, not just the figure. 5 EXPIRED rows on the
        live book have a full remainder because the expiry was never lotted as a disposal. The
        figure is 0 -- an expired position holds nothing -- but the basis NAMES the lot gap
        rather than resolving it silently."""
        got = open_quantity_of({"status": "EXPIRED"}, [{"qty": 5.0}])
        assert got["open_quantity"] == 0.0
        assert "5.0" in got["open_quantity_basis"]
        assert "never lotted" in got["open_quantity_basis"]

    def test_a_retired_duplicate_counts_nothing(self):
        assert open_quantity_of({"status": "DUPLICATE_OF"},
                                [{"qty": 5.0}])["open_quantity"] == 0.0


class TestTheFigureIsNotStored:
    def test_no_open_quantity_column_is_written(self):
        """A column would be a fourth writer of something the lots already say, and it would
        be wrong for as long as it took one lot to be added without it."""
        src = _code("api/unified_positions.py")
        assert "SET open_quantity" not in src
        assert "ADD COLUMN open_quantity" not in _code("database/postgres_client.py")


# --------------------------------------------- #29 on the write paths

class TestReduceLeavesQuantityAtTheSizeOpened:
    def test_the_reduce_path_writes_the_size_opened(self):
        """Anchored to the UPDATE's FIRST ARGUMENT, not to the name appearing anywhere in the
        route. The first version of this test asserted only that `size_opened(...)` occurred
        somewhere in the body -- which the response dict below also satisfies, so reverting the
        UPDATE to `stored_qty` left the test green. A mutation run caught it. An assertion that
        cannot fail when the thing it guards is removed is not evidence of anything."""
        src = _code("api/unified_positions.py")
        i = src.index("async def reduce_position")
        body = src[i:src.index("\nclass ", i)]
        stmt = body[body.index("UPDATE unified_positions"):]
        stmt = stmt[:stmt.index("position_id)") + len("position_id)")]
        assert "SET quantity = $1" in stmt
        assert "size_opened([dict(r) for r in remaining])" in stmt, (
            "/reduce must store the size opened, not the remainder")
        assert "stored_qty," not in stmt, "stored_qty is the REMAINDER"

    def test_and_serves_both_figures_in_its_response(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def reduce_position")
        body = src[i:src.index("\nclass ", i)]
        assert '"open_quantity_after"' in body
        assert '"size_opened"' in body

    def test_the_lots_add_path_writes_the_size_opened(self):
        """POSITIVE CONTROL. `/lots` ALSO writes `quantity = stored_qty`, and that is CORRECT --
        #29 says adds are included. A fix that changed every `quantity =` write would have
        broken it, and this is what tells the two writes apart."""
        src = _code("api/unified_positions.py")
        assert "stored_qty" in src

    def test_the_legacy_add_path_keeps_the_size_opened_and_scales_legs_to_the_remainder(self):
        """A THIRD write path, found while tracing the trade date. The add-to-existing branch
        set `quantity` from `derive_aggregate(...)["qty"]` -- the open REMAINDER -- so adding to
        a partially-closed position would have stored remainder-plus-add and the row would have
        forgotten how big it had been.

        The two figures are now tracked apart in that branch, because the legs genuinely need
        the remainder (the R-IV.517(c) trigger refuses the commit otherwise) while the row needs
        the size opened. One variable serving both was the whole fault."""
        src = _code("api/unified_positions.py")
        body = src[src.index("async def create_position"):src.index("\n@router", src.index(
            "async def create_position"))]
        assert "new_qty = size_opened(_lot_rows)" in body
        assert 'remainder_qty = agg["qty"]' in body
        assert "_scale_legs_to_remainder(conn, pos_id, float(remainder_qty))" in body
        assert "_scale_legs_to_remainder(conn, pos_id, float(new_qty))" not in body


class TestTheCloseDecisionIsAgainstWhatIsHeld:
    """THE REGRESSION R-IV.657(c) INTRODUCED, and the reason the census was necessary.

    The close path decided partial-vs-full with `total_qty = float(pos["quantity"])`, which was
    correct only while a partial close shrank the column. Once `quantity` became the size opened:

      * closing the REST of a partially-closed position (3 left of 5 opened) computed
        `is_partial = 3 < 5` -> True, so the position would be emptied and still left OPEN;
      * a close with no quantity defaulted to 5 and tried to dispose of lots that are not there.
    """

    def test_the_decision_reads_the_remainder(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def close_position")
        body = src[i:src.index("\n@router", i)]
        assert "_open_remainder(_lots_now)" in body
        assert "total_qty = float(_rem)" in body

    def test_the_remainder_is_read_before_the_decision_is_taken(self):
        """The ordering fault this work already hit once: the lots were read at the bottom of
        the route and the decision taken at the top."""
        src = _code("api/unified_positions.py")
        i = src.index("async def close_position")
        body = src[i:src.index("\n@router", i)]
        assert body.index("_open_remainder(_lots_now)") < body.index("is_partial = close_qty")

    def test_the_basis_of_the_decision_reaches_the_caller(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def close_position")
        body = src[i:src.index("\n@router", i)]
        assert '"closed_against_basis": total_qty_basis' in body

    def test_a_lotless_row_can_still_be_closed(self):
        """POSITIVE CONTROL. The remainder is unknown for a row with no lots, and refusing to
        close it would strand exactly the rows the lots trigger already exempts. `quantity` is
        the only size available there, and it is substituted KNOWINGLY, with a basis."""
        src = _code("api/unified_positions.py")
        i = src.index("async def close_position")
        body = src[i:src.index("\n@router", i)]
        assert 'total_qty = float(pos["quantity"] or 0)' in body
        assert "position has no lots" in body


# --------------------------------------------- every payload serves it

class TestEveryPayloadServesIt:
    def test_attach_economics_stamps_it_for_the_list_route_and_the_mcp(self):
        """Stamped in the ONE function where a lot-derived figure reaches a position dict --
        both the positions API and the read-only service the MCP tools read pass through it."""
        assert "stamp_open_quantity_from_lots" in _code("services/read_only/positions.py")

    def test_the_single_position_route_serves_it(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def get_position(")
        assert "stamp_open_quantity" in src[i:src.index("\n@router", i)]

    def test_the_summary_route_serves_it(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def portfolio_summary")
        body = src[i:src.index("\n@router", i)]
        assert "stamp_open_quantity" in body
        assert '"open_quantity": p.get("open_quantity")' in body

    def test_the_touches_block_serves_it(self):
        from models.position_direction import touches_block

        block = touches_block(
            {"position_id": "POS_HYG", "structure": "long_call", "account": "ROBINHOOD",
             "open_quantity": 3.0, "open_quantity_basis": BASIS_LOTS}, "BULLISH")
        assert block["open_quantity"] == 3.0
        assert block["open_quantity_basis"] == BASIS_LOTS

    def test_the_touches_query_selects_the_status_it_reads(self):
        """A figure that silently depends on a column being ABSENT is the shape this
        function's own comment warns about, so `status` is SELECTed although WHERE fixes it."""
        src = _code("signals/feed_service.py")
        i = src.index("async def open_positions_by_ticker")
        body = src[i:src.index("\ndef ", i)]
        assert "structure, account, status" in body
        assert "stamp_open_quantity" in body

    def test_the_mcp_tool_serves_both_fields(self):
        src = _code("hub_mcp/tools/positions.py")
        assert '"open_quantity": row.get("open_quantity")' in src
        assert '"quantity": row.get("quantity")' in src

    def test_the_mcp_description_teaches_the_difference(self):
        """The committee reads these descriptions and nothing else. A field served without an
        account of which question it answers is a field that will be read for the other one."""
        from hub_mcp.tools.positions import DESCRIPTION

        assert "open_quantity" in DESCRIPTION
        assert "size the position was OPENED at" in DESCRIPTION
        assert "STILL OPEN" in DESCRIPTION
        assert "overstates" in DESCRIPTION
        assert "UNKNOWN" in DESCRIPTION


# --------------------------------------------- the census

class TestTheCensusedReaders:
    def test_the_legacy_valuation_values_what_is_held(self):
        src = _code("api/portfolio.py")
        i = src.index("def _v2_to_legacy_dict")
        body = src[i:src.index("\n@router", i)]
        assert 'qty = d.get("open_quantity")' in body
        assert 'qty = float(d.get("quantity") or 0)' not in body

    def test_an_unknown_remainder_yields_no_value_at_all(self):
        import api.portfolio as portfolio

        row = {"structure": "long_call", "asset_type": "OPTION", "current_price": 2.0,
               "quantity": 5, "open_quantity": None, "short_strike": None}
        assert portfolio._v2_to_legacy_dict(row)["current_value"] is None

    def test_and_the_remainder_is_valued_when_it_is_known(self):
        import api.portfolio as portfolio

        row = {"structure": "long_call", "asset_type": "OPTION", "current_price": 2.0,
               "quantity": 5, "open_quantity": 3.0, "short_strike": None}
        d = portfolio._v2_to_legacy_dict(row)
        assert d["current_value"] == 600.0, "3 held x 2.00 x 100, not 5 x 2.00 x 100"
        assert d["quantity_opened"] == 5

    def test_the_mark_job_marks_the_remainder(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def run_mark_to_market")
        body = src[i:src.index("\n@router", i)]
        assert "_open_rem(lots_by_position.get" in body
        assert "quantity = float(_rem)" in body

    def test_the_summary_market_value_uses_the_remainder(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def portfolio_summary")
        body = src[i:src.index("\n@router", i)]
        assert 'oq = p.get("open_quantity")' in body
        assert "cost = ep * float(oq) * 100" in body

    def test_the_loss_alert_already_read_lots(self):
        """Censused and CLEAN -- recorded so the next census does not re-derive it."""
        assert "SUM(qty)" in _code("jobs/loss_alert.py")

    def test_the_account_value_and_ceiling_base_already_read_lots(self):
        """`market_value = mark x REMAINDER x multiplier` in position_economics, which
        `account_value` sums and the sleeve ceiling's base reads. Clean, and recorded."""
        assert "value = m * rem * mult" in _code("services/position_economics.py")


class TestTheCoverageInvariantTestsSomethingThatCanHold:
    """An alarm that cannot be cleared is an alarm nobody reads.

    `get_lots_coverage` asserted `SUM(lot qty) == row quantity`. #29 makes those deliberately
    different on every partially-closed position, so on the live book that test flagged 547
    correct rows and `holds` could never read true again. The invariant that does hold is
    `SUM(qty WHERE qty > 0) == quantity`; measured 2026-10-06 it flags exactly ONE row, the
    HYG artifact of the unfixed /reduce.
    """

    def test_the_rollup_compares_the_opened_sum(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def get_lots_coverage")
        body = src[i:src.index("\nclass ", i)]
        assert "a.opened <> p.quantity" in body
        assert "a.lot_qty <> p.quantity" not in body

    def test_the_remainder_is_reported_as_its_own_figure(self):
        src = _code("api/unified_positions.py")
        i = src.index("async def get_lots_coverage")
        assert "AS partially_closed" in src[i:src.index("\nclass ", i)]

    def test_the_stated_invariant_matches_the_test(self):
        """A surface whose sentence and SQL drift apart is worse than one testing nothing."""
        src = _code("api/unified_positions.py")
        i = src.index("async def get_lots_coverage")
        body = src[i:src.index("\nclass ", i)]
        assert "SUM(lot qty WHERE qty > 0) == row" in body
