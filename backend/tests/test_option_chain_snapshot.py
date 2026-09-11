"""S8 — the forward option-chain collection (R-IV.361).

The collector law makes the FAILURE cases the important ones: a session not
captured cannot be recovered, so a capture that quietly writes nothing, or writes
a censored chain without saying so, is worse than an obvious crash.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import option_chain_snapshot as s8

TODAY = date(2026, 9, 11)


def contract(expiry: str, strike: float, ctype: str = "call",
             bid=1.0, ask=1.2, iv=0.18, oi=10, vol=5):
    return {
        "details": {"expiration_date": expiry, "strike_price": strike,
                    "contract_type": ctype, "ticker": "X"},
        "last_quote": {"bid": bid, "ask": ask},
        "day": {"open_interest": oi, "volume": vol},
        "implied_volatility": iv,
    }


# ---------------------------------------------------------------- DTE window

def test_only_the_dte_window_is_kept():
    chain = [
        contract("2026-09-18", 500),   # 7 DTE  — out
        contract("2026-10-13", 500),   # 32 DTE — IN
        contract("2026-10-24", 500),   # 43 DTE — IN
        contract("2026-12-18", 500),   # 98 DTE — out
    ]
    rows, raw = s8._rows_from_chain("SPY", chain, TODAY)
    assert raw == 4
    assert [r["dte"] for r in rows] == [32, 43]


@pytest.mark.parametrize("dte,keep", [(29, False), (30, True), (45, True), (46, False)])
def test_window_boundaries_are_inclusive(dte, keep):
    from datetime import timedelta
    exp = (TODAY + timedelta(days=dte)).isoformat()
    rows, _ = s8._rows_from_chain("SPY", [contract(exp, 500)], TODAY)
    assert bool(rows) is keep


# ------------------------------------------------ the fields PS-02 depends on

def test_bid_and_ask_are_both_kept_not_collapsed_to_a_mid():
    """The SPREAD is the point. A mid is recoverable from the pair; the pair is
    not recoverable from the mid."""
    rows, _ = s8._rows_from_chain("SPY", [contract("2026-10-13", 500, bid=1.0, ask=1.4)], TODAY)
    assert rows[0]["bid"] == 1.0 and rows[0]["ask"] == 1.4


def test_iv_is_carried_as_published():
    rows, _ = s8._rows_from_chain("SPY", [contract("2026-10-13", 500, iv=0.2345)], TODAY)
    assert rows[0]["iv"] == 0.2345


def test_dte_is_stored_not_left_to_be_derived_later():
    """A DTE recomputed later against a changed calendar is a different number."""
    rows, _ = s8._rows_from_chain("SPY", [contract("2026-10-13", 500)], TODAY)
    assert rows[0]["dte"] == 32


# ------------------------------------------------------------- robustness

def test_one_malformed_contract_does_not_cost_the_session():
    chain = [contract("2026-10-13", 500), {"details": None}, {"garbage": 1},
             contract("2026-10-14", 505)]
    rows, raw = s8._rows_from_chain("SPY", chain, TODAY)
    assert len(rows) == 2 and raw == 4


def test_missing_expiry_is_skipped_not_guessed():
    chain = [{"details": {"strike_price": 500, "contract_type": "call"}}]
    rows, _ = s8._rows_from_chain("SPY", chain, TODAY)
    assert rows == []


def test_empty_chain_returns_empty_not_an_exception():
    assert s8._rows_from_chain("SPY", [], TODAY) == ([], 0)
    assert s8._rows_from_chain("SPY", None, TODAY) == ([], 0)


# --------------------------------------------------- truncation is recorded

def test_cap_constant_matches_the_documented_vendor_limit():
    assert s8.UW_CONTRACT_CAP == 500


def test_raw_count_is_the_pre_filter_count():
    """Truncation is judged on what the VENDOR returned, not on what survived the
    DTE filter — filtering to 2 rows out of a capped 500 is still censored."""
    chain = [contract("2026-09-18", i) for i in range(500)]   # all outside the window
    rows, raw = s8._rows_from_chain("SPY", chain, TODAY)
    assert rows == []
    assert raw == 500, "raw count was taken after filtering — truncation would be invisible"


def test_capture_time_is_inside_rth():
    """A post-close capture records stale, wide, untradeable spreads that look like data."""
    from jobs import stable_jobs as sj
    h, m = sj.S8_SNAPSHOT_TIME
    assert (9, 30) < (h, m) < (16, 0)


def test_tickers_and_window_are_the_spec():
    assert s8.S8_TICKERS == ("SPY", "QQQ")
    assert (s8.DTE_MIN, s8.DTE_MAX) == (30, 45)


# ------------------------------- a capture that wrote nothing must not "complete"

@pytest.mark.asyncio
async def test_zero_row_capture_raises_so_the_retry_keeps_trying(monkeypatch):
    """If a no-row capture returned cleanly, has_completed() would mark the session
    done and the retry would stop on a day with no data at all."""
    from jobs import stable_jobs as sj

    async def empty():
        return {"rows": 0, "tickers": {}}

    monkeypatch.setattr(s8, "run_option_chain_snapshot", empty, raising=False)
    import jobs.option_chain_snapshot as mod
    monkeypatch.setattr(mod, "run_option_chain_snapshot", empty, raising=False)
    with pytest.raises(RuntimeError):
        await sj._run_s8()


@pytest.mark.asyncio
async def test_successful_capture_returns_its_summary(monkeypatch):
    from jobs import stable_jobs as sj

    async def good():
        return {"rows": 412, "tickers": {"SPY": {"rows": 200}}}

    import jobs.option_chain_snapshot as mod
    monkeypatch.setattr(mod, "run_option_chain_snapshot", good, raising=False)
    assert (await sj._run_s8())["rows"] == 412
