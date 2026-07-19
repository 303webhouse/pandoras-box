# BUILD BRIEF — stage2_options_backtest (L1b Stage-2 options-P&L measurement harness)

**Date:** 2026-06-23
**Lane:** L1b canonical factor strategies — the Stage-2 measurement gate
**Status:** Titans-reviewed (ATLAS / DAEDALUS / THALES / ATHENA) 2026-06-23 → PROCEED, MODERATE-HIGH, no vetoes. Validation gate (Step 5) is NON-ARBITRABLE.
**Builder:** Claude Code (CC) in VSCode. Plan authored in Opus.

---

## 0. TL;DR for CC

Build an **offline pure-Python harness** that grades an L1b factor's Stage-1 trade list as an OPTIONS strategy: model per-trade options-P&L (30-delta debit spread, BS-priced) → beta-strip vs a same-model SPY control → report a recent GEX-gated slice → compare to a neutral baseline. **First run: RSI-2.** No DB, no migration, no live-flow touch. Output = a strategy-review doc.

This is NOT "B2 the trading bucket" and NOT the live `b2_options_resolver.py` (which is a *forward* collector). This is a *historical backtest* layer. Different artifact, different name.

---

## 1. Why (condensed)

L1b factor promotion is gated on a two-stage test. Stage-1 (standalone backtest on the underlying) works — RSI-2 cleared it (commit `2d7d0eb`): 71–82% win, PF 2.0–2.5, SURVIVES 2000–2026 on SPY+QQQ. Stage-2 grades the factor in **options-P&L + beta-stripped alpha + a GEX-gated read** — and that historical measurement layer does not exist. Every L1b factor (RSI-2 now, Momentum 12-1 next) parks at this wall. Build this and the pipeline moves. The platform's anti-bloat standard is "judged in options-P&L with a GEX gate, not raw underlying returns" — this harness IS that judge, so a plausible-but-mis-modeled P&L number is the P0 risk class.

---

## 2. HARD CONSTRAINTS (read before writing any code)

1. **Offline only.** Do NOT write to `signals`, `signal_outcomes`, `signal_options_expressions`, or any DB table. No `CREATE TABLE` (Railway Postgres is ~94% full — headroom pre-flight would block it). This harness reads files + APIs and writes files only.
2. **Do NOT modify** the live `backend/jobs/b2_options_resolver.py` or `backend/jobs/a3_options_pnl_resolver.py`. REUSE their pure helpers by importing or copying — never edit them.
3. **Separate entry-date IV and exit-date IV. Always.** Never average or flatten the IV path. RSI-2 enters on a dip (IV elevated/fear) and exits on the snap-back (IV normalizes); a flat IV will overstate P&L. This is the single most important correctness rule (DAEDALUS).
4. **yfinance is permitted here.** This is offline research infra, and UW has no pre-2020 coverage, so yfinance for deep-history bars + VIX/VXN is the explicit, approved carve-out from the UW-first hierarchy (ATLAS). It does NOT generalize to any live/hot path.
5. **Universe = SPY, QQQ only.** No-slippage and BS-mid fills are blessed for SPY/QQQ specifically (penny-wide, deepest options on earth). The day the universe expands beyond SPY/QQQ, slippage must be modeled and the >10% bid-ask flag applies (DAEDALUS).
6. **Git discipline.** `cmd` shell for git (NOT PowerShell), `cd /d C:\trading-hub`. Explicit pathspecs only — never `git add .`. Commit message via `C:\temp\commitmsg.txt` + `git commit -F`. No-deploy window (07:30–14:00 MT) is N/A here — nothing deploys.

---

## 3. STEP 0 — locate reuse targets (read-only, no permission needed)

**a. BS engine.** Grep `backend/` for the hub's existing Black-Scholes implementation (the one producing `greeks_source: "bs_computed"` referenced in DAEDALUS's tooling — likely in `backend/integrations/uw_api.py` or a greeks util). REUSE it for leg pricing so the historical harness and the live Greeks use the SAME engine. If nothing is cleanly importable, implement standard BS (European, zero-dividend) via `scipy.stats.norm` with explicit d1/d2. Price = call value for long-direction factors.

**b. Confirm the UW IV coverage wall.** Via `railway run --service pandoras-box python`, probe `/api/stock/SPY/interpolated-iv?date=` and `/api/stock/SPY/volatility/stats?date=` (and QQQ) at `2022-01-03`, `2021-01-04`, `2020-01-02`. Record the EARLIEST date that returns HTTP 200 with data. That date = the **Tier-A / Tier-B boundary**. (Probe on 2026-06-23 already confirmed coverage ≥4 months back, fields: `volatility/stats.iv` = ATM IV decimal; `interpolated-iv` rows give `volatility` by `days` (DTE).)

**c. Reuse the live options-expression logic.** Read `backend/jobs/b2_options_resolver.py` and reuse verbatim: `_option_type(direction)`, `_spread_width(underlying_price)` + its `_WIDTH_TIERS` ($100→$5 / $20→$2.5 / else $1), `_find_expiry(signal_date)` (first Friday in 8–21 days), and the long-leg "closest abs(delta) to 0.30, fallback ~2% OTM" rule. Historical and forward expressions MUST match for apples-to-apples.

---

## 4. STEP 1 — extend Stage-1 to emit a trade ledger (REQUIRED precursor)

`C:\temp\rsi2_backtest.py` currently records each trade as `{ret, hold, mfe, mae, why}` — **no dates, no prices, no ticker, and it does not persist anything** (prints summary stats only). Options pricing needs dates + prices + ticker.

- At the two `trades.append(...)` sites in `backtest()`, also store: `ticker`, `entry_date = rows[ei][0]`, `entry_close = c[ei]`, `exit_date = rows[i][0]`, `exit_close = c[i]`.
- Add a writer that dumps the pooled trade list to `C:\temp\rsi2_stage1_trades.csv` with columns: `ticker, entry_date, entry_close, exit_date, exit_close, hold, exit_reason, underlying_ret`. Emit all four configs (entry <5 / <10 × exit sma5 / rsi70), tagged in a `config` column, so Stage-2 can grade the chosen one and Nick can compare.
- Keep it pure-stdlib + yfinance. Do NOT restructure the backtest logic — only add fields + the CSV writer.

---

## 5. STEP 2 — the harness: `scripts/stage2_options_backtest.py`

Offline script. Parameterize: input ledger path, factor name, the IV-wall date (from Step 0b), risk-free rate.

For each trade in the ledger:
1. **Strike selection.** Underlying spot at entry = `entry_close`. Long strike via the 0.30-delta rule (approximate delta from BS using entry-date IV + spot + DTE); fallback ~2% OTM call. Short strike = long + width (price tier). Expiry/DTE via `_find_expiry(entry_date)`.
2. **Entry IV.** If `entry_date >= wall` → Tier B: UW `interpolated-iv` at the trade's DTE for that ticker (via `railway run`). Else → Tier A: VIX (SPY) / VXN (QQQ) that date's close ÷ 100, from yfinance.
3. **Entry price.** `BS(long) − BS(short)` with entry-date IV, `r` = risk-free (constant 4% for v1 — flag as a v1 simplification; FRED 3M series is a later refinement).
4. **Exit.** At `exit_date`, re-price both legs with **EXIT-date IV** (same Tier rule), exit spot = `exit_close`, same strikes, DTE reduced by `hold` trading days. `options_pnl = (exit_spread − entry_spread) × 100 × contracts(=1)`.
5. **Record per-trade:** dates, strikes, DTE, entry/exit spread, entry/exit IV, `options_pnl`, `underlying_ret`, IV-tier used.

**Aggregate:** total options-P&L, win%, profit factor, avg/trade, maxDD on the options-P&L equity curve.

**ATM-IV only for v1** (skew refinement deferred per Nick 2026-06-23 — add UW 25-delta `historical_risk_reversal_skew` ONLY if Step 5 shows the overlap error >~5% of spread value).

## 6. STEP 3 — beta-strip (same-model SPY control)

Run the IDENTICAL options model on a SPY control matched to the factor's trade cadence: for each factor trade window, open the same-structure SPY debit spread at `entry_date`, close at `exit_date`. Control options-P&L = the market's contribution. **Factor alpha = factor options-P&L − control options-P&L**, per-trade and aggregate. Document explicitly: this same-model control is the honest strip for options — a regression beta on option P&L is NOT valid (options aren't linear in SPY beta). Cross-check sign/magnitude against the underlying-level beta-strip the June-5 audit computes.

## 7. STEP 4 — GEX-gated slice (recent window only)

For trades whose `entry_date` falls within UW GEX coverage (~last 1yr per `backend/bias_filters/gex.py`, which reads UW `/greek-exposure` ≈251 daily rows), tag the SPY net-GEX sign at entry (reuse gex.py's compute path or pull `/greek-exposure` directly). Report the +GEX-only subset's options-alpha **separately, labeled DIRECTIONAL-ONLY (small N)**. Do NOT proxy GEX for the deep history. Do NOT gate the headline number on GEX. (GEX history does not reach the backtest horizon — this is a known hard constraint, not a gap to paper over.)

## 8. STEP 5 — validation gate (NON-ARBITRABLE — ATLAS + DAEDALUS)

On the Tier-B overlap window:
- **a. Proxy-vs-UW.** Re-run pricing with VIX/VXN proxy IV vs UW IV; report the per-trade and aggregate P&L delta. This bounds the Tier-A (deep-history) modeling error.
- **b. Modeled-vs-real.** Where UW has the actual contract (`/option-contract/{id}/historic`, reached via `/stock/{ticker}/option-chains?date=` to resolve the symbol as-of the entry date), pull a sample of real spread marks and compare to BS-mid. Report the error band.

If either error is large (flag threshold ~>20% of mean P&L), **STOP and surface to Nick** before the Stage-2 verdict is treated as real. Fake-healthy P&L masquerading as a clean number is the P0 failure here.

## 9. STEP 6 — output doc

Write `docs/strategy-reviews/2026-06-23-L1b-rsi2-stage2.md`, same shape as the Stage-1 pilot doc (`docs/strategy-reviews/2026-06-22-L1b-rsi2-pilot.md`):
- Options-P&L table — **full history, ungated** (the headline).
- Beta-stripped options alpha (vs the SPY control).
- Recent-window GEX-gated slice (directional-only).
- Validation error band (Step 5).
- A **SURVIVES / FAILS Stage-2 vs neutral baseline** call.
- Note explicitly: REPLACES-vs-Artemis head-to-head is **deferred to a forward shadow bake-off** (ratified 2026-06-23 — Artemis is intraday 15-min VWAP/RVOL with 6 all-time signals, not historically reproducible).

**Sanity check (DAEDALUS):** if Stage-2 clean alpha > the Stage-1 underlying edge, that's a RED FLAG — options + costs + the mean-reversion vega headwind should *reduce* the edge, not amplify it. Investigate before shipping the number.

## 10. DONE DEFINITION

- `C:\temp\rsi2_stage1_trades.csv` exists with dates + prices for all four configs.
- `scripts/stage2_options_backtest.py` runs end-to-end on the RSI-2 ledger with zero DB writes.
- Output review doc written with ALL sections incl. the validation error band.
- No modification to `b2_options_resolver.py`, `a3_options_pnl_resolver.py`, or any DB/schema object.

## 11. TITANS / OLYMPUS IMPACT

- **Titans pass ratified 2026-06-23** (ATLAS / DAEDALUS / THALES / ATHENA): PROCEED, MODERATE-HIGH, no vetoes. Step-5 validation gate is non-arbitrable.
- **Olympus impact: None** — no skill files change, no hub MCP change. Output feeds L1b promote decisions the committee references.
- **AEGIS not triggered** — no new credential surface; uses the existing `UW_API_KEY` via `railway run`.
- **THALES bias flag (B.05/B.06):** RSI-2 ("buy dips in an uptrend") is maximally aligned with the documented macro-bull thesis. The beta-strip must be ruthless, not generous — that's the whole point of the measurement.
