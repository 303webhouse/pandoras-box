# Trading Theses — canonical thesis ledger
<!-- FINAL for the 2026-09-03 book session (R-IV.207(e)). Standing rules section added
     R-IV.192(e)/201(c); D5 membership rewritten by id R-IV.207(b); option-risk interim
     rule added R-IV.207(d); D4 hedge line DECLINED/rolled R-IV.209.
     All ferry items written. One dated action outstanding: id 407 expiry stamp 2026-09-04. -->
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
- **MEMBERSHIP — BY ID, complete roster (R-IV.207(b), BOOK).** Cost basis, all wrappers:

| id | ticker | account | structure | basis |
|---|---|---|---|---|
| 404 | IEO | FIDELITY_ROTH | stock | 1,400.60 |
| 398 | MOO | FIDELITY_ROTH | stock | 851.70 |
| 402 | GDX | FIDELITY_ROTH | stock | 760.00 |
| 406 | COPX | FIDELITY_ROTH | stock | 356.80 |
| 405 | SIL | FIDELITY_ROTH | stock | 292.62 |
| 332 | USO | ROBINHOOD | call_debit_spread 150/165 | 145.00 |
| 365 | XLE | ROBINHOOD | call_debit_spread 70/80 | 23.10 |
| 367 | WEAT | ROBINHOOD | call_debit_spread 29/30 ×3 | 15.26 |
| | | | **TOTAL** | **3,845.08** |

- **CAP RESTATED: $3,850** all-wrapper cost basis (BOOK's own correction of its earlier
  $3,750). **Headroom $4.92. SLEEVE CLOSED.**
- **Verified against the ledger, not transcribed.** All eight bases reproduce as
  `quantity x entry_price x (100 for options)` and the total lands on $3,845.08 to the cent.
- **Basis is COST BASIS, never `max_loss`.** Two of the three option members carry a wrong
  `max_loss` — XLE 69.30 against a true 23.10, WEAT 30.52 against 15.26. Summing `max_loss`
  instead would total **$3,906.54 and breach the closed cap by $56.54** while appearing to
  be the more conservative figure. See DEF-HUB-MAXLOSS-OPTIONS below.
- **Operative consequence:** the sleeve is CLOSED. Any add to any of the eight ids above is
  declined by rule, regardless of the member's individual size.

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
| 407 | QQQ 690/685 put debit | 1 | **2026-09-04** | **not a tail — expires in 1 day** |

  **id 407 is a third live QQQ downside leg**, opened 2026-09-02, expiring **2026-09-04**.
  It is short-dated rather than a tail, so R-IV.209's "only QQQ downside legs" holds for
  *tails* but not for *downside legs* as written. Flagged because it expires inside the
  revisit window and needs a settlement stamp on 09-04 (TGT id 381 pattern: status EXPIRED,
  realized from settlement, mark fields NULL never zero).

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

---

## Retired theses
(Date closed · thesis · outcome · one-line lesson.)
