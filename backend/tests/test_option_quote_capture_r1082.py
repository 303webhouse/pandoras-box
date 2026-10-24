"""R-IV.1082(b) — the forward option bid/ask capture, and the four ways it could go quietly wrong.

Each group below pins a property whose failure would NOT show up as an error. The capture would
keep running, keep writing rows, and keep looking healthy while the data stopped meaning what it
claims:

  1. spending the FORBIDDEN caller tag -- the ruling names `option_contracts` as off limits, and
     the obvious reuse (`get_options_snapshot`) hard-codes exactly that tag
  2. serving a CACHED chain -- a quote fetched minutes earlier, stored stamped with this slot's
     time, is a fabricated observation and nothing downstream could detect it
  3. shedding the CLOSE instead of the far expiry -- the loss that cannot be made good
  4. capturing AFTER THE CLOSE under a slot's name -- wide, stale spreads wearing a 15:30 label
"""
from __future__ import annotations

import ast
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from jobs import option_quote_capture as oqc
from tests._srcscan import code_of, code_of_file, function_code

ET = ZoneInfo("America/New_York")
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOB_FILE = os.path.join(BACKEND, "jobs", "option_quote_capture.py")


@pytest.fixture(autouse=True)
def _clean():
    oqc.reset_for_tests()
    yield
    oqc.reset_for_tests()


# ── 1. the forbidden tag, and the cache ─────────────────────────────────────

def test_it_does_not_spend_the_forbidden_option_contracts_tag():
    """R-IV.1082(b) verbatim: do not touch option_contracts. Scanned on PARSED code so the
    docstring that EXPLAINS why it is forbidden cannot satisfy the check -- that exact
    confusion has bitten this suite repeatedly."""
    code = code_of_file(JOB_FILE)
    assert "option_contracts" not in code, (
        "the capture job references option_contracts in executable code; every call would be "
        "charged to DAEDALUS's tag, which R-IV.1082(b) forbids")


def test_it_does_not_use_the_CACHED_chain_helper():
    """`get_options_snapshot` reads and writes a shared response cache. A cache hit would be
    stored under THIS slot's timestamp -- a stale quote wearing a fresh one. For a job whose
    product is "the spread at 11:30", that is fabrication, not an optimisation."""
    code = code_of_file(JOB_FILE)
    assert "get_options_snapshot" not in code
    for cache_fn in ("cache_get", "cache_set"):
        assert cache_fn not in code, cache_fn


def test_the_fetch_passes_its_OWN_tag():
    code = function_code(JOB_FILE, "fetch_expiry")
    assert "CALLER_TAG" in code and "caller=" in code
    assert oqc.CALLER_TAG == "option_quote_capture"


def test_the_expiry_filter_is_native_so_the_500_cap_cannot_bind():
    """`expiry` is a native UW parameter; the strike range is not. Filtering per expiry at the
    vendor is what keeps a response far below the 500 cap -- and the cap is still RECORDED,
    because a censored chain is indistinguishable from a thin one."""
    code = function_code(JOB_FILE, "fetch_expiry")
    assert '"expiry"' in code or "'expiry'" in code
    assert oqc.UW_CONTRACT_CAP == 500


# ── 2. the slot grid ────────────────────────────────────────────────────────

def test_thirteen_slots_the_thirty_minute_grid_PLUS_the_1559_close():
    """SUPERSEDED R-IV.1082(b)'s twelve (R-IV.1398(b)1 adds the 15:59 close).

    The old form asserted `len == 12` and a single 1800-second gap, which was the right shape
    for a uniform grid and is the wrong shape now. What still has to hold is that the
    thirty-minute grid is INTACT and the close is appended to it -- not that a 15:59 slot
    exists somewhere, which an edit that replaced 15:30 would also satisfy.
    """
    assert len(oqc.SLOT_TIMES_ET) == 13
    assert oqc.SLOT_TIMES_ET[0] == time(10, 0)
    assert oqc.SLOT_TIMES_ET[-1] == time(15, 59)
    assert oqc.SLOT_TIMES_ET[-2] == time(15, 30), "the 15:30 slot was REPLACED, not kept"
    grid = oqc.SLOT_TIMES_ET[:-1]
    gaps = {(datetime.combine(date(2026, 1, 1), b) -
             datetime.combine(date(2026, 1, 1), a)).total_seconds()
            for a, b in zip(grid, grid[1:])}
    assert gaps == {1800.0}, "the 30-minute grid under the close is no longer uniform"


@pytest.mark.parametrize("hh,mm,expect", [
    (9, 59, None),        # before the first slot
    (10, 0, "10:00"),
    (10, 25, "10:00"),    # inside the grace
    (10, 26, None),       # past the grace, before the next slot
    (10, 30, "10:30"),
    (15, 30, "15:30"),
    (15, 54, "15:30"),
    (16, 30, None),       # POST-CLOSE
    (20, 0, None),        # hours after
])
def test_due_slot(hh, mm, expect):
    got = oqc.due_slot(datetime(2026, 10, 16, hh, mm, tzinfo=ET))
    assert (got.strftime("%H:%M") if got else None) == expect


def test_a_post_close_restart_cannot_capture_the_1530_slot():
    """THE FABRICATION GUARD. Without the bounded grace the 15:30 slot stays "due" all evening,
    so a restart at 18:00 would store post-close spreads -- wide, untradeable -- as the 15:30
    snapshot, and no later reader could tell."""
    for hh in (16, 17, 18, 20, 23):
        assert oqc.due_slot(datetime(2026, 10, 16, hh, 5, tzinfo=ET)) is None, hh


def test_no_slot_on_a_weekend():
    assert oqc.due_slot(datetime(2026, 10, 17, 11, 0, tzinfo=ET)) is None   # Saturday
    assert oqc.due_slot(datetime(2026, 10, 18, 11, 0, tzinfo=ET)) is None   # Sunday


# ── 3. the budget: the close is never shed ──────────────────────────────────

def test_the_per_slot_allowance_reserves_a_share_for_every_later_slot():
    """The guarantee, stated as arithmetic: a greedy early slot cannot consume the close's
    budget, because the allowance is always `remaining // slots_remaining`."""
    assert oqc.slot_allowance(0, 12) == 24
    assert oqc.slot_allowance(oqc.SESSION_CALL_CEILING - 24, 1) == 24
    assert oqc.slot_allowance(oqc.SESSION_CALL_CEILING, 1) == 0


def test_walking_a_whole_session_never_exceeds_the_ceiling_and_the_last_slot_still_runs():
    """POSITIVE CONTROL (Convention #30). Simulate twelve slots each spending its full
    allowance; the last slot must still get a positive allowance and the total must not pass
    the ceiling."""
    # Driven by the SLOT LIST, not by a literal 12. The literal was correct when it was
    # written and silently stopped simulating a whole session the moment a slot was added --
    # the walk would have passed while never reaching the real last slot.
    n = len(oqc.SLOT_TIMES_ET)
    used = 0
    per_slot = []
    for i in range(n):
        a = oqc.slot_allowance(used, n - i)
        per_slot.append(a)
        used += a
    assert used <= oqc.SESSION_CALL_CEILING, used
    assert per_slot[-1] > 0, "the final slot was starved: %r" % per_slot
    assert min(per_slot) > 0, per_slot


def test_the_ceiling_sits_under_the_granted_quota():
    from integrations.uw_governor import quota_for
    granted, _tier = quota_for(oqc.CALLER_TAG)
    assert granted == 300
    assert oqc.SESSION_CALL_CEILING <= granted


def test_pairs_are_ordered_so_the_FARTHEST_expiry_is_shed_first():
    """The shed order IS the design. Dropping the 3-DTE quote costs a row that returns
    tomorrow at 2 DTE; dropping the 15:30 quote costs it permanently."""
    pairs = oqc.plan_pairs(date(2026, 10, 20))        # a Tuesday
    dtes = [dte for _t, _e, dte in pairs]
    assert dtes == sorted(dtes), "pairs must be ordered nearest-expiry-first"
    assert dtes[0] == 0 and dtes[-1] == max(dtes)
    # the tail that an allowance cut would remove is the farthest expiry
    assert dtes[-1] > dtes[0]


def test_candidate_expiries_skip_weekends():
    """Nothing expires on a Saturday, so probing one would waste a call on a certainty."""
    for d, _k in oqc.candidate_expiries(date(2026, 10, 15)):
        assert d.weekday() < 5, d
    assert len(oqc.candidate_expiries(date(2026, 10, 22))) == 2   # Thu -> Thu, Fri


def test_an_expiry_known_absent_is_not_probed_again_this_session():
    """Probed once a day, not twelve times. Without this the non-existent Monday expiries for
    the single names would burn 12 calls each, every day, to re-learn the same nothing."""
    session = date(2026, 10, 20)
    before = len(oqc.plan_pairs(session))
    t, e, _d = oqc.plan_pairs(session)[-1]
    oqc._expiry_known[(t, e.isoformat())] = False
    assert len(oqc.plan_pairs(session)) == before - 1


# ── 4. the ATM centre, and that its weakness is recorded ────────────────────

def _c(typ, strike, bid=None, ask=None, delta=None):
    return {"type": typ, "strike": strike, "bid": bid, "ask": ask, "delta": delta,
            "iv": None, "volume": 0, "open_interest": 0}


def test_atm_prefers_delta_nearest_half():
    chain = [_c("call", 100, delta=0.80), _c("call", 110, delta=0.51),
             _c("call", 120, delta=0.20)]
    strike, method = oqc.atm_strike(chain)
    assert (strike, method) == (110, oqc.ATM_FROM_DELTA)


def test_atm_falls_back_to_parity_when_delta_is_missing():
    """UW does not always serve greeks. Parity -- the strike where call and put mids are
    closest -- is the next best centre and needs no extra call."""
    chain = [_c("call", 100, 11.0, 11.2), _c("put", 100, 1.0, 1.2),
             _c("call", 110, 5.0, 5.2), _c("put", 110, 5.1, 5.3)]
    strike, method = oqc.atm_strike(chain)
    assert (strike, method) == (110, oqc.ATM_FROM_PARITY)


def test_atm_falls_back_to_median_and_SAYS_SO():
    """The weak route. It must still return a centre -- a slot with no centre is a lost slot --
    but the row has to carry the fact, or a reader weights a median-centred window the same as
    a delta-centred one."""
    chain = [_c("call", 90), _c("call", 100), _c("call", 110)]
    strike, method = oqc.atm_strike(chain)
    assert method == oqc.ATM_FROM_MEDIAN
    assert strike == 100


def test_a_far_off_delta_is_NOT_trusted_as_atm():
    """A chain whose nearest delta to 0.50 is 0.05 is not telling you where ATM is; taking it
    anyway would centre the window at the far wing and the +/-5 strikes would miss the money."""
    chain = [_c("call", 500, 0.1, 0.2, delta=0.05), _c("put", 500, 50.0, 50.2)]
    _strike, method = oqc.atm_strike(chain)
    assert method != oqc.ATM_FROM_DELTA


def test_the_method_is_stored_on_every_row():
    code = function_code(JOB_FILE, "_store")
    assert "atm_method" in code and "atm_strike" in code


# ── 5. the +/-5 window ──────────────────────────────────────────────────────

def test_window_is_five_strikes_each_side_both_types():
    chain = []
    for s in range(90, 131, 5):            # 9 strikes
        chain.append(_c("call", s, delta=0.9 - (s - 90) / 50.0))
        chain.append(_c("put", s))
    rows, centre, _m = oqc.select_window(chain, window=2)
    strikes = sorted({r["strike"] for r in rows})
    assert centre in strikes
    assert len(strikes) == 5                                  # centre +/- 2
    assert {r["type"] for r in rows} == {"call", "put"}        # BOTH types kept


def test_window_counts_strikes_not_dollars():
    """TSLA's strike spacing is not SPY's. Counting strikes adapts to each ticker without a
    per-ticker spacing table -- a dollar window would be 5 strikes on one and 50 on another."""
    wide = [_c("call", s, delta=0.5 if s == 500 else 0.9) for s in (400, 450, 500, 550, 600)]
    wide += [_c("put", s) for s in (400, 450, 500, 550, 600)]
    rows, centre, _m = oqc.select_window(wide, window=1)
    assert centre == 500
    assert sorted({r["strike"] for r in rows}) == [450, 500, 550]


def test_the_configured_window_is_five():
    assert oqc.STRIKE_WINDOW == 5


# ── 6. a crossed or missing quote is not a number ───────────────────────────

def test_mid_refuses_a_crossed_quote():
    """ask < bid is not a tradeable market; averaging it produces a confident price for
    something that never existed."""
    assert oqc._mid(1.0, 2.0) == 1.5
    assert oqc._mid(2.0, 1.0) is None
    assert oqc._mid(None, 2.0) is None
    assert oqc._mid(1.0, None) is None


# ── 7. the job never raises, and distinguishes its failure modes ────────────

@pytest.mark.asyncio
async def test_capture_slot_survives_a_dead_db_and_says_nothing_was_stored():
    async def boom():
        raise RuntimeError("no pool")
    import database.postgres_client as pg
    real = pg.get_postgres_client
    pg.get_postgres_client = boom
    try:
        async def no_chain(ticker, expiry):
            return None, 0
        real_fetch = oqc.fetch_expiry
        oqc.fetch_expiry = no_chain
        try:
            out = await oqc.capture_slot(
                now=datetime(2026, 10, 16, 14, 0, tzinfo=ET).astimezone(
                    __import__("datetime").timezone.utc))
        finally:
            oqc.fetch_expiry = real_fetch
    finally:
        pg.get_postgres_client = real
    assert out["rows"] == 0
    assert out["captured"] == 0


@pytest.mark.asyncio
async def test_shed_and_unavailable_are_counted_SEPARATELY():
    """One is this job's own budgeting, the other is something going wrong. A single "missing"
    count would make a deliberate shed and a vendor outage look identical on /health."""
    # Checked on the RETURNED SUMMARY, not on the source: `ast.unparse` normalises string
    # quotes, so a scan for '"shed"' fails on code that is perfectly correct. The keys are
    # observable, so observe them.
    calls = {"n": 0}

    async def one_then_nothing(ticker, expiry):
        calls["n"] += 1
        return None, 0                       # a call that returned nothing: UNAVAILABLE

    real_fetch = oqc.fetch_expiry
    oqc.fetch_expiry = one_then_nothing
    try:
        out = await oqc.capture_slot(
            now=datetime(2026, 10, 20, 10, 0, tzinfo=ET).astimezone(
                __import__("datetime").timezone.utc))      # Tuesday 10:00 -> slot due
    finally:
        oqc.fetch_expiry = real_fetch

    assert "shed" in out and "unavailable" in out
    # 32 pairs planned on a Tuesday. The allowance is the ceiling over the SLOT COUNT, and
    # that is the one figure R-IV.1398(b)1's 15:59 slot moved: 288 // 12 = 24 became
    # 288 // 13 = 22, so the first slot now attempts 22 and sheds 10 rather than attempting
    # 24 and shedding 8. Derived here, because a literal would have to be edited by whoever
    # adds the next slot and silently passes if they do not.
    expected_allowance = oqc.SESSION_CALL_CEILING // len(oqc.SLOT_TIMES_ET)
    assert out["planned"] == 32
    assert out["allowance"] == expected_allowance == 22
    assert out["unavailable"] == expected_allowance
    assert out["shed"] == out["planned"] - expected_allowance == 10
    assert out["captured"] == 0
    assert calls["n"] == expected_allowance, "the allowance must cap the calls actually made"


def test_status_reports_missed_slots_not_just_the_last_one():
    """"the last slot worked" and "every slot worked" are different claims, and only the second
    means the intraday series is usable."""
    code = function_code(JOB_FILE, "capture_status")
    assert "slots_missed" in code
    assert "slots_expected_so_far" in code


# ── 8. the governor: budget-neutral, and nothing protected was touched ──────

def test_the_carve_is_budget_neutral():
    from integrations.uw_governor import (
        QUOTAS, DAILY_BUDGET, QUOTA_SAFETY_BUFFER)
    # R-IV.1265(d) MOVED THE TOTAL: `notables_strip` (50) was funded by cutting the
    # safety buffer 2,000 -> 1,950, so the table now sums to 26,050. The literal 26,000
    # was hard-coded in FIVE separate test files, each written by a different carve to
    # say "this sum must not move" -- so the first ruled move broke all five at once.
    # The INVARIANT was never the literal; it is that the table fills the budget minus
    # the buffer exactly. Asserted that way now, so the next ruled change to either
    # number does not require editing five files that were never about the number.
    total = sum(q for q, _t in QUOTAS.values())
    assert total == DAILY_BUDGET - QUOTA_SAFETY_BUFFER


def test_the_new_tag_was_funded_from_flow_per_expiry():
    from integrations.uw_governor import quota_for
    assert quota_for("option_quote_capture")[0] == 300
    assert quota_for("flow_per_expiry")[0] == 1700      # was 2000


@pytest.mark.parametrize("tag,expected", [
    ("option_contracts", 2100),
    ("darkpool_collector", 250),
    ("triton_flow_shadow", 450),
])
def test_the_protected_tags_are_UNCHANGED(tag, expected):
    """R-IV.1082(b): do not touch the reserve, darkpool_collector, triton_flow_shadow or
    option_contracts. R-IV.1071(c) put the middle two at their ceilings by ruling."""
    from integrations.uw_governor import quota_for
    assert quota_for(tag)[0] == expected


def test_the_reserve_was_not_touched():
    """R-IV.1082(b) funded this capture budget-neutrally out of `flow_per_expiry`, NOT out of
    the foreign reserve. That claim is unchanged and is what this asserts.

    The `== 5165` it used to carry was INCIDENTAL to that claim and broke on an unrelated
    ruling: R-IV.1408(b)1 added `darkpool_forward` at 250 to the reserve, making it 5,415. A
    test that fails when a different ruling spends a different pot was measuring the pot, not
    the claim.
    """
    from integrations.uw_api_cache import UW_FOREIGN_RESERVE
    from integrations.uw_governor import FOREIGN_RESERVE_QUOTAS
    assert "option_quote_capture" not in FOREIGN_RESERVE_QUOTAS, (
        "this capture is funded from the hub table, not the reserve")
    # The reserve must still fit inside itself, whoever has drawn on it since.
    assert sum(q for q, _t in FOREIGN_RESERVE_QUOTAS.values()) <= UW_FOREIGN_RESERVE


def test_it_gets_NO_off_hours_exemption():
    """Its window is 10:00-15:30 ET, entirely RTH, so the STANDARD off-hours haircut never
    applies to it. An exemption would be a licence it has no use for -- and every existing
    entry in that table earned its place by a measured block."""
    from integrations.uw_governor import OFF_HOURS_FACTOR_BY_CALLER
    assert "option_quote_capture" not in OFF_HOURS_FACTOR_BY_CALLER


# ── 9. first boot (R-IV.1052(b)) ────────────────────────────────────────────

def test_the_table_is_created_at_startup():
    """A forward collector that waits on a writer to create its table loses its first session,
    and under the collector law that session never comes back."""
    import re
    from tests.test_first_boot_reads_r1052 import STARTUP_FILES
    startup = ""
    for f in STARTUP_FILES:
        with open(os.path.join(BACKEND, f), encoding="utf-8-sig") as fh:
            startup += fh.read() + chr(10)
    created = {t.lower() for t in re.findall(
        r"CREATE TABLE IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", startup, re.I)}
    assert "option_quote_capture" in created


def test_the_slot_is_part_of_the_row_identity():
    """The same contract is captured twelve times a session. If `slot_et` were not in the
    uniqueness key, each capture would overwrite the last and the intraday series -- the entire
    point of the job -- would collapse to one row a day."""
    import re
    with open(os.path.join(BACKEND, "database", "postgres_client.py"),
              encoding="utf-8-sig") as fh:
        src = fh.read()
    i = src.index("CREATE TABLE IF NOT EXISTS option_quote_capture")
    ddl = src[i:i + 2200]
    m = re.search(r"UNIQUE \(([^)]*)\)", ddl)
    assert m, ddl[:400]
    key = [c.strip() for c in m.group(1).split(",")]
    assert "slot_et" in key, key
    assert "session_date" in key and "ticker" in key and "strike" in key


# ── 10. the health surface must not go quiet after the close ────────────────

@pytest.mark.asyncio
async def test_slots_missed_is_still_populated_AFTER_the_close():
    """THE REGRESSION THIS NAMES. `expected` was first derived from `due_slot`, which returns
    None once the last slot's grace expires -- so from 15:55 ET until midnight the surface
    reported `slots_missed: []` however many slots had been lost. A totally failed session read
    as a clean one, at exactly the hour someone would check.

    Expectation is not capturability: a slot is expected once its time has passed.
    """
    import jobs.option_quote_capture as m
    real = m.datetime

    class _FrozenAfterClose(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 10, 16, 20, 30, tzinfo=__import__("datetime").timezone.utc)

    m.datetime = _FrozenAfterClose
    try:
        m.reset_for_tests()
        st = await m.capture_status()
    finally:
        m.datetime = real

    # THIRTEEN since R-IV.1398(b)1: the frozen instant is 16:30 ET, past every slot
    # including the 15:59 close. Derived from the slot list as well as asserted as a number,
    # so a future slot change fails on the COUNT rather than on an opaque off-by-one.
    assert st["slots_expected_so_far"] == len(oqc.SLOT_TIMES_ET) == 13, st
    assert len(st["slots_missed"]) == 13, st["slots_missed"]
    assert "15:30" in st["slots_missed"]
    assert "15:59" in st["slots_missed"], "the close is not counted as expected"


@pytest.mark.asyncio
async def test_nothing_is_expected_on_a_weekend():
    """The counterpart control: a quiet Saturday must NOT read as twelve missed slots, or the
    surface cries every weekend and stops being read."""
    import jobs.option_quote_capture as m
    real = m.datetime

    class _FrozenSaturday(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 10, 17, 20, 30, tzinfo=__import__("datetime").timezone.utc)

    m.datetime = _FrozenSaturday
    try:
        m.reset_for_tests()
        st = await m.capture_status()
    finally:
        m.datetime = real

    assert st["slots_expected_so_far"] == 0
    assert st["slots_missed"] == []


# ── 11. coverage survives a restart ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_slots_already_STORED_are_not_reported_missed_after_a_restart():
    """THE MIRROR OF THE POST-CLOSE BUG, found on the live surface minutes after deploying.

    `_slots_done` is in-memory and Railway restarts on every deploy. A deploy at 13:00 empties
    it, so a surface built on it alone would report the morning's slots as MISSED while their
    rows sit in the table. One fault hid real misses; this one would invent them -- and a
    surface that cries after every deploy stops being read, which costs the real alarm.
    """
    import jobs.option_quote_capture as m

    class _Conn:
        async def fetch(self, *a, **k):
            return [{"slot_et": "10:00"}, {"slot_et": "10:30"}, {"slot_et": "11:00"}]

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self): return _Acq()

    async def pool():
        return _Pool()

    import database.postgres_client as pg
    real_pool, real_dt = pg.get_postgres_client, m.datetime

    class _At1145(real_dt):
        @classmethod
        def now(cls, tz=None):
            return real_dt(2026, 10, 16, 15, 45, tzinfo=__import__("datetime").timezone.utc)

    pg.get_postgres_client = pool
    m.datetime = _At1145
    try:
        m.reset_for_tests()          # the restart: nothing in memory
        st = await m.capture_status()
    finally:
        pg.get_postgres_client, m.datetime = real_pool, real_dt

    assert st["coverage_source"] == "stored_rows"
    assert set(st["slots_captured"]) == {"10:00", "10:30", "11:00"}
    assert "10:00" not in st["slots_missed"]
    assert "11:30" in st["slots_missed"], "a genuinely missed slot must still be reported"


@pytest.mark.asyncio
async def test_an_unreadable_db_is_NAMED_not_silently_treated_as_no_coverage():
    """"no slot was captured" and "I could not ask" are different claims, and only the first is
    a fault in the capture. Collapsing them would make every DB blip look like a lost session."""
    import jobs.option_quote_capture as m
    import database.postgres_client as pg

    async def boom():
        raise RuntimeError("down")

    real = pg.get_postgres_client
    pg.get_postgres_client = boom
    try:
        m.reset_for_tests()
        st = await m.capture_status()
    finally:
        pg.get_postgres_client = real

    assert st["coverage_source"].startswith("memory")
    assert "db unreadable" in st["coverage_source"]
