"""One fact, two columns, one author — R-IV.584(a)–(e).

Every test names the defect it holds shut. Negatives carry positive controls (#30).
"""

import ast
import io
import os
from datetime import timedelta

import pytest

from models.signal_lifecycle import (ACCEPTED_OPTIONS, ACCEPTED_STOCKS, ACTIVE,
                                     COMMITTEE_REVIEW, DECIDED_STATES, DISMISSED, EXPIRED,
                                     HIGH_SCORE_THRESHOLD, LIVE_STATES, SELECTED, SHADOW,
                                     STATES, STATUS_VALUES, TERMINAL_STATES, WITHHELD,
                                     columns_for, is_high_score, is_live, is_terminal,
                                     score_of, state_of, status_check_sql)
from models.signal_timeframe import (INTRADAY, SWING, WEEKLY, UnknownTimeframe, band_of,
                                     is_intraday, ttl_for)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


EXEMPT_FUNCTIONS = {"init_database"}


def _sql_by_function(rel):
    """[(enclosing function name, string literal), ...] for one module.

    Per FUNCTION, because a whole-file text scan cannot tell a live writer from a boot
    migration, and a test that cannot tell them apart either passes for the wrong reason or
    fails for one.
    """
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    tree = ast.parse(src)
    owner = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            for child in ast.walk(node):
                if (isinstance(child, ast.Constant) and isinstance(child.value, str)
                        and child.value != doc):
                    owner.setdefault(id(child), node.name)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((owner.get(id(node), "<module>"), node.value))
    return out


def _code_without_docstrings(rel):
    # utf-8-sig: `scheduler/bias_scheduler.py` carries a byte-order mark (it predates this
    # work -- it is in HEAD), and `ast.parse` refuses U+FEFF as a non-printable character.
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return src


# ───────────────────────────────── (e) one fact, two columns

class TestTheTwoColumnsAreOneFact:

    def test_every_state_owns_both_columns(self):
        for state in STATES:
            status, action = columns_for(state)
            assert status in STATUS_VALUES, state
            assert action is None or isinstance(action, str), state

    def test_a_state_round_trips(self):
        for state in STATES:
            assert state_of(*columns_for(state)) == state

    def test_the_pairs_are_unique(self):
        """Two states sharing a pair would make `state_of` ambiguous, and it would answer with
        whichever came first in the dict — a silent misclassification."""
        pairs = [columns_for(s) for s in STATES]
        assert len(set(pairs)) == len(pairs), pairs

    def test_the_754_row_condition_reads_as_no_state(self):
        """THE DEFECT. `status=COMMITTEE_REVIEW` with `user_action=DISMISSED` is what 697 rows
        held for up to 147 days: dismissed by the principal, still reading as pending."""
        assert state_of("COMMITTEE_REVIEW", "DISMISSED") is None
        assert state_of("COMMITTEE_REVIEW", "EXPIRED") is None
        assert state_of("DISMISSED", None) is None
        # POSITIVE CONTROL: the states that ARE coherent still resolve.
        assert state_of("COMMITTEE_REVIEW", None) == COMMITTEE_REVIEW
        assert state_of("DISMISSED", "DISMISSED") == DISMISSED

    def test_is_terminal_is_not_the_negation_of_is_live(self):
        """A row in no state is neither, and calling it terminal is how 697 dismissed rows
        stayed parked as though they were pending something."""
        assert not is_live("COMMITTEE_REVIEW", "DISMISSED")
        assert not is_terminal("COMMITTEE_REVIEW", "DISMISSED")
        # POSITIVE CONTROL
        assert is_live("ACTIVE", None)
        assert is_terminal("EXPIRED", "EXPIRED")

    def test_shadow_and_withheld_are_not_outcomes(self):
        """`status != 'ACTIVE'` counts both as results. Neither is: nobody judged them."""
        assert SHADOW not in TERMINAL_STATES
        assert WITHHELD in TERMINAL_STATES        # over, yes
        assert WITHHELD not in DECIDED_STATES     # but not the principal's decision
        assert EXPIRED not in DECIDED_STATES
        assert DISMISSED in DECIDED_STATES

    def test_selected_keeps_its_status_active_on_purpose(self):
        """`api/accept_flow` refuses anything not ACTIVE. Moving the status here would block
        the very next step — creating the position."""
        assert columns_for(SELECTED) == (ACTIVE, "SELECTED")
        assert SELECTED not in LIVE_STATES

    def test_the_expiry_sweep_never_writes_the_principals_word(self):
        """R-IV.434(b): the legacy feeds hide a ticker for 24h on `user_action='DISMISSED'`.
        A system expiry must not fire that."""
        assert columns_for(EXPIRED)[1] == "EXPIRED"
        assert columns_for(WITHHELD)[1] == "WITHHELD"
        assert columns_for(DISMISSED)[1] == "DISMISSED"

    def test_an_unknown_state_is_refused(self):
        with pytest.raises(ValueError):
            columns_for("PENDING_REVIEW")

    def test_the_check_constraint_is_generated_not_retyped(self):
        sql = status_check_sql()
        for value in STATUS_VALUES:
            assert "'" + value + "'" in sql
        # SELECTED is a STATE whose status stays ACTIVE. Generating the constraint from STATES
        # would permit a status value nothing ever writes.
        assert "'SELECTED'" not in sql
        assert "SELECTED" in STATES
        src = _code_without_docstrings("database/postgres_client.py")
        assert "_SIGNAL_STATUS_VALUES" in src


class TestOnlyOneModuleWritesTheColumns:

    WRITERS = ["signals/pipeline.py", "database/postgres_client.py",
               "scheduler/bias_scheduler.py", "api/trade_ideas.py"]

    @pytest.mark.parametrize("rel", WRITERS)
    def test_no_live_path_sets_either_column_by_hand(self, rel):
        """Five writers each moved one half. The SQL that did it is gone from all of them.

        Scanned per function, and `init_database` is EXEMPT and separately pinned below: it
        holds five one-time historical migrations that write `status` (the April 2026 stuck-
        COMMITTEE_REVIEW cleanup, the PENDING_REVIEW backlog sweep, and three NULL-status
        backfills). They are not lifecycle writers, they are boot migrations, and each is
        already a no-op against the live table.
        """
        offenders = []
        for fn, sql in _sql_by_function(rel):
            if fn in EXEMPT_FUNCTIONS:
                continue
            if "UPDATE signals" not in sql:
                continue
            if "SET status" in sql or "SET user_action" in sql:
                offenders.append((fn, sql.strip()[:120]))
        assert not offenders, (rel, offenders)

    def test_the_boot_migrations_are_the_only_exemption_and_are_no_ops(self):
        """POSITIVE CONTROL for the exemption. If `init_database`'s writes were NOT already
        no-ops, exempting them would be hiding live writers — so this pins what makes them
        safe: every one is scoped to a condition the live table no longer satisfies.

        Census 2026-09-25 (23,144 rows): 0 with `status IS NULL`, 0 at PENDING_REVIEW, and the
        two hard-coded signal_ids were cleaned in April.
        """
        found = [sql for fn, sql in _sql_by_function("database/postgres_client.py")
                 if fn == "init_database" and "UPDATE signals" in sql
                 and ("SET status" in sql or "SET user_action" in sql)]
        assert len(found) == 5, len(found)
        for sql in found:
            assert ("status IS NULL" in sql
                    or "status = 'COMMITTEE_REVIEW'" in sql
                    or "status = 'PENDING_REVIEW'" in sql), sql.strip()[:160]

    def test_the_author_itself_does_write_them(self):
        """POSITIVE CONTROL for the scan above: it would catch the statement if one were
        there, so a clean result on the four writers means they are clean."""
        code = _code_without_docstrings("services/signal_lifecycle.py")
        assert "SET status = $2, user_action = $3" in code

    def test_the_only_writer_that_was_correct_kept_its_scope(self):
        """`expire_stale_signals` was the one writer that moved both columns — and its
        `WHERE status = 'ACTIVE'` is why a drifted row could never come back. The scope stays
        (expiring a finished row is not its job) but as a COUNTED refusal, not a silent miss."""
        code = _code_without_docstrings("api/trade_ideas.py")
        assert "only_if=[_ACTIVE]" in code
        assert 'outcome["unchanged"]' in code


# ───────────────────────────────── (b) the auto-promote

class TestTheAutoPromoteIsOff:

    def test_nothing_writes_committee_review_automatically(self):
        """750 rows were promoted on score alone and NOT ONE ever carried committee_data —
        25 to 81 a week, every one scoring 85 to 100, into a queue nothing drains."""
        code = _code_without_docstrings("signals/pipeline.py")
        assert "AUTO_PROMOTE_THRESHOLD" not in code
        assert "COMMITTEE_REVIEW" not in code

    def test_the_manual_analyze_click_still_works(self):
        """POSITIVE CONTROL: the ruling retired the AUTOMATIC promote, not the principal's
        own request for a review."""
        assert COMMITTEE_REVIEW in STATES
        code = _code_without_docstrings("api/trade_ideas.py")
        assert "COMMITTEE_REVIEW" in code

    def test_the_threshold_survives_as_a_flag(self):
        assert HIGH_SCORE_THRESHOLD == 85.0
        assert is_high_score(85.0) is True
        assert is_high_score(100) is True
        assert is_high_score(84.99) is False

    def test_the_flag_survives_the_values_that_break_guards(self):
        """`float("nan")` passes every `if not x` check and every `<= 0` comparison."""
        assert is_high_score(None) is False
        assert is_high_score(float("nan")) is False
        assert is_high_score("not a number") is False
        # POSITIVE CONTROL: a numeric string still reads.
        assert is_high_score("90") is True

    def test_the_flag_reads_the_same_score_the_ranking_does(self):
        assert score_of({"score_v2": 90, "score": 10}) == 90.0
        assert score_of({"score": 70}) == 70.0
        assert score_of({"score_v2": None, "score": 70}) == 70.0
        assert score_of({"score_v2": float("nan"), "score": 70}) == 70.0
        assert score_of({}) is None

    def test_the_flag_is_derived_never_stored(self):
        """A stored flag is one more writer to fall out of step with the column it
        summarises — which is the whole lesson of the 754 rows."""
        code = _code_without_docstrings("signals/feed_service.py")
        # Computed on read, from the canonical score (R-IV.590(c) moved which number that is).
        # Asserted on the CALL, not on one line's exact text, so the next change to how the
        # number is obtained does not fail this for the wrong reason.
        assert "is_high_score(" in code and "tag_row" in code
        for rel in ("signals/pipeline.py", "database/postgres_client.py"):
            assert "high_score" not in _code_without_docstrings(rel), rel
        # ...and it is never a column.
        import inspect

        from database import postgres_client as pc
        assert "high_score" not in inspect.getsource(pc.log_signal)


# ───────────────────────────────── (a) one timeframe vocabulary

class TestTheTimeframeVocabulary:

    @pytest.mark.parametrize("timeframe,band", [
        ("15", INTRADAY), ("60", INTRADAY), ("1H", INTRADAY), ("1h", INTRADAY),
        ("30M", INTRADAY), ("239", INTRADAY),
        ("240", SWING), ("4H", SWING), ("D", SWING), ("1D", SWING),
        ("DAILY", SWING), ("daily", SWING), ("Daily", SWING),
        ("W", WEEKLY), ("1W", WEEKLY), ("WEEKLY", WEEKLY), ("10080", WEEKLY),
    ])
    def test_every_live_spelling_lands_in_the_right_band(self, timeframe, band):
        assert band_of(timeframe) == band

    def test_the_two_spellings_of_one_hour_agree(self):
        """`"1H"` sat in the intraday tuple while `"60"` went down the digit branch. They
        reached the same answer by luck, not by construction."""
        assert band_of("1H") == band_of("60") == INTRADAY
        assert band_of("4H") == band_of("240") == SWING

    def test_the_bands_have_the_rivers_lifetimes(self):
        assert ttl_for("15") == timedelta(hours=4)
        assert ttl_for("DAILY") == timedelta(hours=24)
        assert ttl_for("W") == timedelta(days=7)

    def test_holy_grails_four_hours_is_right(self):
        """R-IV.581(b)1 asked whether Holy_Grail is daily-bar. It is not: its timeframe is
        `60`, so four hours is four bars."""
        assert band_of("60") == INTRADAY
        assert ttl_for("60") == timedelta(hours=4)

    @pytest.mark.parametrize("bad", [None, "", "  ", "nonsense", "0", "-5", "1 hour"])
    def test_an_unrecognised_spelling_is_refused_not_given_four_hours(self, bad):
        """THE DEFECT. The old fallback was four hours — the SHORTEST lifetime in the table —
        so a family writing an unknown spelling had its signals expire early, silently."""
        with pytest.raises(UnknownTimeframe):
            band_of(bad)
        with pytest.raises(UnknownTimeframe):
            ttl_for(bad)
        with pytest.raises(UnknownTimeframe):
            is_intraday(bad)

    def test_a_refusal_never_shortens_a_life(self):
        """`calculate_expiry` catches the refusal and returns None — no expiry — so the row
        falls to the 24-hour sweep rather than being cut to four hours."""
        code = _code_without_docstrings("signals/pipeline.py")
        assert "UnknownTimeframe" in code
        assert "timedelta(hours=4)" not in code

    def test_the_boundary_belongs_to_swing_and_not_to_both(self):
        assert band_of("239") == INTRADAY
        assert band_of("240") == SWING
        assert band_of("10079") == SWING
        assert band_of("10080") == WEEKLY


# ───────────────────────────────── R-IV.590(c): one score

class TestOneCanonicalScore:

    def test_the_flag_reads_the_number_the_pipeline_ranks_by(self):
        """THE DEFECT. The flag read `score_v2 ?? score` while the feed ranked by
        `adjusted_score ?? score_v2 ?? score`, and the two disagreed on 46 of 54 live rows.
        DE read 93 by the flag and 85 by the ranking: one row, one card, two numbers."""
        from models.signal_score import CANONICAL_SCORE_SQL, canonical_score

        assert CANONICAL_SCORE_SQL == "COALESCE(adjusted_score, score_v2, score, 0)"
        de = {"score": 88, "score_v2": 93, "adjusted_score": 85, "context_modifier": -3}
        assert canonical_score(de) == 85.0
        assert score_of(de) == 85.0                      # the flag now agrees
        assert is_high_score(score_of(de)) is True

    def test_the_precedence_is_the_order_bys_own(self):
        from models.signal_score import canonical_score

        assert canonical_score({"adjusted_score": 1, "score_v2": 2, "score": 3}) == 1.0
        assert canonical_score({"score_v2": 2, "score": 3}) == 2.0
        assert canonical_score({"score": 3}) == 3.0

    def test_no_score_is_not_a_score_of_zero(self):
        """The SQL coalesces to 0 so it can sort; this returns None. A row with no score and a
        row scoring zero are different claims, and a card showing 0 for "never scored" would
        state something nobody measured."""
        from models.signal_score import canonical_score

        assert canonical_score({}) is None
        assert canonical_score({"score": None, "score_v2": None}) is None
        assert canonical_score({"score_v2": float("nan"), "score": 70}) == 70.0
        assert is_high_score(canonical_score({})) is False
        # POSITIVE CONTROL: a real zero is a real number.
        assert canonical_score({"score": 0}) == 0.0

    def test_the_expression_is_written_once(self):
        """Three copies of the ORDER BY existed. One sentence now, interpolated."""
        for rel in ("api/trade_ideas.py", "signals/feed_service.py"):
            code = _code_without_docstrings(rel)
            assert "COALESCE(adjusted_score" not in code, rel
            assert "CANONICAL_SCORE_SQL" in code, rel

    def test_the_components_stay_visible(self):
        """A reader seeing 85 must be able to tell whether context moved it or whether a
        scorer was simply absent — the two cases this replaces."""
        from models.signal_score import score_components

        out = score_components({"score": 88, "score_v2": 93, "adjusted_score": 85,
                                "context_modifier": -3})
        assert out["source"] == "adjusted_score"
        assert out["score_v2"] == 93.0 and out["score"] == 88.0
        assert out["context_modifier"] == -3.0
        assert score_components({"score": 70})["source"] == "score"
        assert score_components({})["source"] is None
