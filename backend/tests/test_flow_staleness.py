"""L1.0 Chunk 3 — flow staleness invariants.

Guards: (1) _staleness_from is null when age is unknown — NEVER 0 (0 = fake-fresh
lie); (2) data_updated_at is the oldest updated_at across canonical summaries and
EXCLUDES manual-fallback entries (which carry last_updated, not updated_at).
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import api.flow_radar as fr


# --- _staleness_from: null-safe, never 0 -------------------------------------
def test_staleness_none_when_unknown():
    assert fr._staleness_from(None) is None
    assert fr._staleness_from("") is None
    assert fr._staleness_from("not-a-date") is None        # malformed → None, NOT 0


def test_staleness_real_value_when_dated():
    dua = (datetime.now(timezone.utc) - timedelta(seconds=42)).isoformat()
    s = fr._staleness_from(dua)
    assert isinstance(s, int) and 40 <= s <= 60


def test_staleness_floors_at_zero_not_negative():
    future = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    assert fr._staleness_from(future) == 0   # clock skew → 0, never negative


# --- data_updated_at: oldest updated_at, manual-fallback excluded ------------
def _compute(summaries):
    redis = AsyncMock()
    keys = [f"uw:flow:{s['ticker']}".encode() for s in summaries]
    vals = [json.dumps(s) for s in summaries]

    async def _scan(cursor, match=None, count=None):
        return (b"0", keys)

    redis.scan = AsyncMock(side_effect=_scan)
    redis.mget = AsyncMock(return_value=vals)
    redis.get = AsyncMock(return_value=None)
    with patch("api.flow_radar.get_redis_client", new=AsyncMock(return_value=redis)), \
         patch("api.flow_radar.get_postgres_client", new=AsyncMock(return_value=None)):
        return asyncio.run(fr._compute_flow_radar())["market_pulse"]


def test_data_updated_at_excludes_manual_fallback():
    older = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
    newer = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    mp = _compute([
        {"ticker": "AAA", "sentiment": "BULLISH", "call_premium": 5_000_000,
         "put_premium": 1_000_000, "updated_at": newer},
        {"ticker": "BBB", "sentiment": "BEARISH", "call_premium": 1_000_000,
         "put_premium": 2_000_000, "updated_at": older},
        # manual fallback: last_updated only, NO updated_at → must be excluded
        {"ticker": "CCC", "sentiment": "NEUTRAL", "call_premium": 1_000_000,
         "put_premium": 1_000_000, "source": "manual", "last_updated": "2000-01-01T00:00:00+00:00"},
    ])
    assert mp["data_updated_at"] == older   # oldest of the two canonical, manual ignored


def test_data_updated_at_none_when_only_manual():
    mp = _compute([
        {"ticker": "CCC", "sentiment": "NEUTRAL", "call_premium": 1_000_000,
         "put_premium": 1_000_000, "source": "manual", "last_updated": "2000-01-01T00:00:00+00:00"},
    ])
    assert mp["data_updated_at"] is None
