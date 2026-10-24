"""The greeks recompute on the 15-minute loop, and count real legs. R-IV.1381(d).

(d)1 THE 24-HOUR COPY WAS A SHORT CIRCUIT. `_portfolio_greeks_inner` read
`portfolio:greeks:stale` (86400s) BEFORE any recompute and returned it unconditionally, so the
moment that key existed every request for the next day got it. The BOOK tile's "N of M legs"
fraction could not move for 24 hours, and the payload said only `stale: True` -- no date -- so a
reader could not tell this morning's figure from yesterday afternoon's.

(d)2 THE LEG COUNT CAME FROM TWO COLUMNS. `get_ticker_greeks_summary` built a position's legs
from `long_strike` and `short_strike`, with ONE option type inferred from the structure name.
NVDA 415 is a put_debit_spread plus a long_put: three legs, counted as two. Coverage read better
than it was, which is the dangerous direction -- the same reason this module refuses to report
an unknown greek as 0.

VENDOR CALLS, which is (d)3's question. Neither change adds one:

  * the leg change only alters which contracts are looked up INSIDE a chain that is already
    fetched once per ticker;
  * the refresh runs immediately after the mark job in the same 15-minute loop
    (MTM_MINUTES = [2, 17, 32, 47]), and `get_options_snapshot` caches under `option_contracts`
    with a 300s TTL -- so it reads chains seconds old and already paid for.

Before: the chain was fetched when the 24h key lapsed, about once a day.
After: at most once per 15 minutes, and in practice from the mark job's warm cache.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from ._srcscan import read_source                                   # noqa: E402

UP = read_source(str(_BACKEND / "api" / "unified_positions.py"))
MAIN = read_source(str(_BACKEND / "main.py"))
UW = read_source(str(_BACKEND / "integrations" / "uw_api.py"))


def _fn(src, name):
    i = src.index(name)
    j = src.find("\nasync def ", i + 10)
    k = src.find("\ndef ", i + 10)
    end = min(x for x in (j, k, len(src)) if x > 0)
    return src[i:end]


def _nocomments(s):
    """Comments AND docstrings.

    The 17th firing of this trap in one session, and the first through a DOCSTRING: the
    fix's own docstring quotes the removed redis.get(...stale) call to explain what went,
    so stripping only # lines left the explanation there for the scan to match. Memory
    records exactly this -- ast.unparse drops comments but KEEPS docstrings.
    """
    s = re.sub(r'"""(?:.|\n)*?"""', '', s)
    s = re.sub(r"'''(?:.|\n)*?'''", "", s)
    return re.sub(r"#[^\n]*", "", s)


# ── (d)1 the stale copy is a fallback ───────────────────────────────────────

def test_the_STALE_KEY_IS_NOT_READ_BEFORE_A_RECOMPUTE():
    """Comments stripped: the fix's own comment quotes the removed read."""
    body = _nocomments(_fn(UP, "async def _portfolio_greeks_inner("))
    head = body[:body.index("_stale_fallback")] if "_stale_fallback" in body else body
    assert "portfolio:greeks:stale" not in head, "the 24h key is being read before recomputing"


def test_the_stale_fallback_EXISTS_and_is_used_on_failure():
    body = _fn(UP, "async def _portfolio_greeks_inner(")
    assert "_stale_fallback" in body
    assert body.count("await _stale_fallback(") >= 2, "every failure path must try it"


def test_the_stale_copy_CARRIES_ITS_OWN_AS_OF():
    """`stale: True` alone says "old" without saying how old."""
    body = _fn(UP, "async def _portfolio_greeks_inner(")
    assert 'data["as_of"] = data.get("computed_at")' in body
    assert 'data["stale_reason"]' in body


def test_a_FRESH_result_is_stamped_and_marked_not_stale():
    body = _fn(UP, "async def _portfolio_greeks_inner(")
    assert '"computed_at": datetime.now(timezone.utc).isoformat()' in body
    assert '"stale": False' in body


def test_FORCE_skips_the_sixty_second_cache():
    body = _fn(UP, "async def _portfolio_greeks_inner(")
    assert "force: bool = False" in body
    assert "if redis and not force:" in body


def test_the_FIFTEEN_MINUTE_LOOP_refreshes_them():
    """(d)1: "Recompute from the existing 15-minute loop." Not on the request path -- that
    would put a vendor-backed computation behind every page load."""
    assert "_portfolio_greeks_inner(force=True)" in MAIN
    i = MAIN.index("result = await run_mark_to_market()")
    j = MAIN.index("_portfolio_greeks_inner(force=True)")
    assert i < j, "the refresh must follow the mark job, to reuse its warm chain cache"
    assert "MTM_MINUTES = [2, 17, 32, 47]" in MAIN


def test_a_failed_refresh_NEVER_fails_the_mark_run():
    """The greeks are display-only (#42). The marks are the money."""
    i = MAIN.index("_portfolio_greeks_inner(force=True)")
    block = MAIN[i - 400:i + 600]
    assert "try:" in block and "except Exception" in block


# ── (d)2 real legs ──────────────────────────────────────────────────────────

def test_the_summariser_PREFERS_the_real_legs():
    body = _fn(UW, "async def get_ticker_greeks_summary(")
    assert '_legs = pos.get("legs") or []' in body
    assert "if _legs:" in body


def test_the_greeks_route_READS_position_legs():
    assert "FROM position_legs WHERE position_id = ANY($1::text[])" in UP
    i = UP.index("async def _portfolio_greeks_inner(")
    j = UP.index("\nasync def ", i + 10)
    assert "FROM position_legs" in UP[i:j], "the greeks route must read the legs table itself"


def test_an_UNREADABLE_legs_table_is_SAID_not_silently_undercounted():
    body = _fn(UP, "async def _portfolio_greeks_inner(")
    assert "UNDERSTATE" in body


@pytest.mark.asyncio
async def test_a_THREE_LEG_position_counts_THREE(monkeypatch):
    """NVDA 415's shape: a put spread plus a long put. Two strike columns cannot express it."""
    from integrations import uw_api

    chain = [
        {"details": {"strike_price": 415.0, "expiration_date": "2026-11-20",
                     "contract_type": "put"},
         "greeks": {"delta": -0.4, "gamma": 0.01, "theta": -0.05, "vega": 0.1}},
        {"details": {"strike_price": 400.0, "expiration_date": "2026-11-20",
                     "contract_type": "put"},
         "greeks": {"delta": -0.2, "gamma": 0.01, "theta": -0.03, "vega": 0.08}},
        {"details": {"strike_price": 380.0, "expiration_date": "2026-11-20",
                     "contract_type": "put"},
         "greeks": {"delta": -0.1, "gamma": 0.01, "theta": -0.02, "vega": 0.05}},
    ]
    calls = []

    async def _snap(underlying, **kw):
        calls.append(underlying)
        return chain

    monkeypatch.setattr(uw_api, "get_options_snapshot", _snap)

    pos = {"ticker": "NVDA", "structure": "put_debit_spread", "quantity": 1,
           "expiry": "2026-11-20", "long_strike": 415.0, "short_strike": 400.0,
           "legs": [
               {"option_type": "put", "side": "long", "strike": 415.0,
                "expiry": "2026-11-20", "qty": 1},
               {"option_type": "put", "side": "short", "strike": 400.0,
                "expiry": "2026-11-20", "qty": 1},
               {"option_type": "put", "side": "long", "strike": 380.0,
                "expiry": "2026-11-20", "qty": 1},
           ]}
    out = await uw_api.get_ticker_greeks_summary("NVDA", [pos])
    assert out["legs_expected"] == 3, out
    assert out["legs_priced"] == 3, out
    assert len(calls) == 1, "ONE chain fetch per ticker -- legs add no vendor call"


@pytest.mark.asyncio
async def test_WITHOUT_legs_the_strike_pair_still_works(monkeypatch):
    """Nothing that works today stops working: a position with no leg rows keeps the old path."""
    from integrations import uw_api

    chain = [
        {"details": {"strike_price": 415.0, "expiration_date": "2026-11-20",
                     "contract_type": "put"},
         "greeks": {"delta": -0.4, "gamma": 0.01, "theta": -0.05, "vega": 0.1}},
        {"details": {"strike_price": 400.0, "expiration_date": "2026-11-20",
                     "contract_type": "put"},
         "greeks": {"delta": -0.2, "gamma": 0.01, "theta": -0.03, "vega": 0.08}},
    ]

    async def _snap(underlying, **kw):
        return chain

    monkeypatch.setattr(uw_api, "get_options_snapshot", _snap)
    pos = {"ticker": "NVDA", "structure": "put_debit_spread", "quantity": 1,
           "expiry": "2026-11-20", "long_strike": 415.0, "short_strike": 400.0}
    out = await uw_api.get_ticker_greeks_summary("NVDA", [pos])
    assert out["legs_expected"] == 2
    assert out["legs_priced"] == 2


@pytest.mark.asyncio
async def test_a_SHORT_leg_subtracts(monkeypatch):
    """Side comes from the leg row, not from the structure's name."""
    from integrations import uw_api

    chain = [{"details": {"strike_price": 100.0, "expiration_date": "2026-11-20",
                          "contract_type": "call"},
              "greeks": {"delta": 0.5, "gamma": 0.0, "theta": 0.0, "vega": 0.0}}]

    async def _snap(underlying, **kw):
        return chain

    monkeypatch.setattr(uw_api, "get_options_snapshot", _snap)
    long_p = {"ticker": "X", "structure": "long_call", "quantity": 1, "expiry": "2026-11-20",
              "legs": [{"option_type": "call", "side": "long", "strike": 100.0,
                        "expiry": "2026-11-20", "qty": 1}]}
    short_p = {"ticker": "X", "structure": "long_call", "quantity": 1, "expiry": "2026-11-20",
               "legs": [{"option_type": "call", "side": "short", "strike": 100.0,
                         "expiry": "2026-11-20", "qty": 1}]}
    a = await uw_api.get_ticker_greeks_summary("X", [long_p])
    b = await uw_api.get_ticker_greeks_summary("X", [short_p])
    assert a["net_delta"] == -b["net_delta"] != 0, (a["net_delta"], b["net_delta"])


@pytest.mark.asyncio
async def test_an_UNPRICEABLE_leg_is_a_GAP_not_a_non_event(monkeypatch):
    """A leg the chain cannot price counts as EXPECTED. Dropping it silently would make
    coverage read complete while a real leg is missing from the sum."""
    from integrations import uw_api

    async def _snap(underlying, **kw):
        return []

    monkeypatch.setattr(uw_api, "get_options_snapshot", _snap)
    pos = {"ticker": "X", "structure": "long_call", "quantity": 1, "expiry": "2026-11-20",
           "legs": [{"option_type": "call", "side": "long", "strike": 100.0,
                     "expiry": "2026-11-20", "qty": 1},
                    {"option_type": None, "side": "long", "strike": None,
                     "expiry": None, "qty": 1}]}
    out = await uw_api.get_ticker_greeks_summary("X", [pos])
    assert out["legs_expected"] == 2
    assert out["legs_priced"] == 0
