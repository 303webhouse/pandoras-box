"""R-IV.1052(e)(c)3 — a NULL max_loss is UNKNOWN risk, never zero risk.

`services/position_economics.py` publishes three distinct states, and the readers collapsed two
of them:

    a figure + `max_loss_basis`                          -> the worst case
    0 + "opened for a net credit; cannot lose below zero" -> a STORED zero, honest
    None + a basis saying the width is unknown            -> UNMEASURABLE

`float(p.get("max_loss") or 0)` made the third identical to the second. Inside a RISK total
that reads an unmeasurable position as riskless; at `breakout_remaining_dd` it is SUBTRACTED
from a drawdown limit, so the unmeasurable row handed the account headroom it had not earned.

EVERY TEST HERE IS PAIRED (convention #30). A stored 0 must still behave as 0 -- a fix that
treated every zero as suspect would be the same conflation facing the other way.
"""
from __future__ import annotations

import ast
import inspect
import os
import re

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The sites the ruling named, plus the fourth the census found.
READERS = (
    "analytics/api.py",
    "analytics/oracle_engine.py",
    "api/unified_positions.py",
)


def _src(rel):
    with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
        return fh.read()


def _code_only(rel):
    """Source with comments and docstrings removed.

    A scan for `max_loss") or 0` would otherwise match the COMMENT that explains why that
    expression is wrong -- the prose trap this register has hit repeatedly. ast.unparse drops
    comments; docstrings are excluded BY IDENTITY, never by comparing to get_docstring().
    """
    tree = ast.parse(_src(rel))
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            docs.add(id(body[0]))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            node.body = [n for n in body if id(n) not in docs] or [ast.Pass()]
    return ast.unparse(tree)


# -- 0. positive control ---------------------------------------------------------------

def test_the_scan_reads_real_code():
    """Without this, a broken _code_only() would make every test below vacuous."""
    for rel in READERS:
        code = _code_only(rel)
        assert "max_loss" in code, "%s: the scan lost the column entirely" % rel
        assert "#" not in code.split("\n")[0], "comments should be gone"


# -- 1. the coalesce is gone, in code, not in prose ------------------------------------

def test_no_reader_coalesces_a_null_max_loss_to_zero():
    offenders = []
    for rel in READERS:
        code = _code_only(rel)
        # Both spellings the census found: .get("max_loss") or 0, and ["max_loss"] or 0.
        for pat in (r'get\(\s*[\'"]max_loss[\'"]\s*\)\s*or\s*0',
                    r'\[\s*[\'"]max_loss[\'"]\s*\]\s*or\s*0'):
            if re.search(pat, code):
                offenders.append("%s: %s" % (rel, pat))
    assert not offenders, (
        "a reader still turns an unmeasurable worst case into 0:\n  " + "\n  ".join(offenders))


def test_max_profit_is_not_coalesced_either():
    """The SAME fault one column over. oracle_engine divided by `max_profit or 0` in the very
    next line, so fixing only max_loss would leave the twin in place."""
    code = _code_only("analytics/oracle_engine.py")
    assert not re.search(r'get\(\s*[\'"]max_profit[\'"]\s*\)\s*or\s*0', code)


# -- 2. the gate fails CLOSED ----------------------------------------------------------

def test_can_open_new_requires_a_measurable_drawdown():
    """THE MONEY-RELEVANT ONE. `can_open_new` is where this sum authorises an action. With an
    unknown crypto worst case the remaining drawdown is not computable, so the gate must say
    no rather than yes-by-default."""
    code = _code_only("analytics/api.py")
    m = re.search(r"'can_open_new':(.{0,200})", code, re.S)
    assert m, "can_open_new not found -- did the payload key change?"
    assert "crypto_max_loss_unknown" in m.group(1), (
        "can_open_new does not consider whether the drawdown figure is even computable:\n%s"
        % m.group(1))


def test_the_gate_states_what_blocked_it():
    """A refusal with no reason is indistinguishable from a bug (TA-126)."""
    code = _code_only("analytics/api.py")
    assert "can_open_new_blocked_by" in code


# -- 3. every partial total says it is partial -----------------------------------------

def test_each_total_is_served_with_its_unknown_count():
    """A total that silently covers a subset reads as authoritative. The count beside it is
    what makes a floor legible as a floor -- the `unpriced_count` pattern already in
    unified_positions, applied to risk."""
    for rel, keys in (
        ("analytics/api.py", ("max_loss_unknown_count", "total_max_loss_is_partial")),
        ("api/unified_positions.py", ("max_loss_unknown_count", "capital_at_risk_is_partial")),
        ("analytics/oracle_engine.py", ("max_loss_utilization_unknown_count",
                                        "max_profit_utilization_unknown_count")),
    ):
        code = _code_only(rel)
        for k in keys:
            assert k in code, "%s does not serve %s" % (rel, k)


def test_the_partial_flag_is_derived_from_the_count_not_hardcoded():
    """A flag pinned to False would satisfy the test above while telling every reader the
    total is complete."""
    code = _code_only("api/unified_positions.py")
    vals = re.findall(r"'capital_at_risk_is_partial':([^,\n]*)", code)
    assert vals, "capital_at_risk_is_partial is not served at all"
    # TWO sites, and only one of them may be a literal. The early-return branch fires when
    # there are no positions: nothing is unknown there, so `False` is the honest answer and
    # demanding a derivation would be wrong. The branch that serves REAL rows must compute it.
    derived = [v for v in vals if "max_loss_unknown_count" in v]
    literal = [v for v in vals if "max_loss_unknown_count" not in v]
    assert derived, (
        "every capital_at_risk_is_partial is a literal, so the flag can never report a "
        "partial total: %r" % vals)
    assert all(v.strip() == "False" for v in literal), (
        "a literal partial-flag that is not the empty-book False: %r" % literal)


def test_unified_positions_declares_the_new_fields_as_derived():
    """They are computed per request, not stored, so they belong in _DRIFT_DERIVED_FIELDS --
    convention #42 arriving early on the two fields this change adds."""
    from api import unified_positions as up
    for k in ("max_loss_unknown_count", "capital_at_risk_is_partial"):
        assert k in up._DRIFT_DERIVED_FIELDS, k


# -- 4. THE PAIR: a stored zero is still zero ------------------------------------------

def test_a_stored_zero_max_loss_is_counted_not_skipped():
    """THE CONTROL FOR THE WHOLE FILE. R-IV.761(c) floors a credit-opened debit structure at
    max_loss = 0 WITH a reason. That zero is a real, honest figure and must be summed and
    must NOT be counted as unknown. Excluding falsy values instead of None values would pass
    every test above and silently drop it."""
    code = _code_only("api/unified_positions.py")
    # The sum must be filtered on `is not None`. A truthiness filter (`if p.get("max_loss")`)
    # would drop the stored 0 as well, understating the very total this change exists to
    # make honest.
    m = re.search(r"total_max_loss = sum\((.{0,220}?)\)\n", code, re.S)
    assert m, "the capital_at_risk sum could not be located"
    assert "is not None" in m.group(1), (
        "the sum filters on truthiness, which also drops a stored 0:\n%s" % m.group(1))


def test_the_none_filter_is_identity_based_everywhere():
    """`if p.get("max_loss")` would skip a stored 0 as well as a NULL. Each reader must test
    identity against None."""
    for rel in READERS:
        code = _code_only(rel)
        if "max_loss" not in code:
            continue
        assert "is not None" in code or "is None" in code, (
            "%s must distinguish NULL from 0 by identity" % rel)


def test_position_economics_still_publishes_both_states():
    """The upstream contract this all rests on. If economics stopped emitting None, the
    readers' new branch would be dead code and nobody would notice."""
    from services import position_economics as pe
    src = inspect.getsource(pe)
    assert "cannot lose below zero" in src, "the stored-zero branch is gone"
    assert 'out["max_loss"] = money(credit["max_loss"]) if credit["max_loss"] is not None else None' in src, \
        "the unknown-width branch no longer yields None"
