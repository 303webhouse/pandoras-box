"""HYDRA flow-score ↔ canonical uw:flow contract tests.

Guards the writer↔reader contract for hydra_squeeze._get_flow_score: the poller's
REAL build_flow_summary() output must be scorable by the REAL _get_flow_score,
yielding a non-zero call-dominance on bullish flow. No hand-built summary dict —
that is exactly what hid the phantom-key bug (the scorer read total_call_premium /
call_count / total_count / bullish_count, none of which the canonical writer ever
produced, so every flow score was structurally 0).
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import scanners.hydra_squeeze as hs
from jobs.uw_flow_poller import build_flow_summary


def _row(call_premium, put_premium, pc_ratio, *, ticker="NVDA",
         call_volume=1000, put_volume=500, flow_sentiment="NEUTRAL"):
    """aggregate_ticker_flow output shape (same helper as test_pathA)."""
    return {
        "ticker": ticker,
        "pc_ratio": pc_ratio,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "total_premium": call_premium + put_premium,
        "call_premium": call_premium,
        "put_premium": put_premium,
        "flow_sentiment": flow_sentiment,
        "price": None,
        "change_pct": None,
        "volume": None,
        "source": "railway_poller",
    }


def _score_for(summary):
    """Run the REAL _get_flow_score against a mocked Redis returning `summary`."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps(summary) if summary is not None else None)
    with patch("scanners.hydra_squeeze.get_redis_client", new=AsyncMock(return_value=redis)):
        return asyncio.run(hs._get_flow_score("NVDA"))


# --- the core regression: canonical summary → NON-ZERO score -----------------
def test_canonical_summary_yields_nonzero_call_dominance():
    # 8M call / 1M put premium, 1000/500 volume.
    # prem_dominance = 8/9*100 = 88.89 ; vol_dominance = 1000/1500*100 = 66.67
    # score = 0.5*88.89 + 0.5*66.67 = 77.78  (was structurally 0.0 pre-fix)
    summary = build_flow_summary(_row(8_000_000, 1_000_000, 0.5))
    score, pc_ratio = _score_for(summary)
    assert abs(score - 77.78) < 0.1
    assert pc_ratio == 0.5            # canonical volume put/call, round-tripped


def test_balanced_flow_is_near_fifty():
    # Equal premium and volume → both dominances 50 → score 50.
    summary = build_flow_summary(_row(1_000_000, 1_000_000, 1.0,
                                       call_volume=500, put_volume=500))
    score, pc_ratio = _score_for(summary)
    assert abs(score - 50.0) < 0.01
    assert pc_ratio == 1.0


def test_bearish_flow_scores_low():
    # 1M call / 9M put, 200/1800 volume → low call dominance.
    summary = build_flow_summary(_row(1_000_000, 9_000_000, 9.0,
                                       call_volume=200, put_volume=1800))
    score, _ = _score_for(summary)
    # prem 10.0, vol 10.0 → score 10.0
    assert score < 15.0


def test_all_put_sentinel_scores_zero_dominance():
    # call_premium/volume both 0, pc_ratio sentinel 999 → writer normalizes to None.
    summary = build_flow_summary(_row(0, 5_000_000, 999.0,
                                       call_volume=0, put_volume=500))
    score, pc_ratio = _score_for(summary)
    assert score == 0.0               # no call side at all
    assert pc_ratio == 2.0            # None sentinel → bearish proxy


def test_premium_only_when_volume_absent():
    # Canonical shape with null volumes (single-basis path): use premium alone,
    # NOT half of it.
    summary = build_flow_summary(_row(8_000_000, 2_000_000, 0.0,
                                       call_volume=None, put_volume=None))
    score, _ = _score_for(summary)
    # prem_dominance = 8/10*100 = 80.0, volume basis absent → score == 80.0
    assert abs(score - 80.0) < 0.01


def test_no_flow_key_returns_neutral_default():
    score, pc_ratio = _score_for(None)
    assert score == 0.0
    assert pc_ratio == 1.0


def test_legacy_phantom_keys_do_not_score():
    # A dict carrying ONLY the pre-fix keys (and none of the canonical ones)
    # must score 0 — proving the scorer no longer depends on phantom fields and
    # cannot be fooled by a stale legacy writer.
    legacy = {
        "total_call_premium": 9_000_000,
        "total_put_premium": 1_000_000,
        "call_count": 900,
        "total_count": 1000,
        "bullish_count": 850,
    }
    score, pc_ratio = _score_for(legacy)
    assert score == 0.0
    assert pc_ratio == 1.0
