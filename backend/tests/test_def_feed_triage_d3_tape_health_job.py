"""DEF-FEED-TRIAGE D3 -- new scheduled tape-health job
(scheduler/bias_scheduler.py::run_crypto_tape_health_job_scheduled).

Root cause (live-verified 2026-07-20): compute_all_tape_health() was never
registered with the scheduler at all -- S-3b shipped the engine + endpoint
but no caller. The crypto_tape_health_log write history is three isolated
manual-verification bursts (07-16/17/18), not a broken cron. This adds the
missing job, mirroring the existing crypto_regime/crypto_cycle registration
pattern exactly (ENABLE_* kill switch, interval trigger, status tracking,
exception-swallowing so a failure never takes the scheduler loop down).

No live API/database calls -- compute_all_tape_health is mocked.
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scheduler.bias_scheduler import (
    run_crypto_tape_health_job_scheduled,
    _scheduler_status,
    ENABLE_CRYPTO_TAPE_HEALTH_JOB,
)


def _run(coro):
    return asyncio.run(coro)


def test_enabled_by_default():
    """Kill-switch convention: default True, matching crypto_regime/crypto_cycle."""
    assert ENABLE_CRYPTO_TAPE_HEALTH_JOB is True


def test_job_runs_and_updates_status_on_success():
    results = {
        "BTC": {"state": "PERP_LED"},
        "ETH": {"state": "MIXED"},
        "SOL": {"state": "NA", "reason": "SPOT_FEED_UNAVAILABLE"},
    }
    with patch("bias_filters.crypto_tape_health_engine.compute_all_tape_health", new=AsyncMock(return_value=results)):
        _run(run_crypto_tape_health_job_scheduled())
    status = _scheduler_status["crypto_tape_health"]
    assert status["status"] == "completed"
    assert status["rows_written"] == 2  # BTC + ETH are non-NA; SOL is honest NA
    assert status["last_run"] is not None


def test_job_failure_does_not_raise_and_records_error_status():
    with patch("bias_filters.crypto_tape_health_engine.compute_all_tape_health", new=AsyncMock(side_effect=RuntimeError("db down"))):
        _run(run_crypto_tape_health_job_scheduled())  # must not raise
    status = _scheduler_status["crypto_tape_health"]
    assert status["status"].startswith("error:")


def test_job_registered_in_scheduler_status_dict():
    assert "crypto_tape_health" in _scheduler_status
    assert "interval" in _scheduler_status["crypto_tape_health"]
