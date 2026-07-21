"""DEF-FEED-TRIAGE D2 -- crypto_regime_log symbol-format fix
(api/crypto_market.py::get_crypto_state).

Root cause (live-verified 2026-07-20): the writer (jobs/crypto_regime.py)
has been healthy the entire time -- 648 rows, hourly, zero gaps -- keyed by
the hyphenated canonical form ("BTC-USD", matching crypto_gates.py's real
gate-consumer). The reader queried with the bare base_symbol ("BTC") instead,
so the query matched nothing, ever, since the field was wired (commit
4a9b335). Fix is query-local: hyphenate base_symbol before the
crypto_regime_log lookup only -- crypto_tape_health_log's query (bare form)
is correct as-is and must not change.

No live database access -- the connection pool/query are mocked.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.crypto_market import get_crypto_state


def _run(coro):
    return asyncio.run(coro)


class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _mock_pool(fetchrow_result):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


_COMMON_MOCKS_NO_DB = (
    patch("bias_filters.coinalyze_client.get_funding_rate", new=AsyncMock(return_value={"state": "NA", "reason": "t"})),
    patch("bias_filters.coinalyze_client.get_open_interest", new=AsyncMock(return_value={"state": "NA", "reason": "t"})),
    patch("bias_filters.binance_client.get_quarterly_basis", new=AsyncMock(return_value={"state": "NA", "reason": "t"})),
    patch("config.crypto_gate_loader.get_gate_config", new=AsyncMock(return_value=(1, {"partition_utc": {}}))),
    patch("utils.crypto_sessions.get_session_state", return_value={"current_session": None, "label": None, "partition": None}),
    patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=[])),
    patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value={"state": "NA", "reason": "t"})),
)


def test_regime_query_uses_hyphenated_symbol():
    """The exact regression this defect was: passing bare 'BTC' instead of
    'BTC-USD' as the query's $1 parameter."""
    pool, conn = _mock_pool(None)  # no row either way -- we're checking the param

    async def _run_it():
        with _COMMON_MOCKS_NO_DB[0], _COMMON_MOCKS_NO_DB[1], _COMMON_MOCKS_NO_DB[2], \
             _COMMON_MOCKS_NO_DB[3], _COMMON_MOCKS_NO_DB[4], _COMMON_MOCKS_NO_DB[5], _COMMON_MOCKS_NO_DB[6], \
             patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
            return await get_crypto_state("BTC")

    _run(_run_it())
    # First fetchrow call is the regime query (tape_health's own pool/conn is
    # a separate get_postgres_client() call in this endpoint -- confirm this
    # specific conn saw the hyphenated form).
    call_args = conn.fetchrow.call_args_list[0]
    query_param = call_args.args[1]
    assert query_param == "BTC-USD", f"expected hyphenated symbol, got {query_param!r}"


def test_regime_row_found_with_hyphenated_symbol_surfaces_real_state():
    row = {
        "regime_state": "CHOP",
        "computed_at": datetime.now(timezone.utc),  # fresh -- not stale
        "degraded": False,
        "degrade_reason": None,
    }
    pool, conn = _mock_pool(row)

    async def _run_it():
        with _COMMON_MOCKS_NO_DB[0], _COMMON_MOCKS_NO_DB[1], _COMMON_MOCKS_NO_DB[2], \
             _COMMON_MOCKS_NO_DB[3], _COMMON_MOCKS_NO_DB[4], _COMMON_MOCKS_NO_DB[5], _COMMON_MOCKS_NO_DB[6], \
             patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
            return await get_crypto_state("BTC")

    result = _run(_run_it())
    assert result["regime"]["state"] == "CHOP"
    assert result["regime"]["degraded"] is False


def test_regime_symbol_hyphenation_per_tracked_symbol():
    """Every tracked base symbol maps to its own -USD form, not just BTC."""
    for base in ("ETH", "SOL", "HYPE", "ZEC", "FARTCOIN"):
        pool, conn = _mock_pool(None)

        async def _run_it(b=base, p=pool):
            with _COMMON_MOCKS_NO_DB[0], _COMMON_MOCKS_NO_DB[1], _COMMON_MOCKS_NO_DB[2], \
                 _COMMON_MOCKS_NO_DB[3], _COMMON_MOCKS_NO_DB[4], _COMMON_MOCKS_NO_DB[5], _COMMON_MOCKS_NO_DB[6], \
                 patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=p)):
                return await get_crypto_state(b)

        _run(_run_it())
        query_param = conn.fetchrow.call_args_list[0].args[1]
        assert query_param == f"{base}-USD"
