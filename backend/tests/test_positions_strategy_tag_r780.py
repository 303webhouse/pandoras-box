"""hub_get_positions serves strategy_tag — R-IV.780(e)1.

THE DEFECT. `services/read_only/positions.py` does `SELECT *`, so `strategy_tag` was always in
the row dict. It was `hub_mcp/tools/positions.py`'s own projection — an explicit dict of ~25
keys — that dropped it. No agent could read a bucket, which made X4, X10 and B3's limits
unenforceable from the hub even though the data was sitting in the row the tool had in hand.

That is worth naming precisely: the field was not missing, not stale, and not unqueryable. It was
*omitted from a hand-written dict*, which is the one failure a `SELECT *` cannot protect against.

MEASURED 2026-10-09 across the 32 open rows, before anything was changed:
  classification  STRATEGIC 8 (rows 968-975 exactly, no others), TACTICAL 1 (row 976), CORE 1
  sleeve          TAIL 10, CONVEXITY 8
  TA buckets      B1 7, B2 6
  no tag          4 -- ABNB 379, HYG 516, META 527, XLF 978, all ROBINHOOD options
So ONE column carries FOUR vocabularies, and serving it does not make every row classifiable.
"""
import inspect

import pytest

from hub_mcp.tools import positions as P


def _row(**kw):
    base = {"position_id": "POS_X", "ticker": "X", "account": "ROBINHOOD", "status": "OPEN",
            "structure": "stock", "quantity": 1}
    base.update(kw)
    return base


class TestTheFieldIsServed:
    def test_a_stored_tag_reaches_the_payload(self):
        assert P._build_position(_row(strategy_tag="TAIL"))["strategy_tag"] == "TAIL"

    @pytest.mark.parametrize("tag", ["STRATEGIC", "TACTICAL", "CORE", "TAIL", "CONVEXITY",
                                     "B1", "B2"])
    def test_every_vocabulary_in_use_passes_through_unchanged(self, tag):
        """All four vocabularies, served raw. A test that only covered TAIL would pass while the
        code lower-cased or re-mapped the others."""
        assert P._build_position(_row(strategy_tag=tag))["strategy_tag"] == tag

    def test_an_absent_tag_is_None_and_NOT_a_default_bucket(self):
        """None is the honest answer. Substituting a bucket here would enforce a limit the
        principal never assigned, which is worse than not enforcing one."""
        assert P._build_position(_row())["strategy_tag"] is None
        assert P._build_position(_row(strategy_tag=None))["strategy_tag"] is None

    def test_the_tag_is_not_translated_between_vocabularies(self):
        """POSITIVE CONTROL for 'never inferred'. TAIL is a sleeve, not a classification, and the
        tool must not answer 'is this tactical?' by guessing. If anyone later maps TAIL ->
        TACTICAL here, this fails."""
        assert P._build_position(_row(strategy_tag="TAIL"))["strategy_tag"] != "TACTICAL"
        assert P._build_position(_row(strategy_tag="B2"))["strategy_tag"] != "TACTICAL"


class TestTheProjectionIsTheThingThatDroppedIt:
    def test_the_builder_reads_the_key_from_the_row(self):
        src = inspect.getsource(P._build_position)
        assert '"strategy_tag": row.get("strategy_tag")' in src

    def test_the_service_select_still_carries_every_column(self):
        """The service was never the fault and must not be 'fixed'. If someone narrows this
        SELECT to a column list, the next added field disappears the same way."""
        from services.read_only import positions as svc
        assert "SELECT * FROM unified_positions" in inspect.getsource(svc.list_positions)

    def test_the_DESCRIPTION_promises_the_field(self):
        """The committee reads the description to decide whether it can enforce a limit. A
        payload that carries a field the description never mentions is the R-IV.761(d) fault.

        UPDATED BY TA-123 / R-IV.794(b)1. This used to assert the description told a reader to
        "read it for X4, X10 and B3's limits". That instruction is now FORBIDDEN -- strategy_tag
        mixes three taxonomies and a cap read from it reads 8.26% against a true 19.50%. So the
        test keeps the parts that still hold (the field is named, values are never inferred) and
        asserts the old instruction is GONE, rather than being loosened to pass.
        """
        assert "strategy_tag" in P.DESCRIPTION
        assert "never inferred" in P.DESCRIPTION.lower()
        for v in ("STRATEGIC", "TACTICAL", "TAIL", "CONVEXITY", "B1", "B2", "B3"):
            assert v in P.DESCRIPTION, v
        # The prohibition, and the three fields that replace it.
        assert "NO CAP, GATE OR FILTER MAY BE COMPUTED FROM IT" in P.DESCRIPTION
        for f in ("classification", "sleeve_tag", "bucket"):
            assert "`%s`" % f in P.DESCRIPTION, f
        # And the instruction it replaced must not still be sitting there beside it.
        assert "Read it for X4" not in P.DESCRIPTION


class TestCoverageIsPublished:
    """Serving the field and the book being classified are different claims."""

    def test_untagged_rows_are_counted_and_listed(self):
        rows = [_row(position_id="POS_A", strategy_tag="TAIL"),
                _row(position_id="POS_B"),
                _row(position_id="POS_C", strategy_tag=None)]
        built = [P._build_position(r) for r in rows]
        untagged = [p["position_id"] for p in built if not p.get("strategy_tag")]
        assert untagged == ["POS_B", "POS_C"]

    def test_the_envelope_publishes_the_count(self):
        src = inspect.getsource(P.hub_get_positions)
        assert "positions_without_strategy_tag" in src
        assert "untagged_position_ids" in src
        assert "strategy_tag_basis" in src

    def test_the_summary_says_it_when_rows_are_untagged(self):
        src = inspect.getsource(P.hub_get_positions)
        assert "carry no strategy_tag" in src

    def test_an_empty_string_counts_as_untagged_not_as_a_tag(self):
        """`''` is not a bucket. A falsy check is deliberate: a blank written by a form must not
        read as a classification."""
        built = P._build_position(_row(strategy_tag=""))
        assert not built["strategy_tag"]
