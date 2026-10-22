# § Account Context — v5.5, consolidated verbatim block

```
RULES VERSION: 2026-10-14/v5.5
REVISES:       2026-10-09/v5.4 (claude/account-context-2026-10-09-v5_4.md)
SUPERSEDES:    2026-10-09/v5.3 (claude/account-context-2026-10-09-v5_3.md)
               2026-10-08/v5.2 (claude/account-context-2026-10-08-v5_2.md)
               2026-10-08/v5.1 and 2026-10-08/v5 (claude/account-context-2026-10-08-v5.md)
               2026-10-08/v4  (claude/account-context-2026-10-08-v4.md)
               2026-10-08/v3  (claude/account-context-2026-10-08-v3.md)
               2026-10-07/v2  (claude/account-context-final-and-tranche1-2026-10-07.md, Part 4 v2)
STATUS:        CURRENT — scheduled tasks read the highest RULES VERSION, not the filename
SHAPE:         SECTION A + B + C + D + E, drop-in for COMMITTEE_RULES.md and six
               agent SKILL.md files. The authoritative stamp is INSIDE SECTION A.
STATUS:        FINAL — nothing deferred. Issued under R-IV.1034(c).
CONTAINS:      v5.4 in full, and v5.3 within it. BUILD applies ONCE and the
               principal uploads ONCE.
```

### v5.4 -> v5.5 changelog

**Three entries, all inside SECTIONS A and B. SECTIONS C, D and E are untouched.**
Issued under R-IV.1034(c) from TA-171's pending list.

1. **The Roth/401(a) 20% tactical cap now states its BASIS and its ENFORCEMENT
   LEVEL, and carries its two triggers.** Ruled by the principal 2026-10-14
   [R-IV.1031(a), triggers R-IV.1034(b)]. The cap was written without saying how
   the numerator is measured. For unleveraged holdings the candidate readings
   coincide, which is why it never surfaced; with TSLQ (−2×) and SRTY (−3×) both
   in the sleeve on 2026-10-14 the same two positions read **18.78%** on market
   value and **44.57%** on underlying-equivalent. Canonical text in **SECTION A**
   under FIDELITY_ROTH; agent-facing in **SECTION B**'s cap bullet.
2. **Leverage factor is a RECORDED field at entry, not a lookup**, and a dollar
   delta published to an underlying states the reference asset and the factor
   [TA-164 condition 7]. SRTY −3× added beside SOXS and TSLQ. In **SECTION A**'s
   § Household net-direction cap.
3. **DEBIT_WHITELIST** — the closed, exact-match set the B2 cut reads for a row's
   orientation [TA-168 §1, adopted R-IV.1021(a)]. In **SECTION A** under § Buckets.

**The two caps measure differently, and SECTION A now says so explicitly**, because
entry 1 and the pre-existing § Household net-direction cap would otherwise look
like a contradiction and invite someone to "fix" one to match the other.

### v5.3 -> v5.4 changelog

**Two principal decisions of 2026-10-09 become rules text: C5 and F5** [R-IV.822(c)].
This version CONTAINS v5.3, so BUILD applies one package and the principal uploads
once, the way 09-23's Wave 1 ran.

1. **C5 — before-the-turn signals surface only as B3 or TAIL**, and before-the-turn
   SHORTS carry the no-fly flag "entering parabolic shorts too early." Canonical
   text in **SECTION A** under § Buckets; agent-facing bullet in **SECTION B**.
2. **F5 — the ceiling on flow-originated signals**: B3 with a PYTHIA value-area
   trigger, or TAIL; B2 only after a registered forward pass and a SPINE ruling
   citing it; B1 never. It sharpens X10, so **X10's own bullet is now inside
   SECTION B's replacement set** — it was not in v5.3's. Canonical text in
   SECTION A beside C5.
3. **SECTION E is new** — the five seats that cite X10 or the B3/TAIL rule
   (PIVOT, DAEDALUS, TORO, URSA, PYTHIA). SECTION D's two label targets are
   unchanged, so the package now touches six agent files in total.

**SECTIONS C and D are unchanged from v5.3.** SECTION A gains one sub-section and
three retired-list entries plus its stamp. SECTION B gains two bullets, one of
which replaces X10's existing line. BUILD re-pulls all five.

### What is deliberately NOT in this version

**C1 — the program goal** ("every regime has at least one live, graded long and one
short on the 3x2 grid," replacing the 2026-09-23 equal-balance goal). SPINE ruled
it owns this goal and that **it is not rules text** [R-IV.822(c)1]. TA did not write
it in. It is recorded here only so a later reader does not conclude the omission was
an oversight.

**N4 — the Nemesis naming** (the March-approved WRR is Nemesis; the coded dip-buy
gets its own name). That is a strategy-registry fact, LAB's to card, not a rule any
seat reads.

---

### v5.2 -> v5.3 changelog

**Two changes. This is the version bump R-IV.791(b) anticipated** — both items
change text BUILD applies or reads as instructions, so neither could ride inside
v5.2's stamp.

1. **TA-128 is new** (adopted R-IV.806(c)): *a thesis label's example holdings are
   a template, never an inventory; the book is read from the book.* It lands in two
   places — the agent-facing hard rule in **SECTION B**, and a lead-in note at the
   head of **SECTION C** so the rule sits where the templates do. The failure that
   caused it is recorded in SECTION A's retired list.
2. **The For-BUILD table's SECTION D row is corrected.** It still named
   `skills/ursa/references/equities.md` and `skills/thales/references/` — the two
   wrong paths SECTION D's own prose had already retired. It now reads
   `skills/ursa/SKILL.md` and `skills/thales/SKILL.md`. Held deliberately at
   R-IV.788(d)/TA-121 so it could ride with a bump rather than be edited silently
   under v5.2's stamp. **The SECTION C row is also widened**, because SECTION C is
   now a note plus a bullet rather than a bullet alone.

**SECTIONS A and D are otherwise unchanged from v5.2** — A gains two retired-list
entries and its own stamp line, D gains nothing. **SECTION B CHANGED** (the TA-128
bullet). **SECTION C CHANGED** (the lead-in note). BUILD re-pulls all four.

---

### v5.1 -> v5.2 changelog

Four changes. **Three are additions inside SECTION A; one adds two new sections.**

1. **The `RULES VERSION` stamp now sits INSIDE SECTION A**, as its first line, per
   BUILD's finding that v5.1's stamp sat outside both sections and so did not
   survive a verbatim apply. The stamp in the fenced header above is now a
   convenience copy; **the one inside SECTION A is authoritative.**
2. **New `§ Buckets`** in SECTION A, quoting `skills/ursa/references/equities.md`
   and `skills/toro/references/equities.md` verbatim, so the rules file is the one
   author and no agent reaches into a reference file for a definition the rules
   file already uses. [R-IV.778(b), (f)]
3. **`§ Household net-direction cap` gains the leverage-adjustment measure** ruled
   at R-IV.778(d): shares 1x, leveraged and inverse ETFs at their stated multiple,
   options at delta-adjusted notional.
4. **SECTION C and SECTION D are new** — the CREDIT-STRESS thesis label for
   `§ Bias and Thesis Labels`, and the URSA/THALES reference updates it requires.
   Both live outside `§ Account Context`, so neither could go in SECTION A.

**Nothing in v5.1 was removed or reworded.** BUILD applying v5.1 re-pulls SECTION A
**and SECTION B**, then adds SECTION C and SECTION D.

**SECTION B CHANGED.** An earlier draft of this changelog said it was unchanged from
v5.1; that was written before (c)'s X4 ruling landed there and is corrected here.
SECTION B gained the X4 implied-volatility bullet. [R-IV.786(b)]

**FINALISED 2026-10-08 under R-IV.781(f).** Two items that were open in the first
pass are now in:

5. **TA-044 is quoted verbatim** in § Buckets, and **CONVEXITY is defined** — the
   long-shot ticket that is *not* exempt, held to reachability. It is no longer
   blocked. [R-IV.781(b)]
6. **X4's input is ruled: ATM implied volatility of the position's own
   expiration**, in SECTION B. [R-IV.781(c)]

**And one error in the first pass is corrected, not merely amended.** That pass
carried an "assignment order" reading *fails X4 -> TAIL*, and a TAIL bullet calling
X4 "the discriminating test." **Both inverted TA-044.** The bucket is set at entry
and X4 tests it; letting a failing ticket relabel itself TAIL would make X4
unfalsifiable, since TAIL is the one tag X4 exempts. The inversion is removed from
§ Buckets, named in SECTION B, and added to the retired list. **It was caught
before BUILD applied anything.**

---

## Read this before applying

**One block replaces a three-layer delta stack.** v2 was the base, v3 and v4 were deltas against it, and TA-112 §5 was a delta against v4. BUILD was being asked to apply four documents in order. SECTION A and SECTION B below are the whole rule, assembled, with nothing left to merge.

**A naming hazard, stated so it cannot bite.** TA-112 §2 drafted a gold-restored mix and informally called it "v5." **That mix never issued.** The principal confirmed on 2026-10-08 (R-IV.762(a)) that *both* Fidelity accounts block gold, so it was abandoned. **`2026-10-08/v5` is this consolidation and nothing else.** Any document or note describing "v5" as a gold mix predates the confirmation and is void. This is the same defect family as `max_loss` and the PYTHIA version string — a label read as the thing it labels.

**One claim is deliberately dropped, not carried.** v4 §5 asserted that Part 4 v2 instructs scheduled tasks to size from `hub_get_portfolio_balances`. **It instructs the exact reverse.** v4 is the version the scheduled tasks resolve to today, so the correction is urgent rather than cosmetic. v4 §5 is withdrawn, the original balance-source paragraph survives below unaltered, and v4 has been marked superseded at its own path.

---

## SECTION A — `COMMITTEE_RULES.md § Account Context`

**Apply to all eight rule copies. Replaces the § Account Context Framework section in full.**

```markdown
## § Account Context Framework

RULES VERSION: 2026-10-14/v5.5 — AUTHORITATIVE STAMP. An agent or scheduled task
reading this section resolves its version from THIS line, not from whatever
document carried the section to it. Supersedes 2026-10-09/v5.4, 2026-10-09/v5.3,
2026-10-08/v5.2, /v5.1, /v5, /v4, /v3 and 2026-10-07/v2.

NEVER hardcode dollar amounts. NEVER cite a specific account balance unless it
came from a source named below within this conversation.

**Where balances come from.** Read the balance **from the broker apps**. The hub's
raw balance aggregate (`hub_get_portfolio_balances`) is NOT a sizing input while
its repair is outstanding. A **POSITIONS figure reconciled against a broker export
may be used for sizing only when it carries its as-of date AND the date of its
latest passing broker tie-out**; without both dates it is not usable. [R-IV.732]
An agent that has neither a broker-app figure nor a dated reconciled POSITIONS
figure sizes by **percentage** of the relevant account or sleeve and says the
dollar figure is unavailable. It does not substitute a hub number.

### The three tracked accounts

There are **three** tracked accounts, by number. They are distinct. Any text
treating BrokerageLink as part of the Roth is superseded.

**FIDELITY_401A — BrokerageLink, account ...1836.** Carries the long-term core
in full. One plan with FIDELITY_ROTH (see § One plan, two tax locations).
- Strategic holdings sit **outside** the 20% risk cap, governed instead by the
  **per-position limit** below and a **15% total real-asset** limit. [TA-098 §1a;
  real-asset figure adopted by the principal 2026-10-07, R-IV.729(a)]
- **Per-position limit — 15%, and its scope.** The limit applies to any holding
  whose exposure is concentrated in **one sector, one commodity, one issuer, or
  one theme**: sector ETFs, commodity funds, single names, satellite and thematic
  holdings. It does **NOT** apply to **broad-market multi-sector index funds** or
  to **short-duration US Treasuries** — a broad index failing is the market
  failing, which is not the concentration risk the limit exists to bound.
  [Scope confirmed by the principal 2026-10-07, R-IV.735]
- **The limit's denominator is the combined core across both Fidelity accounts,
  never one account.** Risk is economic, not custodial: a holding that is 7% of
  the money is 7% of the risk wherever it is custodied. This follows directly from
  § One plan, two tax locations. [TA-112 §2]
- Tactical positions sit **fully inside** the 20% cap at TA-034's 100% default.
  [TA-098 §1b]
- A **2% loss alert** on every row, strategic and tactical alike. [TA-098 §1c]
- The cap is measured **at market on both sides of the ratio**. Cost basis remains
  correct for P&L, basis tracking and TA-095 attribution, and is not the cap's
  input. [TA-101 §1]
- **Classification is the principal's**, recorded on the row, never inferred from
  ticker, leverage or bucket tag. [TA-098 §2]
- **Do not consume a field named `max_loss` from either the hub or the book** for
  any cap computation. The two stores disagree: the hub derives it from cost on
  every row; the book stores a written value absent on 11 of 28 rows and exceeding
  the position's maximum possible loss on at least two. Compute from current market
  value. [TA-102 §5]

### § Strategic exit rule

A strategic row may carry a price stop. Where it does, the stop sits at a **weekly
close below the 200-day SMA**, with **3× the 20-day ATR** as a **minimum distance**
— **whichever is further from entry.** A stop closer than that makes the row
**tactical**, automatically, regardless of stated intent. A stopped-out strategic
row closes carrying the classification it held and is flagged for review, never
auto-reclassified. [R-IV.729(a)]

**"Further from entry" is the selection, and 3×ATR is a floor on the stop's room,
never a ceiling.** Where both candidates sit below entry, the one further from
entry governs — which is the looser stop. Reading it as the tighter one would set a
2.6% stop on a decades-horizon index holding. [TA-112 §1]

**Four cases, tested in this order. The order is the rule, not a presentation
choice.**

**Case 0 — ballast, tested FIRST and dispositive.** **Short-duration Treasuries
and cash equivalents held as ballast carry no price stop at all.** Invalidation is
recorded as *allocation only*: they exit on rebalancing or a change in the target
mix, never on a price level. A holding whose moving averages sit within cents of
each other and whose ATR is a rounding error produces a stop that fires on
settlement noise. **Where a row is ballast, cases 1–3 are not reached**, even when
its entry satisfies case 3's condition — both candidates are computed and both are
recorded as *not applicable*, so a reader can see the check was run. Cases 1–3
apply only to rows carrying a thesis that price can invalidate. [v3 §2(a);
precedence stated TA-115 §1]

**Case 1 — entry above the 200-day SMA, gap WIDER than 3×ATR** — the **200-day
SMA** governs, being further from entry. The 3×ATR candidate is computed, loses,
and is recorded as checked.

**Case 2 — entry above the 200-day SMA, gap at or NARROWER than 3×ATR** —
**entry less 3×ATR** governs, being further from entry. This follows from the
"further from entry" selection and was unenumerated in v5; it is stated here so no
reader has to derive it. [TA-115 §1]

**Case 3 — entry at or below the 200-day SMA** — the 200-SMA does not govern; a
stop above entry is an instruction to sell immediately. **The stop is entry less
3× the 20-day ATR until price closes above the 200-day SMA on a weekly basis**,
after which the 200-SMA takes over permanently and cases 1–2 apply. [v3 §2(b)]

**Entry-anchored levels are per-row by construction and are never shared across
rows.** Two accounts filling the same ticker on the same day carry different
levels. An add re-anchors that row to its new weighted average cost. [TA-109]

**Every priced line is published with all candidates shown and the governing one
named** — including candidates that lost and candidates recorded as not
applicable. A line shown alone is indistinguishable from a line never checked.
Where a candidate depends on a position attribute the publishing lane does not
hold, it is published as *pending from the execution record*, never computed from
market data. [TA-110 §7]

**Entry, fill, basis and quantity come from the execution record — never from a
market-data field.** `spot` is not a fill. TA-008 ranks *sources* for a figure and
says nothing about taking the wrong *field* from the right source. [TA-109]

**FIDELITY_ROTH — Roth Brokerage, account ...3158.** 50% core, 50% trading
sleeve. [R-IV.730(a)]
- **The 50% split is measured on total account value** — holdings at market plus
  cash — **at the measurement close.**
- **Core-half deployable cash = (50% × account value) − (market value of core
  holdings held in the Roth).** A holding is "core" if it appears in the target mix.
- **TSLQ sits in the sleeve half**, not the core. It is not in the target mix; the
  deployment schedule neither buys nor sells it. It counts against the sleeve's 20%
  tactical cap and against the household net-direction cap at its 2× leverage.
- **The core half** holds the same target mix as the 401(a), governed by the same
  rules above, and is the only half on the deployment schedule.
- **The trading sleeve** is the principal's active account: a mix of whatever the
  market dictates, higher up the risk curve, positioned in line with his bearish
  bias where the tape allows it. Trading here is tax-sound — realised gains are
  tax-free. No options on this account.
- The **20% risk cap** applies to the sleeve's tactical positions, at market. Its
  basis, enforcement level and triggers are below.

### § The 20% tactical cap — BASIS, LEVEL AND TRIGGERS. RULED by the principal 2026-10-14

Applies to **FIDELITY_ROTH and FIDELITY_401A**. ROBINHOOD is governed by its sleeve
ceiling instead.

**Basis:** market value of TACTICAL positions ÷ the account's total balance
(holdings at market plus cash). **Leveraged and inverse products count at MARKET
VALUE, not underlying-equivalent.** [Principal, 2026-10-14, R-IV.1031(a)]

**Enforcement level: REMINDER.** Surface the percentage when the cap is crossed.
**It never blocks a ticket and never vetoes a pass.** [Principal, 2026-10-14]

**Two triggers, so the reminder has something to fire from** [R-IV.1034(b)]:
1. **Every idea pass** carries the risk-budget line, including the Roth and 401(a)
   tactical percentage on the market-value basis.
2. **Any position write in FIDELITY_ROTH or FIDELITY_401A recomputes the cap.**
   BUILD pushes a phone reminder, **percent only**, at ≥ 20%. A row whose
   `classification` is NULL counts as TACTICAL **provisionally**, so an unclassified
   write cannot hide a crossing.

**WHY THE BASIS HAD TO BE WRITTEN DOWN.** On 2026-10-14 the Roth held TSLQ (−2×) and
SRTY (−3×). The same two positions read **18.78%** on market value and **44.57%** on
underlying-equivalent — a 2.374× difference, compliant under one reading and 24.57
points over under the other. For unleveraged holdings the two coincide, which is why
a cap written without its basis survived this long unexercised.

**THIS CAP AND THE HOUSEHOLD NET-DIRECTION CAP MEASURE DIFFERENTLY, ON PURPOSE.**

| | numerator basis |
|---|---|
| **20% tactical cap** (this section) | **market value** — leveraged and inverse at market |
| **Household net-direction cap** (below) | **leverage-adjusted** — ETFs at their stated multiple, options at delta-adjusted notional |

They are not in conflict and **neither is to be "corrected" to match the other.**
They answer different questions. This cap asks *how much of the account is in
tactical positions*, which is a capital-allocation question answered at market. The
net-direction cap asks *if the market moves 1%, which way does the household move
and how far*, which only leverage and delta answer. An agent that applies one basis
to the other cap has changed the rule.

### § Z2 trend gate — RULED by the principal 2026-10-08 ("match the clock")

The sleeve is trend-gated under Rule 0 and Z2. PYTHAGORAS's read governs what
"confirmed" means.

- **The trend qualifier applies to BOTH clauses.** Long an ETF only on a confirmed
  **uptrend**; inverse or short-side exposure only on a confirmed **downtrend** —
  each **on the timeframe that justifies the trade.** Cash when the trend is
  unclear.
- **A trade justified on an intraday timeframe must be closed by the next
  session's close.** Holding past that requires the **daily** trend to qualify on
  its own merits.
- **Until the hub serves intraday indicators** — `hub_get_chart_indicators` is
  daily-only, intraday pending v1.1, and this is a logged build dependency —
  **Z2 on a same-day row returns NOT EVALUABLE, never FAIL. The clock still
  applies.**

Reading Z2's inverse clause without a timeframe qualifier would have forbidden
news-catalyst momentum trading in the sleeve entirely, whenever the daily trend
was up. Nobody ruled on that, which is why it was a drafting gap and not a rule.
[TA-113 §3; ruled R-IV.765(d)]

### § Buckets — quoted from source, 2026-10-08 [R-IV.778(b)]

Every position carries a bucket. **Classification is the principal's** (TA-098 §2);
these definitions decide what a bucket then REQUIRES. Quoted verbatim from
`skills/ursa/references/equities.md` "Three-Bucket Fit (Bear Side)" and
`skills/toro/references/equities.md` "Three-Bucket Fit", so this file is the one
author.

- **B1 (thesis).** "Multi-week to multi-month bear thesis. Inverse ETFs in
  FIDELITY_ROTH (only on a confirmed downtrend), LEAPS puts, or 30-60 DTE put
  spreads. Sizing per longer-dated thesis rules." Bull side: "Multi-week to
  multi-month bull thesis. Equity, LEAPS, or 30-60 DTE calls/spreads."
  **B1 is a HORIZON, not a DTE band** — LEAPS run well beyond 60 DTE and are
  explicitly B1, so 30-60 DTE is a typical signature, not a boundary. X4 and X10
  both apply.
- **B2 (tactical 3-5 day momentum).** "Sized inside the ROBINHOOD sleeve ceiling
  (the $200-300 cap is retired, 2026-09-23). Common expressions: 7-14 DTE put
  debit spreads, put credit spreads on bounces. **Cut if not profitable in 3
  days.**" Bull side: "7-14 DTE calls or call debit spreads." X4 and X10 both
  apply.
  **Where a B2 row's DTE is at or below its 3-day cut, the time stop is
  INOPERATIVE** — the cut and the expiry are the same event. Such a row carries an
  explicit intra-horizon stop instead (a named level, or a day-1 close), or is
  recorded as expiry-stopped. It is never recorded as carrying a 3-day cut it
  cannot execute. This is why B2's stated expression is 7-14 DTE: the band exists
  so the time stop has room to work. [TA-117 §2a]
  **ORIENTATION FOR THE B2 CUT — DEBIT_WHITELIST, a CLOSED set read by EXACT MATCH**
  [TA-168 §1, adopted R-IV.1021(a)]. The cut's P&L is signed by whether the row was
  opened for a debit or a credit. That orientation is **never parsed out of the
  `structure` string by substring**, which is the `strategy_tag` failure in another
  column (TA-123). A value qualifies only when **its own text states the orientation
  unambiguously under standard options convention**:
  - **DEBIT, orientation +1:** `put_debit_spread`, `call_debit_spread`, `long_put`,
    `long_call`.
  - **UNDETERMINED, held, no evaluation:** `stock` (**can be short**),
    `long_single`, `vertical`, `put_spread`, `three_leg`, `iron_condor`, and **every
    composite containing `+`**.
  One named constant, exact match on the **whole** value, never a substring, never a
  default, no splitting on `+`. Holding `stock` is deliberate: a wrong-signed stock
  verdict reports a LOSING position as PROFITABLE, and silence is recoverable where
  an inverted verdict is not.
- **B3 (intraday scalp).** "Structural Pythia VA trigger required, mechanical stop
  at entry, target = next Pythia level. Two consecutive losers = circuit breaker,
  done for day. $300 daily max loss." Plus, bull side: "max 2 concurrent, max
  3/day, same-day close." The $100 cap is retired (2026-09-23).
- **TAIL.** A long-shot ticket tagged as such **at entry**. The sleeve "buys
  unreachable strikes on purpose and is exempt by design" from X4 (§ Shared Hard
  Rules), so **a TAIL ticket is the one case X4 does not test.**
- **CONVEXITY.** A long-shot ticket that is **NOT** exempt: **convexity held to
  reachability.** It is the same kind of bet as TAIL and the opposite treatment —
  tagging a ticket CONVEXITY rather than TAIL is a claim that its break-even is
  reachable, and X4 then tests that claim.

### § Buckets — the tag is set at entry [TA-044, quoted verbatim]

From `docs/trading-theses.md`, "Standing rules -> Reachability and the TAIL tag ·
TA-044 (R-IV.531(b))", supplied 2026-10-08 under R-IV.781(b):

> "The ROBINHOOD sleeve is the budget for long shots and carries no separate cap
> (TA-039). X4's reachability exemption follows the TICKET, not the account:
> - a ticket tagged TAIL is exempt;
> - a ticket tagged CONVEXITY, or carrying a thesis, must pass reachability —
>   break-even within 1.5x the implied expected move to expiry.
>
> Nothing limits long shots. A far-OTM ticket is tagged TAIL when it is bought.
>
> **BUCKET IS SET AT ENTRY.** The tag is a claim made before the fill about what
> the ticket is. A bucket is not changed to fit the outcome: if a CONVEXITY ticket
> is retagged TAIL after entry, the row records who ruled it and why."

**TA-045's scope:** tickets opened **on or after 2026-09-25**. Existing rows are
not retagged.

**The consequences, spelled out because they invert an earlier draft of this
section:**

1. **X4 does not assign buckets. The bucket assigns X4.** The tag is chosen at
   entry from the ticket's intent and horizon; X4 then reports **PASS or FAIL
   against that tag**. A FAIL on a non-TAIL ticket **is a FAIL** — recorded on the
   row as it falls.
2. **"TAIL if it fails X4" is forbidden.** It is exactly the retag-to-fit-the-
   outcome TA-044 prohibits, and it would make the rule unfalsifiable: every
   failing ticket could relabel itself into the one bucket that exempts it.
3. **For an in-scope row carrying no bucket at entry**, the bucket is **the
   principal's intent at entry** — never inferred from the X4 outcome. [R-IV.781(d)]
4. **A bucket change after entry records its author and reason on the row.**
   Example on the record: 979's B1 -> B2 change is authored by **SPINE
   R-IV.778(b)**, on the ground that 4 DTE is not a multi-week horizon.
5. **A row opened before 2026-09-25 keeps its tag** under TA-045's scope, whatever
   X4 would now say about it.

### § Bucket ceilings by signal provenance — RULED 2026-10-09 [R-IV.822(c)]

Two rules cap **which buckets a ticket may claim**, by where its signal came from.
They are **ceilings on the eligible set**, not bucket definitions, and they do not
touch the definitions above.

**C5 — a signal that fades a move BEFORE the trend breaks surfaces only as B3 or
TAIL.** "Breaks" is the 2026-09-23 definition: **a daily close through the 50-day
average, the average stack turning, and volume confirming.** A signal taken before
all three conditions hold is before-the-turn, whatever its conviction and whatever
the eventual outcome. A before-the-turn **SHORT** additionally carries the no-fly
flag **"entering parabolic shorts too early"** written on its face, at proposal and
on the row. [Principal 2026-10-09; 09-23 collision #3]

**F5 — a flow-originated signal may be:**
- **B3**, with a PYTHIA value-area trigger;
- **TAIL**;
- **B2** only after a **registered forward pass** and **a SPINE ruling that cites
  it**;
- **B1 never.**

A signal is **flow-originated** when the flow read is the reason the ticket exists.
Where a thesis stands on trend and structure on its own and flow is read afterwards,
the signal is not flow-originated and F5 does not reach it — that case is X10's,
unchanged. [Principal 2026-10-09; sharpens X10]

**How these interact with bucket-at-entry. TESTED IN THIS ORDER, and the order is
the rule:**

1. **C5 and F5 define the ELIGIBLE SET** of buckets for that signal.
2. **The principal's intent at entry chooses WITHIN that set** (TA-044; TA-045
   scope; consequence 3 above).
3. **The chosen tag is set at entry** and is not changed to fit the outcome.

**These do not compete, and reading either as the whole rule breaks the other.** A
ceiling the intent could override would not be a ceiling. An intent the ceiling
replaced would make every before-the-turn ticket a B3 by default, including the ones
meant as TAIL — and B3 and TAIL are very different tickets: B3 carries a mechanical
stop, a same-day close and a concurrency limit; TAIL carries none of those and is
X4-exempt.

**Neither rule is a retagging licence.** A ticket discovered after entry to have
been before-the-turn, or to have been flow-originated, is **not** retagged down to
B3. It is recorded on the row as **entered outside its eligible set**, with the
author and the reason, exactly as TA-044 requires of any post-entry bucket note. The
breach is the record; the tag stays as entered.

**What F5 actually changes, stated precisely so it is not oversold.** X10 as written
covers B1 and B2 only, and says a trade whose entire reason is flow *does not pass*.
Against that text, F5:
- **makes B1 absolute** for a flow-originated signal — never, on Rule 16 grounds;
- **opens one narrow path to B2 that X10's text did not have**: a registered forward
  pass plus a citing SPINE ruling. Measured against a strict reading of "does not
  pass," this is a **loosening**, and it is gated on evidence rather than on
  judgment. It is named as a loosening here so nobody records F5 as a pure tightening;
- **adds nothing to B3.** B3's own definition already requires a structural PYTHIA
  value-area trigger, so F5's B3 clause restates a condition B3 already carries. It
  is a confirmation, not a new gate;
- **leaves TAIL unconditioned**, consistent with TAIL being the one tag X4 exempts
  by design.

**ROBINHOOD.** The options and tail/convexity sleeve: high-risk, high-reward plays,
lottos, and portfolio hedges against a broad correction or worse.
- **Ceiling: 10% of ALL tracked accounts combined** — FIDELITY_401A +
  FIDELITY_ROTH + ROBINHOOD — as `backend/services/sleeve_ceiling.py` implements
  it. [TA-070] Any text reading "10% of FIDELITY_ROTH + ROBINHOOD" understates the
  denominator by a whole account and is superseded.
- **At least $200 stays in cash at all times.**
- No per-trade dollar cap. **Never the whole sleeve on one trade.**

**Breakout Prop** — crypto-only, **untracked by design** (DESCOPED 2026-07-23). No
balance row exists. The committee must NOT size against it; declining to size it is
designed behaviour, not a data gap.

### § One plan, two tax locations

FIDELITY_401A and FIDELITY_ROTH are governed as **a single portfolio with a single
set of limits**, then assets are **placed** by tax treatment: highest expected
growth into the Roth, ballast and real assets into the 401(a). Limits, caps and the
real-asset ceiling apply across the pair, **not per account**. ROBINHOOD is governed
by its own sleeve ceiling and sits outside the one-plan boundary. [R-IV.729(a)]

### § Household net-direction cap — TWO TESTS, REPORTED SEPARATELY

**Leverage adjustment — RULED 2026-10-08 [R-IV.778(d)].** "Leverage-adjusted" means:
- **shares at 1x;**
- **leveraged and inverse ETFs at their stated multiple** (SOXS 3x, TSLQ **2x**,
  SRTY **3x** — all inverse);
- **options at delta-adjusted notional** — `|delta| x 100 x contracts x spot`, per
  row, signed by direction.

**THE LEVERAGE FACTOR IS A RECORDED FIELD, NOT A LOOKUP.** Any leveraged or inverse
row records its daily factor **at entry**, on the row. The factor is a property of
the instrument and **has changed at least once in TSLQ's life**, so it is recorded
rather than recalled. TSLQ −2× and SRTY −3× were confirmed by the principal
2026-10-14; a row without a recorded factor is not leverage-adjusted from memory,
it is reported as pending.

**AND A DOLLAR DELTA PUBLISHED TO AN UNDERLYING STATES ITS REFERENCE ASSET AND ITS
FACTOR** [TA-164 condition 7]. A long position in an inverse ETF has delta **+1 to
its own price**; its delta to the underlying is the factor times that, and the
factor is **not derivable from shares and price**. "Short $X of TSLA" is a claim
that cannot be computed from the position row alone. Where the factor is not
recorded, the delta is published **only against the instrument's own price**.
The instance: on 2026-10-13 TA published TSLQ as "−$1,378.80, short TSLA," silently
assuming −1×. At the confirmed −2× the figure is **−$2,908.80**.

Delta is the measure because a net-DIRECTION cap answers exactly one question: **if
the market moves 1%, which way does the household move and how far.** Only delta
answers it. The competing measures keep their own jobs and are not substituted
here: **premium at risk** governs the ROBINHOOD sleeve ceiling, **defined-risk
width notional** governs X3's max-value exit targets, and **strike notional**
governs assignment exposure under § Spread rows entered for a net credit.

A deep-OTM row marked in pennies carries a near-zero delta and therefore provides
**almost no directional offset today** — it is an option ON being short, not a
short position. **A book that looks hedged on a position list can be nearly
unhedged on a delta basis until the move starts.**

**Until the hub serves aggregate book delta** (queued at BUILD, R-IV.780(e)),
**every net-direction report states the measured subset and the count of uncounted
rows — never a total implying the whole book was measured.**

Combined short-side exposure — the FIDELITY_ROTH trading sleeve plus ROBINHOOD
hedges — is subject to both of the following. **Neither test satisfies the other,
and both are reported with their own result.** [TA-112 §3]

1. **The 2× leverage test.** Short-side exposure, leverage-adjusted, is capped at
   **2×-equivalent of the sleeve capital available to it.**
2. **The net-short floor.** **The household is never net short.** The floor is a
   roughly flat household: leverage-adjusted short-side exposure does not exceed
   long equity exposure at market.

**These can disagree while the deployment schedule is incomplete, and will.** Test
1 measures shorts against *sleeve capital*; test 2 measures them against *actual
long exposure*. With the core partly deployed and the short sleeves at full size,
test 1 can pass comfortably while test 2 fails. An agent reporting one result and
calling the cap satisfied is wrong.

**When test 2 fails, the report states the further deployment that closes it** —
73% of each tranche is equity (VTI 60 + XLU 10 + XLE 3), so the gap divided by
0.73 is the figure. The accelerator closes it faster in exactly the tape where the
shorts would be working. Above 2× the sleeves stop hedging the core and begin
cancelling and then inverting it; at 3× the household reaches net −24%.
[R-IV.730(a); two-test shape TA-112 §3]

### § Spread rows entered for a net credit

A spread row whose net entry is a **credit** records `max_loss` at or near zero
with a note that the figure is **correct by construction, not missing.** On a long
higher-strike / short lower-strike put spread entered for a credit, the long leg
fully covers the short leg and the row cannot lose. This is NOT the `max_loss`
defect above and must not be "repaired."

**The row additionally carries its short leg's assignment notional as its own
field.** Economic max loss and settlement exposure are different quantities, and
for a deep-OTM spread the assignment notional becomes reachable precisely in the
scenario the position is a bet on. The book shows both. [TA-112 §6]

### § Deployment schedule — RULED 2026-10-07 [R-IV.730(a), R-IV.734(a)]

**Six tranches, one per month.** Tranche k deploys **1/(7 − k)** of deployable cash
— 1/6, then 1/5 of what remains, through to the remainder at tranche 6. This fully
deploys by construction and absorbs cash arriving mid-schedule. A fixed sixth
measured once strands new inflows; 1/6 of the current balance each time never
completes. Over-deploying early leaves a smaller remainder, so the schedule
self-corrects and **the completion date does not move.**

**Tranche dates: 2026-10-08 (EXECUTED) · 2026-11-02 · 2026-12-01 · 2027-01-04 ·
2027-02-01 · 2027-03-01**, at **1/5 · 1/4 · 1/3 · 1/2 · all remaining**.
(2027-01-04 because 2027-01-01 is a market holiday.)

**The cash** means: all deployable cash in FIDELITY_401A, and the deployable cash
of **FIDELITY_ROTH's core half only**, per that account's definition above.
**Measured as "cash available to trade at the open of the tranche date"** — the
figure the broker displays, which avoids the settled-versus-unsettled trap when
recent sale proceeds are still in T+1.

**Good-faith violations.** In a cash account, buying with unsettled proceeds is
permitted; **selling the position bought before those funds settle is not.** No
position bought with unsettled proceeds is sold before settlement. This binds
tactical rows too: a same-day exit on a row funded by that same day's sale
proceeds is a good-faith violation, and the next session's open is clean.

**Accelerator — SPY weekly closes**, computed from the 52-week high of 781.62:
below **703.46** (−10%) double the monthly tranche; below **625.30** (−20%) deploy
25% of remaining cash at once; below **547.13** (−30%) deploy another 25% at once.
**Weekly closes, not intraday touches.** No decelerator: buying a drawdown is
mechanical, slowing on strength is a forecast.

### § Target mix and buy split

**Target mix of the fully-deployed core:**

| Sleeve | Weight |
|---|---|
| Broad index — VTI | 60% |
| Short Treasuries — SHV | 24.3% |
| Satellite — XLU | 10% |
| Broad commodity — PDBC | 2.7% — suspended, see below |
| Energy — XLE | 3% |

**Real assets = PDBC 2.7 + XLE 3 = 5.7%**, against the 15% limit — 38% used.
Utilities and other non-real-asset sectors count against the separate 10%
satellite cap.

**Buy split for every remaining tranche — PDBC is bought in NO tranche:**

| VTI | SHV | XLU | XLE |
|---|---|---|---|
| **60** | **27** | **10** | **3** |

Sums to 100. **SHV carries PDBC's suspended 2.7 points on top of its own 24.3.**
**Do NOT renormalise the four sleeves proportionally.** Renormalising to 97.3%
gives VTI 61.67 and lifts broad equity 1.67 points above its ruled weight — a
direction change arriving as housekeeping. The residual is assigned to SHV
specifically so the suspension stays direction-neutral and reversible by one
trade. With PDBC fixed in shares, this split converges the core to
60/27/10/3 as PDBC's weight decays, which is the designed outcome.
[TA-112 §5, adopted R-IV.765(c)]

### § Gold — UNAVAILABLE in both Fidelity accounts

**Every mainstream gold-bullion ETF is a grantor trust**, not a '40-Act registered
fund — GLD, IAU/IAUM, SGOL, FGDL, GLDM. That structure is *what permits direct
physical holding*, so it is not incidental, and plan sponsors commonly exclude
commodity grantor trusts alongside LPs. **The principal confirmed on 2026-10-08
that both ...1836 and ...3158 block gold** (R-IV.762(a)).

**There is no mainstream '40-Act bullion substitute.** A registered fund cannot
hold physical metal directly at scale; it holds futures through a Cayman
subsidiary, which is what PDBC already does. The '40-Act options are **miners** —
forbidden as a gold substitute, bullion +5.77% against GDX −69.14% in 2008 — or
**broad commodity funds**, already in the mix.

**SHV is the standing substitute and absorbs gold's former 7%.** On the sourced
record this costs almost nothing: gold wins 2008 by 2.9 points, SHV wins 2022 by
1.7 points, and gold's +5.77% calendar year concealed a **−27% drawdown**. As
*ballast* — the job this sleeve does — SHV is the better instrument, not the
compromise.

**If the principal wants gold exposure it goes to ROBINHOOD or a taxable account**,
where grantor trusts trade freely — never a forced substitution inside the
one-plan boundary. Note that 7% of the core is roughly half the entire ROBINHOOD
sleeve ceiling, and that sleeve exists for convexity, not ballast.

**The honest caveat, recorded:** gold's real case rests on monetary disorder, a
regime none of the plan's three paths model. Its absence removes the one holding
whose argument lives outside the framework.

### § Existing holdings during the schedule

Holdings are measured against the target weights on the **fully-deployed** core,
not on the partially-deployed core, so transitional over-weights self-correct as
tranches land. Two holdings are handled explicitly:

- **PDBC — suspended at 25 shares, by the principal's choice.** Was 110 shares
  (401A 50, ROTH 60) at ~11.9% of the fully-deployed core against a 5% target. The
  principal trimmed on 2026-10-07 and **sold 85 rather than the planned 64 as a
  deliberate decision, not a slip** (confirmed 2026-10-08). **PDBC is bought in no
  tranche. The 5% target is SUSPENDED, NOT RETIRED — it reactivates on the
  principal's word and needs no new ruling to do so.** All 25 shares sit in
  FIDELITY_401A under the one-plan placement rule.
  **Its weight decays on its own.** 25 shares is a fixed count against a core that
  grows at every tranche, so the 2.7% is a recorded weight, not a maintained one,
  and the gap to a 5% target widens over the schedule without anything being sold.
- **TSLQ 80 shares** sits in the FIDELITY_ROTH trading sleeve. Not in the target
  mix; the schedule neither buys nor sells it.

### Retired, do not reinstate

- **The 40% real-asset limit.** Provisional from the outset and never derived;
  superseded by the principal's adopted **15%** on 2026-10-07. [R-IV.729(a)]
- **An unscoped 15%-per-position limit.** The limit stands, but it does not reach
  broad-market index funds or short-duration Treasuries — see its scope above.
  Applied unscoped it would have vetoed the principal's own adopted 60% index core.
- **A per-account denominator for the per-position limit.** The denominator is the
  combined core. [TA-112 §2]
- **Gold at 7% of the core.** Structurally unavailable in both Fidelity accounts;
  SHV carries the weight. Any mix listing GLDM, GLD, IAU, IAUM, SGOL or FGDL as a
  core sleeve is void, including TA-112 §2's staged draft, which never issued.
- **Renormalising the buy split across the remaining sleeves.** Superseded by the
  fixed 60/27/10/3 split above. Both the "renormalised to 95%" text and the
  "renormalised to 97.3%" figures are retired. [TA-112 §5]
- **"The governing line is the higher of the two candidates."** A misstatement of
  the strategic exit rule; "further from entry" governs. [TA-112 §1]
- **Any claim that `hub_get_portfolio_balances` is a sizing input.** It is not,
  while its repair is outstanding. The claim in the superseded v4 §5 is withdrawn.
- **Z2's inverse clause read without a timeframe qualifier.** Superseded by the
  § Z2 trend gate ruling above. [R-IV.765(d)]
- **"Fails X4 -> TAIL," and any assignment order that lets X4 choose a bucket.**
  Inverts TA-044: the bucket is set at entry and X4 tests it. Drafted in error in
  v5.2's first pass and in TA-117 §3; retired before BUILD applied either.
  [R-IV.781(b), (d)]
- **X4 computed on the traded strike's own implied volatility.** The input is ATM
  IV of the position's own expiration. [R-IV.781(c)]
- **"SECTION B is unchanged from v5.1."** It changed — it gained the X4 bullet.
  Label corrected in place 2026-10-08. [R-IV.786(b)]
- **`skills/ursa/references/equities.md` and `skills/thales/references/` as the
  homes of the thesis roster.** Neither hosts it; both rosters are inline in the
  respective `SKILL.md`. Corrected at SECTION D. [R-IV.786(b)]
- **"FIDELITY_ROTH — ONE account (Roth / 401(k) / 403(b) / BrokerageLink, …3158)."**
  Factually wrong on account identity. BrokerageLink is ...1836; the Roth is
  ...3158. Retired 2026-10-07.
- **The 2026-09-23 retirement of the separate BrokerageLink entry** ("it is part of
  FIDELITY_ROTH, not a second account") is itself **reversed**. It is a second
  account.
- **"20% portfolio risk cap — FIDELITY_ROTH only."** The cap now applies to
  tactical positions in both Fidelity accounts. Retired 2026-10-07.
- **AHRP 401A PLAN (76679) and AHRP 403B PLAN (76680) are conduits, not tracked
  accounts** — linked to the brokerage window, holding no tradable capital. Flows
  are carried **where they enter a tracked account, never at the conduit**.
  [TA-105 §1, TA-106 §2]
- **Reading a thesis label's example holdings as a statement of what the book
  holds.** They are a template. The instance: on 2026-10-09 TA said the principal
  was "positioned short duration via TLT puts," reading the example tickers in
  § Bias and Thesis Labels' Fed-hawkish entry as an inventory. **The principal had
  closed those puts at a profit**, and the book showed five closed TLT rows and
  nothing open. The book is read from the book. [TA-128, R-IV.806(c)]
- **A before-the-turn signal sized as a B1 or B2 thesis ticket.** Capped at B3 or
  TAIL by C5. [R-IV.822(c)3]
- **X10 read as silent on B3 and TAIL.** It is silent on them in its own text, which
  is why F5 states the ceiling across all four tags rather than leaving the two
  smallest unconditioned. [R-IV.822(c)4]
- **The 20% tactical cap stated without its measurement basis.** Written for years
  as "20% tactical" with no numerator basis. Harmless while every tactical row was
  unleveraged; on 2026-10-14 the same two rows read 18.78% and 44.57% depending on
  the reading. The basis is market value, ruled by the principal 2026-10-14.
  [R-IV.1031(a)]
- **Applying the net-direction cap's leverage adjustment to the 20% tactical cap,
  or the tactical cap's market-value basis to the net-direction cap.** They measure
  different things deliberately. [R-IV.1031(a); R-IV.778(d)]
- **A leverage factor recalled rather than read from the row.** TSLQ's factor has
  changed at least once. TA published TSLQ as "short $1,378.80 of TSLA" on
  2026-10-13 assuming −1×; the confirmed factor is −2× and the figure is −$2,908.80.
  [TA-164 condition 7]
- **Determining a row's debit/credit orientation by substring-matching
  `structure`.** `vertical`, `three_leg`, `iron_condor`, `put_spread`, `stock` and
  `long_single` state no orientation; an iron condor is normally a credit. Exact
  match against DEBIT_WHITELIST, everything else UNDETERMINED. [TA-168 §1]
- **Reading C5 or F5 as a substitute for the principal's intent at entry.** They
  bound the eligible set; the intent chooses inside it. Both run, in that order.
- Previously retired and still retired: "Fidelity Roth IRA — inverse ETFs only";
  ROBINHOOD's "5% max risk per trade"; "max 3 contracts".
```

---

## SECTION B — the dependent rule lines

**Replacing the corresponding bullets under `§ Shared Hard Rules → Rules for agents that recommend trades`.**

```markdown
- **Sizing is governed by the ROBINHOOD sleeve ceiling** (§ Account Context) —
  **10% of all three tracked accounts combined (FIDELITY_401A + FIDELITY_ROTH +
  ROBINHOOD)**, with a $200 cash floor — not by per-bucket dollar caps. The B2
  $200–300 cap and the B3 $100 cap are **retired** as of 2026-09-23. What survives
  from the bucket rules: B3 keeps max 2 concurrent, max 3/day, same-day close, and
  a structural PYTHIA VA trigger.

- **20% portfolio risk cap — tactical positions in BOTH Fidelity accounts.** Sum of
  max losses across open **tactical** positions must not exceed 20% of the account
  holding them, measured **at market on both sides** (TA-101 §1) and computed from
  current market value rather than from any `max_loss` field (TA-102 §5) — except
  a spread entered for a net credit, whose near-zero figure is correct by
  construction (§ Spread rows entered for a net credit). **FIDELITY_401A strategic
  holdings sit outside this cap**, governed instead by the 15% real-asset limit,
  the scoped per-position limit on a combined-core denominator, and the strategic
  exit rule (TA-098 §§1–4, R-IV.729(a), R-IV.735, TA-112 §2). ROBINHOOD is
  governed by its sleeve ceiling instead, not by this cap. DAEDALUS enforces at
  structure proposal; URSA surfaces in portfolio coherence check; PIVOT vetoes via
  DON'T TRADE if a new position would push the book over.
  **Where the account value is unavailable, the agent publishes the numerator at
  market and the break-even account value that would satisfy the cap, and says the
  denominator is pending from the broker app.** It does not substitute a hub
  balance. [TA-112 §3]
  **BASIS AND LEVEL — RULED by the principal 2026-10-14 [R-IV.1031(a)].** The
  numerator is **market value** of tactical positions; **leveraged and inverse
  products count at market value, NOT underlying-equivalent.** The cap is
  **REMINDER-level: surface the percentage when crossed, never block, never veto.**
  It is recomputed on **every idea pass** and on **every position write in either
  Fidelity account**, with a NULL `classification` counting as TACTICAL
  provisionally [R-IV.1034(b)]. **Do not apply the household net-direction cap's
  leverage adjustment here** — the two caps measure differently on purpose
  (§ The 20% tactical cap).

- **Household net-direction — report BOTH tests, separately.** The 2× leverage test
  and the net-short floor are independent, can disagree during a partially-deployed
  schedule, and neither satisfies the other. A single result is not a verdict. When
  the net-short floor fails, state the further deployment that closes it.
  [§ Household net-direction cap; TA-112 §3]

- **X4's implied-volatility input is the ATM implied volatility of the position's
  own expiration — RULED 2026-10-08 [R-IV.781(c)].** Not the traded strike's own
  IV. Under skew an OTM strike's IV is elevated, so using it is circular: the more
  expensive the tail protection, the more "reachable" X4 would judge the strike,
  and the rule would loosen exactly where it should bind. X4 asks whether **the
  underlying** can plausibly travel to break-even; the market's answer is the ATM
  term structure. The agent names the strike it read ATM from.
  **X4 tests the bucket, it does not choose it** (§ Buckets, TA-044): a FAIL on a
  non-TAIL ticket is recorded as a FAIL, never resolved by retagging to TAIL.

- **Z2 returns one of THREE results, not two:** PASS, FAIL, or **NOT EVALUABLE**.
  NOT EVALUABLE is returned for any row whose justifying timeframe the hub cannot
  read — today, every intraday row. It is not a FAIL and not a pass. The next-
  session's-close clock applies regardless. [§ Z2 trend gate]

- **X10 — flow confirms, it does not originate. WITH ITS CEILING, RULED 2026-10-09
  [R-IV.822(c)4].** On B1 and B2 trades, an options-flow read may only *confirm* a
  thesis that already stands on trend and structure. A trade whose entire reason is
  "there was flow" is Rule 16 — short-term information flow mistaken for an edge —
  and does not pass.
  **A flow-ORIGINATED signal — one where the flow read is the reason the ticket
  exists — is capped as follows: B3 with a PYTHIA value-area trigger; or TAIL; or
  B2 only after a registered forward pass AND a SPINE ruling that cites it; B1
  never.** The ceiling bounds the eligible set; the principal's intent at entry
  chooses within it, and the tag is then set at entry (§ Bucket ceilings by signal
  provenance). Where a thesis stands on its own and flow is read afterwards, the
  signal is not flow-originated and only X10's first paragraph applies.

- **C5 — a signal that fades a move BEFORE the trend breaks is capped at B3 or TAIL.
  RULED 2026-10-09 [R-IV.822(c)3].** "Breaks" is the 2026-09-23 definition: a daily
  close through the 50-day average, the average stack turning, and volume
  confirming. Before all three, the signal is before-the-turn however strong it
  looks, and B1 and B2 are unavailable to it.
  **A before-the-turn SHORT carries the no-fly flag "entering parabolic shorts too
  early" on its face** — in the proposal and on the row. The flag is not a veto; it
  is a disclosure, and an agent that omits it has not met the rule.
  **A ticket found after entry to be before-the-turn is NOT retagged to B3.** It is
  recorded as entered outside its eligible set, with author and reason. The tag is
  still set at entry.

- **A thesis label's example holdings are a TEMPLATE, never an INVENTORY — TA-128,
  adopted 2026-10-09 [R-IV.806(c)].** The tickers in each entry of § Bias and
  Thesis Labels describe *how a thesis is typically expressed*. They are not a
  claim that the household holds them. **No agent states, implies or sizes from a
  position because a label names it.** What the book holds is read from the book —
  POSITIONS, or `hub_get_positions` — in the same turn as the claim, and a row the
  book does not carry as open is not carried as open anywhere else.
  **This cuts both ways:** a label the book no longer supports is also a label to
  re-check, and an agent reciting a label's tickers as the current book will report
  a thesis the principal has already exited.
  The instance it was ruled on is in § Account Context's retired list.
```

---

## SECTION C — `COMMITTEE_RULES.md § Bias and Thesis Labels`

**Two inserts. The note goes at the HEAD of the label list, before the first
label; the bullet goes after the Fed-hawkish bullet. Neither replaces an existing
label.**

**C1 — the lead-in note, at the head of the label list [TA-128, R-IV.806(c)]:**

```markdown
**The holdings named in each label below are a TEMPLATE, not an INVENTORY.** They
describe how a thesis is typically expressed. They are not a claim that the
household holds them, and no agent may state, imply or size from a position
because a label names it. **What the book holds is read from the book** —
POSITIONS, or `hub_get_positions` — in the same turn as the claim. A label whose
example tickers the book no longer carries is a label to re-check, not a position
to report. [TA-128]
```

**C2 — the credit-stress label, after the Fed-hawkish bullet:**

```markdown
- **Credit-stress thesis.** Short regional banks (KRE), short high-yield credit
  (HYG), short private-credit and alternative-asset managers (BX, TRIN, APO,
  ARES), short rate-sensitive financials (XLF). Long short-duration cash
  equivalents as the offset. Macro tells: HY spreads widening against IG,
  regional-bank deposit flight or CRE marks in the headlines, private-credit NAVs
  questioned or gated, KRE underperforming XLF, bank-term-funding usage rising.
  **Distinct from Fed-hawkish, and the two can run opposite.** Fed-hawkish is
  driven by the policy rate - long duration and rate-sensitives fall together as
  yields rise. Credit-stress is driven by the credit cycle, and a cut *into* a
  credit event helps duration while credit keeps widening. A book short both TLT
  and HYG is expressing two theses, not one; label it by whichever leg carries the
  size. Approved by the principal 2026-10-08 [R-IV.778(e)].
```

---

## SECTION D — the agent-file updates SECTION C requires

**Per § Bias and Thesis Labels' own instruction — "add it here first, then update
URSA and THALES references" — SECTION C lands before these.**

**Both targets were named wrongly in the first draft of this section, which said
`skills/ursa/references/equities.md` and `skills/thales/references/`.** The files
were opened and neither hosts the label roster: **URSA's list is inline in
`SKILL.md`, and THALES's WORLD-CHECK is inline in `SKILL.md`** with
`references/world-check-example.md` holding only a worked example. R-IV.786(b)
caught the directory-versus-file problem; opening the files found that both paths
were also the wrong files. **Four insertion points, not two.** [R-IV.786(b)]

### D1 — `skills/ursa/SKILL.md`, the inline thesis list at lines 38-40

Add as a fourth bullet, matching the existing one-line style:

```markdown
   - **Credit-stress thesis:** Short regional banks (KRE), short high-yield credit (HYG), short private-credit and alternative-asset managers (BX, TRIN), short rate-sensitive financials (XLF), long short-duration cash equivalents.
```

And in the THESIS GROUPING guidance, so the grouping check can reach it:

```markdown
- **Credit-stress.** Does the book hold short exposure across at least two of:
  regional banks, high-yield credit, private-credit or alternative-asset
  managers, rate-sensitive financials? If so the grouping is credit-stress, not a
  bias stack - check it before reaching for "Pure macro-bearish." The tell that
  separates it from Fed-hawkish: credit-stress books are short HYG or short
  private-credit names, which a rates thesis does not require.
```

### D2 — `skills/thales/SKILL.md` line 160, the WORLD-CHECK step-1 roster

That line reads "currently: Iran-escalation, AI-bubble-deflation, Fed-hawkish,
**trend-continuation**, Pure macro-bearish bias stack". **Add credit-stress:**

```markdown
1. **Identify the inferred thesis** (same classification labels URSA uses; canonical definitions and macro tells live in `_shared/COMMITTEE_RULES.md § Bias and Thesis Labels` — currently: Iran-escalation, AI-bubble-deflation, Fed-hawkish, **credit-stress**, **trend-continuation**, Pure macro-bearish bias stack).
```

### D3 — `skills/thales/SKILL.md` lines 162-164, the world-support tells

Add as a fourth tell, matching the existing style:

```markdown
   - Credit-stress thesis: HY spreads widening against IG, regional-bank deposit flight or CRE marks in the headlines, private-credit NAVs questioned or gated, KRE underperforming XLF, bank-term-funding usage rising → world supports thesis.
```

**And the discriminating line, because this label is the one that can be confused
with its neighbour:**

```markdown
   - Credit-stress vs Fed-hawkish: read HY-minus-IG spreads, not the 10-year. A widening spread with a FALLING 10-year supports credit-stress and *contradicts* Fed-hawkish; both rising supports Fed-hawkish; spreads tight with equities at highs supports neither, and the book is early rather than wrong — say which.
```

### D4 — `skills/thales/SKILL.md` line 184, a roster that is ALREADY STALE

That line's cross-reference reads "currently: Iran-escalation,
AI-bubble-deflation, Fed-hawkish, Pure macro-bearish bias stack" — **it omits
`trend-continuation`, which line 160 already carries.** The drift predates this
label. Fix both omissions in one edit:

```markdown
> Cross-reference: URSA runs a parallel THESIS GROUPING that classifies whether the existing book is coherent or bias-aligned. THALES reads the WORLD; URSA reads the BOOK. PIVOT's dual-flag gate requires both agents to flag BIAS-ALIGNMENT before the verdict is capped. See `_shared/COMMITTEE_RULES.md § Bias and Thesis Labels` for the canonical label set (currently: Iran-escalation, AI-bubble-deflation, Fed-hawkish, credit-stress, trend-continuation, Pure macro-bearish bias stack).
```

### D5 — a recommendation, not an edit

**The roster is enumerated in four places** — `COMMITTEE_RULES § Bias and Thesis
Labels`, `ursa/SKILL.md` 38-40, `thales/SKILL.md` 160, and `thales/SKILL.md` 184
— so every new label needs four edits. **That is why line 184 is already a label
behind**, and § Bias and Thesis Labels warns about exactly this: "Don't let labels
drift across agent files."

Each of those four sites already cites the shared list **in the same sentence as
its own copy.** **Recommendation: delete the enumerations and keep the citation.**
Then a new label is one edit, in one file, and cannot drift. TA is not making that
change — it touches agent files outside § Account Context and is SPINE's call — but
D4 is the second-order cost of not making it.

**Why this label exists.** Five rows — KRE 981, HYG, BX, XLF 978, XLF 300 — form a
coherent credit book. With no label covering it, the only remaining option on the
canonical list was *"Pure macro-bearish bias stack… no thematic coherence"*, the
stated failure mode. The BIAS-ALIGNMENT flag would have fired on a coherent book
because the list had a hole — the same defect that prompted the Trend-continuation
label under Z6.

---

## SECTION E — the seat updates C5 and F5 require

**Five seats cite X10 or the B3/TAIL rule. All five were opened at 2026-10-09; each
edit below names the line it attaches to.** SECTION D's two targets
(`ursa/SKILL.md`, `thales/SKILL.md`) are separate and unchanged, so the package
touches six agent files in total — URSA appears in both sections, at different
lines.

### E1 — `skills/pivot/SKILL.md` line 199, the PIVOT-specific addendum

That line enumerates what PIVOT enforces from § Shared Hard Rules: the sleeve
ceiling, B3's limits, the circuit breaker, the $300 daily cap, and the DON'T TRADE
veto. **Add the two ceilings, because PIVOT is the seat that vetoes:**

```markdown
PIVOT-specific addendum: PIVOT enforces the sizing rules from § Shared Hard Rules — the **ROBINHOOD sleeve ceiling** (the B2/B3 dollar caps are retired), B3's max 2 concurrent / max 3/day / same-day close, the B3 circuit breaker, and the $300 daily max loss cap. **PIVOT also enforces the two bucket ceilings by signal provenance (§ Account Context): C5 — a before-the-turn signal is capped at B3 or TAIL, and a before-the-turn short must carry the no-fly flag "entering parabolic shorts too early" on its face; F5 — a flow-originated signal is B3 (with a PYTHIA value-area trigger) or TAIL, B2 only on a cited SPINE ruling, B1 never.** If a sizing recommendation from DAEDALUS would breach the sleeve ceiling or the 20% FIDELITY_ROTH cap, **or would place a signal in a bucket its provenance does not permit**, PIVOT issues DON'T TRADE. **A missing no-fly flag on a before-the-turn short is itself a DON'T TRADE until the flag is stated** — the disclosure is the rule, not a courtesy.
```

### E2 — `skills/daedalus/SKILL.md`, two lines

**Line 158**, the one-line cross-reference, currently ends "...X7 max-loss, X10
flow-confirms". Extend it:

```markdown
See `_shared/COMMITTEE_RULES.md § Shared Hard Rules` for universal committee rules (no fabrication of tape-anchored output, web_search precedence, no simulating other agents, no hardcoded dollars, the ROBINHOOD sleeve ceiling, X3 exits, X4 reachability, X7 max-loss, X10 flow-confirms **and its flow-origination ceiling, C5's before-the-turn ceiling**).
```

**Line 219**, the structure checklist, currently reads "X4 reachability: break-even
within 1.5x the implied expected move (every bucket except TAIL)". Add a line
beneath it, because DAEDALUS picks the structure and the ceiling decides which
structures are even available:

```markdown
- Bucket ceiling by provenance: before-the-turn → B3 or TAIL only (C5); flow-originated → B3 with a PYTHIA VA trigger, or TAIL, B2 only on a cited SPINE ruling, B1 never (F5). Name the provenance when proposing the bucket, the same way the TAIL exemption must be named.
```

**Why DAEDALUS gets the checklist line and not only the cross-reference.** The
ceiling changes the structure, not just the size. B3 carries a mechanical stop and a
same-day close; TAIL is X4-exempt. A signal capped at those two cannot be expressed
as a 30-60 DTE spread at all, so the ceiling has to be read **before** the structure
is chosen, not after.

### E3 — `skills/toro/SKILL.md` line 127, the cross-reference

Same extension as E2's line 158, in TORO's wording:

```markdown
See `_shared/COMMITTEE_RULES.md § Shared Hard Rules` for universal committee rules (no fabrication, web_search precedence, no simulating other agents, no hardcoded dollars, the ROBINHOOD sleeve ceiling, X3 exits, X4 reachability, X7 max-loss, X10 flow-confirms **and its flow-origination ceiling, C5's before-the-turn ceiling**).
```

**No second edit for TORO, and the reason is worth recording.** TORO line 135
already says "Never recommend B3 entries without a Pythia VA-based structural
trigger." **F5's B3 clause is therefore already satisfied in TORO's file** — which
is the same point SECTION A makes about F5 adding nothing to B3. One line of the new
rule was already enforced before it was written.

### E4 — `skills/ursa/SKILL.md`, two lines

**Line 173**, the cross-reference, as E3.

**Line 142**, the SIZING SUGGESTION template. **URSA is the seat that surfaces
shorts, so URSA is where the no-fly flag has to appear or it will not appear at
all:**

```markdown
SIZING SUGGESTION: [If recommending a short, B1/B2/B3 bucket fit and specific sizing. **State the signal's provenance: with-trend, confirmed-turn, or before-the-turn. A before-the-turn short is capped at B3 or TAIL (C5) and MUST carry the no-fly flag "entering parabolic shorts too early" in this block — not in a footnote.** If URSA's strongest read is "don't enter this long here," state that explicitly instead.]
```

### E5 — `skills/pythia/SKILL.md` line 83 — and a finding

**PYTHIA is named inside F5's mechanism** — the B3 path exists only "with a PYTHIA
value-area trigger" — **but PYTHIA's cross-reference line names none of the hard
rules it is now a gate for.** Line 83 reads: "...(no fabrication of tape-anchored
output, web_search precedence, no simulating other agents, no hardcoded dollars)."
Four universal rules, and nothing about buckets.

That is defensible as it stands: PYTHIA does not recommend trades, and § Shared Hard
Rules says non-recommending seats "do not need to enforce the trade-sizing rules."
**But F5 makes PYTHIA's trigger load-bearing for a bucket ceiling**, and a seat that
supplies a gate without knowing it is a gate cannot tell when its read is being used
as one. Minimum edit:

```markdown
See `_shared/COMMITTEE_RULES.md § Shared Hard Rules` for universal committee rules (no fabrication of tape-anchored output, web_search precedence, no simulating other agents, no hardcoded dollars). **PYTHIA does not size trades, but its value-area trigger is load-bearing for two rules that others enforce: B3's structural trigger requirement, and F5's B3 path for a flow-originated signal. When a value-area read is requested as a B3 or flow-signal trigger, say plainly whether the level qualifies as a structural trigger or merely as nearby context — the distinction decides a bucket.**
```

**TA flags, does not rule:** whether PYTHIA should cite the bucket rules more fully
is SPINE's call, not TA's, and the edit above is the narrowest version that closes
the gap. [TA-136]

### E6 — a note on rule numbering, NOT an edit

C5 and F5 are **decision IDs from the 2026-10-09 double pass**, not rule numbers in
the X-series. SECTION B labels them as such. **TA has not minted X11 or X12**, because
the X-series is the committee's namespace and numbering in it is SPINE's to do. If
SPINE wants them as X-numbers, that is a one-line relabel in SECTION A and SECTION B,
and it needs a version bump under R-IV.791(b) because BUILD reads both as
instructions.

---

## Provenance — what came from where

| Element in SECTION A / B | Source |
|---|---|
| Balance sourcing, three accounts, cap structure, Roth 50/50, Robinhood ceiling, one plan, schedule, accelerator, conduits | Part 4 v2 (2026-10-07/v2), unaltered |
| Per-position limit scope | Part 4 v2 §1, confirmed by the principal 2026-10-07, R-IV.735 |
| Per-position limit denominator = combined core | TA-112 §2 |
| Gold unavailable → SHV substitute | v3 §1, extended by R-IV.762(a) to both accounts |
| Strategic exit rule, ballast and below-SMA cases | v3 §2(a), v3 §2(b) |
| Case precedence (ballast dispositive) and case 2 enumerated | TA-115 §1 |
| "Further from entry," 3×ATR as a floor | TA-112 §1 |
| Per-row anchoring; execution record over market data | TA-109 |
| All candidates published, governing one named | TA-110 §7 |
| PDBC suspended at 25 shares; residual to SHV; weight decays | v4 §1 |
| XLU entries 40.9560 / 40.9660; stops 39.07 / 39.08 | v4 §2, TA-109 |
| Buy split 60 / 27 / 10 / 3 | TA-112 §5, adopted R-IV.765(c) |
| Net-direction as two separate tests | TA-112 §3 |
| Net-credit spread rows; assignment notional field | TA-112 §6 |
| Z2 trend gate, three results, next-session clock | Ruled by the principal, R-IV.765(d) |
| § Buckets — B1/B2/B3 text | `skills/ursa/references/equities.md` L49 and `skills/toro/references/equities.md` L46, verbatim |
| § Buckets — TAIL's exemption | X4, `COMMITTEE_RULES.md` L378 |
| § Buckets — B1 as a horizon; B2's inoperative-time-stop case | TA-117 §§1, 2a |
| Net-direction leverage adjustment (delta-adjusted notional) | Ruled by the principal, R-IV.778(d), on TA-116 §6 |
| SECTION C — CREDIT-STRESS label | Approved by the principal 2026-10-08, R-IV.778(e); drafted TA-117 §4 |
| SECTION D — URSA/THALES agent-file updates | TA-117 §4; targets corrected to `ursa/SKILL.md` and `thales/SKILL.md` after opening both, R-IV.786(b) |
| § Buckets — TA-044, bucket-at-entry, CONVEXITY | `docs/trading-theses.md` TA-044 (R-IV.531(b)), supplied verbatim R-IV.781(b); scope TA-045 |
| X4's IV input = ATM of the position's own expiration | Ruled by the principal, R-IV.781(c), on TA-117 §2 |
| SECTION B / SECTION C — label holdings are a template, not an inventory | TA-128, adopted R-IV.806(c); cause recorded in SECTION A's retired list |
| § Bucket ceilings by signal provenance — C5 | Principal 2026-10-09, relayed R-IV.822(c)3; drafted from 09-23 collision #3 and the double pass C5 row |
| § Bucket ceilings by signal provenance — F5 | Principal 2026-10-09, relayed R-IV.822(c)4; drafted from the double pass F5 row, PYTHIA Y1-3 and DAEDALUS D1-3 |
| C5's definition of "breaks" | the 2026-09-23 definition, quoted via R-IV.822(c)3: daily close through the 50-day average, stack turning, volume confirming |
| The no-fly flag's wording | the principal's behavioural no-fly list, quoted via R-IV.822(c)3 |
| X10's existing text, quoted before extension | `COMMITTEE_RULES.md` L586, opened 2026-10-09 |
| SECTION E — the five seat insertion points | `pivot/SKILL.md` L199, `daedalus/SKILL.md` L158 and L219, `toro/SKILL.md` L127, `ursa/SKILL.md` L173 and L142, `pythia/SKILL.md` L83 — all opened 2026-10-09 |
| § The 20% tactical cap — basis and REMINDER level | Principal 2026-10-14, relayed R-IV.1031(a); the 18.78% / 44.57% divergence measured by TA the same day |
| § The 20% tactical cap — the two triggers | R-IV.1034(b); TA-171's open question on a reminder with no firing mechanism |
| Leverage factor as a recorded field; SRTY −3×, TSLQ −2× | Principal 2026-10-14; TA-164 condition 7 |
| Delta to an underlying states reference asset and factor | TA-164 condition 7, written after TA's own −1× assumption was corrected |
| DEBIT_WHITELIST, exact match | TA-168 §1, adopted R-IV.1021(a) |
| **NOT written in** | C1, the program goal — SPINE owns it and ruled it is not rules text [R-IV.822(c)1]; N4, the Nemesis naming — a registry fact, LAB's to card |
| **Retired as an error** | "fails X4 -> TAIL" — inverted TA-044; drafted in v5.2's first pass and TA-117 §3, removed before any apply |
| **Retired as an error** | TA's TSLQ delta published to TSLA on an assumed −1× factor; the factor is −2× and the figure doubled [TA-169 §4] |
| **Retired as an error** | reading a label's example holdings as the book — TA said "positioned short duration via TLT puts" on 2026-10-09; the principal had closed them at a profit [TA-128] |
| **Dropped, not carried** | v4 §5's balances claim — withdrawn at TA-112 §4 |
| **Void, never issued** | TA-112 §2's staged gold mix — R-IV.762(a) |

---

## For BUILD

**FIVE blocks, all verbatim, all drop-in. Apply to all eight rule copies.**
**This version CONTAINS v5.4, and v5.3 within it. Do not apply either separately — applying both would
double-insert SECTION C's note and SECTION D's four points.**

| Block | Target | Action |
|---|---|---|
| **SECTION A** | `## § Account Context Framework` | replace in full — carries the authoritative `RULES VERSION` line as its first line. **CHANGED from v5.4:** new `§ The 20% tactical cap`; DEBIT_WHITELIST under § Buckets' B2 bullet; leverage-factor and condition-7 text in § Household net-direction cap; four retired-list entries |
| **SECTION B** | the matching bullets under `## § Shared Hard Rules → Rules for agents that recommend trades` | replace; **CHANGED from v5.3 — AND ITS RANGE GREW.** It now also replaces **X10's own bullet** (L586 in the pre-apply file), which v5.3 did not touch, and adds the new **C5** bullet after it. X10's line sits immediately after the Z2 bullet, so the replacement set is still contiguous. Also carries, from v5.3, the TA-128 bullet, and from v5.1 the X4 implied-volatility bullet |
| **SECTION C** | `## § Bias and Thesis Labels` | unchanged from v5.4. **CHANGED from v5.2** — now TWO inserts: the C1 note at the HEAD of the label list, then the C2 bullet after Fed-hawkish; replaces nothing |
| **SECTION D** | `skills/ursa/SKILL.md`, `skills/thales/SKILL.md` | unchanged from v5.4 and v5.3 — insert at the four points D1–D4; apply AFTER SECTION C per that section's own ordering instruction |
| **SECTION E** | `skills/pivot/SKILL.md`, `skills/daedalus/SKILL.md`, `skills/toro/SKILL.md`, `skills/ursa/SKILL.md`, `skills/pythia/SKILL.md` | unchanged from v5.4, where it was **NEW.** Seven line edits at E1–E5; E6 is a note, not an edit. **URSA is touched by SECTION D and SECTION E at different lines — apply both.** |

**Nothing else needs merging** — v2, v3, v4, v5, v5.1, v5.2 and TA-112 §5 are all
inside these blocks. Mark v2, v3, v4, v5/v5.1, v5.2, v5.3 **and v5.4** superseded at their own
paths so a task resolving to one of them fails loudly. **The stamp to read is the
one inside SECTION A**, which survives a verbatim apply.

**SECTION A and SECTION B must be applied together.** SECTION A carries C5's and
F5's canonical text; SECTION B carries the bullets that enforce them and cites
SECTION A by section name. B alone leaves two bullets pointing at a sub-section that
is not there; A alone leaves the rules unenforced by any seat.

**The SECTION D path correction is the reason v5.3 was a version and not an edit to
v5.2.** v5.2's SECTION D prose already carried the right paths; only the summary
table above was stale. Fixing a table BUILD reads as instructions, under an
unchanged stamp, is exactly what R-IV.791(b) forbids — a reader who had verified
v5.2's hash would have been holding a different document.

## Data note

Levels and indicator values quoted in the superseded documents are unchanged and
not restated here; this is a rules document and carries no live figures by design.
XLU's entries come from the execution record via POSITIONS, not from a quote.
Gold and SHV return figures trace to the allocation plan's §12 sources with that
document's caveats; the fund-structure finding rests on issuer and SEC filings for
GLD, IAU/IAUM, SGOL and FGDL, and TA checked the mainstream bullion ETFs without
attempting an exhaustive survey of every registered fund with gold exposure.
Gold's unavailability in both Fidelity accounts is the principal's confirmation
(R-IV.762(a)), not a TA finding.

*TRADE ANALYSIS, 2026-10-14. v5 issued as TA-114 (R-IV.765(e)); v5.1 as TA-115 (R-IV.773(b)); v5.2 as TA-118 (R-IV.778(f)), finalised as TA-119 (R-IV.781(f)); v5.3 as TA-131 (R-IV.806(c)), carrying TA-128; v5.4 as TA-136 (R-IV.822(c)), carrying C5 and F5; v5.5 as TA-172 (R-IV.1034(c)), carrying the 20% cap's basis and triggers, the recorded leverage factor, and DEBIT_WHITELIST. Nothing executes from this document.*
