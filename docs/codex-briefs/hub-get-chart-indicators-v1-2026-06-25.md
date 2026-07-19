# BRIEF — `hub_get_chart_indicators` v1 (daily-only) → PYTHAGORAS live technical feed

**Recon anchor:** `origin/main` @ `d26b8f6`.
**Titans Pass 1:** ATLAS MODERATE · AEGIS HIGH · HELIOS abstain · ATHENA HIGH → PROCEED.
**Scope:** Daily-only v1. VWAP / intraday is OUT (v1.1, gated on verifying the intraday `get_ohlc` path).

## Purpose
Close PYTHAGORAS's "framework-only when no chart input" gap. An MCP tool returning standard technical indicators computed hub-side from UW **daily** OHLC — SMA stack (CTA zones), EMA, RSI, MACD, ATR, ADX, volume/RVOL. No TradingView webhook, no new secret; hub-side-math-on-UW-data (mirrors Black-Scholes Greeks `greeks_source`). Mirrors `hub_get_options_chain` structurally.

## Tasks (summary — see CC session for full text)
- **Task 1:** pure indicator modules in `backend/indicators/` (rsi, atr, macd, moving_averages), mirror `adx.py`; chronological arrays in, latest+series out, no fetch inside; unit tests per module.
- **Task 2:** `backend/services/read_only/chart_indicators.py` → `get_chart_indicators(ticker, timeframe="daily")`. daily-only (other → unavailable + "intraday pending v1.1"). ONE `get_ohlc` pull; `is_unavailable` sentinel check; compute all indicators; `indicators_source="uw_computed"`; real `as_of` + computed `staleness_seconds`; status ok/degraded/stale/unavailable; `vwap=null`.
- **Task 3:** `backend/hub_mcp/tools/chart_indicators.py` mirroring `options_chain.py` (`@mcp_tool`, validate ticker+timeframe, `make_response`, `_summary`).
- **Task 4:** wiring — `tools/__init__.py` import, `decorators.py` REGISTERED_TOOL_NAMES, `uw_governor.py` QUOTAS (`chart_indicators`:(700,FOREGROUND), reclaim flow_per_expiry 500→100 + darkpool_recent 300→100; sum ≤18,000).
- **Task 5:** `skills/pythagoras/SKILL.md` — add tool to Context-A, narrow the caveat, delete TradingView-webhook note; re-upload full folder + verify in a fresh chat.

## CC Phase-0 deltas (2026-06-25, verified against source @ d26b8f6)
1. `fetch_daily_ohlc(ticker, lookback_sessions=60)` has NO `caller=` param and returns only `{highs,lows,closes}` (drops volume/timestamps). → use the documented Fallback: `get_ohlc(ticker,"1d",caller="chart_indicators",lookback_days≈300)` directly + normalize inline. No `bars.py` edit.
2. No EMA helper exists (three_ten_oscillator is SMA/pandas-based). → implement EMA pure-python in `macd.py`.
3. New modules written pure-python (match `adx.py`), not pandas — no new dependency.
- Governor: current QUOTAS sum = 17,400 → 17,500 after the rebalance (≤18,000 ✓).

## Gates
Daily-only. No `/technical-indicator`. No new deps. No net-add UW quota. `get_ohlc` only (no raw `_uw_request`/httpx/yfinance). No hardcoded `staleness_seconds`; no indicator on insufficient bars. No raw-UW logging; `make_response` only. No push to `main` 07:30–14:00 MT.

## Done
Service boots; `hub_get_chart_indicators("SPY","daily")`→ok full set; degraded (short-history→SMA200 null); unavailable (bad ticker/sentinel); non-daily→unavailable+v1.1; ONE UW pull/call (by_caller); QUOTAS≤18,000; live-validated post-deploy; PYTHAGORAS SKILL.md updated + re-uploaded + fresh-chat verified; Olympus committee retest on SPY; closure note in docs/strategy-reviews/.
