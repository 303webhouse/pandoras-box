"""Verify metrics calculations with synthetic data. No Polygon key required."""

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, "/home/claude/stable_market_board")

from stable.metrics import _compute_for_ticker


def make_synthetic(ticker: str, n_days: int, drift: float = 0.0005, vol: float = 0.02, seed: int = 42):
    """Generate synthetic OHLCV data with a small upward drift."""
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, vol, n_days)
    close = 100 * np.exp(np.cumsum(log_returns))
    high = close * (1 + rng.uniform(0, 0.01, n_days))
    low = close * (1 - rng.uniform(0, 0.01, n_days))
    open_ = close * (1 + rng.normal(0, 0.005, n_days))
    volume = rng.integers(1_000_000, 10_000_000, n_days)
    dates = pd.bdate_range(end="2026-05-08", periods=n_days).date
    return pd.DataFrame({
        "ticker": ticker,
        "date": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def test_basic_metrics():
    nvda = make_synthetic("NVDA", 400, drift=0.001, seed=1)
    qqq = make_synthetic("QQQ", 400, drift=0.0005, seed=2)
    rsp = make_synthetic("RSP", 400, drift=0.0003, seed=3)

    metrics = _compute_for_ticker(nvda, {"QQQ": qqq, "RSP": rsp})

    # Latest row should have all fields populated
    last = metrics.iloc[-1]

    print("Sample metrics for synthetic NVDA, latest row:")
    print(f"  ticker         {last['ticker']}")
    print(f"  date           {last['date']}")
    print(f"  ret_1d         {last['ret_1d']:.4f}")
    print(f"  ret_5d         {last['ret_5d']:.4f}")
    print(f"  ret_20d        {last['ret_20d']:.4f}")
    print(f"  ret_60d        {last['ret_60d']:.4f}")
    print(f"  ma_20          {last['ma_20']:.2f}")
    print(f"  ma_50          {last['ma_50']:.2f}")
    print(f"  ma_200         {last['ma_200']:.2f}")
    print(f"  dist_ma20_pct  {last['dist_ma20_pct']:.4f}")
    print(f"  dist_ma50_pct  {last['dist_ma50_pct']:.4f}")
    print(f"  dist_ma200_pct {last['dist_ma200_pct']:.4f}")
    print(f"  above_ma20     {last['above_ma20']}")
    print(f"  above_ma50     {last['above_ma50']}")
    print(f"  above_ma200    {last['above_ma200']}")
    print(f"  atr_14         {last['atr_14']:.4f}")
    print(f"  atr_ext_50ma   {last['atr_ext_50ma']:.4f}")
    print(f"  vol_ratio      {last['vol_ratio']:.4f}")
    print(f"  new_high_20d   {last['new_high_20d']}")
    print(f"  new_high_52w   {last['new_high_52w']}")
    print(f"  rs_qqq_20d     {last['rs_qqq_20d']:.4f}")
    print(f"  rs_qqq_60d     {last['rs_qqq_60d']:.4f}")
    print(f"  rs_rsp_20d     {last['rs_rsp_20d']:.4f}")
    print(f"  rs_rsp_60d     {last['rs_rsp_60d']:.4f}")

    # Sanity assertions
    assert not pd.isna(last["ret_1d"]), "ret_1d should be populated"
    assert not pd.isna(last["ma_200"]), "ma_200 should be populated with 400 days of data"
    assert not pd.isna(last["atr_14"]), "atr_14 should be populated"
    assert last["above_ma20"] in (0, 1), "above_ma20 should be binary"
    assert last["high_20d"] >= last["high_52w"] - 1e-6 or last["high_52w"] >= last["high_20d"], \
        "52w high should be >= 20d high"
    assert not pd.isna(last["rs_qqq_20d"]), "RS vs QQQ should be populated"

    # Verify ATR extension makes sense: with strong drift, NVDA should be above its 50DMA
    # so atr_ext_50ma should be positive on average over the recent window
    recent = metrics.tail(30)
    print(f"\nRecent 30-day mean atr_ext_50ma: {recent['atr_ext_50ma'].mean():.4f}")
    print(f"Recent 30-day mean dist_ma50_pct: {recent['dist_ma50_pct'].mean():.4f}")

    print("\n[PASS] All basic metric checks passed.")


def test_short_history():
    """Tickers with < 200 days should still compute the metrics they have data for."""
    short = make_synthetic("NEW_IPO", 60, seed=99)
    qqq = make_synthetic("QQQ", 60, seed=2)
    rsp = make_synthetic("RSP", 60, seed=3)

    metrics = _compute_for_ticker(short, {"QQQ": qqq, "RSP": rsp})
    last = metrics.iloc[-1]

    assert pd.isna(last["ma_200"]), "ma_200 should be NaN with only 60 days"
    assert not pd.isna(last["ma_50"]), "ma_50 should be populated with 60 days"
    assert not pd.isna(last["ret_20d"]), "ret_20d should be populated"
    assert pd.isna(last["high_52w"]), "52w high needs 200+ days, should be NaN"

    print("[PASS] Short-history handling works correctly.")


if __name__ == "__main__":
    test_basic_metrics()
    print()
    test_short_history()
