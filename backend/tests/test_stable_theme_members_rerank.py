"""Regression test for the theme member top/bottom re-rank inversion bug
(P1, 2026-07-21): during the RTH live-price overlay, get_theme_members()
recomputed ret_1d for the top+bottom slice but left top_slice/bottom_slice
MEMBERSHIP frozen at the nightly close-based order -- so on a reversal day
the displayed "TOP" and "BOTTOM" buckets could show the worst and best
movers respectively (2026-07-21 Software Infrastructure incident: FROG at
-6.3% ret_1d rendered in TOP, NET at +0.7% ret_1d rendered in BOTTOM).

Fix: re-derive top_slice/bottom_slice from the post-overlay sorted order,
and expose ranking_basis ('live' vs 'close@YYYY-MM-DD') so callers can tell
which vintage the ranking itself is based on.
"""
import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from services.read_only import stable as stable_svc


class _Acq:
    """Async context manager wrapper for mocking pool.acquire()."""
    def __init__(self, conn):
        self._c = conn

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, *args):
        return False


def _roster(n=12):
    """Nightly-close ranking: T00 best (+6%) down to T11 worst (-5%), evenly spaced."""
    latest = date(2026, 7, 21)
    rows = []
    for i in range(n):
        ret = (n - 1 - i) * 0.01 - 0.05
        rows.append({
            "ticker": f"T{i:02d}",
            "name": f"Ticker {i}",
            "subtheme": "core",
            "ret_1d": ret,
            "ret_5d": ret * 2,
            "rs_qqq_20d": 1.0,
            "above_ma20": True,
            "above_ma50": True,
            "atr_ext_50ma": 0.5,
            "last_price": 100.0 + i,
        })
    return latest, rows


def _mock_pool(latest, rows):
    conn = MagicMock()

    async def _fetchval(sql, *a, **k):
        return latest

    async def _fetch(sql, *a, **k):
        return rows

    conn.fetchval = AsyncMock(side_effect=_fetchval)
    conn.fetch = AsyncMock(side_effect=_fetch)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_Acq(conn))
    return pool


def test_live_overlay_inverts_ranking_and_top_bottom_are_rederived(monkeypatch):
    """The 2026-07-21 incident case: live prices fully invert the nightly order.

    live_ret[Ti] = -nightly_ret[Ti] is a clean full reversal here (the nightly
    returns are a symmetric ladder from +6% to -5%), so the nightly-worst
    ticker (T11) becomes today's best mover and the nightly-best (T00)
    becomes today's worst -- reproducing the FROG/NET incident shape exactly.
    """
    latest, rows = _roster(12)
    pool = _mock_pool(latest, rows)
    by_idx = {int(r["ticker"][1:]): r for r in rows}

    def _fake_fetch_live_prices(tickers):
        live_prices = {}
        for t in tickers:
            r = by_idx[int(t[1:])]
            live_prices[t] = r["last_price"] * (1 - r["ret_1d"])
        return live_prices

    monkeypatch.setattr("services.read_only.stable.get_postgres_client", AsyncMock(return_value=pool))
    monkeypatch.setattr("stable_engine.job_status.is_market_hours", lambda: True)
    monkeypatch.setattr("stable_engine.live.fetch_live_prices", _fake_fetch_live_prices)

    result = asyncio.run(stable_svc.get_theme_members("Software Infrastructure", top=5, bottom=5))

    top = result["top"]
    bottom = result["bottom"]
    assert len(top) == 5 and len(bottom) == 5
    assert min(m["ret_1d"] for m in top) >= max(m["ret_1d"] for m in bottom), (
        "top/bottom inversion bug: a bottom-slice member out-returned a top-slice member"
    )
    # The nightly-worst ticker (T11) must now be in TOP; the nightly-best (T00) in BOTTOM.
    assert "T11" in [m["ticker"] for m in top]
    assert "T00" in [m["ticker"] for m in bottom]
    assert result["ranking_basis"] == "live"
    assert result["anchor"] == "provisional"


def test_overlay_failure_keeps_nightly_membership_and_close_basis(monkeypatch):
    """Overlay raises mid-session: membership/order must stay nightly-ranked
    and ranking_basis must say so, rather than silently claiming 'live'."""
    latest, rows = _roster(12)
    pool = _mock_pool(latest, rows)

    def _raise_fetch_live_prices(tickers):
        raise RuntimeError("yfinance unavailable")

    monkeypatch.setattr("services.read_only.stable.get_postgres_client", AsyncMock(return_value=pool))
    monkeypatch.setattr("stable_engine.job_status.is_market_hours", lambda: True)
    monkeypatch.setattr("stable_engine.live.fetch_live_prices", _raise_fetch_live_prices)

    result = asyncio.run(stable_svc.get_theme_members("Software Infrastructure", top=5, bottom=5))

    expected_top = [r["ticker"] for r in rows[:5]]
    expected_bottom = [r["ticker"] for r in rows[-5:][::-1]]
    assert [m["ticker"] for m in result["top"]] == expected_top
    assert [m["ticker"] for m in result["bottom"]] == expected_bottom
    assert result["ranking_basis"] == f"close@{latest}"
    assert result["anchor"] == "close"


def test_db_failure_path_reports_degraded_with_ranking_basis_none(monkeypatch):
    """Outer exception handler (e.g. DB connection failure): degraded envelope
    must still include ranking_basis (as None), not omit the key entirely --
    this exact path was missed on the first pass of the 2026-07-21 fix."""
    async def _raise_get_postgres_client():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("services.read_only.stable.get_postgres_client", _raise_get_postgres_client)

    result = asyncio.run(stable_svc.get_theme_members("Software Infrastructure", top=5, bottom=5))

    assert "ranking_basis" in result
    assert result["ranking_basis"] is None
    assert result["degraded"] is True


def test_outside_rth_skips_overlay_and_reports_close_basis(monkeypatch):
    """No overlay at all (outside RTH): same nightly-ranked contract, close basis."""
    latest, rows = _roster(12)
    pool = _mock_pool(latest, rows)

    monkeypatch.setattr("services.read_only.stable.get_postgres_client", AsyncMock(return_value=pool))
    monkeypatch.setattr("stable_engine.job_status.is_market_hours", lambda: False)

    result = asyncio.run(stable_svc.get_theme_members("Software Infrastructure", top=5, bottom=5))

    expected_top = [r["ticker"] for r in rows[:5]]
    expected_bottom = [r["ticker"] for r in rows[-5:][::-1]]
    assert [m["ticker"] for m in result["top"]] == expected_top
    assert [m["ticker"] for m in result["bottom"]] == expected_bottom
    assert result["ranking_basis"] == f"close@{latest}"
    assert result["anchor"] == "close"
