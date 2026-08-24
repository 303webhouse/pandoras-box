# ARTIFACT — OBE-EXPIRY-RECON  (HELD, files post-freeze)

lane CHAT 4 · task OBE-EXPIRY-RECON · governing SHA 2de26c6 · sid c4-obe-recon-20260820
Charter R-IV.31(b). DB-only. **WRITES EXECUTED: ZERO.** No push, no deploy, no repo file touched.
DB clock at census: 2026-08-20 20:54:00 UTC (14:54 MDT) — post-close, pre-expiry.

## 1. CENSUS (read-only, ::text casts, verbatim)

Predicate: `unified_positions WHERE status = 'OPEN' AND expiry <= DATE '2026-08-21'`

**COUNT = 0. Zero rows returned.**

Corroborating counts, same transaction:
- OPEN total (all expiries): 27
- OPEN with NULL expiry: 4  — all `asset_type = EQUITY` (GUSH 298, SOXS 311, GDXJ 341, XLE 342).
  Equities carry no expiry; none is at expired-worthless stamp risk. No OPEN OPTION has NULL expiry.
- status case-variants of 'OPEN': 0. Distinct status domain: CLOSED | EXPIRED | OPEN.
- All rows with `expiry = 2026-08-21`, any status: 4 rows / 6 contracts, tickers AMC, OBE, XLE —
  **all four CLOSED.** Nothing OPEN expires 08-21.

## 2. PRE-CONFIRMED ROW — OBE 12.5C 08/21 — STATE AT CENSUS

Charter premise: "broker: 3 contracts sold 08-11, $61.00 proceeds · DB: OPEN qty 1".
Premise is **STALE**. No OPEN OBE row exists. Two CLOSED rows carry the full 3-lot:

| id | position_id | qty | status | exit_price | exit_date | realized_pnl | outcome | updated_at (UTC) |
|----|-------------|-----|--------|-----------|-----------|--------------|---------|------------------|
| 349 | POS_OBE_20260713_231900 | 2 | CLOSED | 0.10 | 2026-08-11 | -8.10 | LOSS | 2026-08-18 00:56:21.650644+00 |
| 372 | POS_OBE_20260723_120009 | 1 | CLOSED | 0.41 | 2026-07-23 | 26.94 | WIN  | 2026-08-17 20:26:11.959496+00 |

Both: ticker OBE, long_call LONG, long_strike 12.5, expiry 2026-08-21, account ROBINHOOD, source MANUAL.
id 349 notes: "Partial close 1/3 @ 0.41 (WIN $+27.00)"
id 372 notes: "partial close of POS_OBE_20260713_231900 (1 of 2)"

## 3. BROKER TIE-OUT  (computed in-DB, not by hand)

| measure | DB | broker | variance |
|---|---|---|---|
| contracts | 3 | 3 | 0 |
| gross proceeds | $61.00 | $61.00 | **$0.00** |

Breakdown: `CLOSED:1@0.41 on 2026-07-23 | CLOSED:2@0.10 on 2026-08-11`
(1 x 0.41 x 100 = $41.00) + (2 x 0.10 x 100 = $20.00) = **$61.00**
Cost basis $42.00 · gross P&L $19.00 · net realized $18.84 · residual $0.16 = fees/commission.

**Contract count and proceeds tie to the penny. No correction warranted.**

Date attribution: broker summary lumps all 3 on 08-11; DB splits 1 on 07-23 + 2 on 08-11. Expected
per the known hub-vs-broker date offset — identity match is ticker+expiry+strike, not activity_date.
DB split is the more granular record. Not a defect.

## 4. QUANTITY DISCREPANCY — RESOLVED, NOT REAL

"broker 3 vs DB qty 1" resolves as a **partial-close parent/child pair read in isolation**:
qty 1 (id 372) is the child of the 1-of-2 partial close; qty 2 (id 349) is the remainder. 1 + 2 = 3.
Reading either row alone yields a false shortfall. No quantity drift on OBE.

## 5. WHEN THE PHANTOM WAS ACTUALLY CLEARED

id 349 `updated_at` = 2026-08-18 00:56:21 UTC = **2026-08-17 18:56 MDT**, which matches the mtime of
`backend/database/archive/2026-08-17-rh-book-reconciliation-v3-preimage.jsonl` (Aug 17 18:56) to the
minute. The OBE close landed in the 08-17 RH book reconciliation v3 pass, ~2 days before this spawn.
id 372 was created CLOSED at 2026-08-17 20:26:11 UTC and never updated since — it was never OPEN.

## 6. DETERMINATION

Charter step 3 (preimage -> UPDATE -> postimage) has **zero qualifying rows**. Correct execution is
no write. Nothing was written. Preimage == postimage == the census above, unmutated.

## 7. EVIDENCE -> DEF-NO-BROKER-SYNC (Exhibit A)

Exhibit A is now a **negative** control, and stronger for it: the 08-17 true-up DID carry OBE to
broker truth and tie it to the penny. What failed was not the sync — it was that no instrument
re-read the DB before a correction was chartered against a ~2-day-old observation. The defect class
is unchanged (no standing broker<->DB reconciliation), but OBE is evidence of the true-up working.

**08-17 true-up coverage hole, one line:** the hole is not existence/quantity on reconciled tickers —
it is that a reconciled row carries no proof-of-reconciliation marker, so a later reader cannot
distinguish "verified against broker" from "never checked," which is what re-opened OBE as a phantom.

**Adjacent drift found in census, outside this charter, NOT actioned:** id 311 SOXS notes read
"remaining 125 sh @ 4.57" while `quantity` = 45. Notes-vs-column contradiction on an OPEN equity
position. Unverified against broker. Flagged only.

**Liveness datapoint:** all 4 OPEN NULL-expiry rows show `updated_at` 2026-08-20 20:47 UTC, ~7 min
before census — unified_positions writes are alive today, whatever DEF-SIGNAL-PERSISTENCE-COLLAPSE
is doing to the signals table.

## 8. VERIFICATION TAIL — EXECUTABLE (R-IV.36(h), 08-21 evening, SELECT-ONLY)

No corrected row exists, so the equivalent-value check is: **can a CLOSED row be clobbered by an
auto-expiry stamp?** All 4 rows expiring 2026-08-21 are CLOSED. If any flips to EXPIRED, or its
realized_pnl / exit / quantity moves, that is a fresh P0-class defect (CLOSED-row clobber) — it
would silently destroy a penny-exact reconciliation. File immediately.

Baseline captured 2026-08-20 ~21:0xZ, pre-expiry. Run this verbatim and compare fingerprints:

```sql
SELECT id::text, ticker::text, status::text, realized_pnl::text, trade_outcome::text,
       exit_price::text, exit_date::text, quantity::text, updated_at::text,
       md5(ROW(status, realized_pnl, trade_outcome, exit_price, exit_date, quantity)::text)
         AS fingerprint
FROM unified_positions
WHERE expiry = DATE '2026-08-21'
ORDER BY id;
```

EXPECTED — 4 rows, all `status = CLOSED`, fingerprints unchanged:

| id | ticker | status | realized_pnl | outcome | qty | fingerprint (md5) |
|----|--------|--------|--------------|---------|-----|-------------------|
| 347 | XLE | CLOSED | 53.90  | WIN  | 1 | `efc5197604a8b181d2a7bf83ae974d9b` |
| 349 | OBE | CLOSED | -8.10  | LOSS | 2 | `06eae9e27d5bb6e452cda8b6bf0f543b` |
| 357 | AMC | CLOSED | -16.36 | LOSS | 2 | `8941df987c8a50511ca44a3eb92dcf45` |
| 372 | OBE | CLOSED | 26.94  | WIN  | 1 | `e8e44677d4fe861f605ce49cc2cb8f6b` |

Baseline `updated_at`: 347 / 357 / 372 = `2026-08-17 20:26:11.959496+00`;
349 = `2026-08-18 00:56:21.650644+00`. A moved `updated_at` with an unchanged fingerprint is a
touch-without-semantic-change — note it, do not file it as a clobber.

PASS  = 4 rows, 4 fingerprints match -> CLOSED rows are immune to the stamp. Tail closes, dormancy.
FAIL  = any fingerprint differs or any status <> CLOSED -> CLOSED-row clobber, file immediately,
        preimage is this table.

## 9. FLAG ADDENDUM (adjacent, not actioned, same class as id 311 SOXS)

id 347 `POS_XLE_20260707_06000002`: `cost_basis = 0` on a CLOSED call_spread carrying
`realized_pnl = 53.90`. A zero cost basis makes the P&L unreconstructable and would distort any
cost-basis aggregate. Not verified against broker; flagged only, routes with the SOXS check.

## 10. TAIL RESULT — R-IV.53(h) — **PASS-VACUOUS**, and a defect found in the inverse direction

**VINTAGE:** ordered for 08-21 evening; executed **2026-08-24 16:14Z**, 3 days late (relay reached
CHAT 4 on 08-24). This is an 08-24 read against an 08-20 baseline. It still detects a clobber; it
cannot date one.

### 10.1 Literal result — 4/4 fingerprints match

| id | ticker | status | fingerprint | vs baseline |
|----|--------|--------|-------------|-------------|
| 347 | XLE | CLOSED | `efc5197604a8b181d2a7bf83ae974d9b` | MATCH |
| 349 | OBE | CLOSED | `06eae9e27d5bb6e452cda8b6bf0f543b` | MATCH |
| 357 | AMC | CLOSED | `8941df987c8a50511ca44a3eb92dcf45` | MATCH |
| 372 | OBE | CLOSED | `e8e44677d4fe861f605ce49cc2cb8f6b` | MATCH |

`updated_at` also unchanged on all four — not even a touch-without-semantic-change. No clobber.

### 10.2 Why that is NOT a PASS (null-verifier law applied to this check)

The check asks "are CLOSED rows immune to the auto-expiry stamp?" It would return this exact result
if the stamper were **dead**. Both are true here:

1. `open_past_expiry_now = 0` — zero OPEN rows past expiry. A healthy stamper had no work to do.
2. **The stamper has not fired since 2026-07-19.** (below)

Absence of the actor, not immunity of the row. **Recorded as PASS-VACUOUS.** A real controlled
comparison needs the stamper observed firing and skipping a CLOSED row; that evidence does not exist.

### 10.3 THE ACTUAL FINDING — auto-expiry stamper dark since 2026-07-19

Two writer signatures partition the 26 EXPIRED rows with **zero overlap**:

| signature | n | expiry range | write window |
|---|---|---|---|
| AUTO-STAMPER (status only; exit_date/realized_pnl/trade_outcome all NULL) | 24 | 2026-04-10 → **2026-07-17** | 2026-05-09 → **2026-07-19 06:40:09Z** |
| MANUAL 08-17 batch (exit + P&L backfilled) | 2 | 2026-07-31, 2026-08-03 | 2026-08-17 20:26:11.959496Z (identical) |

Batch-job proof: many distinct rows share byte-identical `updated_at` (ids 331+170 both
`2026-07-19 06:40:09.559799+00`), and pre-07-17 writes cluster just after 00:00Z on expiry+1
(`06-19 00:03:21`, `06-25 00:00:51`, `07-03 00:00:00.545`). That cadence is an automated job.

**It last fired 2026-07-19 — 36 days ago.** The 07-31 and 08-03 expiries received **no** auto-stamp;
both were resolved 17 and 14 days later by the manual RH batch, carrying the manual signature.

*Stated as inference, not fact:* that those two sat OPEN-past-expiry in the interim is strongly
implied by their final shape but unprovable here — `unified_positions` has no history table.

### 10.4 LIVE EXPOSURE — 4 days out

- **22 OPEN options carry an expiry.**
- **Next expiry: 2026-08-28 — 4 days from this read.**
- If the stamper is still dark on 08-28, that position stays silently OPEN past expiry: the exact
  phantom class that opened this thread. No manual reconciliation is scheduled to catch it.

### 10.5 Attribution caution for T8

This darkness began **~2026-07-19**, a month BEFORE the 08-18 cluster
(DEF-SIGNAL-PERSISTENCE-COLLAPSE, DEF-UW-CLIENT-DEATH tide+flow dark 08-18). Absence-not-error
class, same family — but **do not fold it into the 08-18 root cause.** Different date, likely
different cause. Folding it in would corrupt the T8 controlled comparison.
