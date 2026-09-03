# DEF-RH-EQUITY-REALIZED-MISMATCH

**Severity:** P2 · **Filed:** 2026-09-02 · **Narrowed:** R-IV.180(b) · **Class:** VALUATION
**Status:** OPEN — registration only. Remediation HELD and unsequenced per R-IV.170(e)/180(e).
**Owner:** CC-POSITIONS (evidence) · BUILD (pickup)
**Surface:** `unified_positions.realized_pnl` / `entry_price` / `exit_price` / `cost_basis`,
account `ROBINHOOD`
**Evidence:** `rh_crosscheck.json` (ticker level) · `rh_unit_attribution.json` (unit level)

## HEADLINE

**Robinhood units whose stored numbers disagree with the broker.** Worked instances are real
and large in ratio. But unit-level attribution has **narrowed this defect substantially**:
most of the ticker-level $278.10 turns out to sit in rows that do not exist, which is
`DEF-RH-COVERAGE-GAP`, not this.

The population below is a **ceiling on this defect, not its size.**

## POPULATION — the 28, by conjunction

The class is a conjunction, not a threshold. It reproduces exactly from `rh_crosscheck.json`
and has been reproduced independently by CC-QUERY from a byte-identical copy:

```
COMPARABLE = db_rows > 0 AND flat AND export_fills > 0          -> 76
   |delta| <  0.50   -> 48   matched
   |delta| >= 0.50   -> 28   mismatched      <- this defect
                              48 + 28 = 76
```

Equivalently: comparable (zero 2026 net flow, no 2025 carry-in, export activity present),
then `db_rows > 0`, then the $0.50 threshold. **A delta sweep alone does not reach 28**
(≥25 → 38, ≥50 → 24, and `db_rows>0 AND |delta|≥0.50` alone → 52); the missing predicate is a
conjunct. Recorded because the earlier inference that "28 must be ticket-defined" rested on
sweeping thresholds without the conjuncts, and is withdrawn.

Aggregate at ticker level: **DB-low by $278.10** across the 28.

## WORKED INSTANCES — ids 91 and 92, the only confirmed unit-level cases

| id | ticker | DB before | broker | factor |
|---|---|---|---|---|
| 91 | NBIS | −0.20 | **−40.40** | ~202x |
| 92 | ICE | −0.52 | **−8.92** | ~17x |

### VALUES-ONLY ANSWER — the erratum's §3 gate

*R-IV.170(c)1 requires this on the face. R-IV.169(d) patches the filed erratum from it.*

**The correction moved VALUES ONLY. Quantities did not move. Calendar dates did not move.**

From the R-IV.139 preimage/postimage pair (`r139_write_result.json`):

```
id 91 NBIS                 preimage                     postimage             verdict
  quantity                 5                            5                     SAME
  entry_price              115.11                       128.62                changed
  cost_basis               575.55                       643.10                changed
  exit_price               115.07                       120.54                changed
  realized_pnl             -0.20                        -40.40                changed
  exit_date                2026-03-17 18:06:03.395103Z  2026-03-17 20:00:00Z  same DATE
  status / trade_outcome   CLOSED / LOSS                CLOSED / LOSS         SAME

id 92 ICE                  preimage                     postimage             verdict
  quantity                 4                            4                     SAME
  entry_price              160.97                       160.21                changed
  cost_basis               643.88                       640.84                changed
  exit_price               161.10                       162.44                changed
  realized_pnl             -0.52                        -8.92                 changed
  exit_date                2026-03-17 18:06:15.644325Z  2026-03-17 20:00:00Z  same DATE
  status / trade_outcome   CLOSED / LOSS                CLOSED / LOSS         SAME
```

**Qualification, stated not buried:** `exit_date` moved in time-of-day only — a sub-second
capture timestamp normalised to this lane's 20:00Z close convention. **Calendar date identical
on both rows; quantity untouched.** So: values only, with a convention normalisation on the
timestamp rather than a correction to when the trade occurred.

## NARROWING — unit-level attribution (R-IV.176(b)/180(a))

Five unworked candidate tickers were attributed row by row (`rh_unit_attribution.json`,
10 DB units: SOXS 6, SQQQ/TSLQ/URA/BITX 1 each).

**CANDIDATE ids: 69 · 150 · 188 · 348 · 354 · 382 · 383** — seven, corrected below.
**Excluded, do not intersect: 368 · 369 · 370 only**, on INVALID-LIFETIME (NULL
entry_price/exit_price/cost_basis; realized_pnl present with no derivation).

> **CORRECTION (R-IV.192 pass, CC-POSITIONS error).** An earlier version of this file and of
> `rh_unit_attribution.json` labelled **348 and 382** `EXCLUDED-UPSTREAM (EDGE)`. That was
> wrong. The label was taken from a relay parenthetical enumerating rows a mismatch *might
> land on* ("SOXS 368/348/382, SQQQ 370") and hard-coded as a disposition without checking it
> against the ledger. Both are ordinary units with real prices and realized values, and
> CC-QUERY confirms both are **IN THE 66, src=B**.
>
> **`CSV_RECONCILE` is a source tier, not a disposition.** 368/369/370 are excluded because
> their entry/exit/basis are NULL, not because of their source.
>
> This is load-bearing: the weakening argument "a mismatch landing on an already-excluded row
> changes nothing" **does not apply to 348 or 382**. Both contribute.

Content keys for the two restored units:

```
id 348  SOXS  opened_at 2026-07-07 06:00:00+00  qty 87  realized -58.30  CSV_RECONCILE
id 382  SOXS  opened_at 2026-08-05 13:00:10+00  qty  8  realized  +5.14  CSV_RECONCILE
```

### Intersection result (CC-QUERY, on the five originally submitted)

```
188  SOXS  05-14  50  +29.00   IN THE 66 — SEMIS/DRAM, src=B
354  SOXS  07-15   6  +69.79   IN THE 66 — SEMIS/DRAM, src=B
383  SOXS  08-17   6  +38.28   IN THE 66 — SEMIS/DRAM, src=B
 69  TSLQ  03-11  30  +24.10   IN THE 66 — OTHER,      src=B
150  URA   04-23   1  +24.00   OUT-OF-SCOPE (option; no content-key match)
```

348 and 382 were withheld from that pass by the error above and require intersection.
SEMIS/DRAM already carries 3 of 4 hits; both restored units are SOXS, so the concentration
in that cell can only increase.

### Content key is not unique at day granularity

R-IV.183(b) ruled `(ticker, opened_at)`. At **day** granularity the 66 units occupy only 61
distinct keys — five collide, including SOXS 2026-07-15 and TSLQ 2026-03-11, which are two of
the four hits. Keying on ticker+date alone resolves them to the wrong source tier by ordering.
**Adding `quantity` and `realized_pnl` resolves all five uniquely** and is the recommended key.

`position_id` is UNIQUE and stronger, but **the timestamp encoded in it is not a reliable join
key** — 2 of 5 sampled ids disagree with their own `entry_date`:

```
 id 348  POS_SOXS_20260707_060000 03  entry_date 2026-07-07 06:00:00+00   agree
 id 354  POS_SOXS_20260715_060000     entry_date 2026-07-15 00:00:00+00   DISAGREE  6h (TZ artifact at minting)
 id 382  POS_SOXS_20260805_130010     entry_date 2026-08-05 13:00:10+00   agree
 id  69  POS_TSLQ_20260311_000848     entry_date 2026-03-11 00:08:48+00   agree
 id 170  POS_XLF_20260429_062700      entry_date 2026-04-28 00:00:00+00   DISAGREE  date AND time
```

**Two candidates already reconcile against export and are unlikely to be instances:**

```
id 188  SOXS   Buy 50 @8.40 (-419.75) -> Sell 50 @8.98 (+449.01) = +29.26   DB +29.00   fee-scale
id 354  SOXS   -277.25 -> +347.04                                = +69.79   DB +69.79   EXACT
id  69  TSLQ   Buy 20@21.70 + 10@20.85 -> Sell 30@22.22          = +23.95   DB +24.10   fee-scale
```

**The ticker deltas are dominated by unrecorded activity, not by wrong units.** SOXS, SQQQ,
TSLQ, URA and BITX each carry export blocks in early 2026 with no DB row. That is
`DEF-RH-COVERAGE-GAP` sub-population 2, surfacing inside this population because the ticker
has *some* rows and so passes `db_rows > 0`.

**Consequence for erratum-2 scoping:** a mismatch on these tickers is unlikely to move an
existing unit across the win/loss boundary, because the discrepancy is largely not on the
units. The no-inheritance clause still binds — every invariant re-derives — but the exposure
is smaller than the ticker-level magnitudes suggest.

## WHAT IS NOT ESTABLISHED

- **Mechanism.** Not proposed. ids 91/92 both understated *losses*; the aggregate understates
  *wins*. Those may not share a cause.
- **Representativeness.** ids 91/92 are two worked instances, not shown typical of the other 26.
- **Per-row attribution beyond five tickers.** 23 of the 28 have had no unit-level attribution.
- **The true size of this defect.** Unknown and **strictly less than** the $278.10 ceiling,
  by the amount attributable to sub-population 2.

## SCOPE BOUNDARY

41 tickers are not comparable (open at year end and/or 2025 carry-in — XLE has both) and are
outside this defect. Two are test rows (`TEST` 171, `TEST_C1` 172) with no export fills.
`BTCZ` and `RAMZ` route to `DEF-RH-COVERAGE-GAP`: `db_rows = 0`, **there is no unit to be
wrong**. `IPI` reclassed AGREE (+$0.06, inside threshold). `CRCL`/`CF` not-comparable.

## REMEDIATION

**HELD and unsequenced.** No writes were made in filing or narrowing this.
