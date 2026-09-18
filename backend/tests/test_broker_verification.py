"""R-IV.447(b) — BROKER_VERIFIED becomes reachable, and only on evidence.

FAIL-FIRST against the pre-2026-09-17 tree: nothing could write the value at all (deliberately,
while no path matched a broker record), the close path stamped NOW() on every exit, and a
caller's realized figure had nowhere to be checked against the row's own basis.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "041_broker_verification.sql"
BOOT = ROOT / "backend" / "database" / "postgres_client.py"
API = ROOT / "backend" / "api" / "unified_positions.py"


# --- the evidence set ------------------------------------------------------------------
def test_the_constraint_requires_all_three_pieces():
    """Reference, event and timestamp. Take one away and the claim is unfalsifiable again."""
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    for table in ("position_lots", "position_legs"):
        assert (f"ALTER TABLE {table} ADD CONSTRAINT {table}_verified_needs_evidence "
                "CHECK (provenance <> 'BROKER_VERIFIED' OR (broker_ref IS NOT NULL AND "
                "verified_event IS NOT NULL AND verified_at IS NOT NULL))") in sql


def test_the_weaker_constraint_is_replaced_not_left_beside_it():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "DROP CONSTRAINT position_lots_verified_needs_ref" in sql, (
        "one rule, not two — a reference-only check would still admit an unstamped claim")


def test_boot_mirrors_the_migration():
    boot = BOOT.read_text(encoding="utf-8")
    for token in ("verified_at", "verified_event", "position_lots_verified_needs_evidence",
                  "position_legs_verified_needs_evidence",
                  "DROP CONSTRAINT position_lots_verified_needs_ref"):
        assert token in boot, token


def test_verified_at_is_the_match_not_the_fill():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "time of the MATCH" in sql
    api = API.read_text(encoding="utf-8")
    assert "verified_at = NOW()" in api, "the stamp is taken at the transition"


# --- the transition ------------------------------------------------------------------------
def test_verification_is_the_only_route_to_the_value():
    """Nothing else in the write paths may assign BROKER_VERIFIED."""
    api = API.read_text(encoding="utf-8")
    assigns = [ln for ln in api.splitlines()
               if "BROKER_VERIFIED" in ln and ("=" in ln or "SET" in ln)
               and not ln.strip().startswith("#")]
    for ln in assigns:
        assert "provenance = 'BROKER_VERIFIED'" in ln or "\"provenance\": \"BROKER_VERIFIED\"" in ln
    assert sum("provenance = 'BROKER_VERIFIED'" in ln for ln in assigns) == 1, (
        "exactly one SQL site may assign it, and it is the verify transition")


def test_both_lots_and_legs_have_the_route():
    from api import unified_positions as U
    assert inspect.iscoroutinefunction(U.verify_position_lot)
    assert inspect.iscoroutinefunction(U.verify_position_leg)
    leg_src = inspect.getsource(U.verify_position_leg)
    assert 'key_column="leg_seq"' in leg_src, "a leg is addressed by its sequence, not its id"


def test_a_verification_without_evidence_is_refused():
    from api import unified_positions as U
    src = inspect.getsource(U._verify_row)
    assert "broker_ref and verified_event are both required" in src
    assert "status_code=400" in src


def test_a_reference_already_held_elsewhere_is_refused():
    from api import unified_positions as U
    src = inspect.getsource(U._verify_row)
    assert "status_code=409" in src and "already on" in src


def test_the_transition_is_audited_with_before_and_after():
    from api import unified_positions as U
    src = inspect.getsource(U._verify_row)
    assert '"VERIFY"' in src
    assert '"provenance": row["provenance"]' in src and '"BROKER_VERIFIED"' in src


def test_the_request_model_demands_both_fields():
    from api.unified_positions import VerifyRequest
    fields = VerifyRequest.model_fields
    assert fields["broker_ref"].is_required() and fields["verified_event"].is_required()


# --- historical exits and the realized cross-check ------------------------------------------
def test_an_exit_keeps_the_day_it_happened_on():
    from api.unified_positions import ClosePositionRequest
    assert "exit_date" in ClosePositionRequest.model_fields
    src = API.read_text(encoding="utf-8")
    assert "is in the future" in src, "a future exit has not happened"
    assert "now = exit_when" in src, "the supplied date replaces NOW() for the whole close"


def test_the_callers_realized_figure_is_checked_not_stored():
    from api.unified_positions import ClosePositionRequest
    assert "expected_realized" in ClosePositionRequest.model_fields
    src = API.read_text(encoding="utf-8")
    assert "realized disagreement" in src
    assert "Nothing was written" in src
    assert "realized_pnl = round" in src, "the stored figure is still the row's own basis"


def test_the_disagreement_names_both_numbers():
    src = API.read_text(encoding="utf-8")
    i = src.index("realized disagreement")
    window = src[i:i + 600]
    assert "this row's basis implies" in window and "the caller expected" in window


def test_the_tolerance_is_a_cent_by_default():
    from api.unified_positions import ClosePositionRequest
    assert ClosePositionRequest(exit_price=1.0).realized_tolerance == 0.01


# --- fresh-database boot order (the D4 class) -----------------------------------------------
def test_nothing_touches_position_lots_before_it_is_created():
    """On the live database every table already exists, so an ordering mistake here is
    invisible — it only fails on a database booting from empty, which is the one case this
    ordering exists for. Caught on the live shape by a constraint that kept coming back."""
    boot = BOOT.read_text(encoding="utf-8")
    created = boot.index("CREATE TABLE IF NOT EXISTS position_lots (")
    for dependent in ("CREATE TABLE IF NOT EXISTS position_lot_closures",
                      "ADD COLUMN IF NOT EXISTS verified_at",
                      "uq_position_lots_broker_ref"):
        assert boot.index(dependent) > created, (
            f"{dependent!r} runs before position_lots exists — a fresh boot fails there")


def test_the_superseded_constraint_is_not_re_created_after_it_is_dropped():
    """It was: the drop ran in one block and the create in a later one, so every boot put the
    weaker rule back. The end state looked right in code and was wrong in the database."""
    boot = BOOT.read_text(encoding="utf-8")
    creates = [ln for ln in boot.splitlines()
               if "ADD CONSTRAINT position_lots_verified_needs_ref" in ln
               and not ln.strip().startswith("--")]
    assert creates == [], "nothing may re-create the superseded reference-only rule"
    assert "DROP CONSTRAINT position_lots_verified_needs_ref" in boot
