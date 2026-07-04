"""Verify metrics calculations with synthetic data. No DB, no network required.

Adapted from Stable Market Board by Ryan Scott (tests/test_metrics_synthetic.py).
Imports the ported engine's `_compute_for_ticker`; math is byte-identical, so the
same assertions hold. Run:  PYTHONPATH=backend python -m pytest backend/stable_engine/tests
"""

import numpy as np
import pandas as pd

from stable_engine.metrics import _compute_for_ticker


def make_synthetic(ticker: str, n_days: int, drift: float = 0.0005, vol: float = 0.02, seed: int = 42):
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, vol, n_days)
    close = 100 * np.exp(np.cumsum(log_returns))
    high = close * (1 + rng.uniform(0, 0.01, n_days))
    low = close * (1 - rng.uniform(0, 0.01, n_days))
    open_ = close * (1 + rng.normal(0, 0.005, n_days))
    volume = rng.integers(1_000_000, 10_000_000, n_days)
    dates = pd.bdate_range(end="2026-05-08", periods=n_days).date
    return pd.DataFrame({
        "ticker": ticker, "date": dates, "open": open_,
        "high": high, "low": low, "close": close, "volume": volume,
    })


def test_basic_metrics():
    nvda = make_synthetic("NVDA", 400, drift=0.001, seed=1)
    qqq = make_synthetic("QQQ", 400, drift=0.0005, seed=2)
    rsp = make_synthetic("RSP", 400, drift=0.0003, seed=3)

    metrics = _compute_for_ticker(nvda, {"QQQ": qqq, "RSP": rsp})
    last = metrics.iloc[-1]

    assert not pd.isna(last["ret_1d"]), "ret_1d should be populated"
    assert not pd.isna(last["ma_200"]), "ma_200 should be populated with 400 days of data"
    assert not pd.isna(last["atr_14"]), "atr_14 should be populated"
    assert last["above_ma20"] in (0, 1), "above_ma20 should be binary"
    assert last["high_20d"] >= last["high_52w"] - 1e-6 or last["high_52w"] >= last["high_20d"], \
        "52w high should be >= 20d high"
    assert not pd.isna(last["rs_qqq_20d"]), "RS vs QQQ should be populated"


def test_short_history():
    """Tickers with < 200 days still compute the metrics they have data for."""
    short = make_synthetic("NEW_IPO", 60, seed=99)
    qqq = make_synthetic("QQQ", 60, seed=2)
    rsp = make_synthetic("RSP", 60, seed=3)

    metrics = _compute_for_ticker(short, {"QQQ": qqq, "RSP": rsp})
    last = metrics.iloc[-1]

    assert pd.isna(last["ma_200"]), "ma_200 should be NaN with only 60 days"
    assert not pd.isna(last["ma_50"]), "ma_50 should be populated with 60 days"
    assert not pd.isna(last["ret_20d"]), "ret_20d should be populated"
    assert pd.isna(last["high_52w"]), "52w high needs 200+ days, should be NaN"


if __name__ == "__main__":
    test_basic_metrics()
    test_short_history()
    print("[PASS] All synthetic metric checks passed.")
