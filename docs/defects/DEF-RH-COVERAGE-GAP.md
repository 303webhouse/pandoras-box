# DEF-RH-COVERAGE-GAP

**Severity:** P2 · **Filed:** 2026-09-02 · **Reshaped:** R-IV.180(b) · **Class:** EXISTENCE
**Status:** OPEN — registration only. Remediation HELD and unsequenced per R-IV.170(e)/180(e).
**Owner:** CC-POSITIONS (evidence) · BUILD (pickup)
**Surface:** the Robinhood ingest path into `unified_positions` — *absence*, not valuation
**Evidence:** `rh_crosscheck.json` (ticker level) · `rh_unit_attribution.json` (unit level)

## HEADLINE

Robinhood activity that never reached the ledger, in **two distinct sub-populations**:

1. **Zero-row tickers — 34.** Traded in 2026, no row in `unified_positions` at any status.
   Net **+$178.64** of export cash the ledger never saw.
2. **Unrecorded-PERIOD activity on covered tickers.** Tickers that *do* have rows, whose
   ledger nonetheless omits whole blocks of trading — concentrated in **early 2026**.

The remedy family is **INGESTION, not reconciliation.** Nothing here is a wrong number.
Correcting values cannot close an existence gap.

## SUB-POPULATION 1 — 34 zero-row tickers

Method ratified R-IV.170(b): comparable = zero 2026 net flow **and** no 2025 carry-in;
agreement threshold $0.50.

```
class                          n        DB      export      delta
AGREE      (<$0.50)           48   1,532.28   1,526.72      +5.56
MISMATCH   (>=$0.50)          28     806.79   1,084.89    -278.10   -> DEF-RH-EQUITY-REALIZED-MISMATCH
DB-MISSING (no row at all)    34       0.00    -178.64    +178.64   <- here
```

```
BTCZ  PLTZ  ECL   CVNA  SNDK  UNH   CRWV  JEPQ  SPCH  BKR   SBIT  CAT
CORD  ETHU  TTAN  SNOW  BA    UBRL  SPGI  JEPI  AMDL  KWEB  IMAX  ARBE
BRK.B BRKU  SHNY  VRTX  TCEHY IAU   DAX   WFC   GHRS  + 1 further
```

### BTCZ — worked line (R-IV.176(a), verbatim as ruled)

BTCZ carries **+$138.45**, the second-largest single-ticker delta in the whole cross-check,
and `db_rows = 0`. It was initially routed as a candidate for erratum-2 scoping and routes
here instead:

> **There is no unit to be wrong.**

The delta is entirely export-side. An erratum that revalues units cannot touch BTCZ, because
BTCZ has no units. The same reasoning removed RAMZ (+$311.04, `db_rows = 0`, not-comparable)
from the valuation candidate set — **existence defects cannot cross valuation boundaries**,
and the +$311.04 headline dissolves on that ground rather than on magnitude.

## SUB-POPULATION 2 — unrecorded-PERIOD activity on covered tickers

Surfaced by the unit-level attribution (R-IV.176(b)). These tickers pass `db_rows > 0` and so
appear in the *mismatch* population, but per-row attribution shows their rows reproduce their
own fills — the delta sits in export activity with **no DB row at all**:

| ticker | ticker delta | DB units | unrecorded block |
|---|---|---|---|
| SOXS | −105.93 | 6 | **2026-02-03 → 02-12**, ~10 fills |
| SQQQ | −100.06 | 1 | **2026-01-14 → 02-06**, ~10 fills |
| TSLQ | −85.75 | 1 | **Jan/Feb 2026** (its one unit reconciles at fee-scale) |
| URA | −36.15 | 1 | **January 2026** equity round-trips (01-13/14, 01-21/23) |
| BITX | −10.39 | 1 | **Jan and Mar 2026** (its one unit is INVALID-LIFETIME) |

### TIME-STRUCTURE — on the face, per R-IV.180(b)

**The omissions concentrate in early 2026 — January and February.** That is a bounded
window, not a diffuse sync failure. The eventual ingestion fix is therefore scoped to a
**backfill of a known date range**, not a continuous-reconciliation build. Stated at
registration so the remedy is not over-specified later.

Corollary worth recording: the ticker-level conjunction that defines the mismatch population
separates existence from valuation **at ticker level, not unit level**. A ticker can carry
`db_rows > 0` and have its entire delta in rows that do not exist. Sub-population 2 is
precisely that set.

## UNION ARITHMETIC

```
comparable tickers                110
  AGREE                            48
  MISMATCH (valuation defect)      28
  DB-MISSING (this defect, pop 1)  34
                              48+28+34 = 110    (partition, no overlap)
not-comparable                     41
union                             151            (DB 111 + export 149, intersect 109)
```

Sub-population 2 is **not** a fourth partition class — its tickers already sit inside the 28.
It is a re-reading of part of that 28, not an addition to the count.

## FIVE OPEN-WITH-ACTIVITY TICKERS — future-comparable

`ABNB` · `ORCL` · `RAMZ` · `SPCX` · `TJX` sit in the not-comparable 41 (non-zero 2026 net
flow) but each has export activity and **zero DB rows**:

```
 ABNB  -40.18  net_qty  +4      ORCL  -81.20  net_qty  +4
 RAMZ -311.04  net_qty +18      SPCX  -30.48  net_qty +10
 TJX   -64.21  net_qty  +4
```

Same existence gap; excluded from the measured total only because net cash is not realized
P&L while positions remain open. **They become comparable once flat** — flagged so their
later arrival reads as arrival, not regression. `RAMZ` and `TJX` have Fidelity-side rows
(R-IV.112-b / R-IV.105-b); a different account, and they do not close the RH gap.

## WHAT IS NOT ESTABLISHED

- **Cause.** Not proposed, for either sub-population.
- **Whether omission was intentional.** The measurement cannot distinguish a gap from a
  policy; some tickers may be deliberate exclusions.
- **Completeness.** Bounded by the export's own coverage (2025-12-09 → 2026-08-31) and by
  the comparability filter. Tickers traded and closed outside that window would not appear.
- **Whether sub-population 2 is exhaustive.** It was found by attributing five tickers. The
  other 23 in the mismatch population have not had unit-level attribution run.

## AMENDMENT R-IV.215(a) — a backfill SOURCE exists in-DB. Remedy cost changes; defect does not.

**Which ledger this defect is measured against: `unified_positions`.** The cross-check read
`account='ROBINHOOD' AND realized_pnl IS NOT NULL AND COALESCE(exit_date, entry_date) >=
'2026-01-01'`. **`trades` was never read.** That is the ledger every position-level consumer
uses — `hub_get_positions`, account rollups, the ETF-only invariant — so it is the right
surface for the defect.

A rebuild has since ingested Jan–Feb rows into **`trades`**, not into `unified_positions`:

```
trades            RH rows Jan-Feb 2026 ......  97   realized +$1,965.71
unified_positions RH rows Jan-Feb 2026 ......  70

of the 33 enumerated gap tickers
  now present in trades .....................  25
  still absent from trades ..................   8
  still DB-MISSING in unified_positions .....  33   <- UNCHANGED
```

**Measured against `unified_positions` the gap has not moved: 33 of 33, +$178.64.** Measured
against `trades`, 25 tickers now carry −$69.49 of realized and only 8 remain absent.

**BTCZ is not an exception.** It has a `unified_positions` row (id 98, CLOSED, realized
−4.00) but dated **2026-03-20**, unrelated to its Jan–Feb export activity, and it still fails
the defect's predicate.

### What this changes

For **25 of 33** the remedy is no longer re-ingest-from-broker but **PROPAGATE-AND-DIFF**
`trades` → `unified_positions`, with an in-database reference to diff against. Cheaper and
more verifiable.

### Binding conditions on any propagation

- **Key on CONTENT — ticker · dates · quantity · realized — NEVER on `trades.id`.**
  R-IV.188 established that the re-key was observed in **`trades`**, while
  `unified_positions` proved stable by content with every ruled write intact. Propagation
  would therefore be sourcing from the *less* stable of the two ledgers; an id-keyed
  propagation inherits that instability.
- **8 tickers are absent from BOTH ledgers** — `BKR` · `CAT` · `CRWV` · `CVNA` · `GHRS` ·
  `SHNY` · `SNDK` · `SPGI`. The rebuild supplies nothing for these; they still require a
  broker-sourced backfill.

### What this does not change

The defect and its magnitude **stand as measured against `unified_positions`**. A row in
`trades` is invisible to every consumer this defect is about. This is a **remedy-cost
finding**, not a correction to the measurement. Fix remains **HELD**.

## REMEDIATION

**HELD and unsequenced.** Remedy family is ingestion — an RH activity ingest path feeding
`unified_positions`, analogous to the Fidelity path (R-IV.112-b/141), scoped by the
time-structure above. No writes were made in filing or reshaping this.
