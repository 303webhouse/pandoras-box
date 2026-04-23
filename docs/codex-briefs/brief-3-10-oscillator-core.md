# 3-10 Oscillator Core Module — CC Brief (Part A of 2)

**Type:** BUILD — new indicator module + persistence schema + unit tests
**Source:** Titans Pass 2 final (`docs/strategy-reviews/raschke/titans-brief-3-10-oscillator.md` §11)
**Estimated runtime:** ~2–3 days CC work (covers Titans days 1–2 indicator math + divergence + portion of day 6 tests)
**Output:** New `backend/indicators/` package + `divergence_events` table + unit test suite
**Blocks:** Brief B (pipeline integration) — do not start Brief B until this lands and tests are green

---

## 1. Context

Olympus unanimously approved the 3-10 Oscillator as the highest-leverage ELEVATE in the Raschke suite. Titans Pass 2 locked the architecture. This brief implements the **core indicator module** — the pure math, divergence detection, persistence schema, and unit tests. Pipeline integration (Holy Grail dual-gate, sector-ETF enrichment, dev view) is Brief B and depends on this landing first.

**Prior work / references:**
- `docs/strategy-reviews/raschke/titans-brief-3-10-oscillator.md` — Titans Pass 2 final (§11 is the locked architecture)
- `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` — Olympus review source
- `PROJECT_RULES.md` — Strategy Anti-Bloat Framework section

---

## 2. Scope

### IN scope
- New package `backend/indicators/` with `__init__.py` + `three_ten_oscillator.py`
- Pure stateless function `compute_3_10(df, divergence_lookback, divergence_threshold) -> pd.DataFrame`
- Mechanical divergence detection per Olympus-locked spec (§3.1 of Titans brief)
- `functools.lru_cache(maxsize=5000)` keyed on `(ticker, timeframe, last_bar_timestamp)`
- `divergence_events` table schema migration
- Unit test suite covering math correctness, divergence synthetics, frequency cap trigger

### OUT of scope (deferred to Brief B)
- Holy Grail dual-gate integration
- `trade_signals.gate_type` column migration
- `signal_enrichment.py` verification / creation / sector-ETF wiring
- Dev view `/dev/shadow-3-10`
- Frequency cap self-check writing to audit log (the function exists here; wiring is Brief B)

---

## 3. Architecture (Locked by Titans Pass 2 §11)

### 3.1 Module location

New package:
```
backend/
  indicators/
    __init__.py
    three_ten_oscillator.py
```

No `base.py` abstract class yet (YAGNI — defer until a second indicator needs it).

### 3.2 Public API

```python
# backend/indicators/three_ten_oscillator.py

OSC_FAST_COL = "osc_fast"
OSC_SLOW_COL = "osc_slow"
OSC_CROSS_COL = "osc_cross"       # -1 bearish cross, 0 none, +1 bullish cross
OSC_DIV_COL = "osc_div"           # -1 bearish div, 0 none, +1 bullish div

def compute_3_10(
    df: pd.DataFrame,
    divergence_lookback: int = 5,
    divergence_threshold: float = 0.10,
) -> pd.DataFrame:
    """
    Compute Linda Raschke's 3-10 oscillator on an OHLCV DataFrame.

    Args:
        df: DataFrame with at minimum 'high' and 'low' columns and a DatetimeIndex.
        divergence_lookback: Pivot detection window (bars before + pivot + bars after).
            Default 5 = 2 bars before + pivot + 2 bars after.
        divergence_threshold: Minimum relative separation between pivot values for
            divergence to fire (default 0.10 = 10%).

    Returns:
        Input DataFrame with 4 columns appended:
          osc_fast, osc_slow, osc_cross, osc_div
    """
```

**Contract rules:**
- Pure function: no DB writes, no logging, no side effects
- Input DataFrame is not mutated (work on a copy)
- Column name collisions: raise `ValueError` if any of the 4 output column names already exist in input
- Minimum bars required: must handle short histories gracefully (return NaN in indicator cells for insufficient bars, don't raise)
- Timeframe-agnostic: works on any bar interval from 1m to weekly

### 3.3 Math specification (per Linda Raschke canonical)

```
midpoint[i]   = (high[i] + low[i]) / 2
raw[i]        = SMA_3(midpoint)[i] - SMA_10(midpoint)[i]
osc_fast[i]   = SMA_3(raw)[i]
osc_slow[i]   = SMA_10(raw)[i]
```

Where `SMA_n(x)[i]` = arithmetic mean of `x[i-n+1..i]`.

**Implementation: use pandas `.rolling(window=n).mean()`.** Do not implement the SMA manually — pandas' rolling mean handles edge cases (NaN propagation at series start) correctly and this matters for the first 12 bars of any series.

### 3.4 Crossover detection

`osc_cross[i]`:
- +1 if `osc_fast[i] > osc_slow[i]` AND `osc_fast[i-1] <= osc_slow[i-1]` (bullish cross)
- -1 if `osc_fast[i] < osc_slow[i]` AND `osc_fast[i-1] >= osc_slow[i-1]` (bearish cross)
- 0 otherwise

First bar: `osc_cross[0] = 0` (no prior bar to compare).

### 3.5 Mechanical divergence detection (Olympus-locked)

**Pivot detection:**
A bar at index `i` is a pivot low iff `osc_fast[i]` is a local minimum within a window of `divergence_lookback` bars centered on `i`. Symmetrically for pivot high.

For default `divergence_lookback=5`, that's 2 bars before + pivot + 2 bars after. Pivot is only confirmed 2 bars later (cannot detect a pivot on the most recent bar — wait for the lookforward to complete).

**Price pivots and fast-line pivots must ALIGN** (within 1 bar of each other) for divergence comparison.

**Bullish divergence fires on bar `i` (where `i` is the bar the pivot is confirmed, i.e., 2 bars after the pivot itself) when:**
1. Price made a new `divergence_lookback`-bar low at the pivot bar
2. There exists a prior confirmed price pivot low within the last 50 bars (search back limit)
3. The fast-line pivot low at the current pivot bar is HIGHER than the fast-line pivot low at the prior price-pivot bar by ≥ `divergence_threshold` (relative: `(curr - prev) / |prev| >= threshold`)

**Bearish divergence fires symmetrically** on pivot highs (fast-line lower at current than prior).

**`osc_div[i]`:**
- +1 on the bar where bullish divergence is confirmed
- -1 on the bar where bearish divergence is confirmed
- 0 otherwise

**Edge cases:**
- Fewer than `divergence_lookback * 2 + 1` bars: `osc_div` all zeros
- No prior pivot found within 50-bar search back: that occurrence emits no divergence (flag = 0)
- Float arithmetic: compare with `math.isclose` or explicit epsilon; do NOT use `==`

### 3.6 Caching

Apply `@functools.lru_cache(maxsize=5000)` to a helper function. Since DataFrames are not hashable, the caching boundary must be:

```python
@functools.lru_cache(maxsize=5000)
def _compute_3_10_cached(
    ticker: str,
    timeframe: str,
    last_bar_timestamp: str,  # ISO string
    divergence_lookback: int,
    divergence_threshold: float,
) -> tuple:
    # internal function fetches the DataFrame given ticker/timeframe/timestamp
    # and calls the uncached math.
    ...
```

**Design note for CC:** the `compute_3_10(df, ...)` public API takes a DataFrame directly and does NOT use the cache. Callers who want caching call a different helper that takes identifiers and fetches the frame. This is intentional — pure math vs. cached IO are different concerns.

For MVP: implement the pure `compute_3_10(df, ...)` function. The cached variant can be added in Brief B when the callers exist. Leave a `TODO(brief-b)` marker in the module noting the cached variant belongs here.

### 3.7 Frequency cap self-check

Helper function `_divergence_frequency_warning(ticker, timeframe, recent_events)` that logs a warning if divergences exceed 3 per ticker per month on daily bars. MVP: write the function; it is called by Brief B integration. Returns a `bool` (warning fired yes/no) — do not log directly here, return a structured result.

---

## 4. Persistence Schema

### 4.1 `divergence_events` table

New Alembic migration (or Postgres raw SQL migration matching existing project convention — verify `backend/migrations/` or similar for the pattern):

```sql
CREATE TABLE IF NOT EXISTS divergence_events (
  id BIGSERIAL PRIMARY KEY,
  ticker TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  bar_timestamp TIMESTAMPTZ NOT NULL,
  div_type TEXT NOT NULL CHECK (div_type IN ('bullish', 'bearish')),
  fast_pivot_prev NUMERIC(12,6) NOT NULL,
  fast_pivot_curr NUMERIC(12,6) NOT NULL,
  price_pivot_prev NUMERIC(12,6) NOT NULL,
  price_pivot_curr NUMERIC(12,6) NOT NULL,
  threshold_used NUMERIC(5,4) NOT NULL,
  lookback_used INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_divergence_events_ticker_tf_ts
  ON divergence_events (ticker, timeframe, bar_timestamp DESC);

CREATE INDEX idx_divergence_events_created_at
  ON divergence_events (created_at DESC);
```

**`NUMERIC(12,6)` is mandatory** — AEGIS flagged float drift on the 10% threshold as a real risk. Do not substitute `REAL` or `DOUBLE PRECISION`.

### 4.2 Writer helper

```python
# backend/indicators/three_ten_oscillator.py or backend/indicators/divergence_store.py

def persist_divergence_event(
    ticker: str,
    timeframe: str,
    bar_timestamp: datetime,
    div_type: str,              # 'bullish' or 'bearish'
    fast_pivot_prev: Decimal,
    fast_pivot_curr: Decimal,
    price_pivot_prev: Decimal,
    price_pivot_curr: Decimal,
    threshold_used: Decimal,
    lookback_used: int,
) -> int:
    """Insert divergence event row, return new id. Uses get_postgres_client()."""
```

Use `get_postgres_client()` from `backend/database/postgres_client.py` per project convention (per memory entry 12).

**Do not call this function from `compute_3_10` directly** — that would violate the pure-function rule. Callers invoke `compute_3_10` to compute, and separately call `persist_divergence_event` for any bars where `osc_div != 0`. Brief B wires this up.

---

## 5. Unit Tests

Location: `tests/indicators/test_three_ten_oscillator.py` + `tests/indicators/test_divergence_detection.py`

### 5.1 Math correctness

- Hand-calculated SMA on a known 20-bar synthetic series (midpoint values provided as fixtures) — assert `osc_fast` and `osc_slow` match to 4 decimal places.
- Known crossover scenario (constructed data): assert `osc_cross` fires exactly once on the correct bar.
- NaN handling on short histories (bars 0–11 should have NaN in `osc_fast` / `osc_slow` positions that require rolling windows not yet full).

**⚠️ TODO for Nick (not blocking this brief):** Source 2–3 Raschke published test vectors for final validation. Math-matches-pandas-rolling is necessary but not sufficient; matching Linda's own worked examples closes the loop. Tests can be added later as `test_raschke_reference_vectors.py` once vectors are in hand.

### 5.2 Divergence synthetic cases

Build synthetic series:

1. **Classic bullish divergence:** price makes a lower low while oscillator makes a higher low. Assert `osc_div=+1` fires on the confirmation bar (2 bars after the pivot).
2. **Classic bearish divergence:** symmetric; assert `osc_div=-1` on confirmation bar.
3. **Sub-threshold separation:** fast-line pivot higher but by only 5% (below default 10% threshold). Assert `osc_div=0`.
4. **No prior pivot within 50 bars:** new pivot exists but search back finds nothing. Assert `osc_div=0`.
5. **Price pivot and fast-line pivot misaligned by >1 bar:** assert `osc_div=0`.

### 5.3 Frequency cap

Construct a series of divergence events exceeding 3/month on daily bars. Call `_divergence_frequency_warning(...)`. Assert it returns True. Verify it returns False below the threshold.

### 5.4 Input validation

- Missing `high` or `low` columns: assert `ValueError` raised
- Column-name collision on any of the 4 output columns: assert `ValueError`
- Non-DatetimeIndex input: per contract, allowed — but `osc_div` detection uses positional logic, so tests verify it works with both DatetimeIndex and RangeIndex

All tests must pass before CC commits.

---

## 6. Commit

Commit message:

```
feat(indicators): Raschke 3-10 oscillator core module + divergence_events table

Implements Titans Pass 2 §11 architecture for the 3-10 oscillator
core. Pure stateless computation, mechanical divergence detection,
and persistence schema for divergence events. Pipeline integration
(Holy Grail dual-gate, enrichment, dev view) follows in Brief B.

- backend/indicators/three_ten_oscillator.py (new package)
- divergence_events table migration
- tests/indicators/ (math + divergence + freq cap)

Refs:
- docs/strategy-reviews/raschke/titans-brief-3-10-oscillator.md (§11)
- docs/strategy-reviews/raschke/olympus-review-2026-04-22.md
- docs/codex-briefs/brief-3-10-oscillator-core.md (this brief)
```

Push to `origin/main`.

---

## 7. Constraints

- Strict scope: do not build anything from Brief B (integration, enrichment, dev view, dual-gate)
- `NUMERIC(12,6)` in the schema is non-negotiable
- Pure function rule: `compute_3_10` has zero side effects
- Do not touch Holy Grail scanner code in this brief
- Do not add Redis caching (MVP uses in-process LRU per ATHENA decision)

---

## 8. Output

Reply with:

1. Verification: does `backend/indicators/` exist already? (Expected: no.) If yes, report contents before adding to it.
2. Migration framework used (Alembic, raw SQL, Python script?) and exact path of the migration file added.
3. Commit SHA.
4. Files created / modified with line counts.
5. Test suite results — all new tests passing, plus a clean `pytest` run showing no regressions on existing tests (the pre-existing `test_no_unprotected_mutations` failure is known and unrelated).
6. Any architectural surprises or deviations from the §11 spec — if you had to deviate, justify and flag.
7. Note any `TODO(brief-b)` markers you left for the next brief.

---

**End of brief.**
