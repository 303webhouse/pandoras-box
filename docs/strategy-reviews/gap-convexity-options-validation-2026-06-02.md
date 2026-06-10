# Gap Convexity: Options-Layer Validation

**Brief date:** 2026-06-02  |  **Run date:** 2026-06-02

**Primary question:** does a non-directional structure entered at T0 close
(post-IV-crush) cost less than the secondary move it captures?

**Tier A** (NOW Q4, PLTR Q4): actual NBBO bid/ask from `/api/option-contract/{id}/historic`.
Entry = ask, exit = bid. Real spread, no modelling.

**Tier B** (8 events): BS-modelled from `/volatility/term-structure`. Entry/exit at mid;
P&L adjusted -12% for spread. Intrinsic floor shown separately.

ROP = return on premium = (exit − entry) / entry. Positive = profitable.

---

## big(>10%) secondary move

| STRADDLE$ | STRANGLE$ | STR.ROP@T5 | SNG.ROP@T5 | STR.ROP@T3 | SNG.ROP@T3 | STR.ROP@T10 | SNG.ROP@T10 | INTR.FL@T5 | VERDICT | LABEL | TIER | MOVE% | BUCKET | GAP% | H/F | EXPIRY | DTE | IV | ATM_K |
| --------- | --------- | ----------- | ----------- | ----------- | ----------- | ----------- | ----------- | ---------- | ------- | --------- | ---- | ------- | ------------ | ------- | ----- | ---------- | ---- | -------- | ------ |
| 8.3% | 3.1% | +40% | +133% | -3% | +8% | -2% | +70% | PENDING | WIN | NOW Q4 | A | 12.9% | big(>10%) | -8.6% | NEUTRAL | 2026-02-13 | 15 | actual | 117 |
| 9.1% | 5.1% | +46% | +46% | +71% | +89% | +70% | +80% | PENDING | WIN | PLTR Q4 | A | 18.7% | big(>10%) | +11.7% | NEUTRAL | 2026-02-20 | 17 | actual | 160.0 |
| 11.4% | 6.5% | PENDING | PENDING | +107% | +158% | PENDING | PENDING | PENDING | PENDING | ZS Q3 | B | 23.2% | big(>10%) | -25.7% | HOLD | 2026-06-12 | 16 | 68.3% | 125.0 |

**Bucket aggregate (T+5):** straddle avg ROP=+43%, strangle avg ROP=+90% | 2 WIN / 0 LOSS / 1 PENDING

## moderate(5-10%) secondary move

| STRADDLE$ | STRANGLE$ | STR.ROP@T5 | SNG.ROP@T5 | STR.ROP@T3 | SNG.ROP@T3 | STR.ROP@T10 | SNG.ROP@T10 | INTR.FL@T5 | VERDICT | LABEL | TIER | MOVE% | BUCKET | GAP% | H/F | EXPIRY | DTE | IV | ATM_K |
| --------- | --------- | ----------- | ----------- | ----------- | ----------- | ----------- | ----------- | ---------- | ------- | --------- | ---- | ------- | ------------ | ------- | ----- | ---------- | ---- | -------- | ------ |
| 8.8% | 4.6% | -23% | -31% | -26% | -35% | -66% | -95% | -59% | LOSS | NXPI Q1 | B | 5.1% | moderate(5-10%) | +22.1% | HOLD | 2026-05-15 | 16 | 52.7% | 290.0 |
| 5.6% | 2.4% | -36% | -56% | -22% | -33% | +256% | +568% | -86% | LOSS | F Q1 | B | 5.2% | moderate(5-10%) | -5.6% | FAIL | 2026-05-15 | 15 | 34.5% | 12.0 |
| 7.2% | 2.9% | -13% | -26% | -14% | -23% | -16% | -39% | -53% | LOSS | TSN Q2 | B | 5.2% | moderate(5-10%) | +2.4% | HOLD | 2026-06-18 | 45 | 25.2% | 70.0 |
| 4.1% | 1.3% | -14% | -26% | -28% | -50% | PENDING | PENDING | -28% | LOSS | WMT Q1 | B | 5.5% | moderate(5-10%) | -4.9% | HOLD | 2026-06-05 | 15 | 25.0% | 120.0 |

**Bucket aggregate (T+5):** straddle avg ROP=-22%, strangle avg ROP=-35% | 0 WIN / 4 LOSS / 0 PENDING

## sub-5% secondary move

| STRADDLE$ | STRANGLE$ | STR.ROP@T5 | SNG.ROP@T5 | STR.ROP@T3 | SNG.ROP@T3 | STR.ROP@T10 | SNG.ROP@T10 | INTR.FL@T5 | VERDICT | LABEL | TIER | MOVE% | BUCKET | GAP% | H/F | EXPIRY | DTE | IV | ATM_K |
| --------- | --------- | ----------- | ----------- | ----------- | ----------- | ----------- | ----------- | ---------- | ------- | --------- | ---- | ------- | ------------ | ------- | ----- | ---------- | ---- | -------- | ------ |
| 9.0% | 4.6% | -35% | -51% | -23% | -34% | -70% | -97% | -103% | LOSS | PLTR Q1 | B | 3.7% | sub-5% | -3.9% | HOLD | 2026-05-22 | 17 | 52.4% | 135.0 |
| 6.4% | 2.8% | -24% | -37% | -19% | -27% | PENDING | PENDING | -49% | LOSS | NVDA Q1 | B | 4.9% | sub-5% | -0.5% | HOLD | 2026-06-05 | 15 | 39.3% | 220.0 |

**Bucket aggregate (T+5):** straddle avg ROP=-30%, strangle avg ROP=-44% | 0 WIN / 2 LOSS / 0 PENDING

## PENDING secondary move

| STRADDLE$ | STRANGLE$ | STR.ROP@T5 | SNG.ROP@T5 | STR.ROP@T3 | SNG.ROP@T3 | STR.ROP@T10 | SNG.ROP@T10 | INTR.FL@T5 | VERDICT | LABEL | TIER | MOVE% | BUCKET | GAP% | H/F | EXPIRY | DTE | IV | ATM_K |
| --------- | --------- | ----------- | ----------- | ----------- | ----------- | ----------- | ----------- | ---------- | ------- | --------- | ---- | ------- | ------------ | ------- | ----- | ---------- | ---- | -------- | ------ |
| 12.4% | 8.3% | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | DELL Q1 | B | PENDING | PENDING | +31.8% | HOLD | 2026-06-12 | 14 | 79.8% | 420.0 |

**Bucket aggregate (T+5):** straddle avg ROP=—, strangle avg ROP=— | 0 WIN / 0 LOSS / 1 PENDING

---

## Overall aggregate (T+5, excludes PENDING)

- Straddle: 2/8 WIN | avg ROP = -7%
- Strangle: avg ROP = -6%

## Controls check (must be LOSS)

- **PLTR Q1** (FAILED gap / negative case): verdict=LOSS straddle_rop_t5=-35% → **PASS**
- **NVDA Q1** (MUTED control): verdict=LOSS straddle_rop_t5=-24% → **PASS**

---

## Assumptions and caveats

- **Expiry rule:** nearest listed standard expiry >=14 calendar days after T0.
- **Strike rule:** ATM = nearest $5 or $2.5 increment; strangle = ±5% OTM from ATM.
- **Tier B IV:** post-crush ATM IV from UW `volatility/term-structure` at T0 date. IV held flat to exit (conservative; IV decay improves strangle, hurts straddle slightly).
- **Tier B spread:** -12% of entry cost deducted as spread proxy. Intrinsic floor = max(0, |S-K|) with no time value — the worst-case P&L.
- **Tier A spread:** actual NBBO bid (entry=ask, exit=bid). Covers real transaction cost.
- **Risk-free rate:** 4.5% annualised throughout.
- **No dividends / American exercise adjustment:** <5% error for near-ATM short-DTE equity options.
*Re-run ~2026-06-15 to fill PENDING cells for ZS and DELL.*
