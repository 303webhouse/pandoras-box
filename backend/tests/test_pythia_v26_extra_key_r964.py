"""PYTHIA v2.6 adds one key — confirm the handler accepts and STORES it. R-IV.964(f).

v2.6 adds `"script": "v2.6"` to the webhook payload. The principal will not recreate the
TradingView alerts until this is confirmed, so the confirmation is a TEST rather than a reading:
a reading says what the code does today, and a test says it still will.

PROVEN HERE, NOT BY A LIVE POST. A synthetic alert against production would insert a fake row
into `pythia_events` -- a real cost to the table LAB and QUERY read -- so the handler is driven
directly with the database stubbed. Nothing is changed in the handler, as the ruling instructs.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from webhooks import pythia_events as pe  # noqa: E402

# A LITERAL FIXTURE VALUE, never the real secret. The test monkeypatches
# pe.PYTHIA_WEBHOOK_SECRET to this string so the hmac check passes in-process; the real value is
# never read, imported or printed here.
SECRET = "test-secret-not-the-real-one"  # secret-scan: allow literal test fixture, not a credential


def _payload(**extra):
    p = {
        "secret": SECRET,
        "ticker": "SPY",
        "alert_type": "va_migration",
        "price": 778.1,
        "vah": 779.0,
        "val": 776.5,
        "poc": 777.8,
        "direction": "LONG",
        "bar_time": int(time.time() * 1000),
    }
    p.update(extra)
    return p


class _Conn:
    """Captures the INSERT's arguments instead of writing them."""

    def __init__(self, sink):
        self.sink = sink

    async def execute(self, sql, *args):
        self.sink.append((sql, args))
        return "INSERT 0 1"

    async def fetchval(self, *a, **k):
        return 1

    async def fetchrow(self, sql="", *args, **k):
        # THE INSERT GOES THROUGH fetchrow, NOT execute (it uses RETURNING id). My first stub
        # recorded only `execute` and returned None here, so it captured nothing while the
        # "accepted" assertions still passed -- a stub that silently proved nothing.
        self.sink.append((sql, args))
        return {"id": 1} if "INSERT INTO pythia_events" in str(sql) else None

    async def fetch(self, *a, **k):
        return []


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


@pytest.fixture
def captured(monkeypatch):
    sink = []
    monkeypatch.setattr(pe, "PYTHIA_WEBHOOK_SECRET", SECRET)

    async def fake_pool():
        return _Pool(_Conn(sink))

    # PATCHED WHERE IT IS LOOKED UP, not where it is defined. `pythia_events` does
    # `from database.postgres_client import get_postgres_client` at MODULE level (line 17), so
    # the name is already bound in this module's namespace and patching the source module has
    # no effect. My first version did exactly that and captured nothing -- the test passed its
    # "accepted" assertions and silently proved nothing about storage.
    monkeypatch.setattr(pe, "get_postgres_client", fake_pool)
    return sink


def _run(payload):
    return asyncio.run(pe.pythia_webhook(payload=payload))



def _stored_payload(captured):
    """The `raw_payload` argument, PARSED back into a dict.

    Not a substring search on the captured args: `raw_payload` is a JSON STRING nested inside
    the outer dump, so its quotes are escaped and `'"script"' in blob` fails on data that is
    plainly present. Parsing answers the actual question -- is the key in the stored object.
    """
    for _sql, args in captured:
        for a in args:
            if isinstance(a, str) and a.startswith("{"):
                try:
                    d = json.loads(a)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("ticker"):
                    return d
    return None


# ── the confirmation the principal is waiting on ─────────────────────────

def test_an_unknown_extra_key_is_ACCEPTED(captured):
    """v2.6's one new key must not turn a good alert into a rejection."""
    out = _run(_payload(script="v2.6"))
    assert out is not None


def test_the_extra_key_is_STORED_in_raw_payload(captured):
    """Accepting it is half the answer; v2.6 is only useful if the value survives. The handler
    persists the whole payload as JSONB with only `secret` removed, so the key is kept verbatim
    rather than filtered to a named whitelist."""
    _run(_payload(script="v2.6"))
    assert captured, "no INSERT was captured"
    stored = _stored_payload(captured)
    assert stored is not None, "no raw_payload argument found"
    assert stored.get("script") == "v2.6", stored


def test_the_secret_is_STILL_stripped_before_persistence(captured):
    """The control that must not regress while confirming the above: the one key that must NOT
    be stored is the secret."""
    _run(_payload(script="v2.6"))
    stored = _stored_payload(captured)
    assert stored is not None
    assert "secret" not in stored, stored
    blob = json.dumps([a for _sql, args in captured for a in args], default=str)
    assert SECRET not in blob


def test_several_unknown_keys_are_all_tolerated(captured):
    """v2.6 adds one key today; the point is that an unknown key is not special-cased, so a
    v2.7 does not need another ruling."""
    _run(_payload(script="v2.6", some_future_field=42, another="x"))
    stored = _stored_payload(captured)
    assert stored is not None
    assert stored.get("script") == "v2.6"
    assert stored.get("some_future_field") == 42
    assert stored.get("another") == "x"


def test_the_handler_takes_a_PLAIN_DICT_and_not_a_strict_model():
    """THE STRUCTURAL REASON it cannot reject an extra key, read from the signature: a Pydantic
    model with `extra="forbid"` here would reject v2.6 outright, and this is the assertion that
    would fail if someone later added one."""
    import inspect

    sig = inspect.signature(pe.pythia_webhook)
    ann = sig.parameters["payload"].annotation
    assert ann in (dict, "dict"), ann


# ── the rejections that MUST survive (nothing else changed) ─────────────

def test_a_wrong_secret_is_still_rejected(captured):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _run(_payload(script="v2.6", secret="wrong"))
    assert e.value.status_code == 401


@pytest.mark.parametrize("bad", [{"vah": 0}, {"val": -1}, {"poc": None}, {"ticker": ""}])
def test_the_required_field_checks_still_bite(captured, bad):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _run(_payload(script="v2.6", **bad))
    assert e.value.status_code == 400


def test_the_replay_window_still_bites(captured):
    from fastapi import HTTPException

    stale = int((time.time() - 3600) * 1000)
    with pytest.raises(HTTPException) as e:
        _run(_payload(script="v2.6", bar_time=stale))
    assert e.value.status_code == 400
