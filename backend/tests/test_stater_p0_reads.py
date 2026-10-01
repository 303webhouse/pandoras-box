"""Stater Phase 0, item 1 (R-IV.619) — a crypto GET reads; it never recomputes.

/api/crypto/cycle-extremes and /api/crypto/tape-health used to run the full
evaluation on every request: vendor calls, bars through the paid feed for CVD
event detection, an INSERT per symbol, and possible shadow signal events -- from
a page that polls every 30 seconds. They now serve the newest stored row.

The load-bearing assertions, each with a positive control in the same run (#30):
  * the endpoints never call the recompute functions -- and the tripwire used to
    prove that DOES fire when the recompute path is called;
  * the endpoints execute no write -- and the write detector DOES see the
    engine's own INSERT when the persist path runs;
  * a stored row comes back in the shape the page already reads; a missing row is
    NA / degraded, never a fabricated reading; an old row reads stale.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api import crypto_market  # noqa: E402
from bias_filters import crypto_cycle_engine as cyc  # noqa: E402
from bias_filters import crypto_tape_health_engine as tape  # noqa: E402

NOW = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


class Recorder:
    """A fake asyncpg pool/conn that serves canned rows and records every statement."""

    def __init__(self, rows_by_table=None):
        self.rows = rows_by_table or {}
        self.writes = []
        self.reads = []

    # pool interface
    def acquire(self):
        rec = self

        class _Ctx:
            async def __aenter__(self):
                return rec

            async def __aexit__(self, *a):
                return False
        return _Ctx()

    # conn interface
    async def fetch(self, sql, *args):
        self.reads.append(sql)
        for table, rows in self.rows.items():
            if table in sql:
                wanted = set(args[0]) if args else None
                return [r for r in rows if wanted is None or r["symbol"] in wanted]
        return []

    async def fetchrow(self, sql, *args):
        rows = await self.fetch(sql, *args)
        return rows[0] if rows else None

    async def execute(self, sql, *args):
        if any(w in sql.upper() for w in ("INSERT", "UPDATE", "DELETE")):
            self.writes.append(sql)
        return "OK"


def _pool_patch(rec):
    async def _get():
        return rec
    return patch("database.postgres_client.get_postgres_client", _get)


def _tripwire():
    calls = []

    async def _boom(*a, **k):
        calls.append(a)
        raise AssertionError("a GET reached the recompute path")
    return calls, _boom


TAPE_ROW = {"symbol": "BTC", "state": "SPOT_LED", "slope": 12.5, "spot_cvd": 40.0, "perp_cvd": 27.5,
            "degraded": False, "degrade_reason": None, "computed_at": NOW - timedelta(minutes=4)}
CYCLE_ROW = {"symbol": "BTC", "tier": 1, "computed_at": NOW - timedelta(minutes=20), "composite_score": -42,
             "composite_method": "cap_dominant", "degraded": False, "degrade_reason": None,
             "live_cell_count": 9, "config_version": 3,
             "cells": [{"signal_id": "skew_25delta", "column": "CAPITULATION", "state": "LIVE"},
                       {"signal_id": "perp_funding", "column": "CAPITULATION", "state": "LIVE"},
                       {"signal_id": "basis_extreme", "column": "FROTH", "state": "LIVE"}]}


# ── tape-health ───────────────────────────────────────────────────────────────

def test_tape_get_reads_stored_row_and_never_recomputes_or_writes():
    rec = Recorder({"crypto_tape_health_log": [TAPE_ROW]})
    calls, boom = _tripwire()
    live = dict(TAPE_ROW, computed_at=datetime.now(timezone.utc) - timedelta(minutes=4))
    rec.rows["crypto_tape_health_log"] = [live]
    with _pool_patch(rec), patch.object(tape, "compute_tape_health", boom), \
            patch.object(tape, "compute_all_tape_health", boom):
        body = _run(crypto_market.get_tape_health(symbol=None, _=None))
    btc = body["symbols"]["BTC"]
    assert calls == [] and rec.writes == []
    assert btc["state"] == "SPOT_LED" and btc["spot_cvd"] == 40.0 and btc["perp_cvd"] == 27.5
    assert btc["degraded"] is False and btc["stale"] is False
    # Symbols with no stored row are NA, never a made-up reading.
    assert body["symbols"]["ETH"]["state"] == "NA" and body["symbols"]["ETH"]["spot_cvd"] is None


def test_tape_tripwire_and_write_detector_positive_controls():
    # The tripwire fires when the recompute path is actually called.
    calls, boom = _tripwire()
    with pytest.raises(AssertionError):
        _run(boom("BTC", {}))
    assert len(calls) == 1
    # The write detector sees the engine's own INSERT.
    rec = Recorder()
    with _pool_patch(rec):
        _run(tape._persist_tape_health({"state": "MIXED"}, "BTC", NOW, {}))
    assert len(rec.writes) == 1 and "crypto_tape_health_log" in rec.writes[0]


def test_tape_old_row_reads_stale_and_degraded():
    old = dict(TAPE_ROW, computed_at=NOW - timedelta(seconds=tape.TAPE_STALE_AFTER_SECONDS + 60))
    rec = Recorder({"crypto_tape_health_log": [old]})
    with _pool_patch(rec):
        cell = _run(tape.read_latest_tape_health(["BTC"], now_utc=NOW))["BTC"]
    assert cell["stale"] is True and cell["degraded"] is True and "old" in cell["degrade_reason"]
    # Positive control: a row just inside the limit is fresh.
    ok = dict(TAPE_ROW, computed_at=NOW - timedelta(seconds=tape.TAPE_STALE_AFTER_SECONDS - 60))
    rec2 = Recorder({"crypto_tape_health_log": [ok]})
    with _pool_patch(rec2):
        cell2 = _run(tape.read_latest_tape_health(["BTC"], now_utc=NOW))["BTC"]
    assert cell2["stale"] is False


def test_tape_stale_limit_matches_job_cadence():
    # The old 600 s limit sat under the 900 s job cadence, so a healthy feed read
    # stale for a third of every cycle. The limit must clear one full cadence.
    assert tape.TAPE_STALE_AFTER_SECONDS > tape.TAPE_JOB_CADENCE_SECONDS


def test_tape_na_row_keeps_leg_reason():
    na = dict(TAPE_ROW, state="NA", spot_cvd=None)
    rec = Recorder({"crypto_tape_health_log": [na]})
    with _pool_patch(rec):
        cell = _run(tape.read_latest_tape_health(["BTC"], now_utc=NOW))["BTC"]
    assert cell["reason"] == "SPOT_FEED_UNAVAILABLE" and cell["value"] is None


# ── cycle extremes ────────────────────────────────────────────────────────────

def test_cycle_get_reads_stored_row_and_never_recomputes_or_writes():
    rec = Recorder({"crypto_cycle_log": [dict(CYCLE_ROW, computed_at=datetime.now(timezone.utc) - timedelta(minutes=20))]})
    calls, boom = _tripwire()
    with _pool_patch(rec), patch.object(cyc, "evaluate_cycle_extremes", boom), \
            patch.object(cyc, "evaluate_all_symbols", boom):
        body = _run(crypto_market.get_cycle_extremes(symbol=None))
        one = _run(crypto_market.get_cycle_extremes(symbol="BTCUSDT"))
    assert calls == [] and rec.writes == []
    btc = body["symbols"]["BTC"]
    assert btc["composite_score"] == -42.0 and btc["composite_method"] == "cap_dominant"
    assert [c["signal_id"] for c in btc["capitulation_cells"]] == ["skew_25delta", "perp_funding"]
    assert [c["signal_id"] for c in btc["froth_cells"]] == ["basis_extreme"]
    assert one["symbol"] == "BTC" and one["composite_score"] == -42.0
    # No stored evaluation: degraded with no score, never a zero.
    sol = body["symbols"]["SOL"]
    assert sol["composite_score"] is None and sol["degraded"] is True


def test_cycle_write_detector_positive_control():
    # The detector sees a real cycle-log INSERT (the job's path still writes).
    rec = Recorder()
    with _pool_patch(rec):
        _run(rec.execute("INSERT INTO crypto_cycle_log (computed_at) VALUES ($1)", NOW))
    assert len(rec.writes) == 1


def test_cycle_old_row_reads_degraded():
    old = dict(CYCLE_ROW, computed_at=NOW - timedelta(seconds=cyc.CYCLE_STALE_AFTER_SECONDS + 60))
    rec = Recorder({"crypto_cycle_log": [old]})
    with _pool_patch(rec):
        p = _run(cyc.read_latest_cycle(["BTC"], now_utc=NOW))["BTC"]
    assert p["degraded"] is True and p["stale"] is True and "hourly" in p["degrade_reason"]
    fresh = dict(CYCLE_ROW, computed_at=NOW - timedelta(seconds=cyc.CYCLE_STALE_AFTER_SECONDS - 60))
    rec2 = Recorder({"crypto_cycle_log": [fresh]})
    with _pool_patch(rec2):
        p2 = _run(cyc.read_latest_cycle(["BTC"], now_utc=NOW))["BTC"]
    assert p2["degraded"] is False


def test_cycle_cells_as_json_text_are_parsed():
    import json
    row = dict(CYCLE_ROW, cells=json.dumps(CYCLE_ROW["cells"]))
    rec = Recorder({"crypto_cycle_log": [row]})
    with _pool_patch(rec):
        p = _run(cyc.read_latest_cycle(["BTC"], now_utc=NOW))["BTC"]
    assert len(p["capitulation_cells"]) == 2 and len(p["froth_cells"]) == 1
