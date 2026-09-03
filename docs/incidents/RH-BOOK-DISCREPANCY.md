# RH-BOOK-DISCREPANCY — discrimination surface

**R-IV.98(b). POSITIONS-owned; this is the read-only evidence base.**
**No mechanism asserted.** Both candidates are bounded and neither is excluded.

| provenance | value |
|---|---|
| **Tree SHA** | `8b2d767` |
| **DB read** | **2026-08-25 17:51:16Z** (11:51 MT) — clock adjudicated shell vs `now()`, agree |
| **Mark vintage at read** | mixed: **2026-07-24 13:17Z** (oldest) → **2026-08-25 17:47:12Z** (newest) |
| **Balances vintage** | `2026-08-24 17:01:35Z`, age **1 day 00:49** |

**Per R-IV.98(c):** every figure below is stamped. Marks refreshed **three times** during
this session alone (08-25 13:17Z · 17:32Z · 17:47Z). Do not compare these numbers against a
finding taken at another hour without restating both read times.

---

## 1. The four quantities

```
 app total (principal, 17:30Z) ................  ≈835.00
 DB balance      (vintage 08-24 17:01Z) .......   835.69   <-- AGREES with app
 DB cash         (vintage 08-24 17:01Z) .......  1070.00
 DB position value (mixed, →17:47Z) ...........   478.50
 ------------------------------------------------------
 DB-implied account value  (cash + positions) .  1548.50
 GAP vs app ...................................   713.50
```

**The inconsistency is internal to the DB, and `balance` is the column that matches
reality.** The hand-typed screenshot figure agrees with the broker app to $0.69. What fails
to reconcile is `cash + position value` — the two automated quantities.

That is worth stating plainly because it inverts the usual expectation: here the
least-automated column is the accurate one, and the machinery around it is what disagrees.

---

## 2. The discrimination surface

The identity `app_total = true_cash + true_position_value` admits a line of solutions.
Two endpoints bound it:

### Hypothesis A — marks correct, cash overstated

```
 true_cash = 835.00 − 478.50 = 356.50
 DB cash overstatement       = 713.50
   of which the $250 withdrawal explains ... 250.00  (35%)
   unexplained remainder ................... 463.50
```

Requires **$463.50 of additional unrecorded cash movement inside 24.8 hours**, beyond the
withdrawal. (1b) reports "several transactions unrecorded," and every option purchase
debits cash, so the class of event exists — but the magnitude is large for one day.

### Hypothesis B — cash correct after the withdrawal, marks overstated

```
 true_cash = 1070.00 − 250.00 = 820.00
 true_position_value = 835.00 − 820.00 = 15.00
 mark overstatement = 478.50 − 15.00 = 463.50   (96.9% of stated book value)
```

**This is the bound that constrains B, and it is the useful measurement:**

```
 value sitting in STALE marks (>24h) ....... 117.50
 value sitting in FRESH marks (≤24h) ....... 361.00
 ------------------------------------------------
 total ..................................... 478.50
```

**Zeroing every stale mark removes only $117.50.** Hypothesis B needs $463.50, so it
requires roughly **$346 of error in marks refreshed within the last 24 hours** — including
marks written at **17:47:12Z**, minutes before this read. Mark staleness alone cannot carry
B; B requires fresh marks to be substantively wrong.

### Evidence bearing on each — recorded, not weighed to a conclusion

**Supports mark overstatement (B):**
- **TGT is a confirmed instance.** (1e) reports the principal seeing a worthless spread
  render a small profit. DB carries `POS_TGT_20260817_130009` at **+$45.00**, mark vintage
  **08-18 16:32Z** (7 days stale), **3 DTE**. One overstatement of ~$45, sitting in the
  stale bucket.
- Six positions carry marks older than 24h; two carry none at all.

**Cuts against B:**
- **The two unmarked positions contribute $0** (`POS_TRIN_20260727_120003` 2× long_put,
  `POS_BX_20260724_182213` 2× long_put). If they hold any value, true position value is
  **higher** than 478.50, which widens the gap rather than closing it.
- 75% of book value sits in marks under 24h old.

**Supports cash overstatement (A):**
- `cash` is **24.8h stale** and pre-dates the withdrawal entirely.
- `cash` is auto-adjusted on position open/close (`_adjust_account_cash_with_conn`,
  `updated_by='auto'`), so any unrecorded trade leaves it drifted — the defect class is
  already established, only the magnitude is at issue.

**Concentration note:** `POS_USO_20260615_csv04` alone carries **$125.50 — 26% of total book
value** — on a fresh 17:47Z mark. Any single-position mark error there moves the whole
reconciliation materially.

---

## 3. What I am not doing

Not selecting between A and B. The surface above is symmetric in the sense that matters:
each endpoint requires an implausibly large error of its own kind, and the truth is likely a
point on the interior — partial cash drift *and* partial mark overstatement — which no
read-only evidence available to me can locate.

**What would discriminate, stated as a gap not a request:** a Robinhood activity export for
2026-08-24 → 08-25 would fix `true_cash` directly and collapse the line to a point. That is
the same instrument already logged in (e) as DEF-CASH-EVENTS-UNTRACKED's known remedy — one
artifact closes both.

**(b)'s operator consequence is unaffected and I concur:** Pandora's RH picture is wrong in
the flattering direction by up to $713, and the broker app governs for every RH figure until
this closes.

---

## 4. Acknowledged, no action

- **(a)** Surviving statement adopted verbatim; I claim no substitute mechanism for
  DEF-BALANCE-COLUMN-SEMANTICS.
- **(c)** Read-time stamping adopted as standing practice — applied throughout this file.
- **(d)** Frame accepted: AHRP being descoped makes 403(b)→ACCT-ROTH transfers new capital
  into the measured book, so the six recurring transfers are external to the *tracked* book
  even though internal to the Fidelity relationship. My two companion findings stand as
  cited — the 90-day export carries **zero** cash rows, and no Fidelity export can contain an
  RH withdrawal.
- **(e)** Coverage scoping matches my read exactly: 06-25→08-24 covered by the 60-day form
  only; 05-27→06-24 uncovered; Robinhood uncovered entirely.
- **(f)** Fix located at `portfolio_balances.py:118-120`; the `:126-129` asymmetry — funded
  filtering applied to `any_stale` but not to the figure, eight lines apart in the same
  function — matches my Phase 0b §1 read. Shape approved, build not authorized, not mine.
- **(h)** Return-figure caveat adopted. No return percentage against account value will
  appear in my output absent a cash-flow ledger.

**No DB writes. Nothing staged.**
