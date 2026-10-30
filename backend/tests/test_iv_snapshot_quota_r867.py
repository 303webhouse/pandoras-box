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
    NON_RTH_QUOTA_FACTOR, OFF_HOURS_FACTOR_BY_CALLER, TIER_FOREGROUND, TIER_STANDARD,
    effective_quota, quota_for,
)

ET = pytz.timezone("America/New_York")
RTH = ET.localize(datetime(2026, 10, 13, 11, 0))        # a Tuesday, mid-session
AT_1645 = ET.localize(datetime(2026, 10, 13, 16, 45))   # when iv_snapshot runs
AT_1630 = ET.localize(datetime(2026, 10, 13, 16, 30))   # when darkpool_collector runs
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
    """A named set, not a count: it fails on an unintended addition exactly as a count would AND
    says which callers are exempt, so the next reader need not go and look.

    It has now done its job THREE TIMES: darkpool_collector under R-IV.876(e),
    darkpool_backfill_triton under R-IV.940(b), and iv_term_backfill under R-IV.1073(c) --
    each failed this assertion rather than passing silently. That is the whole reason to name
    the set instead of counting it.

    Each exemption needs the same justification -- the caller's WHOLE WINDOW is after the close,
    so budgeting it as though off-hours were its idle time is wrong. The backfill earned it the
    hard way: the 0.25 factor turned its ruled 2,500/day into 625 and blocked the first night's
    run after about 600 calls."""
    assert set(OFF_HOURS_FACTOR_BY_CALLER) == {
        "iv_snapshot",                # R-IV.867(e)
        "darkpool_collector",         # R-IV.876(e) / R-IV.839(c)
        "darkpool_backfill_triton",   # R-IV.940(b)
        # R-IV.1073(c), ratified by R-IV.1079(a): "iv_term_backfill: 1.0 makes the approved
        # 136 calls spendable and does not widen the grant; quota 165 and tier STANDARD are
        # unchanged." It earned it the same hard way as the line above -- the 0.25 factor cut
        # the ruled 165 to 41 and the governor logged "BLOCK ... count=41 limit=41".
        "iv_term_backfill",           # R-IV.1073(c) / R-IV.1079(a)
        # R-IV.1451(b): the third with the same haircut -- 250 x 0.25 = 62, "QUOTA_EXCEEDED
        # darkpool_forward 62/62" every night 10-27 -> 10-30, partway through NVDA.
        "darkpool_forward",           # R-IV.1451(b)
        "darkpool_topup",             # R-IV.1456(f): the one weekend top-up
    }


# ── the second user of the mechanism — R-IV.823(e) / R-IV.839(c) ────────────

def test_darkpool_collector_has_the_interim_quota():
    """R-IV.886(d): 250, not the 3,000 of R-IV.839(c). 3,000 does not FIT -- it put the table at
    28,750 against a 26,000 ceiling, with UW_GOVERNOR_MODE = enforce in production, so the
    overrun would refuse real calls. 250 is exactly the room available, and the resize waits on
    10 UW days of measured spend."""
    assert quota_for("darkpool_collector") == (250, TIER_STANDARD)


def test_the_table_fits_the_ceiling_EXACTLY_at_the_interim_figure():
    """The reason 250 and not 300: it is the whole remaining room, to the call. This asserts the
    arithmetic the interim rests on, so a later quota change cannot silently reintroduce the
    overrun that held the merge."""
    from integrations.uw_api_cache import DAILY_BUDGET
    from integrations.uw_governor import QUOTAS, QUOTA_SAFETY_BUFFER

    # R-IV.1265(d) MOVED THE TOTAL: `notables_strip` (50) was funded by cutting the
    # safety buffer 2,000 -> 1,950, so the table now sums to 26,050. The literal 26,000
    # was hard-coded in FIVE separate test files, each written by a different carve to
    # say "this sum must not move" -- so the first ruled move broke all five at once.
    # The INVARIANT was never the literal; it is that the table fills the budget minus
    # the buffer exactly. Asserted that way now, so the next ruled change to either
    # number does not require editing five files that were never about the number.
    assert sum(q for q, _ in QUOTAS.values()) == DAILY_BUDGET - QUOTA_SAFETY_BUFFER


def test_darkpool_collector_keeps_its_quota_at_1630_when_it_runs():
    """Its cron is 16:30 ET. Without the per-caller factor, STANDARD's 25% would leave 62 calls
    -- which is why the factor matters more at 250 than it did at 3,000."""
    assert effective_quota("darkpool_collector", AT_1630) == (250, TIER_STANDARD)


def test_darkpool_ticker_is_left_UNRESIZED():
    """R-IV.886(d): darkpool_ticker stays as it was until the measurement. Asserted so a resize
    cannot ride along unnoticed with the collector's."""
    assert quota_for("darkpool_ticker") == (500, TIER_STANDARD)
    assert "darkpool_ticker" not in OFF_HOURS_FACTOR_BY_CALLER


def test_darkpool_collector_is_NOT_promoted_to_foreground():
    """R-IV.839(c), explicitly: "Do NOT promote it to FOREGROUND." FOREGROUND would have given
    the same 1.0 factor and also made it immune from shedding, and a nightly bulk collection is
    the first thing that should be shed under pressure, not the last."""
    assert quota_for("darkpool_collector")[1] == TIER_STANDARD
    assert quota_for("darkpool_collector")[1] != TIER_FOREGROUND


def test_the_tier_factors_themselves_are_unchanged():
    """The per-caller map is an override, not a replacement. If the tier table drifted, every
    unlisted caller's budget moved and this file would not have noticed."""
    assert NON_RTH_QUOTA_FACTOR[TIER_STANDARD] == 0.25


def test_an_unknown_caller_keeps_the_default_behaviour():
    """`.get(caller, tier_factor)` must leave the fall-through path alone — a typo'd caller tag
    should behave exactly as it did before the exemption existed."""
    assert effective_quota("not_a_real_caller", AT_1645) == (125, TIER_STANDARD)
