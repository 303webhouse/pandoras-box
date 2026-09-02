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

**B0 rendered for zero units. This is a DETECTION FAILURE, not a finding that every unit is single-exit.** B0 is registered to render for MULTI-EXIT and ROLL-PAIR units only, but the arm-computation spec never specified how multi-exit status is determined, and the merged ledger does not expose exit count — it is recoverable only by resolving each unit's `;`-joined fill hashes against the normalized fills file. The executor had no instruction to open that file, so B0 could not render for any unit regardless of the data.

Of the 34 units whose fills resolve, **7 are MULTI-EXIT** and B0 was owed for all seven: ENERGY GUSH 05-27→06-16 (10 buys / 5 sells, −219.85) · SEMIS SOXS 06-12→06-26 (10/3, +111.40) · SEMIS SOXS 07-06→07-14 (4/3, −6.58) · CRYPTO BITX 06-15 (1/2, +3.97) · ENERGY GUSH 08-03→08-14 (2/2, +111.10) · SEMIS SOXS 07-20→07-27 (4/2, +150.97) · SEMIS SOXS 08-05→08-19 (4/2, +218.99). The other 32 units cannot be tested either way.

B0 is **NOT computed retroactively here**: the other arm values are visible, and computing a registered arm after results exist would let visible numbers shape a new computation. It registers forward with a stated multi-exit determination method.

**ZERO-WINDOW units are counted as non-beats** in the `beat` column, because a 0.00 differential is not > 0. Each affected cell states both the full count and the count excluding zero-window units, since the first understates the beat rate among units that actually had a window.

---

## SEMIS/DRAM

**n = 14** — **SHAPE, not a finding** (n < 30)

1× reference: `SOXX`

**Composition:** 13 inverse (SOXS 12, RAMZ 1) / 1 long (SOXL) — B1 mean inverse +10.50 (n=13), long +4.54 (n=1).

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | 14 | +10.07 | +9.64 | 11/14 | -8.11 | +25.32 |
| B2 | 14 | -0.53 | +0.06 | 7/14 | -47.77 | +30.19 |
| B3 | 14 | +7.60 | +7.15 | 11/14 | -7.66 | +20.73 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

**MULTI-EXIT WINDOW INTEGRITY:** 4 unit(s) in this cell are MULTI-EXIT and are measured as one continuous hold by RULING 1's convention — see the ledger-wide note. Reaches B1/B2/B3.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 8 BROKER-VALIDATED / 2 CSV_RECONCILE / 3 MANUAL / 1 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## ENERGY

**n = 7** — **SHAPE, not a finding** (n < 30)

1× reference: `XLE`

**Composition:** 0 inverse / 7 long — B1 is a **clean** vehicle read.

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | 7 | +0.85 | +1.34 | 6/7 | -5.39 | +3.44 |
| B2 | 7 | -0.57 | +2.16 | 4/7 | -13.98 | +11.86 |
| B3 | 7 | +0.54 | +2.23 | 5/7 | -8.23 | +3.56 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

**MULTI-EXIT WINDOW INTEGRITY:** 2 unit(s) in this cell are MULTI-EXIT and are measured as one continuous hold by RULING 1's convention — see the ledger-wide note. Reaches B1/B2/B3.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 5 BROKER-VALIDATED / 0 CSV_RECONCILE / 1 MANUAL / 1 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## PRECIOUS METALS/MINERS

**n = 9** — **SHAPE, not a finding** (n < 30)

1× reference: `GDX`

**Composition:** 0 inverse / 9 long — B1 is a **clean** vehicle read.

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | 7 | -0.97 | -0.63 | 2/7 | -3.97 | +0.63 |
| B2 | 9 | +5.54 | +4.12 | 7/9 (excl. zero-window 6/8) | -16.92 | +24.85 |
| B3 | 9 | -1.80 | -3.04 | 3/9 (excl. zero-window 3/8) | -8.58 | +3.66 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

**B1 n=7 vs B2/B3 n=9** — GDX trades are excluded from B1 as self-comparisons, per the registered rule; the divergence is expected, not a data gap.

**ZERO-WINDOW (n=1):** same-day units whose entry and exit fall in one session. B1 and B3 differentials are 0.00 BY CONSTRUCTION — the absence of a measurable window, never a measured tie — and those units are counted as non-beats there. B2 is NOT zeroed: it compares the trade against a fixed 20-trading-day horizon, so a same-day exit carries a real, signed differential and is counted on its merits. Excl-zero-window figures are stated per arm for this reason.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 7 BROKER-VALIDATED / 0 CSV_RECONCILE / 0 MANUAL / 2 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## CRYPTO

**n = 12** — **SHAPE, not a finding** (n < 30)

1× reference: `IBIT`

**Composition:** 5 inverse (MSTZ 3, BITI 1, BTCZ 1) / 7 long (BITX 4, CRCL 3) — B1 mean inverse +6.21 (n=5), long +1.81 (n=7).

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | 12 | +3.65 | +0.00 | 5/12 (excl. zero-window 5/7) | +0.00 | +6.88 |
| B2 | 12 | -7.61 | +3.60 | 7/12 (excl. zero-window 3/7) | -28.77 | +19.73 |
| B3 | 12 | +4.13 | +0.00 | 5/12 (excl. zero-window 5/7) | +0.00 | +12.62 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

**ZERO-WINDOW (n=5):** same-day units whose entry and exit fall in one session. B1 and B3 differentials are 0.00 BY CONSTRUCTION — the absence of a measurable window, never a measured tie — and those units are counted as non-beats there. B2 is NOT zeroed: it compares the trade against a fixed 20-trading-day horizon, so a same-day exit carries a real, signed differential and is counted on its merits. Excl-zero-window figures are stated per arm for this reason.

**MULTI-EXIT WINDOW INTEGRITY:** 1 unit(s) in this cell are MULTI-EXIT and are measured as one continuous hold by RULING 1's convention — see the ledger-wide note. Reaches B1/B2/B3.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 7 BROKER-VALIDATED / 0 CSV_RECONCILE / 3 MANUAL / 2 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

## OTHER

**n = 24** — **SHAPE, not a finding** (n < 30)

1× reference: **none** — see below

**Composition:** 12 inverse (SQQQ 6, TSLQ 5, SRTY 1) / 12 long — B1 NOT APPLICABLE (Ruling 2).

| arm | n | mean | median | beat | p10 | p90 |
|---|---|---|---|---|---|---|
| B1 | — | — | — | — | — | — |
| B2 | 24 | +2.00 | +1.17 | 14/24 (excl. zero-window 11/17 — ZW denominator) | -12.58 | +24.32 |
| B3 | 24 | -0.82 | +0.00 | 7/24 (excl. zero-window 7/17 — ZW denominator) | -13.99 | +8.38 |

- **B1 — VEHICLE (vs cell 1× reference)**
- **B2 — EXIT TIMING (vs same instrument to a fixed 20-trading-day horizon)**
- **B3 — BETA (vs SPY)**

**B1 NOT APPLICABLE** — OTHER is a residual cell with no shared underlying and therefore no 1× reference; naming one post-hoc would be benchmark selection. B3 (SPY) carries the market comparison.

**ZERO-WINDOW (n=7):** same-day units whose entry and exit fall in one session. B1 and B3 differentials are 0.00 BY CONSTRUCTION — the absence of a measurable window, never a measured tie — and those units are counted as non-beats there. B2 is NOT zeroed: it compares the trade against a fixed 20-trading-day horizon, so a same-day exit carries a real, signed differential and is counted on its merits. Excl-zero-window figures are stated per arm for this reason.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 7 BROKER-VALIDATED / 0 CSV_RECONCILE / 7 MANUAL / 10 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

---

## Ledger-wide

66 units across five cells. **ZERO-WINDOW total: 13 of 66** — METALS 1, CRYPTO 5, OTHER 7; SEMIS and ENERGY carry none. A fifth of the sample has no measurable window, which pulls every affected mean toward zero and is the single largest interpretive caveat on this table.

bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field shipped in 773e7a8; DEF-BARS-NO-PROVENANCE closed) · trades 34 BROKER-VALIDATED / 2 CSV_RECONCILE / 14 MANUAL / 16 PRINCIPAL-ATTESTED-INTERIOR

*Returns are instrument close-to-close over the trade window, not realized-P&L returns. B1/B2/B3 measure instrument and timing behavior; the study's realized metrics (part-1 render) are the P&L record.*

**REALIZED-DISCRETIONARY** — measures the principal's discretionary book only; says nothing about signal-layer strategy edge.

**ARM CONFOUND BY COMPOSITION.** B1 compares a unit against a LONG 1× cell reference; B3 compares it against SPY, also long. For an INVERSE unit, both differentials are dominated by the direction of the underlying — they record whether the directional call was right, not whether the vehicle was efficient (B1) or the selection good (B3). B1 and B3 are therefore clean ONLY in cells holding no inverse units: **ENERGY and METALS**. **30 of 66 units (45%) are inverse instruments.**

**B2 IS THE ONLY CONFOUND-FREE ARM.** It compares an instrument against ITSELF at a fixed 20-trading-day horizon, so direction cancels regardless of composition. B2 reads cleanly in every cell — and shows no consistent pattern: metals +5.54 (6/8 excl ZW) and OTHER +2.00 (11/17, ZW denominator) positive; semis −0.53 (7/14), energy −0.57 (4/7), crypto −7.61 (3/7) negative-to-neutral.

**SEMIS IS EFFECTIVELY SINGLE-INSTRUMENT AT UNIT LEVEL.** The closed map gives the cell seven tickers, but the traded units are 12 SOXS + 1 RAMZ + 1 SOXL. R-IV.86-b's original finding — that "a read on semis" and "traded SOXS well" are the same proposition in this dataset — SURVIVES at the unit level. EDGE's earlier reversal of it was drawn from map membership rather than traded units and is withdrawn. CRYPTO, by contrast, is genuinely multi-instrument at unit level: 12 units across 5 instruments.

**ZERO-WINDOW SIGNATURE, registered not acted on:** seven of the thirteen zero-window units are Robinhood tier MANUAL with windows of 6 to 101 seconds — a signature shared with TEST (6s) and TEST_C1 (1s), which are excluded as smoke. Ids 89/91/92 fall within 40 seconds of each other on 2026-03-17; ids 152/153 within 43 seconds on 2026-04-23. Separately, CRCL id 89 carries realized −43.85 bit-identical at full float precision to CRCL id 82, and id 89 is one of the sub-10-second rows. The six Fidelity-half zero-window units are date-granularity only, so the signature cannot be tested on them either way. ADMISSION WAS RULED UPSTREAM AND IS NOT REOPENED: no unit is excluded, no number moves, and this study renders as computed. The signature is stated because it was seen, and because the numbers were visible when it was seen — removing units on a property discovered after the results exist would be outcome-adjacent exclusion. Registered for adjudication; PR-106 part 2 is a separate registration and inherits any resolution.

**ZERO-WINDOW census cross-check:** per-cell counts METALS 1 · CRYPTO 5 · OTHER 7, ledger-wide 13 of 66, independently reproduced by CC-QUERY from the merged ledger (census sha256 `a86e0cee…`); per-cell n 14/7/9/12/24 reproduces the filed render exactly.

**RULING 1's close-to-close convention measures a multi-exit unit as ONE CONTINUOUS HOLD.** For the 7 units named in the B0 paragraph that is not what happened — a ten-entry/five-exit campaign over twenty days is measured as a single window. This limitation reaches **B1, B2 and B3, not B0 alone.** Affected cells: **ENERGY** (2 of 5 fill-resolvable units, including the cell's largest loss), **SEMIS** (4), **CRYPTO** (1). Untestable for the remaining 32 units.

**TIER LABELS ARE READ, NOT DERIVED.** The two-tier lines this artifact previously carried were produced by complement (cell n − BROKER-VALIDATED), which labelled MANUAL and CSV_RECONCILE units with a tier they do not carry. The filed render was always correct four-tier; only the arms collapsed non-BV into PAI. **No tier is derived by subtraction.** A tier with zero units in a cell renders `0`, never omitted — an absent tier and a zero-count tier must not read alike.

**DENOMINATOR LABELING.** OTHER's excl-zero-window denominator (17) and OTHER's non-broker-validated count (17) are **unrelated quantities that happen to be equal**. Every `/17` in this document states which one it is.

## Patch numbering (R-IV.123)

Stated so the sequence never reads as a lost payload — a gap explained is a gap; a gap
unexplained is a missing artifact.

| patch | artifact | status |
|---|---|---|
| 1–5 | `PR-106-RESULTS-PART1` (the render) | applied, filed `ad584b8`, sha256 `4b781c84…` |
| 6 | `PR-106-RESULTS-PART1` (the render) | applied, filed `817b531`, sha256 `d2baffb2…` |
| **7** | — | **NEVER ASSIGNED.** No patch-7 artifact was drafted or dropped. R-IV.119(c) ruled the SMST wording a *sub-patch* — "No patch 7" — deferring the tightened wording to part 2's spec, where UNCLASSIFIED re-renders post-backfill regardless. Disk corroborates: no `pr106-*patch7*` file exists on any ferry path. |
| 8 (8A + 8B) | `PR-106-ARMS-PART1` (this document) | applied, filed `ca7d0b3` |
| 9 (folded as 8C) | `PR-106-ARMS-PART1` (this document) | applied in the same commit per patch 9's batching instruction |

Patches 1–6 acted on the RENDER; patches 8–9 act on the ARMS. The two artifacts have
separate hash chains: render `4b781c84 → d2baffb2`; arms `dc9e8178 → …`.

## Not computable

**None.** All 66 cells-contributing units produced arm values. SBU is the study's only fetch failure and is cell-excluded, so no arm consumes it.

## Enumerated NOT APPLICABLE

- **OTHER B1 — 24 units.** Residual cell, no shared underlying, no 1× reference.
- **METALS B1 — 2 units.** GDX trades are self-comparisons against the metals reference `GDX`.

Neither is estimated, substituted, or silently dropped.
