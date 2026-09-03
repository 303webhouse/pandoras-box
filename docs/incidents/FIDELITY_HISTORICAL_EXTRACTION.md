# FIDELITY ACCT-ROTH — HISTORICAL EXTRACTION + OVERLAP VALIDATION

**READ-ONLY. No writes performed.** Precedes Phase 1a.

**Dual-provenance stamp** (R-IV.84(h)):

| provenance | value |
|---|---|
| **Tree SHA** | **`8b2d767`** — own fetch 2026-08-25 07:15 UTC, `git ls-remote` confirmed, 0 ahead / 0 behind |
| **DB read** | 2026-08-25 07:10–07:16 UTC, read-only Postgres MCP, `::text` on all timestamps |
| **Stamped** | 2026-08-25 07:16 UTC (2026-08-25 01:16 MDT) |

`unrealized_pnl` and `current_price` were **not read** for any ledger purpose, per
DEF-MARK-INTEGRITY. Realized-from-exit only. `hub_get_positions` not used as a read path.

---

## HEADLINE — the record is NOT Jan–May. It starts 2026-03-11.

The premise under Task 1, and under Flag 2's sample-growth expectation, is that the
principal maintained the Fidelity record "from 2026-01-01." **He did not.**

```
 FIDELITY earliest entry_date ........ 2026-03-11 18:34:48.856412+00
 FIDELITY rows BEFORE 2026-03-11 ..... 0
 FIDELITY latest entry_date .......... 2026-06-18 17:49:13.085966+00
```

**Zero Fidelity rows exist before 2026-03-11.** There is no January and no February data.
POSITIONS could see back to 03-18 via ticker-scoped queries; the true earliest is
**2026-03-11** — one week earlier, not four months.

**Likely source of the recollection:** `ROBINHOOD` rows *do* begin **2026-01-05**. The hub
was maintained from the first of the year — but the *Fidelity* half of it was not.

**Consequence for PR-106:** the extended history is **~3.2 months (03-11 → 06-18)**, not
eight. Any sample-growth projection built on an eight-month series is overstated by more
than half before the overlap test is even run.

---

## Blockers — confirm each is a tool limit, not a data gap

### 1. `exit_price` / `realized_pnl` — CONFIRMED TOOL LIMIT

Both columns exist in `unified_positions` and are populated:

| field | column name | type | populated (Fidelity) |
|---|---|---|---|
| exit price | **`exit_price`** | `numeric` | 42 / 46 |
| realized P&L | **`realized_pnl`** | `numeric` | 42 / 46 |
| exit timestamp | **`exit_date`** | `timestamptz` | 42 / 46 |

The four unpopulated rows are the four still open. `hub_get_positions`'s serializer
`_build_position` ([positions.py:78-97](../../backend/hub_mcp/tools/positions.py#L78-L97))
emits **none of these three** — it emits `unrealized_pnl` only. **Tool limit, not a data
gap.** The clean realized ledger is fully present in the table.

### 2. `hub_get_positions(account=…)` — REFUTED as the same family. Item 13 is TWO bugs.

The two code paths are structurally different, and only one is broken:

**Balances (broken).** `get_account_balances`
([balances.py:33-38](../../backend/services/read_only/balances.py#L33-L38)) does
`WHERE account_name = $1` on `account.upper()`. `account_balances` stores `'Fidelity Roth'`
— space, mixed case. `'FIDELITY_ROTH' ≠ 'Fidelity Roth'` → 0 rows. Confirmed by direct
probe in Phase 0b: only `BROKERAGE_LINK_401K` matches.

**Positions (sound).** `_normalize_account`
([positions.py:44-52](../../backend/hub_mcp/tools/positions.py#L44-L52)) uses an explicit
mapping dict, not `.upper()`:

```python
mapping = {"robinhood": "ROBINHOOD", "fidelity_roth": "FIDELITY_ROTH", ...}
```

and `list_positions` ([read_only/positions.py:57-69](../../backend/services/read_only/positions.py#L57-L69))
matches a **literal**: `conditions.append("account = 'FIDELITY_ROTH'")`. All 46 Fidelity
rows store exactly `'FIDELITY_ROTH'`. **The filter matches and should return 46 rows.**

So the `.upper()` mismatch **does not exist on the positions path**. Item 13's balances bug
is real; the positions failure is **not** the same family and needs its own cause.

**What that failure actually is: UNKNOWN.** I can confirm the account-filter logic is
correct; I cannot reproduce or explain the error POSITIONS observed twice, and I did not
invoke the tool to try (standing instruction). Reporting the refutation, not a substitute
diagnosis.

### 3. Split contamination — **the ~6x is mostly real price decay, and nothing is 10x**

This is the blocker most consequential to Flag 2, and the premise needs correcting.

**Which rows carry adjusted units: exactly ONE.**

| rows | units | applied by |
|---|---|---|
| `POS_SOXS_20260610_154556` (entry 40.395) | **×10 adjusted** | `scripts/def_position_integrity.py` — hardcoded `position_id`, guard `entry_price < 20`, pre-split 4.0395 → 40.395, qty 450 → 45 |
| all other 8 Fidelity SOXS rows | **raw as entered** | nothing — no mechanism exists |

Phase 0 Q3.5 established there is **no corporate-actions table, no adjustment column, and
no adjustment log** anywhere in the schema. That one script, keyed to one id, is the only
adjustment that has ever run. So "part adjusted, part raw" is true — but the split is
**1 row vs 8**, not a date range.

**Every row is internally unit-consistent.** `realized_pnl` reproduces exactly from
`(exit − entry) × qty` on all 8 closed rows — max delta **$0.005** (rounding on the
5.8801 row):

```
 position_id                   qty   entry     exit    stated    recomputed   delta
 POS_SOXS_20260318_051305       25  38.8520  38.8000    -1.30       -1.30    0.0000
 POS_SOXS_20260401_174006       15  35.4100  36.4900    16.20       16.20    0.0000
 POS_SOXS_20260407_165228       15  35.1800  27.6600  -112.80     -112.80    0.0000
 POS_SOXS_20260428_065253       35  14.3300  14.8400    17.85       17.85    0.0000
 POS_SOXS_20260513_183950      100   8.2500   8.9200    67.00       67.00    0.0000
 POS_SOXS_20260526_170058       50   9.7300   8.7500   -49.00      -49.00    0.0000
 POS_SOXS_20260526_170617      250   5.8801   5.4100  -117.52     -117.52   -0.0050
 POS_SOXS_20260609_230655      150   5.4100   6.1100   105.00      105.00    0.0000
```

**The decisive test is same-day price pairs** — one row's exit against another's entry on
the same calendar date. A real quote cannot be two values on one day, so any gap here is
an artifact:

| date | prices observed | ratio | verdict |
|---|---|---|---|
| 2026-04-07 | exit 36.49 / entry 35.18 | **1.04** | ✅ consistent (intraday) |
| 2026-05-13 | exit 14.84 / entry 8.25 | **1.80** | ⚠️ discontinuity |
| 2026-05-26 | exit 8.75 / entry 5.8801 | **1.49** | ⚠️ discontinuity |
| 2026-06-09 | exit 5.41 / entry 5.41 | **1.000** | ✅ exact |
| 2026-06-10 | exit 6.11 / entry 4.0395 *(raw)* | **1.51** | ⚠️ discontinuity |

**No gap is 10x. None is even 2x.** A 1-for-10 reverse split produces exactly 10×. These
are 1.49–1.80×, and two same-day pairs are clean — including 06-09 matching to the cent.

**Decomposition of the ~6x.** Total move 03-18 → 06-10 is 38.852 → 4.0395 raw = **9.62×**.
The three discontinuities compound to 1.80 × 1.49 × 1.51 = **4.05×**. So:

- **~4.05× is unexplained same-day discontinuity** — real, and larger than I first judged
- **~2.38× is genuine price decay** — ordinary for a 3× inverse semiconductor ETF over
  three months, and precisely why the reverse split happened

**Ruling: this is NOT split contamination.** It is three discrete ~1.5–1.8× breaks whose
cause is **UNKNOWN** and cannot be adjudicated from DB state. Candidate explanations
(data-entry from mixed sources, lot-averaging, partial-close accounting) are not separable
without the broker export.

**This strengthens the case for the overlap test rather than threatening it.** The overlap
export is the exact instrument that would resolve these three breaks. Flag 2 lists split
contamination as a known pre-data threat; on measurement it is a smaller, different, and
*testable* anomaly — and the test is the one already briefed.

---

## Task 1 — Historical ledger extracted

**Scope:** all Fidelity-labelled rows, `entry_date` 2026-01-01 → 2026-06-30, every status.

```
 rows ............................ 46   (all 46 Fidelity rows fall in this range)
 accounts ........................ FIDELITY_ROTH 46 · BROKERAGE_LINK_401K 0
 date span ....................... 2026-03-11 → 2026-06-18
 distinct tickers ................ 23
 priced (realized_pnl NOT NULL) .. 42
 open (no exit) .................. 4    GUSH · SOXS · GDXJ · XLE
 rows touching 05-27 → 06-18 ..... 22
```

**Tickers (23):** BITI · BITX · BTCZ · GDX · GDXJ · GDXY · GUSH · JNUG · MOO · MSTZ ·
NLR · NUGT · QQQI · SBU · SMST · SOXL · SOXS · SQQQ · SRTY · TLT · TSLQ · URA · XLE

**Sources:** `MANUAL` 42 · `fidelity_confirm` 4. All `structure='stock'`, all EQUITY —
the ETF-only invariant holds across the full history, with `SBU` still the one unconfirmed
classification (single row, 2026-04-29, outside every window).

**22 of 46 rows touch the overlap window** — a substantial test set. If the overlap
validation can be run, it has real statistical purchase.

---

## Task 2 — OVERLAP VALIDATION: CANNOT BE RUN. Three independent blockers.

**1. The 90-day export does not exist.** `data/imports/` holds only the 60-day file
(`History_for_Account_ACCT-ROTH.csv`, 18,306 B, mtime 2026-08-24 12:23, 107 raw rows → 83
fills). Searched the repo, `~/Downloads`, `~/Desktop`, `~/Documents` — no 90-day or
multi-account export anywhere.

**2. The normalizer has not been updated for the multi-account form.** The brief states it
"now handles" the form that omits `Cash Balance` and carries `Account Number`. The file on
disk (mtime 2026-08-24 18:37, unchanged) hard-depends on the omitted column at
[line 66](../../data/imports/normalize_fidelity_history.py):

```python
t["settled"] = t["Cash Balance ($)"].astype(str).str.strip() != "Processing"
```

Against the multi-account form this raises `KeyError: 'Cash Balance ($)'`. There is no
`Account Number` handling anywhere in the file. It would fail, not adapt.

**3. Decisively — the 60-day export does not reach the overlap window at all.** It spans
**2026-06-25 → 2026-08-24**. The overlap window is **2026-05-27 → 2026-06-18**. These do
not intersect; the export begins seven days *after* the window closes.

So Task 2 cannot be run in full **or in part**, and no substitute exists. Both artifacts
must arrive. This is not a degraded result — it is no result, reported as such.

---

## Task 3 — Report, do not resolve

### id 368 — the price test cannot be run. Both prices are NULL.

```
 id 368  POS_SOXS_20260720_120005   ticker SOXS   qty 10   account ROBINHOOD
 entry_price  NULL          exit_price  NULL          cost_basis  NULL
 realized_pnl 20.57         source CSV_RECONCILE      structure stock
 entry_date   2026-07-20 12:00:05+00
 exit_date    2026-07-20 00:00:00+00
```

**Ticker is SOXS and quantity is 10 — both match.** But `entry_price` is **NULL**, so the
"~52.38" comparison the brief specifies is **not answerable**. Only `realized_pnl` exists.

**A separate observation weakens the double-record hypothesis on the CSV's own evidence.**
id 368 records an entry *and* an exit on 2026-07-20. The Fidelity CSV's only 07-20 fill is
a **BUY 10 @ 52.38** — an opening trade. That lot is not sold on 07-20; the next SOXS sells
are 07-24 (SELL 30 @ 49.06) and 07-27. So the CSV shows no 07-20 round trip, while id 368
claims one. On date and quantity they coincide; on trade shape they do not.

**Verdict: UNRESOLVED, and not resolvable from these artifacts.** It needs the Robinhood
export for the window. Three of the eight ROBINHOOD equity rows (ids 368, 369, 370 — all
`CSV_RECONCILE`) carry NULL entry *and* exit prices, so price-matching cannot adjudicate
any of them.

### Zero-basis: the DB history closes 2 of 5 fully, 1 nearly, 1 partially, 1 not at all

DB positions open as of **2026-05-27** (the 90-day window start), versus the pre-window
inventory the brief reports:

| ticker | brief's pre-window need | DB open at 05-27 | closes? |
|---|---|---|---|
| **URA** | −10 | `POS_URA_20260526_170738` qty **10** @ 50.67 | ✅ **fully** |
| **SOXS** | −15 | `POS_SOXS_20260526_170617` qty **250** @ 5.8801 | ✅ **fully** (covers 15) |
| **XLE** | −20.071 | `POS_XLE_20260526_170826` qty **20** @ 58.945 | ⚠️ **20 of 20.071** — 0.071 remains UNKNOWN |
| **SMST** | −20 | `POS_SMST_20260526_181424` qty **10** @ 31.08 | ⚠️ **10 of 20** — half remains UNKNOWN |
| **GDXY** | −0.891 | none (GDXY entered 06-10, after the window opens) | ❌ **not closed** |

**The brief's conclusion holds, with a material softening.** Extending the window did
reveal more zero-basis cases, and no window short of full account history eliminates them —
the residual XLE 0.071 and GDXY 0.891 fractionals are exactly the permanent class. But the
DB history **does** supply basis for URA and SOXS outright and for 20 of XLE's 20.071, so
condition 1's UNKNOWN convention would apply to **fewer trades than the export alone
implies**. Worth restating before PR-106 sizes its exclusion count.

Note the caveat: these are **DB-derived** bases from a principal-maintained record that is
itself pending the overlap validation. If Task 2 later fails, these closures fail with it.

---

## Bearing on the R-IV.86-a flags

**Flag 2 — supported, and strengthened by a second failure mode.** The extended history is
genuinely uncertain, and PR-106 firing on "reconstruction landed" rather than "validation
passed" risks burning its single run. I would add: **even if the overlap test passes, the
series is 3.2 months, not 8.** The Jan–Feb sample-growth simply is not there. Conditioning
(d) on the validation *result* is right, and the result should be read against a 03-11
floor.

**Flag 2's split-contamination premise — needs correction before it reaches spine.** As
measured above, this is not a 10x units problem and not a date-range population split. It
is three discrete 1.5–1.8× same-day breaks plus ordinary decay, with exactly one adjusted
row. It remains a real anomaly and a real threat to *precision*, but it is not the
category of threat stated, and the overlap test is its remedy rather than its casualty.

**Flag 3 — I am blocked on this ruling and concur with the amendment.** Excluding the 7
unsettled fills would strand the 08-24 SOXS final exit and the RAMZ/GDXJ closes, producing
phantom open positions in the very ledger the study consumes. Settlement is cash timing,
not trade existence. **I will not execute Phase 1a under condition 6 as ratified** — the
`unsettled=true` flag plus post-settlement re-verification is the correct form, and the
segmenter already emits the column.

---

## Manifest (law v2)

| Scope | Rows | Note / fingerprint |
|---|---|---|
| Fidelity historical ledger, 2026-01-01 → 06-30 | **46** | 23 tickers · 03-11 → 06-18 · 42 priced · 4 open |
| Fidelity rows touching overlap 05-27 → 06-18 | **22** | test set, unusable until artifacts arrive |
| Fidelity SOXS rows examined | **9** | 8 closed, all reproduce `realized_pnl` at ≤$0.005 |
| Same-day price pairs tested | **5** | 2 consistent (1.00×, 1.04×) · 3 discontinuous (1.49–1.80×) |
| DB positions open at 2026-05-27 | **4** | SMST 10 · SOXS 250 · URA 10 · XLE 20 |
| 90-day export | **ABSENT** | Task 2 blocked |
| `fidelity_ACCT-ROTH_trades.csv` (segmenter output) | **ABSENT** | not in tree; Phase 1a still blocked |

**No writes, no migrations, no schema changes. Nothing staged.**
