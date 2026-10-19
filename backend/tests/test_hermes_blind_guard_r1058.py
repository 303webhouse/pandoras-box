"""R-IV.1058(b) — the Hermes alarm gets its own quota, and announces its own blindness.

WHAT HAPPENED, measured, not inferred:

    uw_day       snapshot  429s       quota 1100
    2026-10-12        458     0       baseline: MTM + quote + macro strip
    2026-10-13       1106     0       OVER by 6
    2026-10-14       1100     0       pinned AT the ceiling

`hermes_session_poll` shared the `snapshot` caller tag, whose 1,100/day was measured on
2026-09-14 -- before this job existed. The tag ran out at 2026-10-14 17:47:08Z and the job then
failed 133 times, once a minute, to the 16:00 ET close, reporting "alarm is blind". 429s = 0 on
every row: UW's own limiter never fired, so the block was this hub's governor doing its job on
an under-funded tag.

AND THE ALARM NEVER SAID SO WHERE IT MATTERED. `stable_job_status.alerted` was TRUE -- the
flatline alert fired, reached /health, and did not reach the phone. The escalation now travels
the same road as the alerts it is failing to send.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from integrations.uw_governor import (
    DAILY_BUDGET, QUOTA_SAFETY_BUFFER, QUOTAS,
)
from jobs import hermes_session_poll as poll

#: What the tag was spending when it broke, from uw_caller_spend_daily.
MEASURED_SNAPSHOT_PEAK = 1106
#: 3 symbols x one poll per 60s x 390 RTH minutes.
HERMES_PROJECTED_DEMAND = 1170


# ── 1. the alarm no longer spends another consumer's quota ────────────────────

def test_the_job_has_its_own_caller_tag():
    assert poll.CALLER_TAG == "hermes_session"
    assert poll.CALLER_TAG in QUOTAS


def test_it_does_not_spend_under_snapshot_any_more():
    """THE FIX. `snapshot` funds MTM, quote and the macro strip, and MTM marks positions --
    so the alarm starving that tag was the worse half of this failure."""
    src = inspect.getsource(poll._snapshot)
    assert "caller=CALLER_TAG" in src, "the snapshot read must carry this job's own tag"


def test_get_snapshot_accepts_a_caller_and_still_defaults_to_snapshot():
    """Every existing consumer must be unchanged -- the parameter is additive."""
    from integrations.uw_api import get_snapshot
    sig = inspect.signature(get_snapshot)
    assert "caller" in sig.parameters
    assert sig.parameters["caller"].default == "snapshot"
    assert sig.parameters["caller"].kind == inspect.Parameter.KEYWORD_ONLY


def test_the_quota_covers_a_full_session():
    """Sized by this table's own max(observed, projected) x ~1.2 rule. A quota under a full
    session's demand would reproduce the failure later in the day instead of removing it."""
    q = QUOTAS["hermes_session"][0]
    assert q >= HERMES_PROJECTED_DEMAND, (q, HERMES_PROJECTED_DEMAND)
    assert q / HERMES_PROJECTED_DEMAND >= 1.19


def test_it_is_FOREGROUND_so_it_is_never_clock_gated():
    """A displacement alarm that stops at a quiet hour is not an alarm."""
    assert QUOTAS["hermes_session"][1] == "FOREGROUND"


def test_snapshot_keeps_its_whole_allowance():
    """The fix must not pay for itself out of the tag it was starving: the baseline it has to
    cover (458 measured, pre-alarm) is unchanged, and its quota is too."""
    assert QUOTAS["snapshot"][0] == 1100


# ── 2. the reallocation was budget-neutral ───────────────────────────────────

def test_the_table_still_sums_to_exactly_the_committed_total():
    """Headroom was ZERO, so the tag could only be funded by a reallocation. Two separate
    tests already pin this sum; this one says why it must not move."""
    # R-IV.1265(d) MOVED THE TOTAL: `notables_strip` (50) was funded by cutting the
    # safety buffer 2,000 -> 1,950, so the table now sums to 26,050. The literal 26,000
    # was hard-coded in FIVE separate test files, each written by a different carve to
    # say "this sum must not move" -- so the first ruled move broke all five at once.
    # The INVARIANT was never the literal; it is that the table fills the budget minus
    # the buffer exactly. Asserted that way now, so the next ruled change to either
    # number does not require editing five files that were never about the number.
    assert sum(q for q, _ in QUOTAS.values()) == DAILY_BUDGET - QUOTA_SAFETY_BUFFER
    assert sum(q for q, _ in QUOTAS.values()) <= DAILY_BUDGET - QUOTA_SAFETY_BUFFER


@pytest.mark.parametrize("tag,peak", [
    ("ohlc_bars", 1491),
    ("ohlc_sector", 1850),
    ("technical_indicator", 1848),
])
def test_no_tag_was_funded_down_below_its_own_measured_peak(tag, peak):
    """THE CONTROL ON THE FUNDING. Paying for this tag by under-sizing another just moves the
    outage, and this table's history is explicit that a quota under measured demand "blocks
    the largest consumer on sight"."""
    q = QUOTAS[tag][0]
    assert q > peak, (tag, q, peak)
    assert q / peak >= 1.19, (tag, q, peak, round(q / peak, 3))


def test_the_crypto_resolver_was_NOT_raided():
    """It was the obvious source -- 3,350 funded, measured peak 0 in the window -- and a test
    rightly refuses it, because the family's measured peak is 2,764 in a single day. Crypto
    research being closed is not evidence the resolver will never run again."""
    assert QUOTAS["crypto_bars_outcome_resolver"][0] == 3350
    assert QUOTAS["crypto_bars_outcome_resolver"][0] > 2764


# ── 3. a blind alarm surfaces ITSELF ─────────────────────────────────────────

class _Spy:
    """Stands in for `integrations.ntfy_push`, recording what the guard tried to send."""

    def __init__(self, configured=True, sent=True, boom=False):
        self.configured, self.ok, self.boom, self.calls = configured, sent, boom, []

    def is_configured(self):
        return self.configured

    async def send(self, ticker, alert_type, action, *, title=None, priority="default"):
        if self.boom:
            raise RuntimeError("ntfy exploded")
        self.calls.append({"ticker": ticker, "alert_type": alert_type, "action": action,
                           "title": title, "priority": priority})
        return {"sent": self.ok}


@pytest.fixture(autouse=True)
def _clean_session():
    poll._blind_pushed.clear()
    poll._session_date = "2026-10-14"
    yield
    poll._blind_pushed.clear()


def _install(monkeypatch, spy):
    """Patch the REAL module's attributes, not sys.modules.

    THE FIRST VERSION PATCHED sys.modules AND PASSED IN ISOLATION, THEN FAILED IN THE SUITE.
    `_push_blind_notice` does `from integrations import ntfy_push`, which resolves the
    `ntfy_push` ATTRIBUTE on the already-imported `integrations` package rather than looking in
    sys.modules. Whenever another test had imported the real module first -- which is to say,
    in the full suite but not on its own -- the patch was bypassed and the real `send` ran. The
    captured log said so plainly: "BLIND and NTFY_TOPIC is not set".

    A test that passes alone and fails in company was testing the harness, not the code.
    """
    from integrations import ntfy_push as real
    monkeypatch.setattr(real, "is_configured", spy.is_configured)
    monkeypatch.setattr(real, "send", spy.send)


def test_a_blind_pass_pushes_a_notice(monkeypatch):
    spy = _Spy()
    _install(monkeypatch, spy)
    res = asyncio.run(poll._push_blind_notice(3))
    assert res.get("sent") is True
    assert len(spy.calls) == 1
    c = spy.calls[0]
    assert c["ticker"] == "HERMES"
    assert "BLIND" in c["alert_type"].upper()


def test_it_pushes_AT_MOST_ONCE_PER_SESSION(monkeypatch):
    """THE WHOLE POINT OF THE LADDER. The failure fired 133 times in 134 minutes; 133 pushes
    would be the outage reproduced on the phone instead of reported."""
    spy = _Spy()
    _install(monkeypatch, spy)
    for _ in range(50):
        asyncio.run(poll._push_blind_notice(3))
    assert len(spy.calls) == 1, "%d notices sent" % len(spy.calls)


def test_a_NEW_SESSION_may_be_notified_again(monkeypatch):
    """THE PAIR. Once-ever would mean a second blind day said nothing. _roll_session clears
    the flag with the ladder."""
    spy = _Spy()
    _install(monkeypatch, spy)
    asyncio.run(poll._push_blind_notice(3))
    poll._roll_session("2026-10-15")
    asyncio.run(poll._push_blind_notice(3))
    assert len(spy.calls) == 2


def test_the_notice_carries_NO_MONEY(monkeypatch):
    """R-IV.901(b)2. The real `build_message` enforces it; this asserts the three strings this
    job passes cannot carry a figure in the first place."""
    spy = _Spy()
    _install(monkeypatch, spy)
    asyncio.run(poll._push_blind_notice(3))
    blob = " ".join(str(v) for v in spy.calls[0].values())
    import re
    assert not re.search(r"[$€£]\s*\d|\b\d+\.\d{2}\b", blob), blob


def test_the_notice_survives_an_unconfigured_topic(monkeypatch):
    """It must report, not raise: this runs immediately before the OutputCheckFailed that
    records the blindness, and an exception here would mislabel the ledger entry."""
    spy = _Spy(configured=False)
    _install(monkeypatch, spy)
    res = asyncio.run(poll._push_blind_notice(3))
    assert res.get("sent") is False
    assert "NTFY_TOPIC" in res.get("reason", "")
    assert not spy.calls


def test_the_notice_survives_the_notifier_raising(monkeypatch):
    _install(monkeypatch, _Spy(boom=True))
    res = asyncio.run(poll._push_blind_notice(3))
    assert res.get("sent") is False
    assert res.get("reason") == "RuntimeError"


def test_the_ladder_is_marked_BEFORE_the_await(monkeypatch):
    """A cancelled await must not leave the flag unset -- otherwise the next pass pushes again,
    once a minute, which is the failure this guard reports rather than reproduces."""
    # PARSED, NOT INDEXED. The first version of this test failed on the COMMENT that explains
    # the await ordering -- it contains the word "await". ast.unparse drops comments, and the
    # docstring is removed by identity. Seventh instance of that trap in this register.
    import ast
    import textwrap
    fn = ast.parse(textwrap.dedent(inspect.getsource(poll._push_blind_notice))).body[0]
    doc = fn.body[0] if (fn.body and isinstance(fn.body[0], ast.Expr)
                         and isinstance(getattr(fn.body[0], "value", None), ast.Constant)
                         and isinstance(fn.body[0].value.value, str)) else None
    code = "\n".join(ast.unparse(n) for n in fn.body if n is not doc)
    mark = code.index("_blind_pushed[key] = True")
    first_await = code.index("await ")
    assert mark < first_await, (
        "the flag must be set before the first await:\n%s" % code)


def test_the_blind_raise_still_happens_and_is_still_the_ledger_entry():
    """The notice is an ADDITION. If it replaced the raise, /health would go quiet about a
    blind alarm -- trading one silent channel for another."""
    src = inspect.getsource(poll._recorded_pass)
    assert "_push_blind_notice" in src
    assert "raise OutputCheckFailed" in src
    assert src.index("_push_blind_notice") < src.index("raise OutputCheckFailed")
