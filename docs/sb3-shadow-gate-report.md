# Sub-Brief 3 — Shadow Gate Report (2026-06-12)

**Window:** 2026-06-11 → 2026-06-12 (2 RTH sessions) | **Sample:** 164 signals carrying `score_v2_factors.sb3_shadow`
**Mode:** read-only readout of accumulated shadows. **Nothing promoted** — each gate returns here for Fable's greenlight (gate = relayed report, not self-certification). Live score unchanged throughout.

---

## Gate 1 — Chunk 3 (ADX UW-bars) → **MATURE, decisive. Recommend promote review.**

The writer **ran and produced real regimes** (not just `unknown`), confirming the Redis path end-to-end.

| `new_label` (UW-bars ADX) | live (`default-25`) | count | would_change |
|---|---|---|---|
| **choppy** (reason ok) | trending | **116** | 116 |
| unknown (no_data) | trending | 48 | 48 |
| *(real trending)* | — | **0** | — |

**Read:** over these 2 sessions SPY ADX was **< 20 (choppy)** — yet the dead default-25 scored **100% of signals as "trending"** (no chop penalty). **116/164 (71%)** would flip trending→choppy and correctly receive the −10 chop penalty + chop-strategy adjustments they're currently denied. **Not one signal** was actually in a real trending regime — i.e. the default-25 was wrong on every signal in this window. This is the dead-gate finding, quantified.

**The 48 `unknown` (29%)** are signals fired outside the writer's RTH-fresh window (overnight/premarket/crypto) → shadow key expired (90-min TTL) → `unknown` (neutral). That's the designed fail-loud behavior, but the rate is a **promote-tuning question**: extend the writer beyond RTH (ADX is a daily value) or accept `unknown` off-hours. Either way it beats a false "trending."

**Recommendation:** promote-ready. At promote, signals correctly get chop penalties in choppy tape; decide the off-RTH `unknown` policy.

---

## Gate 2 — Chunk 2-R (flow reconciliation) → **shape clear; PRELIMINARY (2 of 5–10 days).**

| path | count | notes |
|---|---|---|
| **gapfill** | 153 (93%) | P4A absent/stale/NEUTRAL → fixed-P2 (neutral-or-positive) |
| **overlap** | 10 (6%) | P4A fresh + conviction → authoritative, P2 suppressed |
| **weak** | 1 | fresh but <$2M (recent-but-weak, kept distinct) |

- **Freshness guard works:** 2 signals had *stale-but-high-conviction* P4A → correctly demoted to gapfill (the 45-min guard catching the 4h-staleness risk).
- **Hedging damp fired (the suppression list, as requested):** **UNH, 2026-06-12, pc=4.37** + bullish premium → suppressed (detail logged). Caught the hedging signature without eating directional puts. Only 1 case this window (vs the XLK-heavy 10-day sample — fewer extreme-pc events these 2 days).
- **Net impact:** current live flow averages **−0.70** (P2's false-bearish penalties drag scores down); reconciled averages **+1.18** (false penalties floored out). **106/164 (65%)** signals change. Confirms the reconciliation removes the systematic false-bearish drag + the double-count.

**Recommendation:** continue to the full 5–10 day window before promote (P4A overlap n=10 is thin; want more overlap + hedging cases). Shape is already validating the design.

---

## Gate 3 — Chunk 1 (iv true-rank) → **PRELIMINARY (2 of 7 days).**

- 164 signals; **UW true-rank present on 99 (60%)** (rest crypto/non-watchlist → `no_data`, correctly null).
- **bonus differs on 114/164 (70%)** — proxy vs UW true-rank disagree on the iv_bonus, as expected (proxy measures chain *dispersion*, UW measures *percentile*).

**Recommendation:** continue to the full week, then run the 1c gate (review the distribution + **hand-check ~5 tickers against an independent IV read** — correctness over convergence) before promote.

---

## Bottom line
| Chunk | Gate | Status | Next |
|---|---|---|---|
| 3 — ADX | 3c | **Mature** — writer proven, 71% mis-scored trending→choppy | **Fable promote-review** + off-RTH `unknown` policy |
| 2-R — flow | 2R-b | Preliminary, design validating | continue to 5–10 days |
| 1 — iv | 1c | Preliminary | continue to 1 week + 5-ticker hand-check |

Nothing auto-promoted. Live scoring unchanged. Chunk 3 is the one ready to advance on your call.
