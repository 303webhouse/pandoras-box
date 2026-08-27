# PR-106 PART 1 - REALIZED METRICS BY SECTOR x INSTRUMENT CLASS

Executor CC-QUERY - SELECT-only / read-only. Rebuilt under R-IV.118(a)-(c); the prior build hashing 657a0386 is STRUCK.

## Header (Addendum 1 - sources by hash, computed at read time)
```
in-script wall-time (in-DB UTC) : 2026-08-27 17:38:08.570701
data/imports/90d/merged_ledger.csv
    sha256 6ab4d5c1f9c2315281349432e004718816844c3d6885c9eca159c24bb800f9d6
data/imports/90d/merged_ledger_flags.csv
    sha256 3ae39c9520241e3acfff112a5b84ac7a8b2fba0a3c95fe7087462d5b3b78b645
data/imports/90d/merge_reconciliation.json
    sha256 2d384b1a62ed39b185c09e14eaae3f52b08a085a48c66a7405c271330971c9c6
data/imports/90d/fidelity_db_half_notes_sidecar.md
    sha256 026cc8ea4700b3c9ac74024fca51f97d7ba3aff7f62044a26ed9723c1a57c460
population        : BOTH accounts, equity/ETF class (Amendment 4 / R-IV.110(a))
unit              : one trade = one position lifetime; account is provenance, not a partition
sector assignment : closed 133-ticker map (Amendments 1-3), static lookup, not a query
```

## Face statements

**Scope label (PATCH 1, R-IV.115(b)) - DAEDALUS amendment verbatim:** "ETF book measured high-hit/symmetric (66 units); options-book identity UNMEASURED until PR-106 part 2." The spine original unscoped pairing is STRUCK. The measured population is the equity/ETF class only; 103 OPTION-typed tickers await the realized backfill, so an unqualified identity claim would let a finding about the smaller half stand for the book.

**SBU exclusion layer (PATCH 5):** "SBU is excluded from SECTOR CELLS (UNCLASSIFIED pending R-IV.94(g)), not from the population. Its trade unit is ADMITTED, contributes_unit=True, PRINCIPAL-ATTESTED-INTERIOR, realized +59.00, and it is counted in the 53 units and in realized_admitted 1,098.76. Its benchmark series is absent and inert (R-IV.111(c)): no arm consumes it, because an instrument with no sector cell has no cell reference to be benchmarked against."

**Data guard (PATCH 2, R-IV.111(b)(1)):** "Sentinel string lives in ENTRY_DATE (5 rows = the 5 UNKNOWN-BASIS seeds). exit_date measured ZERO non-dates at hash 6ab4d5c1...; this hashed read supersedes both earlier unhashed reports."

**OVERLAP-UNMATCHED annotation (PATCH 3) - three-cause split verbatim; the "sentinel artifact" class label is DEAD:** "10 OVERLAP-UNMATCHED rows decompose three ways - 4 sentinel-seeded (SOXS x2 / GDXY / XLE) - 4 date-offset matched pairs (MOO / MSTZ x2 / TSLQ, fee-level deltas, among the 13 validated pairs) - 2 GUSH, the only genuine candidates, already carried on the Dimension-B lifecycle item. Eight of ten have benign explanations; two are named."

**Sub-gate clause (PATCH 4, R-IV.111(b)(3)) - INERT for part 1:** "Sub-gate accumulation-rate clause is INERT for part 1: no threshold exists in the registered text, and the executor correctly declined to invent one. Part 2 fixes a threshold pre-render or drops the clause."

**Sample band (Addendum 2):** n=53 admitted trade units against the pre-registered ~50-60 expectation (R-IV.93(c)) - **IN BAND**.

**Band statement, verbatim:** "The 53/53 / 64/64 band closed exactly. This is the completeness DETECTOR passing, not completeness confirmed - a <=2-unit understatement lies inside a spread of 11 by construction. Two rows describing multiple closing events in prose (POS_GDXY_20260610_173410, POS_SOXS_20260526_170617) are the named, bounded residue; GDXY is OVERLAP-UNMATCHED with contributes_unit=False."

**Disclosure label (R-IV.97(e)), verbatim, historical record:** "sector classification built without outcome values; ticker salience for SOXS and validation status for five tickers disclosed in R-IV.93(c)."

**ENERGY: the only cell testing against uncontaminated outcomes.**

**LAYERED COUNTS (R-IV.118(b)) - each count states its layer:**

| layer | n | realized |
|---|---|---|
| population (smoke-excluded) | 69 | $1203.60 |
| cells-contributing | 66 | $1124.23 |
| cells-contributing tickers | 25 of 133 universe | - |

---

## Per-cell metrics - sector x EQUITY_ETF

Options rows are part 2, excluded here and enumerated. Cross-class pooling barred. The UNCLASSIFIED sector cell DISSOLVES per R-IV.118(a) - a classification failure is not a category.

### SEMIS/DRAM x EQUITY_ETF

**n = 14**  -- **SHAPE, not a finding** (n < 30)

| n | win rate | avg win | avg loss | expectancy/trade | total realized |
|---|---|---|---|---|---|
| 14 | 85.7% | $83.71 | $-32.44 | $67.12 | $939.66 |

**Provenance-tier line:** 8 BROKER-VALIDATED / 2 CSV_RECONCILE / 3 MANUAL / 1 PRINCIPAL-ATTESTED-INTERIOR - accounts: 9 FIDELITY_ROTH / 5 ROBINHOOD

tickers: RAMZ / SOXL / SOXS

**REALIZED-DISCRETIONARY** - measures the principal discretionary book only; says nothing about signal-layer strategy edge, and Track A says nothing about it.

### ENERGY x EQUITY_ETF

**n = 7**  -- **SHAPE, not a finding** (n < 30)

| n | win rate | avg win | avg loss | expectancy/trade | total realized |
|---|---|---|---|---|---|
| 7 | 71.4% | $30.93 | $-113.77 | $-10.41 | $-72.89 |

**Provenance-tier line:** 5 BROKER-VALIDATED / 1 MANUAL / 1 PRINCIPAL-ATTESTED-INTERIOR - accounts: 6 FIDELITY_ROTH / 1 ROBINHOOD

tickers: GUSH / NLR / URA

**REALIZED-DISCRETIONARY** - measures the principal discretionary book only; says nothing about signal-layer strategy edge, and Track A says nothing about it.

### PRECIOUS METALS/MINERS x EQUITY_ETF

**n = 9**  -- **SHAPE, not a finding** (n < 30)

| n | win rate | avg win | avg loss | expectancy/trade | total realized |
|---|---|---|---|---|---|
| 9 | 55.6% | $34.05 | $-60.07 | $-7.78 | $-70.03 |

**Provenance-tier line:** 7 BROKER-VALIDATED / 2 PRINCIPAL-ATTESTED-INTERIOR - accounts: 9 FIDELITY_ROTH / 0 ROBINHOOD

tickers: GDX / GDXJ / JNUG / NUGT

**REALIZED-DISCRETIONARY** - measures the principal discretionary book only; says nothing about signal-layer strategy edge, and Track A says nothing about it.

### CRYPTO x EQUITY_ETF

**n = 12**  -- **SHAPE, not a finding** (n < 30)

| n | win rate | avg win | avg loss | expectancy/trade | total realized |
|---|---|---|---|---|---|
| 12 | 66.7% | $34.20 | $-26.49 | $13.97 | $167.66 |

**Provenance-tier line:** 7 BROKER-VALIDATED / 3 MANUAL / 2 PRINCIPAL-ATTESTED-INTERIOR - accounts: 9 FIDELITY_ROTH / 3 ROBINHOOD

tickers: BITI / BITX / BTCZ / CRCL / MSTZ

**REALIZED-DISCRETIONARY** - measures the principal discretionary book only; says nothing about signal-layer strategy edge, and Track A says nothing about it.

### OTHER x EQUITY_ETF

**n = 24**  -- **SHAPE, not a finding** (n < 30)

| n | win rate | avg win | avg loss | expectancy/trade | total realized |
|---|---|---|---|---|---|
| 24 | 62.5% | $34.68 | $-40.04 | $6.66 | $159.83 |

**Provenance-tier line:** 7 BROKER-VALIDATED / 7 MANUAL / 10 PRINCIPAL-ATTESTED-INTERIOR - accounts: 17 FIDELITY_ROTH / 7 ROBINHOOD

tickers: CF / ICE / IPI / MOO / NBIS / QQQI / SQQQ / SRTY / TLT / TSLQ

**REALIZED-DISCRETIONARY** - measures the principal discretionary book only; says nothing about signal-layer strategy edge, and Track A says nothing about it.

### Ledger-wide (cells-contributing layer)

**n = 66** - win rate 68.2% - avg win $47.18 - avg loss $-47.57 - expectancy/trade $17.03 - total realized $1124.23

### Exclusions, enumerated per row with layer and reason

**POPULATION-EXCLUDED (SMOKE-ARTIFACT, R-IV.118(a))** - fail the unit definition, enumerated beside the INVALID-LIFETIME trio:

- TEST id=171 account=ROBINHOOD realized=$0.50 - SMOKE-ARTIFACT
- TEST_C1 id=172 account=ROBINHOOD realized=$5.00 - SMOKE-ARTIFACT

**CELL-EXCLUDED, POPULATION-RETAINED (SBU treatment, R-IV.118(a))** - real trades, unclassifiable; counted in the population layer, absent from every sector cell:

- SBU id=POS_SBU_20260429_031106 account=FIDELITY_ROTH realized=$59.00 tier=PRINCIPAL-ATTESTED-INTERIOR
- SSPC id=4f8ccd244633dcdf;48e2516344119523 account=FIDELITY_ROTH realized=$13.90 tier=BROKER-VALIDATED
- WRTH id=a347e93e29c7a638;5778ec276e0a0921 account=FIDELITY_ROTH realized=$6.47 tier=BROKER-VALIDATED

**Ledger-side exclusions carried from the merge:** LIFECYCLE-UNVALIDATED 11 / OVERLAP-UNMATCHED 10 / SUPERSEDED-BY-EXPORT 8 / UNKNOWN-BASIS 5 / STILL-OPEN 2 / INVALID-LIFETIME 3 (368 SOXS / 369 BITX / 370 SQQQ).

**REALIZED-DISCRETIONARY** - measures the principal discretionary book only; says nothing about signal-layer strategy edge, and Track A says nothing about it.
