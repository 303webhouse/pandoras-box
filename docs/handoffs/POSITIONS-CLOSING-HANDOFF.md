> **GATE NOTE (CC-BUILD, R-IV.237(c)).** Filed at the **measured-of-record** gate
> `50ba9b0f` / 7,021 B, re-hashed at apply time. The **authored** gate
> `d905a30d` / 7,039 B **disagrees by −18 B** — character-level, structure
> complete, no section missing. **Unresolved**; most likely an editor whitespace-trim at
> save. Recorded rather than reconciled, because an 18-byte disagreement with intact
> structure is a provenance question, not a content one, and guessing which copy is
> canonical would settle it without evidence.
> 
> This note is CC-BUILD's addition, so the filed bytes are the measured 7,021 plus this
> block; the gate above describes the payload as received, not this file.

# POSITIONS — CLOSING HANDOFF
## Per R-IV.230 consolidation. Holdings declared; no guidance issued.

This lane's picture may predate recent rulings. Every item carries the date of the
last information it rests on. Nothing below is a recommendation.

---

## 1. OPEN — NOT DELIVERED OR UNACKNOWLEDGED

### 1.1 WRTH close basis conflict · rests on 2026-08-28
R-IV.125(d) states basis 20 sh @ 25.87. The 90-day normalized fills carry WRTH as
3 fills, net +20 sh, net cash −$510.93 = $25.55/sh. Divergence $6.47, which equals
WRTH's already-booked closed round-trip exactly (trade_reconciliation.json,
per_ticker_realized WRTH: 6.47). The order's realized ≈ −$0.60 DOES derive from
artifacts; the 25.87 basis does not.
Relay authored this turn. **Delivery to spine unconfirmed.**

### 1.2 B0 suppressed population is at least 12, not 7 · rests on 2026-08-28
CC-QUERY recovered 7 multi-exit units from fill resolution. POSITIONS adds 5 DB-half
rows from the notes sidecar that narrate partial closes and reproduce coherently:
GDX +39.75 · GUSH −107.17 · SMST +46.70 · XLE +73.15 · SOXS −117.52. Second instance
of the id-375 pattern (lifecycle in prose, invisible to column queries).
Relay authored this turn. **Delivery to spine unconfirmed.**

### 1.3 Tranche-window standing-figure restatement · rests on 2026-08-27
POSITIONS requested that after each QQQM tranche fills, the principal state the Roth
account value from the app and the standing figure restate — same procedure as the RH
normalized read. Raised against R-IV.115(c)'s principal-manual execution with DB
catch-up. **No acknowledgement received.**

### 1.4 RH cash write (−$250 ACH) · rests on 2026-08-26
POSITIONS relayed the write to CC-POSITIONS gated on three absence checks
(cash_flows row for 08-24 · balances-row notes · whether $1,070.00 reconciles pre- or
post-ACH). **No execution report received by this lane.** Status unknown here.

---

## 2. OPEN — DELIVERED, DEFERRED BY RULING

### 2.1 merge_halves.py PRE-WINDOW sentinel · rests on 2026-08-27
Script stamps literal "PRE-WINDOW" into entry_date and exit_date on any export trade
consuming a pre-window seed. Two effects: type violation (max/sort/range over
exit_date returns a string), and destroyed matchability driving spurious
OVERLAP-UNMATCHED on seeded tickers. Fix logged, deferred past the current merge by
POSITIONS' own proposal, accepted at R-IV.110 receipts. **Not executed.**

### 2.2 segment_trades.py exit-count omission · rests on 2026-08-28
Script emits `fills` as a total and never splits buys from sells, so exit count is
invisible in the merged ledger and B0 had no trigger to fire on. Fix is two lines
(emit `entries` and `exits`), both already computable in the loop. POSITIONS proposed
bundling with 2.1 at the next merge. **Not executed. Bundling not ruled on.**

### 2.3 Frozen-ticket evidence held · rests on 2026-08-28
Registered, not worked, per R-IV.114: TGT preimage as canonical bounded-structure
fixture (current_price −0.53 on a debit spread; unrealized_pnl −146.18 against a
$40.18 max loss, marked same-day 13:17:10Z). Second fresh-but-wrong instance beside
the XLF 30-put (DB 0.10 / +6.96 vs broker 0.01 / −65.04).

### 2.4 Dimension-B quantity conflicts · rests on 2026-08-27
Two rows where a column contradicts a note or a counterpart, filed together:
SOXS POS_SOXS_20260610_154556 (note claims 125 remaining, column carries 45) and
GDXJ 2026-06-18 (db_qty 5 vs export_qty 8). Neither gates anything this lane holds.

---

## 3. ARTIFACTS THIS LANE HOLDS

### 3.1 Offered, not claimed — URSA duration audit · rests on 2026-08-28
RH activity report (`data/imports/3b84f64e-64dc-5c92-bcaa-3b4a75d1f072.csv`,
71 rows, 8/17→8/25) carries per-leg expiries; merged ledger carries the Fidelity
side. Baseline for Sunday's Brief is **6 of 19** (was 7 of 21 before the TGT stamp).

### 3.2 Scripts authored by this lane, on disk
- `scripts/normalize_fidelity_history.py` — handles both Fidelity export forms
- `scripts/segment_trades.py` — flat-to-flat segmentation, derivation of record
- `scripts/merge_halves.py` — R-IV.94(a) dedup, tiers, exclusion enumeration
Each is the derivation of record for its output. Both known defects are in 2.1/2.2.

### 3.3 Standing figure as this lane last held it · rests on 2026-08-25
≈$12,217 = RH ≈$835 (app, 08-25 11:30 MT) + Roth $11,382.17 (app, 08-25 00:59 ET).
**Both components predate the WRTH sale (08-28) and any QQQM tranche.**

---

## 4. STANDING RULES THIS LANE ENFORCED

Listed as holdings, not as instruction. Several were adopted board-wide.

- **Realized-from-exit is the only verified-clean P&L path.** All other P&L fields
  inadmissible until their tickets clear. (Q4 audit, 2026-08-25)
- **No mechanism OR provenance without an artifact.** Lane case law after nine
  self-corrections; symptom is a read, mechanism is a claim, and so is a pin.
- **A disclosure warning describes the shape of a disclosure, never reproduces its
  content.** Proposed by this lane and broken twice by it; the mechanical
  digit-scan instrument replaced the rule at R-IV.96(b).
- **Null-verifier test:** "what would a failure have looked like? No answer = the
  check proved nothing." Adopted board-wide; this lane contributed one instance
  (fractional-quantity test against an integer column).
- **Zero-basis bar:** a disposal with no in-window acquisition renders cost_basis
  NULL/UNKNOWN, never 0; realized N/A.
- **Marks NULLed on close, never zeroed.**
- **Operator caveat, enforced not authored:** broker app governs every RH figure.

---

## 5. PENDING EXPECTATIONS

- **PR-106 part 2** gated on R-IV.113-b, which is on disk and is CC-POSITIONS'
  critical path. POSITIONS has **not read** that brief and owes nothing on it unless
  it assigns this lane something. (rests on 2026-08-28)
- **Next merge** should carry the 2.1 and 2.2 fixes if the bundling is ruled.
  (rests on 2026-08-28)
- **Sunday Battlefield Brief** duration audit baseline 6 of 19. (rests on 2026-08-28)

---

## 6. LOGGED IN-LANE, NEVER RELAYED

- **SBU carried as "pending R-IV.94(g)"** in the closing map. Resolution was
  discharged 2026-08-25 (Leverage Shares 2X Long SBUX, classified consumer
  discretionary/restaurants, rejected alternatives on record, ETF-only invariant
  closed on it). Label-only; moves no count, changes no cell. Withheld under
  R-IV.99's standing rule. (rests on 2026-08-27)
- **merged_ledger.csv residual arithmetic:** OTHER's section total read 89 in one
  amendment pass while OBE had just been added to it; resolved mechanically by the
  set difference without adjudication. Noted so a 2-vs-3 residual is not later read
  as a new gap. (rests on 2026-08-27)

---

## 7. NOT HELD

Merge, notes gate, sector map, TGT stamp, XLF quantity, FCX intent, notes sidecar
filing, OVERLAP-UNMATCHED census, RH activity report load, and the cash-events
discharge are all **closed and delivered**. This lane holds no open question on any
of them.

---

END OF HANDOFF.
