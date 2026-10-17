"""R-IV.1183(b) — `unrealized_pnl` and `max_loss` are DERIVED, and the gates that rested on it.

WHY THEY WERE MISLABELLED, and how the payload proved it. `hub_get_positions` reads
`list_positions`, which calls `attach_economics` (R-IV.526(b)). That function REPLACES both
fields with the figure the row's lots support and moves the table's own value to
`unrealized_pnl_stored` / `max_loss_stored`. So by the time the tool serialises a row, neither
field holds what the book stores — and the live payload read on 2026-10-16 carried
`"unrealized_pnl":"stored"` beside a `22.86` computed from lots.

Under #42 a STORED label is what GRANTS gating (`GATEABLE = {STORED, GATEABLE_BY_RULING}`), so
the wrong label did not merely misdescribe these fields: it licensed caps and gates on them.

THE TESTS BELOW ARE IN TWO HALVES. The first pins the labels and the refusal. The second pins
the census R-IV.1183(b) asked for — the gates, checks and alerts that read either field —
because a census that lives only in a report rots, and the most important entry in it is a
breach that is still open:

    analytics/api.py `can_open_new` gates opening a new crypto position on
    `breakout_remaining_dd > 250`, where that figure is the drawdown limit MINUS A SUM OF
    `max_loss` — the sum R-IV.207(d) already forbids.

Those tests assert the breach EXISTS, so they fail the day someone fixes it and the fix cannot
land silently without this file being read.
"""
from __future__ import annotations

import io
import os
import re

import pytest

from hub_mcp import field_origin as fo

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = "hub_get_positions"
MONEY = ("unrealized_pnl", "max_loss")


def _src(rel: str) -> str:
    return io.open(os.path.join(BACKEND, rel), encoding="utf-8", errors="replace").read()


# ── 1. the labels, and what the label controls ───────────────────────────────

@pytest.mark.parametrize("field", MONEY)
def test_the_field_is_declared_DERIVED(field):
    assert fo.origin_of(TOOL, field) == fo.DERIVED


@pytest.mark.parametrize("field", MONEY)
def test_no_gate_may_rest_on_it(field):
    """The label is not decoration. `GATEABLE = {STORED, GATEABLE_BY_RULING}`, so STORED was
    granting permission to cap, gate and filter on a computed figure."""
    ok, why = fo.may_gate(TOOL, field)
    assert ok is False
    assert "DERIVED" in why


@pytest.mark.parametrize("field", MONEY)
def test_the_declaration_carries_its_reason(field):
    """A relabel with no stated cause invites the next reader to relabel it back."""
    note = fo.NOTES.get((TOOL, field))
    assert note, "no NOTES entry for %s" % field
    assert "attach_economics" in note or "lots" in note
    assert "R-IV.1183(b)" in note


@pytest.mark.parametrize("field", MONEY)
def test_neither_is_quietly_exempted_by_ruling(field):
    """GATEABLE_BY_RULING is the one way a derived field becomes gateable, and it requires a
    named ruling. Neither of these has one, and neither should acquire one by accident."""
    assert fo.origin_of(TOOL, field) != fo.GATEABLE_BY_RULING


def test_the_tool_does_not_serve_a_stored_sibling_to_point_readers_at():
    """There is no `unrealized_pnl_stored` in this tool's payload, so DERIVED is not hiding a
    gateable alternative — within this tool the derived figure IS the field. Stated because the
    obvious next question is "then what may I gate on?", and the answer is: neither, here."""
    declared = fo.origin_map(TOOL)
    assert "unrealized_pnl_stored" not in declared
    assert "max_loss_stored" not in declared


def test_the_relabel_is_consistent_with_what_the_code_does():
    """The claim is about behaviour, not opinion: `attach_economics` must actually overwrite
    both fields. If it ever stopped, the label would be wrong in the other direction."""
    src = _src(os.path.join("services", "read_only", "positions.py"))
    assert 'p["max_loss"] = e["max_loss"]' in src
    assert 'p["unrealized_pnl"] = e["unrealized_pnl"]' in src
    assert 'p["max_loss_stored"] = p.get("max_loss")' in src
    assert 'p["unrealized_pnl_stored"] = p.get("unrealized_pnl")' in src


def test_the_mcp_tool_really_does_go_through_that_function():
    """The label belongs to the tool, so the tool's own path is what makes it true."""
    assert "list_positions" in _src(os.path.join("hub_mcp", "tools", "positions.py"))
    assert "attach_economics" in _src(os.path.join("api", "unified_positions.py"))


# ── 2. the census R-IV.1183(b) asked for, pinned so it cannot rot ────────────

def test_THE_OPEN_BREACH_a_gate_is_computed_from_a_SUM_of_max_loss():
    """`can_open_new` decides whether a new crypto position may be opened, and it rests on
    `breakout_remaining_dd > 250`, where that figure is the static drawdown limit MINUS a sum
    of `max_loss`.

    Two rules broken at once: #42 (a gate on a derived field) and R-IV.207(d), which forbids
    summing `max_loss` at all — the stored column carried the wrong scope on ten of seventeen
    lotted open rows, understating the total by $632.08 on 2026-09-24.

    THIS TEST ASSERTS THE BREACH EXISTS. It fails the day it is fixed, which is the point: the
    fix is a ruling (it changes who may open a position), and it must not land silently.
    """
    src = _src(os.path.join("analytics", "api.py"))
    assert "breakout_remaining_dd = breakout_static_dd - crypto_max_loss" in src
    assert "breakout_remaining_dd > 250" in src
    assert 'sum(abs(float(p["max_loss"]))' in src, (
        "if this sum is gone the breach may be fixed — re-read R-IV.1183(b) before deleting "
        "this test")


def test_the_breaching_route_reads_the_RAW_column_not_the_derived_one():
    """It runs its own SELECT and never calls `attach_economics`, so it gets the stored column
    — which is the wrong-scope figure gap 1 exists to replace. The gate is wrong twice over,
    and relabelling the MCP field does not touch it."""
    src = _src(os.path.join("analytics", "api.py"))
    i = src.index("breakout_remaining_dd = breakout_static_dd")
    window = src[max(0, i - 4000):i]
    assert "attach_economics" not in window


def test_portfolio_summary_also_sums_the_raw_column():
    """A second aggregate on the stored column, in the route the dashboard reads. Not a gate —
    it is served as a total with an `is_partial` flag — so it is recorded, not asserted as a
    breach."""
    src = _src(os.path.join("api", "unified_positions.py"))
    assert 'total_max_loss = sum(float(p["max_loss"])' in src
    assert "max_loss_unknown_count" in src


def test_the_loss_alert_still_refuses_BOTH_fields():
    """THE MODEL TO FOLLOW, and the strongest entry in the census. The Roth loss alert was
    written knowing these columns carry the wrong scope: its docstring names them, its SQL
    names neither, and that is what keeps an alert from inheriting the fault it exists to
    catch. A loss alert that under-reads a loss by half is worse than no alert."""
    src = _src(os.path.join("jobs", "loss_alert.py"))
    i = src.index("POSITION_SQL")
    sql = src[i:src.index('"""', src.index('"""', i) + 3)]
    assert "max_loss" not in sql
    assert "unrealized_pnl" not in sql


def test_the_b2_cut_verdict_still_refuses_unrealized_pnl():
    """The B2 cut reads `unrealized_pnl`, but only to REPORT a total beside the verdict and to
    warn on divergence — `cut_pnl` owns its own arithmetic. A check, not a gate, and it must
    stay that way: the verdict deciding on a figure a different writer owns is the fault
    TA-161 removed."""
    from tests._srcscan import function_code

    import models.b2_cut_alert as b2

    code = function_code(b2.__file__, "cut_pnl")
    assert "unrealized_pnl" not in code


def test_capital_at_risk_still_refuses_to_sum_max_loss():
    """R-IV.207(d), and the reason the breach above is a breach: the published figure is
    cost-derived and labelled as such, or there is none."""
    from tests._srcscan import function_code

    import services.position_economics as pe

    code = function_code(pe.__file__, "capital_at_risk")
    assert "max_loss" not in code
