# PR-106 PART 1 — B0/B1/B2/B3 BENCHMARK ARMS

Executor CC-BUILD. **SINGLE RUN** per R-IV.86(d), executed once; this document is annotation of that run under EDGE's three dispositions plus the ZERO-WINDOW enumeration. No recomputation.

## Inputs and provenance

```
spec        : docs/codex-briefs/pr106-arm-computation-spec.md
              Clause-1 wording amended per R-IV.118(f)
bars        : 33 specced series + IBIT reference (R-IV.118(e))
              captured close-to-close; MANIFEST DRIFT none across two
              independent fetches — every series matched its manifest entry
population  : 66 cells-contributing units, reconstructed and VERIFIED against
              part-1's per-cell n (14 / 7 / 9 / 12 / 24) before computing
units       : 66 computed, 0 NOT COMPUTABLE
failures    : SBU — no benchmark series, ruled inert (R-IV.111(c)); no arm
              consumes it
```

## Conventions binding on every table

**RETURN CONVENTION (EDGE Ruling 1):** Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.

**SCOPE NOTE:** this convention makes the arms **non-comparable** to the render's realized figures — they are different quantities, not two views of one. A realized-return variant is a NEW registration, part-2-adjacent, post-backfill when cost bases exist. Never a silent re-run.

**B0** renders for MULTI-EXIT and ROLL-PAIR units only. Every unit in this population is single-exit, so B0 is **DEGENERATE-FOR-SINGLE-EXIT** throughout — an arithmetic identity, not evidence — and no B0 column is rendered.

**ZERO-WINDOW units are counted as non-beats** in the `beat` column, because a 0.00 differential is not > 0. Each affected cell states both the full count and the count excluding zero-window units, since the first understates the beat rate among units that actually had a window.

---

## SEMIS/DRAM

**n = 14** — **SHAPE, not a finding** (n < 30)

1× reference: `SOXX`

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | 14 | +10.07 | +9.64 | 11/14 | -8.11 | +25.32 |
| B2 | 14 | -0.53 | +0.06 | 7/14 | -47.77 | +30.19 |
| B3 | 14 | +7.60 | +7.15 | 11/14 | -7.66 | +20.73 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 8 BROKER-VALIDATED / 6 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## ENERGY

**n = 7** — **SHAPE, not a finding** (n < 30)

1× reference: `XLE`

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | 7 | +0.85 | +1.34 | 6/7 | -5.39 | +3.44 |
| B2 | 7 | -0.57 | +2.16 | 4/7 | -13.98 | +11.86 |
| B3 | 7 | +0.54 | +2.23 | 5/7 | -8.23 | +3.56 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 5 BROKER-VALIDATED / 2 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## PRECIOUS METALS/MINERS

**n = 9** — **SHAPE, not a finding** (n < 30)

1× reference: `GDX`

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | 7 | -0.97 | -0.63 | 2/7 | -3.97 | +0.63 |
| B2 | 9 | +5.54 | +4.12 | 7/9 (excl. zero-window 6/8) | -16.92 | +24.85 |
| B3 | 9 | -1.80 | -3.04 | 3/9 (excl. zero-window 3/8) | -8.58 | +3.66 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

**B1 n=7 vs B2/B3 n=9** — GDX trades are excluded from B1 as self-comparisons, per the registered rule; the divergence is expected, not a data gap.

**ZERO-WINDOW (n=1):** same-day units whose entry and exit fall in one session. Their 0.00 arm values are the absence of a measurable window, never a measured tie.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 7 BROKER-VALIDATED / 2 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## CRYPTO

**n = 12** — **SHAPE, not a finding** (n < 30)

1× reference: `IBIT`

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | 12 | +3.65 | +0.00 | 5/12 (excl. zero-window 5/7) | +0.00 | +6.88 |
| B2 | 12 | -7.61 | +3.60 | 7/12 (excl. zero-window 3/7) | -28.77 | +19.73 |
| B3 | 12 | +4.13 | +0.00 | 5/12 (excl. zero-window 5/7) | +0.00 | +12.62 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

**ZERO-WINDOW (n=5):** same-day units whose entry and exit fall in one session. Their 0.00 arm values are the absence of a measurable window, never a measured tie.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 7 BROKER-VALIDATED / 5 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## OTHER

**n = 24** — **SHAPE, not a finding** (n < 30)

1× reference: **none** — see below

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | — | — | — | — | — | — |
| B2 | 24 | +2.00 | +1.17 | 14/24 (excl. zero-window 11/17) | -12.58 | +24.32 |
| B3 | 24 | -0.82 | +0.00 | 7/24 (excl. zero-window 7/17) | -13.99 | +8.38 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

**B1 NOT APPLICABLE** — OTHER is a residual cell with no shared underlying and therefore no 1× reference; naming one post-hoc would be benchmark selection. B3 (SPY) carries the market comparison.

**ZERO-WINDOW (n=7):** same-day units whose entry and exit fall in one session. Their 0.00 arm values are the absence of a measurable window, never a measured tie.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 7 BROKER-VALIDATED / 17 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

---

## Ledger-wide

66 units across five cells. **ZERO-WINDOW total: 13 of 66** — METALS 1, CRYPTO 5, OTHER 7; SEMIS and ENERGY carry none. A fifth of the sample has no measurable window, which pulls every affected mean toward zero and is the single largest interpretive caveat on this table.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 34 BROKER-VALIDATED / 32 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## Not computable

**None.** All 66 cells-contributing units produced arm values. SBU is the study's only fetch failure and is cell-excluded, so no arm consumes it.

## Enumerated NOT APPLICABLE

- **OTHER B1 — 24 units.** Residual cell, no shared underlying, no 1× reference.
- **METALS B1 — 2 units.** GDX trades are self-comparisons against the metals reference `GDX`.

Neither is estimated, substituted, or silently dropped.
