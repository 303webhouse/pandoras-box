"""R-IV.435(f) — a factor reading names the vendor that actually served it.

`get_price_history` reads UW FIRST for equity and ETF symbols (the branch is still called the
"Polygon primary path") and falls back to yfinance. Thirteen factor readings carried
`source="yfinance"` as a literal, so a UW-served reading said yfinance on its face.
"""
import ast
import inspect
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bias_engine import factor_utils as fu  # noqa: E402


def _frame(vendor=None):
    df = pd.DataFrame({"close": [1.0, 2.0]})
    return fu.tag_vendor(df, vendor) if vendor else df


def test_a_frame_carries_the_vendor_that_served_it():
    assert fu.price_vendor(_frame("uw")) == "uw"
    assert fu.price_vendor(_frame("yfinance")) == "yfinance"


def test_an_untagged_or_missing_frame_is_unknown_not_a_guess():
    assert fu.price_vendor(_frame()) == fu.VENDOR_UNKNOWN
    assert fu.price_vendor(None) == fu.VENDOR_UNKNOWN


def test_a_reading_built_from_two_vendors_says_so():
    assert fu.price_vendors(_frame("uw"), _frame("uw")) == "uw"
    assert fu.price_vendors(_frame("uw"), _frame("yfinance")) == "uw+yfinance"
    assert fu.price_vendors(None, None) == fu.VENDOR_UNKNOWN
    assert fu.price_vendors(_frame("uw"), None) == "uw"


def test_the_uw_path_tags_the_vendor_that_served_it_not_the_branch_it_took():
    """CORRECTED 2026-09-17: this asserted a literal "uw" on the UW branch, which is exactly
    the bug one layer down. get_bars() falls back to yfinance inside itself, so the branch
    says nothing about the vendor; only the frame does."""
    src = inspect.getsource(fu.get_price_history)
    assert 'return tag_vendor(polygon_df, served_by)' in src
    assert 'served_by = _frame_provider(polygon_df) or VENDOR_UNKNOWN' in src
    assert 'if served_by == "uw":' in src, "the primary is recorded only when uw served it"
    flat = " ".join(src.split())
    assert 'cache_key + ":vendor", PRICE_CACHE_TTL, served_by' in flat, (
        "the cached vendor must be the one that served the frame, not the branch's name")


def test_a_frame_carries_its_providers_stamp_out_of_the_bar_list():
    """The stamp exists per bar and used to die at the DataFrame boundary."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from integrations import uw_api
    bars = [{"o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "t": 1757980800000 + i * 86400000,
             "provider": "yfinance"} for i in range(3)]
    with patch.object(uw_api, "get_bars", new=AsyncMock(return_value=bars)):
        df = asyncio.run(uw_api.get_bars_as_dataframe("QQQ", days=3))
    assert uw_api.frame_provider(df) == "yfinance"


def test_a_mixed_or_unstamped_frame_does_not_claim_a_vendor():
    from integrations import uw_api
    assert uw_api.frame_provider_of([{"provider": "uw"}, {"provider": "yfinance"}]) is None
    assert uw_api.frame_provider_of([{"o": 1}]) is None
    assert uw_api.frame_provider(None) is None


def test_the_yfinance_path_is_announced_except_where_it_is_the_primary():
    src = inspect.getsource(fu.get_price_history)
    assert "if symbol not in _YFINANCE_ONLY_SYMBOLS:" in src
    assert 'record_substitution(PRICE_CONSUMER, "uw", "yfinance"' in src
    assert 'return tag_vendor(data, "yfinance")' in src


def test_the_vendor_survives_the_cache_in_its_own_key():
    """A DataFrame's attrs do not survive serialisation; a cached frame must not lose its vendor."""
    src = inspect.getsource(fu.get_price_history)
    assert 'cache_key + ":vendor"' in src
    assert src.count('cache_key + ":vendor"') >= 3        # read, uw write, yfinance write
    assert "cached_vendor or VENDOR_UNKNOWN" in src


def test_no_factor_still_hardcodes_the_vendor_where_a_frame_is_in_scope():
    """The rewrite is asserted over the tree, not per file, so a new factor cannot slip back."""
    root = Path(fu.__file__).resolve().parents[1] / "bias_filters"
    offenders = []
    for p in sorted(root.glob("*.py")):
        src = p.read_text(encoding="utf-8", errors="ignore")
        if not re.search(r'source\s*=\s*"yfinance"|"source"\s*:\s*"yfinance"', src):
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fetches = any(
                getattr(getattr(sub, "func", None), "id", None) == "get_price_history"
                or getattr(getattr(sub, "func", None), "attr", None) == "get_price_history"
                for sub in ast.walk(node) if isinstance(sub, ast.Call))
            if not fetches:
                continue
            body = "\n".join(src.split("\n")[node.lineno - 1:node.end_lineno])
            if re.search(r'source\s*=\s*"yfinance"|"source"\s*:\s*"yfinance"', body):
                offenders.append(f"{p.name}:{node.name}")
    assert offenders == [], offenders


def test_the_rewritten_factors_label_from_their_frames():
    root = Path(fu.__file__).resolve().parents[1] / "bias_filters"
    labelled = [p.name for p in sorted(root.glob("*.py"))
                if "price_vendors(" in p.read_text(encoding="utf-8", errors="ignore")]
    assert len(labelled) >= 11, labelled
    for name in ("breadth_momentum.py", "credit_spreads.py", "market_breadth.py",
                 "sector_rotation.py", "iv_regime.py"):
        assert name in labelled


# ── DEF-GEX-STALE-SPY-PRICE: a price carries its date and its vendor ───────────

def test_price_detail_carries_as_of_and_vendor():
    import asyncio
    from unittest.mock import AsyncMock, patch
    idx = pd.to_datetime(["2026-09-15", "2026-09-16"])
    df = fu.tag_vendor(pd.DataFrame({"close": [660.0, 754.2]}, index=idx), "uw")
    with patch.object(fu, "get_price_history", new=AsyncMock(return_value=df)):
        out = asyncio.run(fu.get_latest_price_detail("SPY"))
    assert out == {"price": 754.2, "as_of": "2026-09-16", "vendor": "uw"}
    with patch.object(fu, "get_price_history", new=AsyncMock(return_value=pd.DataFrame())):
        out = asyncio.run(fu.get_latest_price_detail("SPY"))
    assert out == {"price": None, "as_of": None, "vendor": fu.VENDOR_UNKNOWN}


def test_the_gex_payload_carries_the_price_provenance():
    from pathlib import Path
    src = (Path(fu.__file__).resolve().parents[1] / "bias_filters" / "gex.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "get_latest_price_detail(" in src
    assert '"spy_price_as_of"' in src and '"spy_price_vendor"' in src
