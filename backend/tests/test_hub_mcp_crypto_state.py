"""HUB-MCP-CRYPTO-STATE — tests for the DB/cache-backed crypto state tool (Path B).

Covers the three non-negotiables from the brief:
  1. No fail-open defaults anywhere — a MISSING health state renders degraded,
     never healthy. Guarded at both the pure-classifier level and the
     cell-parsing level (the class of bug that hid the funding cache defect on
     OI/basis for its whole life).
  2. Per-block health with a WORST-of-blocks top-level rollup.
  3. Honest per-symbol unavailable — no fabricated values when a row/cell is
     absent; ATR (live-only) is an explicit omission, never a number.

Plus: zero vendor calls (the whole reason for Path B) — asserted structurally.
No DB and no network: the async _read_* helpers are driven by a FakeConn, and
the tool layer patches the service.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.read_only import crypto_state as svc
from services.read_only.crypto_state import (
    _classify, _block, _cells_to_list, _atr_omitted,
    _read_cycle_blocks, _read_regime, _read_tape_health,
    CYCLE_STALE_SECONDS, ROLLUP_BLOCKS,
)


def _run(coro):
    return asyncio.run(coro)


NOW = datetime(2026, 7, 21, 23, 0, 0, tzinfo=timezone.utc)


class FakeConn:
    """Dispatches fetchrow by target table; rows are plain dicts (or None).
    Never touches a network or a vendor — the point of Path B."""

    def __init__(self, cycle=None, regime=None, tape=None):
        self._cycle, self._regime, self._tape = cycle, regime, tape

    async def fetchrow(self, sql, *args):
        if "crypto_cycle_log" in sql:
            return self._cycle
        if "crypto_regime_log" in sql:
            return self._regime
        if "crypto_tape_health_log" in sql:
            return self._tape
        return None


def _cell(signal_id, state="LIVE", stale=False, as_of=None, value=1.0, **extra):
    d = {"signal_id": signal_id, "state": state, "stale": stale,
         "as_of": (as_of or NOW).isoformat(), "value": value,
         "signal": "NEUTRAL", "column": "CAPITULATION", "source": "coinalyze"}
    d.update(extra)
    return d


# ─────────────────────────────────────────────────────────────────────────
# 1. NO FAIL-OPEN — the load-bearing guard for the whole tool
# ─────────────────────────────────────────────────────────────────────────

def test_classify_missing_state_is_degraded_not_healthy():
    # state=None (field absent) must NEVER resolve to ok.
    assert _classify(state=None, stale_flag=False, row_degraded=False,
                     age=10, stale_threshold=CYCLE_STALE_SECONDS) == "degraded"


def test_classify_non_live_state_is_degraded():
    assert _classify(state="STALE", stale_flag=False, row_degraded=False,
                     age=10, stale_threshold=CYCLE_STALE_SECONDS) == "degraded"
    assert _classify(state="DEGRADED", stale_flag=False, row_degraded=False,
                     age=10, stale_threshold=CYCLE_STALE_SECONDS) == "degraded"


def test_classify_stale_flag_and_row_degraded_win():
    assert _classify(state="LIVE", stale_flag=True, row_degraded=False,
                     age=10, stale_threshold=CYCLE_STALE_SECONDS) == "degraded"
    assert _classify(state="LIVE", stale_flag=False, row_degraded=True,
                     age=10, stale_threshold=CYCLE_STALE_SECONDS) == "degraded"


def test_classify_live_fresh_is_ok_but_old_is_stale():
    assert _classify(state="LIVE", stale_flag=False, row_degraded=False,
                     age=10, stale_threshold=CYCLE_STALE_SECONDS) == "ok"
    assert _classify(state="LIVE", stale_flag=False, row_degraded=False,
                     age=CYCLE_STALE_SECONDS + 1, stale_threshold=CYCLE_STALE_SECONDS) == "stale"


def test_read_cycle_block_with_missing_state_key_is_degraded():
    """Integration-level no-fail-open: a cell present but WITHOUT a 'state' key
    must render degraded, not ok. This is the exact shape of the OI/basis
    fail-open bug reproduced against the parser."""
    bad_cell = {"signal_id": "perp_funding", "as_of": NOW.isoformat(), "value": 0.001}
    row = {"computed_at": NOW, "degraded": False, "degrade_reason": None,
           "cells": [bad_cell], "tier": 1, "live_cell_count": 1, "min_live_cells": 1}
    blocks, _ = _run(_read_cycle_blocks(FakeConn(cycle=row), "BTC", NOW))
    assert blocks["funding"]["status"] == "degraded"
    assert blocks["funding"]["degraded"] is True


# ─────────────────────────────────────────────────────────────────────────
# 2. Block envelope shape + parsing
# ─────────────────────────────────────────────────────────────────────────

def test_block_shape_and_degraded_mirror():
    b = _block("stale", NOW, NOW, value=5)
    assert b["value"] == 5 and b["as_of"] == NOW.isoformat()
    assert b["data_age_seconds"] == 0 and b["status"] == "stale"
    assert b["degraded"] is True
    assert _block("ok", NOW, NOW)["degraded"] is False


def test_cells_to_list_handles_all_forms():
    import json
    lst = [{"signal_id": "x"}]
    assert _cells_to_list(lst) == lst                    # already a list
    assert _cells_to_list(json.dumps(lst)) == lst         # jsonb-as-str
    assert _cells_to_list(None) == []                     # null column
    assert _cells_to_list("not json{{") == []             # garbage -> empty, not crash
    assert _cells_to_list(42) == []                       # wrong type


# ─────────────────────────────────────────────────────────────────────────
# 3. Honest unavailable / no fabrication
# ─────────────────────────────────────────────────────────────────────────

def test_atr_is_omitted_never_fabricated():
    a = _atr_omitted()
    assert a["available"] is False and a["value"] is None and "reason" in a


def test_no_cycle_row_yields_unavailable_blocks_not_zeros():
    blocks, cyc = _run(_read_cycle_blocks(FakeConn(cycle=None), "BTC", NOW))
    assert cyc is None
    for name in ("funding", "open_interest", "basis", "liquidations"):
        assert blocks[name]["status"] == "unavailable"
        assert blocks[name]["value"] is None  # honest null, not 0


def test_missing_cell_in_row_is_unavailable():
    # Row exists but the 'liquidations' cell is absent from cells[].
    row = {"computed_at": NOW, "degraded": False, "degrade_reason": None,
           "cells": [_cell("perp_funding", value=0.001)],
           "tier": 1, "live_cell_count": 1, "min_live_cells": 1}
    blocks, _ = _run(_read_cycle_blocks(FakeConn(cycle=row), "BTC", NOW))
    assert blocks["funding"]["status"] == "ok"
    assert blocks["liquidations"]["status"] == "unavailable"


def test_live_cell_passes_values_and_labels_through():
    row = {"computed_at": NOW, "degraded": False, "degrade_reason": None,
           "cells": [
               _cell("perp_funding", value=0.0013, sentiment="neutral"),
               _cell("liquidations", value=12532819.9, long_pct=7.3, composition="short_heavy"),
           ],
           "tier": 1, "live_cell_count": 2, "min_live_cells": 1}
    blocks, _ = _run(_read_cycle_blocks(FakeConn(cycle=row), "BTC", NOW))
    assert blocks["funding"]["status"] == "ok"
    assert blocks["funding"]["value"] == 0.0013
    assert blocks["funding"]["cta_zone"] == "CAPITULATION"
    assert blocks["funding"]["sentiment"] == "neutral"
    assert blocks["liquidations"]["long_pct"] == 7.3
    assert blocks["liquidations"]["composition"] == "short_heavy"


def test_regime_stale_vs_degraded_and_missing():
    fresh = {"regime_state": "TREND_DOWN", "computed_at": NOW, "degraded": False, "degrade_reason": None}
    assert _run(_read_regime(FakeConn(regime=fresh), "BTC", NOW))["status"] == "ok"

    old = {"regime_state": "TREND_DOWN", "computed_at": NOW - timedelta(seconds=8000),
           "degraded": False, "degrade_reason": None}
    assert _run(_read_regime(FakeConn(regime=old), "BTC", NOW))["status"] == "stale"

    flagged = {"regime_state": "TREND_DOWN", "computed_at": NOW, "degraded": True, "degrade_reason": "x"}
    assert _run(_read_regime(FakeConn(regime=flagged), "BTC", NOW))["status"] == "degraded"

    assert _run(_read_regime(FakeConn(regime=None), "BTC", NOW))["status"] == "unavailable"


def test_tape_health_carries_cvd():
    row = {"state": "SPOT_LED", "slope": 1.2, "spot_cvd": 100.0, "perp_cvd": -50.0,
           "degraded": False, "degrade_reason": None, "computed_at": NOW}
    b = _run(_read_tape_health(FakeConn(tape=row), "BTC", NOW))
    assert b["status"] == "ok" and b["state"] == "SPOT_LED"
    assert b["spot_cvd"] == 100.0 and b["perp_cvd"] == -50.0


# ─────────────────────────────────────────────────────────────────────────
# Tool layer: worst-status rollup + envelope + guards
# ─────────────────────────────────────────────────────────────────────────

def _blocks(**status_by_block):
    """Build a minimal get_crypto_state return with the given per-block statuses."""
    data = {"symbol": "BTC", "atr": _atr_omitted(),
            "cycle_snapshot_at": NOW.isoformat(), "generated_at": NOW.isoformat()}
    for name in ROLLUP_BLOCKS:
        st = status_by_block.get(name, "ok")
        data[name] = {"status": st, "degraded": st != "ok",
                      "data_age_seconds": 100, "as_of": NOW.isoformat(),
                      "value": None, "state": None}
    return data


def test_tool_rollup_is_worst_of_blocks():
    from hub_mcp.tools.crypto_state import hub_get_crypto_state
    # all ok -> ok
    with patch("hub_mcp.tools.crypto_state.get_crypto_state",
               new=AsyncMock(return_value=_blocks())):
        r = _run(hub_get_crypto_state("BTC"))
    assert r["status"] == "ok"

    # one block degraded -> top-level degraded even though the rest are ok
    with patch("hub_mcp.tools.crypto_state.get_crypto_state",
               new=AsyncMock(return_value=_blocks(regime="degraded"))):
        r = _run(hub_get_crypto_state("BTC"))
    assert r["status"] == "degraded"

    # unavailable beats degraded
    with patch("hub_mcp.tools.crypto_state.get_crypto_state",
               new=AsyncMock(return_value=_blocks(regime="degraded", tape_health="unavailable"))):
        r = _run(hub_get_crypto_state("BTC"))
    assert r["status"] == "unavailable"


def test_tool_valid_envelope_shape():
    from hub_mcp import SCHEMA_VERSION
    from hub_mcp.tools.crypto_state import hub_get_crypto_state
    with patch("hub_mcp.tools.crypto_state.get_crypto_state",
               new=AsyncMock(return_value=_blocks(funding="stale"))):
        r = _run(hub_get_crypto_state("btc-usd"))
    assert r["schema_version"] == SCHEMA_VERSION
    assert r["status"] in {"ok", "stale", "degraded", "unavailable"}
    assert "data" in r and "error" in r and "staleness_seconds" in r
    assert isinstance(r["summary"], str) and len(r["summary"]) <= 300


def test_tool_untracked_and_empty_are_unavailable():
    from hub_mcp.tools.crypto_state import hub_get_crypto_state
    r = _run(hub_get_crypto_state("AAPL"))
    assert r["status"] == "unavailable" and r["data"] is None
    r2 = _run(hub_get_crypto_state("   "))
    assert r2["status"] == "unavailable"


def test_tool_service_exception_is_unavailable():
    from hub_mcp.tools.crypto_state import hub_get_crypto_state
    with patch("hub_mcp.tools.crypto_state.get_crypto_state",
               new=AsyncMock(side_effect=RuntimeError("db down"))):
        r = _run(hub_get_crypto_state("BTC"))
    assert r["status"] == "unavailable" and "db down" in (r["error"] or "")


# ─────────────────────────────────────────────────────────────────────────
# Zero-vendor-call guarantee (Path B) — structural
# ─────────────────────────────────────────────────────────────────────────

def test_service_never_imports_vendor_clients():
    """Path B's whole point: this service must not reach a vendor. Assert the
    module source references no vendor client, so a cache miss can never fan out
    to Coinalyze/Binance/OKX the way the live endpoint does."""
    import inspect
    src = inspect.getsource(svc)
    for banned in ("coinalyze_client", "binance_client", "_make_okx_request",
                   "fetch_crypto_ohlc", "get_funding_rate", "get_open_interest"):
        assert banned not in src, f"Path B violation: service references {banned}"
