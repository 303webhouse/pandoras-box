# CONVENTIONS INSTANCE — A BACK-SOLVED INPUT SURVIVES ITS OUTPUT'S CORRECTION

**FROM:** CC-POSITIONS — sole author (conventions #9). **Commissioned:** R-IV.458(c).
**Kin to:** `conventions.md` → *A DERIVED VALUE CANNOT WITNESS ITS OWN INPUT* (R-IV.336(a)), and
#23 *AN ADJUDICATION SHOWS ITS EVIDENCE LINES BESIDE ITS VERDICT*.

---

## THE SHAPE

An output is taken as given, and an input is solved backwards from it so that the row agrees
with itself. **When the output is later corrected, the input stays** — still consistent with the
figure the book no longer holds, and now inconsistent with the one it does.

> **A value solved from another value inherits that value's error, and does not leave when the
> error does. Correct the output without re-deriving what was solved from it, and the row
> disagrees with itself — and a re-derivation check will side with the old figure.**

---

## THE INSTANCE — six rows, 2026-09-18 → 09-19

R-IV.457(d) corrected six realized figures to the export's gross at **19:33:35 UTC on
2026-09-18**. The exit prices beside them were left as stored, flagged but not changed, because
only the realized figures had been adjudicated. They were corrected under R-IV.458(c) at
**06:00:25 UTC on 2026-09-19**. **For 10 h 27 m, each of the six rows disagreed with itself.**

| id | exit as stored | what it equals | fill in the export |
|---|---|---|---|
| 351 XLE | 0.9994 | (81.94 + 18.00) / 100 — the superseded figure plus basis | **0.82** (L151) |
| 357 AMC | 0.0582 | (28.00 − 16.36) / 200 — from the superseded net | **0.06** (L163/L162) |
| 352 TSLA | 1.7488 | (128.78 + 46.10) / 100 — from the superseded net | **1.75** (L154/L153) |
| 347 XLE | 0.8290 | 82.90 / 100 — close cash | **0.83** (L135/L134) |
| 343 DRAM | 1.2490 | 124.90 / 100 — close cash | **1.25** (L143/L142) |
| 38 META | 0.1100 | (0.11 − 0.5767) × 300 = −140.01 exactly | **0.12** (L1159–L1162) |

**Five of the six cannot be fills.** Each is one contract or one spread, and every leg trades in
whole cents, so the price per contract or spread is a whole cent too. A price of 0.0582 or 0.9994
can only have come from arithmetic, and each equals the superseded figure's identity to the
digit.

**The sixth is not proven.** META's 0.11 is a legal fill price, and the identity holds in both
directions. Whether 0.11 produced −140.01 or was solved from it is **UNKNOWN**. The export says
only that 0.11 was wrong.

**The input carried the old answer's fingerprint in its digits.** A four-decimal exit price on
a penny-increment contract is the identity of the old figure, not a price.

**Two more, found 2026-09-19 while adjudicating F4 (R-IV.464(e)):** AAPL **345** stored exit
0.149 and **346** stored 0.749 — close cash over 100, solved from realized figures that were
themselves close-cash-less-gross-basis. Same shape, same correction: −22.00 and +40.00 gross,
exits 0.15 and 0.75.

---

## WHY IT IS WORSE THAN A STALE NUMBER

During those ten hours, anything that re-derived realized from the row's own prices would have
**endorsed the old figure and refused the correct one**:

```
351:  (0.9994 - 0.18) x 100  =  +81.94   the superseded figure
                                 +64.00   the figure on the row
```

That is exactly the check BUILD built on the close path (`expected_realized`: "the stored number
stays the one this row can re-derive"). **Pointed at these rows, it would have called the
correction the error.** The back-solved input did more than lag the correction: it testified
against it.

---

## RESIDUE — inputs that survived THIS pass's corrections

The same shape, found while checking this filing:

| id | column | stored | should follow | why it survived |
|---|---|---|---|---|
| 352 TSLA | `max_loss` | 46.10 | the gross debit, 46.00 | the correction path does not carry `max_loss` |
| 358 GUSH | `max_loss` | 586.35 | the basis for 15.35049 shares, 600.05 | the same |
| 38 META | entry vs realized | (0.12 − 0.5767) × 300 = −137.01 | −137.00 | entry is 173/300 stored to four places |

**Not corrected here.** None of them is ruled, and the first two have no path to write through.

---

## THE RULE THIS INSTANCE ADDS

- **A correction lists what was derived from the figure it replaces, and what the figure was
  derived from.** Each item is re-derived in the same write or flagged on the row by name.
  Flagging is what R-IV.457(d) did; it limited the damage and did not stop it.
- **After a correction, re-run the row's own identity** (quantity × (exit − entry) × multiplier
  against realized). A mismatch means an input still holds the old answer.
- **A sub-increment price on an increment-traded instrument is not a fill — but it is not
  automatically a back-solve either.** On a row holding ONE fill it can only be arithmetic, and
  it is the fingerprint of whatever figure it was solved from. On a row holding SEVERAL fills it
  may be their weighted average, which is legitimate: IBIT **319** now stores 0.045 for two
  contracts at 0.08 and two at 0.01 (R-IV.464(e)). **The test is the row's fill count** — and a
  row whose lots were flattened into one cannot answer it, which is the same missing capability
  as a closed row that cannot take its lots.
