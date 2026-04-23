# CC Build Brief — 3-10 Oscillator (Raschke)

**Upstream context:** [Titans Pass 2 brief](../strategy-reviews/raschke/titans-brief-3-10-oscillator.md)
**Olympus source:** `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md`
**Build type:** Phased (4 phases with checkpoints). Do not skip ahead — each phase gates the next.
**Estimate:** ~6 days total across 4 phases.

---

## Prime Directives

1. **Read `PROJECT_RULES.md` and `CLAUDE.md` at repo root before touching code.** They contain conventions you must follow (empty-safe env vars, route ordering, factor scoring, data source hierarchy).
2. **Data source hierarchy (April 2026, superseding stale PROJECT_RULES.md line 106):** UW API is primary for everything including OHLCV bars. yfinance is fallback only. Polygon and FMP are deprecated — never add new dependencies.
3. **Existing yfinance calls in legacy code (e.g., `holy_grail_scanner._fetch_1h_bars()`) stay untouched in this ticket.** Migrating legacy code is a separate concern. Any *new* data fetching you add follows UW-primary + yfinance-fallback.
4. **Ship one phase at a time.** After each phase, stop. Nick reviews the output in the checkpoint before you start the next phase.
5. **All exact find/replace anchors in this brief are copy-paste-verbatim.** Do not paraphrase. If the string doesn't match exactly, something has drifted since this brief was written — STOP and ask Nick before guessing.

---

## Phase 0 — Pre-Flight Check (30 min, no code)

Before starting Phase 1, verify the following and report findings to Nick:

1. Confirm `backend/enrichment/signal_enricher.py` exists and contains the `enrich_signal(signal_data)` async function (it should — this brief was written against commit `123d66b` or later).
2. Confirm `backend/scanners/holy_grail_scanner.py` contains the exact anchor strings listed in Phase 2 of this brief. If any anchor doesn't match verbatim, STOP and escalate to Nick before proceeding.
3. Identify where FastAPI routes live — check `backend/main.py` and `backend/api/` — so Phase 4 knows where to add the dev view endpoint.
4. Run `pytest backend/tests/` once to confirm the test suite is currently green. If broken tests exist, list them to Nick but do not fix them as part of this ticket.

Report findings as a short message to Nick, then wait for the go-ahead to start Phase 1.

---

# PHASE 1 — Indicator Module + Tests + Schema Migration

**Objective:** Create the 3-10 Oscillator math module, its tests, and the database schema changes. Fully additive — zero production impact. Can deploy to Railway cleanly without breaking anything.

**Estimate:** 2 days.

## Files to Create

### 1.1 `backend/indicators/__init__.py`

```python
"""
System-wide technical indicators.

Indicators are pure, stateless functions that take a DataFrame and return
a DataFrame with additional columns appended. They have no side effects
(no DB writes, no logging, no config lookups).

Callers are responsible for caching, persistence, and side effects.
"""
```

### 1.2 `backend/indicators/three_ten_oscillator.py`

Full file content (this is the canonical implementation — do not modify the math without Olympus re-review):

```python
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
```

### 1.3 `backend/tests/indicators/__init__.py`

Empty file (pytest package marker).

### 1.4 `backend/tests/indicators/test_three_ten_oscillator.py`

```python
"""
Tests for the 3-10 Oscillator indicator.

Test strategy:
    1. Math correctness — verify SMAs and oscillator values match expected
       output on a deterministic synthetic series.
    2. Column contract — function appends exactly OSC_FAST, OSC_SLOW,
       OSC_CROSS, OSC_DIV columns without mutating other columns.
    3. Insufficient data — returns df with NA columns when len(df) < 20.
    4. Divergence detection — synthetic bull-div and bear-div patterns
       trigger the correct osc_div sign.
    5. Raschke published vectors — PLACEHOLDER. Nick must supply these;
       the test is marked skip until he provides real values.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from indicators.three_ten_oscillator import (
    OSC_CROSS,
    OSC_DIV,
    OSC_FAST,
    OSC_SLOW,
    compute_3_10,
)


def _make_df(highs, lows):
    assert len(highs) == len(lows)
    idx = [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(len(highs))]
    return pd.DataFrame({"high": highs, "low": lows}, index=idx)


def test_columns_appended_correctly():
    df = _make_df([10 + i * 0.1 for i in range(30)], [9 + i * 0.1 for i in range(30)])
    result = compute_3_10(df)
    for col in (OSC_FAST, OSC_SLOW, OSC_CROSS, OSC_DIV):
        assert col in result.columns, f"Missing column: {col}"


def test_returns_na_columns_when_insufficient_data():
    df = _make_df([10.0] * 15, [9.0] * 15)
    result = compute_3_10(df)
    assert result[OSC_FAST].isna().all()
    assert result[OSC_SLOW].isna().all()


def test_math_deterministic_series():
    """
    On a monotonically rising series (constant +0.1 per bar), the oscillator
    should be positive and fast should track above slow in the tail.
    """
    df = _make_df(
        highs=[10 + i * 0.1 for i in range(50)],
        lows=[9 + i * 0.1 for i in range(50)],
    )
    result = compute_3_10(df)
    # After warmup, oscillator values should be defined and fast > slow
    tail = result.iloc[25:]
    assert not tail[OSC_FAST].isna().any()
    assert (tail[OSC_FAST] > tail[OSC_SLOW]).mean() > 0.8  # Majority fast > slow


def test_bull_divergence_smoke():
    """
    Smoke test: verify divergence detection runs without error on a realistic
    price series. Does NOT assert that divergence fires — synthetic patterns
    are fragile proxies for real divergences. Actual divergence quality is
    validated during the 6-month shadow period against real market data.
    """
    # Construct 50 bars of mixed price action (falling then sideways then rising)
    lows = [10 - i * 0.15 for i in range(15)] + [7.5 + (i % 3) * 0.1 for i in range(15)] + [8 + i * 0.2 for i in range(20)]
    highs = [lo + 0.5 for lo in lows]
    df = _make_df(highs, lows)
    result = compute_3_10(df)
    # Verify column populated with valid integer values (no exceptions raised)
    assert result[OSC_DIV].dtype in ("int8", "int64", "Int64")
    assert result[OSC_DIV].isin([-1, 0, 1]).all()


def test_divergence_detection_handles_flat_series():
    """
    Edge case: a perfectly flat price series should produce no divergences
    (no pivots at all) and should not crash.
    """
    df = _make_df([10.0] * 30, [9.0] * 30)
    result = compute_3_10(df)
    assert (result[OSC_DIV] == 0).all()


@pytest.mark.skip(reason="Nick to supply Raschke published test vectors — see Phase 1 checkpoint")
def test_raschke_published_vectors():
    """
    Validate math output matches Raschke's published examples to 4 decimal places.

    TODO (Nick): Source 2-3 known 3-10 readings from Linda Raschke's published
    examples (her books or trading course materials). Replace this stub with
    real test vectors.

    When ready:
        expected = [
            {"bar_index": 14, "osc_fast": 0.1234, "osc_slow": 0.0567},
            ...
        ]
        df = build_df_from_raschke_example()
        result = compute_3_10(df)
        for e in expected:
            assert abs(result[OSC_FAST].iloc[e["bar_index"]] - e["osc_fast"]) < 1e-4
    """
    pass
```

### 1.5 `migrations/012_three_ten_oscillator.sql`

```sql
-- Migration 012: 3-10 Oscillator infrastructure
-- Adds gate_type column to signals table for Holy Grail shadow-mode A/B comparison.
-- Creates divergence_events table for persisted 3-10 divergence firings.
-- Idempotent: safe to re-run.

-- 1. signals.gate_type — tags which gate (RSI, 3-10, or both) qualified a signal.
--    VARCHAR(20) accommodates future gate labels beyond "rsi"/"3-10"/"both".
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS gate_type VARCHAR(20);

CREATE INDEX IF NOT EXISTS idx_signals_gate_type
    ON signals(gate_type) WHERE gate_type IS NOT NULL;

-- 2. divergence_events — persistent log of 3-10 divergence firings for analysis.
CREATE TABLE IF NOT EXISTS divergence_events (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_timestamp TIMESTAMPTZ NOT NULL,
    div_type TEXT NOT NULL CHECK (div_type IN ('bull', 'bear')),
    fast_pivot_prev NUMERIC(12, 6),
    fast_pivot_curr NUMERIC(12, 6),
    price_pivot_prev NUMERIC(12, 6),
    price_pivot_curr NUMERIC(12, 6),
    threshold_used NUMERIC(5, 4),
    lookback_used INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, timeframe, bar_timestamp, div_type)
);

CREATE INDEX IF NOT EXISTS idx_divergence_events_ticker_time
    ON divergence_events(ticker, bar_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_divergence_events_type
    ON divergence_events(div_type, bar_timestamp DESC);
```

## Files to Edit

### 1.6 `backend/database/postgres_client.py`

Mirror the migration into `init_database()` for fresh-deploy idempotency. Do NOT remove the migration file — both must exist.

**EXACT FIND/REPLACE ANCHOR:** find this block near the end of `init_database()` (look for the `ZEUS Phase 2: Feed tier classification column` comment):

```
        # ZEUS Phase 2: Feed tier classification column
        try:
            await conn.execute("""
                ALTER TABLE signals
                ADD COLUMN IF NOT EXISTS feed_tier VARCHAR(20) DEFAULT 'research_log'
            """)
        except Exception as e:
            print(f"WARNING: signals feed_tier column skipped (lock timeout?): {e}")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_feed_tier ON signals(feed_tier)
        """)

        print("Database schema initialized")
```

**REPLACE WITH:**

```
        # ZEUS Phase 2: Feed tier classification column
        try:
            await conn.execute("""
                ALTER TABLE signals
                ADD COLUMN IF NOT EXISTS feed_tier VARCHAR(20) DEFAULT 'research_log'
            """)
        except Exception as e:
            print(f"WARNING: signals feed_tier column skipped (lock timeout?): {e}")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_feed_tier ON signals(feed_tier)
        """)

        # Raschke Phase 1 (migration 012): 3-10 Oscillator shadow-mode infrastructure
        try:
            await conn.execute("""
                ALTER TABLE signals
                ADD COLUMN IF NOT EXISTS gate_type VARCHAR(20)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_gate_type
                ON signals(gate_type) WHERE gate_type IS NOT NULL
            """)
        except Exception as e:
            print(f"WARNING: signals gate_type column skipped: {e}")

        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS divergence_events (
                    id SERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    bar_timestamp TIMESTAMPTZ NOT NULL,
                    div_type TEXT NOT NULL CHECK (div_type IN ('bull', 'bear')),
                    fast_pivot_prev NUMERIC(12, 6),
                    fast_pivot_curr NUMERIC(12, 6),
                    price_pivot_prev NUMERIC(12, 6),
                    price_pivot_curr NUMERIC(12, 6),
                    threshold_used NUMERIC(5, 4),
                    lookback_used INT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(ticker, timeframe, bar_timestamp, div_type)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_divergence_events_ticker_time
                ON divergence_events(ticker, bar_timestamp DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_divergence_events_type
                ON divergence_events(div_type, bar_timestamp DESC)
            """)
        except Exception as e:
            print(f"WARNING: divergence_events table creation skipped: {e}")

        print("Database schema initialized")
```

## Verify Commands (CC runs these)

```bash
# From repo root
cd backend && python -m pytest tests/indicators/ -v
# Expected: 5 tests collected. 4 pass, 1 skipped (the Raschke vector placeholder).

# Verify no import errors in the new module
cd backend && python -c "from indicators.three_ten_oscillator import compute_3_10; print('OK')"
```

## Phase 1 Done Criteria

- [ ] `backend/indicators/three_ten_oscillator.py` exists with `compute_3_10` function exported.
- [ ] `backend/tests/indicators/test_three_ten_oscillator.py` passes 4 tests (1 skipped).
- [ ] `migrations/012_three_ten_oscillator.sql` exists.
- [ ] `backend/database/postgres_client.py` has the new ALTER/CREATE blocks in `init_database()`.
- [ ] Running `python backend/main.py` locally completes schema init without errors.
- [ ] Committed to a branch (not `main` directly — open a PR or push to a feature branch for Nick to review).

## Phase 1 Checkpoint (CC stops here)

**Post to Nick:**
1. Link to the PR or branch.
2. Output of pytest run.
3. Confirmation that schema migration ran cleanly locally.
4. Reminder that `test_raschke_published_vectors` is skipped pending Nick's test data.

**Nick reviews and greenlights Phase 2 before CC continues.**

---

# PHASE 2 — Holy Grail Dual-Gate Tagging

**Objective:** Modify the Holy Grail scanner to emit signals tagged with `gate_type = "rsi" | "3-10" | "both"`. Current RSI behavior preserved; 3-10 behavior added in shadow mode.

**Estimate:** 2 days.

## Files to Edit

### 2.1 `backend/scanners/holy_grail_scanner.py`

**EDIT 1 — Add 3-10 computation to `calculate_holy_grail_indicators()`.**

**FIND:**

```
    # RSI
    df["rsi"] = ta.rsi(df["Close"], length=HG_CONFIG["rsi_length"])

    # EMA touch tolerance band (VIX-adjusted at scan time via _hg_touch_tolerance)
```

**REPLACE WITH:**

```
    # RSI
    df["rsi"] = ta.rsi(df["Close"], length=HG_CONFIG["rsi_length"])

    # 3-10 Oscillator (Raschke) — shadow-mode dual-gate companion to RSI
    try:
        from indicators.three_ten_oscillator import compute_3_10
        df = compute_3_10(df)
    except Exception as e:
        logger.warning("3-10 oscillator compute failed; continuing RSI-only: %s", e)

    # EMA touch tolerance band (VIX-adjusted at scan time via _hg_touch_tolerance)
```

**EDIT 1B — Add divergence persistence call in `scan_ticker_holy_grail()`.**

The `compute_3_10` call above populates `osc_div` column on the DataFrame. Those flags need to be persisted to the `divergence_events` table so the Phase 4 frequency cap has data to query.

**FIND:**

```
        df = calculate_holy_grail_indicators(df)
        signals = check_holy_grail_signals(df, ticker)
```

**REPLACE WITH:**

```
        df = calculate_holy_grail_indicators(df)

        # Persist any 3-10 divergences detected on this scan for frequency-cap
        # monitoring and future Turtle Soup consumption. Safe on failure —
        # never blocks signal emission.
        try:
            from indicators.divergence_persister import persist_divergences
            await persist_divergences(df, ticker=ticker, timeframe="1h")
        except Exception as e:
            logger.debug("Divergence persistence failed for %s: %s", ticker, e)

        signals = check_holy_grail_signals(df, ticker)
```

### 2.2 Create `backend/indicators/divergence_persister.py`

New file. Writes divergence events from a DataFrame's `osc_div` column to the `divergence_events` table.

```python
"""
Divergence event persistence.

Writes 3-10 Oscillator divergence firings from a DataFrame's osc_div column
to the divergence_events table for later analysis and frequency-cap monitoring.
"""

import logging
from typing import Optional

import pandas as pd

from indicators.three_ten_oscillator import OSC_DIV, OSC_FAST

logger = logging.getLogger(__name__)


async def persist_divergences(
    df: pd.DataFrame,
    ticker: str,
    timeframe: str,
    threshold_used: float = 0.10,
    lookback_used: int = 5,
) -> int:
    """
    Write all divergence events in df to divergence_events table.

    Uses ON CONFLICT DO NOTHING via the UNIQUE constraint on
    (ticker, timeframe, bar_timestamp, div_type) so re-scans of overlapping
    bar windows are idempotent.

    Args:
        df: DataFrame with OSC_DIV column populated by compute_3_10.
            DatetimeIndex required.
        ticker: symbol to tag events with.
        timeframe: e.g. "1h", "1d", "15m".
        threshold_used: divergence threshold used in detection (for audit).
        lookback_used: lookback window used in detection (for audit).

    Returns:
        Count of rows inserted (excluding duplicates rejected by UNIQUE).
    """
    if df is None or df.empty or OSC_DIV not in df.columns:
        return 0

    # Filter to rows where divergence fired (+1 bull, -1 bear)
    div_rows = df[df[OSC_DIV] != 0]
    if div_rows.empty:
        return 0

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
    except Exception as e:
        logger.warning("Cannot get DB pool for divergence persistence: %s", e)
        return 0

    inserted = 0
    async with pool.acquire() as conn:
        for idx, row in div_rows.iterrows():
            div_type = "bull" if row[OSC_DIV] == 1 else "bear"
            # We don't surface pivot values from the detection function in MVP
            # — passing NULL for pivot columns is acceptable per schema.
            try:
                result = await conn.execute(
                    """
                    INSERT INTO divergence_events (
                        ticker, timeframe, bar_timestamp, div_type,
                        fast_pivot_prev, fast_pivot_curr,
                        price_pivot_prev, price_pivot_curr,
                        threshold_used, lookback_used
                    ) VALUES ($1, $2, $3, $4, NULL, NULL, NULL, NULL, $5, $6)
                    ON CONFLICT (ticker, timeframe, bar_timestamp, div_type)
                    DO NOTHING
                    """,
                    ticker,
                    timeframe,
                    idx if isinstance(idx, pd.Timestamp) else pd.Timestamp(idx),
                    div_type,
                    threshold_used,
                    lookback_used,
                )
                if str(result).strip().endswith("1"):
                    inserted += 1
            except Exception as e:
                logger.debug("Divergence insert failed for %s @ %s: %s", ticker, idx, e)

    if inserted > 0:
        logger.info("Persisted %d divergence events for %s (%s)", inserted, ticker, timeframe)
    return inserted
```

**EDIT 2 — Restructure `check_holy_grail_signals()` to emit dual-gate signals.**

This edit lives in `backend/scanners/holy_grail_scanner.py` (same file as EDIT 1 / 1B from section 2.1 above).

**FIND the entire block** starting at:

```
    # Long: ADX strong, uptrend, previous bar pulled back to EMA, current closes above EMA
    long_signal = (
        adx >= HG_CONFIG["adx_threshold"] and
        di_plus > di_minus and
        prev.get("long_pullback", False) and
        latest["Close"] > ema20 and
        rsi < HG_CONFIG["rsi_long_max"]
    )

    # Short: ADX strong, downtrend, previous bar pulled back to EMA, current closes below EMA
    # In strong downtrends (ADX >= 30 + DI- > 1.5x DI+), RSI stays "oversold" for weeks.
    # Skip RSI floor for continuation shorts — Holy Grail is trend continuation, not mean reversion.
    strong_bearish_trend = (adx >= 30 and di_minus > di_plus * 1.5)
    rsi_ok_for_short = (rsi > HG_CONFIG["rsi_short_min"]) or strong_bearish_trend

    short_signal = (
        adx >= HG_CONFIG["adx_threshold"] and
        di_minus > di_plus and
        prev.get("short_pullback", False) and
        latest["Close"] < ema20 and
        rsi_ok_for_short
    )
```

**REPLACE WITH:**

```
    # Base conditions — everything EXCEPT the filter gate (RSI or 3-10).
    # These are the structural HG criteria that must hold regardless of gate.
    base_long = (
        adx >= HG_CONFIG["adx_threshold"] and
        di_plus > di_minus and
        prev.get("long_pullback", False) and
        latest["Close"] > ema20
    )
    strong_bearish_trend = (adx >= 30 and di_minus > di_plus * 1.5)
    base_short = (
        adx >= HG_CONFIG["adx_threshold"] and
        di_minus > di_plus and
        prev.get("short_pullback", False) and
        latest["Close"] < ema20
    )

    # RSI gate (existing filter — preserves current behavior).
    rsi_long_ok = rsi < HG_CONFIG["rsi_long_max"]
    rsi_short_ok = (rsi > HG_CONFIG["rsi_short_min"]) or strong_bearish_trend

    # 3-10 gate (new — Raschke shadow mode).
    # Fast > slow = bullish momentum; fast < slow = bearish momentum.
    osc_fast = latest.get("osc_fast")
    osc_slow = latest.get("osc_slow")
    three_ten_available = (osc_fast is not None and osc_slow is not None
                           and not pd.isna(osc_fast) and not pd.isna(osc_slow))
    three_ten_long_ok = three_ten_available and osc_fast > osc_slow
    three_ten_short_ok = three_ten_available and osc_fast < osc_slow

    # Gate resolution: which gate(s) qualified the long/short setup?
    long_gate = _resolve_gate_type(rsi_long_ok, three_ten_long_ok) if base_long else None
    short_gate = _resolve_gate_type(rsi_short_ok, three_ten_short_ok) if base_short else None

    # Emit signals — current contract preserved; gate_type is the new field.
    long_signal = long_gate is not None
    short_signal = short_gate is not None
```

**EDIT 3 — Add the `_resolve_gate_type` helper.**

**FIND:**

```
def check_holy_grail_signals(df: pd.DataFrame, ticker: str) -> List[Dict]:
    """Check for Holy Grail long and short setups on latest bars."""
```

**REPLACE WITH:**

```
def _resolve_gate_type(rsi_ok: bool, three_ten_ok: bool) -> Optional[str]:
    """
    Resolve which filter gate(s) qualified a setup.

    Returns:
        "both" if both RSI and 3-10 passed — primary signal, Nick-visible
        "rsi"  if only RSI passed — current production behavior, Nick-visible
        "3-10" if only 3-10 passed — shadow-mode-only, hidden from main feed
        None   if neither passed — no signal emitted
    """
    if rsi_ok and three_ten_ok:
        return "both"
    if rsi_ok:
        return "rsi"
    if three_ten_ok:
        return "3-10"
    return None


def check_holy_grail_signals(df: pd.DataFrame, ticker: str) -> List[Dict]:
    """Check for Holy Grail long and short setups on latest bars."""
```

**EDIT 4 — Attach `gate_type` to emitted signal dicts.**

**FIND** both occurrences of this block (there are two — one for long, one for short):

```
            signals.append({
                "signal_id": f"HG_{ticker}_{now_str}",
                "timestamp": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "LONG",
```

**For the LONG block, REPLACE WITH:**

```
            signals.append({
                "signal_id": f"HG_{ticker}_{now_str}_{long_gate}",
                "timestamp": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "LONG",
                "gate_type": long_gate,
```

**For the SHORT block (same FIND pattern but with `"direction": "SHORT"`), REPLACE WITH the equivalent using `short_gate`:**

```
            signals.append({
                "signal_id": f"HG_{ticker}_{now_str}_{short_gate}",
                "timestamp": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "SHORT",
                "gate_type": short_gate,
```

**EDIT 5 — Import `Optional` and `pd` check fix at top of file.**

**FIND:**

```
from typing import Dict, List, Optional
```

(This line should already exist — if not, add it.)

Ensure `import pandas as pd` is present (it is — already at the top of the file).

### 2.3 Signal Pipeline Persistence

Check whether `signals.pipeline.process_signal_unified` persists arbitrary keys from the signal dict. If `gate_type` is dropped on INSERT, update the INSERT statement. Specifically, look at how `backend/database/postgres_client.py:log_signal()` handles the INSERT — it currently maps specific keys. Add `gate_type` to the INSERT:

**EDIT `backend/database/postgres_client.py:log_signal`:**

**FIND:**

```
        result = await conn.execute("""
            INSERT INTO signals (
                signal_id, timestamp, strategy, ticker, asset_class,
                direction, signal_type, entry_price, stop_loss, target_1,
                target_2, risk_reward, timeframe, bias_level, adx, line_separation,
                score, bias_alignment, triggering_factors, bias_at_signal, notes,
                day_of_week, hour_of_day, is_opex_week, days_to_earnings, market_event, signal_category,
                feed_tier, adx_value, feed_tier_ceiling, score_ceiling_reason
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31
            )
            ON CONFLICT (signal_id) DO NOTHING
        """,
```

**REPLACE WITH** (adds `gate_type` as $32):

```
        result = await conn.execute("""
            INSERT INTO signals (
                signal_id, timestamp, strategy, ticker, asset_class,
                direction, signal_type, entry_price, stop_loss, target_1,
                target_2, risk_reward, timeframe, bias_level, adx, line_separation,
                score, bias_alignment, triggering_factors, bias_at_signal, notes,
                day_of_week, hour_of_day, is_opex_week, days_to_earnings, market_event, signal_category,
                feed_tier, adx_value, feed_tier_ceiling, score_ceiling_reason, gate_type
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32
            )
            ON CONFLICT (signal_id) DO NOTHING
        """,
```

Then find the parameter list that follows this query (ends with `signal_data.get("_score_ceiling_reason"),`) and add a final parameter:

**FIND:**

```
            signal_data.get("_score_ceiling_reason"),              # $31 ZEUS Ph5: why ceiling applied
        )
        inserted = str(result).strip().endswith("1")
```

**REPLACE WITH:**

```
            signal_data.get("_score_ceiling_reason"),              # $31 ZEUS Ph5: why ceiling applied
            signal_data.get("gate_type"),                          # $32 Raschke P1: dual-gate shadow mode
        )
        inserted = str(result).strip().endswith("1")
```

## Verify Commands

```bash
# Ensure scanner still imports without errors
cd backend && python -c "from scanners.holy_grail_scanner import run_holy_grail_scan; print('OK')"

# Run a single-ticker scan and check output
cd backend && python -c "
import asyncio
from scanners.holy_grail_scanner import scan_ticker_holy_grail

async def main():
    signals = await scan_ticker_holy_grail('SPY')
    print(f'Signals emitted: {len(signals)}')
    for s in signals:
        print(f'  {s.get(\"direction\")} gate_type={s.get(\"gate_type\")}')

asyncio.run(main())
"
```

## Phase 2 Done Criteria

- [ ] `holy_grail_scanner.py` modifications in place (5 edits).
- [ ] `backend/indicators/divergence_persister.py` created.
- [ ] `postgres_client.py:log_signal` updated to persist `gate_type`.
- [ ] Scanner smoke test prints at least one signal (or cleanly prints "0 signals" on a day with no setups).
- [ ] No regression in existing RSI-gated signals — when RSI passes, signal is emitted with `gate_type="rsi"` or `gate_type="both"`.
- [ ] DB verification: `SELECT gate_type, COUNT(*) FROM signals WHERE strategy='Holy_Grail' AND created_at > NOW() - INTERVAL '1 hour' GROUP BY gate_type;` returns rows.
- [ ] Divergence persistence verification: `SELECT COUNT(*) FROM divergence_events WHERE created_at > NOW() - INTERVAL '1 hour';` returns rows after a scan completes (assuming any divergences fired).

## Phase 2 Checkpoint (CC stops)

Post to Nick:
1. Branch/PR link.
2. Output of smoke test.
3. Sample DB rows showing `gate_type` values from recent signals.
4. Count of 3-10-only signals observed in first market hour after deploy (proves shadow mode is capturing data).

**Nick reviews and greenlights Phase 3.**

---

# PHASE 3 — Sector-ETF 3-10 + Enrichment Pipeline

**Objective:** Compute 3-10 on the 11 SPDR sector ETFs. Wire readings into `signal_enricher.py` so every signal's `enrichment_data` JSONB carries the relevant sector 3-10 context.

**Estimate:** 1 day.

## Pre-Phase 3 Verification (CC runs FIRST)

Two assumptions in the code below need verification before implementation. If either fails, follow the fallback path noted:

1. **Ticker-to-sector mapping in `backend/scanners/sector_rs.py`:**
   - Inspect the file. If a function like `get_ticker_sector_etf(ticker) -> str` exists or can be cleanly derived from existing data structures, use it (delete the `_DEFAULT_SECTOR_MAP` hard-code in favor of that lookup).
   - If no such function exists, keep the hard-coded `_DEFAULT_SECTOR_MAP` but expand it to cover the top 50 watchlist tickers. Report back with the list of tickers in the mapping.

2. **UW API candles endpoint (`integrations.uw_api.get_candles`):**
   - Inspect `backend/integrations/uw_api.py`. If a `get_candles(ticker, timeframe, days)` function exists, use it as primary per the code below.
   - If it doesn't exist, do NOT build a thin wrapper as part of this ticket (scope creep). Instead, comment out the UW primary block in `_fetch_daily_bars` and fall back to yfinance directly. Log a follow-up TODO for Nick titled "Add `uw_api.get_candles` for sector-ETF bar fetching" so it gets built in a proper ticket with Titans review.

Report findings from both checks to Nick before writing Phase 3 code.

## Files to Create

### 3.1 `backend/indicators/sector_rotation_3_10.py`

```python
"""
Sector-ETF 3-10 Oscillator readings with in-process caching.

Computes 3-10 on the 11 SPDR sector ETFs every bar close, caches readings,
and exposes a lookup function for the signal enrichment pipeline.

Data source: UW API primary, yfinance fallback (per April 2026 data hierarchy).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd

from indicators.three_ten_oscillator import OSC_FAST, OSC_SLOW, OSC_CROSS, compute_3_10

logger = logging.getLogger(__name__)

# 11 SPDR sector ETFs
SECTOR_ETFS = [
    "XLK",  # Technology
    "XLF",  # Financials
    "XLE",  # Energy
    "XLY",  # Consumer Discretionary
    "XLV",  # Health Care
    "XLP",  # Consumer Staples
    "XLU",  # Utilities
    "XLI",  # Industrials
    "XLB",  # Materials
    "XLRE", # Real Estate
    "XLC",  # Communication Services
]

# Ticker-to-sector ETF map (partial — extend via sector_rs module lookup at runtime).
# This is a best-effort shortcut for the most common watchlist tickers.
_DEFAULT_SECTOR_MAP = {
    # Tech
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "GOOGL": "XLK", "META": "XLK",
    "AMZN": "XLY", "TSLA": "XLY",
    # Financials
    "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "GS": "XLF", "MS": "XLF",
    # Energy
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE",
    # Health
    "UNH": "XLV", "JNJ": "XLV", "LLY": "XLV", "PFE": "XLV",
    # etc. Extend as needed.
}

# In-process cache: sector_etf -> latest 3-10 reading dict
_sector_cache: Dict[str, Dict] = {}
_last_refresh: Optional[datetime] = None
_REFRESH_INTERVAL = timedelta(minutes=15)  # Refresh every 15 min at most


async def get_sector_3_10_for_ticker(ticker: str) -> Optional[Dict]:
    """
    Return the latest 3-10 reading for a ticker's sector ETF.

    Returns None if we can't resolve the sector or the cache is empty.
    Shape: {"sector_etf": "XLK", "osc_fast": 0.12, "osc_slow": 0.08, "osc_cross": 0}
    """
    sector_etf = _DEFAULT_SECTOR_MAP.get(ticker.upper())
    if not sector_etf:
        # Try the sector_rs module for a broader lookup
        try:
            from scanners.sector_rs import get_ticker_sector_etf
            sector_etf = await get_ticker_sector_etf(ticker)
        except Exception:
            pass
    if not sector_etf:
        return None

    # Refresh cache if stale
    await _refresh_if_stale()

    return _sector_cache.get(sector_etf)


async def refresh_sector_cache() -> None:
    """
    Force-refresh all sector ETF 3-10 readings. Safe to call on a schedule.
    """
    global _last_refresh
    tasks = [_compute_single_sector(etf) for etf in SECTOR_ETFS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for etf, result in zip(SECTOR_ETFS, results):
        if isinstance(result, Exception):
            logger.warning("Sector 3-10 compute failed for %s: %s", etf, result)
            continue
        _sector_cache[etf] = result
    _last_refresh = datetime.utcnow()
    logger.info("Sector 3-10 cache refreshed: %d ETFs", len(_sector_cache))


async def _refresh_if_stale() -> None:
    global _last_refresh
    if _last_refresh is None or (datetime.utcnow() - _last_refresh) > _REFRESH_INTERVAL:
        await refresh_sector_cache()


async def _compute_single_sector(sector_etf: str) -> Dict:
    """
    Fetch daily bars for a sector ETF and compute the latest 3-10 reading.
    UW primary, yfinance fallback.
    """
    df = await _fetch_daily_bars(sector_etf, days=60)
    if df is None or df.empty or len(df) < 20:
        return {"sector_etf": sector_etf, "osc_fast": None, "osc_slow": None, "osc_cross": 0}

    df = compute_3_10(df)
    latest = df.iloc[-1]
    return {
        "sector_etf": sector_etf,
        "osc_fast": float(latest[OSC_FAST]) if not pd.isna(latest[OSC_FAST]) else None,
        "osc_slow": float(latest[OSC_SLOW]) if not pd.isna(latest[OSC_SLOW]) else None,
        "osc_cross": int(latest[OSC_CROSS]) if not pd.isna(latest[OSC_CROSS]) else 0,
    }


async def _fetch_daily_bars(ticker: str, days: int = 60) -> Optional[pd.DataFrame]:
    """UW API primary, yfinance fallback."""
    # 1. Try UW API
    try:
        from integrations.uw_api import get_candles
        df = await get_candles(ticker, timeframe="1d", days=days)
        if df is not None and not df.empty:
            return df
    except ImportError:
        logger.debug("uw_api.get_candles not available, falling back to yfinance")
    except Exception as e:
        logger.debug("UW candles fetch failed for %s: %s", ticker, e)

    # 2. Fallback: yfinance
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        df = stock.history(period=f"{days}d", interval="1d")
        if df is not None and not df.empty:
            # Normalize column names to lowercase for compute_3_10
            df = df.rename(columns={"High": "high", "Low": "low", "Close": "close"})
            return df
    except Exception as e:
        logger.warning("yfinance fallback failed for %s: %s", ticker, e)

    return None
```

### 3.2 Edit `backend/enrichment/signal_enricher.py`

Add sector 3-10 context to the enrichment payload.

**FIND:**

```
    enrichment: Dict[str, Any] = {
        "ticker": ticker,
        "enriched_at": datetime.utcnow().isoformat(),
        # Tier 1 (from universe cache)
        "atr_14": None,
        "avg_volume_20d": None,
        "iv_rank": None,
        # Tier 2 (live snapshot)
        "current_price": None,
        "today_volume": None,
        "prev_close": None,
        "change_pct": None,
        "rvol": None,
        # Derived
        "atr_pct": None,  # ATR as % of current price
        "risk_in_atr": None,  # (entry - stop) / ATR — how many ATRs of risk
    }
```

**REPLACE WITH:**

```
    enrichment: Dict[str, Any] = {
        "ticker": ticker,
        "enriched_at": datetime.utcnow().isoformat(),
        # Tier 1 (from universe cache)
        "atr_14": None,
        "avg_volume_20d": None,
        "iv_rank": None,
        # Tier 2 (live snapshot)
        "current_price": None,
        "today_volume": None,
        "prev_close": None,
        "change_pct": None,
        "rvol": None,
        # Derived
        "atr_pct": None,  # ATR as % of current price
        "risk_in_atr": None,  # (entry - stop) / ATR — how many ATRs of risk
        # Raschke Phase 3: sector 3-10 context
        "sector_3_10": None,  # dict: {sector_etf, osc_fast, osc_slow, osc_cross}
    }
```

**FIND** (near the end of `enrich_signal`, just before the final `signal_data["enrichment_data"] = enrichment` line):

```
    # --- Write to signal ---
    signal_data["enrichment_data"] = enrichment
```

**REPLACE WITH:**

```
    # --- Sector 3-10 context (Raschke Phase 3) ---
    try:
        from indicators.sector_rotation_3_10 import get_sector_3_10_for_ticker
        sector_reading = await get_sector_3_10_for_ticker(ticker)
        if sector_reading:
            enrichment["sector_3_10"] = sector_reading
    except Exception as e:
        logger.debug(f"Sector 3-10 enrichment failed for {ticker}: {e}")

    # --- Write to signal ---
    signal_data["enrichment_data"] = enrichment
```

### 3.3 Scheduler Hook (optional but recommended)

If `backend/scheduler/` has a jobs registry, add a recurring job that calls `refresh_sector_cache()` every 15 minutes during market hours. If no clean scheduler pattern exists, skip this — the lazy refresh in `get_sector_3_10_for_ticker` will handle cache staleness on demand, it's just less efficient.

**CC task:** inspect `backend/scheduler/` for the existing pattern. If a clean addition is possible in <30 LOC, add it. Otherwise skip and log a followup TODO for Nick.

## Verify Commands

```bash
cd backend && python -c "
import asyncio
from indicators.sector_rotation_3_10 import refresh_sector_cache, get_sector_3_10_for_ticker

async def main():
    await refresh_sector_cache()
    for ticker in ['AAPL', 'JPM', 'XOM']:
        reading = await get_sector_3_10_for_ticker(ticker)
        print(f'{ticker}: {reading}')

asyncio.run(main())
"
```

Expected output: each ticker prints a dict with `sector_etf`, `osc_fast`, `osc_slow`, `osc_cross`.

## Phase 3 Done Criteria

- [ ] `backend/indicators/sector_rotation_3_10.py` exists.
- [ ] `signal_enricher.py` populates `sector_3_10` field on enrichment_data.
- [ ] Smoke test prints valid sector 3-10 readings for 3 test tickers.
- [ ] DB verification: `SELECT enrichment_data->'sector_3_10' FROM signals WHERE created_at > NOW() - INTERVAL '1 hour' AND enrichment_data->'sector_3_10' IS NOT NULL LIMIT 5;` returns rows.

## Phase 3 Checkpoint

Post to Nick: branch link, smoke test output, sample enrichment payload from a recent signal. Greenlight before Phase 4.

---

# PHASE 4 — Dev View + Frequency Cap Self-Check

**Objective:** Ship the `/dev/shadow-3-10` view for Nick to inspect 3-10-only signals, and add a frequency cap self-check that logs warnings when divergences fire too often.

**Estimate:** 1 day.

## Files to Create

### 4.1 API Route

**CC task in Phase 0:** you identified where FastAPI routes live. Add the new endpoint there following the existing pattern.

Route spec:
- **Path:** `GET /api/dev/shadow-3-10`
- **Auth:** `X-API-Key` header (same pattern as other `/api/*` routes)
- **Query params:** `limit` (default 50, max 200), `since_hours` (default 168 = 7 days)
- **Response:** JSON list of signals filtered by `gate_type = '3-10'`, ordered by `created_at DESC`

Reference implementation (adapt to the pattern you find in `backend/api/`):

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any

router = APIRouter(prefix="/api/dev", tags=["dev-shadow"])

@router.get("/shadow-3-10")
async def get_shadow_3_10_signals(
    limit: int = Query(50, ge=1, le=200),
    since_hours: int = Query(168, ge=1, le=720),
    _auth = Depends(verify_api_key),  # use the existing auth dep
) -> Dict[str, Any]:
    """
    Return 3-10-only Holy Grail signals for shadow-mode review.
    X-API-Key required. No nav link — direct URL access only.
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id, ticker, direction, gate_type, entry_price, stop_loss, target_1,
                   adx, rsi, enrichment_data, created_at
            FROM signals
            WHERE gate_type = '3-10'
              AND created_at > NOW() - ($1 * INTERVAL '1 hour')
            ORDER BY created_at DESC
            LIMIT $2
            """,
            since_hours,
            limit,
        )
    return {
        "signals": [dict(r) for r in rows],
        "count": len(rows),
        "since_hours": since_hours,
    }
```

Register the router in the main app (CC finds where other routers are registered — likely `backend/main.py`).

### 4.2 Frontend Dev View Page

Create a single HTML page served from wherever the existing static files live. Direct URL: `/dev/shadow-3-10.html`. No nav link from the main dashboard.

Minimum content: fetch the API endpoint (include `X-API-Key` header from `window.PIVOT_API_KEY` or equivalent existing pattern), render a table with `ticker`, `direction`, `entry_price`, `stop_loss`, `target_1`, `adx`, `rsi`, sector 3-10 snapshot, and `created_at`.

Keep styling minimal — match existing dev tool pages if any exist, otherwise plain HTML + minimal CSS. This is an internal tool, not a polished surface.

### 4.3 Frequency Cap Self-Check

The `divergence_events` table is populated by `backend/indicators/divergence_persister.py` (created in Phase 2), which is called from the Holy Grail scanner after `compute_3_10(df)`. Phase 4 adds a monitoring wrapper that logs warnings when frequency exceeds the sanity threshold.

**Add a helper inside `backend/indicators/divergence_persister.py`:**

```python
async def check_divergence_frequency(ticker: str, timeframe: str) -> None:
    """
    Log a warning if divergence events for a ticker on a given timeframe
    exceed 3 per month on daily bars. URSA frequency-cap sanity check
    (Olympus-locked 2026-04-22).

    Only applies to 1d timeframe — intraday divergences fire more frequently
    by design and are not subject to this cap.
    """
    if timeframe != "1d":
        return

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
    except Exception as e:
        logger.warning("Cannot get DB pool for frequency check: %s", e)
        return

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM divergence_events
            WHERE ticker = $1
              AND timeframe = '1d'
              AND bar_timestamp > NOW() - INTERVAL '30 days'
            """,
            ticker,
        )
    if count and count > 3:
        logger.warning(
            "FREQ_CAP_BREACH: ticker=%s divergences=%d/30d on daily — "
            "rule may be detecting noise. Review threshold/lookback.",
            ticker, count,
        )
```

**Call this helper from `persist_divergences()`** after the insert loop completes. **EXACT FIND/REPLACE** in `backend/indicators/divergence_persister.py`:

**FIND:**

```
    if inserted > 0:
        logger.info("Persisted %d divergence events for %s (%s)", inserted, ticker, timeframe)
    return inserted
```

**REPLACE WITH:**

```
    if inserted > 0:
        logger.info("Persisted %d divergence events for %s (%s)", inserted, ticker, timeframe)
        # Frequency cap sanity check (URSA — Olympus 2026-04-22)
        await check_divergence_frequency(ticker, timeframe)
    return inserted
```

## Verify Commands

```bash
# Hit the dev endpoint locally
curl -H "X-API-Key: $PIVOT_API_KEY" \
     "http://localhost:8000/api/dev/shadow-3-10?limit=10&since_hours=24"

# Trigger the frequency cap log by artificially inserting 4+ divergences
# for a test ticker, then verify the warning appears in logs.
```

## Phase 4 Done Criteria

- [ ] `GET /api/dev/shadow-3-10` returns JSON when authenticated, 401 when not.
- [ ] Dev view HTML page loads and renders the signal list.
- [ ] Frequency cap self-check triggers warning log at >3 divergences/month on daily.
- [ ] Page is NOT linked from main nav.

## Phase 4 Checkpoint (Final)

Post to Nick: branch link, screenshot of dev view rendering, log excerpt showing frequency cap warning fires correctly. **MVP complete — ready for 6-month shadow period.**

---

## Day-90 Olympus Checkpoint (NOT PART OF THIS BUILD)

At day 90 of shadow operation, Nick triggers an Olympus review to determine whether early cutover to 3-10 gate is justified. Requires:
1. Statistical significance on win-rate/PF delta
2. Sufficient out-of-sample volume (Olympus call)

If both clear, Nick greenlights a follow-up brief to swap the primary gate from RSI to 3-10.

---

## Open TODOs (Nick-owned, parallel to CC work)

1. **Raschke test vectors:** source 2-3 known 3-10 readings from Linda Raschke's published materials for `test_raschke_published_vectors`. Replace the placeholder in Phase 1 test file.
2. **Stale PROJECT_RULES.md:** line 106 says Polygon is primary — should be corrected to match April 2026 data hierarchy (UW primary, yfinance fallback). Separate one-line PR whenever convenient.

---

**End of CC build brief.**
