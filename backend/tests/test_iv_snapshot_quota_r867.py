"""iv_snapshot's UW quota and its per-caller off-hours exemption — R-IV.867(e).

THE BRANCH ARRIVED WITHOUT A QUOTA. It adds a new UW caller tag, `iv_snapshot`, and registered
nothing for it, so it fell through to DEFAULT_QUOTA/DEFAULT_TIER = (500, STANDARD). The job runs
at 16:45 ET, outside RTH, where STANDARD keeps 25% -- 125 calls for a job that needs its budget
in full, once, on the only occasion it ever runs. Measured before the fix:

    quota_for('iv_snapshot')     -> (500, 'STANDARD')
    effective at 16:45 ET        -> (125, 'STANDARD')

That failure mode is quiet: a half-budget pass yields a PARTIAL snapshot, not an error, so the
missing half would read as "those tickers had no IV" rather than "the governor cut us off".

WHY A PER-CALLER FACTOR AND NOT A TIER CHANGE. The tier does two jobs -- it sets the off-hours
factor AND what gets shed first under pressure. FOREGROUND already carries factor 1.0, but it is
never shed, and a nightly snapshot is precisely what SHOULD be shed before a live quote. The
per-caller factor buys the off-hours quota without the shedding immunity.
"""
from __future__ import annotations

import sys
from datetime import datetime

import pytest
import pytz

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from integrations.uw_governor import (  # noqa: E402
    NON_RTH_QUOTA_FACTOR, OFF_HOURS_FACTOR_BY_CALLER, TIER_STANDARD, effective_quota, quota_for,
)

ET = pytz.timezone("America/New_York")
RTH = ET.localize(datetime(2026, 10, 13, 11, 0))        # a Tuesday, mid-session
AT_1645 = ET.localize(datetime(2026, 10, 13, 16, 45))   # when the job actually runs
OVERNIGHT = ET.localize(datetime(2026, 10, 14, 3, 0))


def test_the_ruled_quota_is_registered():
    assert quota_for("iv_snapshot") == (250, TIER_STANDARD)


def test_it_is_not_promoted_to_foreground():
    """The exemption must not be bought by changing the tier: FOREGROUND is never shed, and a
    nightly snapshot should be shed before a live quote."""
    assert quota_for("iv_snapshot")[1] == TIER_STANDARD


def test_the_full_quota_survives_the_off_hours_cut():
    """The whole point. 250, not 62, at the only time it ever runs."""
    assert effective_quota("iv_snapshot", AT_1645) == (250, TIER_STANDARD)


def test_it_is_the_same_in_and_out_of_session():
    assert effective_quota("iv_snapshot", RTH) == effective_quota("iv_snapshot", AT_1645)
    assert effective_quota("iv_snapshot", OVERNIGHT) == (250, TIER_STANDARD)


def test_the_exemption_is_declared_as_1_point_0():
    assert OFF_HOURS_FACTOR_BY_CALLER["iv_snapshot"] == 1.0


# ── the pair: nothing else moved ────────────────────────────────────────────

@pytest.mark.parametrize("caller,rth_quota", [
    ("darkpool_ticker", 500),
    ("short_interest", 200),
    ("stock_info", 400),
])
def test_an_unlisted_standard_caller_still_takes_the_25_percent_cut(caller, rth_quota):
    """Without this, an exemption applied to every caller would pass every test above. The
    change has to be scoped to the one caller that was ruled."""
    assert effective_quota(caller, RTH) == (rth_quota, TIER_STANDARD)
    assert effective_quota(caller, AT_1645) == (int(rth_quota * 0.25), TIER_STANDARD)


def test_only_the_ruled_callers_are_exempt():
    """A named set, not a count: it fails on an unintended addition exactly as a count would
    AND says which callers are exempt, so the next reader need not go and look."""
    assert set(OFF_HOURS_FACTOR_BY_CALLER) == {"iv_snapshot"}


def test_the_tier_factors_themselves_are_unchanged():
    """The per-caller map is an override, not a replacement. If the tier table drifted, every
    unlisted caller's budget moved and this file would not have noticed."""
    assert NON_RTH_QUOTA_FACTOR[TIER_STANDARD] == 0.25


def test_an_unknown_caller_keeps_the_default_behaviour():
    """`.get(caller, tier_factor)` must leave the fall-through path alone — a typo'd caller tag
    should behave exactly as it did before the exemption existed."""
    assert effective_quota("not_a_real_caller", AT_1645) == (125, TIER_STANDARD)
