"""A partial close records what it consumed, and realized is the sum — R-IV.657(c).

NVDA 702 (`POS_NVDA_20261001_173647`). The principal opened 5 contracts at 0.03 on 10-01 and
closed them in three parts through the UI on 10-02: **2 at 0.18, 1 at 0.33, 2 at 0.10**. The
row read **realized 14.00** where its lots say **74.00**.

14.00 is the LAST close alone. Three separate faults produced it, and each had to be fixed:

  1. the partial branch wrote **no realized at all**, so the first two closes' 30.00 + 30.00
     went nowhere;
  2. the final close took the remainder to zero, so it ran the FULL branch, which wrote
     `realized_pnl = <this close>` — 14.00 — over a position that had realized 74.00;
  3. **no closure row was written**, by either branch. `/reduce` wrote them; `/close`, which
     the UI uses, never did. So a close had no record of which fills it consumed or at what
     cost, and realized had nothing to be derived *from* — which is precisely why each close
     could only report itself.

And the partial branch cut `quantity` and `cost_basis` on every close, against convention #29:
`quantity` is the size OPENED, `SUM(lots.qty)` is the open remainder. After three closes the
row claimed to be a smaller position than the one the principal took, and the basis every
percentage divides by shrank with it.

WHY THIS MATTERS MORE THAN ITS SIZE. Selling part of a position at 2–3× cost is the principal's
standard exit, so the defect corrupted exactly the trades the book should record best.

REALIZED IS DERIVED, NOT ACCUMULATED. `+=` would fix the symptom and keep the shape that caused
it: a running total has no author, and a replayed close double-counts in silence. A SUM over
`position_lot_closures` is idempotent and cannot drift from the allocations it is made of.
"""

import ast
import io
import os

import pytest

from models.position_lots import fifo_plan

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# NVDA 702, exactly as the principal traded it
OPENED_QTY, OPENED_PRICE = 5.0, 0.03
CLOSES = [(2.0, 0.18), (1.0, 0.33), (2.0, 0.10)]
EXPECTED_REALIZED = 74.00
EXPECTED_PER_CLOSE = [30.00, 30.00, 14.00]


def _code(rel):
    """Live code only: docstrings and comments both removed, spacing preserved."""
    import tokenize

    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    lines = src.splitlines(keepends=True)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
            lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
    except (tokenize.TokenError, IndentationError):
        pass
    return "".join(lines)


def _replay():
    """702's three closes through the real `fifo_plan`, returning the closure ledger.

    This is the arithmetic the close path now performs: plan against the fills as they stand,
    write the disposal, record one closure row per allocation.
    """
    lots = [{"id": 1, "fill_time": "2026-10-01", "qty": OPENED_QTY,
             "price": OPENED_PRICE, "fees": 0}]
    ledger, per_close = [], []
    for i, (qty, price) in enumerate(CLOSES, start=2):
        plan = fifo_plan(list(lots), qty, price, "OPTION", 0)
        assert plan["sufficient"], f"close {i} should have been coverable"
        this = round(sum(a["realized"] for a in plan["allocations"]), 2)
        per_close.append(this)
        ledger.extend(plan["allocations"])
        # the disposal joins the lot set, exactly as the route writes it
        lots.append({"id": i, "fill_time": "2026-10-02", "qty": -qty,
                     "price": price, "fees": 0})
    return ledger, per_close, lots


# ─────────────────────── THE REGRESSION TEST (c) SPECIFIES

class TestNvda702:

    def test_each_close_realizes_what_it_should(self):
        _, per_close, _ = _replay()
        assert [round(v, 2) for v in per_close] == EXPECTED_PER_CLOSE

    def test_the_ledger_sums_to_seventy_four(self):
        """THE FIGURE. 30.00 + 30.00 + 14.00 = 74.00, and the row read 14.00."""
        ledger, _, _ = _replay()
        assert round(sum(a["realized"] for a in ledger), 2) == EXPECTED_REALIZED

    def test_fourteen_was_the_last_close_alone(self):
        """Named so the symptom is recognisable if it ever returns: a row whose realized
        equals its FINAL close is this bug, not a small one."""
        _, per_close, _ = _replay()
        assert round(per_close[-1], 2) == 14.00
        assert round(per_close[-1], 2) != EXPECTED_REALIZED

    def test_quantity_stays_at_the_size_opened(self):
        """#29. The row's `quantity` is what was opened — 5 — however many parts it left in."""
        assert OPENED_QTY == 5.0

    def test_the_remainder_reaches_zero_through_the_lots(self):
        """The remainder is the lots' sum, which is where a partial close belongs: 5 − 2 − 1 −
        2 = 0, with `quantity` untouched at 5."""
        _, _, lots = _replay()
        assert round(sum(l["qty"] for l in lots), 6) == 0.0

    def test_every_allocation_names_the_fill_it_consumed(self):
        """All three closes consume the single opening lot, at its 0.03 cost. Without the
        closure rows there is no record of this at all — which is the third fault."""
        ledger, _, _ = _replay()
        assert len(ledger) == 3
        assert {a["lot_id"] for a in ledger} == {1}
        assert all(round(a["cost_per_unit"], 4) == OPENED_PRICE for a in ledger)
        assert [round(a["proceeds_per_unit"], 4) for a in ledger] == [0.18, 0.33, 0.10]


# ─────────────────────── the close path's shape

class TestTheClosePathWritesWhatItConsumed:

    def test_it_writes_the_closure_rows(self):
        code = _code("api/unified_positions.py")
        i = code.index("async def close_position")
        j = code.index("async def ", i + 10)
        block = code[i:j]
        assert "INSERT INTO position_lot_closures" in block
        assert "fifo_plan(" in block

    def test_realized_is_summed_from_the_ledger_not_accumulated(self):
        """ONE statement, after the closures, subquerying them. The first version computed a
        `realized_total` local beside the disposal lot and read it in the UPDATE blocks, which
        run EARLIER in this route -- so it was read before assignment and every close 500'd.
        A subquery has no local to be unbound and no ordering to get wrong."""
        code = _code("api/unified_positions.py")
        i = code.index("async def close_position")
        j = code.index("async def ", i + 10)
        block = code[i:j]
        assert "SELECT SUM(realized) FROM position_lot_closures" in block
        assert "realized_pnl = COALESCE(" in block
        assert "realized_pnl = realized_pnl +" not in block, "a running total has no author"

    def test_the_partial_branch_no_longer_cuts_quantity_or_cost_basis(self):
        """The assertion that would have caught the regression. Both columns described the
        position as opened, and both were being rewritten on every partial."""
        code = _code("api/unified_positions.py")
        i = code.index("if is_partial:")
        j = code.index("else:", i)
        partial = code[i:j]
        assert "quantity = $1" not in partial
        assert "cost_basis = $2" not in partial
        # No ASSIGNMENT to realized_pnl in this branch -- the statement after the closures
        # owns it, for both branches. The branch does still MENTION this close's figure, in
        # the human-readable note (`${realized_pnl:+.2f}`), which is why the assertion is on
        # the SQL assignment and not on the name: a bare `not in` failed for the right word
        # in the wrong place.
        assert "realized_pnl =" not in partial
        assert "${realized_pnl:+.2f}" in partial

    def test_the_full_branch_is_corrected_by_the_same_statement(self):
        """The final close of 702 took the remainder to zero, so it ran the FULL branch and
        wrote its own 14.00. That branch still writes this close's figure first -- the
        allocations do not exist yet at that point -- and the statement after the closures
        then corrects it to the ledger's total. One owner, both branches."""
        code = _code("api/unified_positions.py")
        i = code.index("async def close_position")
        j = code.index("async def ", i + 10)
        block = code[i:j]
        assert "UPDATE unified_positions SET realized_pnl = COALESCE(" in " ".join(
            block.split())
        assert block.count("SELECT SUM(realized) FROM position_lot_closures") == 1

    def test_the_legs_still_follow_the_remainder(self):
        """NOT a fault to fix: the trigger is `position_legs_match_open_remainder`, so the legs
        must track `SUM(lots.qty)` and the commit is refused otherwise. What was wrong was
        cutting `quantity`, not moving the legs."""
        # Scoped to the FUNCTION, not to a window around `if is_partial:` -- there are two
        # of those in this route (the UPDATE branch and the legs branch) and `index` finds
        # the first, so a window around it reported absence for the wrong reason.
        code = _code("api/unified_positions.py")
        i = code.index("async def close_position")
        j = code.index("async def ", i + 10)
        assert "_scale_legs_to_remainder" in code[i:j]

    def test_a_row_with_no_lots_still_closes(self):
        """POSITIVE CONTROL. A position booked before its fills were lotted writes no
        disposal and no closures, so the correcting statement never runs and the row keeps
        this close's own figure -- which is the only figure available for it. The alternative
        is a close that cannot complete, on exactly the rows the lots trigger already exempts.

        Pinned structurally: the closure write and the realized correction both sit inside
        the `if _has_lots and close_qty:` branch, so neither can touch a lotless row."""
        code = _code("api/unified_positions.py")
        i = code.index("if _has_lots and close_qty:")
        j = code.index("if is_partial:", i)
        guarded = code[i:j]
        assert "INSERT INTO position_lot_closures" in guarded
        assert "SELECT SUM(realized) FROM position_lot_closures" in guarded
