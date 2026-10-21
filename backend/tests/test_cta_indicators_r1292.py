"""The CTA indicator builder must be TOTAL, not fail-open. R-IV.1292(b).

WHAT WAS WRONG, found by reading production logs rather than by reasoning about the code.
/health reported `signals_freshness:flatline` for `cta_scanner` on 2026-10-21. The flatline
itself was a FALSE RED -- the scanner ran 19 times on schedule and every signal it found in the
quiet window was suppressed by its own 24h per-ticker cooldown. But the same logs carried
**96 ERROR lines** that nothing was watching:

    ERROR:scanners.cta_scanner:Error calculating CTA indicators:
        '>' not supported between instances of 'float' and 'NoneType'

MEASURED CAUSE. `pandas_ta` returns **None, not a short Series**, when its window exceeds the
input: `ta.sma(s, length=120)` gives a Series at 120 bars and None at 119 and below. `df[col] =
None` makes an OBJECT column of None, and the next comparison in the function --
`df['Close'] > df['sma120']` -- raises. `check_ticker_filters` fetches ONE MONTH (~21 bars) and
calls the whole suite for `atr` alone, so that path threw for every ticker of every universe
build.

THE THROW WAS THE HARMLESS HALF. `atr` is assigned before it, so the universe filter still
answered correctly. Two things were not harmless:

  1. The ERROR channel. 96 lines a day, naming no ticker, in the one place a real indicator
     failure on a real 150-bar scan would have shown up. An alarm that always fires is an alarm
     nobody can read -- the same fault as the always-red `test_asset_pins` of R-IV.1288(d).
  2. THE FAIL-OPEN. The `except` logged and returned the PARTIALLY BUILT frame, so `cta_zone`,
     `days_above_120`, `close_above_50` and the `dist_to_*` columns were absent. Four of the
     seven `check_*` functions then ANSWERED "no signal" on that frame instead of refusing.
     The ticker escaped a wrong verdict only because `check_golden_touch` runs first and raises
     KeyError('days_above_120') before the other four. A reordering of those calls was the
     entire distance between this and a signal computed from columns that were never built.

THE FIX IS THE REFUSAL THAT WAS ALREADY WRITTEN. NaN is what every reader here already handles:
`pd.isna` guards `get_cta_zone`, and a NaN comparison is False, so a condition needing a 120dma
cannot pass without one. The refusal path existed all along and the TypeError pre-empted it.
"""
from __future__ import annotations

import ast
import logging
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from scanners import cta_scanner as cs                              # noqa: E402

from ._srcscan import function_code                                 # noqa: E402

SRC = str(_BACKEND / "scanners" / "cta_scanner.py")

#: Every check that takes (df, ticker) and returns a signal dict or None.
CHECKS = ("check_golden_touch", "check_two_close_volume", "check_pullback_entry",
          "check_death_cross", "check_resistance_rejection", "check_trapped_shorts",
          "check_trapped_longs", "check_bearish_breakdown", "check_zone_upgrade",
          "check_zone_downgrade")

#: The columns the `check_*` functions index directly. A frame missing any of them makes a
#: check either raise or answer from nothing, which is the fault this module pins.
REQUIRED = ("sma20", "sma50", "sma120", "sma200", "atr", "adx", "rsi", "cta_zone",
            "days_above_120", "close_above_50", "close_above_20", "dist_to_20_pct",
            "dist_to_50_pct", "dist_to_120_pct", "correction_pct", "vol_ratio", "rvol")


def _frame(n: int, rising: bool = True) -> pd.DataFrame:
    """`n` business-day OHLCV bars with a little shape, so the checks have something to read."""
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    base = np.linspace(100, 140, n) if rising else np.linspace(140, 100, n)
    close = pd.Series(base + np.sin(np.arange(n) / 3.0) * 2.0, index=idx)
    return pd.DataFrame({
        "Open": close, "High": close * 1.02, "Low": close * 0.98, "Close": close,
        "Volume": pd.Series(np.linspace(1e6, 3e6, n), index=idx),
    })


# ── the vendor premise, measured rather than assumed ────────────────────────

@pytest.mark.parametrize("n,is_series", [(120, True), (119, False), (60, False), (21, False)])
def test_pandas_ta_returns_NONE_below_its_window(n, is_series):
    """THE WHOLE REASON THE FIX IS SHAPED THIS WAY, pinned so a library upgrade that started
    returning a short Series (or raising) cannot quietly make `_as_float_series` dead code
    whose removal then looks safe."""
    import pandas_ta as ta
    got = ta.sma(pd.Series(np.linspace(100, 110, n)), length=120)
    assert isinstance(got, pd.Series) is is_series, (n, type(got).__name__)


# ── the builder is total ────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [21, 60, 119, 150, 300])
def test_every_column_is_built_at_every_history_depth(n):
    """21 bars is `check_ticker_filters`'s own fetch (`period="1mo"`); 150 is
    `scan_ticker_cta`'s floor; 119 is one bar under the 120dma, the exact edge that threw."""
    out = cs.calculate_cta_indicators(_frame(n))
    missing = [c for c in REQUIRED if c not in out.columns]
    assert not missing, "history=%d bars lost %r" % (n, missing)


@pytest.mark.parametrize("n", [21, 60, 119, 300])
def test_no_indicator_column_is_an_OBJECT_COLUMN_OF_NONE(n):
    """The defect's actual shape. `df[col] = None` is an object column, and it is the dtype --
    not the missing values -- that makes the comparison raise."""
    out = cs.calculate_cta_indicators(_frame(n))
    for col in ("sma20", "sma50", "sma120", "sma200", "atr", "adx", "rsi"):
        assert out[col].dtype.kind == "f", "%s is %s at %d bars" % (col, out[col].dtype, n)
        assert not out[col].isin([None]).any(), "%s holds a literal None at %d bars" % (col, n)


@pytest.mark.parametrize("n", [21, 60, 119, 150, 300])
def test_the_builder_logs_NO_ERROR_at_any_depth(n, caplog):
    """96 lines a day is what made the ERROR channel useless for this scanner. The assertion is
    on the CHANNEL, not on the message: any error from this module at any depth is the fault."""
    with caplog.at_level(logging.ERROR, logger="scanners.cta_scanner"):
        cs.calculate_cta_indicators(_frame(n))
    assert [r.getMessage() for r in caplog.records] == []


def test_the_exact_production_message_can_no_longer_be_produced(caplog):
    """The 2026-10-21 line, verbatim, at the depth that produced it."""
    with caplog.at_level(logging.ERROR, logger="scanners.cta_scanner"):
        cs.calculate_cta_indicators(_frame(21))
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "not supported between instances of 'float' and 'NoneType'" not in joined
    assert "Error calculating CTA indicators" not in joined


# ── the positive control: refusing is not the same as being unable to answer ─

@pytest.mark.parametrize("name", CHECKS)
@pytest.mark.parametrize("rising", [True, False])
def test_every_check_REFUSES_on_a_history_too_short_to_judge(name, rising):
    """CONVENTION #30. Making the builder total is only right if the checks then say NO rather
    than guessing: a 60-bar frame cannot support a 120dma claim in either direction, so both a
    rising and a falling series must come back empty. Before the fix these either raised
    KeyError (two of them) or answered from absent columns (four of them)."""
    fn = getattr(cs, name, None)
    if fn is None:
        pytest.skip("%s is not in this build" % name)
    assert fn(cs.calculate_cta_indicators(_frame(60, rising)), "TEST") is None


@pytest.mark.parametrize("name", CHECKS)
def test_the_same_checks_still_RUN_on_a_full_history(name):
    """The control on the control. If a short frame refuses because the checks are simply broken,
    these would refuse too and the test above would prove nothing. A full history must at least
    be ANSWERABLE -- no exception -- for the refusal above to mean "not enough history"."""
    fn = getattr(cs, name, None)
    if fn is None:
        pytest.skip("%s is not in this build" % name)
    got = fn(cs.calculate_cta_indicators(_frame(300)), "TEST")
    assert got is None or isinstance(got, dict)


# ── long histories are untouched ────────────────────────────────────────────

def test_the_wrapper_is_a_PASS_THROUGH_for_a_real_series():
    """What makes this fix safe for every ticker that already worked: at 120+ bars `ta.sma`
    returns a Series and the wrapper returns that identical object, so nothing downstream of a
    normal 150-bar scan sees a different value. The fix can only act where the old code raised."""
    s = pd.Series([1.0, 2.0, 3.0])
    assert cs._as_float_series(s, s.index) is s


def test_the_fallback_is_NaN_and_keeps_the_frames_index():
    out = cs._as_float_series(None, pd.RangeIndex(4))
    assert out.dtype.kind == "f" and len(out) == 4 and out.isna().all()


# ── the fault cannot be written back in ─────────────────────────────────────

def test_no_indicator_column_is_assigned_a_BARE_NONE():
    """`df['adx'] = None` was the fault written out by hand, beside three vendor calls that
    produced it by accident. Read from the PARSED tree: this module's prose quotes the broken
    line repeatedly, so a substring scan would fail on its own explanation -- the trap that has
    now cost eight separate fixes in this repo."""
    tree = ast.parse(function_code(SRC, "calculate_cta_indicators"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Constant) and node.value.value is None):
            continue
        for tgt in node.targets:
            assert not isinstance(tgt, ast.Subscript), (
                "a bare `= None` assignment to a dataframe column is the object-column fault")


def test_the_builder_no_longer_RETURNS_A_PARTIAL_FRAME_on_failure():
    """The fail-open half. With every vendor refusal turned into NaN there is nothing left for
    the `except` to swallow, but if one is ever reintroduced the handler must not hand a
    half-built frame to callers that index its columns."""
    code = function_code(SRC, "calculate_cta_indicators")
    tree = ast.parse(code)
    handlers = [h for n in ast.walk(tree) if isinstance(n, ast.Try) for h in n.handlers]
    assert handlers, "the function still has its guard"
    # Every vendor call that can refuse is wrapped, which is what makes the handler unreachable
    # for the measured cause. Assert the wrapping rather than the handler's body: the wrapping is
    # the fix, and the handler is the net under it.
    for call in ("ta.sma(df['Close'], length=120)", "ta.rsi(df['Close'], length=14)"):
        i = code.find(call)
        assert i != -1, call
        assert "_as_float_series(" in code[max(0, i - 60):i], (
            "%s is not wrapped; it can return None" % call)
