"""DEF-SIGNAL-METADATA (reduced scope, 2026-07-21) tests.

Scope (approved by Nick+Fable after Phase 0 falsified S2/S3 as a
viewing-tool artifact, not a real timestamp bug -- see
docs/codex-briefs/def-signal-metadata-phase0-findings.md):
  1. source passthrough -- log_signal() now persists the real
     signal_data["source"] (set by process_signal_unified) instead of
     silently dropping it and letting the column DEFAULT 'tradingview'
     stamp every row.
  2. timestamp hygiene -- the naive datetime.now() fallbacks in
     webhooks/tradingview.py and scanners/cta_scanner.py that feed a
     signal's `timestamp` (and the TRAPPED_* signal_id date) are now
     datetime.now(timezone.utc), so they're correct regardless of the
     host process timezone (they were correct only by virtue of
     Railway's container clock being UTC).

No DB or network in these tests -- the pool/conn and calendar helper are
mocked; the timestamp checks are static-source regression guards.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.postgres_client import log_signal, _normalize_timestamp_for_db

_BACKEND = os.path.join(os.path.dirname(__file__), "..")


class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _mock_pool():
    conn = MagicMock()
    conn.execute = AsyncMock(return_value="INSERT 0 1")  # ends in "1" -> inserted=True
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


def _signal(**overrides):
    base = {
        "signal_id": "TEST_SRC_1",
        "timestamp": "2026-07-21T06:32:00+00:00",
        "strategy": "CVD_ABSORPTION",
        "ticker": "BTC",
        "asset_class": "CRYPTO",
        "direction": "LONG",
        "signal_type": "CVD_ABSORPTION",
        "entry_price": 65000.0,
        "stop_loss": 64800.0,
        "target_1": 65300.0,
        "bias_at_signal": {"skip": "snapshot"},  # non-empty -> skips get_bias_snapshot()
    }
    base.update(overrides)
    return base


def _run_log_signal(signal_data):
    pool, conn = _mock_pool()
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)), \
         patch("database.postgres_client._build_calendar_metadata", new=AsyncMock(return_value={})):
        asyncio.run(log_signal(signal_data))
    return conn


# ---------------------------------------------------------------------------
# 1. source passthrough
# ---------------------------------------------------------------------------

def test_log_signal_persists_real_source():
    """The core fix: a signal carrying source='crypto_engine' must write
    that value, not the DEFAULT 'tradingview'."""
    conn = _run_log_signal(_signal(source="crypto_engine"))
    args = conn.execute.await_args.args
    assert args[-1] == "crypto_engine", f"source not persisted; got {args[-1]!r}"
    # SQL must actually name the source column now
    assert "source" in args[0]


def test_log_signal_source_varies_by_writer():
    for src in ("cta_scanner", "footprint", "whale_hunter", "crypto_cvd_engine", "server_scanner"):
        conn = _run_log_signal(_signal(signal_id=f"TEST_{src}", source=src))
        assert conn.execute.await_args.args[-1] == src


def test_log_signal_source_falls_back_to_tradingview_when_absent():
    """The only sourceless path is the (unused) direct log_signal() caller;
    fallback preserves the historical column default rather than writing
    NULL."""
    sig = _signal()
    sig.pop("source", None)
    conn = _run_log_signal(sig)
    assert conn.execute.await_args.args[-1] == "tradingview"


def test_log_signal_none_source_falls_back():
    conn = _run_log_signal(_signal(source=None))
    assert conn.execute.await_args.args[-1] == "tradingview"


# ---------------------------------------------------------------------------
# 2a. timestamp storage correctness (aware writer -> correct naive UTC)
# ---------------------------------------------------------------------------

def test_normalize_aware_utc_to_naive_utc_preserves_walltime():
    """Now that writers pass datetime.now(timezone.utc).isoformat(), confirm
    the storage normalizer turns that aware string into the correct naive
    UTC datetime the tz-naive column expects (no offset shift)."""
    out = _normalize_timestamp_for_db("2026-07-21T06:32:00+00:00")
    assert out.tzinfo is None                       # naive, as the column requires
    assert (out.year, out.month, out.day, out.hour, out.minute) == (2026, 7, 21, 6, 32)


def test_normalize_z_suffix_utc():
    out = _normalize_timestamp_for_db("2026-07-21T06:32:00Z")
    assert out.tzinfo is None
    assert out.hour == 6 and out.minute == 32       # Z correctly read as UTC, no shift


def test_normalize_non_utc_aware_converts_to_utc():
    """An aware datetime in a non-UTC zone must be converted to UTC before
    the tzinfo is stripped -- guards against the exact 'naive value carries
    local walltime' class the hygiene fix prevents at the writer."""
    out = _normalize_timestamp_for_db("2026-07-21T00:32:00-06:00")  # 06:32 UTC
    assert out.tzinfo is None
    assert out.hour == 6 and out.minute == 32


# ---------------------------------------------------------------------------
# 2b. static regression guards for the writer hardening
# ---------------------------------------------------------------------------

def _read(rel):
    with open(os.path.join(_BACKEND, rel), encoding="utf-8") as f:
        return f.read()


def test_tradingview_signal_timestamps_are_utc_aware():
    txt = _read("webhooks/tradingview.py")
    # every signal-timestamp fallback is now aware; no naive isoformat remains
    assert "datetime.now().isoformat()" not in txt
    assert txt.count("datetime.now(timezone.utc).isoformat()") >= 7
    # signal_id date/time components (SCOUT_/HG_/ARTEMIS_/PHALANX_/... ids) also aware
    assert "datetime.now().strftime('%Y%m%d_%H%M%S_%f')" not in txt
    assert txt.count("datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')") >= 7
    assert "from datetime import datetime, timezone" in txt


def test_cta_scanner_signal_timestamps_and_ids_are_utc_aware():
    txt = _read("scanners/cta_scanner.py")
    # signal `timestamp` fields: no naive form remains
    assert '"timestamp": datetime.now().isoformat()' not in txt
    # TRAPPED_* signal_id date component: no naive strftime remains
    assert "datetime.now().strftime('%Y%m%d')" not in txt
    assert txt.count("datetime.now(timezone.utc).isoformat()") >= 9
    assert "from datetime import datetime, timedelta, timezone" in txt


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\nAll {len(tests)} DEF-SIGNAL-METADATA tests passed.")
