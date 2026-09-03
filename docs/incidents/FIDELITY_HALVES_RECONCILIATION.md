# HALVES RECONCILIATION — DB + EXPORT under R-IV.93(c)

**R-IV.93(h) step 2.** READ-ONLY. No DB writes, no migrations.

| provenance | value |
|---|---|
| **Tree SHA** | **`8b2d767`** — own fetch 2026-08-25 07:38 UTC, `ls-remote` confirmed, 0/0 |
| **DB read** | 2026-08-25 07:35 UTC, read-only MCP |
| **Export artifact** | `data/imports/90d/` — 159 fills → 43 trades |
| **Stamped** | 2026-08-25 07:38 UTC (01:38 MDT) |

---

## 1. The halves overlap — union, not sum

Stated first because it is the arithmetic that governs the count:

```
 DB record      2026-03-11 ──────────────── 06-18
 Export                        05-27 ──────────────────── 08-24
 overlap                       05-27 ── 06-18
```

Class-B DB rows (05-28 → 06-18) are the **same trades** the export carries. Adding 46 DB
rows to 43 export trades double-counts the overlap. The union is **class A + export**.

## 2. Class A composition (03-11 → 05-26, 28 rows, all priced)

| disposition | tickers | rows |
|---|---|---|
| **admitted** | BITI 1 · BTCZ 1 · GDX 2 · MOO 2 · QQQI 1 · SBU 1 · SOXL 1 · SQQQ 3 · SRTY 1 · TLT 1 · TSLQ 2 · URA 1 | **17** |
| **LIFECYCLE-UNVALIDATED** | GDXJ 1 · SMST 1 · **SOXS 7** · XLE 2 | **11** |
| | | **28** |

Note GUSH contributes **0** class-A rows — its only pre-05-27 entry is 05-28, which is
class B. So the Dimension-B exclusion touches 4 of the 5 named tickers in the DB half; the
GUSH exclusion applies to the export half only, where (c) rules those units
broker-validated and unaffected.

**SOXS carries 7 of the 11 excluded rows** — the concentration ticker is also the bulk of
the lifecycle exclusion, which is precisely why (c)'s both-ways rendering matters.

## 3. Trade-level unit count — lands inside the pre-render expectation

```
 Class A admitted ......................... 17
 Class A LIFECYCLE-UNVALIDATED ............ 11   (excluded from units; rendered both ways)
 Export priced closed ..................... 36   (43 trades − 2 open − 5 unknown-basis)
 ---------------------------------------------
 WITH exclusions applied .................. 53
 BOTH-WAYS upper (incl. the 11) ........... 64
```

**53 falls inside R-IV.93(c)'s stated ~50–60 band.** The both-ways upper bound is 64.
Recording both now, pre-render, so neither figure reads as a segmentation failure later.

Tier composition per (d), for the cell lines:

| tier | units | source |
|---|---|---|
| **BROKER-VALIDATED** | 36 | export half, 05-27 → 08-24 |
| **PRINCIPAL-ATTESTED** | 17 | class A admitted, 03-11 → 05-26 |
| **PRINCIPAL-ATTESTED, excluded** | 11 | class A LIFECYCLE-UNVALIDATED |

Plus the four 05-26-entry / overlap-exit rows (SMST · URA · XLE · SOXS) noted in (d) as
partially corroborated on the exit leg — they sit inside the 11 and are not separately
counted.

**Flag for the sector map:** `SBU` is in the *admitted* 17. It remains the one ticker
unconfirmable as an ETF (absent from `stable_universe`, single row 2026-04-29). It now
enters the sample rather than sitting outside every window, so it needs a tier/classification
decision it did not previously need.

---

## 4. ⚠️ (f) — the "6.57× high" figure conflates a legitimate adjustment with the anomaly

Not disputing that the 06-10 break is real — I measured and registered it. Disputing the
**magnitude**, because a wrong magnitude authorizes a wrong fix, which is the law adopted
in R-IV.90(a).

`6.57×` = 40.395 ÷ ~6.15. That compares the DB's **split-adjusted** value against the
external **raw** value. The ×10 between them is legitimate and deliberate:

- id 311 opened **2026-06-10, pre-split**, at raw 4.0395 × 450 sh.
- The position is **still open** (`exit_date` NULL), so it survived the 07-14/15 1-for-10.
- `def_position_integrity.py` converted it to post-split units — 40.395 × 45 sh — which is
  correct accounting for a position held across a reverse split, and is what makes the
  live mark coherent: (50.75 − 40.395) × 45 = +465.98.

Like-for-like:

| comparison | DB | external | ratio |
|---|---|---|---|
| raw vs raw | 4.0395 | ~6.15 | **1.52×** |
| adjusted vs adjusted | 40.395 | ~61.5 | **1.52×** |
| **as stated in (f)** | 40.395 *(adjusted)* | ~6.15 *(raw)* | 6.57× |

**The discrepancy is ~1.52×** — which matches my independently measured 06-10 break of
**1.51×** and the registered DEF-SOXS-PRICE-DISCONTINUITY. The 6.57 figure embeds the
factor of 10 that is supposed to be there.

**Why it matters:** a remediation targeting 6.57× would remove the ×10 — the single
adjustment in the table that is *correct*. Stripping it would leave a post-split-surviving
position expressed in pre-split units and would break the live mark. This is the same
category error as the vacated DEF-SPLIT-ADJUSTMENT-MIXED, recurring inside its own
substantiation; flagging the pattern, not just the instance.

### The "4.57" note is stale, and cites a different quantity

id 311's note, verbatim:

> `Fidelity confirm reconcile 2026-06-18 (FIFO): qty 150->125 after 6/11-6/16 churn;`
> `remaining 125 sh @ 4.57 (6/16 lot).`

Two problems with using it as corroboration:

1. **It predates the correction.** Dated 06-18; `def_position_integrity.py` ran afterward.
   Its mutation list is `["quantity","entry_price","stop_loss","target_1","target_2","breakeven"]`
   — **`notes` is not in it** (script line 84, verified). So the note was never updated and
   describes the pre-correction state.
2. **It says 125 shares**, against the row's 45 (adjusted) / 450 (raw) and against the
   principal-confirmed 45 that anchors Phase 1a's SOXS exemption. Three quantity claims,
   none reconciling.

And on the number itself: 4.57 against an implied raw band of 6.00–6.32 is still **1.35×
apart** — closer than 4.0395, but not inside the band. It does not corroborate.

**Recommendation:** record the 06-10 break at **~1.52×**, drop the 4.57 note as stale
provenance, and treat the 125-vs-45 quantity conflict as a separate Dimension-B lifecycle
item on the row that anchors the SOXS exemption. Cause not proposed.

---

## 5. Standing

- (a) file-conflict resolution matches my read; the 90-day artifact is on disk and consumed.
- (b) MAR–JUN scope accepted as filed.
- (c) both-ways rendering: the 11 excluded rows are enumerated by ticker in §2, never
  silently dropped.
- (d) my entry-date split is operative and reproduced in §2–3.
- (f) SOXS re-run folded into the B1 fetch — CC-BUILD's; the §4 magnitude correction should
  travel with it. DEF-BARS-NO-PROVENANCE noted; bar-derived findings here state **PROVIDER
  UNDETERMINED**, and §4's external band is quoted from (f) rather than independently
  fetched.
- Phase 1a: no open blocker. Input is `data/imports/90d/` (43 trades).

## Manifest (law v2)

| Scope | Rows | Note |
|---|---|---|
| DB Fidelity, all | **46** | 03-11 → 06-18, 42 priced |
| Class A (attested interior) | **28** | 17 admitted · 11 LIFECYCLE-UNVALIDATED |
| Class B (broker-overlapped) | **18** | duplicates export trades — not summed |
| Export trades | **43** | 41 closed · 2 open · 5 unknown-basis → 36 priced |
| **Union, exclusions applied** | **53** | inside the ~50–60 band |
| **Union, both-ways upper** | **64** | |

**No DB writes. Nothing staged. All local artifacts gitignored.**
