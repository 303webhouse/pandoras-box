"""The chain spot join — TA-160 §2 / R-IV.978(c).

THE DEFECT: `hub_get_options_chain` returned `spot: null` with `greeks_source "bs_computed"`, so
EVERY greek was null, while `hub_get_quote` returned a live spot in the same minute (KRE
2026-12-18, HYG 2026-11-20).

THE CAUSE the old fallback could not survive: it called `get_snapshot()`, which needs a SECOND
UW call (`/ohlc/1d` under caller `ohlc_bars`) for the regular-session change -- and that caller
has been observed governor-BLOCKED at 625/625. `hub_get_quote` succeeds on a single
`/stock-state`, so the chain now reads the same source.
"""
from __future__ import annotations

import asyncio
import inspect
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from services.read_only import options_chain as oc  # noqa: E402

TKR, EXP = "KRE", "2026-12-18"


def _contract(strike, otype="put", with_underlying_price=False):
    c = {
        "details": {"strike_price": strike, "contract_type": otype,
                    "expiration_date": EXP},
        "last_quote": {"bid": 0.20, "ask": 0.28},
        "implied_volatility": 0.37,
        "open_interest": 10,
        "day": {"volume": 5},
    }
    if with_underlying_price:
        c["underlying_asset"] = {"price": 69.0}
    return c


def _run(**kw):
    return asyncio.run(oc.get_options_chain(TKR, expiry=EXP, **kw))


@pytest.fixture
def stubbed(monkeypatch):
    """Chain WITHOUT underlying_asset.price -- the real failing shape."""
    calls = {"stock_state": 0, "snapshot": 0}

    async def fake_chain(ticker, **kw):
        return [_contract(60.0), _contract(65.0)]

    async def fake_request(path, params=None, caller=None, **kw):
        if "stock-state" in path:
            calls["stock_state"] += 1
            return {"data": {"close": "69.065", "tape_time": "2026-10-13T19:59:37Z"}}
        return None

    async def fake_snapshot(ticker):
        calls["snapshot"] += 1
        return {"lastTrade": {"p": 1.23}}      # deliberately wrong, to prove it is not used

    async def no_rank(*a, **k):
        return None

    import integrations.uw_api as uw
    monkeypatch.setattr(oc, "get_options_snapshot", fake_chain)
    monkeypatch.setattr(oc, "get_snapshot", fake_snapshot)
    monkeypatch.setattr(oc, "get_iv_rank", no_rank)
    monkeypatch.setattr(oc, "get_max_pain", no_rank)
    monkeypatch.setattr(uw, "_uw_request", fake_request)
    # bypass the read-through cache so each test exercises the live path
    async def no_cache(*a, **k):
        return None
    monkeypatch.setattr(oc, "cache_get", no_cache)
    async def noop_set(*a, **k):
        return None
    monkeypatch.setattr(oc, "cache_set", noop_set)
    return calls


# ── the spot, sourced exactly as hub_get_quote does ──────────────────────

def test_spot_comes_from_stock_state_when_the_chain_omits_it(stubbed):
    out = _run()
    assert out["spot"] == pytest.approx(69.065)
    assert out["spot_source"] == "stock_state"


def test_the_snapshot_is_NOT_used_when_stock_state_answers(stubbed):
    """The old fallback depended on a call that is frequently governor-blocked. The stub returns
    a deliberately wrong 1.23, so if it were reached the spot would be visibly wrong."""
    out = _run()
    assert out["spot"] != pytest.approx(1.23)
    assert stubbed["snapshot"] == 0


def test_the_chains_own_price_still_WINS_when_present(monkeypatch, stubbed):
    async def chain_with_price(ticker, **kw):
        return [_contract(60.0, with_underlying_price=True)]
    monkeypatch.setattr(oc, "get_options_snapshot", chain_with_price)
    out = _run()
    assert out["spot"] == pytest.approx(69.0)
    assert out["spot_source"] == "chain"
    # SPOT and TIMESTAMP are separate questions. The chain wins for the spot, but this stub's
    # contracts carry no `last_fill`, so stock-state is still consulted for the VENDOR STAMP --
    # which is the point of fix-first #2. An earlier version of this test asserted zero calls
    # and was asserting the wrong thing.
    assert out["uw_timestamp_source"] == "stock_state.tape_time"
    assert stubbed["stock_state"] == 1


def test_a_chain_with_BOTH_a_price_and_a_last_fill_needs_no_extra_call(monkeypatch, stubbed):
    """The genuine no-extra-call case: when the chain answers both questions, nothing else is
    asked."""
    async def chain_complete(ticker, **kw):
        c = _contract(60.0, with_underlying_price=True)
        c["last_fill"] = "2026-10-13T19:58:00Z"
        return [c]
    monkeypatch.setattr(oc, "get_options_snapshot", chain_complete)
    out = _run()
    assert out["spot_source"] == "chain"
    assert out["uw_timestamp_source"] == "last_fill"
    assert stubbed["stock_state"] == 0
    assert stubbed["snapshot"] == 0


# ── the timestamp: the VENDOR's stamp, or an honest statement ────────────

def test_the_timestamp_is_the_vendors_tape_time(stubbed):
    """fix-first #2. `synthetic` presented a SERVER clock under a name that did not say so,
    which is indistinguishable from a vendor reading."""
    out = _run()
    assert out["uw_timestamp"] == "2026-10-13T19:59:37Z"
    assert out["uw_timestamp_source"] == "stock_state.tape_time"


def test_the_word_synthetic_is_no_longer_a_VALUE(stubbed):
    """Read from the parsed tree, because the module's prose explains why it is gone -- a grep
    would match the explanation."""
    import ast

    tree = ast.parse(inspect.getsource(oc))
    doc_nodes = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = getattr(n, "body", None) or []
            if (b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                doc_nodes.add(id(b[0].value))
    live = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in doc_nodes]
    assert "synthetic" not in live


def test_with_no_vendor_stamp_the_field_SAYS_so(monkeypatch, stubbed):
    import integrations.uw_api as uw

    async def no_stamp(path, params=None, caller=None, **kw):
        if "stock-state" in path:
            return {"data": {"close": "69.065"}}        # a price, but no tape_time
        return None
    monkeypatch.setattr(uw, "_uw_request", no_stamp)
    out = _run()
    assert out["spot"] == pytest.approx(69.065)
    src = out["uw_timestamp_source"]
    assert src.startswith("server_time"), src
    assert "NO vendor stamp" in src


# ── honest when there is genuinely no spot ───────────────────────────────

def test_no_spot_anywhere_is_stated_not_silent(monkeypatch, stubbed):
    import integrations.uw_api as uw

    async def nothing(path, params=None, caller=None, **kw):
        return None

    async def no_snap(ticker):
        return None
    monkeypatch.setattr(uw, "_uw_request", nothing)
    monkeypatch.setattr(oc, "get_snapshot", no_snap)
    out = _run()
    assert out["spot"] is None
    assert out["spot_source"].startswith("unavailable")
    # and it names what was asked, so a reader need not guess
    for probe in ("chain", "stock-state", "snapshot"):
        assert probe in out["spot_source"]


# ── the greeks, which are the point of having a spot ────────────────────

def test_greeks_COMPUTE_once_a_spot_exists(stubbed):
    """MEASURED on the real chain after the fix: delta/gamma/theta/vega are non-null on exactly
    the 28 of 128 KRE contracts that carry `implied_volatility` -- IV present and delta present
    28, IV present and delta missing 0. The remaining 100 have no IV at the vendor, which is
    documented behaviour and not a hub defect."""
    out = _run()
    cs = out["contracts"]
    assert cs, "no contracts"
    assert all(c.get("delta") is not None for c in cs), cs[0]
    assert all(c.get("vega") is not None for c in cs)


def test_a_contract_with_no_IV_keeps_null_greeks_and_that_is_correct(monkeypatch, stubbed):
    """The control. A fix that invented greeks without IV would be worse than null ones."""
    async def chain_no_iv(ticker, **kw):
        c = _contract(60.0)
        c.pop("implied_volatility")
        return [c]
    monkeypatch.setattr(oc, "get_options_snapshot", chain_no_iv)
    out = _run()
    assert out["spot"] is not None            # the spot is still found
    assert out["contracts"][0].get("delta") is None


# -- R-IV.1037(c)1: the quote service as the FOURTH spot source ------------------------

def test_the_quote_service_is_the_third_source_inside_spot_now():
    """TA, 2026-10-14T18:29:28Z: AAPL chain spot NULL while hub_get_quote returned 343.11 six
    seconds later. Same endpoint, same field, DIFFERENT caller tag -- so a different quota
    bucket and a different cache entry, which is why one answered and the other did not.
    Added inside `spot_now` rather than in the chain, so the B2 mark path gets it too: one
    author for "the current spot" (R-IV.983(b))."""
    import ast
    import inspect

    from integrations import spot_price

    assert spot_price.SRC_QUOTE == "quote_service"
    src = inspect.getsource(spot_price.spot_now)
    fn = ast.parse(src).body[0]
    doc = fn.body[0].value if fn.body and isinstance(fn.body[0], ast.Expr) else None
    code = chr(10).join(ast.unparse(n) for n in fn.body
                        if not (isinstance(n, ast.Expr) and n.value is doc))
    assert "get_quote" in code, "spot_now does not reach the quote service"
    # ORDER MATTERS: the quote service is the LAST resort, after stock-state and the snapshot.
    assert code.index("stock-state") < code.index("get_snapshot") < code.index("get_quote")


def test_the_unavailable_string_names_ALL_FOUR_sources():
    """A reader told three sources failed will not know a fourth was tried."""
    import inspect

    from integrations import spot_price
    from services.read_only import options_chain

    assert "quote service" in spot_price.SRC_NONE, spot_price.SRC_NONE
    chain_src = inspect.getsource(options_chain)
    assert "snapshot and the quote " in chain_src, "the chain's string still names only three"
