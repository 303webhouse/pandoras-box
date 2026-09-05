# Trading Theses — canonical thesis ledger
<!-- FINAL for the 2026-09-04 session (R-IV.251(d)). Standing rules section added
     R-IV.192(e)/201(c); D5 membership rewritten by id R-IV.207(b) and again R-IV.251(d);
     option-risk interim rule added R-IV.207(d); D4 hedge line DECLINED/rolled R-IV.209.
     All ferry items written. NO DATED ACTIONS OUTSTANDING — id 407 stamped R-IV.243,
     id 408 stamped R-IV.251(b), both 2026-09-04 post-close.
     Expiry completeness is now a QUERY, not this header (R-IV.251(c)): each session close,
     every row WHERE expiry <= today AND status='OPEN' is stamped. The hand-enumerated
     dated-action line is retired as the completeness instrument; id 408 is why. -->
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
| 406 | COPX | FIDELITY_ROTH | stock | 356.80 |
| 332 | USO | ROBINHOOD | call_debit_spread 150/165 | 145.00 |
| 365 | XLE | ROBINHOOD | call_debit_spread 70/80 | 23.10 |
| 367 | WEAT | ROBINHOOD | call_debit_spread 29/30 ×3 | 15.26 |
| | | | **TOTAL** | **2,792.46** |

- **CAP: $3,850** all-wrapper cost basis. **Headroom $1,057.54.**
- **SLEEVE OPEN — adds within headroom, each subject to standing rules.** This reverses the
  prior CLOSED state. Two members exited **2026-09-04 18:01Z**: id 402 GDX (760.00) and
  id 405 SIL (292.62), removing $1,052.62 of basis and taking headroom from $4.92 to
  $1,057.54. An add is no longer refused by rule; it still faces every other standing rule.
- **COMPOSITION — precious metals ZERO as of 2026-09-04 18:01Z.** GDX and SIL were the only
  precious-metals members and both exited 39 seconds apart. What remains is energy (IEO,
  USO, XLE), agriculture (MOO, WEAT) and copper (COPX). The sleeve's size fell 27% but its
  *composition* changed more than its size did — read the cap against that, not just the
  dollar figure.
- **Verified against the ledger, not transcribed.** All six bases reproduce as
  `quantity x entry_price x (100 for options)` and the total lands on $2,792.46 to the cent.
- **Basis is COST BASIS, never `max_loss` — and the failure direction has FLIPPED.**
  Stored `max_loss` on this roster: XLE **69.30** against a true 23.10 (+46.20), WEAT
  **30.52** against 15.26 (+15.26), and **MOO is NULL** — absent, not wrong. Summing
  `max_loss` now yields **$2,002.22, understating the true $2,792.46 by $790.24**, because
  the NULL silently drops an $851.70 member and outweighs the two overstatements. Under the
  old roster the same mistake overstated and breached the cap; it now *understates* and
  would invite adds the cap should refuse. The dangerous direction reversed with the
  roster. See DEF-HUB-MAXLOSS-OPTIONS below.

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

### Interim rule — option risk figures · R-IV.207(d)
- **Never size off `max_loss`.** It is unreliable on option rows.
- **Derive** `entry_price x quantity x 100`, and **cross-check** against `unrealized_pnl`.
- Binds until DEF-HUB-MAXLOSS-OPTIONS is closed. Trace and fix sit in BUILD's held queue.

---

## Active theses

### id 411 · SOXS — fade the semis pop · R-IV.253(b)
- Bucket: **B2** (tactical, 1–3 day)
- Thesis (one sentence): fade today's semis pop on weak volume.
- Expression (ticker/structure): SOXS ×7 stock, ROBINHOOD, entry 51.67 @ 2026-09-04 17:58Z,
  basis **$361.69**.
- Entry logic: pop into weak participation; short-horizon mean reversion.
- Invalidation (price/level/event): **semis extend above 2026-09-04's high on expanding
  volume.** **Price leg LIKELY FIRED** — semis extended after entry. **Volume leg
  UNASSESSED**, pending principal; whichever he states governs Tuesday's open (R-IV.256(c)).
- **EXIT PLAN — two fields (R-IV.256(b)):**
  - **TIME STOP: flat by Wed 2026-09-09 close.** Binds per B2, ruled. Monday 09-07 is a
    holiday, so only **two sessions remain** — Tue 09-08 and Wed 09-09.
  - **PRICE STOP: PENDING — OLYMPUS sets at the PIVOT pass before Tue 2026-09-08 open**
    (R-IV.257(b)). Written as the word, not left blank. The `stop_loss` column is numeric
    and cannot carry it, so the column stays NULL and the absence is recorded in `notes`
    where every read will see it. **The pass is now the binding dependency** — if it does
    not happen before Tuesday's open, the position runs to the time stop with no price
    stop at all.
- **SIZE EXCEPTION LOGGED:** $361.69 basis against B2's $300 cap — **principal-accepted**,
  R-IV.253(b). Recorded as an exception, not a new cap.
- Review date: **2026-09-08** (first session after the holiday).
- Status: **UNDER PRESSURE** — day-one −10.3%.
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
