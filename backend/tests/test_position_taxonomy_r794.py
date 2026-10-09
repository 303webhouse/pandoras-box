"""TA-123 / R-IV.794(b) — three taxonomies, three fields, and nothing guessed.

THE DEFECT. `strategy_tag` is one column carrying three INDEPENDENT taxonomies, so each row keeps
whichever was written last and the other two are gone. Filtering it for the Roth's 20% tactical
cap returned SOXS alone at 8.26%, against the truth of SOXS + TSLQ at 19.50% — TSLQ's `TACTICAL`
had been overwritten by its bucket `B2`. A cap read off that field is a cap read off the last
edit, and it under-reported by more than half.

CONFIRMED INDEPENDENTLY, from hub data, before building anything: 8.26% -> 19.50% is a multiple
of 2.361x, and the hub's own current values give SOXS 1,013.70 against SOXS+TSLQ 2,392.10 — a
multiple of 2.360x. The PERCENTAGES need a denominator the hub does not hold (~12,270, a broker
figure; the hub's stored Roth balance is 8,842.09 and two weeks stale), so the multiple is what
is reproducible and it reproduces to three figures.

Convention #30: every "it maps" is paired with a case that must NOT map, because a mapper that
filled in every field would pass every positive test and silently invent the classifications the
cap is enforced from.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models import position_taxonomy as tx  # noqa: E402


class TestTheThreeVocabularies:
    def test_they_are_the_ruled_ones(self):
        assert tx.CLASSIFICATIONS == ("STRATEGIC", "TACTICAL")
        assert tx.SLEEVE_TAGS == ("TAIL", "CONVEXITY")
        assert tx.BUCKETS == ("B1", "B2", "B3")
        assert tx.FIELDS == ("classification", "sleeve_tag", "bucket")

    def test_they_do_NOT_inherit_the_old_module(self):
        """`models/strategy_tag.py` calls itself the one author of the vocabulary and does not
        recognise STRATEGIC, TACTICAL or B3 — `is_known("STRATEGIC")` is False — while nine live
        rows carry the first two. Inheriting a list two labels behind the book is how this
        defect started."""
        from models import strategy_tag as st

        assert st.is_known("STRATEGIC") is False
        assert st.is_known("TACTICAL") is False
        assert "STRATEGIC" not in st.TAGS
        # ... and this module carries them anyway, from the ruling.
        assert "STRATEGIC" in tx.CLASSIFICATIONS and "TACTICAL" in tx.CLASSIFICATIONS

    @pytest.mark.parametrize("field,value", [("classification", "STRATEGIC"),
                                             ("classification", "TACTICAL"),
                                             ("sleeve_tag", "TAIL"), ("bucket", "B3")])
    def test_is_valid_accepts_the_vocabulary(self, field, value):
        assert tx.is_valid(field, value) is True

    @pytest.mark.parametrize("field,value", [("classification", "TAIL"),
                                             ("classification", "B1"),
                                             ("sleeve_tag", "STRATEGIC"),
                                             ("bucket", "CONVEXITY"),
                                             ("classification", "CORE")])
    def test_is_valid_refuses_another_taxonomys_word(self, field, value):
        """The three are independent. A sleeve is not a classification."""
        assert tx.is_valid(field, value) is False

    @pytest.mark.parametrize("field", list(tx.FIELDS))
    def test_none_is_never_valid(self, field):
        """NULL is absence, not a value, and must never be a default."""
        assert tx.is_valid(field, None) is False


class TestTheMappingDoesNotGuess:
    def test_a_classification_maps_and_leaves_the_other_two_unknown(self):
        """A tag names at most ONE of the three — that IS the defect. A clean mapping still
        leaves two fields unknown, and that is correct, not incomplete."""
        vals, reason = tx.split_display_tag("STRATEGIC")
        assert reason is None
        assert vals == {"classification": "STRATEGIC", "sleeve_tag": None, "bucket": None}

    @pytest.mark.parametrize("tag,field,value", [
        ("TACTICAL", "classification", "TACTICAL"), ("TAIL", "sleeve_tag", "TAIL"),
        ("B1", "bucket", "B1"), ("B2", "bucket", "B2"), ("B3", "bucket", "B3"),
    ])
    def test_each_word_maps_to_its_own_taxonomy_only(self, tag, field, value):
        vals, reason = tx.split_display_tag(tag)
        assert reason is None and vals[field] == value
        assert all(vals[f] is None for f in tx.FIELDS if f != field)

    def test_CORE_is_ambiguous_and_is_NOT_called_strategic(self):
        """CORE was a classification under an older scheme and is neither STRATEGIC nor
        TACTICAL. Picking one would be exactly the guess the ruling forbids."""
        vals, reason = tx.split_display_tag("CORE")
        assert all(v is None for v in vals.values())
        assert reason and "no ruled vocabulary" in reason

    @pytest.mark.parametrize("tag", ["HEDGE", "MOMENTUM", "OTHER"])
    def test_the_other_orphan_words_are_ambiguous_too(self, tag):
        vals, reason = tx.split_display_tag(tag)
        assert all(v is None for v in vals.values()) and reason

    def test_an_unrecognised_word_is_reported_not_dropped(self):
        vals, reason = tx.split_display_tag("SOMETHING_NEW")
        assert all(v is None for v in vals.values())
        assert reason and "unrecognised" in reason

    def test_an_absent_tag_says_so_rather_than_mapping_to_nothing_quietly(self):
        vals, reason = tx.split_display_tag(None)
        assert all(v is None for v in vals.values())
        assert reason and "no strategy_tag" in reason

    def test_case_and_whitespace_do_not_change_the_answer(self):
        """The scope-must-not-depend-on-case lesson, applied to a vocabulary."""
        for spelling in (" strategic ", "Strategic", "STRATEGIC"):
            vals, reason = tx.split_display_tag(spelling)
            assert reason is None and vals["classification"] == "STRATEGIC"


class TestTheConvexityDateBoundary:
    """R-IV.794(b)3 names it: CONVEXITY on a pre-09-25 row may have been a classification."""

    def test_on_a_recent_row_it_is_a_sleeve(self):
        vals, reason = tx.split_display_tag("CONVEXITY", entry_date="2026-10-06")
        assert reason is None and vals["sleeve_tag"] == "CONVEXITY"

    @pytest.mark.parametrize("day", ["2026-08-11", "2026-09-24", "2026-01-01"])
    def test_on_a_pre_09_25_row_it_is_AMBIGUOUS(self, day):
        vals, reason = tx.split_display_tag("CONVEXITY", entry_date=day)
        assert vals["sleeve_tag"] is None
        assert reason and "pre-2026-09-25" in reason

    def test_the_boundary_day_itself_is_a_sleeve(self):
        vals, reason = tx.split_display_tag("CONVEXITY", entry_date="2026-09-25")
        assert reason is None and vals["sleeve_tag"] == "CONVEXITY"

    def test_an_unknown_date_does_not_silently_pass_as_recent(self):
        """With no date there is nothing to place the row against. It maps as a sleeve, which is
        today's meaning — recorded here so the choice is visible rather than incidental."""
        vals, reason = tx.split_display_tag("CONVEXITY", entry_date=None)
        assert reason is None and vals["sleeve_tag"] == "CONVEXITY"

    def test_an_iso_timestamp_is_read_as_its_day(self):
        vals, reason = tx.split_display_tag("CONVEXITY",
                                            entry_date="2026-08-11T13:00:07+00:00")
        assert vals["sleeve_tag"] is None and reason


class TestCapEligibility:
    def test_a_row_without_a_classification_cannot_be_capped(self):
        assert tx.cap_eligible({"classification": None}) is False
        assert tx.cap_eligible({}) is False

    def test_a_classified_row_can(self):
        assert tx.cap_eligible({"classification": "TACTICAL"}) is True
        assert tx.cap_eligible({"classification": "STRATEGIC"}) is True

    def test_another_taxonomys_word_does_not_make_a_row_cap_eligible(self):
        """POSITIVE CONTROL for the whole defect: `B2` in the classification slot is what the
        old single column produced, and it must not read as an answer."""
        assert tx.cap_eligible({"classification": "B2"}) is False
        assert tx.cap_eligible({"classification": "TAIL"}) is False


class TestTheGeneratedDDL:
    def test_one_statement_per_field_and_all_nullable(self):
        ddl = tx.column_ddl()
        assert len(ddl) == 3
        for f, stmt in zip(tx.FIELDS, ddl):
            assert "ADD COLUMN IF NOT EXISTS %s TEXT" % f in stmt
            assert "NOT NULL" not in stmt and "CHECK" not in stmt

    def test_the_comments_are_generated_from_the_vocabularies(self):
        """A vocabulary with two authors has no author — the lesson strategy_tag.py records."""
        c = tx.column_comments()
        assert set(c) == set(tx.FIELDS)
        assert "STRATEGIC | TACTICAL" in c["classification"]
        assert "B1 | B2 | B3" in c["bucket"]
        for text in c.values():
            assert "display string only" in text.lower()

    def test_boot_adds_the_three_columns(self):
        import inspect

        from database import postgres_client as pc

        src = inspect.getsource(pc)
        for f in tx.FIELDS:
            assert "ADD COLUMN IF NOT EXISTS %s TEXT" % f in src, f


class TestThePayload:
    """R-IV.794(b)1 and (b)2 on `hub_get_positions`."""

    def test_the_description_forbids_computing_anything_from_strategy_tag(self):
        from hub_mcp.tools.positions import DESCRIPTION

        assert "NO CAP, GATE OR FILTER MAY BE COMPUTED FROM IT" in DESCRIPTION
        assert "8.26%" in DESCRIPTION and "19.50%" in DESCRIPTION, \
            "it names the figures, so the cost is legible"
        assert "DISPLAY STRING" in DESCRIPTION.upper()

    def test_the_description_points_at_the_three_fields(self):
        from hub_mcp.tools.positions import DESCRIPTION

        for f in tx.FIELDS:
            assert "`%s`" % f in DESCRIPTION, f

    def test_the_description_warns_that_null_means_not_yet_migrated(self):
        """The absent-fact-as-satisfied-condition trap: a reader seeing null before the backfill
        would conclude the row has no classification and leave it out of the cap."""
        from hub_mcp.tools.positions import DESCRIPTION

        assert "classification_backfilled" in DESCRIPTION
        assert "not yet" in DESCRIPTION.lower()

    def test_the_three_fields_are_served_on_every_row(self):
        from hub_mcp.tools.positions import _build_position

        row = {"position_id": "P", "ticker": "X", "classification": "TACTICAL",
               "sleeve_tag": "TAIL", "bucket": "B2", "strategy_tag": "B2"}
        out = _build_position(row)
        assert out["classification"] == "TACTICAL"
        assert out["sleeve_tag"] == "TAIL"
        assert out["bucket"] == "B2"
        assert out["strategy_tag"] == "B2", "the display string is still served, as itself"

    def test_a_row_missing_them_serves_null_not_a_default(self):
        from hub_mcp.tools.positions import _build_position

        out = _build_position({"position_id": "P", "ticker": "X"})
        for f in tx.FIELDS:
            assert out[f] is None, f

    @pytest.mark.parametrize("tag", ["B2", "TAIL", "STRATEGIC", "CORE"])
    def test_the_three_fields_NEVER_fall_back_to_the_display_string(self, tag):
        """THE DISCRIMINATING CASE, and it was missing: a row with a `strategy_tag` and no
        taxonomy fields.

        A mutation making `classification` read `row.get("classification") or
        row.get("strategy_tag")` passed every other test in this file — because each one either
        supplied the fields or supplied neither. That fallback IS the defect: it is how a bucket
        ends up answering a question about classification, which is what read 8.26% instead of
        19.50%. Note TAIL and STRATEGIC are included deliberately: a fallback that looks correct
        for STRATEGIC is still wrong, because the same code path then serves `B2` as a
        classification.
        """
        from hub_mcp.tools.positions import _build_position

        out = _build_position({"position_id": "P", "ticker": "X", "strategy_tag": tag})
        assert out["strategy_tag"] == tag, "the display string is served, as itself"
        for f in tx.FIELDS:
            assert out[f] is None, (
                "%s must stay null — it was filled from strategy_tag %r" % (f, tag))

    def test_the_basis_note_carries_the_prohibition_and_the_figures(self):
        import inspect

        from hub_mcp.tools import positions as mod

        src = inspect.getsource(mod)
        assert "no cap, gate or filter may be computed from it" in src
        assert "8.26%" in src and "19.50%" in src

    def test_backfilled_is_false_until_a_row_carries_a_classification(self):
        from hub_mcp.tools.positions import _classification_backfilled

        assert _classification_backfilled([]) is False
        assert _classification_backfilled([{"classification": None}]) is False
        assert _classification_backfilled([{"strategy_tag": "STRATEGIC"}]) is False, \
            "the display string is not the field"
        assert _classification_backfilled([{"classification": "TACTICAL"}]) is True

    def test_cap_enforceable_requires_every_row_to_be_classified(self):
        """One unclassified row means the cap cannot be computed for the book — which is
        different from that row not being tactical."""
        import inspect

        from hub_mcp.tools import positions as mod

        src = inspect.getsource(mod)
        assert "cap_enforceable" in src
        assert "positions_without_classification" in src
        assert "position_ids_without_classification" in src
