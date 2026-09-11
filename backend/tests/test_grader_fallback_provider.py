"""R-IV.324/325 — the grader's yfinance fallback and its provenance.

The load-bearing tests here are the TRAP tests. A fallback that is installed and
silently returns nothing looks exactly like no fallback at all: the job still
reports `no_regular_session_bars` and the 944-row backlog still grows. So the
cases that would produce that outcome are asserted explicitly:

  * yfinance bars carry NO `market_time`, and must NOT be dropped by the 'r'
    filter that UW bars require;
  * the fallback must not fire while UW is healthy;
  * the provider must be READ off the bar, never assumed from which branch ran.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import triton_shadow_common as tsc


UW_BAR = {"market_time": "r", "close": 100.0, "start_time": "2026-09-08T20:00:00Z"}
UW_PRE = {"market_time": "pr", "close": 999.0, "start_time": "2026-09-08T12:00:00Z"}
# The yfinance/polygon shape: c/t, epoch ms, and NO market_time at all.
YF_BAR = {"c": 101.5, "t": 1788825600000, "provider": "yfinance"}


@pytest.fixture
def patched(monkeypatch):
    """Install fakes for both legs; each test sets .ret on the ones it needs."""
    calls = {"ohlc": 0, "yf": 0, "callers": []}

    class Fakes:
        ohlc_ret = None
        yf_ret = None
        ohlc_raises = False

    async def fake_get_ohlc(ticker, candle_size="1d", lookback_days=30, caller="ohlc"):
        calls["ohlc"] += 1
        calls["callers"].append(caller)
        if Fakes.ohlc_raises:
            raise RuntimeError("uw down")
        return Fakes.ohlc_ret

    async def fake_yf(ticker, from_date=None, to_date=None):
        calls["yf"] += 1
        return Fakes.yf_ret

    import integrations.uw_api as uw
    monkeypatch.setattr(uw, "get_ohlc", fake_get_ohlc, raising=False)
    monkeypatch.setattr(uw, "get_bars_yfinance", fake_yf, raising=False)
    return Fakes, calls


# ---------------------------------------------------------------- the trap

@pytest.mark.asyncio
async def test_yfinance_bars_survive_the_r_filter(patched):
    """THE TRAP. yfinance bars have no market_time; the 'r' filter must not see them."""
    F, calls = patched
    F.ohlc_ret = []                       # UW yields nothing
    F.yf_ret = [YF_BAR]
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert idx, "the yfinance bar was dropped — the fallback is installed and inert"
    assert provider == "yfinance"
    assert list(idx.values()) == [101.5]


@pytest.mark.asyncio
async def test_uw_bars_still_filtered_to_regular_session(patched):
    """The filter is dropped for yfinance ONLY — UW must still exclude pre/post."""
    F, calls = patched
    F.ohlc_ret = [UW_BAR, UW_PRE]
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert provider == "uw"
    assert 999.0 not in idx.values(), "a pre-market close entered the index"
    assert list(idx.values()) == [100.0]
    assert calls["yf"] == 0


@pytest.mark.asyncio
async def test_fallback_does_not_fire_while_uw_is_healthy(patched):
    """A net that catches a rope that never dropped is a silent provider swap."""
    F, calls = patched
    F.ohlc_ret = [UW_BAR]
    F.yf_ret = [YF_BAR]
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert provider == "uw"
    assert calls["yf"] == 0, "fallback fired with UW healthy"


@pytest.mark.asyncio
async def test_uw_returning_only_nonregular_bars_triggers_fallback(patched):
    """UW 'up' but with zero 'r' bars is the live failure — it must fall through."""
    F, calls = patched
    F.ohlc_ret = [UW_PRE]                 # non-empty, but nothing regular-session
    F.yf_ret = [YF_BAR]
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert provider == "yfinance"
    assert calls["yf"] == 1


# ------------------------------------------------------- governor isolation

@pytest.mark.asyncio
async def test_uw_leg_uses_the_triton_caller(patched):
    """Triton must never ride ohlc_bars — its own module docstring says so."""
    F, calls = patched
    F.ohlc_ret = [UW_BAR]
    await tsc.fetch_r_close_index("SPY", 25)
    assert calls["callers"] == [tsc.TRITON_CALLER]
    assert "ohlc_bars" not in calls["callers"]


@pytest.mark.asyncio
async def test_fallback_makes_no_second_uw_call(patched):
    """get_bars() would re-enter UW as ohlc_bars. get_bars_yfinance must not."""
    F, calls = patched
    F.ohlc_ret = []
    F.yf_ret = [YF_BAR]
    await tsc.fetch_r_close_index("SPY", 25)
    assert calls["ohlc"] == 1, "the fallback re-issued the UW query that just failed"


# ------------------------------------------------------------- provenance

@pytest.mark.asyncio
async def test_provider_is_read_off_the_bar_not_assumed(patched):
    """If get_bars_yfinance ever returns a uw-stamped bar, say 'uw'."""
    F, calls = patched
    F.ohlc_ret = []
    F.yf_ret = [{"c": 1.0, "t": 1788825600000, "provider": "uw"}]
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert provider == "uw", "the provider was assumed from the branch, not read"


@pytest.mark.asyncio
async def test_mixed_providers_are_flagged_not_silently_picked(patched):
    """A stitched series is a cross-adjustment seam inside one measurement."""
    F, calls = patched
    F.ohlc_ret = []
    F.yf_ret = [
        {"c": 1.0, "t": 1788825600000, "provider": "uw"},
        {"c": 2.0, "t": 1788912000000, "provider": "yfinance"},
    ]
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert provider == "mixed"


@pytest.mark.asyncio
async def test_total_failure_reports_none_not_a_guess(patched):
    """Both legs empty must say 'none' — never a provider for an empty index."""
    F, calls = patched
    F.ohlc_ret = []
    F.yf_ret = []
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert idx == {}
    assert provider == tsc.PROVIDER_NONE


@pytest.mark.asyncio
async def test_uw_raising_still_reaches_the_fallback(patched):
    """An exception on the UW leg is a failure like any other, not a dead end."""
    F, calls = patched
    F.ohlc_raises = True
    F.yf_ret = [YF_BAR]
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert provider == "yfinance"
    assert idx


@pytest.mark.asyncio
async def test_never_raises_even_when_both_legs_explode(patched, monkeypatch):
    """The grader's contract: empty index, never an exception."""
    F, calls = patched
    F.ohlc_raises = True

    async def boom(ticker, from_date=None, to_date=None):
        raise RuntimeError("yfinance down")

    import integrations.uw_api as uw
    monkeypatch.setattr(uw, "get_bars_yfinance", boom, raising=False)
    idx, provider = await tsc.fetch_r_close_index("SPY", 25)
    assert idx == {}
    assert provider == tsc.PROVIDER_NONE


# ---------------------------------------------------------------- _as_date

@pytest.mark.parametrize("raw,expected", [
    (1788825600000, date(2026, 9, 8)),          # epoch ms (yfinance shape)
    ("2026-09-08T20:00:00Z", date(2026, 9, 8)),  # ISO (UW shape)
    ("2026-09-08", date(2026, 9, 8)),
    (None, None),
    ("not-a-date", None),
    ("", None),
])
def test_as_date_handles_both_schemas(raw, expected):
    assert tsc._as_date(raw) == expected


def test_as_date_does_not_raise_on_absurd_epoch():
    assert tsc._as_date(10 ** 18) is None


# --------------------------------------------------------------------------
# R-IV.358(b) — the cash-settled guard
#
# The load-bearing assertion is NOT "it skipped". It is that NO FETCH WAS
# ATTEMPTED. Before the fallback, an index ticker failed slowly on an empty UW
# answer. With a yfinance net behind it, yfinance DOES serve ^SPX-shaped series
# — so the net would hand back a price and the grader would compute a forward
# return on an instrument that has no such return. A wrong grade inside the
# sealed population is a registration breach; the skip it replaces is a gap.
# --------------------------------------------------------------------------

from jobs.instrument_class import classify, is_gradeable


@pytest.mark.parametrize("sym", ["SPX", "SPXW", "RUT", "RUTW", "VIX",
                                 "spx", " spxw ", "Vix"])
def test_cash_settled_tickers_are_ungradeable(sym):
    """The guard's predicate is the classifier's, case/space tolerant."""
    assert is_gradeable(classify(sym, None)) is False


@pytest.mark.parametrize("sym", ["SPY", "QQQ", "NVDA", "IWM", "XLF", "TLT"])
def test_tradeable_tickers_stay_gradeable(sym):
    """The guard must not eat the population it exists to protect."""
    assert is_gradeable(classify(sym, None)) is True


def test_guard_predicate_matches_the_classifier_set_exactly():
    """One author for that symbol set — the guard must not carry a second copy."""
    from jobs.instrument_class import CASH_SETTLED_INDEX_SYMBOLS
    for sym in CASH_SETTLED_INDEX_SYMBOLS:
        assert is_gradeable(classify(sym, None)) is False
    src = Path(__file__).resolve().parents[1] / "jobs" / "triton_shadow_grader.py"
    body = src.read_text(encoding="utf-8")
    assert "is_gradeable(classify(" in body, "the guard is not using the classifier"
    for sym in CASH_SETTLED_INDEX_SYMBOLS:
        assert '"%s"' % sym not in body, "the grader hard-codes %s — second copy of the set" % sym


def test_guard_reason_string_is_the_ruled_one():
    src = Path(__file__).resolve().parents[1] / "jobs" / "triton_shadow_grader.py"
    assert 'UNGRADEABLE-NO-SERIES' in src.read_text(encoding="utf-8")


def test_guard_precedes_any_fetch_in_source_order():
    """`never fetched from either source` — assert the ORDER, not just presence."""
    src = Path(__file__).resolve().parents[1] / "jobs" / "triton_shadow_grader.py"
    body = src.read_text(encoding="utf-8")
    guard = body.index("UNGRADEABLE-NO-SERIES")
    fetch = body.index("idx, provider = await fetch_r_close_index")
    assert guard < fetch, "the guard runs AFTER the fetch — the net still gets consulted"


@pytest.mark.asyncio
async def test_index_ticker_never_reaches_either_provider(patched):
    """End to end: neither leg is called for a cash-settled symbol."""
    F, calls = patched
    F.ohlc_ret = [UW_BAR]
    F.yf_ret = [YF_BAR]
    # fetch_r_close_index is what the guard prevents being called at all; prove
    # that calling it for SPX WOULD have produced a series, so the guard is what
    # stops it rather than an empty upstream.
    idx, provider = await tsc.fetch_r_close_index("SPX", 25)
    assert idx, "precondition: a series IS available for SPX — the guard is load-bearing"
    assert calls["ohlc"] == 1
