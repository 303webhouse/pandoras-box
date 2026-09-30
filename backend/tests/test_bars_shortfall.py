"""A partial answer is not an answer — R-IV.599(d).

2026-09-29 landed in `stable_daily_bars` for 2 of 679 tickers; 2026-09-22 for 135. FANUY survived
both times, which is the tell: the vendor returned a frame holding a couple of symbols and
`fetch_batch` handed that back as the batch's result.

The backfill run that repaired 09-29 had no shortfall, so it did not exercise either new branch.
These do.
"""

import pandas as pd
import pytest

from stable_engine import bars_yf


def _frame():
    return pd.DataFrame({"date": [pd.Timestamp("2026-09-29").date()],
                         "o": [1.0], "h": [2.0], "l": [0.5], "c": [1.5], "v": [10]})


class TestAShortfallIsAFailedAttempt:

    def test_a_thin_first_answer_is_retried(self, monkeypatch):
        """THE FAULT. `return out` sat inside the `try`, so a call that succeeded but returned a
        near-empty frame raised nothing and returned on attempt 1. The retry never ran."""
        calls = []
        tickers = [f"T{i}" for i in range(10)]

        def fake(yahoo, tick, start, end):
            calls.append(len(tick))
            if len(calls) == 1:
                return {"T0": _frame()}                  # 1 of 10 — the 09-29 shape
            return {t: _frame() for t in tick}           # the retry answers properly

        monkeypatch.setattr(bars_yf, "_download_batch", fake)
        out = bars_yf.fetch_batch(tickers, None, None)
        assert len(out) == 10
        assert calls[:2] == [10, 10], calls            # it asked AGAIN, for the whole batch

    def test_a_full_first_answer_is_not_retried(self, monkeypatch):
        """POSITIVE CONTROL: the retry is narrow. A good batch still costs one call."""
        calls = []
        tickers = [f"T{i}" for i in range(10)]

        def fake(yahoo, tick, start, end):
            calls.append(len(tick))
            return {t: _frame() for t in tick}

        monkeypatch.setattr(bars_yf, "_download_batch", fake)
        assert len(bars_yf.fetch_batch(tickers, None, None)) == 10
        assert calls == [10]

    def test_the_best_attempt_is_kept_when_both_are_thin(self, monkeypatch):
        """Two thin answers must not lose the better one. Before, the second attempt's result
        replaced the first wholesale."""
        tickers = [f"T{i}" for i in range(10)]
        answers = [{"T0": _frame(), "T1": _frame(), "T2": _frame()}, {"T0": _frame()}]

        def fake(yahoo, tick, start, end):
            return answers.pop(0) if answers else {}

        monkeypatch.setattr(bars_yf, "_download_batch", fake)
        out = bars_yf.fetch_batch(tickers, None, None)
        assert {"T0", "T1", "T2"} <= set(out)


class TestOneBadSymbolDoesNotTakeTheBatch:

    def test_stragglers_are_asked_alone(self, monkeypatch):
        """A batch that raised twice used to return {}, abandoning all 100 tickers without ever
        asking whether one bad symbol had taken 99 with it."""
        tickers = [f"T{i}" for i in range(5)]
        singles = []

        def fake(yahoo, tick, start, end):
            if len(tick) > 1:
                raise RuntimeError("vendor said no")
            singles.append(tick[0])
            if tick[0] == "T3":
                raise RuntimeError("this one really is bad")
            return {tick[0]: _frame()}

        monkeypatch.setattr(bars_yf, "_download_batch", fake)
        monkeypatch.setattr(bars_yf.time, "sleep", lambda *_: None)
        out = bars_yf.fetch_batch(tickers, None, None)
        assert sorted(out) == ["T0", "T1", "T2", "T4"]     # four of five recovered
        assert sorted(singles) == tickers                  # and every one was asked
        assert "T3" not in out                             # the genuinely bad one is absent

    def test_the_serial_fallback_is_capped(self, monkeypatch):
        """A total vendor outage must degrade, not turn into 679 sequential requests."""
        tickers = [f"T{i}" for i in range(bars_yf._MAX_SINGLE_RETRIES + 25)]
        singles = []

        def fake(yahoo, tick, start, end):
            if len(tick) > 1:
                raise RuntimeError("outage")
            singles.append(tick[0])
            raise RuntimeError("still out")

        monkeypatch.setattr(bars_yf, "_download_batch", fake)
        monkeypatch.setattr(bars_yf.time, "sleep", lambda *_: None)
        assert bars_yf.fetch_batch(tickers, None, None) == {}
        assert len(singles) == bars_yf._MAX_SINGLE_RETRIES

    def test_a_ticker_that_answered_in_the_batch_is_not_asked_again(self, monkeypatch):
        """FANUY and HUBB answered. Re-asking them would be paying twice for what arrived."""
        tickers = [f"T{i}" for i in range(6)]
        singles = []

        def fake(yahoo, tick, start, end):
            if len(tick) > 1:
                return {"T0": _frame()}          # the survivor
            singles.append(tick[0])
            return {tick[0]: _frame()}

        monkeypatch.setattr(bars_yf, "_download_batch", fake)
        monkeypatch.setattr(bars_yf.time, "sleep", lambda *_: None)
        out = bars_yf.fetch_batch(tickers, None, None)
        assert len(out) == 6
        assert "T0" not in singles


def test_an_empty_request_costs_nothing(monkeypatch):
    called = []
    monkeypatch.setattr(bars_yf, "_download_batch",
                        lambda *a: called.append(1) or {})
    assert bars_yf.fetch_batch([], None, None) == {}
    assert bars_yf.fetch_batch([None, ""], None, None) == {}
    assert not called
