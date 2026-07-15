"""
Regression test for the datetime-serialization bug found during the S-1 F-4
crypto cutover's live verification (2026-07-15).

process_signal_unified() sets signal_data["expires_at"] to a raw datetime
(signals/pipeline.py:1200, via calculate_expiry()) on every signal, from every
source. cache_signal() and broadcast_signal_smart() used to carry their own
duplicate sanitize_for_json() that only handled numpy scalars -- json.dumps()
raised TypeError for any signal carrying that field, caught and logged as a
warning, never surfacing further. Fixed by consolidating all three
sanitize_for_json() copies (database/redis_client.py, websocket/broadcaster.py,
database/postgres_client.py) into utils/json_sanitize.py, which handles
datetime/date/Decimal in addition to numpy.

See docs/strategy-reviews/stater-swap-redesign/s1-phase4-findings.md.

Async tests use asyncio.run() directly to avoid requiring pytest-asyncio.
"""

import asyncio
import json
import sys
import os
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from utils.json_sanitize import sanitize_for_json


def _signal_with_datetime_fields() -> dict:
    """Mirrors the shape process_signal_unified() actually produces: a raw
    datetime in expires_at (calculate_expiry()'s return value), plus a raw
    date and Decimal for good measure."""
    return {
        "signal_id": "TEST_JSON_SANITIZE_BTC_20260715",
        "ticker": "BTC-USD",
        "strategy": "Crypto Scanner",
        "direction": "LONG",
        "score": Decimal("42.50"),
        "expires_at": datetime.utcnow() + timedelta(hours=4),
        "as_of_date": date(2026, 7, 15),
        "nested": {"created_at": datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)},
        "history": [datetime(2026, 7, 14, tzinfo=timezone.utc), 1, "x"],
    }


def test_sanitize_for_json_handles_datetime_date_decimal():
    raw = _signal_with_datetime_fields()
    sanitized = sanitize_for_json(raw)

    # Must not raise -- this is the actual failure mode being regression-tested.
    encoded = json.dumps(sanitized)
    round_tripped = json.loads(encoded)

    assert isinstance(round_tripped["expires_at"], str)
    assert round_tripped["expires_at"] == raw["expires_at"].isoformat()
    assert round_tripped["as_of_date"] == raw["as_of_date"].isoformat()
    assert round_tripped["nested"]["created_at"] == raw["nested"]["created_at"].isoformat()
    assert round_tripped["history"][0] == raw["history"][0].isoformat()
    assert round_tripped["score"] == 42.5


def test_cache_signal_serializes_datetime_bearing_signal():
    async def _run():
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(return_value=True)

        with patch("database.redis_client.get_redis_client", new_callable=AsyncMock, return_value=mock_redis):
            from database.redis_client import cache_signal

            signal_data = _signal_with_datetime_fields()
            # Must not raise -- pre-fix this threw
            # "Object of type datetime is not JSON serializable".
            await cache_signal(signal_data["signal_id"], signal_data, ttl=3600)

        assert mock_redis.setex.await_count == 1
        args, _ = mock_redis.setex.await_args
        key, ttl, payload = args
        assert key == f"signal:{signal_data['signal_id']}"
        assert ttl == 3600
        # The payload must itself be valid, round-trippable JSON.
        round_tripped = json.loads(payload)
        assert isinstance(round_tripped["expires_at"], str)

    asyncio.run(_run())


def test_broadcast_signal_smart_serializes_datetime_bearing_signal():
    async def _run():
        from websocket.broadcaster import ConnectionManager

        manager = ConnectionManager()
        assert manager.active_connections == []  # no connections needed to prove serialization

        signal_data = _signal_with_datetime_fields()
        signal_data["score"] = 42.0  # below priority_threshold -> regular broadcast path

        # Must not raise -- pre-fix this threw
        # "Object of type datetime is not JSON serializable".
        await manager.broadcast_signal_smart(signal_data, priority_threshold=75.0)

    asyncio.run(_run())


if __name__ == "__main__":
    test_sanitize_for_json_handles_datetime_date_decimal()
    test_cache_signal_serializes_datetime_bearing_signal()
    test_broadcast_signal_smart_serializes_datetime_bearing_signal()
    print("All json_sanitize datetime tests passed.")
