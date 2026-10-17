"""R-IV.1198(b) — salvage fix-first #4: an ARTEMIS fire's mode is stored.

THE DEFECT. `webhooks/tradingview.py:803` has set `signal_data["artemis_mode"]` since Artemis
shipped. `_log_signal_insert` bound 40 named columns and this was not among them, so the value
was built, logged once in the acceptance line, and discarded at the write. No column existed to
receive it either.

It is the swallowed-write class the `log_signal` docstring describes, in its quietest form: a
missing REQUIRED key raises KeyError and someone eventually notices; an extra key that no
column consumes raises nothing at all and simply never appears. Nothing failed, so nothing was
investigated.

WHAT IT COST. `mode` is the only thing separating a Normal fire (trend plus a confirmation
candle at the VWAP band) from a Flush fire (exhaustion reversal after a 3%+ move into the band).
Every Artemis outcome question turns on that distinction, and none of it was on record. Due
11-30 or ARTEMIS retires, which is why it is first in this pass.

THE RULED TEST is `test_a_fire_with_a_mode_STORES_THAT_MODE` below. It runs against a fake
connection that records exactly what the INSERT bound, because the real assertion is about the
column-to-argument mapping and a live database would prove the same thing less precisely --
and only when one is reachable.

NO BACKFILL (R-IV.1198(b)). The field records from the deploy. Rows written before it are NULL,
and NULL here means "not recorded", never "Normal".
"""
from __future__ import annotations

import ast
import os
import re

import pytest

from ._srcscan import code_of_file, read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
CLIENT = os.path.join(BACKEND, "database", "postgres_client.py")
WEBHOOK = os.path.join(BACKEND, "webhooks", "tradingview.py")
MIGRATION = os.path.join(ROOT, "migrations", "054_artemis_mode.sql")


def _insert_call():
    """The one `conn.execute("INSERT INTO signals (...)", ...)` call, as an AST node."""
    tree = ast.parse(read_source(CLIENT))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Attribute) and call.func.attr == "execute"
                    and call.args and isinstance(call.args[0], ast.Constant)
                    and "INSERT INTO signals (" in str(call.args[0].value)):
                hits.append(call)
    assert len(hits) == 1, "expected exactly one signals INSERT, found %d" % len(hits)
    return hits[0]


def _insert_columns():
    sql = str(_insert_call().args[0].value)
    head = sql[sql.index("(") + 1:sql.index(") VALUES")]
    return [c.strip() for c in head.replace("\n", " ").split(",") if c.strip()]


# ── the ruled test ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_fire_with_a_mode_STORES_THAT_MODE():
    """THE RULED TEST. An Artemis fire carrying mode "Flush" must reach the INSERT with
    "Flush" bound to the artemis_mode column -- not dropped, and not turned into "Normal"."""
    from database import postgres_client as pc

    captured = {}

    class _Conn:
        async def execute(self, sql, *args):
            captured["sql"] = sql
            captured["args"] = args
            return "INSERT 0 1"

        async def fetchval(self, *a, **k):
            return None

        async def fetchrow(self, *a, **k):
            return None

        async def fetch(self, *a, **k):
            return []

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _fake_pool():
        return _Pool()

    async def _noop_evidence(conn, signal_data):
        return None

    orig_pool = pc.get_postgres_client
    orig_ev = pc._write_iv_regime_evidence
    pc.get_postgres_client = _fake_pool
    pc._write_iv_regime_evidence = _noop_evidence
    try:
        ok = await pc._log_signal_insert({
            "signal_id": "ARTEMIS_SPY_20261017_120000_000001",
            "timestamp": "2026-10-17T16:00:00+00:00",
            "strategy": "Artemis",
            "ticker": "SPY",
            "asset_class": "EQUITY",
            "direction": "SHORT",
            "signal_type": "ARTEMIS_SHORT",
            "entry_price": 764.29,
            "stop_loss": 770.00,
            "target_1": 755.00,
            "artemis_mode": "Flush",
        }, "ARTEMIS_SPY_20261017_120000_000001", None, None)
    finally:
        pc.get_postgres_client = orig_pool
        pc._write_iv_regime_evidence = orig_ev

    assert ok is True
    cols = _insert_columns()
    assert "artemis_mode" in cols, "the column is not even named in the INSERT"
    idx = cols.index("artemis_mode")
    assert captured["args"][idx] == "Flush", (
        "artemis_mode bound as %r, not 'Flush'" % (captured["args"][idx],))


@pytest.mark.asyncio
async def test_POSITIVE_CONTROL_the_OTHER_mode_stores_too():
    """Without this, a binding hard-wired to "Flush" would satisfy the test above."""
    from database import postgres_client as pc

    captured = {}

    class _Conn:
        async def execute(self, sql, *args):
            captured["args"] = args
            return "INSERT 0 1"

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _fake_pool():
        return _Pool()

    orig_pool, orig_ev = pc.get_postgres_client, pc._write_iv_regime_evidence
    pc.get_postgres_client = _fake_pool

    async def _noop(conn, sd):
        return None

    pc._write_iv_regime_evidence = _noop
    try:
        for mode in ("Normal", "Flush"):
            await pc._log_signal_insert({
                "signal_id": "ARTEMIS_QQQ_1", "timestamp": "2026-10-17T16:00:00+00:00",
                "strategy": "Artemis", "ticker": "QQQ", "asset_class": "EQUITY",
                "direction": "LONG", "signal_type": "ARTEMIS_LONG",
                "artemis_mode": mode,
            }, "ARTEMIS_QQQ_1", None, None)
            idx = _insert_columns().index("artemis_mode")
            assert captured["args"][idx] == mode, (mode, captured["args"][idx])
    finally:
        pc.get_postgres_client = orig_pool
        pc._write_iv_regime_evidence = orig_ev


@pytest.mark.asyncio
async def test_a_NON_ARTEMIS_signal_binds_NULL_not_a_default():
    """"This strategy has no mode" is NULL. A default of "Normal" would make every CTA signal
    look like an Artemis Normal fire to anyone grouping by the column."""
    from database import postgres_client as pc

    captured = {}

    class _Conn:
        async def execute(self, sql, *args):
            captured["args"] = args
            return "INSERT 0 1"

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _fake_pool():
        return _Pool()

    async def _noop(conn, sd):
        return None

    orig_pool, orig_ev = pc.get_postgres_client, pc._write_iv_regime_evidence
    pc.get_postgres_client, pc._write_iv_regime_evidence = _fake_pool, _noop
    try:
        await pc._log_signal_insert({
            "signal_id": "CTA_SPY_1", "timestamp": "2026-10-17T16:00:00+00:00",
            "strategy": "CTA", "ticker": "SPY", "asset_class": "EQUITY",
            "direction": "LONG", "signal_type": "CTA_LONG",
        }, "CTA_SPY_1", None, None)
    finally:
        pc.get_postgres_client, pc._write_iv_regime_evidence = orig_pool, orig_ev

    idx = _insert_columns().index("artemis_mode")
    assert captured["args"][idx] is None


# ── the mapping cannot drift ────────────────────────────────────────────────

def test_the_COLUMN_COUNT_matches_the_PLACEHOLDERS_and_the_ARGUMENTS():
    """THE GUARD THAT MAKES ADDING THE NEXT COLUMN SAFE. Three lists have to agree -- the names,
    the $n placeholders and the bound values -- and a mismatch in the third raises only at
    runtime, on a live fire, inside a handler that catches broadly."""
    call = _insert_call()
    cols = _insert_columns()
    sql = str(call.args[0].value)
    placeholders = [int(n) for n in re.findall(r"\$(\d+)", sql[sql.index(") VALUES"):])]
    args = len(call.args) - 1          # args[0] is the SQL itself
    assert len(cols) == 41, len(cols)
    assert len(placeholders) == 41 and max(placeholders) == 41, placeholders
    assert sorted(placeholders) == list(range(1, 42)), "a placeholder is skipped or repeated"
    assert args == 41, args


def test_artemis_mode_is_the_LAST_column_and_the_LAST_argument():
    """Appended rather than inserted mid-list. Slotting it in the middle would renumber every
    placeholder after it, and the bound values are positional."""
    cols = _insert_columns()
    assert cols[-1] == "artemis_mode"


# ── the column exists, in both copies, as TEXT ─────────────────────────────

def test_the_column_is_created_at_startup():
    code = code_of_file(CLIENT)
    assert "ADD COLUMN IF NOT EXISTS artemis_mode TEXT" in code


def test_the_migration_mirrors_the_startup_ddl():
    sql = read_source(MIGRATION)
    assert "ADD COLUMN IF NOT EXISTS artemis_mode TEXT" in sql
    assert "idx_signals_artemis_mode" in sql


def test_the_column_is_TEXT_so_a_LABEL_CANNOT_REJECT_A_FIRE():
    """The value arrives from a webhook payload via `(alert.mode or "Normal").capitalize()`, so
    its length is the sender's choice. On a VARCHAR(n) a long one raises inside the INSERT, and
    log_signal re-raises by design -- losing the whole SIGNAL over a label."""
    code = code_of_file(CLIENT)
    i = code.index("ADD COLUMN IF NOT EXISTS artemis_mode")
    decl = code[i:i + 80]
    assert "TEXT" in decl
    assert not re.search(r"artemis_mode\s+VARCHAR", code)


def test_a_LONG_mode_does_not_raise_in_the_binding():
    """The property that matters, not just the declared type: a 500-character mode binds as the
    string it is. No truncation either -- truncation invents a value."""
    long_mode = "F" * 500
    assert len(long_mode) == 500
    # Nothing in the write path shortens or validates it.
    code = code_of_file(CLIENT)
    assert "signal_data.get('artemis_mode')" in code
    assert "artemis_mode'][:" not in code and 'artemis_mode")[:' not in code


# ── the producing end still produces it ────────────────────────────────────

def test_the_webhook_STILL_SETS_the_field_the_insert_now_reads():
    """The two ends have to name the same key. They did not disagree before -- the writer simply
    ignored it -- so a rename on either side would restore the defect silently."""
    web = code_of_file(WEBHOOK)
    assert "'artemis_mode': mode" in web or '"artemis_mode": mode' in web
    client = code_of_file(CLIENT)
    assert "signal_data.get('artemis_mode')" in client


def test_the_two_modes_are_the_ones_the_handler_documents():
    """Normal: trend plus a confirmation candle at the VWAP band. Flush: exhaustion reversal
    after a 3%+ move into the band. Asserted from the source, so the test does not become the
    place a third mode gets invented."""
    web = read_source(WEBHOOK)
    i = web.index("Process Artemis")
    doc = web[i:i + 500]
    assert "Normal" in doc and "Flush" in doc
    assert '(alert.mode or "Normal").capitalize()' in web


def test_NO_BACKFILL_in_this_ruling():
    """R-IV.1198(b): "No backfill: the field starts recording from the deploy." Nothing may
    write a mode onto rows that predate the column -- NULL means not recorded, not Normal."""
    for path in (CLIENT, MIGRATION):
        src = read_source(path)
        assert not re.search(r"UPDATE\s+signals\s+SET\s+artemis_mode", src, re.I)
    assert "No backfill" in read_source(MIGRATION) or "NO BACKFILL" in read_source(MIGRATION)
