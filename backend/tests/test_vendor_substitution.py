"""R-IV.433(c) / conventions #21 — a substituted vendor is announced."""
import asyncio
import inspect
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import vendor_substitution as vs  # noqa: E402


def setup_function(_):
    vs._STATE.clear()


def test_an_episode_logs_once_and_its_end_logs_once():
    t0 = datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc)
    clock = {"now": t0}
    with patch.object(vs, "_now", lambda: clock["now"]), patch.object(vs, "logger") as log:
        for i in range(5):
            vs.record_substitution("c", "uw", "yfinance", "empty", f"T{i}")
        vs.record_primary("c", "uw")                       # still inside the window: no restore
        assert log.warning.call_count == 1 and log.info.call_count == 0
        clock["now"] = t0 + timedelta(seconds=vs.RECENT_S + 1)
        vs.record_primary("c", "uw")
        assert log.info.call_count == 1                    # the episode ended
        vs.record_substitution("c", "uw", "yfinance", "empty")
        assert log.warning.call_count == 2                 # a new episode


def test_summary_state_follows_the_window():
    t0 = datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc)
    with patch.object(vs, "_now", lambda: t0):
        vs.record_substitution("c", "uw", "yfinance", "empty", "AAPL")
        vs.record_primary("d", "uw")
    s = vs.summary(now=t0 + timedelta(minutes=5))
    assert s["any_substituting"] is True
    assert s["consumers"]["c"]["state"] == "substituting"
    assert s["consumers"]["c"]["last_subject"] == "AAPL"
    assert s["consumers"]["d"]["state"] == "primary"
    assert vs.summary(now=t0 + timedelta(seconds=vs.RECENT_S + 1))["any_substituting"] is False


def test_recording_never_raises():
    with patch.object(vs, "_now", side_effect=RuntimeError("clock")):
        vs.record_substitution("c", "uw", "yfinance", "x")
        vs.record_primary("c", "uw")


def test_get_bars_announces_its_fallback_and_not_the_index_path():
    from integrations import uw_api
    bars = [{"o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "t": 0}]
    with patch.object(uw_api, "cache_get", new=AsyncMock(return_value=None)), \
         patch.object(uw_api, "cache_set", new=AsyncMock()), \
         patch.object(uw_api, "_get_bars_via_uw", new=AsyncMock(return_value=None)), \
         patch.object(uw_api, "_fetch_yfinance_bars", return_value=list(bars)):
        asyncio.run(uw_api.get_bars("AAPL", 1, "day", "2026-09-01", "2026-09-16"))
        asyncio.run(uw_api.get_bars("^VIX", 1, "day", "2026-09-01", "2026-09-16"))
    c = vs.summary()["consumers"]["uw_api.get_bars"]
    assert c["state"] == "substituting" and c["substitutions"] == 1
    assert (c["primary"], c["fallback"], c["last_subject"]) == ("uw", "yfinance", "AAPL")


def test_get_bars_on_the_primary_records_the_primary():
    from integrations import uw_api
    with patch.object(uw_api, "cache_get", new=AsyncMock(return_value=None)), \
         patch.object(uw_api, "cache_set", new=AsyncMock()), \
         patch.object(uw_api, "_get_bars_via_uw",
                      new=AsyncMock(return_value=[{"o": 1, "h": 1, "l": 1, "c": 1, "t": 0}])):
        asyncio.run(uw_api.get_bars("AAPL", 1, "day"))
    c = vs.summary()["consumers"]["uw_api.get_bars"]
    assert c["state"] == "primary" and c["primary_ok"] == 1


def test_the_triton_fallback_is_announced():
    from jobs import triton_shadow_common as tsc
    fb = [{"c": 10.0, "t": 1757980800000}]
    with patch("integrations.uw_api.get_ohlc", new=AsyncMock(return_value=[])), \
         patch("integrations.uw_api.get_bars_yfinance", new=AsyncMock(return_value=fb)):
        asyncio.run(tsc.fetch_r_close_index("koru", 10))
    assert vs.summary()["consumers"]["triton_grader.bars"]["state"] == "substituting"


def test_the_triton_primary_path_records_the_primary():
    """The path that raised NameError before this test existed: only the fallback was covered."""
    from jobs import triton_shadow_common as tsc
    bars = [{"market_time": "r", "start_time": "2026-09-16T13:30:00Z", "close": "10"}]
    with patch("integrations.uw_api.get_ohlc", new=AsyncMock(return_value=bars)):
        out, provider = asyncio.run(tsc.fetch_r_close_index("koru", 10))
    assert provider == "uw" and out
    assert vs.summary()["consumers"]["triton_grader.bars"]["state"] == "primary"


def test_every_wired_consumer_and_health_publish_it():
    import main
    assert '"vendor_substitution": vendor_block' in inspect.getsource(main)
    for mod, name in [("enrichment.signal_enricher", "enricher.snapshot"),
                      ("jobs.a3_fwd_return_resolver", "a3_fwd.bars"),
                      ("enrichment.universe_cache", "universe_cache.bars"),
                      ("jobs.triton_shadow_common", "triton_grader.bars"),
                      ("integrations.uw_api", "uw_api.get_bars")]:
        src = inspect.getsource(__import__(mod, fromlist=["x"]))
        assert f'record_substitution("{name}"' in src, name
