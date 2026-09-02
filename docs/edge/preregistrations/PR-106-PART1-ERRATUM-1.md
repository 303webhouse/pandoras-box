# PR-106 PART-1 — ERRATUM #1 (v2 — exact figures)

**Supersedes** the v1 erratum draft whole (no-splice). v1 left restated values as "*from
render*"; v2 computes them from the filed render (`PR-106-RESULTS-PART1`, read 2026-09-02).
**Commissioned:** spine, on R-IV.122's pre-committed erratum path. **Authored by:** EDGE.
**Files beside part 1**, with falsified-findings-ledger entry E-10.
**No re-render. No arm recomputation. No verdict change — SHAPE throughout.**

## 1 · The correction

| id | ticker | cell | filed realized | broker-corrected | delta |
|---|---|---|---|---|---|
| 91 | NBIS | OTHER | −0.20 | **−40.40** | −40.20 |
| 92 | ICE | OTHER | −0.52 | **−8.92** | −8.40 |
| | | | −0.72 | **−49.32** | **−48.60** |

Both tickers are confirmed OTHER-cell members on the render's ticker list.

## 2 · Restated figures — exact

Derivation: OTHER win rate 62.5% × n=24 → **15 wins / 9 losses**; ledger-wide 68.2% × n=66 →
**45 wins / 21 losses**. Both corrected units were losses at the filed values and remain
losses, so loss counts do not move and the delta lands entirely in the loss totals.

### OTHER × EQUITY_ETF

| figure | filed | restated |
|---|---|---|
| n | 24 | **24** (unchanged) |
| win rate | 62.5% | **62.5%** (unchanged — no boundary crossing) |
| avg win | $34.68 | **$34.68** (unchanged) |
| avg loss | −$40.04 | **−$45.44** (−360.36 − 48.60 = −408.96 ÷ 9) |
| expectancy/trade | $6.66 | **$4.63** |
| total realized | $159.83 | **$111.23** |

### Ledger-wide (cells-contributing layer)

| figure | filed | restated |
|---|---|---|
| n | 66 | **66** (unchanged) |
| win rate | 68.2% | **68.2%** (unchanged) |
| avg win | $47.18 | **$47.18** (unchanged) |
| avg loss | −$47.57 | **−$49.89** (−998.97 − 48.60 = −1,047.57 ÷ 21) |
| expectancy/trade | $17.03 | **$16.30** |
| total realized | $1,124.23 | **$1,075.63** |

### Layered counts table

| layer | n | filed realized | restated |
|---|---|---|---|
| population (smoke-excluded) | 69 | $1,203.60 | **$1,155.00** |
| cells-contributing | 66 | $1,124.23 | **$1,075.63** |
| cells-contributing tickers | 25 of 133 | — | unchanged |

Internal check: (15 × 34.68 + 9 × −45.44) ÷ 24 = $4.63 ✓ · (45 × 47.18 + 21 × −49.89) ÷ 66 =
$16.30 ✓ (cent-level rounding in the filed averages).

## 3 · What does NOT change, and why

- **All unit counts** — OTHER 24, cells-contributing 66, population 69, 25 of 133 tickers.
- **Win rates**, OTHER and ledger-wide. Both units were losses before and after: no unit
  crosses the boundary. Unchanged **by construction**, not by coincidence.
- **Average win**, both layers. Neither unit is a win at either value.
- **All four other cells** — SEMIS, ENERGY, METALS, CRYPTO are untouched.
- **Gate status.** Every cell was SHAPE (n < 30) and remains so.
- **All B0/B1/B2/B3 arm values.** Ruling 1 fixed arm returns as *instrument close-to-close
  over the trade window*, not realized-P&L returns, so a realized correction changes neither
  the window nor the series. The SCOPE NOTE cuts both ways: the arms are non-comparable to
  the render's realized figures, and they do not inherit its errata.

**REQUIRED VERIFICATION before this files as value-only:** confirm the broker correction moved
**values only** — not entry/exit dates, not quantities. A date change moves the arm windows and
the arms would need restating; a quantity change touches QTY-FROM-NOTE and denominator
handling. State the check's result on the erratum's face rather than assuming it.

## 4 · Interaction with the ZERO-WINDOW SIGNATURE — material

Ids **91 and 92 are two of the seven** Robinhood tier-MANUAL zero-window units flagged on the
arms artifact (6–101 second windows, sharing a signature with TEST and TEST_C1). Id 91 sits in
the 03-17 cluster with ids 89 and 92, all three within 40 seconds.

**Registered observation, not a conclusion:** the broker correction establishes these two are
*real trades whose filed values were materially wrong* — by roughly 200× and 17×. That shifts
the leading hypothesis for the cluster away from phantom/smoke rows and toward **data-entry
error**, and it is the first hard evidence on the cluster from outside the DB. It does not
resolve the remaining five flagged rows, and it does not touch the separate CRCL id-89/id-82
bit-identical-realized candidate, which stays a duplicate-lifetime question rather than a value
one. Admission was ruled upstream and is not reopened; no unit is excluded.

Corroborating detail from the render: OTHER carries **7 MANUAL-tier units** — the tier the
seven flagged rows sit in — so the flagged cluster is concentrated in the cell this erratum
corrects.

## 5 · Falsified-findings ledger — entry E-10

**Claim:** OTHER-cell and ledger-wide realized totals as filed in `PR-106-RESULTS-PART1`.
**Artifact:** the part-1 render.
**Falsified by:** broker records — ids 91 and 92 carried filed realized values of −0.20 and
−0.52 against actual −40.40 and −8.92.
**Sub-form:** **NONE — SOURCE-DATA ERROR, not an inference failure.**
**Why the distinction is filed:** E-1 through E-9 are analyst inference errors with named
sub-forms. E-10 is the first whose cause is upstream data. Without the distinction the ledger
implies every falsification is an analyst's, which is false. A study can be reasoned correctly
end to end and still carry wrong numbers if the ledger beneath it is wrong — the argument for
broker reconciliation as infrastructure rather than hygiene, which REC-006 already carries.
**What survived:** every count, both win rates, both average wins, all four other cells, all
gate statuses, all arm values. The correction moves money, not structure.
