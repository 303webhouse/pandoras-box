"""The tide warmer actually runs a cycle and writes the cell — and no helper is called by a
name that does not exist.

THE LIVE BUG THIS CLOSES (2026-10-07, mine). `084fdd5` wired the tide warmer through
`_run_job("market_tide", _warm_tide)`. **There is no `_run_job`.** The helper is `_record`, which
is what all fourteen other call sites use. So every 5-minute cycle raised `NameError`, the loop's
broad `except` swallowed it, `board:tide:latest` was never written, and **the v2 Tide cell was dark
from the open.** The same fault sat at the `spy_minute` site from `d564053`.

Before that change the loop called `await _warm_tide()` directly and WORKED. I replaced a working
call with a non-existent wrapper.

WHY THE EXISTING TESTS PASSED, which is the part worth not repeating. They string-matched the
source: `assert '_run_job("market_tide", _warm_tide)' in src`. That asserts the presence of the
text I had just written — including the wrong name — so the test and the bug agreed with each
other. `py_compile` cannot catch it either: the name is resolved only when the line runs, and the
line is inside a function, so an import does not reach it.

So this file tests two different things:
  1. a REAL cycle, through the same helper the loop uses, writing the real Redis key;
  2. structurally, that no private helper anywhere in the backend is CALLED by a name that is
     never defined — the general form of the fault, not just this instance.
"""

import ast
import builtins
import json
import os
from typing import Any, Dict, List

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILTINS = set(dir(builtins))

TIDE_PAYLOAD = {"data": [
    {"timestamp": "2026-10-07T09:30:00-04:00", "date": "2026-10-07",
     "net_call_premium": "20650902.0000", "net_put_premium": "-4503628.0000",
     "net_volume": 61108},
    {"timestamp": "2026-10-07T09:35:00-04:00", "date": "2026-10-07",
     "net_call_premium": "66692614.0000", "net_put_premium": "-5613996.0000",
     "net_volume": 261253},
]}


class _Redis:
    def __init__(self):
        self.setex_calls: List[Any] = []

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))


class _Conn:
    def __init__(self):
        self.executed: List[Any] = []

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))


class _Acq:
    def __init__(self, conn):
        self._c = conn

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, *a):
        return False

    def __call__(self):
        return self


def _pool(conn):
    class P:
        acquire = _Acq(conn)
    return P()


@pytest.fixture
def wired(monkeypatch):
    """Stub only the three edges: the vendor, Redis, and the DB. Everything between them --
    `_record`, `_warm_tide`, `persist_series` -- is the real code under test, because the bug was
    in the WIRING and a test that stubs the wiring cannot see it."""
    import database.postgres_client as pg
    import database.redis_client as rc
    import integrations.uw_api as uw
    import stable_engine.job_status as js

    redis = _Redis()
    conn = _Conn()

    async def _tide():
        return TIDE_PAYLOAD

    async def _get_redis():
        return redis

    async def _get_pool():
        return _pool(conn)

    marked: Dict[str, Any] = {}

    async def _ok(job_name):
        marked["success"] = job_name

    async def _fail(job_name, err):
        marked["failure"] = (job_name, err)
        return False

    monkeypatch.setattr(uw, "get_market_tide", _tide)
    monkeypatch.setattr(rc, "get_redis_client", _get_redis)
    monkeypatch.setattr(pg, "get_postgres_client", _get_pool)
    monkeypatch.setattr(js, "mark_success", _ok)
    monkeypatch.setattr(js, "mark_failure", _fail)
    return {"redis": redis, "conn": conn, "marked": marked}


class TestARealCycleWritesTheCell:
    @pytest.mark.asyncio
    async def test_one_cycle_through_the_loops_own_helper_writes_board_tide_latest(self, wired):
        """THE TEST THAT WAS MISSING. Runs the cycle the way the loop runs it — through the same
        helper — and asserts the key the v2 cell reads actually gets written."""
        from jobs.stable_jobs import _record, _warm_tide

        await _record("market_tide", _warm_tide)

        keys = [c[0] for c in wired["redis"].setex_calls]
        assert "board:tide:latest" in keys, (
            "the v2 Tide cell reads this key; if it is not written the cell is dark")
        key, ttl, raw = wired["redis"].setex_calls[0]
        payload = json.loads(raw)
        assert ttl == 1800
        # the LAST reading of the series, which is what the cell shows
        assert payload["net_call_premium"] == "66692614.0000"
        assert payload["net_volume"] == 261253
        assert "warmed_at" in payload

    @pytest.mark.asyncio
    async def test_the_same_cycle_also_persists_the_series(self, wired):
        """R-IV.675(b) and the cell are one cycle, not two. The whole series is upserted while the
        cell takes the last row."""
        from jobs.stable_jobs import _record, _warm_tide

        await _record("market_tide", _warm_tide)
        upserts = [e for e in wired["conn"].executed if "market_tide_history" in e[0]]
        assert len(upserts) == 2, "both readings in the payload are stored, not just the last"

    @pytest.mark.asyncio
    async def test_the_cycle_is_recorded_as_a_SUCCESS_not_a_swallowed_failure(self, wired):
        """The bug's signature was a job that never reported anything. A cycle that completes must
        mark success, which is what puts `market_tide` in /health's jobs block."""
        from jobs.stable_jobs import _record, _warm_tide

        await _record("market_tide", _warm_tide)
        assert wired["marked"].get("success") == "market_tide"
        assert "failure" not in wired["marked"]

    @pytest.mark.asyncio
    async def test_a_vendor_that_returns_nothing_still_does_not_raise(self, wired, monkeypatch):
        """POSITIVE CONTROL. The loop must keep ticking on an empty vendor read, and the cell
        simply is not refreshed — that is different from the NameError case, where the cycle
        never got as far as asking."""
        import integrations.uw_api as uw

        async def _none():
            return None

        monkeypatch.setattr(uw, "get_market_tide", _none)
        from jobs.stable_jobs import _record, _warm_tide

        await _record("market_tide", _warm_tide)
        assert wired["redis"].setex_calls == []


class TestNoHelperIsCalledByANameThatDoesNotExist:
    """The general form of the fault, not just this instance.

    `py_compile` cannot see it (the name resolves only when the line runs) and an import cannot
    either (the line is inside a function). pyflakes would, and is not installed in this
    environment — so the check lives here, where it runs on every suite.
    """

    FILES = [
        "jobs/stable_jobs.py", "jobs/market_tide_sink.py", "jobs/spy_minute_sink.py",
        "jobs/spy_minute_backfill.py", "jobs/tide_backfill.py", "jobs/loss_alert.py",
        "strategies/registered_shadow.py",
        "jobs/iv_snapshot.py",
        "api/portfolio.py", "api/unified_positions.py", "api/crypto_market.py",
        "bias_filters/crypto_perps.py", "bias_filters/crypto_cycle_engine.py",
        "services/open_quantity.py", "services/position_economics.py",
        "services/read_only/positions.py", "models/position_lots.py",
        "models/position_direction.py", "config/accounts.py", "signals/feed_service.py",
    ]

    @staticmethod
    def _bound(tree):
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    out.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    out.add(a.asname or a.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.add(node.name)
                args = node.args
                for a in (list(args.args) + list(args.kwonlyargs) + list(args.posonlyargs)):
                    out.add(a.arg)
                if args.vararg:
                    out.add(args.vararg.arg)
                if args.kwarg:
                    out.add(args.kwarg.arg)
            elif isinstance(node, ast.ClassDef):
                out.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                out.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                out.add(node.name)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                out.update(node.names)
        return out

    @pytest.mark.parametrize("rel", FILES)
    def test_every_private_call_resolves(self, rel):
        path = os.path.join(BACKEND, rel)
        if not os.path.exists(path):
            pytest.skip("%s absent" % rel)
        tree = ast.parse(open(path, encoding="utf-8-sig").read())
        known = self._bound(tree) | BUILTINS
        missing = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                n = node.func.id
                if n.startswith("_") and n not in known:
                    missing.setdefault(n, node.lineno)
        assert not missing, (
            "%s calls private helper(s) that are never defined: %s. This is the shape that took "
            "the Tide cell down -- _run_job() called at two sites and defined nowhere."
            % (rel, ", ".join("%s() at line %d" % (n, l) for n, l in sorted(missing.items()))))

    def test_the_check_can_fail(self):
        """POSITIVE CONTROL (#30). A structural check that cannot fail is decorative, and this
        one exists because the tests it replaces could not fail."""
        tree = ast.parse("def f():\n    return _does_not_exist()\n")
        known = self._bound(tree) | BUILTINS
        found = [n.func.id for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id.startswith("_") and n.func.id not in known]
        assert found == ["_does_not_exist"]
