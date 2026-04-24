# CC Build Brief — Raschke 3-10 Day-0 Calibration Fixes

**Upstream context:** Day-0 verification queries run 2026-04-24 surfaced two calibration issues in the Raschke 3-10 MVP (shipped 2026-04-23, commit `801ec8b`). Both are non-regressing — they're scope items Phase 1-4 deferred as "acceptable for MVP, calibrate later."

**Build type:** Two small fixes bundled. ~1-2 hours CC work total.

**Upstream evidence:**
- `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` — URSA frequency cap rule, THALES sector-rotation tag requirement
- Day-0 query results summarized inline below

---

## Prime Directives

1. **Read `PROJECT_RULES.md` and `CLAUDE.md` at repo root before touching code.**
2. **Do NOT change the math of `compute_3_10`.** Only parameters and the sector map.
3. **Do NOT modify Holy Grail scanner logic.** Changes are scoped to `backend/indicators/`.
4. **No new DB migrations.** The tables and columns already exist.
5. **All find/replace anchors are copy-paste-verbatim. If a string has drifted, STOP and ask Nick.**


---

## Issue 1 — Divergence threshold over-firing on 1h bars

### Evidence from Day-0 query (last 30 days, all 1h timeframe)

```
Top tickers by divergence count:
  KREF     total=20   bull=10  bear=10
  LPTH     total=20   bull=10  bear=10
  VZ       total=19   bull=10  bear=9
  XOM      total=19   bull=9   bear=10
  CRM      total=19   bull=8   bear=11

Timeframe distribution: 8,743 events on 1h, 0 on daily.
```

URSA's frequency cap rule from Olympus 2026-04-22: divergences should fire ≤3/month per ticker, or the rule is detecting noise. On 1h bars we're seeing 19-20/month per ticker — ~6-7x over threshold.

### Root cause

`DEFAULT_DIVERGENCE_THRESHOLD = 0.10` (10%) in `backend/indicators/three_ten_oscillator.py`. This threshold was chosen for daily bars where oscillator pivots are larger and more meaningful. On 1h bars, oscillator noise is much higher, so 10% separation between successive pivot points fires constantly.

### Fix — Timeframe-aware threshold

Update `compute_3_10` so the caller can pass a timeframe hint OR the threshold auto-scales by timeframe. The cleanest approach: keep the existing signature (backward compatible) and add an optional `timeframe` kwarg that selects a calibrated threshold.

**EXACT FIND/REPLACE ANCHOR** in `backend/indicators/three_ten_oscillator.py`:

**FIND:**

```python
# Default parameters per Raschke spec.
DEFAULT_DIVERGENCE_LOOKBACK = 5
DEFAULT_DIVERGENCE_THRESHOLD = 0.10  # 10%
PIVOT_WINDOW = 2  # Bars before and after pivot candidate (total window = 5 bars)
```

**REPLACE WITH:**

```python
# Default parameters per Raschke spec (calibrated post-Day-0 verification 2026-04-24).
DEFAULT_DIVERGENCE_LOOKBACK = 5
DEFAULT_DIVERGENCE_THRESHOLD = 0.10  # 10% — canonical Raschke daily default
PIVOT_WINDOW = 2  # Bars before and after pivot candidate (total window = 5 bars)

# Timeframe-calibrated thresholds. Day-0 verification showed the canonical 10%
# threshold over-fires on intraday bars (~20 events/month/ticker on 1h vs URSA's
# <3/month cap). Wider thresholds for noisier intraday frames keep the signal
# meaningful. Revisit at Day-30 cadence check with real post-deploy data.
TIMEFRAME_DIVERGENCE_THRESHOLDS = {
    "1m":   0.25,   # very noisy
    "5m":   0.22,
    "15m":  0.20,
    "30m":  0.18,
    "1h":   0.15,   # Day-0 data: 10% gave ~20/mo/ticker, target <3/mo
    "4h":   0.12,
    "1d":   0.10,   # canonical Raschke default
    "1w":   0.08,   # wider windows, cleaner pivots
}
```


**EXACT FIND/REPLACE ANCHOR** in `backend/indicators/three_ten_oscillator.py`:

**FIND:**

```python
def compute_3_10(
    df: pd.DataFrame,
    divergence_lookback: int = DEFAULT_DIVERGENCE_LOOKBACK,
    divergence_threshold: float = DEFAULT_DIVERGENCE_THRESHOLD,
) -> pd.DataFrame:
```

**REPLACE WITH:**

```python
def compute_3_10(
    df: pd.DataFrame,
    divergence_lookback: int = DEFAULT_DIVERGENCE_LOOKBACK,
    divergence_threshold: float | None = None,
    timeframe: str | None = None,
) -> pd.DataFrame:
    """
    [existing docstring preserved]

    Day-0 calibration (2026-04-24): `timeframe` kwarg selects a calibrated
    threshold from TIMEFRAME_DIVERGENCE_THRESHOLDS. Passing `divergence_threshold`
    explicitly overrides. If neither is provided, falls back to the canonical
    Raschke 10% default (suitable for daily bars).
    """
    # Resolve effective threshold: explicit override > timeframe lookup > default
    if divergence_threshold is None:
        if timeframe and timeframe in TIMEFRAME_DIVERGENCE_THRESHOLDS:
            divergence_threshold = TIMEFRAME_DIVERGENCE_THRESHOLDS[timeframe]
        else:
            divergence_threshold = DEFAULT_DIVERGENCE_THRESHOLD
```

**Note:** The rest of `compute_3_10` should be unchanged. The function body that uses `divergence_threshold` in its divergence detection should continue working with the resolved value.

### Update the Holy Grail scanner caller

**EXACT FIND/REPLACE ANCHOR** in `backend/scanners/holy_grail_scanner.py`:

**FIND:**

```python
    # 3-10 Oscillator (Raschke) — shadow-mode dual-gate companion to RSI
    try:
        from indicators.three_ten_oscillator import compute_3_10
        df = compute_3_10(df)
    except Exception as e:
        logger.warning("3-10 oscillator compute failed; continuing RSI-only: %s", e)
```

**REPLACE WITH:**

```python
    # 3-10 Oscillator (Raschke) — shadow-mode dual-gate companion to RSI
    try:
        from indicators.three_ten_oscillator import compute_3_10
        # Holy Grail runs on 1h bars — use calibrated threshold per Day-0 finding
        df = compute_3_10(df, timeframe="1h")
    except Exception as e:
        logger.warning("3-10 oscillator compute failed; continuing RSI-only: %s", e)
```

### Unit test — add one case

Add a test to `backend/tests/indicators/test_three_ten_oscillator.py` verifying:
- `compute_3_10(df, timeframe="1h")` uses `0.15` as threshold
- `compute_3_10(df, timeframe="1d")` uses `0.10` as threshold
- `compute_3_10(df, divergence_threshold=0.25)` uses `0.25` (explicit override wins)
- `compute_3_10(df, timeframe="unknown")` falls back to `0.10` (default)

Mock or spy on `_detect_divergences` to inspect the threshold passed through.


---

## Issue 2 — Sector map coverage gap

### Evidence from Day-0 query (last 2 hours)

```
total recent signals:              26
with sector_3_10 field present:    26   (schema good)
with sector_3_10 populated:         2   (only 8% coverage)
```

Top tickers with divergences today (KREF/LPTH/VZ/XOM/CRM/KRMN/SNOW/ELIL/MAN/NVD) are mostly NOT in the current hardcoded `_DEFAULT_SECTOR_MAP`. Only mega-caps and a few known names map successfully. Non-mapped → null sector enrichment → THALES sector-rotation tag mostly missing in production.

### Fix approach

Expand `_DEFAULT_SECTOR_MAP` in `backend/indicators/sector_rotation_3_10.py` to cover:

1. All 10 tickers in the Phase 0.5 logger watchlist (`config/uw_logger_watchlist.yaml`)
2. The top ~60 tickers actually appearing in production signals (from DB query below)
3. All tickers in the current dashboard watchlist

### CC Task

**Step 1 — Query production to identify coverage gaps:**

```sql
SELECT ticker, COUNT(*) as signal_count
FROM signals
WHERE created_at > NOW() - INTERVAL '7 days'
  AND (enrichment_data -> 'sector_3_10' IS NULL
       OR enrichment_data -> 'sector_3_10' = 'null'::jsonb)
GROUP BY ticker
ORDER BY signal_count DESC
LIMIT 80;
```

Run this against Railway (DSN per memory) and capture the ticker list.

**Step 2 — Classify each ticker to its SPDR sector ETF.**

Use this reference table (stable S&P sector classifications as of 2026):

- **XLK (Tech):** AAPL, MSFT, NVDA, AVGO, ORCL, CRM, CSCO, ADBE, AMD, QCOM, INTU, TXN, IBM, NOW, PANW, MU, ADI, AMAT, LRCX, KLAC, MRVL, SNPS, CDNS, ANET, FTNT, SNOW
- **XLC (Comm):** GOOGL, GOOG, META, NFLX, DIS, T, VZ, CMCSA, TMUS, CHTR
- **XLY (Cons Disc):** AMZN, TSLA, HD, MCD, NKE, LOW, BKNG, TJX, SBUX, ABNB, F, GM
- **XLP (Cons Stap):** PG, COST, WMT, KO, PEP, PM, MO, MDLZ, CL, KMB
- **XLF (Fin):** JPM, BAC, WFC, GS, MS, C, BLK, AXP, SCHW, SPGI, V, MA, PGR, CB, PYPL, COIN
- **XLV (Health):** UNH, JNJ, LLY, PFE, ABBV, MRK, TMO, ABT, DHR, AMGN, BMY, GILD, ISRG, ELV, CVS, NVS
- **XLE (Energy):** XOM, CVX, COP, SLB, OXY, EOG, PSX, MPC, VLO, HES
- **XLI (Industrial):** CAT, HON, UNP, DE, RTX, LMT, UPS, BA, GE, GEV, MMM, NOC, ETN
- **XLU (Utilities):** NEE, SO, DUK, AEP, SRE, D
- **XLB (Materials):** LIN, FCX, NEM, APD, DD, DOW, SHW
- **XLRE (Real Estate):** PLD, AMT, EQIX, CCI, WELL, SPG, O
- **SPY/QQQ/IWM/DIA (Index ETFs):** Map to "INDEX" (special sentinel) — THALES should treat these as sector-agnostic, NOT map to any single sector ETF.

Add an `INDEX` special key handling: if mapped value is `"INDEX"`, the enrichment function returns `None` (not an error — intentional signal that sector-rotation context doesn't apply).


**Step 3 — Update `_DEFAULT_SECTOR_MAP` in `backend/indicators/sector_rotation_3_10.py`**

Expand the existing dict to cover all tickers from Step 1 query plus the reference table in Step 2. Aim for 80-100 entries total. Organize alphabetically by ETF with comments for readability.

For any ticker in the Step 1 query results that's NOT in the reference table above (obscure small-caps, ETFs we don't know, etc.), leave it out of the map rather than guessing wrong. `get_sector_3_10_for_ticker` returns `None` for unmapped tickers, which is the correct behavior.

**Step 4 — Handle the `INDEX` sentinel in `get_sector_3_10_for_ticker`:**

**EXACT FIND/REPLACE ANCHOR** in `backend/indicators/sector_rotation_3_10.py`:

**FIND:**

```python
    sector_etf = _DEFAULT_SECTOR_MAP.get(ticker.upper())
    if not sector_etf:
```

**REPLACE WITH:**

```python
    sector_etf = _DEFAULT_SECTOR_MAP.get(ticker.upper())
    # INDEX sentinel: mapped but intentionally sector-agnostic (SPY, QQQ, etc.)
    if sector_etf == "INDEX":
        return None
    if not sector_etf:
```

### Unit test — add coverage cases

Add tests verifying:
- `get_sector_3_10_for_ticker("NVDA")` returns an XLK reading
- `get_sector_3_10_for_ticker("JPM")` returns an XLF reading
- `get_sector_3_10_for_ticker("SPY")` returns `None` (INDEX sentinel)
- `get_sector_3_10_for_ticker("UNKNOWN_TICKER")` returns `None` (unmapped)

---

## Verification

After both fixes land, the agent should re-run the Day-0 verification queries:

```sql
-- Divergence rate should drop significantly after next 1h HG scan
SELECT ticker, COUNT(*) FROM divergence_events
WHERE timeframe = '1h' AND created_at > NOW() - INTERVAL '30 days'
GROUP BY ticker ORDER BY 2 DESC LIMIT 10;

-- Sector enrichment coverage should jump to 70-90%
SELECT
  COUNT(*) FILTER (WHERE enrichment_data -> 'sector_3_10' IS NOT NULL
                      AND enrichment_data -> 'sector_3_10' != 'null'::jsonb) AS populated,
  COUNT(*) AS total
FROM signals WHERE created_at > NOW() - INTERVAL '2 hours';
```

Note: divergence rate change won't be immediately obvious because historical rows persist. Track going forward via `created_at` after deploy time.

---

## Commit & Merge

Branch: `feature/raschke-day0-calibration`

Commit message:

```
fix(raschke): Day-0 calibration — timeframe-aware divergence threshold + expanded sector map

Day-0 verification 2026-04-24 (ref: docs/strategy-reviews/raschke/olympus-review-2026-04-22.md
URSA frequency cap rule) found 1h divergences firing ~20x/month per ticker vs
<3/month target, and only ~8% of production signals getting sector enrichment.

Fix 1 — TIMEFRAME_DIVERGENCE_THRESHOLDS dict calibrates per-bar-size. 1h defaults
to 0.15, daily stays at Raschke canonical 0.10. HG scanner passes timeframe="1h".

Fix 2 — _DEFAULT_SECTOR_MAP expanded from ~15 to ~80 tickers covering full
production watchlist. INDEX sentinel added for SPY/QQQ/etc. (sector-agnostic).

No scanner logic changes. No new migrations. Backward compatible.
```

Push to origin, open PR, do NOT merge — Nick reviews before merge.


---

## Output to Nick

1. Branch HEAD SHA + PR link
2. Full test suite output (expect baseline + 4-5 new tests passing)
3. Divergence threshold: value of `compute_3_10(df, timeframe='1h').attrs` or equivalent showing 0.15 was used
4. Sector map: final ticker count, sample lookups (NVDA, JPM, SPY, UNKNOWN)
5. Any surprises or scope-creep tempted but not taken

---

## Constraints

- Strict scope: only the two calibration items. Do NOT touch `feed_tier_classifier.py`, Holy Grail signal logic, or any other scanner file.
- Do NOT modify the divergence detection algorithm. Only the threshold parameter flow.
- INDEX sentinel is a thin add — don't over-engineer (no enum, no special class, just a string check).
- Don't touch the Phase 0.5 forward-logger scripts — separate workstream, separate branch.

---

**End of brief.**
