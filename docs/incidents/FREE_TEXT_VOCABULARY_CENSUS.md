# FREE-TEXT VOCABULARY CENSUS — `unified_positions`

**R-IV.450(g) · CC-POSITIONS · 2026-09-18 · READ-ONLY.** Commissioned R-IV.448(d): every
free-text column with a finite legal vocabulary gets a census; `structure` leads it.
**No writes, no schema changes.** 383 rows, all statuses.

**The headline finding is not the variant count. It is that the variants are traceable to a
writer, not spread across the book** — which makes them fixable by fixing one path rather than
by a sweep.

---

## THE SIX COLUMNS

| column | distinct values | non-canonical | verdict |
|---|---|---|---|
| `structure` | 10 | **3 rows** short-form + 3 NULL | **worst**, and fully traced |
| `direction` | 4 | **4 rows** BULLISH/BEARISH | same writer as above |
| `asset_type` | 3 | **16 rows** `SPREAD` | overlapping category, not a spelling |
| `source` | 8 | **4 rows** `fidelity_confirm` | case drift, one batch |
| `status` | 4 | 1 row `DUPLICATE_OF` | deliberate, R-IV.449(a) |
| `trade_outcome` | 4 | **25 rows NULL on a closed row** | absence, not vocabulary |

---

## 1 · `structure` — the short-form variants are ONE writer, ONE day

```
 put_debit_spread   149      long_call           12      call_spread          2   <-- variant
 stock              103      (null)               3      put_spread           1   <-- variant
 call_debit_spread   90      iron_condor          1      put_credit_spread    1
 long_put            21
```

**All three short-form rows are a single sequential batch:**

| id | position_id | ticker | structure | direction | source |
|---|---|---|---|---|---|
| 345 | `POS_AAPL_20260707_06000000` | AAPL | `put_spread` | `BEARISH` | `CSV_RECONCILE` |
| 346 | `POS_AAPL_20260707_06000001` | AAPL | `call_spread` | `BULLISH` | `CSV_RECONCILE` |
| 347 | `POS_XLE_20260707_06000002` | XLE | `call_spread` | `BULLISH` | `CSV_RECONCILE` |

Same date, same account, **consecutive sequence numbers `…00`, `…01`, `…02`**, same source.
This is not vocabulary drifting over months — **it is one import run, on 2026-07-07, writing a
different dialect.**

**`call_spread` is confirmed to mean `call_debit_spread`.** id 347 was adjudicated at
R-IV.400(b) against the export: XLE 60/65, bought 2 @ 0.36, a debit. The short form carries no
extra meaning; it is the same structure spelled shorter.

### Not variants — leave these alone

- **`iron_condor`** (id 80) and **`put_credit_spread`** (id 180) are **real, distinct
  structures**, not misspellings of anything. A credit spread is not a debit spread with a
  different name, and folding it in would destroy the row's economics.
- **`(null)` ×3** — ids 130, 131, 132, a `MANUAL` batch on **2026-04-08 within seven seconds**
  (`…231338`, `…231342`, `…231345`). These carry `asset_type=OPTION`, `structure` NULL **and no
  strikes at all**. Nothing to normalize; they need a source read or explicit exclusion
  (already flagged on `DEF-STRUCTURE-STORED-TWO-WAYS`).

## 2 · `direction` — same writer, same dialect

```
 LONG  203      SHORT  176      BEARISH  2      BULLISH  2
```

**All four non-canonical rows are `source='CSV_RECONCILE'`** — ids 345/346/347 from the 07-07
batch, plus id 385 (TJX, 08-25). id 385 is the telling one: it carries a **canonical
`structure`** (`put_debit_spread`) with a **variant `direction`** (`BEARISH`).

**So the importer is not uniformly on a different dialect — it mixes.** A fix that keys on
"rows from the 07-07 batch" would miss id 385 six weeks later.

> **Every non-canonical `structure` and `direction` value in the table came from one source:
> `CSV_RECONCILE`. Not one came from the manual-entry path.**

That is the opposite of `DEF-MANUAL-ENTRY-WRONG-ACCOUNT-LABEL`, where the manual path was the
offender and the human data was right. **Two free-text columns, two different guilty paths** —
which is why a census was the right instrument and why a single "fix the entry form" would
have closed only half of it.

## 3 · `asset_type` — `SPREAD` is a category overlap, not a spelling

```
 OPTION  264      EQUITY  103      SPREAD  16
```

All 16 `SPREAD` rows date **2026-03-04 → 03-25** and are closed. **A spread *is* an option
position**, so `SPREAD` and `OPTION` are not two values of one dimension — one is a subset of
the other, recorded as a sibling. Any count grouped on `asset_type` splits option rows across
two buckets.

**This one cannot be fixed by mapping alone**: deciding `SPREAD → OPTION` is correct only if
nothing downstream uses `SPREAD` to mean "multi-leg." That is a legs-model question, so it
belongs with `DEF-STRUCTURE-STORED-TWO-WAYS`, not here.

## 4 · `source` — one lowercase value among UPPER_SNAKE

```
 MANUAL 246 · IMPORTED_HISTORICAL 70 · CSV_RECONCILE 26 · CSV_IMPORT 14
 CSV_SYNC 10 · SCREENSHOT_SYNC 9 · SIGNAL 4 · fidelity_confirm 4   <-- case drift
```

`fidelity_confirm` (4 rows, 2026-06-11 → 06-15) is the only value not in UPPER_SNAKE. Harmless
to read, fatal to a case-sensitive `WHERE source = 'FIDELITY_CONFIRM'` — **the same failure
mode measured on `trades.account`**, where 132 of 312 Robinhood rows sat under `robinhood` and
a case-sensitive predicate returned a clean, wrong answer.

## 5 · `trade_outcome` — an absence, not a vocabulary problem

```
 WIN 170 · LOSS 157 · BREAKEVEN 3 · NULL 53
```

Of the **53 NULLs, 28 are OPEN rows** — correct, an open position has no outcome. **The
remaining 25 are CLOSED or EXPIRED rows carrying no outcome at all.** That is a real gap and it
is not a spelling question; a realized-P&L rollup grouped by outcome silently drops 25 finished
trades.

**Not measured here:** whether those 25 also lack `realized_pnl`, and whether they cluster by
source the way the structure variants do. Worth one query before anyone backfills them.

---

## WHAT THE CENSUS ESTABLISHES

1. **`structure` and `direction` are fully traced to `CSV_RECONCILE`.** Seven rows total,
   fixable at one writer. **No manual-entry row is implicated in either column.**
2. **`asset_type` is not a spelling problem** and must not be swept with the others.
3. **`source` has the same case-sensitivity hazard already measured on `trades.account`.**
4. **`trade_outcome`'s 25 NULLs are a data gap** that a vocabulary fix would not touch.
5. **A CHECK constraint would have prevented 1 and 3 and neither 2 nor 4** — which is the
   already-recorded point that a constraint is not the whole fix, now with a measured split.

## WHAT IT DOES NOT ESTABLISH

- **Why `CSV_RECONCILE` emits a second dialect.** The importer is untraced; that is BUILD's.
- **Whether `SPREAD` carries meaning** some consumer depends on.
- **Whether the 25 outcome-less rows share a cause.**
- **Anything about columns outside this table.** `trades`, `closed_positions` and
  `cash_flows` were not censused.
