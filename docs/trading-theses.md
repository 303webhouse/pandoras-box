# Trading Theses — canonical thesis ledger
<!-- FINAL for the 2026-09-04 session (R-IV.251(d)). Standing rules section added
     R-IV.192(e)/201(c); D5 membership rewritten by id R-IV.207(b) and again R-IV.251(d);
     option-risk interim rule added R-IV.207(d); D4 hedge line DECLINED/rolled R-IV.209.
     All ferry items written. NO DATED ACTIONS OUTSTANDING — id 407 stamped R-IV.243,
     id 408 stamped R-IV.251(b), both 2026-09-04 post-close.
     Expiry completeness is now a QUERY, not this header (R-IV.251(c)): each session close,
     every row WHERE expiry <= today AND status='OPEN' is stamped. The hand-enumerated
     dated-action line is retired as the completeness instrument; id 408 is why.
     TA-044/TA-045 (2026-09-24): reachability exemption follows the TICKET, not the account —
     TAIL is exempt, CONVEXITY or a thesis must pass break-even within 1.5x the implied
     expected move. Bucket is set AT ENTRY and a retrospective change names its author.
     Applies to tickets opened on or after 2026-09-25; nothing existing is retagged.
     TA-042 (2026-09-24): D5 cap-test integrity rule added — where a confirmed exit is pending
     and unbooked, the test runs against the broker-true roster and the hub figure is
     indicative. GUSH id 441 is the live instance: member by composition, not a breach.
     TA-043 (2026-09-24): source hierarchy added — rows/exports/broker documents are
     evidence; briefs and narrative are context and never the basis for a tag, a roster
     membership, a sizing figure or a trade. The briefs are not amended.
     TA-041 (2026-09-24): D5 carried TWO caps, $3,750 at the head of the section and $3,850
     below the roster. $3,850 is in force (R-IV.386(d): 3,003.50 + 846.50 = 3,850.00). The
     $3,750 line is struck and its all-wrapper scope folded into the surviving statement.
     TA-038 (2026-09-24): TA-020 VOID — GDXJ is not held and all four rows are closed.
     TA-004 (2026-09-07): id 411 entry updated by the Trade Analysis lane — invalidation
     resolved (volume leg NOT FIRED, TA-002), price stop set (TA-002/TA-003), companion lot
     id 409 recorded. Book-writes now originate at Trade Analysis; data-integrity at spine.
     TA-005 (2026-09-07): TA-004 figure corrections — id 409 basis $982.45 (avg 49.1225),
     combined $1,344.14, partial restated as 4 of 7 (57%); D5 roster carries a note that
     id 332 USO's basis is under review, table and total deliberately unchanged.
     TA-009 (2026-09-07): acceptance-test coverage rule added to Standing rules — no
     BROKER_VERIFIED figure without an export covering the entry date; screenshots correct
     only where the export is silent and the note must say so. id 409 is the first instance.
     R-IV.313 / TA-012 (2026-09-07): USO id 332 SPLIT FIFO — id 332 is now the CLOSED 6/15
     lot (realized +37.00 gross) and the OPEN 7/06 lot is the new id 412 (basis 38.00).
     THE D5 USO MEMBER IS id 412; the TA-005 stamp above naming id 332 records that stamp as
     issued, and its "basis under review" is now CLOSED. WEAT normalized to gross
     (15.26 -> 15.00) with its 8/24 partial sale recorded as id 413. Roster total $2,685.20,
     headroom $1,164.80. Book stamps TA-006/TA-010 carried to id 412 — disposition only;
     TA-010's average-cost figures are superseded by FIFO and must not be revived.
     R-IV.386(d) / TA (2026-09-15): D5 roster restamped from the September export — FIVE
     members, total $3,003.50, headroom $846.50. id 412 USO and id 365 XLE both EXITED
     2026-09-10 (+512.00 / +31.90) and leave the sleeve; COPX adds a second lot, id 431
     (09-08, 4 @ 94.85). TA's line said seven members; the total and headroom were right.
     TA-017 (2026-09-15): id 411 RETIRED with its outcome and lesson; the surviving Roth SOXS
     x40 gets its own Active entry, bucket and invalidation PENDING principal, review 09-16
     FOMC. id 409 stop_loss 43.20 -> NULL (TA-013's order, which never reached CC-POSITIONS).
     target_1 49.00 and strategy_tag B2 on id 409 flagged stale, not changed. -->
<!-- Owned by Nick. Olympus updates on committee passes. Cowork morning task reads this + live positions (Pandora MCP) + the Stable board. Created 2026-07-03. -->

## How this doc works
One entry per active thesis (B1 longer-dated, B2 tactical). Every entry MUST have an invalidation level and a review date. When a thesis dies, move it to Retired with the outcome — dead theses teach more than live ones.

---

## Standing rules
(Rules that bind without a session. Added by ruling; each carries its ruling id.)

### Reachability and the TAIL tag · TA-044 (R-IV.531(b))

The **ROBINHOOD sleeve is the budget for long shots** and carries **no separate cap** (TA-039).
X4's reachability exemption **follows the TICKET, not the account**:

- a ticket tagged **TAIL** is **exempt**;
- a ticket tagged **CONVEXITY**, or carrying a thesis, **must pass reachability** — break-even within
  **1.5× the implied expected move to expiry**.

**Nothing limits long shots.** A far-OTM ticket is tagged **TAIL when it is bought**.

**BUCKET IS SET AT ENTRY.** The tag is a claim made **before the fill** about what the ticket is. **A
bucket is not changed to fit the outcome:** if a CONVEXITY ticket is retagged TAIL after entry, **the
row records who ruled it and why.**

The documented pattern was never knowingly buying lotteries — it was **thesis legs** that became
lotteries only in hindsight:

| the named instances | as the rows now read |
|---|---|
| **UVXY 40/45 at +120%** | id **376**, ×9, basis 65.00 — **expired worthless 09-18, realized −65.00** |
| **BX 60p on a 142 stock** | id **303**, ×8, basis 66.00 — **expired worthless 09-18, realized −66.00** |
| **QQQ 510/500** | id **355**, ×8, basis 185.00 — **still OPEN**, expiry 10/16 |

**A retrospective tag reproduces that pattern exactly** — it relabels the thesis as a lottery after the
outcome is known, which is why the tag is fixed at entry and a change must name its author.

**TA-045 — scope.** Applies to tickets **opened on or after 2026-09-25**. **Existing rows keep their
tags and run to their existing exits; nothing is retagged or closed on account of this rule.**

### Source hierarchy for passes · TA-043

**Rows, exports and broker documents are EVIDENCE. Weekly briefs and prior narrative are CONTEXT:**
they may be cited for what was believed on a date, **never as the basis for a tag, a roster
membership, a sizing figure or a trade.**

**Two instances, both on the record:**
1. **RAMZ filed as an energy / D5 member in the 08-31 and 09-07 briefs — and in no row, ever**
   (TA-037). RAMZ is a leveraged short of DRAM; it was never in the sleeve, and the membership
   existed only in brief text. Checked on execution: no RAMZ row mentions D5, energy or commodity,
   `tags` is NULL on all four, and this document contained no RAMZ entry.
2. **The 09-05 PIVOT verdict to sell 2 of 3 WEAT**, premised on brief text rather than the ledger's
   own partial-sale record (TA-007). The ledger already held the 3-of-6 sale at 0.10.

**The briefs are dated artifacts and are NOT amended.** Correcting them would destroy the evidence
of what was believed when; the correction belongs on the row and in this section.

### D5 — commodity / inflation sleeve cap · R-IV.192(e), R-IV.201(c)
- **The cap BINDS AT ADD.** Any order that would breach it is **declined by rule** — no
  session, no committee pass, no override needed to refuse. Refusal is the default.
- **Worst case, on its face:** de-escalation *and* a hike anyway. The sleeve can be wrong
  on both legs at once; the cap is what bounds that, not a view on either leg.
- **MEMBERSHIP — BY ID, complete roster (R-IV.251(d), rewritten from R-IV.207(b)).**
  Cost basis, all wrappers:

| id | ticker | account | structure | basis |
|---|---|---|---|---|
| 404 | IEO | FIDELITY_ROTH | stock | 1,400.60 |
| 398 | MOO | FIDELITY_ROTH | stock | 851.70 |
| **431** | COPX | FIDELITY_ROTH | stock (09-08 lot) | **379.40** |
| 406 | COPX | FIDELITY_ROTH | stock (09-02 lot) | 356.80 |
| 367 | WEAT | ROBINHOOD | call_debit_spread 29/30 ×3 | 15.00 |
| | | | **TOTAL** | **3,003.50** |

- **CAP: $3,850 all-wrapper cost basis — headroom $846.50.** Every account, every
  structure. Down from $1,164.80. **This is the single cap statement for D5 (TA-041).**
- **TA-041: this section carried two caps ($3,750 and $3,850) a few paragraphs apart.**
  $3,850 is in force per R-IV.386(d)'s arithmetic — the five members' $3,003.50 plus the
  $846.50 headroom is **$3,850.00 exactly**. One cap, one place. The stale $3,750 line has
  been struck from the head of this section; the scope it carried ("across ALL wrappers,
  every account, every structure") is preserved in the surviving statement above, so
  striking it removed an amount and not a rule.
- **FIVE members, not seven (R-IV.386(d), corrected on execution).** TA's line said seven; two
  members **exited 2026-09-10** and are no longer in the sleeve:
  **id 412 USO** (basis 38.00, realized **+512.00**) and **id 365 XLE** (basis 23.10, realized
  **+31.90**). Both closures are export-verified and were reported at R-IV.385; they had not
  reached the roster line. The **total and headroom TA quoted are correct** — $3,003.50 and
  $846.50 — because the arithmetic was already run over open rows only. Only the count was wrong.
- **COPX is now two lots, both members.** id 406 (09-02, 4 @ 89.20) and **id 431 (09-08, 4 @
  94.85)** — 8 shares, combined basis **736.20**. The 09-08 lot is the single largest addition
  since the last stamp and is what consumed most of the headroom.
- **Membership is by id, and ids change when lots split or close.** The sleeve has turned over
  twice in ten days: USO moved 332 → 412 on the FIFO split, then 412 exited; XLE exited; COPX
  gained a second id. Reading this table by ticker rather than by id will misstate it.
- **Verified against the ledger, not transcribed.** All five bases reproduce as
  `quantity × entry_price × (100 for options)` and the total lands on $3,003.50 to the cent.

- **Cap test integrity — TA-042.** D5 binds at add, so the cap test must run against a roster the
  book can vouch for. Where a broker-confirmed exit is pending and unbooked, the test runs against
  the **broker-true roster** and the hub-derived figure is marked **indicative, not binding**.
  **A cap computed from rows known to be stale is not a cap test.**
  - *Live instance, 2026-09-24:* **GUSH id 441** is a D5 member by composition (leveraged long
    energy, basis **1,124.91**). Against the $3,850 cap the hub roster would read **4,128.41 —
    over by 278.41** — but the principal **does not hold GUSH** (R-IV.516(c)) and the row is open
    only because the exit has not booked. **The sleeve is NOT breached and no add is refused on
    this row's account.** The broker-true roster is the five members at **$3,003.50**.

### D4 hedge line — DECLINED, rolled · R-IV.209
- **DECLINED 2026-09-03 by principal.** No new convexity purchased.
- **Rolls to the FOMC cluster:** CPI **2026-09-11** · FOMC **2026-09-16**.
- **Revisit window ~2026-09-08 → 09-11, pre-CPI.**
- **QQQ downside legs — the 10/16 tails are NOT the only open ones.** Per BOOK's
  don't-close ruling the two tails stand:

| id | structure | qty | expiry | note |
|---|---|---|---|---|
| 355 | QQQ 510/500 put debit | 8 | 2026-10-16 | tail, don't-close |
| 356 | QQQ 360/350 put debit | 8 | 2026-10-16 | tail, don't-close |
| ~~407~~ | ~~QQQ 690/685 put debit~~ | ~~1~~ | ~~2026-09-04~~ | **SETTLED — expired worthless, R-IV.243** |

  **id 407 was a third QQQ downside leg**, opened 2026-09-02 and expired **2026-09-04**.
  It was short-dated rather than a tail, so R-IV.209's "only QQQ downside legs" held for
  *tails* but not for *downside legs* as written. **Settled 2026-09-04 post-close** on the
  TGT id-381 pattern: QQQ 717.98 against a 690 long strike, both legs OTM, realized −15.00,
  marks NULL. **The two 10/16 tails are now the only open QQQ downside legs**, so R-IV.209's
  sentence is true again as of 09-04 — it was the short-dated leg, not the wording, that
  made it false.

### Acceptance-test coverage · TA-009
No row is acceptance-tested, and no figure marked BROKER_VERIFIED, without an export covering
its entry date. A screenshot corrects only where the export is silent, and the note says the
export was silent.

**First instance, now RESOLVED:** id 409 SOXS was corrected 2026-09-06 as **SCREEN_VERIFIED**
because no export on disk then carried a September 2026 activity line. **That is no longer true.**
A Robinhood export covering 2026-09-01 → 09-14 landed 2026-09-15, and Fidelity trade
confirmations cover 09-01 → 09-08. id 409's figures are now **BROKER_VERIFIED**: the account
bought **10 @ 51.5850 on 09-03** and **10 @ 46.6601 on 09-04** — 20 shares, $982.45, average
**49.1225**, matching the screen correction to the cent.

**And the open question closed with it.** The "missing 10 shares" were never sold and never
existed: the hub's original 30 @ 49.9433 = $1,498.30 = 515.85 **× 2** + 466.60, i.e. the 09-03
lot was **ingested twice**. See `DEF-EXPORT-COVERAGE-GAP` (Robinhood coverage now closed;
Fidelity still evidenced by confirmation rather than export).

### Interim rule — option risk figures · R-IV.207(d)
- **Never size off `max_loss`.** It is unreliable on option rows.
- **Derive** `entry_price x quantity x 100`, and **cross-check** against `unrealized_pnl`.
- Binds until DEF-HUB-MAXLOSS-OPTIONS is closed. Trace and fix sit in BUILD's held queue.

---

## Active theses

### [TEMPLATE — copy for each new thesis]
- Bucket: B1 / B2
- Thesis (one sentence):
- Expression (ticker/structure):
- Entry logic:
- Invalidation (price/level/event):
- Review date:
- Theme (Stable universe):
- Status: building / on / trimming
- Last Olympus read (date + verdict):

---

## Watch / developing
(Ideas not yet expressed — one line each, with the trigger that would activate them.)

### QQQM core re-entry — single level, no order placed · R-IV.257(a)
- **Trigger: QQQ-equivalent 681.** Approx **QQQM 280.3** — *derived, not ruled*: 681 × 0.4116,
  the ratio from the verified 2026-09-04 pair QQQ 717.98 / QQQM 295.53. The ratio drifts;
  re-derive at the pass rather than treating 280.3 as fixed.
- **Replaces the three-tranche ladder, which is not merely cancelled but collapsed to its
  lowest rung.** T2 at QQQ-equiv 697 is **SKIPPED** outright. 681 was T3's level and survives
  as a **level, not a dated tranche** — the old 10-09 backstop is **NOT carried** unless the
  principal says so.
- **Size: strictly less than the prior $1,456.60 tranche.** Exact size TBD at the PIVOT pass.
- **NO ORDER PLACED.** GTC-vs-alert mechanics decided at the pass, on the principal's
  reasoning that *a level nobody watches is a rule that can't fire.*
- Predecessor: id 401, closed 2026-09-04 at 295.53 for +21.05 — a discretionary exit and a
  principal exception to D1 (regime-break-only), no regime-break call made.

---

## Retired theses
(Date closed · thesis · outcome · one-line lesson.)

### 2026-09-21 · SOXS · FIDELITY_ROTH — semis / equity-drawdown thesis (TA-017, retired R-IV.515(d))
**Closed 09-21.** The thesis went flat and no SOXS row is OPEN in either account.

**The arc, from the rows:**

| leg | ids | qty | closed | realized |
|---|---|---|---|---|
| the chartered ×40 | 409 + 430 | 40 | **09-14** | +32.25 · +144.90 = **+177.15** |
| a same-day round trip | 438 | 20 | 09-14 | **−7.50** |
| re-expressed, then closed | **432** | 35 | **09-21** at 36.235 | **−415.04** |
| | | | **net, 09-03 → 09-21** | **−245.39** |

**432's −415.04 is from the Fidelity confirmations**, four of them: 754.50 (`26258-Q4ZDR8`) +
242.65 (`26259-PM8MYF`) + 246.43 (`26259-QKPYQL`) + 439.69 (`26261-N7WG83`) = basis **1,683.27**
against proceeds 1,268.23. Round-then-sum, per convention #27 — summing unrounded and rounding once
gives 1,683.26 and loses a cent (R-IV.507(b)).

*Parallel, other account:* ROBINHOOD id 433 (16 shares) also closed **09-21** at 36.11 for
**−220.08**, export-verified. Not part of this Fidelity thesis, but the same day and the same move.

**Lesson: no bucket and no invalidation was ever written, so it closed on discretion rather than on
a rule.** The Active entry carried "**Bucket: PENDING principal**" and "**Invalidation: PENDING
principal**" from the day it was opened to the day it went flat — five weeks — and the one price
level it ever had (43.20) belonged to a *different* trade in a *different* account and was NULLed at
TA-017(3). A thesis with no bucket has no sizing rule and a thesis with no invalidation has no exit
rule, so the only thing left to close on was judgement. **The −415.04 leg was opened 09-16 and shut
five days later; nothing written down could have told anyone whether that was right.**

**Two stale fields survive on id 409, flagged again and still not changed** (never ordered):
`target_1` **49.00** and `strategy_tag` **B2**, both TA-002's, set for the Robinhood trade retired
below. A closed row carrying another trade's bucket tag is a label the thesis contradicts.

### 2026-09-14 · id 411 SOXS ×7 ROBINHOOD — fade the semis pop (B2, R-IV.253(b))
**Entry** 51.67 on 09-04 · **outcome:** CLOSED 09-14, **realized −4.76 gross** (7 × 50.99 =
356.93 against basis 361.69), export-verified.

**The trade did not end alone.** A second lot — **id 418, 7 @ 43.60 on 09-11, realized +51.73**
— was bought while this one was underwater, and the 09-14 sale of 14 shares closed both FIFO.
**Pair net +46.97.** The retirement is of id 411; the money was made by the lot that was never
chartered.

**Lesson: no rule in this trade fired.** The Wed 09-09 time stop was overridden — added to
instead of exited. The 43.20 price stop was never reached. The exit was discretionary, three
sessions later. **A B2 that outlives its time stop is an untagged position until it is
re-chartered.**

*Full working entry retained below as filed, for the record.*

### id 411 · SOXS — fade the semis pop · R-IV.253(b)
- Bucket: **B2** (tactical, 1–3 day)
- Thesis (one sentence): fade today's semis pop on weak volume.
- Expression (ticker/structure): SOXS ×7 stock, ROBINHOOD, entry 51.67 @ 2026-09-04 17:58Z,
  basis **$361.69**.
- Entry logic: pop into weak participation; short-horizon mean reversion.
- Invalidation (price/level/event): **semis extend above 2026-09-04's high on expanding
  volume.** **Price leg fired 09-04. Volume leg NOT FIRED — principal ruling 2026-09-06
  (TA-002): low-volume session, extension not on expanding volume. Compound invalidation did
  not fire; held on stops.**
- **EXIT PLAN — two fields (R-IV.256(b)):**
  - **TIME STOP: flat by Wed 2026-09-09 close.** Binds per B2, ruled. Monday 09-07 is a
    holiday, so only **two sessions remain** — Tue 09-08 and Wed 09-09.
  - **PRICE STOP (TA-002/TA-003): hard 43.20 unconditional (SMH≈580) = `stop_loss` column.
    Daily-close stop 44.10 conditional on SMH>576 — notes only. Target 49.00: **4 of 7 off
    at 49.00 (57%, rounded up from 50%); remaining 3 carry the stop set.** Time stop
    unchanged: flat by Wed 2026-09-09 close.**
- **SIZE EXCEPTION LOGGED:** $361.69 basis against B2's $300 cap — **principal-accepted**,
  R-IV.253(b). Recorded as an exception, not a new cap.
- **COMPANION LOT — id 409, FIDELITY_ROTH, B2 (TA-002).** Same stop set; 100% off at 49.00 or
  Wed close. Broker: **20 sh, basis $982.45 (avg 49.1225, shown as 49.12)** bought 09-04 —
  *basis total is authoritative* (TA-005). Hub row: **30 @ 49.9433 dated 09-03 — qty/entry
  DISPUTED, fix at SPINE.** Combined basis **$1,344.14 (broker)** vs B2's $300 cap —
  exception logged, principal-accepted.
- Review date: **2026-09-08** (first session after the holiday).
- Status: **CLOSED 2026-09-14 — thesis resolved, awaiting retirement by TA.**

> **⚠ THIS ENTRY DESCRIBES A CLOSED POSITION (R-IV.385).** Robinhood SOXS went flat on
> **2026-09-14** and the book carried it as open for six days. The stops never fired: a second
> lot was added 09-11 at 43.60 and **both lots were sold 09-14 at 50.99**.
>
> | lot | bought | basis | realized |
> |---|---|---|---|
> | id 411 | 09-03, 7 @ 51.67 | 361.69 | **−4.76** |
> | id 418 | 09-11, 7 @ 43.60 | 305.20 | **+51.73** |
> | | | | **+46.97 net** |
>
> **Outcome for the retirement note:** the B2 time stop (Wed 09-09 close) and the price stops
> (hard 43.20 / daily-close 44.10) were all **overtaken by an add-and-hold** that was never
> booked. The thesis was right in direction and wrong in timing; the position was rescued by
> averaging down, not by the discipline that was written for it. **Per this doc's own rule —
> "when a thesis dies, move it to Retired with the outcome" — this belongs in Retired. That
> move is TA's, not POSITIONS'.**
- **Concurrency — UNENFORCEABLE AS THE BOOK STANDS.** B2 permits two concurrent. This is
  the only row in the book carrying any bucket tag: across 355 rows `strategy_tag` has ever
  held one value (`CORE`, on id 401, closed 2026-09-04) and `tags` is NULL on every row.
  So "no other B2 row is open" is true of the *labels* and says nothing about the 22 other
  open positions, which are untagged rather than known-not-B2. The cap is recorded here; it
  is not measurable until the book is tagged.
- **Mark PRINCIPAL-VERIFIED 2026-09-05 (R-IV.256(a)).** `current_price 46.34` /
  `unrealized_pnl −37.31` is **real price action** — a −10.3% same-day move from a 51.67
  entry. **DEF-SOXS-PRICE-DISCONTINUITY is NOT implicated: a negative instance on that
  defect's own namesake ticker.** Filed 09-04 as UNVERIFIED because the quote source
  returned unavailable and bars stopped at 09-03; the caution was right to raise and
  resolved against the position rather than in its favour.
- **ANTI-PATTERN TALLY (R-IV.256(d)):** logged as a **candidate** instance of *"entering
  parabolic shorts too early"* — the principal's own monitored list. Candidate, not
  confirmed: the entry went into a pop that continued, which fits the shape, but one day
  does not establish it and the volume leg is unassessed.

