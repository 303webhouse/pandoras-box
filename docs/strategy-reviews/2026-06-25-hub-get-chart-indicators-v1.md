# Closure — `hub_get_chart_indicators` v1 (daily) → PYTHAGORAS technical feed

**Date:** 2026-06-25 · **Anchor:** main @ d26b8f6 · **Brief:** `docs/codex-briefs/hub-get-chart-indicators-v1-2026-06-25.md`
**Titans Pass 1:** ATLAS MODERATE · AEGIS HIGH · HELIOS abstain · ATHENA HIGH → PROCEED.

## What shipped
A new read-only MCP tool returning DAILY technical indicators computed hub-side from a single UW daily-OHLC pull — the same hub-side-math-on-UW-data pattern as the Black-Scholes Greeks. Closes PYTHAGORAS's "framework-only when no chart input" gap for daily levels. No TradingView webhook, no new secret.

- **Indicator modules** (`backend/indicators/`, pure-python, mirror `adx.py`): `rsi.py` (Wilder RSI+state), `atr.py` (Wilder ATR), `macd.py` (MACD 12/26/9 + an `ema_series` helper — none existed), `moving_averages.py` (SMA 20/50/120/200 + EMA-200 + stack_state + price_vs; null on insufficient bars). 11 hand-verifiable unit tests.
- **Service** `backend/services/read_only/chart_indicators.py` — one `get_ohlc(…,caller="chart_indicators")` pull; `is_unavailable` sentinel check; computes SMA stack / EMA-200 / RSI / MACD / ATR(+atr_pct) / ADX / volume(+RVOL); `indicators_source="uw_computed"`; real `as_of`; **computed** `staleness_seconds`; status ok/degraded/stale/unavailable; `vwap=null`.
- **MCP tool** `backend/hub_mcp/tools/chart_indicators.py` (mirrors `options_chain.py`) + wiring (`tools/__init__.py`, `decorators.py` whitelist).
- **PYTHAGORAS** `skills/pythagoras/SKILL.md`: added the tool as Context-A call #2; narrowed the caveat to intraday-VWAP/pivots only; deleted the stale "v2 via TradingView webhook" note.

## Governor rebalance
Added `chart_indicators: (700, TIER_FOREGROUND)`, funded by reclaim: `flow_per_expiry` 500→100 (deactivated poller standby) + `darkpool_recent` 300→100. **QUOTAS sum 17,400 → 17,500 ≤ 18,000** (verified in code + a comment). Governor default mode is `observe` (won't block yet; table correct for `enforce`).

## Phase-0 deltas (brief assumptions vs source @ d26b8f6) + live-run catches
1. `fetch_daily_ohlc` has **no `caller=` param** and returns only `{highs,lows,closes}` (drops volume/timestamps) → used the brief's documented Fallback (direct `get_ohlc` + inline normalize). **No `bars.py` edit.**
2. **No EMA helper existed** (three_ten_oscillator is SMA/pandas-based) → implemented `ema_series` pure-python in `macd.py`.
3. **UW `/ohlc/1d` returns SESSION-SPLIT rows per date** (`market_time` pr/r/po — 756 rows / ~290 sessions). The live validation caught indicators being computed on premarket/postmarket partials → **filter to regular-session (`'r'`) bars, one per date** (→ 252 true daily bars for SPY). *(Pre-existing risk flagged below.)*
4. **Date-only staleness bug:** `datetime.fromisoformat("YYYY-MM-DD")` → midnight UTC → rolls to the PRIOR ET day → today's bar false-flagged `stale`. Fixed: anchor date-only timestamps at 20:00 UTC (~16:00 ET). Daily stale rule rewritten so a forming intraday bar is NOT stale (stale only after-close-with-no-today-bar or >4 calendar days behind).

## Validation (local, live UW)
All four status paths verified + **one UW pull per call**:
- `SPY daily` → `ok`, 252 bars, real `as_of`, `staleness_seconds=667`, full set (sma200/rsi/macd/atr/adx/rvol), `uw_computed`.
- `SPY 5m` → `unavailable` + "intraday timeframe pending v1.1".
- bad ticker → `unavailable` (no fake-fresh).
- 60-bar short history → `degraded`, SMA-200/EMA-200 null + warnings.
- governor sentinel → `unavailable` (quota-block ≠ no-data).

## v1.1 deferred scope
VWAP + intraday timeframes — gated on verifying the intraday `get_ohlc` path. **Note for v1.1:** the session-split (`market_time`) discovery means intraday will need explicit session handling (pr/r/po), and VWAP needs intraday volume-weighted bars not in the daily feed.

## Discovered pre-existing risk (out of scope — flag)
`backend/indicators/bars.py` (and its sub-brief-3 consumers) do **not** filter `market_time=='r'`, so they may compute on session-split daily rows too. Not touched here (brief scope); worth a follow-up audit.

## Remaining (Nick-side, gates "done")
1. Commit + push (after-window) → **post-deploy live MCP validation** on Railway (~60–170s restart).
2. **Re-upload the full `pythagoras` folder** (incl. `references/`) to Claude.ai + **verify in a fresh chat** the tool is called and the blanket framework-only disclaimer no longer fires on a daily setup.
3. **One Olympus committee pass on SPY** confirming PYTHAGORAS reads the feed with no output regression (2026-05-21 TORO fabrication precedent).
