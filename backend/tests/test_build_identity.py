"""Tests for the /health build-identity block — R-IV.344(b).

The load-bearing assertions here are the NEGATIVE ones: that an unreadable
identity reports itself as unreadable rather than passing, and that a malformed
value is never echoed. A field that silently guesses would recreate the exact
defect this block was built to close.
"""

import re

import pytest

from build_identity import (
    COMMIT_ENV_NAMES,
    BRANCH_ENV_NAMES,
    MALFORMED,
    build_identity,
)

ALL_NAMES = tuple(COMMIT_ENV_NAMES) + tuple(BRANCH_ENV_NAMES)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ALL_NAMES:
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------
# unreadable is never a pass (R-IV.344(d))
# --------------------------------------------------------------------------

def test_no_env_reports_unreadable_not_a_guess():
    b = build_identity()
    assert b["commit"] is None
    assert b["commit_source"] == "unavailable"
    assert b["identity_readable"] is False


def test_unreadable_note_names_what_was_checked():
    """An absence that does not say what it looked for is not a finding."""
    note = build_identity()["note"]
    for name in COMMIT_ENV_NAMES:
        assert name in note
    assert "MUST fail the identity half" in note


def test_empty_string_is_absent_not_present():
    """Railway hands back '' for an unset reference, not None."""
    import os
    os.environ["RAILWAY_GIT_COMMIT_SHA"] = ""
    try:
        b = build_identity()
        assert b["identity_readable"] is False
        assert b["commit"] is None
    finally:
        del os.environ["RAILWAY_GIT_COMMIT_SHA"]


def test_whitespace_only_is_absent(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "   ")
    assert build_identity()["identity_readable"] is False


# --------------------------------------------------------------------------
# a malformed value is named, never echoed
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "not-a-sha",
    "ZZZZZZZ",
    "8A4F4D6",                       # uppercase is not git's output shape
    "abc",                           # too short
    "a" * 41,                        # too long
    "8a4f4d6; rm -rf /",
    "<script>alert(1)</script>",
])
def test_malformed_commit_is_flagged_and_never_echoed(monkeypatch, bad):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", bad)
    b = build_identity()
    assert b["commit"] == MALFORMED
    assert b["identity_readable"] is False
    blob = repr(b)
    assert bad not in blob, "the malformed VALUE reached the payload"


def test_malformed_branch_is_flagged_and_never_echoed(monkeypatch):
    bad = "branch with spaces and $(cmd)"
    monkeypatch.setenv("GIT_BRANCH", bad)
    b = build_identity()
    assert b["branch"] == MALFORMED
    assert bad not in repr(b)


def test_only_allowlisted_names_are_read(monkeypatch):
    """Never os.environ at large — /health is public."""
    monkeypatch.setenv("DB_PASSWORD", "a" * 40)          # SHA-shaped on purpose
    monkeypatch.setenv("PIVOT_API_KEY", "b" * 40)
    b = build_identity()
    assert b["commit"] is None
    assert "a" * 40 not in repr(b)
    assert "b" * 40 not in repr(b)


# --------------------------------------------------------------------------
# the happy path
# --------------------------------------------------------------------------

def test_full_sha_is_read_and_source_named(monkeypatch):
    sha = "8a4f4d6a183fef3872d6a18f65453a5814ec1681"
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", sha)
    b = build_identity()
    assert b["commit"] == sha
    assert b["commit_source"] == "RAILWAY_GIT_COMMIT_SHA"
    assert b["identity_readable"] is True
    assert "note" not in b


def test_short_sha_is_accepted(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "8a4f4d6")
    b = build_identity()
    assert b["commit"] == "8a4f4d6"
    assert b["identity_readable"] is True


def test_allowlist_precedence_is_most_authoritative_first(monkeypatch):
    monkeypatch.setenv("BUILD_COMMIT", "f" * 40)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    b = build_identity()
    assert b["commit_source"] == "RAILWAY_GIT_COMMIT_SHA"
    assert b["commit"] == "a" * 40


def test_branch_is_read(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "main")
    assert build_identity()["branch"] == "main"


# --------------------------------------------------------------------------
# the restart witness — the corroborating half
# --------------------------------------------------------------------------

def test_uptime_and_start_are_always_present_even_when_unreadable():
    """Identity can be unverifiable while the restart witness still works."""
    b = build_identity()
    assert b["identity_readable"] is False
    assert isinstance(b["uptime_seconds"], int)
    assert b["uptime_seconds"] >= 0
    assert re.match(r"\A\d{4}-\d{2}-\d{2}T", b["process_started_at"])


def test_process_started_at_is_stable_across_calls():
    """It witnesses the PROCESS, so it must not move between reads."""
    assert build_identity()["process_started_at"] == build_identity()["process_started_at"]


def test_no_railway_internal_ids_are_exposed(monkeypatch):
    """The SHA is public; account-shaped identifiers are not."""
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "e2be1633-1f9a-474b-832a-7e01012f9a05")
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "e19cc86b-204b-486c-b63c-91531791e754")
    blob = repr(build_identity())
    assert "e2be1633" not in blob
    assert "e19cc86b" not in blob


# --------------------------------------------------------------------------
# witness vs attestation — R-IV.345(b)
#
# This service has no RAILWAY_GIT_* var, so every SHA that arrives is DECLARED
# by whoever set it. The field must say so: a declaration that presents itself
# as a witness is the fabrication this register keeps finding.
# --------------------------------------------------------------------------

def test_platform_sourced_commit_is_a_witness(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    b = build_identity()
    assert b["identity_kind"] == "platform"
    assert "note" not in b


@pytest.mark.parametrize("name", ["SOURCE_COMMIT", "GIT_COMMIT", "COMMIT_SHA", "BUILD_COMMIT"])
def test_non_platform_commit_is_declared_and_says_so(monkeypatch, name):
    monkeypatch.setenv(name, "b" * 40)
    b = build_identity()
    assert b["identity_kind"] == "declared"
    assert b["commit_source"] == name
    assert "CANNOT witness what is running" in b["note"]
    assert name in b["note"]


def test_absent_commit_kind_is_unavailable():
    assert build_identity()["identity_kind"] == "unavailable"


def test_malformed_commit_kind_is_unavailable(monkeypatch):
    """Malformed must not be dressed up as a declaration."""
    monkeypatch.setenv("SOURCE_COMMIT", "not-a-sha")
    b = build_identity()
    assert b["identity_kind"] == "unavailable"
    assert b["identity_readable"] is False


def test_platform_beats_declaration_when_both_present(monkeypatch):
    """If Railway ever starts providing it, the witness must win automatically."""
    monkeypatch.setenv("BUILD_COMMIT", "d" * 40)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "e" * 40)
    b = build_identity()
    assert b["identity_kind"] == "platform"
    assert b["commit"] == "e" * 40


def test_declared_note_does_not_claim_verification(monkeypatch):
    """The wording is the safeguard; assert it cannot be read as a pass."""
    monkeypatch.setenv("SOURCE_COMMIT", "f" * 40)
    note = build_identity()["note"]
    assert "intended to deploy" in note
    assert "compare it to the sha it pushed itself" in note
    assert "uptime_seconds" in note
