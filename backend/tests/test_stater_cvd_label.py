"""R-IV.645(d)2 — the CVD leg's label is "no data"; scores stay put.

btc_market_structure._fetch_cvd reads `cvd_analysis`, a key /crypto/market
has never returned. Every live call therefore defaulted to NEUTRAL / 0.5 / 0
and _score_cvd returned 0, "CVD neutral". This is an honest-label change only:
the missing key still contributes 0, now labelled "no data". It does not start
reading the real `cvd` key (that stays a shadow score under R-IV.637(c)).
"""

import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strategies.btc_market_structure import _fetch_cvd, _score_cvd  # noqa: E402
import strategies.btc_market_structure as bms  # noqa: E402


# Frozen: every (signal direction, CVD payload) pair's score as _score_cvd
# already returned it. The missing-key path is the only reason-string change.
UNCHANGED = [
    ("LONG", {"direction": "BULLISH"}, 10, "CVD confirms buying pressure"),
    ("SHORT", {"direction": "BEARISH"}, 10, "CVD confirms selling pressure"),
    ("LONG", {"direction": "NEUTRAL"}, 0, "CVD neutral"),
    ("SHORT", {"direction": "NEUTRAL"}, 0, "CVD neutral"),
    ("LONG", {"direction": "BEARISH"}, -15, "CVD diverges: selling pressure vs LONG signal"),
    ("SHORT", {"direction": "BULLISH"}, -15, "CVD diverges: buying pressure vs SHORT signal"),
    ("LONG", {"direction": "SIDEWAYS"}, 0, "CVD inconclusive"),
    ("SHORT", {"direction": "SIDEWAYS"}, 0, "CVD inconclusive"),
    ("LONG", {"error": "timeout"}, 0, "CVD unavailable"),
    ("SHORT", {"error": "timeout"}, 0, "CVD unavailable"),
]


@pytest.fixture(autouse=True)
def _clear_cache():
    bms._cache.clear()
    yield
    bms._cache.clear()


@pytest.mark.parametrize("signal_dir,cvd,score,reason", UNCHANGED)
def test_every_cvd_score_is_unchanged(signal_dir, cvd, score, reason):
    got_score, got_reason = _score_cvd(cvd, signal_dir)
    assert got_score == score
    assert got_reason == reason


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def test_missing_cvd_analysis_scores_zero_and_says_no_data():
    """Live shape: top-level `cvd` is present, `cvd_analysis` is not.

    Score stays 0 (what NEUTRAL contributed). Reason is "no data", not
    "CVD neutral". The real `cvd.direction` BULLISH is ignored on purpose.
    """
    payload = {
        "status": "success",
        "cvd": {"direction": "BULLISH", "net_usd": 1_000_000},
        "prices": {},
        "funding": {},
        "errors": [],
    }

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp(payload)

    with patch("httpx.AsyncClient", _Client):
        data = asyncio.run(_fetch_cvd("BTCUSDT"))

    assert data["direction"] == "NEUTRAL"
    assert data["buy_ratio"] == 0.5
    assert data["net_volume_usd"] == 0
    assert data["no_data"] is True
    for signal_dir in ("LONG", "SHORT"):
        score, reason = _score_cvd(data, signal_dir)
        assert score == 0
        assert reason == "no data"


def test_present_cvd_analysis_still_scores_as_before():
    payload = {"cvd_analysis": {"direction": "BULLISH", "buy_ratio": 0.8, "net_volume_usd": 9}}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp(payload)

    with patch("httpx.AsyncClient", _Client):
        data = asyncio.run(_fetch_cvd("BTCUSDT"))

    assert "no_data" not in data
    assert data["direction"] == "BULLISH"
    score, reason = _score_cvd(data, "LONG")
    assert score == 10
    assert reason == "CVD confirms buying pressure"
