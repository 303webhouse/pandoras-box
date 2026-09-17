"""R-IV.379(c) — the governor governs the ACCOUNT, and gates outside RTH.

The load-bearing tests are the FAIL-OPEN ones. This gate sits at the single
chokepoint every UW call passes through: if it can block on its own ignorance —
no header yet, Redis down, calendar unreadable — then the instrument built to
prevent an outage becomes one. That is the failure this register keeps finding,
and it would be especially poor here.
"""

import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations import uw_governor as g

ET = ZoneInfo("America/New_York")
RTH = datetime(2026, 9, 14, 11, 0, tzinfo=ET)        # Monday, mid-session
AFTER = datetime(2026, 9, 14, 22, 0, tzinfo=ET)      # Monday night
WEEKEND = datetime(2026, 9, 13, 11, 0, tzinfo=ET)    # Sunday
HOLIDAY = datetime(2026, 9, 7, 11, 0, tzinfo=ET)     # Labor Day


# ---------------------------------------------------------------- RTH gate

def test_rth_is_rth():
    assert g._is_rth(RTH) is True


@pytest.mark.parametrize("when,label", [(AFTER, "after hours"), (WEEKEND, "sunday"),
                                        (HOLIDAY, "labor day")])
def test_non_rth_is_not_rth(when, label):
    assert g._is_rth(when) is False, label


def test_holiday_uses_the_one_calendar_not_a_weekday_test():
    """Labor Day 2026-09-07 is a Monday. A weekday test would call it RTH."""
    assert HOLIDAY.weekday() < 5
    assert g._is_rth(HOLIDAY) is False


def test_background_quota_goes_to_zero_outside_rth():
    q_rth, tier = g.effective_quota("ohlc_sector", RTH)
    q_off, _ = g.effective_quota("ohlc_sector", AFTER)
    assert tier == g.TIER_BACKGROUND
    assert q_rth > 0 and q_off == 0


def test_foreground_is_never_gated_by_the_clock():
    q_rth, tier = g.effective_quota("snapshot", RTH)
    q_off, _ = g.effective_quota("snapshot", AFTER)
    assert tier == g.TIER_FOREGROUND
    assert q_off == q_rth, "a live read was throttled for being out of hours"


def test_standard_is_reduced_not_eliminated():
    q_rth, _ = g.effective_quota("ohlc_bars", RTH)
    q_off, _ = g.effective_quota("ohlc_bars", AFTER)
    assert 0 < q_off < q_rth


def test_calendar_failure_fails_open(monkeypatch):
    """Gating a live caller on a calendar error turns a data problem into an outage."""
    import stable_engine.market_calendar as mc

    def boom(d):
        raise RuntimeError("calendar exhausted")

    monkeypatch.setattr(mc, "is_trading_day", boom, raising=False)
    assert g._is_rth(AFTER) is True, "an unreadable calendar blocked traffic"


# ------------------------------------------------- account shedding, by tier

@pytest.fixture
def account(monkeypatch):
    # R-IV.441(c): a shed decision needs a FRESH reading, so the fixture carries the timestamp
    # every real reading carries. Age is exercised separately below.
    state = {"used": 0, "limit": 40000}

    async def fake():
        from datetime import datetime as _d, timezone as _tz
        return dict(state, at=state.get("at") or _d.now(_tz.utc).isoformat())

    import integrations.uw_api as uw
    monkeypatch.setattr(uw, "account_quota", fake, raising=False)
    return state


@pytest.mark.asyncio
async def test_no_shed_on_an_empty_account(account):
    account["used"] = 1000
    for tier in (g.TIER_BACKGROUND, g.TIER_STANDARD, g.TIER_FOREGROUND):
        assert await g.account_shed(tier) is None


@pytest.mark.asyncio
async def test_tiers_shed_in_order_as_the_account_fills(account):
    account["used"] = int(0.60 * 40000)          # 60%
    assert await g.account_shed(g.TIER_BACKGROUND) is not None
    assert await g.account_shed(g.TIER_STANDARD) is None
    assert await g.account_shed(g.TIER_FOREGROUND) is None

    account["used"] = int(0.80 * 40000)          # 80%
    assert await g.account_shed(g.TIER_STANDARD) is not None
    assert await g.account_shed(g.TIER_FOREGROUND) is None

    account["used"] = int(0.95 * 40000)          # 95%
    assert await g.account_shed(g.TIER_FOREGROUND) is not None


@pytest.mark.asyncio
async def test_foreground_survives_the_2026_09_11_shape(account):
    """23,417 of 40,000 spent by a client we do not control = 59%. The decision
    callers must still work; the heatmap must not."""
    account["used"] = 23417
    assert await g.account_shed(g.TIER_FOREGROUND) is None
    assert await g.account_shed(g.TIER_BACKGROUND) is not None


@pytest.mark.asyncio
async def test_shed_reason_names_the_numbers(account):
    account["used"] = 30000
    r = await g.account_shed(g.TIER_BACKGROUND)
    assert "30000" in r and "40000" in r


# ----------------------------------------------------- fail-open on unknowns

@pytest.mark.asyncio
async def test_no_header_yet_does_not_block(account):
    account.clear()
    account.update({"note": "no UW quota header seen yet this process"})
    assert await g.account_shed(g.TIER_BACKGROUND) is None


@pytest.mark.asyncio
async def test_missing_limit_does_not_block(account):
    account.clear()
    account.update({"used": 39000})
    assert await g.account_shed(g.TIER_BACKGROUND) is None, "blocked without a denominator"


@pytest.mark.asyncio
async def test_zero_limit_does_not_divide_or_block(account):
    account.clear()
    account.update({"used": 100, "limit": 0})
    assert await g.account_shed(g.TIER_BACKGROUND) is None


@pytest.mark.asyncio
async def test_account_read_raising_does_not_block(monkeypatch):
    async def boom():
        raise RuntimeError("redis down")

    import integrations.uw_api as uw
    monkeypatch.setattr(uw, "account_quota", boom, raising=False)
    assert await g.account_shed(g.TIER_FOREGROUND) is None


# ------------------------------------------------------------- the constants

def test_reserve_covers_the_typical_and_the_gate_covers_the_tail():
    """The reserve is sized to the TYPICAL foreign spend (~8,200 projected
    2026-09-14), not the worst case (23,417 on 09-11) — because a static reserve
    at the worst case leaves the hub 16,583 against its own measured demand of
    21,275, starving it every day to insure against one.

    The worst case is covered by account_shed() instead, which reads the vendor's
    counter and sheds tiers whoever filled the account. Two mechanisms, each
    doing what it is good at; neither has to be worst-case alone."""
    from integrations.uw_api_cache import (
        UW_ACCOUNT_LIMIT, UW_FOREIGN_RESERVE, DAILY_BUDGET)
    assert UW_ACCOUNT_LIMIT == 40000
    assert UW_FOREIGN_RESERVE >= 8246, "reserve below the measured typical"
    assert UW_FOREIGN_RESERVE < 23417, (
        "reserve at the worst case — that is the dynamic gate's job, and this "
        "would starve the hub every normal day")
    assert DAILY_BUDGET == UW_ACCOUNT_LIMIT - UW_FOREIGN_RESERVE


def test_hub_quota_table_fits_inside_the_hub_budget():
    """Asserted, not commented. The previous table carried an arithmetic comment
    that survived two edits to the numbers it described."""
    from integrations.uw_api_cache import DAILY_BUDGET
    target = DAILY_BUDGET - g.QUOTA_SAFETY_BUFFER
    total = sum(q for q, _ in g.QUOTAS.values())
    assert total <= target, (
        "quota table sums to %d, above the buffered hub budget %d — sized to "
        "overrun the account by design" % (total, target))


def test_every_measured_caller_has_an_explicit_entry():
    """`outcome_resolver` was the largest hub caller on 2026-09-14 and was not in
    the table at all, running on the 500 default meant for unknown code paths."""
    for caller in ("outcome_resolver", "ohlc_quote", "flow_per_expiry",
                   "ohlc_sector", "technical_indicator", "ohlc_bars"):
        assert caller in g.QUOTAS, "%s has no explicit quota" % caller


def test_measured_monday_demand_does_not_trip_the_table():
    """The retune exists because the old table blocked three live callers on
    sight, one of them FOREGROUND."""
    measured = {"outcome_resolver": 2764, "ohlc_quote": 1439, "technical_indicator": 1419,
                "ohlc_sector": 1417, "flow_per_expiry": 1140, "ohlc_bars": 1109,
                "option_contracts": 1052, "snapshot": 445}
    for caller, used in measured.items():
        quota, _ = g.quota_for(caller)
        assert used < quota, "%s would block at its measured %d (quota %d)" % (
            caller, used, quota)


def test_shed_thresholds_are_ordered():
    assert (g.ACCOUNT_SHED_AT[g.TIER_BACKGROUND]
            < g.ACCOUNT_SHED_AT[g.TIER_STANDARD]
            < g.ACCOUNT_SHED_AT[g.TIER_FOREGROUND] <= 1.0)


# --------------------------------------------------------------------------
# R-IV.380(a) — fail-open must not fail SILENTLY
#
# "the governor is not shedding" and "the governor cannot see the account" are
# the same observation from outside unless the gate publishes its own condition.
# That is the absent-vs-neutral collapse this register has filed four times.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_state_armed_when_the_account_is_readable(account):
    account["used"] = 1000
    await g.account_shed(g.TIER_BACKGROUND)
    assert g.gate_state()["state"] == "armed"


@pytest.mark.asyncio
async def test_gate_state_says_shedding_with_its_numbers(account):
    account["used"] = 30000
    await g.account_shed(g.TIER_BACKGROUND)
    st = g.gate_state()
    assert st["state"] == "shedding"
    assert "30000" in st["detail"]


@pytest.mark.asyncio
async def test_gate_state_distinguishes_no_header_from_armed(account):
    account.clear()
    account.update({"note": "nothing yet"})
    await g.account_shed(g.TIER_BACKGROUND)
    st = g.gate_state()
    assert st["state"] == "open:no_header"
    assert st["state"] != "armed", "an unseeing gate reported as an armed one"


@pytest.mark.asyncio
async def test_gate_state_distinguishes_missing_limit(account):
    account.clear()
    account.update({"used": 39000})
    await g.account_shed(g.TIER_BACKGROUND)
    assert g.gate_state()["state"] == "open:no_limit"


@pytest.mark.asyncio
async def test_gate_state_records_a_read_error(monkeypatch):
    async def boom():
        raise RuntimeError("redis down")

    import integrations.uw_api as uw
    monkeypatch.setattr(uw, "account_quota", boom, raising=False)
    await g.account_shed(g.TIER_FOREGROUND)
    st = g.gate_state()
    assert st["state"] == "open:read_error"
    assert "RuntimeError" in st["detail"]


@pytest.mark.asyncio
async def test_every_open_path_is_distinguishable(account, monkeypatch):
    """Three different ways to fail open, three different states. If any two
    collapsed, a reader could not tell which instrument was blind."""
    seen = set()
    account.clear(); account.update({"note": "x"})
    await g.account_shed(g.TIER_BACKGROUND); seen.add(g.gate_state()["state"])
    account.clear(); account.update({"used": 1})
    await g.account_shed(g.TIER_BACKGROUND); seen.add(g.gate_state()["state"])

    async def boom():
        raise RuntimeError("x")

    import integrations.uw_api as uw
    monkeypatch.setattr(uw, "account_quota", boom, raising=False)
    await g.account_shed(g.TIER_BACKGROUND); seen.add(g.gate_state()["state"])
    assert len(seen) == 3, "open states collapsed: %s" % seen


@pytest.mark.asyncio
async def test_gate_state_timestamps_itself(account):
    account["used"] = 100
    await g.account_shed(g.TIER_BACKGROUND)
    assert g.gate_state()["at"] is not None


# ── R-IV.441(c): a shed decision needs a FRESH reading ─────────────────────────

def test_reading_age_is_measured_or_unknown_never_invented():
    from datetime import datetime, timezone
    now = datetime(2026, 9, 17, 18, 15, tzinfo=timezone.utc)
    assert g._reading_age_s("2026-09-17T14:59:31+00:00", now) == pytest.approx(11728.0, abs=2)
    assert g._reading_age_s("2026-09-17T18:10:00Z", now) == pytest.approx(300.0, abs=2)
    assert g._reading_age_s(None, now) is None
    assert g._reading_age_s("not-a-time", now) is None


@pytest.mark.asyncio
async def test_the_production_latch_opens_instead_of_sustaining_itself(account):
    """3,717 calls, four readings, no attempts: the gate shed on a reading hours old, and
    shedding suppressed the calls whose responses carry the header."""
    from datetime import datetime, timedelta, timezone
    account["used"] = 38168
    account["at"] = (datetime.now(timezone.utc) - timedelta(hours=3, minutes=16)).isoformat()
    assert await g.account_shed(g.TIER_STANDARD) is None
    assert g.gate_state()["state"] == "open:reading_too_old"


@pytest.mark.asyncio
async def test_a_fresh_reading_still_sheds(account):
    from datetime import datetime, timedelta, timezone
    account["used"] = 38168
    account["at"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    reason = await g.account_shed(g.TIER_STANDARD)
    assert reason and "95%" in reason
    assert g.gate_state()["state"] == "shedding"


@pytest.mark.asyncio
async def test_an_unageable_reading_does_not_shed(account):
    account["used"] = 38168
    account["at"] = "not-a-time"
    assert await g.account_shed(g.TIER_STANDARD) is None
    assert g.gate_state()["state"] == "open:reading_unageable"


@pytest.mark.asyncio
async def test_the_cross_day_state_is_still_its_own(account):
    """Two causes, two names (conventions #18): yesterday's counter vs today's stale one."""
    from datetime import datetime, timedelta, timezone
    account["used"] = 38168
    account["at"] = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                     - timedelta(minutes=5)).isoformat()
    assert await g.account_shed(g.TIER_STANDARD) is None
    assert g.gate_state()["state"] == "open:stale_reading"


# ── a refusal is a measurement (measured 2026-09-17: a 429 carries no counter) ──────────
@pytest.mark.asyncio
async def test_a_recent_refusal_sheds_the_tiers_nobody_is_waiting_on(account):
    """The account cannot be read while it is exhausted, because the refusal carries no
    number. The refusal itself is the reading."""
    from datetime import datetime, timedelta, timezone
    account["used"] = 100                       # a healthy counter, and stale by definition
    account["last_429_at"] = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    reason = await g.account_shed(g.TIER_STANDARD)
    assert reason and "refused" in reason
    assert g.gate_state()["state"] == "shed:rate_limited"
    assert await g.account_shed(g.TIER_BACKGROUND)


@pytest.mark.asyncio
async def test_a_refusal_never_sheds_the_interactive_tier(account):
    """FOREGROUND stays open: it is what a person is waiting on, and it is the path through
    which a 200 -- the only response that carries a counter -- can still arrive."""
    from datetime import datetime, timedelta, timezone
    account["used"] = 100
    account["last_429_at"] = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    assert await g.account_shed(g.TIER_FOREGROUND) is None


@pytest.mark.asyncio
async def test_the_backoff_expires_on_its_own(account):
    """A shed that outlived its evidence would be the latch again, in a new costume."""
    from datetime import datetime, timedelta, timezone
    account["used"] = 100
    account["last_429_at"] = (datetime.now(timezone.utc)
                              - timedelta(seconds=g.RATE_LIMIT_BACKOFF_S + 60)).isoformat()
    assert await g.account_shed(g.TIER_STANDARD) is None
    assert g.gate_state()["state"] != "shed:rate_limited"


@pytest.mark.asyncio
async def test_an_unreadable_refusal_timestamp_does_not_shed(account):
    account["used"] = 100
    account["last_429_at"] = "not-a-time"
    assert await g.account_shed(g.TIER_STANDARD) is None
    assert g.gate_state()["state"] != "shed:rate_limited"
