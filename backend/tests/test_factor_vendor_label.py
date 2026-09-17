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


def test_the_uw_path_tags_uw_and_records_the_primary():
    src = inspect.getsource(fu.get_price_history)
    assert 'return tag_vendor(polygon_df, "uw")' in src
    assert 'record_primary(PRICE_CONSUMER, "uw")' in src


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
