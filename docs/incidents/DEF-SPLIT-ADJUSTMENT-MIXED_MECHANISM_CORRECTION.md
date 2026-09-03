# DEF-SPLIT-ADJUSTMENT-MIXED — MECHANISM CORRECTION

**To:** spine · POSITIONS · cc EDGE **From:** CC-POSITIONS
**Re:** R-IV.88(c) · **READ-ONLY, no writes**
**Tree SHA `8b2d767`** (own fetch 2026-08-25 07:20 UTC, `ls-remote` confirmed, 0/0) ·
stamped 2026-08-25 07:20 UTC (01:20 MDT)

**Not disputing that a defect exists.** A real, measurable price-integrity break is present
and P2 is defensible. Disputing the **stated mechanism**, which is falsified by direct
measurement, and the **name**, which will misdirect the fix.

R-IV.88(e) adopts the disclosure-audit practice: *a lane asserting what another lane has
seen verifies against that lane's own context, not against the sender's assumption.* This
filing is that practice applied to a data claim — verified against `unified_positions`
itself, not against the summary table the claim travelled in.

---

## 1. Two hard factual errors in the registration text

The registration reads:

> *"SOXS entries 38.852 03-18 · 14.33 04-07 · 8.25 05-13 · 5.41 06-09, ~6x apart across a
> 1-for-10 boundary"*

### Error A — `14.33` is not the 04-07 row. It is the 04-28 row.

Queried directly:

```
 entry_d     position_id                 entry_px   qty   exit_d      exit_px
 2026-03-18  POS_SOXS_20260318_051305     38.8520    25   2026-03-20  38.8000
 2026-04-07  POS_SOXS_20260407_165228     35.1800    15   2026-04-10  27.6600   <-- 35.18, not 14.33
 2026-04-28  POS_SOXS_20260428_065253     14.3300    35   2026-05-13  14.8400   <-- 14.33 lives here
 2026-05-13  POS_SOXS_20260513_183950      8.2500   100   2026-05-26   8.9200
 2026-06-09  POS_SOXS_20260609_230655      5.4100   150   2026-06-10   6.1100
```

`POS_SOXS_20260407_165228` carries **35.18**. The source brief's table labelled that
`position_id` "14.33 — ambiguous"; the "ambiguity" was read off a price the row does not
hold. Correcting the pairing removes it: 38.852 → 35.41 → 35.18 is a smooth series, not an
ambiguous one.

### Error B — there is no 1-for-10 boundary between these rows. They are all on one side.

```
 Fidelity SOXS rows with entry_date > 2026-07-14 (the split boundary): 0
```

The boundary is **2026-07-14 → 2026-07-15**. All four cited entries are March–June. **Zero
Fidelity SOXS rows exist after the boundary at all.** Nothing here is "across" it, so a
1-for-10 ratio cannot be the mechanism producing spread between them.

---

## 2. What the measurement actually shows

Established in [`FIDELITY_HISTORICAL_EXTRACTION.md`](FIDELITY_HISTORICAL_EXTRACTION.md)
(same tree SHA) and re-verified for this filing.

**Exactly one row is adjusted — not a date range.**

| rows | units | applied by |
|---|---|---|
| `POS_SOXS_20260610_154556` | ×10 adjusted (4.0395 → 40.395, qty 450 → 45) | `scripts/def_position_integrity.py` — hardcoded id, guard `entry_price < 20` |
| the other 8 Fidelity SOXS rows | raw as entered | nothing — no mechanism exists |

Phase 0 Q3.5 established there is no corporate-actions table, no adjustment column, and no
adjustment log anywhere in the schema. One script, one id, one run. "Split-adjusted and raw
in a date-range pattern" describes a population split of **1 vs 8**, not a date range.

**Every row is internally unit-consistent.** `realized_pnl` reproduces from
`(exit − entry) × qty` on all 8 closed rows, max delta **$0.005**. If two unit systems were
mixed *within* rows, this would not hold.

**Same-day price pairs — the decisive test.** A real quote cannot be two values on one
calendar date, so any gap is an artifact:

| date | prices | ratio | verdict |
|---|---|---|---|
| 2026-04-07 | exit 36.49 / entry 35.18 | **1.04** | ✅ consistent |
| 2026-05-13 | exit 14.84 / entry 8.25 | **1.80** | ⚠️ break |
| 2026-05-26 | exit 8.75 / entry 5.8801 | **1.49** | ⚠️ break |
| 2026-06-09 | exit 5.41 / entry 5.41 | **1.000** | ✅ exact to the cent |
| 2026-06-10 | exit 6.11 / entry 4.0395 (raw) | **1.51** | ⚠️ break |

**No gap is 10×. None is even 2×.** A 1-for-10 reverse split produces exactly 10×, and two
of the five pairs are clean — one matching to the cent.

**Decomposition of the "~6x".** Total 03-18 → 06-10 is 38.852 → 4.0395 raw = **9.62×**.
The three breaks compound to 1.80 × 1.49 × 1.51 = **4.05×**. Remainder **2.38×** is ordinary
decay for a −3× semiconductor ETF over three months — which is *why* the reverse split
happened in July.

So: **~4.05× is a genuine unexplained defect. ~2.38× is not a defect at all.**

---

## 3. Why the name matters — the misdirected-fix risk

This is the operational reason to correct rather than let it ride.

A remediation brief written against **DEF-SPLIT-ADJUSTMENT-MIXED** will look for a 10×
factor, a split boundary, and two unit populations. It will find:

- no 10× anywhere,
- no boundary between the affected rows,
- one adjusted row that is already correct,
- eight raw rows that are each internally consistent.

The honest conclusion from that search is **"no defect found — close it."** The real ~4.05×
break survives, now with a closed ticket over it. Spine's own note that *"every future
realized study inherits it"* is exactly right, and is precisely what makes a false close
expensive.

---

## 4. "Registration costs nothing extra" — the premise is currently false

R-IV.88(c) rests on: *"the overlap-validation brief already tests it, so registration costs
nothing extra."*

**The overlap validation cannot currently be run.** Three independent blockers, filed in
full in the extraction report:

1. The **90-day export does not exist** — searched repo, Downloads, Desktop, Documents.
   `data/imports/` holds only the 60-day file.
2. The **normalizer was not updated** for the multi-account form. It hard-depends on
   `Cash Balance ($)` at line 66 and has no `Account Number` handling — it raises
   `KeyError`, it does not adapt.
3. Decisively: the 60-day export spans **06-25 → 08-24**; the overlap window is
   **05-27 → 06-18**. They do not intersect — the export begins seven days *after* the
   window closes.

So the test that would confirm-or-refute this defect is blocked on artifacts that have not
arrived. The registration is not free-riding on a scheduled test; it is riding on a blocked
one. That does not argue against registering — it argues for registering the **measured**
mechanism, which needs no artifact because it is already measured.

---

## 5. Recommended re-registration

| field | current | recommended |
|---|---|---|
| **name** | `DEF-SPLIT-ADJUSTMENT-MIXED` | `DEF-SOXS-PRICE-DISCONTINUITY` (or any name not asserting split adjustment) |
| **mechanism** | split-adjusted + raw in a date-range pattern, ~6× across a 1-for-10 boundary | **three discrete same-day price breaks of 1.49× / 1.51× / 1.80×**, compounding to ~4.05×; cause **UNKNOWN** |
| **scope** | date range | three dated boundaries: **2026-05-13 · 2026-05-26 · 2026-06-10** |
| **adjusted rows** | "part of the table" | exactly **one** — `POS_SOXS_20260610_154556`, already correct |
| **severity** | P2 | **P2 sustained** — 4.05× of cumulative price error is material to any realized study |
| **falsified** | — | 10× ratio · date-range population · boundary-crossing · the 04-07/14.33 pairing |

**Cause is UNKNOWN and I am not proposing one.** Candidates not separable from DB state:
data entry from mixed sources, lot-averaging on partial closes, or a genuine unrecorded
corporate action at a non-10:1 ratio. The broker export over 05-13 → 06-10 would separate
them — which is a *narrower and different* artifact request than the 05-27 → 06-18 overlap
window, and would resolve this defect independently of PR-106.

---

## 6. Acknowledged from R-IV.88(d)

- **Flag 3 ruled — unsettled INCLUDED, flagged, re-verified post-settlement.** This clears
  my stated refusal to execute Phase 1a under condition 6 as previously ratified. No
  remaining objection on that condition.
- **PR-106 trigger conditioned on validation RESULT, both branches pre-fixed.** Noted. Flagging
  only that **neither branch can currently evaluate**: the PASSES branch needs the overlap
  test (blocked, §4), and the FAILS branch needs the 90-day sample (absent). The trigger is
  well-formed; its inputs have not arrived.
- **Phase 1a remains blocked** independently on the segmenter script and
  `fidelity_ACCT-ROTH_trades.csv`, neither of which is in the tree at `8b2d767`.

**No writes, no migrations, nothing staged.**
