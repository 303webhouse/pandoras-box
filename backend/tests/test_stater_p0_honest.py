"""Stater Phase 0, items 4-6 (R-IV.619): honest readings, the crypto-only feed, the reset route.

  * The session block reads the keys crypto_sessions actually returns. It used to
    ask for `current_session` / `label`, which never exist, so `state` was null.
  * The tape stale limit clears one full job cadence (it was 600 s against a 900 s
    job, so a healthy feed read stale a third of the time) in BOTH readers.
  * GET /api/crypto/signals serves CRYPTO rows newest first, all marked shadow,
    behind auth; /api/trade-ideas and its RV4 crypto exclusion are untouched.
  * POST /api/btc/bottom-signals/reset reaches the reset handler, not the
    /{signal_id} handler.
Each check that expects a failure carries a positive control in the same run (#30).
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.crypto_sessions import get_session_state, session_block_fields  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


CFG = {"sessions": {"partition_utc": {"ASIA": [0, 8], "LONDON": [8, 16], "NY": [16, 24]},
                    "event_windows": {}, "holiday_dates": []}}


def test_session_block_reads_real_keys():
    sess = get_session_state(datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc), CFG)   # Thu 09:00 UTC
    f = session_block_fields(sess)
    assert f["state"] == "LONDON" and f["partition"] == "LONDON" and f["session_label"] == "LONDON"
    # Positive control: the old keys really are absent, which is why state was always null.
    assert sess.get("current_session") is None and sess.get("label") is None


def test_session_label_names_event_windows_and_thin_weekend():
    f = session_block_fields({"partition": "NY", "event_windows_active": ["etf_fixing"],
                              "weekend_holiday_flag": True})
    assert f["session_label"] == "NY · etf_fixing · thin (weekend/holiday)"


def test_tape_stale_limit_is_shared_and_clears_the_job_cadence():
    from bias_filters.crypto_tape_health_engine import TAPE_JOB_CADENCE_SECONDS, TAPE_STALE_AFTER_SECONDS
    from services.read_only import crypto_state
    assert crypto_state.TAPE_STALE_SECONDS == TAPE_STALE_AFTER_SECONDS > TAPE_JOB_CADENCE_SECONDS


def test_crypto_state_tape_block_fresh_inside_one_cadence():
    from api import crypto_market
    from bias_filters.crypto_tape_health_engine import TAPE_JOB_CADENCE_SECONDS

    def _pool_with(age_s):
        row = {"state": "SPOT_LED", "slope": 1.0, "spot_cvd": 2.0, "perp_cvd": 1.0, "degraded": False,
               "degrade_reason": None,
               "computed_at": datetime.now(timezone.utc) - timedelta(seconds=age_s)}

        class _C:
            async def __aenter__(s):
                return s

            async def __aexit__(s, *a):
                return False

            async def fetchrow(s, sql, *a):
                return row if "crypto_tape_health_log" in sql else None

        class _P:
            def acquire(self):
                return _C()

        async def _get():
            return _P()
        return _get

    async def _na(*a, **k):
        return {"state": "NA"}

    async def _no_bars(*a, **k):
        return []

    from bias_filters import binance_client, coinalyze_client
    common = [patch.object(coinalyze_client, n, _na) for n in ("get_funding_rate", "get_open_interest", "get_liquidations")]
    common += [patch.object(binance_client, "get_quarterly_basis", _na),
               patch("jobs.crypto_bars.fetch_crypto_ohlc", _no_bars)]
    for p in common:
        p.start()
    try:
        # 12 minutes old: inside one 15-min cadence -> fresh (was "stale" under the 600 s limit)
        with patch("database.postgres_client.get_postgres_client", _pool_with(720)):
            body = _run(crypto_market.get_crypto_state("BTC"))
        assert body["tape_health"]["degraded"] is False
        # Positive control: two cadences old -> degraded.
        with patch("database.postgres_client.get_postgres_client", _pool_with(2 * TAPE_JOB_CADENCE_SECONDS)):
            body = _run(crypto_market.get_crypto_state("BTC"))
        assert body["tape_health"]["degraded"] is True
    finally:
        for p in common:
            p.stop()


def test_crypto_signals_feed_serves_crypto_rows_marked_shadow():
    from api import crypto_market
    seen = {}
    rows = [{"signal_id": "s1", "ticker": "BTCUSDT", "direction": "SHORT", "signal_type": "Session_Sweep",
             "strategy": "Session_Sweep", "source": "crypto_engine", "asset_class": "CRYPTO",
             "entry_price": "84000.5", "stop_loss": 84300, "target_1": 83500, "score": 70,
             "status": "ACTIVE", "created_at": datetime(2026, 9, 30, 12, 0), "expires_at": None,
             "private_note": "must not leak"}]

    class _C:
        async def __aenter__(s):
            return s

        async def __aexit__(s, *a):
            return False

        async def fetch(s, sql, *a):
            seen["sql"], seen["args"] = sql, a
            return rows

    class _P:
        def acquire(self):
            return _C()

    async def _get():
        return _P()

    with patch("database.postgres_client.get_postgres_client", _get):
        body = _run(crypto_market.get_crypto_signals(limit=20, days=14, _=None))
    assert "asset_class = 'CRYPTO'" in seen["sql"] and seen["args"] == (20, 14)
    s = body["signals"][0]
    assert s["entry_price"] == 84000.5 and s["shadow"] is True
    assert s["created_at"] == "2026-09-30T12:00:00+00:00"
    assert "private_note" not in s                       # projection, not SELECT * passthrough


def test_crypto_signals_route_is_gated_and_trade_ideas_still_excludes_crypto():
    from fastapi.routing import APIRoute
    from api import crypto_market, trade_ideas
    route = next(r for r in crypto_market.router.routes if isinstance(r, APIRoute) and r.path.endswith("/signals"))
    deps = [d.call.__name__ for d in route.dependant.dependencies]
    assert "require_api_key" in deps
    # Positive control: an ungated sibling route has no such dependency, so the check can fail.
    regime = next(r for r in crypto_market.router.routes if isinstance(r, APIRoute) and r.path.endswith("/regime"))
    assert "require_api_key" not in [d.call.__name__ for d in regime.dependant.dependencies]
    import inspect
    assert "EXCLUDE_CRYPTO_SQL" in inspect.getsource(trade_ideas.get_trade_ideas_feed)


def test_reset_route_reaches_reset_handler():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import btc_signals
    from utils.pivot_auth import require_api_key

    calls = {"reset": 0, "update": 0}

    async def _reset():
        calls["reset"] += 1

    async def _update(**k):
        calls["update"] += 1
        return {}

    app = FastAPI()
    app.include_router(btc_signals.router, prefix="/api")
    app.dependency_overrides[require_api_key] = lambda: None
    with patch.object(btc_signals, "reset_all_signals", _reset), \
            patch.object(btc_signals, "update_signal_manual", _update):
        client = TestClient(app)
        r = client.post("/api/btc/bottom-signals/reset")
        assert r.status_code == 200 and calls == {"reset": 1, "update": 0}, (r.status_code, r.text)
        # Positive control: a real signal id still reaches the update handler.
        r2 = client.post("/api/btc/bottom-signals/funding_rate", json={"status": "FIRING"})
        assert r2.status_code == 200 and calls["update"] == 1, (r2.status_code, r2.text)
