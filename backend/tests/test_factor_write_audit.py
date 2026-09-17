"""R-IV.442(b) — a write into the regime engine leaves a line, and never leaks the key.

FAIL-FIRST against the pre-2026-09-17 tree: no audit existed on any factor write, and the
collector trigger fired on every velocity breach regardless of whether anything was listening.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from utils import factor_write_audit as fwa  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "038_factor_write_audit.sql"
BOOT = ROOT / "backend" / "database" / "postgres_client.py"


# --- the credential never becomes an identity ----------------------------------------------
def test_the_api_key_itself_is_never_the_caller_identity():
    """FastAPI's auth dependency returns the KEY on the header path. Passing that through
    would write a live secret into a table and into every log line quoting it."""
    secret = "a-secret-value-that-must-not-propagate"
    assert fwa.auth_mode(secret) == "api_key"
    assert secret not in fwa.auth_mode(secret)


def test_the_three_modes_are_distinguishable():
    assert fwa.auth_mode("session") == "session"
    assert fwa.auth_mode(None) == "none"
    assert fwa.auth_mode("") == "none"


def test_the_caller_is_what_the_request_reveals_and_says_when_it_reveals_nothing():
    req = MagicMock()
    req.client.host = "10.0.0.7"
    req.headers = {"user-agent": "pivot-collector/2.1", "x-caller": "pivot"}
    assert fwa.caller_of(req) == "pivot@10.0.0.7 (pivot-collector/2.1)"

    bare = MagicMock()
    bare.client = None
    bare.headers = {}
    out = fwa.caller_of(bare)
    assert "unknown-host" in out and "unknown-agent" in out


def test_an_unreadable_request_does_not_raise():
    broken = MagicMock()
    type(broken).headers = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    assert fwa.caller_of(broken) == "unreadable-request"


# --- the audit records, and never fails the write it observes ------------------------------
class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _pool():
    conn = MagicMock()
    conn.calls = []

    async def execute(sql, *args):
        conn.calls.append((" ".join(sql.split()), args))

    conn.execute = execute
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


def test_an_accepted_write_records_endpoint_factor_caller_and_mode(monkeypatch):
    pool, conn = _pool()
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
        asyncio.run(fwa.record_factor_write("POST /bias/factors/{factor_name}",
                                            factor_id="gex", caller="pivot@10.0.0.7 (ua)",
                                            auth="api_key", source="pivot", score=0.42))
    sql, args = conn.calls[0]
    assert "INSERT INTO factor_write_audit" in sql
    assert args[0] == "POST /bias/factors/{factor_name}" and args[1] == "gex"
    assert args[3] == "api_key" and args[4] == "pivot" and args[5] == 0.42


def test_a_failed_audit_does_not_fail_the_write(monkeypatch):
    """An instrument that can break the thing it measures is not an instrument."""
    with patch("database.postgres_client.get_postgres_client",
               new=AsyncMock(side_effect=RuntimeError("db down"))):
        asyncio.run(fwa.record_factor_write("POST /bias/override", factor_id="OVERRIDE:RISK_ON",
                                            caller="x", auth="none"))


# --- the endpoints are wired ---------------------------------------------------------------
def test_every_factor_write_endpoint_audits_its_acceptance():
    from api import bias
    for fn, endpoint in ((bias.update_factor_from_pivot, "POST /bias/factors/{factor_name}"),
                         (bias.update_factor_reading, "POST /bias/factor-update"),
                         (bias.set_bias_override, "POST /bias/override")):
        src = inspect.getsource(fn)
        assert "record_factor_write(" in src, f"{endpoint} does not audit"
        assert endpoint in src


def test_the_audit_line_comes_after_the_write_not_before():
    """An audit written first would make a failed write look real."""
    from api import bias
    src = inspect.getsource(bias.update_factor_from_pivot)
    assert src.index("record_factor_reading(") < src.index("record_factor_write(")


def test_the_migration_and_boot_agree():
    sql = MIGRATION.read_text(encoding="utf-8")
    boot = BOOT.read_text(encoding="utf-8")
    for token in ("factor_write_audit", "claimed_source", "auth_mode",
                  "idx_factor_write_audit_time"):
        assert token in sql and token in boot, token
    assert "-- DOWN" in sql


# --- the retired door ----------------------------------------------------------------------
def test_the_collector_trigger_is_off_unless_explicitly_enabled(monkeypatch):
    import importlib
    from webhooks import hermes
    monkeypatch.delenv("HERMES_VPS_TRIGGER_ENABLED", raising=False)
    importlib.reload(hermes)
    assert hermes.VPS_TRIGGER_ENABLED is False
    monkeypatch.setenv("HERMES_VPS_TRIGGER_ENABLED", "true")
    importlib.reload(hermes)
    assert hermes.VPS_TRIGGER_ENABLED is True
    monkeypatch.delenv("HERMES_VPS_TRIGGER_ENABLED", raising=False)
    importlib.reload(hermes)


def test_the_disabled_path_says_so_instead_of_failing_quietly():
    from webhooks import hermes
    src = inspect.getsource(hermes)
    assert "not VPS_TRIGGER_ENABLED" in src
    assert "nothing sent outbound" in src
