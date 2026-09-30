"""What the 2026-09-30 rotation outage exposed — R-IV.610(c) and (d)."""

import ast
import io
import os

import pytest

from models.watchlist_priority import (LOW, NORMAL, PRIORITIES, RANK, UNKNOWN_RANK,
                                       order_by_sql, rank)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(rel):
    """Live code only: docstrings and comments both removed, spacing preserved."""
    import tokenize

    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    lines = src.splitlines(keepends=True)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
            lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
    except (tokenize.TokenError, IndentationError):
        pass
    return "".join(lines)


# ─────────────────── (c) "degraded" must name its subject

class TestHealthNamesTheFailingCheck:

    def test_the_status_is_derived_and_never_assigned(self):
        """THE DEFECT. Three checks could set `overall = "degraded"` and none recorded which
        one had. During the outage the route read `degraded` while the app could not reach the
        database at all, and only one nested block carried the real error.

        Deriving it means a check cannot degrade the hub without naming itself — the structural
        fix rather than a better label.
        """
        code = _code("main.py")
        assert 'overall = "degraded"' not in code
        assert '"status": "degraded" if degraded_by else "healthy"' in code
        assert '"degraded_by": degraded_by' in code

    def test_every_degrading_check_appends_a_reason(self):
        code = _code("main.py")
        assert 'degraded_by.append("postgres:%s" % postgres_state)' in code
        assert 'degraded_by.append("stable_jobs:' in code
        assert 'degraded_by.append("signals_freshness:' in code

    def test_the_postgres_reason_carries_its_state(self):
        """`postgres:error` and `postgres:disconnected` are different faults — one is an
        exception, the other a missing pool — and the reader should not have to guess which."""
        code = _code("main.py")
        assert 'if postgres_state in {"error", "disconnected"}:' in code
        assert "% postgres_state" in code


# ─────────────────── (c) a label has no natural order

class TestWatchlistPriority:

    def test_the_live_query_no_longer_coalesces_a_label_to_an_integer(self):
        """`ORDER BY COALESCE(priority, 999)` raised `COALESCE types character varying and
        integer cannot be matched` — the column is a NOT NULL label, so the COALESCE was both
        type-invalid and pointless, and the query had never once succeeded."""
        code = _code("analytics/price_collector.py")
        assert "COALESCE(priority, 999)" not in code
        assert "order_by_sql" in code

    def test_the_failure_is_no_longer_swallowed_at_debug(self):
        """It was `logger.debug`, so a watchlist contributing nothing read exactly like a
        watchlist with no rows. 189 unmuted rows were reaching the collector as zero."""
        code = _code("analytics/price_collector.py")
        assert 'logger.warning("watchlist_tickers unavailable' in code

    def test_the_known_labels_order_as_written(self):
        assert rank("normal") < rank("low")
        assert rank("high") < rank("normal")
        assert PRIORITIES == ("high", "normal", "low")

    def test_an_unknown_or_null_label_sorts_last_not_arbitrarily(self):
        for value in (None, "", "   ", "urgent", "9"):
            assert rank(value) == UNKNOWN_RANK, value
        assert UNKNOWN_RANK > max(RANK.values())

    def test_the_label_is_matched_case_insensitively(self):
        assert rank("NORMAL") == rank("normal") == RANK[NORMAL]
        assert rank(" Low ") == RANK[LOW]

    def test_the_sql_is_generated_from_the_rank_not_retyped(self):
        sql = order_by_sql("priority")
        for label in PRIORITIES:
            assert "WHEN '%s' THEN %d" % (label, RANK[label]) in sql
        assert "ELSE %d" % UNKNOWN_RANK in sql
        assert sql.startswith("CASE lower(priority)")

    def test_it_orders_a_column_by_any_name(self):
        assert order_by_sql("w.priority").startswith("CASE lower(w.priority)")


# ─────────────────── (d) an unreadable expiry is refused

class TestAnUnreadableExpiryIsRefused:

    def test_the_bare_pass_is_gone(self):
        """THE DEFECT. A mis-typed date created an option position with `expiry = NULL` and the
        route reported SUCCESS. The expiry sweep then cannot age it, `COALESCE(expiry,
        '2099-12-31')` sorts it last forever, and DTE is unknowable — while the principal saw a
        confirmation."""
        code = _code("api/unified_positions.py")
        i = code.index("expiry = date.fromisoformat(str(req.expiry)[:10])")
        window = code[i:i + 420]
        assert "raise HTTPException" in window
        assert "pass" not in window.split("raise HTTPException")[0]

    def test_the_message_says_what_to_type_and_that_nothing_was_written(self):
        """A date he can retype is worth more than a row he has to discover."""
        code = _code("api/unified_positions.py")
        assert "YYYY-MM-DD" in code
        assert "Nothing was written." in code

    def test_the_dte_is_computed_only_after_the_parse_succeeds(self):
        """It used to sit inside the same `try`, so a parse failure skipped it silently and the
        two nulls — bad date, and no date given — became one."""
        code = _code("api/unified_positions.py")
        i = code.index("expiry = date.fromisoformat(str(req.expiry)[:10])")
        j = code.index("dte = max(0, (expiry - date.today()).days)", i)
        assert "raise HTTPException" in code[i:j]

    def test_a_row_with_no_expiry_given_is_still_allowed(self):
        """POSITIVE CONTROL: the refusal is for an UNREADABLE expiry, not a missing one — a
        stock position has no expiry and must still be bookable."""
        code = _code("api/unified_positions.py")
        assert "if req.expiry:" in code
        i = code.index("if req.expiry:")
        assert "expiry = None" in code[max(0, i - 200):i]
