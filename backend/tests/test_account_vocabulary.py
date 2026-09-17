"""R-IV.445(a) — one account vocabulary, read by every write path.

FAIL-FIRST against the pre-2026-09-17 tree: the canonical set lived inside one endpoint and
every other write path took `(value or "ROBINHOOD").upper()`, which is how five rows were
written under a retired alias eleven days after the remap. The path minted them; it was not
residue.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models.accounts import (  # noqa: E402
    CANONICAL_ACCOUNTS, DISPUTED, FIDELITY_401A, FIDELITY_ROTH, ROBINHOOD,
    canonical_account, non_canonical, normalize_account,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "remap_legacy_account_label.py"


def test_the_vocabulary_is_the_three_canonical_labels():
    assert CANONICAL_ACCOUNTS == (ROBINHOOD, FIDELITY_ROTH, FIDELITY_401A)


def test_a_canonical_label_passes_through_unchanged():
    for a in CANONICAL_ACCOUNTS:
        assert canonical_account(a) == a
        assert canonical_account(a.lower()) == a


def test_the_retired_alias_normalises_rather_than_failing():
    """A caller that has been right for months should not start failing; it should stop
    writing the retired spelling."""
    for spelling in ("FIDELITY", "fidelity", " Fidelity ", "fidelity - individual", "FID"):
        assert canonical_account(spelling) == FIDELITY_ROTH


def test_an_unknown_label_is_refused_and_the_refusal_quotes_what_arrived():
    with pytest.raises(HTTPException) as e:
        canonical_account("SCHWAB_BROKERAGE")
    assert e.value.status_code == 400
    assert "SCHWAB_BROKERAGE" in e.value.detail, (
        "a caller told only 'invalid account' sends the same string again")
    assert "FIDELITY_ROTH" in e.value.detail


def test_the_disputed_label_is_refused_and_says_why():
    with pytest.raises(HTTPException) as e:
        canonical_account(DISPUTED[0])
    assert "dispute" in e.value.detail, (
        "resolving it by writing would take a side in an open question")


def test_an_empty_account_is_refused_rather_than_defaulted():
    for bad in ("", "   ", None):
        with pytest.raises(HTTPException):
            canonical_account(bad)


def test_normalize_reports_none_instead_of_guessing():
    assert normalize_account("SCHWAB") is None
    assert normalize_account(None) is None


def test_reading_a_book_names_every_label_a_write_should_not_have_stored():
    assert non_canonical(["ROBINHOOD", "FIDELITY", "FIDELITY_ROTH", None, "SCHWAB"]) == [
        "FIDELITY", "SCHWAB"]


# --- every write path reads it --------------------------------------------------------------
def test_the_position_create_path_takes_the_account_from_the_module():
    from api import unified_positions as U
    src = inspect.getsource(U.create_position) if hasattr(U, "create_position") else U.__file__
    whole = pathlib.Path(U.__file__).read_text(encoding="utf-8")
    assert 'canonical_account(req.account or "ROBINHOOD")' in whole
    assert '(req.account or "ROBINHOOD").upper()' not in whole, (
        "an uppercased free string is the defect, not a smaller version of it")


def test_the_cash_event_path_takes_it_from_the_module_too():
    whole = pathlib.Path(
        ROOT / "backend" / "api" / "unified_positions.py").read_text(encoding="utf-8")
    assert "acct = canonical_account(req.account)" in whole


def test_the_legacy_signal_entry_paths_take_it_from_the_module():
    whole = pathlib.Path(ROOT / "backend" / "api" / "positions.py").read_text(encoding="utf-8")
    assert '(request.account or "ROBINHOOD").upper()' not in whole
    assert whole.count("canonical_account(") >= 3, "create, insert and cash adjustment"


# --- the remap is the principal's to run ----------------------------------------------------
def test_the_remap_script_previews_by_default():
    src = SCRIPT.read_text(encoding="utf-8")
    assert '"--confirm"' in src and "action=\"store_true\"" in src
    assert "PREVIEW ONLY" in src


def test_the_remap_never_invents_a_mapping():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "normalize_account(" in src
    assert "no canonical meaning" in src, "an unresolvable label is skipped, not guessed"
    assert "DISPUTED" in src


def test_the_remap_writes_only_the_account_column():
    src = SCRIPT.read_text(encoding="utf-8")
    assert src.count("UPDATE unified_positions") == 1
    assert "SET account = $1, updated_at = NOW()" in src
