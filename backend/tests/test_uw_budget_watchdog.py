"""Acceptance test for the UW budget watchdog (Fable 2026-07-09).

Covers the pre-registered acceptance criteria with fakes (no prod Redis/Discord/DB):
  - simulated trigger (injected total >= 17K) -> shed flag SETS
  - exactly ONE alert fires (SET NX => first-of-day only; second tick is silent)
  - the flag carries a TTL that clears at the UTC rollover (ex set, 0 < ex <= 86400)
  - the Triton poller cycle SKIPS while the flag is set (get_flow_alerts never reached)
  - >= 18K escalation fires a SECOND (human-call) alert
  - the daily-burn snapshot WRITES rows (per-caller + _TOTAL) to uw_daily_burn

Dependency-free: async coroutines are driven via asyncio.run(), so no pytest-asyncio
config is required in backend/tests/.
"""

import asyncio
from datetime import date

import jobs.uw_budget_watchdog as wd


class FakeRedis:
    def __init__(self, hashes=None, strings=None):
        self.store = dict(strings or {})
        self.hashes = dict(hashes or {})
        self.set_calls = []

    async def set(self, key, val, nx=False, ex=None):
        self.set_calls.append((key, val, nx, ex))
        if nx and key in self.store:
            return None            # NX miss -> not set (already present)
        self.store[key] = val
        return True

    async def get(self, key):
        return self.store.get(key)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))


def _aret(val):
    async def _f(*a, **k):
        return val
    return _f


def _patch_alerts(monkeypatch):
    fired = []

    async def fake_alert(title, description, color=0xFF4444):
        fired.append((title, description))
        return True

    monkeypatch.setattr(wd, "_discord_alert", fake_alert)
    return fired


def _patch_jobstatus(monkeypatch):
    async def _noop(*a, **k):
        return False
    monkeypatch.setattr("stable_engine.job_status.mark_success", _noop)
    monkeypatch.setattr("stable_engine.job_status.mark_failure", _noop)


def test_shed_sets_flag_and_fires_exactly_one_alert(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr("database.redis_client.get_redis_client", _aret(fr))
    alerts = _patch_alerts(monkeypatch)
    _patch_jobstatus(monkeypatch)

    r1 = asyncio.run(wd.run_budget_watchdog(injected_total=17_500))
    assert r1["shed"] is True and r1["alert_fired"] is True
    assert fr.store.get(wd.SHED_KEY) == "1"
    # TTL clears at rollover: NX set with 0 < ex <= 86400
    shed_set = [c for c in fr.set_calls if c[0] == wd.SHED_KEY][0]
    _, _, nx, ex = shed_set
    assert nx is True and ex is not None and 0 < ex <= 86_400
    assert len(alerts) == 1

    # Second tick, same day: flag already set -> NX miss -> NO new alert.
    r2 = asyncio.run(wd.run_budget_watchdog(injected_total=17_800))
    assert r2["shed"] is True and r2["alert_fired"] is False
    assert len(alerts) == 1  # still exactly one


def test_no_shed_under_threshold(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr("database.redis_client.get_redis_client", _aret(fr))
    alerts = _patch_alerts(monkeypatch)
    _patch_jobstatus(monkeypatch)

    r = asyncio.run(wd.run_budget_watchdog(injected_total=16_000))
    assert r["shed"] is False and r["alert_fired"] is False
    assert wd.SHED_KEY not in fr.store
    assert alerts == []


def test_escalation_at_18k_fires_second_alert(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr("database.redis_client.get_redis_client", _aret(fr))
    alerts = _patch_alerts(monkeypatch)
    _patch_jobstatus(monkeypatch)

    r = asyncio.run(wd.run_budget_watchdog(injected_total=18_500))
    assert r["shed"] is True and r["escalated"] is True
    assert fr.store.get(wd.ESCALATE_KEY) == "1"
    # two distinct alerts: shed + escalation (human call)
    assert len(alerts) == 2
    assert any("ESCALATION" in title for title, _ in alerts)


def test_triton_poller_skips_when_shed(monkeypatch):
    fr = FakeRedis(strings={wd.SHED_KEY: "1"})
    monkeypatch.setattr("database.redis_client.get_redis_client", _aret(fr))
    assert asyncio.run(wd.is_triton_shed()) is True

    import jobs.triton_shadow_poller as tp
    reached = {"flow": False}

    async def boom(*a, **k):
        reached["flow"] = True
        return []

    monkeypatch.setattr("integrations.uw_api.get_flow_alerts", boom)
    # Should short-circuit at the top, before importing/calling get_flow_alerts.
    asyncio.run(tp.run_triton_shadow_poller())
    assert reached["flow"] is False


def test_daily_burn_snapshot_writes_rows(monkeypatch):
    d = "2026-07-08"
    fr = FakeRedis(
        hashes={f"uw:daily_requests_by_caller:{d}": {"ohlc_bars": "3600", "triton_flow_shadow": "440"}},
        strings={f"uw:daily_requests:{d}": "17200"},
    )
    monkeypatch.setattr("database.redis_client.get_redis_client", _aret(fr))

    executed = []

    class FakeConn:
        async def execute(self, sql, *args):
            executed.append((sql, args))

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConn()
        async def __aexit__(self, *a):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    monkeypatch.setattr("database.postgres_client.get_postgres_client", _aret(FakePool()))

    r = asyncio.run(wd.run_daily_burn_snapshot(target_date=date(2026, 7, 8)))
    assert r["grand_total"] == 17_200
    assert r["rows"] == 3  # 2 callers + _TOTAL
    inserts = [(sql, args) for sql, args in executed if "INSERT INTO uw_daily_burn" in sql]
    # per-caller rows + the grand-total row
    assert any(args[1] == "_TOTAL" and args[2] == 17_200 for _, args in inserts)
    assert any(args[1] == "ohlc_bars" and args[2] == 3600 for _, args in inserts)
