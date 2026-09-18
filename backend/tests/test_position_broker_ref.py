"""R-IV.448(b) — the broker's reference on the position row, out of prose and into a column.

FAIL-FIRST against the pre-2026-09-18 tree: unified_positions had no broker_ref at all (it was
asserted to exist and did not), no provenance, and no way to stamp a verified match on a row.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "042_position_broker_ref.sql"
BOOT = ROOT / "backend" / "database" / "postgres_client.py"
SCRIPT = ROOT / "scripts" / "lift_broker_refs_from_notes.py"

sys.path.insert(0, str(ROOT / "scripts"))
from lift_broker_refs_from_notes import classify  # noqa: E402


# --- the columns -----------------------------------------------------------------------
def test_the_row_gets_both_references_because_it_has_two_orders():
    """A row is opened by one order and closed by another; one column would have forced a
    choice, and the loser would have stayed in the prose this migration empties."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS broker_ref" in sql
    assert "ADD COLUMN IF NOT EXISTS exit_broker_ref" in sql
    assert "-- DOWN" in sql


def test_the_reference_is_not_unique_at_the_position_level():
    """One fill can close several positions. Unique here would have rejected the correction
    set's own evidence -- the 60-share sale covers three rows."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX" not in sql.upper().replace("CREATE UNIQUE INDEX IF NOT EXISTS UQ_POSITION_LOTS", "")
    assert "idx_unified_positions_broker_ref" in sql
    assert "one fill can close several positions" in sql


def test_a_verified_position_carries_the_same_three_pieces():
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    assert ("CHECK (provenance <> 'BROKER_VERIFIED' OR (broker_ref IS NOT NULL AND "
            "verified_event IS NOT NULL AND verified_at IS NOT NULL))") in sql


def test_the_backfill_never_claims_a_verification():
    sql = MIGRATION.read_text(encoding="utf-8")
    backfill = sql.split("DO $$")[0]
    assert "SET provenance = CASE" in backfill
    assert "'BROKER_VERIFIED'" not in backfill.split("SET provenance = CASE")[1].split(";")[0]


def test_boot_mirrors_the_migration():
    boot = BOOT.read_text(encoding="utf-8")
    for token in ("ADD COLUMN IF NOT EXISTS exit_broker_ref",
                  "unified_positions_verified_needs_evidence",
                  "unified_positions_provenance_check",
                  "idx_unified_positions_broker_ref"):
        assert token in boot, token


def test_the_alters_run_after_the_table_exists():
    boot = BOOT.read_text(encoding="utf-8")
    assert boot.index("ADD COLUMN IF NOT EXISTS exit_broker_ref") > \
        boot.index("CREATE TABLE IF NOT EXISTS unified_positions ("), (
            "the D4 class again — invisible on a populated database, fatal on an empty one")


# --- the verify route ------------------------------------------------------------------
def test_a_position_can_be_matched_to_a_broker_record():
    from api import unified_positions as U
    src = inspect.getsource(U.verify_position)
    assert "provenance = 'BROKER_VERIFIED'" in src
    assert "verified_at = NOW()" in src
    assert '"VERIFY"' in src


def test_the_position_route_demands_both_pieces_too():
    from api import unified_positions as U
    src = inspect.getsource(U.verify_position)
    assert "broker_ref and verified_event are both required" in src


def test_the_route_says_why_a_repeated_reference_is_allowed_here():
    from api import unified_positions as U
    assert "EXPECTED to repeat" in inspect.getsource(U.verify_position)


# --- the lift out of prose --------------------------------------------------------------
def test_a_note_that_says_bought_and_sold_splits_into_two_references():
    got = classify("Bought 09-16 50 @ 16.3850 (ref 26259-MCQGWD), sold 09-16 50 @ 16.0650 "
                   "(ref 26259-PBRZHP)")
    assert got == [("entry", "26259-MCQGWD"), ("exit", "26259-PBRZHP")]


def test_a_note_that_does_not_say_which_order_leaves_it_undecided():
    """Half these rows were opened and closed by different orders, so a lone reference is not
    assumed to be the entry."""
    assert classify("covered by confirmation 26254-Q7D3D4") == [(None, "26254-Q7D3D4")]


def test_the_lift_previews_by_default_and_never_verifies():
    src = SCRIPT.read_text(encoding="utf-8")
    assert '"--confirm"' in src and "PREVIEW ONLY" in src
    assert "BROKER_VERIFIED" in src and "a reference is evidence, not a verification" in src
    assert "UPDATE unified_positions" in src and src.count("UPDATE unified_positions") == 1


def test_the_lift_never_overwrites_a_reference_already_set():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "COALESCE(broker_ref, $1)" in src and "COALESCE(exit_broker_ref, $2)" in src


def test_the_lift_leaves_the_prose_alone():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "notes = " not in src, "the note records how the reference was established"
