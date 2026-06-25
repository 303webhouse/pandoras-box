# CC Build Brief — PEAD (Post-Earnings Announcement Drift) — L1b Factor #3, Stage-1

**Date:** 2026-06-24
**Lane:** L1b canonical factor strategies (author → Anti-Bloat → backtest)
**Planner:** Claude (Opus) — Anti-Bloat + data feasibility cleared this session
**Builder:** Claude Code (VSCode)
**Status going in:** Anti-Bloat CLEARED (distinct directional lens) · data feasibility CONFIRMED · Stage-1 NOT YET RUN
**Mode:** OFFLINE RESEARCH ONLY — no DB, no migrations, no production writes. New standalone script in C:\temp, same pattern as momentum_backtest.py.

---

## 0. Context — already decided, do not re-derive

- PEAD = post-earnings announcement drift: a stock keeps drifting in the direction of its earnings SURPRISE for weeks after the report (under-reaction; Ball-Brown 1968, Bernard-Thomas 1989/90).
- **Anti-Bloat: CLEARED.** The only existing earnings work (earnings-gap-characterization, gap-convexity-options-validation) is NON-directional long-vol (straddle/strangle on the secondary move) and mostly failed in options terms. PEAD is a DISTINCT lens — directional drift, one-sided debit spread. Do NOT re-litigate; it advanced.
- L1b factor #3. #1 RSI-2 (cleared Stage-1 → FAILED Stage-2). #2 Momentum 12-1 (REJECTED Stage-1). Same gate, one at a time.

## 1. Objective

Run a Stage-1 (UNDERLYING-returns) backtest of PEAD and produce a documented SURVIVES / FAILS-vs-neutral-baseline verdict, in the exact format of docs/strategy-reviews/2026-06-22-L1b-momentum-12-1.md.

## 2. The make-or-break rule — entry AFTER the gap

**Entry = first close AFTER the announcement gap, never before.** The gap is the announcement reaction (already covered by the gap study). PEAD's edge is the UNDER-reaction — the drift AFTER the initial move. Conflating gap + drift invalidates the test.

Entry-timing alignment by UW `report_time`:
- `postmarket`: released after close on report_date → reaction is report_date+1. T0 (entry) = CLOSE of report_date+1.
- `premarket`: released before open on report_date → reaction is report_date. T0 (entry) = CLOSE of report_date.
- `null/unknown`: default to postmarket (assume next-session reaction); log the null count. If >10% of sample, flag it.
- Drift is always measured T0 → T0+k.

## 3. Data

- **Earnings + surprise:** UW `get_earnings_history(ticker, report_type='quarterly')` → report_date, report_time, reported_eps, estimated_eps, surprise, surprise_percentage. One call = full per-ticker history. Estimates (hence surprise) reliably populated ~2004→present; DROP events with null estimated_eps/surprise. One call per universe name.
- **Daily prices:** yfinance daily bars, `auto_adjust=True` (TOTAL RETURN). OFFLINE-RESEARCH carve-out — NOT a hot path, so it does not trip the UW-primary hot-path rule; consistent with prior L1b Stage-1 work and the Stage-2 research carve-out. NOTE: Stage-1 measures UNDERLYING returns, so ADJUSTED closes are CORRECT here — the unadjusted-close rule applies only to options pricing at Stage-2, not this build.
- **Universe:** ~200-500 liquid, optionable US large-caps (current S&P 500 membership or a stable liquid set). Breadth is MANDATORY — momentum XS proved this kind of edge dies in small baskets. v0 caveat: current-membership = survivorship bias; acceptable for a first read but MUST be flagged in the doc as a v1 fix (point-in-time membership).

## 4. Method

- Per name: pull earnings, drop null-surprise events, compute T0 per the report_time rule (Section 2).
- Forward drift returns T0 close to T0+k close for **k = 20, 40, 60 trading days** (classic PEAD horizons), adjusted closes.
- **Decile formation (POINT-IN-TIME — mandatory):** rank each event into deciles using ONLY surprises observed up to that event's date (rolling/expanding cross-section) — NEVER the full-sample distribution. Full-sample pooling is look-ahead bias and the single most likely source of a falsely-strong result (ties to the Section 6 red flag). Equal-weight events within decile; document the rolling window.
- **Core tests (mirror momentum XS structure):**
  1. **Top-minus-bottom decile spread** (D10 minus D1) forward return per horizon — the clean beta-stripped test of the drift edge.
  2. **Long-only top decile vs (a) equal-weight-all-events and (b) SPY buy&hold** over matched windows — alpha or just beta?
- **Sub-period robustness:** at least 3 regimes (e.g., 2004-09 / 2010-19 / 2020-26); report spread + long-only per regime. One-regime-only edge = fragile.
- **Concentration check:** does the edge hold broadly, or only in the most extreme surprises? (Yellow flag from the gap study — monster surprises often reverse.)
- Grade in UNDERLYING total-return terms (CAGR/Sharpe/maxDD summary, momentum-doc style). No options modeling — Stage-2 only if this clears.

## 5. Deliverables

1. `C:\temp\pead_backtest.py` — standalone, reproducible (pandas/numpy/yfinance + UW earnings). Print a clean summary table.
2. `docs/strategy-reviews/2026-06-24-L1b-pead-stage1.md` — same structure as the momentum Stage-1 doc (Factor / Spec / Anti-Bloat [CLEARED upstream, summarize] / Stage-1 tables / Status+next / verdict).
3. Validation note: confirm a couple of surprise values + price points against an independent source (StockAnalysis/Yahoo) before claiming numbers.

## 6. Verdict rule (Done def)

- **CLEARED → Stage-2** (options harness, ~30-60 DTE directional spread, NOT 8-21 DTE) IF: top-minus-bottom decile drift materially positive AND robust across sub-periods AND long-only top decile beats SPY (real alpha).
- **REJECTED** → logged with reason, no Stage-2 (spread ~ 0, or = beta, or not robust, or edge only in the extreme-surprise tail).
- **Red flag:** implausibly strong Stage-1 drift → suspect look-ahead in entry-timing/decile logic; investigate before documenting CLEARED.

## 7. Guardrails

- OFFLINE only. No DB, no migrations. Stage-1 is self-contained price/earnings math — it should need NO imports from b2_options_resolver.py / a3_options_pnl_resolver.py (those are Stage-2 options helpers); do not pull production options modules into this script. Shadow-by-default.
- **Credentials (AEGIS):** read UW_API_KEY from the existing env/config (same pattern as other scripts) — never hardcode it, never print/log it. Read-only research use; no new credential surface.
- Git: cmd shell, explicit pathspecs (never `git add .`), commit msg via C:\temp\commitmsg.txt + `git commit -F`. No push to main 07:30-14:00 MT.
- Phase-0 first: confirm UW field shapes + yfinance bar availability on a sample of the universe BEFORE the full run.
