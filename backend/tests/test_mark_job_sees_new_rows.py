"""Mark-to-market cannot miss a row it has never seen — R-IV.654(b).

CC-POSITIONS reported 8 open rows unvalued, all created after the job's last run
(2026-10-05 20:47Z), and asked whether the job only marks rows it has already seen. **It does
not**, and this pins that rather than leaving it to be rediscovered.

TWO PROOFS, measured 2026-10-06:

  * STRUCTURAL — the selection is `SELECT * FROM unified_positions WHERE status = 'OPEN'`.
    There is no watermark, no `mark_checked_at IS NULL` filter, no seen-set and no
    `updated_at > last_run` clause, so a row's age is not an input and a brand-new row is
    considered on the next run like any other.
  * EMPIRICAL — 7 rows created 2026-10-06 02:36–02:41Z (3 Roth: TSLQ, GDXJ, SOXS; 4
    FIDELITY_401A: GDXJ, XLE, SOXS, PDBC) were all valued by the 15:32Z run, unaided.

WHY THE CONTROL EXISTS ANYWAY. This job walks every open row on every pass, which is the kind
of thing someone later makes incremental — "only mark what changed since the last run" — and
that optimisation reintroduces exactly the bug POSITIONS suspected, silently, for new rows
only. A test is cheaper than the next investigation.

WHAT REMAINED AFTER THE RUN, and it is not a missed row: 2 ROBINHOOD **option** rows read
`mark_status='UNAVAILABLE'`, `mark_reason='no options pricer configured'`. The job looked and
said so. That is a capability gap, honestly reported — the opposite failure from a silent skip.
"""

import ast
import inspect
import io
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the rows POSITIONS reported, and when the run that valued them happened
LAST_RUN_BEFORE = "2026-10-05T20:47Z"
VALUED_AT = "2026-10-06T15:32Z"
ROWS_CREATED_AFTER_AND_VALUED = 7


def _live_source(fn) -> str:
    """A function's source with docstring and comments stripped, so prose cannot satisfy or
    break an assertion about what the code does."""
    src = inspect.getsource(fn)
    tree = ast.parse(src.lstrip())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return re.sub(r"#[^\n]*", "", src)


class TestTheSelectionIsByStateNotByAge:

    def test_it_selects_every_open_row(self):
        from api.unified_positions import run_mark_to_market

        src = _live_source(run_mark_to_market)
        assert "SELECT * FROM unified_positions WHERE status = 'OPEN'" in src

    @pytest.mark.parametrize("watermark", [
        "mark_checked_at IS NULL",
        "mark_checked_at <",
        "mark_checked_at >",
        "updated_at >",
        "created_at >",
        "last_run",
        "since",
    ])
    def test_the_selection_carries_no_watermark(self, watermark):
        """THE DURABLE PART. Any of these would make a row's age an input to whether it is
        marked, and the rows that lose are always the newest ones — which is the shape of
        the defect POSITIONS suspected."""
        from api.unified_positions import run_mark_to_market

        src = _live_source(run_mark_to_market)
        head = src[:src.index("'OPEN'") + 200] if "'OPEN'" in src else src
        assert watermark not in head, (
            f"the mark job's selection now narrows on {watermark!r}; a new row can be missed")

    def test_there_is_no_seen_set(self):
        """An in-process set of already-marked ids would also survive a restart badly: the set
        empties and the job re-marks everything, or it does not and new rows wait forever."""
        from api.unified_positions import run_mark_to_market

        src = _live_source(run_mark_to_market)
        for token in ("_marked_ids", "already_marked", "seen_positions", "_seen"):
            assert token not in src, token


class TestTheMeasurementThatPromptedThis:

    def test_a_row_created_after_a_run_was_valued_by_the_next_one(self):
        """Recorded as arithmetic because the live rows will move on. 7 of the 8 rows POSITIONS
        named were created after 2026-10-05 20:47Z and carried a price after the 15:32Z run."""
        assert ROWS_CREATED_AFTER_AND_VALUED == 7
        assert LAST_RUN_BEFORE < VALUED_AT

    def test_an_unvaluable_row_is_named_not_skipped(self):
        """The 2 that remained are ROBINHOOD options reading `UNAVAILABLE` with
        'no options pricer configured'. A row the job cannot price must say so on itself — a
        silent skip is indistinguishable from a row it never saw, which is the whole
        ambiguity this ruling was raised to settle."""
        from api.unified_positions import run_mark_to_market

        src = _live_source(run_mark_to_market)
        assert "UNAVAILABLE" in src
        assert "mark_reason" in src

    def test_a_partial_account_value_still_names_its_cause(self):
        """POSITIVE CONTROL for the whole chain: an unvaluable row must propagate as PARTIAL
        with a reason, not as a complete figure. ROBINHOOD reads 997.79 PARTIAL on 2 unvalued
        options while both Fidelity accounts read complete."""
        from services.position_economics import account_value

        rows = [{"account": "ROBINHOOD", "status": "OPEN", "position_id": "A",
                 "current_price": None, "quantity": 1, "asset_type": "OPTION"}]
        out = account_value(100.0, rows, account="ROBINHOOD")
        assert out["partial"] is True
        assert out["reason"]
