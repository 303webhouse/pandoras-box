"""DEF-FUNDING-CACHE-HEALTH -- cache must carry health_status (coinalyze_client.py).

Defect (surfaced by DEF-FUNDING-DUTY-CYCLE Phase 0, 04a1983):
`_finalize_result` cached the result dict BEFORE attaching `health_status`,
so every cache hit inside the 300s TTL returned a dict missing the field. The
funding consumer reads it with a bare `.get("health_status")`
(api/crypto_market.py:716), so a cache hit yielded None -> None != "LIVE" ->
degraded=true on perfectly healthy data ("fake-degraded"). Production repro
was three consecutive calls returning degraded = false, true, true with an
identical rate.

Fix: build one merged {**result, "health_status": status} dict and use it for
BOTH the cache write and the return, so the cache-hit and cache-miss paths can
never diverge again.

THESE TESTS MUST FAIL AGAINST PRE-FIX CODE. A regression guard that passes
before the fix guards nothing. Verified failing pre-fix by stashing the edit
(see completion doc). No live API calls -- _make_request/record_observation
are mocked.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bias_filters.coinalyze_client import get_funding_rate


def _run(coro):
    return asyncio.run(coro)


def _clear_cache():
    import bias_filters.coinalyze_client as cc
    cc._cache.clear()


# Real Coinalyze primary-path shape; value is already a percent, well within
# FUNDING_RATE_PCT_BOUNDS (-5.0, 5.0), so the sanity check passes (ok=True) and
# the result is cached.
_HEALTHY_RESPONSE = [{"symbol": "BTCUSD_PERP.A", "value": 0.0013, "update": 1}]


def _consumer_degraded(funding_data: dict) -> bool:
    """Mirror of the exact funding-consumer predicate at
    api/crypto_market.py:716 -- bare .get(), no default. Kept in lockstep so
    this test fails the moment the consumer's fake-degraded exposure returns."""
    is_na = funding_data.get("state") == "NA"
    return is_na or bool(funding_data.get("error")) or funding_data.get("health_status") != "LIVE"


# ---------------------------------------------------------------------------
# 1. PRIMARY: a cache hit must return health_status intact. FAILS pre-fix.
# ---------------------------------------------------------------------------

def test_cache_hit_carries_health_status():
    _clear_cache()
    with patch("bias_filters.coinalyze_client._make_request",
               new=AsyncMock(return_value=_HEALTHY_RESPONSE)), \
         patch("bias_filters.coinalyze_client.record_observation",
               new=AsyncMock(return_value="LIVE")) as rec:
        first = _run(get_funding_rate("BTC"))   # cache miss -> populates cache
        second = _run(get_funding_rate("BTC"))  # cache HIT -> the bug's blast radius

    # The network was hit exactly once; the second call was served from cache.
    assert rec.await_count == 1, "second call should have been a cache hit, not a refetch"
    assert first.get("health_status") == "LIVE"
    # Pre-fix this is None (field stripped by the cache write); post-fix "LIVE".
    assert second.get("health_status") == "LIVE", (
        "cache hit dropped health_status -- fake-degraded regression"
    )


# ---------------------------------------------------------------------------
# 2. CONSUMER VERDICT: degraded must be identical across a miss then a hit.
#    This is the production repro (false,true,true) reduced to a unit. FAILS pre-fix.
# ---------------------------------------------------------------------------

def test_consumer_degraded_stable_across_cache_hit():
    _clear_cache()
    with patch("bias_filters.coinalyze_client._make_request",
               new=AsyncMock(return_value=_HEALTHY_RESPONSE)), \
         patch("bias_filters.coinalyze_client.record_observation",
               new=AsyncMock(return_value="LIVE")):
        first = _run(get_funding_rate("BTC"))
        second = _run(get_funding_rate("BTC"))
        third = _run(get_funding_rate("BTC"))

    d1, d2, d3 = _consumer_degraded(first), _consumer_degraded(second), _consumer_degraded(third)
    # Healthy feed -> degraded must be False on every call, not False,True,True.
    assert (d1, d2, d3) == (False, False, False), (
        f"fake-degraded across cache hits: got degraded={(d1, d2, d3)}, expected all False"
    )
    # And the rate is genuinely identical -- proving it is the SAME reading,
    # so any degraded flip is purely a cache artifact, not new data.
    assert first["funding_rate"] == second["funding_rate"] == third["funding_rate"]


# ---------------------------------------------------------------------------
# 3. HONEST DEGRADATION preserved: a genuinely DEGRADED fetch must still read
#    degraded on cache hits -- for the RIGHT reason (field present == "DEGRADED"),
#    not the coincidental pre-fix reason (field absent -> None). FAILS pre-fix
#    on the health_status assertion (None != "DEGRADED").
# ---------------------------------------------------------------------------

def test_honest_degradation_survives_cache_hit():
    _clear_cache()
    # In-bounds value (ok=True, so it IS cached) but vendor health is DEGRADED
    # -- the stale-but-valid case. record_observation is the sole source of the
    # status, independent of the bounds check.
    with patch("bias_filters.coinalyze_client._make_request",
               new=AsyncMock(return_value=_HEALTHY_RESPONSE)), \
         patch("bias_filters.coinalyze_client.record_observation",
               new=AsyncMock(return_value="DEGRADED")):
        first = _run(get_funding_rate("BTC"))
        second = _run(get_funding_rate("BTC"))  # cache hit

    assert first.get("health_status") == "DEGRADED"
    # The fix must not convert a real degradation into a false all-clear.
    assert second.get("health_status") == "DEGRADED", (
        "cache hit masked a genuine degradation -- worse than the original bug"
    )
    assert _consumer_degraded(first) is True
    assert _consumer_degraded(second) is True


# ---------------------------------------------------------------------------
# 4. NON-REGRESSION: the cached object and the returned object are the SAME
#    content, so the two code paths are provably unified (root-cause lock).
# ---------------------------------------------------------------------------

def test_cache_and_return_are_consistent():
    _clear_cache()
    import bias_filters.coinalyze_client as cc
    with patch("bias_filters.coinalyze_client._make_request",
               new=AsyncMock(return_value=_HEALTHY_RESPONSE)), \
         patch("bias_filters.coinalyze_client.record_observation",
               new=AsyncMock(return_value="LIVE")):
        returned = _run(get_funding_rate("BTC"))

    cached = cc._cache["funding_rate:BTC"]["data"]
    assert cached.get("health_status") == returned.get("health_status") == "LIVE"
    assert cached["funding_rate"] == returned["funding_rate"]
