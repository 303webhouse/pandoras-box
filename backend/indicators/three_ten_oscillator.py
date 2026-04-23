"""
3-10 Oscillator (Linda Raschke canonical)

Mathematical definition:
    midpoint = (high + low) / 2
    raw      = SMA(midpoint, 3) - SMA(midpoint, 10)
    fast     = SMA(raw, 3)
    slow     = SMA(raw, 10)

Outputs four columns appended to the input DataFrame:
    osc_fast  : fast line value per bar
    osc_slow  : slow line value per bar
    osc_cross : +1 if fast crossed ABOVE slow on this bar, -1 if crossed BELOW, 0 otherwise
    osc_div   : +1 for bullish divergence, -1 for bearish divergence, 0 otherwise

Mechanical divergence rule (URSA-locked from Olympus 2026-04-22):
    - Bullish: price makes a new N-bar low, while fast line's corresponding
      pivot low is HIGHER than its prior pivot low by >= threshold.
    - Bearish: price makes a new N-bar high, while fast line's corresponding
      pivot high is LOWER than its prior pivot high by >= threshold.
    - Pivots confirmed via 5-bar window (2 before + pivot + 2 after).
    - Flag fires only when BOTH price pivot and fast-line pivot are confirmed.
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Exported column names — downstream consumers should import these constants,
# not hardcode strings. If we ever rename a column, only this file changes.
OSC_FAST = "osc_fast"
OSC_SLOW = "osc_slow"
OSC_CROSS = "osc_cross"
OSC_DIV = "osc_div"

# Default parameters per Raschke spec.
DEFAULT_DIVERGENCE_LOOKBACK = 5
DEFAULT_DIVERGENCE_THRESHOLD = 0.10  # 10%
PIVOT_WINDOW = 2  # Bars before and after pivot candidate (total window = 5 bars)


def compute_3_10(
    df: pd.DataFrame,
    divergence_lookback: int = DEFAULT_DIVERGENCE_LOOKBACK,
    divergence_threshold: float = DEFAULT_DIVERGENCE_THRESHOLD,
) -> pd.DataFrame:
    """
    Compute the 3-10 Oscillator and append four columns to df.

    Args:
        df: DataFrame with at minimum 'high' and 'low' columns (case-insensitive
            — will try both 'high'/'High' and 'low'/'Low'). DatetimeIndex preferred
            but not required for math; required for divergence pivot detection
            alignment.
        divergence_lookback: N-bar window for new-high/low detection.
        divergence_threshold: Minimum fractional gap between pivots to count as
            divergence (0.10 = 10%).

    Returns:
        The input DataFrame with OSC_FAST, OSC_SLOW, OSC_CROSS, OSC_DIV columns
        appended. Returns df unchanged if it has fewer than 20 bars (not enough
        data for the slow line's 10-bar SMA of the raw line).
    """
    if df is None or df.empty or len(df) < 20:
        # Append empty columns so callers can rely on them existing.
        for col in (OSC_FAST, OSC_SLOW, OSC_CROSS, OSC_DIV):
            df[col] = pd.NA
        return df

    # Resolve column names (support both Yahoo 'High'/'Low' and lowercase).
    high_col = "high" if "high" in df.columns else "High"
    low_col = "low" if "low" in df.columns else "Low"
    if high_col not in df.columns or low_col not in df.columns:
        logger.warning(
            "compute_3_10: missing high/low columns, returning df unchanged"
        )
        for col in (OSC_FAST, OSC_SLOW, OSC_CROSS, OSC_DIV):
            df[col] = pd.NA
        return df

    # Core math
    midpoint = (df[high_col] + df[low_col]) / 2.0
    raw = midpoint.rolling(window=3, min_periods=3).mean() - midpoint.rolling(
        window=10, min_periods=10
    ).mean()

    df[OSC_FAST] = raw.rolling(window=3, min_periods=3).mean()
    df[OSC_SLOW] = raw.rolling(window=10, min_periods=10).mean()

    # Crossover detection: compare current and previous fast-vs-slow sign.
    prev_fast = df[OSC_FAST].shift(1)
    prev_slow = df[OSC_SLOW].shift(1)
    cross_up = (df[OSC_FAST] > df[OSC_SLOW]) & (prev_fast <= prev_slow)
    cross_down = (df[OSC_FAST] < df[OSC_SLOW]) & (prev_fast >= prev_slow)
    df[OSC_CROSS] = 0
    df.loc[cross_up, OSC_CROSS] = 1
    df.loc[cross_down, OSC_CROSS] = -1

    # Mechanical divergence detection
    df[OSC_DIV] = _detect_divergences(
        df=df,
        high_col=high_col,
        low_col=low_col,
        fast_col=OSC_FAST,
        lookback=divergence_lookback,
        threshold=divergence_threshold,
    )

    return df


def _detect_divergences(
    df: pd.DataFrame,
    high_col: str,
    low_col: str,
    fast_col: str,
    lookback: int,
    threshold: float,
) -> pd.Series:
    """
    Mechanical divergence detection using 5-bar pivot confirmation.

    Returns a Series aligned with df, where each value is:
        +1 for bullish divergence on that bar
        -1 for bearish divergence on that bar
         0 otherwise
    """
    result = pd.Series(0, index=df.index, dtype="int8")

    # Identify pivot lows and pivot highs using a 5-bar window.
    price_pivot_lows = _find_pivots(df[low_col], direction="low")
    price_pivot_highs = _find_pivots(df[high_col], direction="high")
    fast_pivot_lows = _find_pivots(df[fast_col], direction="low")
    fast_pivot_highs = _find_pivots(df[fast_col], direction="high")

    # Bullish divergence: new N-bar low in price, but fast's pivot low is
    # higher than its prior pivot low by >= threshold.
    for i, (idx, is_pivot) in enumerate(price_pivot_lows.items()):
        if not is_pivot or i < lookback:
            continue
        # Check new N-bar low in price
        window = df[low_col].iloc[max(0, i - lookback + 1) : i + 1]
        if df[low_col].iloc[i] > window.min():
            continue
        # Find fast's pivot low near this bar and its prior pivot low
        curr_fast_pivot_val, prev_fast_pivot_val = _nearest_fast_pivot_pair(
            fast_pivot_lows, df[fast_col], i
        )
        if curr_fast_pivot_val is None or prev_fast_pivot_val is None:
            continue
        # Higher low on fast vs prior = bullish divergence
        if prev_fast_pivot_val == 0:
            continue
        gap = (curr_fast_pivot_val - prev_fast_pivot_val) / abs(prev_fast_pivot_val)
        if gap >= threshold:
            result.iloc[i] = 1

    # Bearish divergence: mirror of bullish
    for i, (idx, is_pivot) in enumerate(price_pivot_highs.items()):
        if not is_pivot or i < lookback:
            continue
        window = df[high_col].iloc[max(0, i - lookback + 1) : i + 1]
        if df[high_col].iloc[i] < window.max():
            continue
        curr_fast_pivot_val, prev_fast_pivot_val = _nearest_fast_pivot_pair(
            fast_pivot_highs, df[fast_col], i
        )
        if curr_fast_pivot_val is None or prev_fast_pivot_val is None:
            continue
        if prev_fast_pivot_val == 0:
            continue
        gap = (prev_fast_pivot_val - curr_fast_pivot_val) / abs(prev_fast_pivot_val)
        if gap >= threshold:
            result.iloc[i] = -1

    return result


def _find_pivots(series: pd.Series, direction: str) -> pd.Series:
    """
    Identify pivot points using a 5-bar window (2 before + center + 2 after).

    Args:
        series: values to search for pivots.
        direction: 'low' for pivot lows, 'high' for pivot highs.

    Returns:
        Boolean Series aligned with input, True where bar is a confirmed pivot.
    """
    pivots = pd.Series(False, index=series.index)
    for i in range(PIVOT_WINDOW, len(series) - PIVOT_WINDOW):
        window = series.iloc[i - PIVOT_WINDOW : i + PIVOT_WINDOW + 1]
        center = series.iloc[i]
        if pd.isna(center):
            continue
        if direction == "low" and center == window.min() and (window == center).sum() == 1:
            pivots.iloc[i] = True
        elif direction == "high" and center == window.max() and (window == center).sum() == 1:
            pivots.iloc[i] = True
    return pivots


def _nearest_fast_pivot_pair(
    fast_pivots: pd.Series,
    fast_values: pd.Series,
    at_index: int,
) -> tuple[Optional[float], Optional[float]]:
    """
    Find the most recent and prior fast-line pivot values at or before at_index.

    Returns:
        (current_fast_pivot_value, prior_fast_pivot_value) or (None, None) if
        fewer than 2 fast pivots exist before at_index.
    """
    pivot_indices = [i for i in range(at_index + 1) if fast_pivots.iloc[i]]
    if len(pivot_indices) < 2:
        return None, None
    curr_idx = pivot_indices[-1]
    prev_idx = pivot_indices[-2]
    return float(fast_values.iloc[curr_idx]), float(fast_values.iloc[prev_idx])
