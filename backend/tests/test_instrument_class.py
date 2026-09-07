"""T5 — instrument classification (R-IV.279(e)).

Every expected value below comes from the LIVE /info read of 2026-09-06 recorded
in the module docstring, not from the endpoint's documentation.
"""

import pytest

from jobs import instrument_class as ic


class TestLiveVocabulary:
    """The four tickers actually read, with the values actually returned."""

    def test_spy_etf(self):
        assert ic.classify("SPY", "ETF") == ic.CLASS_ETF_BROAD

    def test_xlf_etf(self):
        assert ic.classify("XLF", "ETF") == ic.CLASS_ETF_SECTOR

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
        assert ic.classify("spy", "  etf ") == ic.CLASS_ETF_BROAD
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

    @pytest.mark.parametrize("c", [ic.CLASS_ETF_BROAD, ic.CLASS_ETF_SECTOR,
                              ic.CLASS_ETF_LEVERAGED_INVERSE, ic.CLASS_ETF_OTHER,
                              ic.CLASS_SINGLE_NAME, ic.CLASS_UNMAPPED])
    def test_everything_else_is(self, c):
        assert ic.is_gradeable(c) is True

    def test_unmapped_is_gradeable_deliberately(self):
        """Excluding on ignorance would silently shrink the population."""
        assert ic.is_gradeable(ic.CLASS_UNMAPPED) is True


class TestS3SubClasses:
    """R-IV.301(c). Static maps with a stated horizon."""

    def test_broad_index_etfs(self):
        for s in ["SPY", "QQQ", "IWM", "DIA"]:
            assert ic.classify(s, "ETF") == ic.CLASS_ETF_BROAD

    def test_spdr_sector_etfs(self):
        assert len(ic.SPDR_SECTOR_ETFS) == 11
        for s in ic.SPDR_SECTOR_ETFS:
            assert ic.classify(s, "ETF") == ic.CLASS_ETF_SECTOR

    def test_leveraged_inverse(self):
        for s in ["SOXL", "SOXS", "TQQQ", "SQQQ", "TZA", "FAZ"]:
            assert ic.classify(s, "ETF") == ic.CLASS_ETF_LEVERAGED_INVERSE

    def test_etf_other_is_not_unmapped(self):
        """The vendor POSITIVELY said ETF. Collapsing that into UNMAPPED would
        discard a measured fact — these six are the gap, not an unknown."""
        for s in ["COPX", "GLD", "HYG", "RSP", "SMH", "TLT"]:
            c = ic.classify(s, "ETF")
            assert c == ic.CLASS_ETF_OTHER
            assert c != ic.CLASS_UNMAPPED

    def test_smh_is_in_H_CORE4_and_is_not_broad(self):
        """H-CORE4 = {SPY, QQQ, IWM, SMH} is NOT homogeneous under S3."""
        assert ic.classify("SMH", "ETF") == ic.CLASS_ETF_OTHER
        assert ic.classify("SPY", "ETF") == ic.CLASS_ETF_BROAD

    def test_static_maps_have_a_stated_horizon(self):
        from datetime import date
        assert ic.STATIC_MAP_VALID_THROUGH == date(2027, 3, 31)
        assert ic.static_map_expired(date(2027, 3, 31)) is False
        assert ic.static_map_expired(date(2027, 4, 1)) is True

    def test_expiry_is_loud_and_refuses_a_stale_subclass(self, monkeypatch):
        """Past the horizon the map must not serve a sub-class it can no longer
        vouch for — reachability of the loud path, proven."""
        monkeypatch.setattr(ic, "static_map_expired", lambda *a, **k: True)
        assert ic.classify("SPY", "ETF") == ic.CLASS_ETF_OTHER


class TestS4Sector:
    """R-IV.301(b)."""

    def test_broad_index_etfs_are_BROAD(self):
        for s in ["SPY", "QQQ", "IWM", "DIA"]:
            assert ic.sector_for(s, ic.classify(s, "ETF")) == "BROAD"

    def test_spdr_sector_etfs_carry_their_sector(self):
        assert ic.sector_for("XLF", ic.CLASS_ETF_SECTOR) == "Financials"
        assert ic.sector_for("XLRE", ic.CLASS_ETF_SECTOR) == "Real Estate"

    def test_single_name_uses_info_sector(self):
        assert ic.sector_for("NVDA", ic.CLASS_SINGLE_NAME, "Technology") == "Technology"

    def test_single_name_with_null_vendor_sector_is_unmapped(self):
        assert ic.sector_for("ZZZZ", ic.CLASS_SINGLE_NAME, None) is None
        assert ic.sector_for("ZZZZ", ic.CLASS_SINGLE_NAME, "  ") is None

    def test_other_etfs_are_unmapped_for_sector(self):
        """Measured: /info returns sector=None for every ETF, so there is nothing
        to fall back to — this is the magnitude declared on the registration face."""
        for s in ["SMH", "GLD", "TLT", "HYG", "COPX", "RSP"]:
            assert ic.sector_for(s, ic.CLASS_ETF_OTHER) is None

    def test_leveraged_inverse_is_unmapped_for_sector(self):
        assert ic.sector_for("SOXS", ic.CLASS_ETF_LEVERAGED_INVERSE) is None
