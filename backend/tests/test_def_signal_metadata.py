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
import pytest
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


# log_signal()'s positional parameters, READ OFF ITS OWN INSERT rather than counted
# backwards from the end.
#
# These were `-3`, `-2`, `-1`, with a comment promising that a future append would "fail
# loudly here". It did not. R-IV.587(b) appended `release_at` as $40 and all three indices
# slid one column to the left in silence: the source assertion began reading `status`, found
# 'ACTIVE', and reported "source not persisted". The failure named the wrong defect, which is
# the real cost — a positional index that nothing anchors will eventually point somewhere else
# and still look like an assertion about the thing it was named for.
#
# So the index is now DERIVED from the column list in the statement itself. An append moves
# nothing; a RENAME or a removal raises here by name, which is the case worth failing on.


def _arg_index(column: str) -> int:
    """Which positional argument carries `column`, from log_signal's own INSERT."""
    import inspect
    import re

    from database import postgres_client as _pc

    src = inspect.getsource(_pc.log_signal)
    match = re.search(r"INSERT INTO signals \(\s*(.*?)\)\s*VALUES", src, re.S)
    assert match, "log_signal's INSERT could not be read"
    columns = [c.strip() for c in match.group(1).split(",")
               if c.strip() and not c.strip().startswith("--")]
    assert column in columns, "%s is not a column of log_signal's INSERT; it lists %s" % (
        column, columns)
    # The parameters follow the SQL string, so argument 0 is the statement itself.
    return columns.index(column) + 1


SOURCE_ARG = _arg_index("source")
STATUS_ARG = _arg_index("status")
EXPIRES_ARG = _arg_index("expires_at")
RELEASE_ARG = _arg_index("release_at")


def test_the_parameter_indices_are_read_off_the_statement_not_counted_backwards():
    """The guard the old `-3, -2, -1` could not give.

    POSITIVE CONTROL: the derivation really does find distinct, ordered positions, and it
    raises by name for a column that is not there — so a rename fails loudly instead of
    re-pointing an assertion at its neighbour.
    """
    assert SOURCE_ARG < STATUS_ARG < EXPIRES_ARG < RELEASE_ARG
    assert len({SOURCE_ARG, STATUS_ARG, EXPIRES_ARG, RELEASE_ARG}) == 4
    with pytest.raises(AssertionError):
        _arg_index("a_column_that_does_not_exist")


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
    assert args[SOURCE_ARG] == "crypto_engine", f"source not persisted; got {args[SOURCE_ARG]!r}"
    # SQL must actually name the source column now
    assert "source" in args[0]


def test_log_signal_source_varies_by_writer():
    for src in ("cta_scanner", "footprint", "whale_hunter", "crypto_cvd_engine", "server_scanner"):
        conn = _run_log_signal(_signal(signal_id=f"TEST_{src}", source=src))
        assert conn.execute.await_args.args[SOURCE_ARG] == src


def test_log_signal_source_falls_back_to_tradingview_when_absent():
    """The only sourceless path is the (unused) direct log_signal() caller;
    fallback preserves the historical column default rather than writing
    NULL."""
    sig = _signal()
    sig.pop("source", None)
    conn = _run_log_signal(sig)
    assert conn.execute.await_args.args[SOURCE_ARG] == "tradingview"


def test_log_signal_none_source_falls_back():
    conn = _run_log_signal(_signal(source=None))
    assert conn.execute.await_args.args[SOURCE_ARG] == "tradingview"


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


def test_log_signal_status_defaults_to_active_for_ordinary_writers():
    """STRIKE-SPEC-01 regression guard. $38 `status` was appended to log_signal so
    the STRIKE converter could persist status='SHADOW'. Every OTHER writer must
    still land 'ACTIVE' — including writers that set signal_data["status"]
    themselves (webhooks/tradingview.py:538 sets 'IGNORE'), because honoring
    those would change what board_state and trade_ideas display.
    See docs/defects/DEF-SIGNAL-STATUS-DISCARDED.md."""
    conn = _run_log_signal(_signal(source="crypto_engine"))
    assert conn.execute.await_args.args[STATUS_ARG] == "ACTIVE"

    conn = _run_log_signal(_signal(source="tradingview", status="IGNORE"))
    assert conn.execute.await_args.args[STATUS_ARG] == "ACTIVE", (
        "an IGNORE status must NOT reach the insert — that is a live-surface change"
    )

    conn = _run_log_signal(_signal(source="STRIKE_IB_BREAK", status="SHADOW"))
    assert conn.execute.await_args.args[STATUS_ARG] == "SHADOW"


def test_log_signal_persists_expires_at_as_naive_utc():
    """R-IV.432(f): the pipeline's computed expiry is stored ($39), never discarded."""
    from datetime import datetime, timezone
    conn = _run_log_signal(_signal(expires_at=datetime(2026, 9, 17, 18, 0, tzinfo=timezone.utc)))
    assert conn.execute.await_args.args[EXPIRES_ARG] == datetime(2026, 9, 17, 18, 0)
    assert "expires_at" in conn.execute.await_args.args[0]
    conn = _run_log_signal(_signal())
    assert conn.execute.await_args.args[EXPIRES_ARG] is None
