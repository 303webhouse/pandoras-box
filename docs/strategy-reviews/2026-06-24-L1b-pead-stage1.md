# L1b Factor #3 — PEAD (Post-Earnings Announcement Drift)

**Date:** 2026-06-24
**Lane:** L1b canonical factor strategies (author → Anti-Bloat → backtest)
**Status:** STAGE-1 REJECTED (real but decayed edge) · NOT SHIPPED · zero live exposure
**Baseline:** current main @ 55946e0
**Why this doc:** Third L1b factor through the gate. A *real* historical edge that fails the robustness bar — distinct from Momentum (no edge ever) and RSI-2 (cleared Stage-1, failed Stage-2).

---

## 1. Factor

PEAD: a stock keeps drifting in the direction of its earnings SURPRISE for weeks after the report (under-reaction; Ball-Brown 1968, Bernard-Thomas 1989/90). The tradeable claim is a directional drift in the days *after* the announcement gap — the under-reaction, not the gap itself.

## 2. Spec v0.1

- **Surprise = seasonal-random-walk SUE** (Bernard-Thomas / Foster-Olsen-Shevlin): `SUE_q = (actual_q − actual_{q-4}) / stdev(trailing 8 seasonal diffs)`, computed **point-in-time** from the firm's own prior earnings. *Not* analyst-estimate surprise — forced by data (see §3 / caveat 2).
- **Entry T0 = first close AFTER the gap** (the make-or-break rule — PEAD is the under-reaction, not the gap reaction): `postmarket` → close of report_date+1; `premarket` → close of report_date; null/unknown → default postmarket (0.1% of events — well under the 10% flag).
- **Drift:** T0 → T0+k for k = 20, 40, 60 trading days, adjusted (total-return) closes.
- **Deciles:** point-in-time expanding cross-section (rank each event's SUE vs all SUEs observed *before* it) — never full-sample (look-ahead guard). First 200 events dropped as cross-section warmup.
- **Universe:** S&P 500 constituents (503; 486 usable). Breadth is mandatory — Momentum XS proved this edge class dies in small baskets (and a 61-megacap dry-run here confirmed it: PEAD is weakest in megacaps).
- **signal_category:** under-reaction/continuation family (directional drift), distinct from the existing non-directional long-vol earnings work. Enum deferred per pilot discipline.

## 3. Anti-Bloat verdict — CLEARED upstream (summary)

CLEARED this session by the planner: the only existing earnings work (earnings-gap-characterization, gap-convexity-options-validation) is **non-directional long-vol** (straddle/strangle on the secondary move, mostly failed in options terms). PEAD is a **distinct directional lens** — one-sided drift, a one-sided debit spread at Stage-2. Advanced to backtest; not re-litigated here.

## 4. Stage-1 backtest — canon

**Method:** standalone Python (`scripts/pead_backtest.py`), UW `/api/stock/{t}/earnings` for `actual_eps`+`report_time` (one call/name, cached), yfinance daily bars `auto_adjust=True` (total return — correct for a Stage-1 *underlying* test; the unadjusted-close rule applies only to Stage-2 options pricing). 486/503 names usable, **36,050 events** with a point-in-time decile, 2004→2026. **Validation:** SPY 2026-06-22 = 744.39 (exact match to the RSI-2 pilot anchor); EPS magnitudes spot-checked (AAPL ~$1.85–2.84/q, NVDA ~$1.24–1.87, JPM ~$5–6).

**Decile drift + spread (full sample), the beta-stripped test (D10−D1):**

| Horizon | D1 | D10 | **D10−D1 spread** | t | D10 vs EW-all | D10 vs SPY (alpha) |
|---|---|---|---|---|---|---|
| **k=20** | +0.45% | +2.17% | **+1.72%** | **6.31** | +2.17 vs +1.40 | +1.74% |
| k=40 | +1.79% | +2.59% | +0.80% | 2.22 | +2.59 vs +2.22 | +2.08% |
| k=60 | +3.23% | +3.51% | +0.28% | 0.66 | +3.51 vs +3.56 | +2.29% |

At k=20 the decile gradient is clean and monotonic (per-decile t rises D1 +1.99 → D10 +14.01), spread **+1.72% (t=6.31)**, top decile beats both the equal-weight average and SPY. **The effect front-loads and decays with horizon** (t 6.31 → 2.22 → 0.66; by k=60 D10 ≈ EW-all, no edge). Concentration is *not* the problem — the edge is a broad D5→D10 gradient, not a single extreme-tail spike (D10 ≈ D9).

**Sub-period robustness (D10−D1 spread) — the decisive table:**

| Regime | k=20 | k=40 | k=60 |
|---|---|---|---|
| 2004–2009 | +2.54% | +0.78% | −1.26% |
| 2010–2019 | **+3.23%** | **+2.70%** | +2.58% |
| **2020–2026** | **+0.07%** | **−0.33%** | **−0.20%** |

**The edge is gone in the regime that matters.** Strong and consistent 2004–2019, **~zero across all horizons in 2020–2026** — the textbook post-discovery arbitraging-away of PEAD.

**Yearly k=20 spread (confirms it's a regime shift, not one bad year):** 2010–2019 was positive in **9 of 10 years** (+2.4% to +6.5%; only 2016 negative). 2020–2026 is sign-flipping noise around zero — 2022 −0.9%, 2023 +1.5%, 2024 +4.5%, 2025 −1.7%, 2026 +0.4% (the larger-sample recent years lean flat-to-negative; 2020 n=32 is a COVID outlier, 2021 too thin to rank). The *consistency* that defined 2004–2019 is gone.

## 5. Status + next

- **REJECTED** at Stage-1, per the Done-def: a materially-positive spread exists **only at the short horizon and only pre-2020**; it is **not robust across sub-periods** (the hard AND condition), and the live-relevant 2020–2026 regime shows no dependable edge. Does not advance to a build brief → no Titans → no CC. Logged with reason. Zero live exposure.
- **Why this is a real REJECT, not a measurement miss:** +1.72%/t6.31 is a realistic PEAD magnitude (not "implausibly strong" — no look-ahead red flag), and the point-in-time deciles + after-the-gap T0 guard the two bias sources the brief flagged. Distinct from Momentum (no edge *ever*): PEAD had a genuine edge that has been **arbitraged away**.
- **The decay is the finding.** A factor that worked 2004–2019 but has shown no consistent edge for ~6 years is a dead edge for forward trading; modeling Stage-2 options costs on top would only deepen the rejection.

**Caveats (bound the claim):**
1. **Survivorship bias (v0):** current S&P 500 membership, not point-in-time — winners that drifted up are over-represented. This biases *toward* a CLEAR, yet the recent regime still shows no spread, so the REJECT is robust to it. **v1 fix = point-in-time membership.**
2. **Surprise definition:** time-series seasonal-random-walk SUE, NOT analyst-estimate surprise — forced because UW `street_mean_est` only populates from ~2022 (too shallow for the 3-regime bar); `actual_eps` reaches ~1997–2003, so a TS-SUE preserves the deep-history test (Nick's call, 2026-06-24). An analyst-estimate SUE on 2022→ data is a possible recent-only cross-check, but cannot meet the multi-regime bar.
3. **Coverage:** 17/503 names dropped (insufficient bars/earnings history); pre-2004 events excluded (SUE σ warmup + thin early cross-section).

**Workflow:** author → Anti-Bloat → backtest → documented reject. The gate held — a disciplined kill of a real-but-decayed edge, not a rubber-stamp. L1b scorecard: RSI-2 (S1 ✓ / S2 ✗), Momentum (S1 ✗), **PEAD (S1 ✗ — decayed)**. Next factors (ORB, VRP, + bonus) run the same gate, one at a time.
