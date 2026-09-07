"""T5 — instrument classification (R-IV.279(e)).

Every expected value below comes from the LIVE /info read of 2026-09-06 recorded
in the module docstring, not from the endpoint's documentation.
"""

import pytest

from jobs import instrument_class as ic


class TestLiveVocabulary:
    """The four tickers actually read, with the values actually returned."""

    def test_spy_etf(self):
        assert ic.classify("SPY", "ETF") == ic.CLASS_ETF

    def test_xlf_etf(self):
        assert ic.classify("XLF", "ETF") == ic.CLASS_ETF

    def test_nvda_common_stock(self):
        assert ic.classify("NVDA", "Common Stock") == ic.CLASS_SINGLE_NAME

    def test_spx_null_issue_type_still_classifies(self):
        """THE CASE THAT DICTATED THE ORDER. UW returns issue_type NULL for SPX,
        so a vendor-first implementation would return UNMAPPED for exactly the
        class this build exists to separate out."""
        assert ic.classify("SPX", None) == ic.CLASS_CASH_SETTLED_INDEX


class TestCashSettled:
    @pytest.mark.parametrize("sym", sorted(ic.CASH_SETTLED_INDEX_SYMBOLS))
    def test_all_five_classify_without_a_vendor_answer(self, sym):
        assert ic.classify(sym, None) == ic.CLASS_CASH_SETTLED_INDEX

    def test_the_five_are_exactly_the_def_list(self):
        assert ic.CASH_SETTLED_INDEX_SYMBOLS == {"SPX", "SPXW", "RUT", "RUTW", "VIX"}

    def test_cash_settled_wins_over_a_contradicting_issue_type(self):
        """If the vendor ever calls SPX an ETF, the list still wins — it encodes
        settlement, which is the property that makes the row ungradeable."""
        assert ic.classify("SPX", "ETF") == ic.CLASS_CASH_SETTLED_INDEX


class TestUnknownIsNeverGuessed:
    @pytest.mark.parametrize("val", [None, "", "   ", "Preferred Stock", "ADR", "Warrant"])
    def test_unrecognised_issue_type_is_unmapped(self, val):
        assert ic.classify("ZZZZ", val) == ic.CLASS_UNMAPPED

    def test_blank_ticker_is_unmapped(self):
        assert ic.classify("", "ETF") == ic.CLASS_UNMAPPED
        assert ic.classify(None, "ETF") == ic.CLASS_UNMAPPED

    def test_case_and_whitespace_insensitive(self):
        assert ic.classify("spy", "  etf ") == ic.CLASS_ETF
        assert ic.classify("nvda", "COMMON STOCK") == ic.CLASS_SINGLE_NAME


class TestIndexTickersIsNeverConsulted:
    def test_the_six_single_names_in_INDEX_TICKERS_classify_as_single_names(self):
        """The whole point of R-IV.279(e). INDEX_TICKERS holds these six; a
        classifier built on it would label them indices."""
        for sym in ["NVDA", "AVGO", "MSFT", "GOOGL", "AMZN", "META"]:
            assert ic.classify(sym, "Common Stock") == ic.CLASS_SINGLE_NAME

    def test_module_does_not_import_INDEX_TICKERS(self):
        import pathlib
        src = pathlib.Path(ic.__file__).read_text(encoding="utf-8")
        code = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
        body = code.split('"""', 2)[-1]          # past the docstring
        assert "INDEX_TICKERS" not in body


class TestGradeability:
    def test_cash_settled_is_not_gradeable(self):
        assert ic.is_gradeable(ic.CLASS_CASH_SETTLED_INDEX) is False

    @pytest.mark.parametrize("c", [ic.CLASS_ETF, ic.CLASS_SINGLE_NAME, ic.CLASS_UNMAPPED])
    def test_everything_else_is(self, c):
        assert ic.is_gradeable(c) is True

    def test_unmapped_is_gradeable_deliberately(self):
        """Excluding on ignorance would silently shrink the population."""
        assert ic.is_gradeable(ic.CLASS_UNMAPPED) is True
