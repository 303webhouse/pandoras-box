"""Amendment 5: a grade compares like with like — R-IV.647(c).

READ 2 FOUND A GRADE THAT MOVED AFTER IT WAS MADE: BTI 499789, **+0.3851 → −1.1908**. BTI
went ex-dividend on 2026-10-02 and the vendor's auto-adjusted series rescaled every earlier
close, while the entry stayed the raw price at fire. A series mismatch, not a market move.

THE CODE LOCATION, which the ruling did not have. `backtest/bars.py` already declared
`auto_adjust=False` and warned in its own docstring — *"stated, never a library default (the
default changed once)"*. But the Triton grader does not read through it. Its chain is

    triton_fresh_grade → triton_shadow_common → get_bars_yfinance
                       → _fetch_yfinance_bars → yf.download(...)

and that `yf.download` call **omitted `auto_adjust` entirely**, so it took the library
default, which yfinance 0.2.59 changed to True and announces at runtime: *"YF.download() has
changed argument auto_adjust default to True"*. The same trap the sibling module had been
written to avoid, one directory away.

MEASURED, and both figures reconcile to the cent against the two bases:

    entry (raw spot_at_fire)                        55.8350
    2026-09-28 close, auto_adjust=False             56.0500  →  +0.3851 %
    2026-09-28 close, auto_adjust=True              55.1701  →  −1.1908 %

Controls here are W1/W2 only — never W3, which has not been read.
"""

import ast
import io
import os
from datetime import date

import pytest

from jobs.triton_shadow_common import cumulative_split_ratio, split_adjusted_entry

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# BTI 499789, cohort W2. Entry is the row's stored raw price; the closes are the vendor's
# two bases for the 3-day horizon session, both measured 2026-10-05.
BTI_ENTRY = 55.8350
BTI_CLOSE_UNADJUSTED = 56.0500
BTI_CLOSE_DIVIDEND_ADJUSTED = 55.1701
BTI_GRADE_ORIGINAL = 0.3851
BTI_GRADE_MOVED = -1.1908


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


def _pct(entry, close):
    return round((close - entry) / entry * 100, 4)


# ─────────────────────── CONTROL 1: BTI 499789 returns to +0.3851

class TestBtiReturnsToItsOriginalGrade:

    def test_the_unadjusted_close_reproduces_the_original_grade(self):
        assert _pct(BTI_ENTRY, BTI_CLOSE_UNADJUSTED) == BTI_GRADE_ORIGINAL

    def test_the_adjusted_close_reproduces_the_moved_grade(self):
        """The other half of the diagnosis. Reproducing BOTH figures is what makes this a
        series mismatch rather than a market move — a market move would not be recoverable
        by changing one vendor flag."""
        assert _pct(BTI_ENTRY, BTI_CLOSE_DIVIDEND_ADJUSTED) == BTI_GRADE_MOVED

    def test_the_dividend_accounts_for_the_whole_gap(self):
        """BTI's 2026-10-02 dividend was 0.8350. The two 09-28 closes differ by 0.8799,
        which is that dividend carried back through the vendor's ratio — not a price."""
        assert round(BTI_CLOSE_UNADJUSTED - BTI_CLOSE_DIVIDEND_ADJUSTED, 4) == 0.8799

    def test_bti_has_no_split_so_the_split_clause_leaves_it_alone(self):
        """Measured: BTI has no split in 2026. The two clauses of 5(a) must not interfere —
        fixing the dividend basis must not move a row through the split path."""
        assert cumulative_split_ratio({}, date(2026, 9, 23), date(2026, 9, 28)) == 1.0
        assert split_adjusted_entry(BTI_ENTRY, 1.0) == BTI_ENTRY


# ─────────────────────── CONTROL 2: a row with no dividend or split is unchanged

class TestARowWithNeitherIsUnchanged:

    def test_no_split_leaves_the_entry_exactly_as_it_was(self):
        for entry in (1.00, 55.8350, 412.07, 10_000.0):
            assert split_adjusted_entry(entry, cumulative_split_ratio(
                {}, date(2026, 7, 1), date(2026, 7, 8))) == entry

    def test_a_split_outside_the_window_does_not_touch_it(self):
        """Before the fire, or after the graded session: neither is "between fire and
        grading", and counting one would move a grade that nothing happened to."""
        before = {date(2026, 6, 1): 2.0}
        after = {date(2026, 8, 1): 2.0}
        f, g = date(2026, 7, 1), date(2026, 7, 8)
        assert cumulative_split_ratio(before, f, g) == 1.0
        assert cumulative_split_ratio(after, f, g) == 1.0

    def test_the_ex_date_boundaries(self):
        """Exclusive of the fire session, inclusive of the graded one — a split whose ex-date
        IS the fire session is already in the raw price."""
        f, g = date(2026, 7, 1), date(2026, 7, 8)
        assert cumulative_split_ratio({f: 2.0}, f, g) == 1.0
        assert cumulative_split_ratio({g: 2.0}, f, g) == 2.0


# ─────────────────────── CONTROL 3: a split case (a real one, not synthetic)

class TestASplitCase:
    """NVDA's 10-for-1, ex-date 2024-06-10, read from the vendor by
    `get_splits_yfinance("NVDA", "2024-01-01", "2024-12-31")` → `{'2024-06-10': 10.0}`. The
    ruling allowed a synthetic case; a real one exists, so it is used."""

    NVDA_SPLITS = {date(2024, 6, 10): 10.0}

    def test_a_ten_for_one_divides_the_entry_by_ten(self):
        """A pre-split 1,200 is 120 on the scale the post-split closes are quoted in.
        WITHOUT this the grade would read −90% on a row where nothing happened."""
        f, g = date(2024, 6, 5), date(2024, 6, 12)
        ratio = cumulative_split_ratio(self.NVDA_SPLITS, f, g)
        assert ratio == 10.0
        assert split_adjusted_entry(1_200.0, ratio) == 120.0

    def test_the_unadjusted_entry_would_have_read_minus_ninety_percent(self):
        """The size of the error being removed, stated."""
        assert _pct(1_200.0, 122.0) == -89.8333
        assert _pct(120.0, 122.0) == 1.6667

    def test_a_horizon_before_the_split_is_untouched_and_one_after_is_adjusted(self):
        """PER HORIZON. A split between the 3d and 5d sessions must move one grade and not
        the other, which a single per-row adjustment would get wrong for one of them."""
        f = date(2024, 6, 5)
        assert cumulative_split_ratio(self.NVDA_SPLITS, f, date(2024, 6, 7)) == 1.0
        assert cumulative_split_ratio(self.NVDA_SPLITS, f, date(2024, 6, 12)) == 10.0

    def test_two_splits_compound(self):
        assert cumulative_split_ratio(
            {date(2024, 6, 10): 10.0, date(2024, 6, 11): 2.0},
            date(2024, 6, 5), date(2024, 6, 12)) == 20.0

    def test_an_unreadable_ratio_is_skipped_not_taken_as_one(self):
        """Taking it as 1.0 for the window would turn one unreadable action into a clean
        grade. The others still apply."""
        bad = {date(2024, 6, 10): 0, date(2024, 6, 11): 2.0, date(2024, 6, 12): None}
        assert cumulative_split_ratio(bad, date(2024, 6, 5), date(2024, 6, 12)) == 2.0

    @pytest.mark.parametrize("ratio", [0, -2.0, float("nan")])
    def test_an_impossible_ratio_yields_no_entry_rather_than_a_number(self, ratio):
        assert split_adjusted_entry(100.0, ratio) is None


# ─────────────────────── the basis is stated, never defaulted

class TestTheBasisIsStated:

    def test_the_fetch_requires_the_basis_and_has_no_default(self):
        """THE DURABLE PART. The call omitted `auto_adjust` and inherited a library default
        that changed under it. A required keyword cannot be inherited."""
        import inspect

        from integrations.uw_api import _fetch_yfinance_bars, get_bars_yfinance

        for fn in (_fetch_yfinance_bars, get_bars_yfinance):
            p = inspect.signature(fn).parameters["auto_adjust"]
            assert p.kind is inspect.Parameter.KEYWORD_ONLY, fn.__name__
            assert p.default is inspect.Parameter.empty, fn.__name__

    def test_the_download_passes_it_explicitly(self):
        code = _code("integrations/uw_api.py")
        assert "auto_adjust=auto_adjust" in code
        assert "yf.download(ticker, start=from_date, end=to_date, interval=\"1d\"," in code

    def test_the_grading_leg_asks_for_the_unadjusted_basis(self):
        code = _code("jobs/triton_shadow_common.py")
        assert "get_bars_yfinance(ticker.upper(), auto_adjust=False)" in code

    def test_the_general_path_keeps_its_old_behaviour_stated(self):
        """POSITIVE CONTROL: the change is narrow. `get_bars`'s yfinance fallback was on the
        library default (True) and stays there — but now says so, so the next default change
        cannot move it either."""
        code = _code("integrations/uw_api.py")
        assert "auto_adjust=True" in code

    def test_the_cache_key_carries_the_basis(self):
        """Without it, a series cached by one basis is served to a caller that asked for the
        other — the same mismatch arriving through the cache instead of the default."""
        code = _code("integrations/uw_api.py")
        assert 'aa={int(bool(auto_adjust))}' in code

    def test_the_entry_has_no_vendor_series_fallback(self):
        """Amendment 5(a) says the entry IS the raw price at fire. The fallback to
        `close_on_session` would have graded a row off an adjusted entry and read as clean.
        All 9,859 shadow rows carry a positive spot_at_fire, so it never fired."""
        code = _code("jobs/triton_fresh_grade.py")
        assert "no_raw_entry_price" in code
        assert "entry = close_on_session(idx, fd)" not in code

    def test_the_grade_records_the_basis_and_any_ratio_it_used(self):
        """A grade that cannot say what it was computed against cannot be re-checked after a
        vendor calendar changes — which is how read 2's grade became a mystery."""
        code = _code("jobs/triton_fresh_grade.py")
        assert '"price_basis"' in code
        assert '"split_ratios"' in code

    def test_the_split_adjustment_is_per_horizon(self):
        code = _code("jobs/triton_fresh_grade.py")
        i = code.index("_ratio = cumulative_split_ratio(splits, fd, tgt)")
        j = code.index("_dir_adj(_entry_k, close_k, direction)", i)
        assert j > i
        assert "split_adjusted_entry(entry, _ratio)" in code[i:j]
