"""A DUPLICATE_OF row's money is never summed — R-IV.874(b).

POSITIONS retired KNX row 504 as DUPLICATE_OF row 331. The fills happened once, so the money
counts once; the row is kept because deleting it would destroy the evidence of the duplication,
and left CLOSED it would double every figure computed from it.

504 was on the ROW-LEVEL realized_pnl FALLBACK branch — the one that exists because eight rows
carry a recorded realized_pnl and no closure rows at all, so summing the closures ledger alone
would discard eight real losses. That fallback is a guard, not a design, and a guard that reads
raw rows is exactly where a retired row slips back in.

FOUR READERS SUM ROW-LEVEL REALIZED. Two exclude DUPLICATE_OF explicitly; two exclude it only
because they enumerate an allowlist of statuses. The second kind is safe TODAY and fragile:
relaxing a status filter is precisely what the 107.48 defect required (realized hides on OPEN
rows), so the next person to widen one could readmit a duplicate without noticing. Both kinds
are pinned here.
"""
from __future__ import annotations

import ast
import re
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models import position_status  # noqa: E402

REPO_BACKEND = __file__.rsplit("tests", 1)[0]


def _code_without_docstrings(path):
    """Source with `#` comments and DOCSTRINGS removed — every other string left intact.

    The first version of this stripped ALL triple-quoted text, which deleted the SQL itself:
    these guards live inside triple-quoted query strings, so blanking them made all three
    readers look unguarded and the test failed on files that were correct.

    That is the mirror of the prose trap. The goal is to remove PROSE — and a docstring is
    prose, while a query is code. So docstrings are located with `ast` and blanked by line
    range, and nothing else is touched.
    """
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    kill = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            d = body[0]
            kill.update(range(d.lineno - 1, (d.end_lineno or d.lineno)))
    return "\n".join("" if i in kill else l.split("#")[0] for i, l in enumerate(lines))


# ── the one author ──────────────────────────────────────────────────────────

def test_duplicate_of_is_a_known_status_not_a_typo():
    assert position_status.DUPLICATE_OF in position_status.STATUSES


def test_duplicate_of_money_does_not_count():
    """MONEY_STATUSES answers "does this row's money count?". A duplicate's answer is no."""
    assert position_status.DUPLICATE_OF not in position_status.MONEY_STATUSES


def test_duplicate_of_is_not_a_realized_result_either():
    assert position_status.DUPLICATE_OF not in position_status.REALIZED_STATUSES


def test_a_duplicate_row_with_a_real_realized_figure_is_refused():
    """Row 504's exact shape: retired, and carrying a non-null realized figure. The figure being
    PRESENT is the whole hazard — a NULL would have been harmless."""
    row = {"status": "DUPLICATE_OF", "realized_pnl": -119.23, "duplicate_of": "row 331"}
    assert position_status.counts_as_realized(row["status"]) is False


@pytest.mark.parametrize("spelling", ["DUPLICATE_OF", "duplicate_of", "Duplicate_Of"])
def test_the_refusal_does_not_depend_on_CASE(spelling):
    """R-IV.849(d)'s lesson: stored casing is not guaranteed (`Whale_Hunter`, not
    `whale_hunter`). A guard that matches only one spelling is not a guard."""
    assert position_status.counts_as_realized(spelling) is False


def test_the_pair_a_closed_row_with_realized_DOES_count():
    """Convention #30 — without this, a function refusing everything would pass above."""
    assert position_status.counts_as_realized("CLOSED") is True
    assert position_status.counts_as_realized("EXPIRED") is True


def test_an_open_row_with_realized_still_counts_as_MONEY():
    """The 107.48 finding, pinned: a partial exit books real money on a row that is still OPEN.
    Excluding duplicates must not be achieved by narrowing back to closed-only."""
    assert "OPEN" in position_status.MONEY_STATUSES


def test_the_analytics_filter_keeps_one_row_and_drops_the_duplicate():
    """Through the predicate the analytics surface actually uses, not a reimplementation."""
    rows = [
        {"status": "CLOSED", "pnl_dollars": 100.0},
        {"status": "DUPLICATE_OF", "pnl_dollars": -119.23},
    ]
    kept = [r for r in rows if position_status.counts_as_realized(r.get("status"))]
    assert [r["pnl_dollars"] for r in kept] == [100.0]


# ── every SQL reader of row-level realized carries a guard ─────────────────

# file -> the guard shape it relies on. An allowlist of statuses excludes DUPLICATE_OF by
# omission; an explicit inequality excludes it by name. Both are acceptable; neither is not.
SQL_READERS = {
    "api/abacus.py": "explicit",
    "analytics/queries.py": "allowlist",
    "analytics/oracle_engine.py": "allowlist",
}


@pytest.mark.parametrize("rel", sorted(SQL_READERS))
def test_each_sql_reader_of_row_realized_is_guarded(rel):
    """Reads the SOURCE, because the guard IS SQL text — there is no object to interrogate.

    Deliberately not a hunt for the status name: an allowlist guard never mentions DUPLICATE_OF
    at all, so requiring the name would fail the two safe readers and teach the next person to
    add a decorative mention.
    """
    code = _code_without_docstrings(REPO_BACKEND + rel)
    assert "realized_pnl" in code, "%s no longer sums row-level realized" % rel

    explicit = re.search(r"<>\s*'DUPLICATE_OF'", code) is not None
    allowlist = re.search(r"status\s*(?:=|IN)\s*\(?\s*'(?:CLOSED|EXPIRED)'", code,
                          re.I) is not None
    assert explicit or allowlist, (
        "%s sums row-level realized_pnl with neither an explicit DUPLICATE_OF exclusion nor a "
        "status allowlist — a retired duplicate would be counted" % rel)

    if SQL_READERS[rel] == "explicit":
        assert explicit, "%s is recorded as using an explicit guard; it no longer does" % rel


def test_abacus_excludes_duplicates_on_BOTH_branches():
    """The closures branch AND the no-closures FALLBACK branch. 504 was on the fallback, so a
    guard on only the first would have missed it — the whole point of R-IV.874."""
    code = _code_without_docstrings(REPO_BACKEND + "api/abacus.py")
    assert len(re.findall(r"<>\s*'DUPLICATE_OF'", code)) >= 2, (
        "expected the exclusion on both the closures and the fallback branch")


def test_the_explicit_guards_are_case_insensitive_in_sql_too():
    """UPPER(COALESCE(status,'')) rather than a bare comparison — the same casing lesson, in
    SQL. The COALESCE is there so a NULL status cannot slip past either."""
    code = _code_without_docstrings(REPO_BACKEND + "api/abacus.py")
    for m in re.finditer(r"(.{0,70})<>\s*'DUPLICATE_OF'", code):
        assert "UPPER(" in m.group(1), (
            "an exclusion compares status without UPPER(): %r" % m.group(1).strip()[-50:])


def test_the_stripper_removes_prose_but_keeps_sql():
    """A positive control for the helper everything above depends on. Its first version blanked
    the SQL along with the prose, so all three readers read as unguarded — a test that fails on
    correct code teaches people to delete the test."""
    code = _code_without_docstrings(REPO_BACKEND + "api/abacus.py")
    assert "<> 'DUPLICATE_OF'" in code, "the SQL guard was stripped — the helper is wrong"
    assert "are not DUPLICATE_OF" not in code, "docstring prose survived the strip"
