# Signal Edge & Feed-Tier Validation — Findings

**Date:** 2026-06-16 (analysis run 2026-06-16 18:36 MDT / 2026-06-17 00:36 UTC)
**Bucket:** investigation · READ-ONLY (no prod writes, no classifier/threshold changes)
**Data:** `signals` (12,822 rows, 2026-02-20 → 2026-06-17), `signal_outcomes` (12,239 resolved w/ MFE/MAE), `bias_composite_history` (20,746 snapshots) for fire-time regime tagging. Resolved WIN/LOSS population analyzed: **9,666**.
**P&L unit:** `signals.outcome_pnl_pct` (percent; WIN median +2.5%, LOSS median −1.3%). "Expectancy" = mean `outcome_pnl_pct` over the WIN+LOSS pool.

---

## Answer-first

**The score/feed-tier system does not have the edge. The edge lives in `strategy × direction × bias-regime`, and the classifier does not key on those axes.**

1. **Score is broken as a win-probability sorter.** Win rate is flat at ~30–35% across *every* score band from 20 to 100. Band 50 (35.3%) has the single highest win rate; band 90 (32.9%) does not beat it. "84 must beat 73" **fails on win rate** and is only weakly true on expectancy. The score sorts P&L *magnitude* faintly at the extreme top and does **not** sort hit-rate at all.

2. **`top_feed` is directionally positive but statistically unusable.** n = **14–15** resolved signals (43% WR, +0.685 expectancy; survives the AI-beta strip, actually improves to +0.93). You cannot run a book on 14 signals over four months. The edge it shows is real-looking but not reliable, and it is too thin to be the strategy by itself.

3. **The tier ladder is inverted vs its names.** Measured expectancy: `top_feed` +0.69 (n=14) > `research_log` −0.31 > `watchlist` −0.53 > **`ta_feed` −1.08 (the *worst* tier).** A signal being promoted to `ta_feed` is, empirically, a negative indicator.

4. **The blended feed is flat-to-negative.** Whole-population expectancy = **−0.46%/signal**, win rate 32.7%. The floor sweep shows expectancy crosses zero only around **score ~78–80**, and even there it is barely breakeven (+0.09 at ≥80, n=402). Only ≥95 is robustly positive (+0.31, n=70).

5. **AI-beta is NOT the driver.** The mega-cap AI complex (NVDA/semis/memory) is 2–7% of volume and *underperformed* in Feb and April. Stripping it barely moves any aggregate. There **is** a broad large-cap / index-liquidity edge (semis_ai_tech incl. MSFT/XLK +0.82; SPY/QQQ/HYG-type index_macro 57.8% WR +0.78) — but that is a *liquidity/large-cap* effect, not a pure-AI effect, and the score/tier system does not capture it.

6. **The one genuine directional edge is "short in a bear-tagged regime," and it is fragile.** `sell_the_rip` SHORT in URSA bias = 59% WR, +1.36 (n=900) — but **decay analysis shows that edge is almost entirely March**; it lost −7.80 in April and −2.33 in June when the regime flipped. It is a downtape momentum bet with no protection on regime flip, not a durable alpha.

### Recommendation: **REWORK the classifier — do NOT simply "lean on top_feed."**

`top_feed` (n=14) is too thin to lean on, and a cosmetic floor-raise to 80 only buys breakeven. The predictive signal is in dimensions the classifier currently ignores. Concretely (all to be specced/validated in a follow-up build, not done here):
- **Demote/suppress `Holy_Grail` and `Crypto Scanner`** — they are the loss center (Holy_Grail alone ≈ −4,855 pnl-units, negative in every regime and every month).
- **Gate `sell_the_rip` on bias regime** — surface only in URSA/NEUTRAL, hard-suppress in TORO, and add a regime-flip kill-switch (April is the cautionary tale).
- **Suppress / quarantine LONG signals** — the system has **no long edge in any regime** (LONG/URSA 20.4% WR, LONG/NEUTRAL −0.68).
- **Bias toward large-cap/index/liquid names**; the 7,400-signal single-name "other" bucket is where expectancy dies (−0.70).
- Keep `top_feed` as a high-conviction *surface*, but treat it as a flag, not a strategy.

---

## Headline tables

### Per-strategy × bias-regime edge (resolved WIN/LOSS, n≥30)

| Strategy | Bias regime | n | Win rate | Expectancy | Read |
|---|---|---|---|---|---|
| **sell_the_rip** | URSA_MINOR | 900 | **59.0%** | **+1.355** | strong, regime-conditional |
| sell_the_rip | NEUTRAL | 716 | 55.9% | +0.119 | thin-positive |
| sell_the_rip | TORO_MINOR | 30 | 36.7% | −0.872 | loses in bull |
| Artemis | TORO_MINOR | 366 | 40.4% | +0.189 | marginal |
| Artemis | URSA_MINOR | 393 | 37.4% | +0.047 | breakeven |
| Artemis | NEUTRAL | 1429 | 34.7% | −0.115 | negative |
| CTA Scanner | NEUTRAL | 1024 | 33.0% | −0.363 | negative |
| CTA Scanner | URSA_MINOR | 203 | 37.9% | −0.777 | negative |
| CTA Scanner | TORO_MINOR | 156 | 29.5% | −0.407 | negative |
| **Holy_Grail** | URSA_MINOR | 1227 | 27.9% | −0.823 | negative |
| **Holy_Grail** | NEUTRAL | 2798 | **18.8%** | **−1.265** | worst-in-class |
| **Holy_Grail** | TORO_MINOR | 289 | 25.6% | −1.081 | negative |
| Crypto Scanner | NEUTRAL | 75 | 8.0% | −2.046 | catastrophic |
| Crypto Scanner | TORO_MINOR | 33 | 18.2% | −2.623 | catastrophic |

### Calibration curve (T1) — by 10-pt score band (v1 score, drives `feed_tier`)

| Score band | n | Win rate | Expectancy |
|---|---|---|---|
| 20 | 318 | 28.3% | −0.679 |
| 30 | 703 | 26.3% | −0.751 |
| 40 | 1268 | 30.1% | −0.612 |
| 50 | 2652 | **35.3%** | −0.289 |
| 60 | 3315 | 33.0% | −0.554 |
| 70 | 934 | 35.4% | −0.332 |
| 80 | 288 | 31.9% | **+0.124** |
| 90 | 73 | 32.9% | −0.104 |
| 100 | 41 | 31.7% | +0.155 |

Win rate is non-monotonic and flat; only expectancy at 80+ turns positive, and band 90 breaks even that. **The score is not a calibrated probability.**

### Floor sweep (T6) — outcomes at/above a score threshold

| Threshold | n | Win rate | Expectancy | Expectancy (AI-stripped) |
|---|---|---|---|---|
| ≥50 | 7303 | 34.1% | −0.394 | −0.399 |
| ≥70 (current top_feed floor) | 1336 | 34.4% | −0.206 | −0.205 |
| ≥75 | 662 | 32.9% | −0.018 | −0.061 |
| ≥80 | 402 | 32.1% | +0.086 | +0.028 |
| ≥85 | 211 | 30.3% | −0.043 | −0.232 |
| ≥90 | 114 | 32.5% | −0.011 | −0.405 |
| ≥95 | 70 | 34.3% | +0.312 | +0.408 |

Zero-cross ≈ **78–80**. The 85–90 band's slim positivity **leans on AI names** (AI-stripped goes −0.23 / −0.40). Only ≥95 (n=70) is robustly positive. Raising the floor from 70→80 moves expectancy from −0.21 to +0.09 — a move from "bleeding" to "breakeven," not to "edge."

### Feed-tier outcomes, full vs AI-stripped (alpha-vs-AI-beta decomposition)

| feed_tier (v1) | n | Win rate | Expectancy | n (no-AI) | Win rate (no-AI) | Expectancy (no-AI) |
|---|---|---|---|---|---|---|
| top_feed | 14 | 42.9% | +0.685 | 12 | 50.0% | +0.926 |
| research_log | 5069 | 37.3% | −0.311 | 4897 | 37.1% | −0.308 |
| watchlist | 3699 | 27.8% | −0.529 | 3569 | 27.6% | −0.544 |
| ta_feed | 884 | 27.0% | −1.076 | 853 | 27.0% | −1.091 |

AI-strip changes nothing material at the tier level → **the (weak) edge is not AI-beta.**

---

## Per-task findings

**T1 — Score calibration: BROKEN.** Win rate flat ~30–35% across all bands 20–100; band 50 is the modal high. Expectancy is faintly monotonic only at the top (positive at 80, 100; negative at 90). "84 beats 73" is true on expectancy (band 80 +0.124 vs band 70 −0.332) but **false on win rate** (band 70 35.4% > band 80 31.9%). The score discriminates magnitude weakly and probability not at all.

**T2 — Strategy × regime/sector: edge is concentrated and conditional.** See headline table. `sell_the_rip` carries the book in URSA/NEUTRAL; `Holy_Grail`/`CTA`/`Crypto` are negative across regimes; `Artemis` is marginal and only in TORO/URSA. Sector cut (T10) shows liquid large-cap/index names positive, single-name "other" negative.

**T3 / T8 — Path A vs C / confluence stacking: NO edge.** Explicit Path tags are unusably small (A=5, C=20). Using `confluence_tier` as the A-vs-C proxy: STANDALONE −0.465 (n=9,300), CONFIRMED −0.391 (n=359), CONVICTION −0.574 (n=7). Confirmed is marginally less-bad but still negative; CONVICTION (n=7) is worse. **Confluence confirmation does not beat direct/standalone — Triton's premise is unsupported on this data.**

**T4 — Long/short asymmetry: the structural core.** SHORT/URSA is the **only** positive directional cell (47.3% WR, +0.256, n=2,036). SHORT/NEUTRAL −0.688, SHORT/TORO −0.447. **Every LONG cell is negative** (LONG/NEUTRAL −0.683, LONG/URSA −0.629 at 20.4% WR, LONG/TORO −0.504). The system has a short-in-bear edge and no long edge anywhere.

**T5 — Failure modes (ranked by total P&L bleed):** `Holy_Grail HOLY_GRAIL_1H SHORT` −2,493 and `…LONG` −2,362 (16.6% WR) are the two largest loss centers. `CTA RESISTANCE_REJECTION SHORT` −483, `Crypto PULLBACK_ENTRY LONG` −190. The only consistently positive signal_types are the `sell_the_rip` family — `SELL_RIP_VWAP` (65.9% WR, +1.411, +356), `SELL_RIP_EARLY` (57.1%, +1.34, +303), `SELL_RIP_EMA` (55.3%, +0.527, +612) — plus small-n CTA `APIS_CALL` (+0.61) and `TRAPPED_SHORTS` (+0.82).

**T6 — False-negative / floor sweep:** see table. Best achievable static floor is ~80 (breakeven) or ~95 (n=70, +0.31). No floor produces a strong, sized, positive book. Demoting on score alone cannot fix the system because the score is uncorrelated with hit-rate.

**T7 — Edge decay: the sell_the_rip story collapses under time-segmentation.**

| Strategy | Mar | Apr | May | Jun |
|---|---|---|---|---|
| sell_the_rip | 63.2% WR / +1.49 (n=1330) | **11.3% / −7.80** (n=97) | 49.1% / +0.87 | **9.1% / −2.33** (n=44) |
| Holy_Grail | 24.6% / −1.01 | 16.0% / −2.15 | 24.6% / −0.33 | 21.5% / −0.63 |
| Artemis | 37.8% / +0.08 | 38.8% / +0.01 | 32.7% / −0.12 | 35.4% / −0.07 |
| CTA Scanner | 38.3% / −0.19 | 30.5% / −1.14 | 35.5% / +0.17 | 23.7% / −0.83 |

`sell_the_rip`'s lifetime edge is a **March (bear-grind) phenomenon**; it was destroyed in the April flip and again in June. `Artemis` drifts from +0.08 to negative — a decaying marginal edge. `Holy_Grail` is negative every month. **Months 4–6 broke the strategies that looked good in months 1–3.**

**T8 — Confluence stacking:** covered with T3. CONVICTION (2+ strategies aligned) n=7, −0.574 — no support for a conviction premium.

**T9 — Committee efficacy (linked subset only):** 46 signals carry completed committee data (0 overrides); 37 resolved to WIN/LOSS. Committee-linked = **43.2% WR, +0.803** vs all-resolved baseline 32.7% / −0.463. *Directionally* the committee-reviewed set outperformed strongly — **but n=37, self-selected (review is requested on already-promising signals), and survivorship-prone.** This cannot distinguish committee skill from selection bias and must not be cited as proof of committee edge. Flagged for a properly-controlled (matched-population, pre-registered) test later.

**T10 — Trend-riding by sector (coarse ticker→sector buckets):**

| Sector bucket | n | Win rate | Expectancy |
|---|---|---|---|
| semis_ai_tech (incl. MSFT/XLK/GOOGL/ZS) | 563 | 45.8% | +0.817 |
| index_macro (SPY/QQQ/IWM/HYG/TLT/FXI) | 427 | 57.8% | +0.784 |
| energy_materials | 595 | 33.6% | +0.153 |
| financials | 681 | 31.6% | −0.313 |
| other (single-name long tail) | 7400 | 30.3% | −0.695 |

The positive buckets are **large-cap tech + index/macro instruments** — liquid, well-behaved names where these mean-reversion/trend setups work. Note this uses the *broad* tech definition (mega-cap software + ETFs); the **tight** AI complex (pure NVDA/semis/memory, T1–T6 strip list) did **not** carry the edge. The conclusion: the edge is *large-cap liquidity*, not *AI-beta*.

---

## Per-strategy verdicts (REAL / FRAGILE / NONE)

- **sell_the_rip — FRAGILE (regime-only).** Genuinely strong in URSA/NEUTRAL (short-in-bear), survives the AI-strip, but the edge is concentrated in one regime-month (March) and reverses catastrophically when the regime flips (April −7.80, June −2.33). Promotable to REAL *only* if hard-gated to URSA/NEUTRAL with a regime-flip kill-switch. As currently surfaced (un-gated), it is a regime bet, not alpha.
- **Artemis — FRAGILE → NONE.** Marginal positive only in TORO (+0.19) and URSA (+0.05); negative in NEUTRAL; decays to negative by May–June. Barely breakeven at best, fading.
- **CTA Scanner — NONE.** Net negative; oscillates with the tape (regime noise). Two sub-types (`APIS_CALL`, `TRAPPED_SHORTS`) are marginally positive at small n — worth isolating, not worth running the parent strategy for.
- **Holy_Grail — NONE (actively destructive).** Highest-volume strategy (4,657), negative in every regime, every month, both directions; the single largest P&L loss center. Top candidate for suppression.
- **Crypto Scanner — NONE.** 8–18% win rate, −2 to −2.6 expectancy. Catastrophic.

---

## Methodology, caveats, limitations

- **Regime tagging:** each signal tagged with the bias level (`NEUTRAL` / `URSA_MINOR` / `TORO_MINOR`) from the nearest-prior `bias_composite_history` snapshot at fire time (99.98% coverage). `signals.regime` and `signals.bias_level` columns are 100% NULL and were not usable.
- **VIX state — partial.** `vix_regime` is present in only ~9% of bias snapshots (1,877 / 20,746), too sparse for a clean VIX-state cut. Macro phase was therefore proxied by **calendar month + bias mix** (Feb–Mar = URSA-heavy grind/correction; April = vol-spike/whipsaw, the −1.55 month; May–June = chop/melt-up attempt) rather than a dedicated VIX axis. `regime_overrides` is test/stub data (3 rows) and unusable. This is the main methodological gap; a real VIX-state segmentation needs a denser vol feed.
- **AI-beta strip:** tight definition = NVDA + semis + memory + AI-infra + semi/tech ETFs (explicit list in the T1–T6 queries). A broad definition (adding mega-cap software + QQQ) is what powers the T10 "semis_ai_tech" bucket — the two are reported separately on purpose.
- **P&L proxy:** `outcome_pnl_pct` is the resolved signal P&L percent; a −267% outlier exists (likely a short/spread artifact) but does not move medians. Cross-checked against `signal_outcomes` MFE/MAE availability (11,302 rows). Personal-trade P&L review was **deferred** per scope (trade log not current); only the committee-linked subset (T9) touches trade-side data.
- **Sample-size flags:** `top_feed` n=14, CONVICTION n=7, committee-linked n=37, Path A/C n=5/20, score≥95 n=70 — every conclusion drawn from these is explicitly caveated and must not be treated as statistically settled.
- **Scope honored:** READ-ONLY. No prod writes, no classifier or threshold changes. All recommendations are for a separate, reviewed build.
