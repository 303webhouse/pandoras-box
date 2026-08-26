"""FEAT-POSITION-LIFECYCLE D1 second half — column allowlists.

"The trigger audits; the allowlist prevents." The audit trigger records every
mutation but cannot refuse one; these scopes refuse the mutations that should never
originate from a given caller.

FAIL-FIRST: every test here fails against pre-fix unified_positions.py — the
behavioural tests because _position_write_scope did not exist, the structural tests
because neither dynamic-SET site called it.
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from api._position_write_scope import (  # noqa: E402
    MARK_COLUMNS, REALIZED_COLUMNS, WriteScope, assert_columns_allowed,
)

UP = pathlib.Path(__file__).resolve().parents[1] / "api" / "unified_positions.py"


# --- the contract Phase 4's insulation test is written against -----------------
@pytest.mark.parametrize("col", sorted(MARK_COLUMNS))
def test_manual_edit_cannot_write_any_mark_field(col):
    with pytest.raises(HTTPException) as e:
        assert_columns_allowed(["quantity", col], WriteScope.MANUAL_EDIT)
    assert e.value.status_code == 400
    assert col in e.value.detail


@pytest.mark.parametrize("col", sorted(REALIZED_COLUMNS))
def test_manual_edit_cannot_write_any_realized_field(col):
    with pytest.raises(HTTPException) as e:
        assert_columns_allowed(["notes", col], WriteScope.MANUAL_EDIT)
    assert e.value.status_code == 400
    assert col in e.value.detail


def test_manual_edit_permits_position_semantics():
    """The point is to refuse marks, not to freeze the book."""
    assert_columns_allowed(
        ["quantity", "long_strike", "short_strike", "expiry", "notes", "updated_at"],
        WriteScope.MANUAL_EDIT,
    )


def test_mark_job_may_write_marks_but_not_realized():
    assert_columns_allowed(sorted(MARK_COLUMNS), WriteScope.MARK_JOB)
    with pytest.raises(HTTPException):
        assert_columns_allowed(["current_price", "realized_pnl"], WriteScope.MARK_JOB)


def test_close_path_may_write_both():
    assert_columns_allowed(
        sorted(MARK_COLUMNS | REALIZED_COLUMNS), WriteScope.CLOSE_PATH
    )


def test_error_names_the_owner_of_each_refused_class():
    """A refusal that does not say who MAY write the field just blocks the operator."""
    with pytest.raises(HTTPException) as e:
        assert_columns_allowed(["current_price", "realized_pnl"], WriteScope.MANUAL_EDIT)
    detail = e.value.detail
    assert "mark-to-market" in detail
    assert "/close" in detail


def test_new_semantic_column_is_permitted_new_mark_column_is_not():
    """Denylist-by-class, deliberately: unknown columns are semantic until declared.

    A new mark column must be added to MARK_COLUMNS to be writable by the mark job,
    which fails toward refusing marks rather than silently admitting them.
    """
    assert_columns_allowed(["some_future_semantic_col"], WriteScope.MANUAL_EDIT)
    assert "some_future_semantic_col" not in MARK_COLUMNS


# --- structural: the wiring, not a copy of it ---------------------------------
def test_patch_site_checks_set_clause_columns_not_model_fields():
    src = UP.read_text(encoding="utf-8")
    assert 'assert_columns_allowed(\n        [s.split("=")[0].strip() for s in sets], WriteScope.MANUAL_EDIT\n    )' in src, (
        "the PATCH site must check the columns actually entering the SET clause; "
        "checking the request model's declared fields would miss any column that "
        "reaches SQL by another route")


def test_reconcile_mark_site_is_scoped_to_mark_job():
    src = UP.read_text(encoding="utf-8")
    assert "assert_columns_allowed(updates.keys(), WriteScope.MARK_JOB)" in src


def test_both_dynamic_set_sites_are_guarded():
    """Two sites build SET dynamically; an unguarded one is the whole hole."""
    src = UP.read_text(encoding="utf-8")
    dynamic_sites = (
        src.count("UPDATE unified_positions SET {set_clause}")
        + src.count("UPDATE unified_positions SET {', '.join(set_parts)}")
    )
    guards = src.count("assert_columns_allowed(")
    assert dynamic_sites == 2, f"expected 2 dynamic-SET sites, found {dynamic_sites}"
    assert guards >= dynamic_sites, (
        f"{dynamic_sites} dynamic-SET sites but only {guards} guard(s) - "
        "an unguarded dynamic site can write any column its caller supplies")
