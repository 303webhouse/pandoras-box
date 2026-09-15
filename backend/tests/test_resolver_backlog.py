"""R-IV.383(c) — the unresolved fraction published beside the budget.

`outcome_resolver` is the hub's largest UW caller, and its spend is
`unresolved_signals x runs_per_day` because every unresolved signal in the
rolling window is re-fetched on every run. So a WORSENING SIGNAL GENERATOR —
more signals touching neither target nor stop — raises the UW bill with no code
change and no alarm.

The budget is coupled to a quality metric. These tests are about making that
coupling visible, and about the two ways the number itself could lie.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import outcome_resolver as r


class _Conn:
    def __init__(self, total, unresolved):
        self._t, self._u = total, unresolved

    async def fetchval(self, q):
        return self._u if "outcome IS NULL" in q else self._t

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, conn):
        self._c = conn

    def acquire(self):
        return self._c


@pytest.fixture
def pool(monkeypatch):
    holder = {}

    async def fake_pool():
        return _Pool(holder["conn"])

    import database.postgres_client as pc
    monkeypatch.setattr(pc, "get_postgres_client", fake_pool, raising=False)
    return holder


@pytest.mark.asyncio
async def test_reports_the_fraction(pool):
    pool["conn"] = _Conn(200, 50)
    out = await r.resolver_backlog_status()
    assert out["measurable_signals"] == 200
    assert out["unresolved"] == 50
    assert out["resolved"] == 150
    assert out["unresolved_fraction"] == 0.25


@pytest.mark.asyncio
async def test_empty_population_yields_none_not_nan(pool):
    """A rate over an empty population is the NaN that took /health down on
    2026-09-14. It must be None, and the endpoint must still serialise."""
    import json
    import math
    pool["conn"] = _Conn(0, 0)
    out = await r.resolver_backlog_status()
    assert out["unresolved_fraction"] is None
    assert not any(isinstance(v, float) and math.isnan(v) for v in out.values())
    json.dumps(out)


@pytest.mark.asyncio
async def test_all_unresolved_is_one_not_an_error(pool):
    pool["conn"] = _Conn(75, 75)
    out = await r.resolver_backlog_status()
    assert out["unresolved_fraction"] == 1.0


@pytest.mark.asyncio
async def test_never_raises_on_a_dead_pool(monkeypatch):
    async def boom():
        raise RuntimeError("db down")

    import database.postgres_client as pc
    monkeypatch.setattr(pc, "get_postgres_client", boom, raising=False)
    out = await r.resolver_backlog_status()
    assert out["state"] == "ERROR"


def test_the_predicate_mirrors_the_resolver_s_own():
    """If the two drift, this number describes a different population than the
    one actually being re-fetched — worse than no number, because it would look
    like a reconciliation. The same-predicate test, third use."""
    src = (Path(__file__).resolve().parents[1] / "jobs" / "outcome_resolver.py").read_text(
        encoding="utf-8")
    for clause in ("status NOT IN ('DISMISSED', 'EXPIRED')",
                   "signal_type NOT IN ('SCOUT_ALERT')",
                   "entry_price IS NOT NULL"):
        assert src.count(clause) >= 2, "predicate clause not shared: %s" % clause


def test_window_matches_the_resolver_default():
    import inspect
    sig = inspect.signature(r.resolve_signal_outcomes)
    assert sig.parameters["backfill_days"].default == r.RESOLVER_WINDOW_DAYS


def test_the_note_says_what_the_number_is_for():
    """A count nobody can interpret is a count nobody reads."""
    import asyncio

    async def _run():
        import database.postgres_client as pc
        orig = getattr(pc, "get_postgres_client", None)

        async def fake():
            return _Pool(_Conn(10, 2))

        pc.get_postgres_client = fake
        try:
            return await r.resolver_backlog_status()
        finally:
            if orig:
                pc.get_postgres_client = orig

    out = asyncio.run(_run())
    assert "multiplier" in out["note"]
    assert out["uw_caller"] == "outcome_resolver"
