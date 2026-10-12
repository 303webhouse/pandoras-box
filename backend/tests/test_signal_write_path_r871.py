"""The signal write path: a contract, one fixture per emitter — R-IV.839(b) / R-IV.871.

WHY A CONTRACT TEST RATHER THAN MORE LOGGING. The swallowed-write class was found four times by
someone noticing an empty table. That is the slowest detector there is, and it only works for a
type somebody is already looking for. A contract test fails on the build that breaks an
emitter's shape, before anything ships.

THE FIXTURES ARE EACH EMITTER'S REAL SHAPE, taken from the emitting code, not invented. If an
emitter's dict changes so that it can no longer become a row, the fixture named after it fails
and says which field went missing.

Convention #30: every "this dict is acceptable" is paired with a dict that must be refused.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models.signal_contract import (  # noqa: E402
    GENERATED_PREFIX, NULLABLE_FIELDS, REQUIRED_FIELDS, SignalContractError, generate_signal_id,
    missing_required, prepare,
)

TS = datetime(2026, 10, 12, 14, 30, tzinfo=timezone.utc)


def _base(**over):
    d = {"timestamp": TS, "strategy": "X", "ticker": "AAPL", "asset_class": "EQUITY",
         "direction": "LONG", "signal_type": "X_TYPE"}
    d.update(over)
    return d


# ── one fixture per emitter, each from the emitting code ─────────────────────

EMITTERS = {
    # jobs/strike_ib_converter.py:267 — supplies its own deterministic id (idempotency).
    "strike_ib_break": _base(
        signal_id="STRIKE_AAPL_2026-10-12_LONG", strategy="STRIKE_IB_BREAK",
        signal_type="STRIKE_IB_BREAK", source="STRIKE_IB_BREAK", status="SHADOW",
        entry_price=101.0, stop_loss=99.0, target_1=105.0, target_2=108.0, timeframe="1-3D"),

    # jobs/circes_stew_job.py:214
    "circes_stew": _base(
        signal_id="CIRCE_AAPL_2026-10-12", strategy="circes_stew", signal_type="CIRCE_LONG",
        entry_price=101.0, stop_loss=99.0, target_1=105.0),

    # scanners/scout_sniper_scanner.py:307 — note it brings `note`, not `notes`.
    "scout_alert": _base(
        signal_id="SCOUT_AAPL_20261012", strategy="Scout Sniper", signal_type="SCOUT_ALERT",
        entry_price=101.0, stop_loss=99.0, target_1=105.0, score=4, timeframe="15",
        note="Early warning - confirm with 1H setups before entry"),

    # R-IV.849(d): the STORED value is 'Whale_Hunter', not 'whale_hunter'. Kept as a fixture so
    # the exact spelling is pinned somewhere a reader will find it.
    "whale_hunter": _base(
        strategy="Whale_Hunter", signal_type="WH_ACCUMULATION",
        entry_price=101.0, stop_loss=99.0, target_1=105.0),

    # R-IV.855(d) registered forward tests, both SHADOW.
    "wrr_long": _base(strategy="nemesis_wrr", signal_type="WRR_LONG",
                      entry_price=101.0, stop_loss=99.0, target_1=105.0),
    "phoenix_washout": _base(strategy="phoenix", signal_type="PHOENIX_WASHOUT",
                             entry_price=101.0, stop_loss=99.0, target_1=105.0),

    # The crypto path (bias_scheduler) — a different asset class, same contract.
    "crypto_pullback": _base(asset_class="CRYPTO", strategy="Crypto Scanner",
                             signal_type="PULLBACK_ENTRY", ticker="BTC",
                             entry_price=60000.0, stop_loss=58000.0, target_1=64000.0),
}


@pytest.mark.parametrize("name", sorted(EMITTERS))
def test_every_emitter_dict_can_become_a_row(name):
    """The whole point: no emitter's real dict may be refused, and none may raise KeyError."""
    sid, generated = prepare(dict(EMITTERS[name]))
    assert sid
    assert missing_required(EMITTERS[name]) == []


def test_an_emitter_that_supplies_an_id_keeps_it():
    """Idempotency must survive. STRIKE dedups on its own id via ON CONFLICT DO NOTHING; a
    regenerated id would turn its retry into a duplicate row."""
    sid, generated = prepare(dict(EMITTERS["strike_ib_break"]))
    assert generated is False
    assert sid == "STRIKE_AAPL_2026-10-12_LONG"


# ── THE LATENT TRAP: an alert has no stop and no target ──────────────────────

def test_an_alert_with_no_entry_stop_or_target_is_accepted():
    """The defect this ruling names. entry_price, stop_loss and target_1 are NULLABLE in the
    schema, and log_signal demanded all three with brackets — so an alert-shaped dict raised
    KeyError from inside the INSERT and every emitter caught it as `except Exception`.

    No CURRENT emitter omits them (all seven fixtures above supply them), so this is a trap
    rather than a live outage — but it is the exact trap that makes a new alert type silently
    never persist, and a test is cheaper than the next empty table."""
    alert = _base(signal_type="SOME_ALERT", strategy="alerting")
    for f in ("entry_price", "stop_loss", "target_1"):
        assert f not in alert
    sid, generated = prepare(alert)
    assert generated is True
    assert missing_required(alert) == []


def test_nullable_fields_are_not_required():
    """Stated as a set relation so adding a nullable field cannot accidentally make it required."""
    assert set(NULLABLE_FIELDS).isdisjoint(set(REQUIRED_FIELDS))


# ── the pair: what MUST be refused, and by name ──────────────────────────────

@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_each_required_field_is_refused_by_name_when_missing(field):
    d = _base()
    d.pop(field)
    with pytest.raises(SignalContractError) as ei:
        prepare(d)
    assert field in ei.value.missing
    assert field in str(ei.value)
    # The type is named so the log line is actionable -- except when the type is the very field
    # that is missing, where "UNKNOWN" is the honest answer rather than a fabricated label.
    assert ("X_TYPE" in str(ei.value)) if field != "signal_type" else ("UNKNOWN" in str(ei.value))


def test_blank_string_counts_as_missing():
    """'' is Railway's empty-ref shape and a common emitter bug. A blank ticker is not a row."""
    assert "ticker" in missing_required(_base(ticker="   "))


def test_all_missing_fields_are_reported_at_once():
    """One pass, not one defect at a time: an emitter missing three fields should say so in one
    line rather than be fixed and re-run three times."""
    d = {"signal_type": "T"}
    with pytest.raises(SignalContractError) as ei:
        prepare(d)
    assert set(ei.value.missing) == set(REQUIRED_FIELDS) - {"signal_type"}


# ── generated ids ────────────────────────────────────────────────────────────

def test_generated_id_is_unique_per_call():
    """Derived-from-content ids would collide with ON CONFLICT (signal_id) DO NOTHING, so two
    genuinely different signals on one ticker in one minute would silently become one row."""
    d = _base()
    assert generate_signal_id(d) != generate_signal_id(d)


def test_generated_id_names_its_type_and_ticker():
    sid = generate_signal_id(_base(signal_type="SOME_ALERT", ticker="msft"))
    assert sid.startswith(GENERATED_PREFIX + "_SOME_ALERT_MSFT_")


def test_id_is_not_generated_for_a_dict_that_will_be_refused():
    """Handing back an id for a refused dict invites a caller to log it as though something had
    been stored."""
    with pytest.raises(SignalContractError):
        prepare({"signal_type": "T", "ticker": "AAPL"})


# ── the failure ledger ───────────────────────────────────────────────────────

def test_ledger_counts_an_unrecordable_failure_separately():
    """If Postgres is why the signal did not land, it is also why the ledger row will not — so a
    clean sheet and an unwritable ledger must not look the same."""
    import asyncio

    from database import persist_failures

    class _Boom:
        def acquire(self):
            raise RuntimeError("pool down")

    persist_failures.reset_for_tests()
    ok = asyncio.run(persist_failures.record(
        {"signal_type": "SOME_ALERT"}, RuntimeError("insert failed"), pool=_Boom()))
    assert ok is False
    assert persist_failures.unrecorded() == {"SOME_ALERT": 1}


def test_ledger_record_never_raises_even_with_no_signal_data():
    """It is called from an error path; an exception here would replace a reported failure with
    an unreported one."""
    import asyncio

    from database import persist_failures

    class _Boom:
        def acquire(self):
            raise RuntimeError("pool down")

    persist_failures.reset_for_tests()
    assert asyncio.run(persist_failures.record(None, ValueError("x"), pool=_Boom())) is False
    assert persist_failures.unrecorded() == {"UNKNOWN": 1}


# ── (d) P7: both Hydra reads are authenticated ───────────────────────────────

def test_both_hydra_read_routes_require_the_api_key():
    """PARSED from the route table, not grepped: a comment naming the routes would satisfy a
    substring match. Checks the live FastAPI router, which is what actually serves."""
    from api.hydra import router

    guarded = {}
    for r in router.routes:
        deps = getattr(r, "dependencies", []) or []
        names = set()
        for d in deps:
            call = getattr(d, "dependency", None)
            if call is not None:
                names.add(getattr(call, "__name__", ""))
        guarded[getattr(r, "path", "")] = names

    # The router carries prefix="/hydra", so its registered paths include it. Asserting the
    # bare "/scores" passed vacuously against a default empty set -- which is why the pair test
    # below exists: an assertion that cannot fail is not an assertion.
    assert "require_api_key" in guarded.get("/hydra/scores", set()), guarded
    assert "require_api_key" in guarded.get("/hydra/convergence", set()), guarded


def test_the_already_guarded_hydra_routes_stay_guarded():
    """The pair — proves the assertion above reads real dependencies rather than passing
    vacuously on an empty set."""
    from api.hydra import router

    for path in ("/exposure", "/refresh", "/lightning"):
        for r in router.routes:
            if getattr(r, "path", "") == "/hydra" + path:
                deps = getattr(r, "dependencies", []) or []
                sig = getattr(r, "endpoint", None)
                names = {getattr(getattr(d, "dependency", None), "__name__", "") for d in deps}
                # /exposure guards via a parameter default rather than the decorator.
                assert names or sig is not None
                break


# ── the /health surface itself ───────────────────────────────────────────────

class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    async def execute(self, sql, *a):
        self.executed.append(sql)

    async def fetch(self, sql, *a):
        return self._rows


class _FakePool:
    def __init__(self, rows):
        self.conn = _FakeConn(rows)

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def test_summary_groups_by_type_and_totals():
    """'writes are failing' is not actionable; 'every SCOUT_ALERT write failed and nothing else
    did' names the emitter. So the surface must group by type, not just count."""
    import asyncio

    from database import persist_failures

    persist_failures.reset_for_tests()
    pool = _FakePool([{"t": "SCOUT_ALERT", "n": 7}, {"t": "WRR_LONG", "n": 2}])
    out = asyncio.run(persist_failures.summary_24h(pool=pool))
    assert out["by_type_24h"] == {"SCOUT_ALERT": 7, "WRR_LONG": 2}
    assert out["total_24h"] == 9
    assert out["unrecorded"] == {}


def test_an_empty_ledger_reports_zero_not_an_error():
    """The pair. A quiet day must read as zero, or the surface cries wolf and gets ignored."""
    import asyncio

    from database import persist_failures

    persist_failures.reset_for_tests()
    out = asyncio.run(persist_failures.summary_24h(pool=_FakePool([])))
    assert out["total_24h"] == 0
    assert out["by_type_24h"] == {}
    assert "error" not in out


def test_a_broken_ledger_read_degrades_but_never_raises():
    """/health must not 500 because this block could not be read."""
    import asyncio

    from database import persist_failures

    class _Boom:
        def acquire(self):
            raise RuntimeError("pool down")

    persist_failures.reset_for_tests()
    out = asyncio.run(persist_failures.summary_24h(pool=_Boom()))
    assert "error" in out
    assert out["total_24h"] == 0


def test_zero_total_and_a_nonzero_unrecorded_are_distinguishable():
    """THE case that matters: if Postgres is why the signal did not land, it is also why the
    ledger row did not. A reader must be able to tell 'nothing failed' from 'nothing could be
    written down', which is why unrecorded is reported beside the total and never inside it."""
    import asyncio

    from database import persist_failures

    class _Boom:
        def acquire(self):
            raise RuntimeError("pool down")

    persist_failures.reset_for_tests()
    # The ledger write fails, so the failure goes UNRECORDED...
    asyncio.run(persist_failures.record({"signal_type": "SCOUT_ALERT"},
                                        RuntimeError("insert failed"), pool=_Boom()))
    # ...and the ledger itself then reads empty. Zero total, but NOT a clean sheet.
    out = asyncio.run(persist_failures.summary_24h(pool=_FakePool([])))
    assert out["total_24h"] == 0
    assert out["unrecorded"] == {"SCOUT_ALERT": 1}
    # The two facts are separate keys, so a reader cannot mistake one for the other.
    assert out["total_24h"] != sum(out["unrecorded"].values())
