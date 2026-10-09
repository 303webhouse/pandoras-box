"""TA-126 / R-IV.804(b)+(c) — the served row carries its own basis, and says so when it does not.

THE DEFECT, AND IT WAS MINE. The R-IV.797(c) backfill passed a citation on every one of its 29
writes, so the audit log holds them. But I wrote `classification_reason` as a COMPUTED field that
returned `None` whenever a row was classified — so all 11 Fidelity rows served a null basis
beside a confident verdict. TA-126 found it. A citation only an auditor can reach is not served
provenance, and a null basis is indistinguishable from "this row is fine".

THE SHAPE, for both axes: a value with no recorded basis reads
`NO BASIS RECORDED — do not gate on this value`, never `None`. Fail loud in the field a reader is
already looking at, rather than requiring them to notice an absence.

Convention #30 throughout: each "it reports a gap" is paired with a case that must read as
SETTLED, because a module that answered NO BASIS to everything would pass every fail-loud test
and make every axis permanently ungateable.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models import position_taxonomy as tx  # noqa: E402

CITE = "R-IV.797(c)1 + Part 4 v2"


class TestClassificationCarriesItsCitation:
    def test_a_classified_row_serves_the_ruling_it_was_written_under(self):
        assert tx.classification_reason("FIDELITY_ROTH", "TACTICAL", CITE) == CITE

    def test_a_classified_row_with_NO_basis_says_so_loudly(self):
        """The exact state TA-126 found, now visible instead of null."""
        out = tx.classification_reason("FIDELITY_ROTH", "TACTICAL", None)
        assert out == tx.NO_BASIS_RECORDED
        assert out is not None
        assert "do not gate" in out

    @pytest.mark.parametrize("blank", ["", "   ", "\n", "\t "])
    def test_whitespace_is_not_a_basis(self, blank):
        assert tx.classification_reason("FIDELITY_ROTH", "STRATEGIC", blank) == \
            tx.NO_BASIS_RECORDED

    def test_it_is_NEVER_none_for_a_classified_row(self):
        """The regression that produced TA-126, pinned in both directions."""
        for stored in (None, "", "  ", CITE):
            assert tx.classification_reason("FIDELITY_401A", "STRATEGIC", stored) is not None

    def test_an_absent_classification_still_says_WHY(self):
        """Three distinct cases; conflating any two is the defect."""
        assert tx.classification_reason("ROBINHOOD", None) == "not applicable: ROBINHOOD"
        assert tx.classification_reason("FIDELITY_ROTH", None) == "not recorded"

    def test_a_stored_basis_on_an_UNCLASSIFIED_row_does_not_mask_the_gap(self):
        """CONTROL. A leftover citation must not make an unclassified row look settled."""
        assert tx.classification_reason("FIDELITY_ROTH", None, CITE) == "not recorded"
        assert tx.classification_reason("ROBINHOOD", None, CITE) == "not applicable: ROBINHOOD"

    def test_a_non_vocabulary_value_is_not_treated_as_classified(self):
        """`B2` in the classification slot is the TA-123 defect; it must not acquire a basis."""
        assert tx.classification_reason("FIDELITY_ROTH", "B2", CITE) == "not recorded"


class TestBucketCarriesItsOwn:
    """R-IV.804(c), the same shape."""

    def test_a_bucketed_row_with_a_basis_serves_it(self):
        assert tx.bucket_reason("B2", "R-IV.803(b) row 12") == "R-IV.803(b) row 12"

    def test_a_bucketed_row_without_one_says_so_loudly(self):
        """Today's state for all 8 bucketed rows: inherited from a legacy display string."""
        assert tx.bucket_reason("B1") == tx.NO_BASIS_RECORDED

    def test_an_absent_bucket_is_always_a_GAP_never_a_decision(self):
        """Unlike the 20% cap, buckets are not scoped to an account, so there is no
        "not applicable" case to confuse with a missing one."""
        assert tx.bucket_reason(None) == "not recorded"

    def test_it_is_never_none_for_a_bucketed_row(self):
        for stored in (None, "", "x"):
            assert tx.bucket_reason("B3", stored) is not None

    @pytest.mark.parametrize("blank", ["", "   ", "\n", "\t "])
    def test_whitespace_is_not_a_bucket_basis_either(self, blank):
        """Added after a mutation got through: the whitespace case was parametrised for
        `classification` and not for `bucket`, so an implementation that accepted "   " as a
        citation passed all 34 tests. Both axes now carry the same assertion."""
        assert tx.bucket_reason("B2", blank) == tx.NO_BASIS_RECORDED

    def test_a_non_vocabulary_value_acquires_no_basis(self):
        assert tx.bucket_reason("TAIL", "whatever") == "not recorded"


class TestHasBasis:
    def test_true_only_when_both_the_value_and_its_basis_are_present(self):
        assert tx.has_basis({"classification": "TACTICAL",
                             "classification_reason": CITE}, "classification") is True
        assert tx.has_basis({"classification": "TACTICAL"}, "classification") is False

    def test_a_row_with_no_value_is_not_counted_as_missing_a_basis(self):
        """There is nothing to have a basis FOR, and counting those would bury the real gaps
        among 21 rows that are null by design."""
        assert tx.has_basis({"classification": None,
                             "classification_reason": CITE}, "classification") is False

    def test_an_axis_with_no_basis_column_is_false_rather_than_raising(self):
        """`sleeve_tag` has none — it is derived wholly from the legacy tag and cites no ruling
        of its own, so a third column would be a field with nothing to put in it."""
        assert "sleeve_tag" not in tx.REASON_COLUMNS
        assert tx.has_basis({"sleeve_tag": "TAIL"}, "sleeve_tag") is False


class TestBucketCoverageMirrorsCapEnforceable:
    def test_not_safe_to_gate_while_any_bucketed_row_lacks_a_basis(self):
        cov = tx.bucket_coverage([{"position_id": "A", "bucket": "B1", "bucket_reason": "x"},
                                  {"position_id": "B", "bucket": "B2"}])
        assert cov["safe_to_gate"] is False
        assert cov["rows_bucketed"] == 2 and cov["rows_without_basis"] == 1
        assert cov["position_ids_without_basis"] == ["B"]

    def test_safe_to_gate_once_every_bucketed_row_has_one(self):
        """POSITIVE CONTROL. It must be reachable, or it is a condition nothing can satisfy —
        the fault I committed on `cap_enforceable` two rulings ago."""
        cov = tx.bucket_coverage([{"position_id": "A", "bucket": "B1", "bucket_reason": "x"},
                                  {"position_id": "B", "bucket": "B2", "bucket_reason": "y"}])
        assert cov["safe_to_gate"] is True

    def test_an_empty_selection_is_NOT_safe_to_gate(self):
        """"Nothing to gate on" is not "the gate is satisfied", and the safe reading is the one
        that does not claim compliance."""
        assert tx.bucket_coverage([])["safe_to_gate"] is False
        assert tx.bucket_coverage([{"position_id": "A"}])["safe_to_gate"] is False

    def test_unbucketed_rows_do_not_count_against_coverage(self):
        cov = tx.bucket_coverage([{"position_id": "A", "bucket": "B1", "bucket_reason": "x"},
                                  {"position_id": "B"}, {"position_id": "C", "bucket": None}])
        assert cov["rows_bucketed"] == 1 and cov["safe_to_gate"] is True

    def test_it_says_why_in_its_own_payload(self):
        assert "not safe to gate" in tx.bucket_coverage([])["basis"].lower()
        assert "R-IV.803(b)" in tx.bucket_coverage([])["basis"]


class TestThePayload:
    def test_both_reasons_are_served_on_every_row(self):
        from hub_mcp.tools.positions import _build_position

        out = _build_position({"position_id": "P", "ticker": "X", "account": "FIDELITY_ROTH",
                               "classification": "TACTICAL", "classification_reason": CITE,
                               "bucket": "B2"})
        assert out["classification_reason"] == CITE
        assert out["bucket_reason"] == tx.NO_BASIS_RECORDED

    def test_the_stored_column_is_READ_not_recomputed(self):
        """The whole point of (b): the citation comes off the row, not out of a function."""
        from hub_mcp.tools.positions import _build_position

        out = _build_position({"position_id": "P", "ticker": "X", "account": "FIDELITY_401A",
                               "classification": "STRATEGIC",
                               "classification_reason": "bespoke citation 123"})
        assert out["classification_reason"] == "bespoke citation 123"

    def test_the_envelope_counts_classifications_with_no_basis(self):
        import inspect

        from hub_mcp.tools import positions as mod

        src = inspect.getsource(mod)
        assert "classifications_without_basis" in src
        assert "bucket_coverage" in src

    def test_the_description_says_bucket_is_not_safe_to_gate_on(self):
        from hub_mcp.tools.positions import DESCRIPTION

        assert "NOT SAFE TO GATE ON" in DESCRIPTION.upper()
        assert "bucket_coverage" in DESCRIPTION
        assert "R-IV.803(b)" in DESCRIPTION

    def test_the_description_promises_the_basis_fields(self):
        from hub_mcp.tools.positions import DESCRIPTION

        for f in ("classification_reason", "bucket_reason"):
            assert f in DESCRIPTION, f
        assert "NO BASIS RECORDED" in DESCRIPTION


class TestThePatchRouteTakesACitation:
    def test_both_basis_fields_are_accepted(self):
        from api.unified_positions import UpdatePositionRequest

        for f in ("classification_reason", "bucket_reason"):
            assert f in UpdatePositionRequest.model_fields, f

    def test_the_route_reads_the_column_names_from_the_module(self):
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up)
        assert "_TAXONOMY_REASON_COLUMNS.values()" in src
        assert "REASON_COLUMNS as _TAXONOMY_REASON_COLUMNS" in src

    def test_a_citation_is_length_capped_rather_than_vocabulary_checked(self):
        """It is free text — a ruling reference, not a vocabulary — so it cannot be validated
        against a list, but it must not become a narrative either."""
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up)
        assert "is a citation, not a narrative" in src
        assert "len(_text) > 500" in src

    def test_a_basis_may_be_written_without_resetting_the_value(self):
        """R-IV.804(b) is precisely a backfill of citations onto already-classified rows, so
        the route must not require the value to be re-sent."""
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up)
        assert "backfilling a citation onto an already-classified" in src

    def test_the_basis_columns_are_not_in_the_derived_guard(self):
        from api._position_write_scope import DERIVED_COLUMNS

        for f in ("classification_reason", "bucket_reason"):
            assert f not in DERIVED_COLUMNS, f

    def test_boot_creates_both_columns(self):
        import inspect

        from database import postgres_client as pc

        src = inspect.getsource(pc)
        for f in ("classification_reason", "bucket_reason"):
            assert "ADD COLUMN IF NOT EXISTS %s TEXT" % f in src, f
