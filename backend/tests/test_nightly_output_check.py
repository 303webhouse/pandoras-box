"""R-IV.426 — the nightly's own output is its success predicate; a completed pass that
produced nothing is a recorded failure and is NOT retried; one Yahoo symbol mapping.

The defect this guards: for eight days the nightly reported `ok` while storing zero theme
rows, because "no exception" was the only success test.
"""
import asyncio
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import job_runs, stable_jobs  # noqa: E402
from stable_engine import bars_yf  # noqa: E402

GOOD = {"coverage": 98.12, "degraded": False, "metrics_rows": 871700, "themes_stored": 44}


# ── the predicate ────────────────────────────────────────────────────────────────────────

def test_a_pass_with_output_is_ok():
    stable_jobs.check_nightly_output(GOOD)


def test_the_eight_day_night_is_now_a_failure():
    """The exact result logged by production on 2026-09-16."""
    night = {"coverage": 98.12, "degraded": False, "metrics_rows": 871700, "themes_stored": 0}
    with pytest.raises(stable_jobs.OutputCheckFailed) as e:
        stable_jobs.check_nightly_output(night)
    assert "themes_stored=0" in str(e.value)
    assert "98.12" in str(e.value)


def test_no_metrics_is_a_failure_too():
    with pytest.raises(stable_jobs.OutputCheckFailed):
        stable_jobs.check_nightly_output({**GOOD, "metrics_rows": 0})


def test_degraded_download_with_no_output_is_RETRYABLE():
    """The retry exists for a pass that did not properly complete. A degraded download is
    that case, so it must NOT be classed as the non-retried kind."""
    with pytest.raises(RuntimeError) as e:
        stable_jobs.check_nightly_output({**GOOD, "degraded": True, "themes_stored": 0})
    assert not isinstance(e.value, stable_jobs.OutputCheckFailed)


def test_missing_fields_are_not_success():
    with pytest.raises(stable_jobs.OutputCheckFailed):
        stable_jobs.check_nightly_output({"coverage": 99.0, "degraded": False})


# ── how _record closes each outcome ─────────────────────────────────────────────────────

def _run_record(coro_fn):
    finished = []

    async def fake_finish(run_id, status, error=None):
        finished.append((status, error))

    with patch.object(job_runs, "start_run", AsyncMock(return_value=7)), \
         patch.object(stable_jobs, "_finish_run", side_effect=fake_finish), \
         patch.object(stable_jobs, "_fire_flatline_alert", AsyncMock()), \
         patch("stable_engine.job_status.mark_success", AsyncMock()) as ok, \
         patch("stable_engine.job_status.mark_failure", AsyncMock(return_value=False)) as bad:
        asyncio.run(stable_jobs._record("nightly", coro_fn, session_date=date(2026, 9, 16)))
    return finished, ok, bad


def test_output_failure_is_recorded_as_failed_AND_as_a_completed_pass():
    async def job():
        raise stable_jobs.OutputCheckFailed("themes_stored=0")
    finished, ok, bad = _run_record(job)
    assert finished and finished[0][0] == job_runs.STATUS_COMPLETED_DEFECTIVE
    assert "themes_stored=0" in (finished[0][1] or "")
    bad.assert_awaited_once()          # the dashboard sees the failure and the reason
    ok.assert_not_awaited()


def test_an_ordinary_exception_stays_retryable():
    async def job():
        raise RuntimeError("yahoo timed out")
    finished, _, bad = _run_record(job)
    assert finished[0][0] == "error"
    bad.assert_awaited_once()


def test_success_is_unchanged():
    async def job():
        return GOOD
    finished, ok, bad = _run_record(job)
    assert finished[0][0] == "ok"
    ok.assert_awaited_once()
    bad.assert_not_awaited()


# ── the retry reads it ──────────────────────────────────────────────────────────────────

def test_the_retry_counts_a_defective_pass_as_done():
    assert job_runs.STATUS_COMPLETED_DEFECTIVE in job_runs.PASS_COMPLETE_STATUSES
    assert job_runs.STATUS_OK in job_runs.PASS_COMPLETE_STATUSES
    assert "error" not in job_runs.PASS_COMPLETE_STATUSES


def test_has_completed_queries_the_whole_completed_set():
    captured = {}

    class Conn:
        async def fetchval(self, sql, *args):
            captured["sql"], captured["args"] = sql, args
            return 1

    class Acquire:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *a):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    with patch("database.postgres_client.get_postgres_client", AsyncMock(return_value=Pool())):
        assert asyncio.run(job_runs.has_completed(job_runs.JOB_NIGHTLY, date(2026, 9, 16))) is True
    assert "ANY(" in captured["sql"]
    assert set(captured["args"][2]) == set(job_runs.PASS_COMPLETE_STATUSES)


def test_freshness_does_not_count_a_defective_pass():
    """last_completed answers 'when did good data last land' — a pass that stored nothing
    must not refresh that answer."""
    import inspect
    src = inspect.getsource(job_runs.last_completed)
    assert "STATUS_COMPLETED_DEFECTIVE" not in src


# ── one symbol mapping ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("given,want", [
    ("BRK.B", "BRK-B"), ("BF.B", "BF-B"), ("BRK.A", "BRK-A"),
    ("AAPL", "AAPL"), ("7203.T", "7203.T"), ("SHOP.TO", "SHOP.TO"),
    ("BTC-USD", "BTC-USD"), ("^GSPC", "^GSPC"), ("", ""),
])
def test_to_yahoo_symbol(given, want):
    assert bars_yf.to_yahoo_symbol(given) == want


def test_fetch_batch_requests_yahoo_form_and_stores_universe_form():
    idx = pd.to_datetime(["2026-09-15", "2026-09-16"])
    cols = pd.MultiIndex.from_product([["BRK-B", "AAPL"], ["Open", "High", "Low", "Close", "Volume"]])
    data = pd.DataFrame(1.0, index=idx, columns=cols)
    seen = {}

    def fake_download(tickers, **kw):
        seen["requested"] = list(tickers)
        return data

    with patch("yfinance.download", side_effect=fake_download):
        out = bars_yf.fetch_batch(["BRK.B", "AAPL"], date(2026, 9, 2), date(2026, 9, 17))
    assert seen["requested"] == ["BRK-B", "AAPL"]
    assert sorted(out) == ["AAPL", "BRK.B"]          # never "BRK-B"
    assert len(out["BRK.B"]) == 2
