"""Hermes push phase 1, replayed against 10-08's real rows — R-IV.775(d) / R-IV.780(d).

The 13 timestamps below are the actual `created_at` values from `catalyst_events` for the ET
session 2026-10-08, read out of the database rather than reconstructed. That matters: my first
hand-built instant for the 13:02 ET breach was 19:02Z, which is 13:02 MOUNTAIN. The real row is
17:02Z (ET is UTC−4 in October), and MT is 11:02. A replay built on a reconstructed clock would
have "passed" against the wrong minute.
"""
from datetime import datetime, timezone

import pytest

from webhooks import hermes_push as HP

UTC = timezone.utc


def _t(h, m, s=0):
    return datetime(2026, 10, 8, h, m, s, tzinfo=UTC)


# (utc, ticker, move_pct) — every velocity_breach row for the 2026-10-08 ET session.
TAPE = [
    (_t(13, 30, 30), "USO", 3.03),
    (_t(13, 30, 32), "SMH", -1.51),
    (_t(13, 43, 21), "IBIT", -2.01),
    (_t(13, 44, 2), "SMH", -1.66),
    (_t(13, 44, 2), "USO", 3.36),
    (_t(13, 59, 2), "SMH", -1.82),
    (_t(13, 59, 10), "USO", 3.26),
    (_t(14, 29, 5), "SMH", 1.55),
    (_t(16, 17, 16), "USO", -2.52),
    (_t(16, 53, 3), "SMH", -1.52),
    (_t(17, 2, 2), "QQQ", -1.01),
    (_t(17, 2, 3), "SMH", -2.37),
    (_t(17, 17, 4), "SMH", -1.83),
]


def replay(tape=TAPE):
    """Run the tape through the PURE decision, returning one record per row.

    Uses `should_push` + `co_breaches` directly: no HTTP, no module state, so the result is the
    rule and not the network.
    """
    last: dict = {}
    seen: list = []          # (ticker, ts, move) for co-breach lookup
    out = []
    for ts, tkr, mv in tape:
        # MIRRORS push_breach EXACTLY: the co-breach is computed FIRST, because it can override
        # the cooldown. The first version of this helper called should_push without it, so the
        # replay exercised a rule production does not have -- a test and a bug agreeing.
        co = HP.co_breaches(tkr, ts, seen) if HP.is_pushable(tkr) else []
        ok, reason = HP.should_push(tkr, ts, last.get(tkr), has_co_breach=bool(co))
        if ok:
            last[tkr] = ts
        out.append({"ts": ts, "ticker": tkr, "move": mv, "pushed": ok,
                    "reason": reason, "co": co})
        seen.append((tkr, ts, mv))
    return out


class TestTheControlsTheRulingNames:
    def test_POSITIVE_the_1302_pair_reaches_the_phone_in_one_message(self):
        """R-IV.780(d)'s positive control. QQQ is the day's FIRST QQQ breach so it pushes, and
        its message names SMH −2.37 as the co-breach — so the pair arrives together."""
        r = {(x["ticker"], x["ts"]): x for x in replay()}
        qqq = r[("QQQ", _t(17, 2, 2))]
        smh = r[("SMH", _t(17, 2, 3))]
        # BOTH push. QQQ is the day's first QQQ; SMH is inside its 16:53 cooldown and is let
        # through by the co-breach override. Measured: the webhooks land ONE SECOND apart, so
        # QQQ's backward look sees SMH's 16:53 breach (-1.52) and SMH's sees QQQ's -1.01.
        assert qqq["pushed"] is True and smh["pushed"] is True
        assert qqq["co"] == [("SMH", -1.52)], qqq["co"]
        assert smh["co"] == [("QQQ", -1.01)], smh["co"]
        assert "co-breach overrides the cooldown" in smh["reason"]
        msg = HP.format_message("SMH", -2.37, 30, _t(17, 2, 3), smh["co"])
        assert "SMH -2.37%" in msg
        assert "QQQ -1.01%" in msg
        assert "11:02 AM MDT" in msg, msg      # 17:02Z is 11:02 Mountain, not 13:02

    def test_the_1344_SMH_IS_suppressed_because_it_has_no_co_breach(self):
        """The override is narrow, and this is the control for that. SMH at 13:44 is 14 minutes
        after its first push and has NO equity-beta co-breach (the cluster around it was IBIT and
        USO), so the cooldown holds. Without this the override would be a cooldown bypass."""
        r = {(x["ticker"], x["ts"]): x for x in replay()}
        smh = r[("SMH", _t(13, 44, 2))]
        assert smh["pushed"] is False
        assert "cooldown" in smh["reason"] and "14 min ago" in smh["reason"]
        assert smh["co"] == []

    def test_NEGATIVE_no_USO_breach_ever_pushes(self):
        """R-IV.780(d)'s negative control. NOTE: USO has FOUR breaches on 10-08 (09:30, 09:44,
        09:59, 12:17), not the three the ruling names. Asserted over all of them."""
        uso = [x for x in replay() if x["ticker"] == "USO"]
        assert len(uso) == 4, "the tape holds four USO rows"
        assert not any(x["pushed"] for x in uso)
        for x in uso:
            assert "equity beta only" in x["reason"]

    def test_NEGATIVE_IBIT_does_not_push_either(self):
        ibit = [x for x in replay() if x["ticker"] == "IBIT"]
        assert len(ibit) == 1 and ibit[0]["pushed"] is False
        assert "equity beta only" in ibit[0]["reason"]

    def test_the_whole_tape_pushes_exactly_the_equity_rows_the_cooldown_allows(self):
        """The full ledger, so a change to either rule shows up as a changed list rather than a
        changed count."""
        fired = [(x["ticker"], x["ts"].strftime("%H:%M")) for x in replay() if x["pushed"]]
        assert fired == [
            ("SMH", "13:30"),   # first SMH of the day
            ("SMH", "13:59"),   # 28 min after 13:30
            ("SMH", "14:29"),   # 30 min later
            ("SMH", "16:53"),
            ("QQQ", "17:02"),   # first QQQ -- names SMH -1.52 as its co-breach
            ("SMH", "17:02"),   # inside cooldown, let through by the QQQ co-breach
            ("SMH", "17:17"),
        ], fired
        assert not any(t in ("USO", "IBIT") for t, _ in fired)




class TestTheRosterIsPhase1s:
    @pytest.mark.parametrize("t", ["SPY", "QQQ", "SMH", "spy", " qqq "])
    def test_equity_beta_pushes(self, t):
        assert HP.is_pushable(t) is True

    @pytest.mark.parametrize("t", ["USO", "IBIT", "TLT", "GLD", "HYG", "XLF", "IYR"])
    def test_the_seven_named_do_not_push(self, t):
        """R-IV.775(d) names these explicitly as phase-1 exclusions."""
        assert HP.is_pushable(t) is False
        ok, why = HP.should_push(t, _t(17, 0), None)
        assert ok is False and "equity beta only" in why

    @pytest.mark.parametrize("t", [None, "", "   ", "UNKNOWN"])
    def test_junk_does_not_push(self, t):
        assert HP.should_push(t, _t(17, 0), None)[0] is False


class TestTheCooldownIsPerTicker:
    def test_one_tickers_cooldown_does_not_silence_another(self):
        """A per-ticker cooldown is the point: SMH breaching all morning must not stop QQQ's
        first breach from reaching the phone — which is exactly what happened at 13:02."""
        assert HP.should_push("QQQ", _t(17, 2), None)[0] is True
        assert HP.should_push("SMH", _t(17, 2), _t(16, 53))[0] is False

    @pytest.mark.parametrize("mins,expect", [(0, False), (1, False), (14, False),
                                             (15, True), (16, True), (60, True)])
    def test_the_boundary_is_15_minutes_inclusive(self, mins, expect):
        from datetime import timedelta
        base = _t(17, 0)
        assert HP.should_push("SPY", base + timedelta(minutes=mins), base)[0] is expect

    def test_a_first_breach_always_pushes(self):
        assert HP.should_push("SPY", _t(17, 0), None) == (True, "first push for SPY")


class TestCoBreachIsEquityOnly:
    def test_oil_and_bitcoin_are_not_a_co_breach(self):
        """Measured on 10-08: the morning's 'three ticker' cluster was IBIT + SMH + USO — three
        unrelated complexes — while the pair that mattered was QQQ + SMH. Counting unrelated
        tickers as breadth is what rated the noise above the signal."""
        recent = [("USO", _t(13, 44), 3.36), ("IBIT", _t(13, 43), -2.01)]
        assert HP.co_breaches("SMH", _t(13, 44, 2), recent) == []

    def test_an_equity_co_breach_is_reported(self):
        recent = [("SMH", _t(16, 53, 3), -1.52), ("USO", _t(17, 1), 1.0)]
        assert HP.co_breaches("QQQ", _t(17, 2, 2), recent) == [("SMH", -1.52)]

    def test_a_co_breach_outside_the_window_is_not_counted(self):
        recent = [("SMH", _t(16, 40), -2.0)]
        assert HP.co_breaches("QQQ", _t(17, 2), recent) == []

    def test_a_ticker_is_never_its_own_co_breach(self):
        recent = [("QQQ", _t(17, 1), -1.0)]
        assert HP.co_breaches("QQQ", _t(17, 2), recent) == []


class TestItNeverCostsAnIngest:
    @pytest.mark.asyncio
    async def test_a_missing_webhook_is_reported_and_does_NOT_start_the_cooldown(self):
        """A message that never left must not suppress the next one."""
        HP.reset_for_tests()
        out = await HP.push_breach("QQQ", -1.01, 30, now=_t(17, 2), webhook_url="")
        assert out["pushed"] is False and "not set" in out["reason"]
        assert HP.should_push("QQQ", _t(17, 3), HP._last_push.get("QQQ"))[0] is True

    @pytest.mark.asyncio
    async def test_a_non_pushable_ticker_makes_no_request(self):
        HP.reset_for_tests()
        out = await HP.push_breach("USO", 3.36, 30, now=_t(13, 44),
                                   webhook_url="http://127.0.0.1:1/never")
        assert out["pushed"] is False
        assert "equity beta only" in out["reason"]

    @pytest.mark.asyncio
    async def test_a_transport_failure_is_returned_not_raised(self):
        HP.reset_for_tests()
        out = await HP.push_breach("QQQ", -1.01, 30, now=_t(17, 2),
                                   webhook_url="http://127.0.0.1:1/dead")
        assert out["pushed"] is False
        assert HP._last_push.get("QQQ") is None, "a failed send must not start the cooldown"


class TestTheHandlerCallsIt:
    def test_the_push_is_wired_after_the_store(self):
        """A notifier the handler never calls is the defect this replaces, in a new place."""
        import inspect
        from webhooks import hermes
        src = inspect.getsource(hermes.hermes_webhook)
        assert "push_breach" in src
        assert src.index("_store_catalyst_event") < src.index("push_breach"), \
            "the row must be stored before the message is sent"
