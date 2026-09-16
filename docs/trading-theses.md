# Trading Theses — canonical thesis ledger
<!-- FINAL for the 2026-09-04 session (R-IV.251(d)). Standing rules section added
     R-IV.192(e)/201(c); D5 membership rewritten by id R-IV.207(b) and again R-IV.251(d);
     option-risk interim rule added R-IV.207(d); D4 hedge line DECLINED/rolled R-IV.209.
     All ferry items written. NO DATED ACTIONS OUTSTANDING — id 407 stamped R-IV.243,
     id 408 stamped R-IV.251(b), both 2026-09-04 post-close.
     Expiry completeness is now a QUERY, not this header (R-IV.251(c)): each session close,
     every row WHERE expiry <= today AND status='OPEN' is stamped. The hand-enumerated
     dated-action line is retired as the completeness instrument; id 408 is why.
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

### D5 — commodity / inflation sleeve cap · R-IV.192(e), R-IV.201(c)
- **Cap: $3,750 across ALL wrappers** (every account, every structure).
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

- **Cap $3,850 — headroom $846.50.** Down from $1,164.80.
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

### SOXS ×40 · FIDELITY_ROTH — semis / equity-drawdown thesis · TA-017
- **Bucket: PENDING principal.** Leveraged ETF; B2 rules do not fit a multi-week hold, and B1
  is excluded for leveraged by standing rule. **The position is live and unchartered.**
- Thesis: hot-CPI / hike / oil-shock equity drawdown, expressed through 3× inverse semis.
- **Invalidation: PENDING principal.** No price level is live — id 409's 43.20 was TA-002's
  Robinhood level and was NULLed at TA-017(3).
- Review date: **2026-09-16 (FOMC).**
- Status: **on — unchartered.**
- Last Olympus read: 09-09/09-10 — instrument mismatch for a multi-week thesis, stated once.

**The two lots, both BROKER_VERIFIED against Fidelity confirmations:**

| id | bought | qty | price | basis |
|---|---|---|---|---|
| 409 | 09-03 + 09-04 | 20 | 51.5850 / 46.6601 → avg **49.1225** | 982.45 |
| 430 | 09-08 | 20 | **43.4901** | 869.80 |
| | | **40** | | **1,852.25** |

At the 09-14 mark of **51.73** the pair carries **+$216.95** into FOMC eve.

> **⚠ TWO STALE FIELDS ON id 409, flagged not changed.** `target_1` still reads **49.00** and
> `strategy_tag` still reads **B2** — both are TA-002's, set for the Robinhood trade that
> retired below. They are stale by exactly the reasoning that retired the 43.20 stop, but
> neither was ordered changed. **A position whose bucket is PENDING should not be carrying a
> bucket tag**; until it is re-chartered, `B2` on this row is a label the thesis contradicts.

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

