"""DEF-BARS-NO-PROVENANCE — R-IV.108(a).

get_bars determines its provider at each return point and was discarding it. UW and
yfinance disagree by adjustment convention (the SOXS series showed 150x / 10.5x / 1x
plateaus against the raw ledger), so an unlabelled series cannot be used in a
benchmark arm without risking a silent provider mix inside one test (P10).

FAIL-FIRST: every assertion here fails against pre-fix uw_api.py, where neither the
constants nor the tagger existed and no bar carried a provider.
"""
from __future__ import annotations

import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from integrations.uw_api import (  # noqa: E402
    PROVIDER_UW, PROVIDER_YFINANCE, _tag_provider,
)


def _bars(n=3):
    return [{"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100, "t": 1767830400000 + i}
            for i in range(n)]


def test_every_bar_carries_its_provider():
    out = _tag_provider(_bars(3), PROVIDER_UW)
    assert len(out) == 3
    assert all(b["provider"] == PROVIDER_UW for b in out)


def test_providers_are_distinguishable():
    """The whole point: a UW series must not read as a yfinance one."""
    assert PROVIDER_UW != PROVIDER_YFINANCE
    uw = _tag_provider(_bars(2), PROVIDER_UW)
    yf = _tag_provider(_bars(2), PROVIDER_YFINANCE)
    assert {b["provider"] for b in uw} != {b["provider"] for b in yf}


def test_list_shape_is_unchanged():
    """R-IV.108(a): list shape unchanged, existing consumers untouched."""
    src = _bars(4)
    out = _tag_provider(src, PROVIDER_UW)
    assert isinstance(out, list) and len(out) == 4
    for b in out:
        for k in ("o", "h", "l", "c", "v", "t"):
            assert k in b, "an OHLCV key was lost"


def test_falsy_input_passes_through_untouched():
    """`if not bars:` consumers must see exactly what they saw before."""
    assert _tag_provider(None, PROVIDER_UW) is None
    assert _tag_provider([], PROVIDER_UW) == []


def test_high_and_low_survive_tagging():
    """The fetch spec requires HIGH and LOW; the same-day break test depends on them."""
    out = _tag_provider(_bars(1), PROVIDER_YFINANCE)
    assert out[0]["h"] == 2.0 and out[0]["l"] == 0.5


def test_tagging_is_idempotent():
    """A cached series is re-returned already tagged; re-tagging must not corrupt it."""
    out = _tag_provider(_tag_provider(_bars(2), PROVIDER_UW), PROVIDER_UW)
    assert all(b["provider"] == PROVIDER_UW for b in out)


def test_mixed_provider_series_is_detectable():
    """The arm rule is enforceable only if a mix is observable. This is that check."""
    mixed = _tag_provider(_bars(2), PROVIDER_UW) + _tag_provider(_bars(2), PROVIDER_YFINANCE)
    providers = {b["provider"] for b in mixed}
    assert len(providers) == 2, "a provider mix inside one series must be visible"


def test_both_live_return_points_are_tagged_in_source():
    """A tagger that exists but is not wired at a return point labels nothing."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "integrations" / "uw_api.py").read_text(encoding="utf-8")
    assert "_tag_provider(bars, PROVIDER_UW)" in src, "UW return point not tagged"
    assert "_tag_provider(bars, PROVIDER_YFINANCE)" in src, "yfinance return point not tagged"
    # tagging must precede the cache write, or cached series come back unlabelled
    uw_tag = src.index("_tag_provider(bars, PROVIDER_UW)")
    uw_cache = src.index('await cache_set("quote", cache_key, bars)', uw_tag - 400)
    assert uw_tag < uw_cache, "UW series is cached before it is tagged"
