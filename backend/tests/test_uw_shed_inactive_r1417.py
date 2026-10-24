"""R-IV.1417(a) — the shed is INACTIVE as a settled state, and the 429 count is split.

(a)1 THE WORDING WAS THE FAULT. The surface said "no UW quota header seen YET this process" and
`open:no_header`. Both read as a transient about to clear -- which is what they meant when a
header was still expected on the next response. The probe settled it on 2026-10-24: UW publishes
only `x-uw-req-per-minute-remaining` and `-reset`, from which a DAILY used/limit cannot be formed
at any sampling rate. Nothing in the wording may read like a fault about to clear.

(a)3 THE 429 COUNT IS WHAT WOULD REOPEN THIS. The hub already tells the two kinds apart --
`LIMIT_BODY_MARKER` against the 429 body, R-IV.901(c)3 -- but the only tally,
`uw:daily_429s_by_caller`, lumps both under one per-caller number, so one daily-limit refusal
looked like one burst throttle on a busy poller.
"""
from __future__ import annotations

import ast
import os

import pytest

from integrations import uw_api as u
from integrations import uw_governor as g

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UW_FILE = os.path.join(BACKEND, "integrations", "uw_api.py")


def _fn(name):
    with open(UW_FILE, encoding="utf-8-sig") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    raise AssertionError(name)


# ── (a)1 a settled statement ────────────────────────────────────────────────

def test_the_surface_says_INACTIVE_not_pending():
    code = _fn("account_quota")
    assert "INACTIVE" in code
    assert "no longer publishes" in code
    assert "not a fault awaiting a fix" in code
    # The old pending wording must be gone: "yet" is the word that made it read as transient.
    assert "seen yet this process" not in code, (
        "the surface still says the header has not been seen YET, which reads as pending")


def test_it_carries_the_DATE_of_the_last_real_reading():
    """So nobody has to guess how long this has been true."""
    code = _fn("account_quota")
    assert "last_real_account_reading" in code and "2026-09-11" in code
    assert "headers_absent_since_observed" in code and "2026-10-24" in code


def test_it_names_what_protection_IS_in_force():
    """A statement that the shed is off, without saying what still holds, would read as "there
    is no protection"."""
    code = _fn("account_quota")
    assert "PER-TAG" in code or "per-tag" in code
    assert "reserve" in code


# ── (a)2 nothing else in the governor changed ───────────────────────────────

def test_the_per_tag_quotas_and_the_reserve_STAND():
    from integrations.uw_api_cache import UW_FOREIGN_RESERVE

    assert UW_FOREIGN_RESERVE == 12000
    assert g.ACCOUNT_SHED_AT == {g.TIER_BACKGROUND: 0.55, g.TIER_STANDARD: 0.75,
                                 g.TIER_FOREGROUND: 0.92}
    # The shed being inactive is about its INPUT, not its thresholds: they stay, so the day a
    # counter exists again it arms without a further change.
    assert g.QUOTAS and g.FOREIGN_RESERVE_QUOTAS


# ── (a)3 the split count ────────────────────────────────────────────────────

def test_the_two_kinds_are_counted_SEPARATELY():
    assert u.REDIS_KEY_UW_429_DAILY_LIMIT != u.REDIS_KEY_UW_429_PER_MINUTE
    assert "daily" in u.REDIS_KEY_UW_429_DAILY_LIMIT
    assert "per_minute" in u.REDIS_KEY_UW_429_PER_MINUTE


def test_the_split_uses_the_vendors_OWN_marker():
    """`daily_request_limit_hit` is the vendor's string and Nick's. The body is the only thing
    that distinguishes the two kinds, which is why the count happens where the body is read."""
    assert g.LIMIT_BODY_MARKER == "daily_request_limit_hit"
    src = open(UW_FILE, encoding="utf-8-sig").read()
    i = src.index("_GOV_LIMIT_MARKER in _body")
    window = src[i - 400:i + 400]
    assert "REDIS_KEY_UW_429_DAILY_LIMIT" in window
    assert "REDIS_KEY_UW_429_PER_MINUTE" in window


def test_the_count_is_per_UW_DAY_not_per_calendar_day():
    """The vendor's budget resets at 20:00 ET. A calendar count would split one budget across
    two rows, which is the one thing a limit-hit count must not do."""
    code = _fn("_uw_day_str")
    assert "uw_day" in code
    surface = _fn("account_quota")
    assert "20:00 ET" in surface


@pytest.mark.asyncio
async def test_counting_never_raises_and_increments_the_right_key():
    import database.redis_client as rc

    store = {}

    class _FR:
        async def incr(self, k):
            store[k] = store.get(k, 0) + 1

        async def expire(self, k, t):
            store[(k, "ttl")] = t

        async def get(self, k):
            return store.get(k)

    real = rc.get_redis_client

    async def fake():
        return _FR()

    rc.get_redis_client = fake
    try:
        await u._count_429(u.REDIS_KEY_UW_429_DAILY_LIMIT)
        await u._count_429(u.REDIS_KEY_UW_429_PER_MINUTE)
        await u._count_429(u.REDIS_KEY_UW_429_PER_MINUTE)
    finally:
        rc.get_redis_client = real

    day = u._uw_day_str()
    assert store["%s:%s" % (u.REDIS_KEY_UW_429_DAILY_LIMIT, day)] == 1
    assert store["%s:%s" % (u.REDIS_KEY_UW_429_PER_MINUTE, day)] == 2
    assert store[("%s:%s" % (u.REDIS_KEY_UW_429_DAILY_LIMIT, day), "ttl")] == u.REDIS_429_TTL_S

    # A dead Redis must not raise into the call it observes.
    async def dead():
        return None

    rc.get_redis_client = dead
    try:
        assert await u._count_429(u.REDIS_KEY_UW_429_PER_MINUTE) is None
    finally:
        rc.get_redis_client = real


def test_the_surface_explains_WHICH_count_reopens_the_question():
    code = _fn("account_quota")
    assert "429_today" in code
    assert "daily_limit_hit" in code and "per_minute" in code
    assert "reopen" in code.lower()
