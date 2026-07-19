# CC Build Brief — bars.py regular-session (`market_time == 'r'`) filter

**Repo / branch:** `303webhouse/pandoras-box` @ `main` (recon'd against `2617c31`)
**Size:** ~5-line change, one file. No schema, no new deps, no new bar path.
**Urgency:** Low for live (shadow-only blast radius) — but a **hard prerequisite for the ADX-regime Chunk-3 promote decision.** See Sequencing.

## Why
`backend/indicators/bars.py::fetch_daily_ohlc()` is the bar reader for the SPY ADX-regime shadow job (`backend/jobs/adx_regime_job.py`, `fetch_daily_ohlc("SPY", lookback_sessions=60)` → writes `regime:spy_adx_shadow`). UW's `/ohlc/1d` returns SESSION-SPLIT rows per date (`market_time` = pr/r/po). `fetch_daily_ohlc()` appended every row with no filter → ADX(14) computed on premarket/postmarket partials, not clean daily bars. Every other UW-daily consumer (`chart_indicators.py`, `uw_api._get_bars_via_uw`, `sector_constituent_refresh.py`, `earnings_gap_backtest.py`) already filters to `'r'`; bars.py was the holdout.

## The change
`backend/indicators/bars.py` → `fetch_daily_ohlc`: add, at the top of the `for b in bars:` loop, before the try:
```python
        if (b.get("market_time") or "").lower() != "r":
            continue
```
(Verbatim form from `chart_indicators.py`.)

## Verification (done — local, live UW)
- `fetch_daily_ohlc("SPY", 60)` → **251 clean 'r' bars** (was ~3× that in mixed pr/r/po rows), ADX(14)=**23.77** (sane, valid 0–100), returns a dict. NOTE: bar count is ~251 not the brief's ~73 estimate — UW returns ~1yr regardless of the `lookback_days=106` request; harmless (further above ADX's ~28-bar warmup). Post-deploy: read `regime:spy_adx_shadow` after the next RTH `adx_regime_job` run; cross-check vs a TradingView SPY daily ADX(14).

## Sequencing
Shadow-only blast radius (`regime:spy_adx_shadow` has zero live-scoring impact; the live gate reads `regime:spy_adx`, absent → default-25 → 'trending'). It gates the ADX-regime Chunk-3 promote decision: that decision leans on the shadow's regime history, which until now was written on session-split garbage. The fix does NOT backfill — only post-deploy writes are clean, so there's a re-accumulation window. Shipping sooner starts the clean-data clock sooner; land it before scoring the promote decision.

## Out of scope
No change to `adx_regime_job.py` / `adx.py` / the regime classifier; no change to the live `regime:spy_adx` path; VWAP/intraday session handling; the shadow→live promotion itself.

## Status: SHIPPED 2026-06-29 (commit on main; pushed after-window).
