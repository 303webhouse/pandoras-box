"""No full account number is in any tracked file. R-IV.1332(c).

WHAT HAPPENED. `de9c86f` (2026-10-01) committed the FULL account numbers for FIDELITY_ROTH
(...3158) and FIDELITY_401A (...1836) into `backend/models/accounts.py` -- in the
`ACCOUNT_NUMBERS` map and interpolated into error messages and account descriptions. This
repository is PUBLIC (verified with `gh repo view`: `{"isPrivate":false,"visibility":"PUBLIC"}`),
so they were readable on GitHub from that day until the commit this test ships with.

They had spread well past that file: **18 tracked files, 81 occurrences**, including eight
copies of `COMMITTEE_RULES.md` under `skills/*/_shared/`, a context note under `claude/`, a
handoff brief, and two scripts that used a number inside a FILENAME.

WHY THIS TEST IS A SWEEP AND NOT AN ASSERTION ABOUT ONE FILE. The numbers did not spread by
anyone deciding to copy them; they spread because a skills directory is duplicated per agent and
a context note quotes whatever the source said. A guard on `accounts.py` alone would have passed
on 2026-10-01 while seventeen other files carried the numbers.

HOW IT KNOWS WHAT TO LOOK FOR WITHOUT HOLDING IT. A test that hard-coded the numbers in order to
forbid them would be the thing it forbids. So it reconstructs them from the LAST FOUR plus the
known length (nine digits) and searches for any nine-digit run ending in one of ours -- which
catches the real numbers without this file ever containing them, and catches a different account
sharing a last-4 as well.

R-IV.1332(c)7 asks that no merge bring them back. The sweep runs on the working tree, so it runs
on every branch and in every merge result; a merge that reintroduces a number fails here before
anything is pushed.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))


def _tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=str(_REPO),
                         capture_output=True, text=True, timeout=120)
    return [p for p in out.stdout.split("\n") if p.strip()]


def _nine_digit_runs(text):
    return re.findall(r"(?<!\d)\d{9}(?!\d)", text)


def test_the_module_no_longer_holds_a_full_number():
    """The file the numbers were committed in."""
    src = (_BACKEND / "models" / "accounts.py").read_text(encoding="utf-8")
    assert _nine_digit_runs(src) == []
    assert re.findall(r"(?<!\d)\d{6,}(?!\d)", src) == []


def test_NO_TRACKED_FILE_holds_a_number_ending_IN_ONE_OF_OURS():
    """THE SWEEP. R-IV.1332(c)1 and (c)7.

    Reconstructed from the last four and the length, so this file never contains a full number
    while still being able to find one. A nine-digit run ending ...3158 or ...1836 in any
    tracked file is either the real number returning or a different account that the last-4
    identity could not tell apart -- both are findings.
    """
    from models.accounts import ACCOUNT_LAST4

    wanted = set(ACCOUNT_LAST4.values())
    offenders = {}
    for rel in _tracked_files():
        path = _REPO / rel
        try:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        except Exception:
            continue
        hits = [r for r in _nine_digit_runs(text) if r[-4:] in wanted]
        if hits:
            # Report the FILE and the COUNT only. Never the number, here or anywhere.
            offenders[rel] = len(hits)
    assert offenders == {}, (
        "tracked files contain a 9-digit number ending in a tracked account's last 4 "
        "(file -> count, numbers deliberately not printed): %r" % offenders)


def test_the_last_four_are_all_that_is_kept():
    from models.accounts import ACCOUNT_LAST4

    assert set(ACCOUNT_LAST4.values()) == {"3158", "1836"}
    assert all(len(v) == 4 for v in ACCOUNT_LAST4.values())


def test_the_removed_symbols_are_GONE_and_not_merely_emptied():
    """`ACCOUNT_NUMBERS` and `ACCOUNT_BY_NUMBER` held the full numbers. An emptied dict under
    the same name would let a caller keep reading it and get nothing, which fails later and
    further away than an ImportError."""
    from models import accounts

    assert not hasattr(accounts, "ACCOUNT_NUMBERS")
    assert not hasattr(accounts, "ACCOUNT_BY_NUMBER")
    assert hasattr(accounts, "ACCOUNT_LAST4") and hasattr(accounts, "ACCOUNT_BY_LAST4")


def test_no_repo_file_still_imports_the_removed_symbols():
    import ast

    bad = []
    for rel in _tracked_files():
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse((_REPO / rel).read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name in ("ACCOUNT_NUMBERS", "ACCOUNT_BY_NUMBER"):
                        bad.append("%s imports %s" % (rel, a.name))
    assert bad == [], bad


# ── (c)3: last four only on every surface ───────────────────────────────────

def test_the_display_helper_never_returns_more_than_the_last_four():
    from models.accounts import (CANONICAL_ACCOUNTS, FIDELITY_401A, FIDELITY_ROTH,
                                 account_display_number)

    assert account_display_number(FIDELITY_ROTH) == "...3158"
    assert account_display_number(FIDELITY_401A) == "...1836"
    for key in CANONICAL_ACCOUNTS:
        got = account_display_number(key)
        assert got is None or (got.startswith("...") and len(got) == 7), (key, got)


def test_the_account_DESCRIPTION_shows_last_four_only():
    """It is built for the MCP tools, so it reaches a committee member's prompt."""
    from models.accounts import describe_accounts

    d = describe_accounts()
    assert "...3158" in d and "...1836" in d
    assert _nine_digit_runs(d) == []


@pytest.mark.parametrize("value", ["Fidelity", "FIDELITY", "fidelity brokeragelink"])
def test_the_AMBIGUOUS_FIDELITY_refusal_shows_last_four_only(value):
    """The refusal names both accounts so a caller can pick one. It used to name them with
    their full numbers, so a 400 handed the numbers to whoever triggered it."""
    from fastapi import HTTPException

    from models.accounts import canonical_account

    with pytest.raises(HTTPException) as exc:
        canonical_account(value)
    detail = str(exc.value.detail)
    assert "...3158" in detail and "...1836" in detail
    assert _nine_digit_runs(detail) == []


def test_the_DISPUTED_label_refusal_shows_last_four_only():
    from fastapi import HTTPException

    from models.accounts import DISPUTED, canonical_account

    label = sorted(DISPUTED)[0]
    with pytest.raises(HTTPException) as exc:
        canonical_account(label)
    assert _nine_digit_runs(str(exc.value.detail)) == []


def test_the_write_paths_missing_account_error_shows_last_four_only():
    """`unified_positions` builds this when a write names no account -- the most likely 400 on
    that route, and it interpolated the full number."""
    src = (_BACKEND / "api" / "unified_positions.py").read_text(encoding="utf-8")
    i = src.index("account is required: this hub tracks")
    block = src[max(0, i - 900):i + 300]
    assert "account_display_number" in block
    assert "ACCOUNT_NUMBERS" not in block


# ── identification still works ──────────────────────────────────────────────

def test_both_accounts_still_RESOLVE_which_is_the_point_of_keeping_last_four():
    from models.accounts import (FIDELITY_401A, FIDELITY_ROTH, account_for_number,
                                 canonical_account, normalize_account)

    for raw, expect in (("3158", FIDELITY_ROTH), ("...3158", FIDELITY_ROTH),
                        ("1836", FIDELITY_401A), ("x-1836", FIDELITY_401A)):
        assert account_for_number(raw) == expect, raw
        assert normalize_account(raw) == expect, raw
        assert canonical_account(raw) == expect, raw


def test_an_unknown_account_still_REFUSES():
    from fastapi import HTTPException

    from models.accounts import account_for_number, canonical_account

    assert account_for_number("4242") is None
    with pytest.raises(HTTPException):
        canonical_account("4242")
