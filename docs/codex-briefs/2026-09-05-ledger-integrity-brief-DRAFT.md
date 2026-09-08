# CC BRIEF — LEDGER INTEGRITY: one account vocabulary, guarded marks, honest vintage

**Authority** R-IV.268(d), slotted 1b; **re-sequenced to position 3** by R-IV.273(d)
(grader P1/P2 → sinks + backfill → ledger integrity). **Drafts on paper in parallel**, per
the same ruling.

**Status: DRAFT. Awaiting the ATLAS/AEGIS pass at spine. NO CODE until that returns** —
same gate as the grader brief.

**Author** CC-BUILD, 2026-09-05.

---

## What this fixes, in one line

**The hub's account ledger cannot be reconciled against the broker**, because
**two tracked accounts plus parked out-of-scope money were mistaken for a third account**
(R-IV.284), the parked sum is added into every aggregate, the tracked account carries
several names across code, and the marks that price the positions are written without a
guard.

## Binding conditions

- **Committee sizing uses broker figures, never hub balances, until acceptance**
  (R-IV.268(d)). **This brief does not lift that.** Only the Trade Analysis acceptance in
  D-final does, and nothing in Phase 0 or T1–T7 may be read as lifting it early.
- **No hard deletes, anywhere in this build.** IB's 90 orphan snapshot rows are **marked
  retired** (R-IV.271(e)). A row that is wrong is evidence; a row that is gone is not.
- **Broker exports are never committed.** The GitHub repo is PUBLIC.
- **No manual SQL against prod.** Migrations are code, reviewed, and reversible.
- **The account number is never written into an artifact.** It reached a public commit once
  already (register item S4); a content scan that looks only for keys and DSNs does not
  catch an account identifier.

## Phase 0 — measurement before any write

**Nothing in T1–T7 starts until Phase 0 returns.** Each item states who supplies it,
because half of it is not this lane's to measure.

### P0.1 — Alias census

**POSITIONS supplies the six-surface census** (the DB side). **The code side is measured
below** — CC-BUILD, 2026-09-05, read at `fda9224`, and it is worse than "casing drift":
**the surfaces disagree on the third account's NAME, not merely its form.**

| surface | third account is called | form |
|---|---|---|
| `init_database()` seed, `postgres_client.py:970-995` | **`Fidelity 401A` AND `Fidelity 403B`** — two separate rows — plus `Interactive Brokers` | Title Case, spaces |
| `_DB_TO_NORMAL`, `hub_mcp/tools/portfolio_balances.py:35` | **`BROKERAGE_LINK_401K`** | UPPER_SNAKE, **lowercased on output** |
| `_CANONICAL_ACCOUNTS`, `unified_positions.py:2572` | **`FIDELITY_401A`** | UPPER_SNAKE |
| `ACCOUNT_DISPLAY_MAP`, `unified_positions.py:63` | **`FIDELITY_401A`**, plus a `FIDELITY` legacy fallback | UPPER_SNAKE + free-text aliases |
| `hub_mcp/tools/positions.py:48-49` | `brokerage_link_401k` | lower_snake |

**Two surfaces call it `BROKERAGE_LINK_401K` and two call it `FIDELITY_401A`.** Per
R-IV.268(a) the Roth IRA and the 401k BrokerageLink are **ONE account**, so the correct
collapse target is **two canonical accounts**, not three.

> **ANSWERED — R-IV.275(e)(3), then CORRECTED BY R-IV.284 BEFORE ANY CODE. Read the
> correction, not the first answer.**
>
> **PRINCIPAL FACT (R-IV.284(a)):** Pandora tracks **exactly two accounts** — `FIDELITY_ROTH`,
> the Roth 401k BrokerageLink and **the account actually traded**, and `ROBINHOOD`,
> high-risk: options primarily, with crypto, ETFs and stocks at times. **The 401A and 403B
> balances are PARKED MUTUAL-FUND MONEY, untraded, OUT OF SCOPE.**
>
> **THE CORRECTION MATTERS AND IS NOT COSMETIC.** R-IV.275(e)(3) called the
> `BROKERAGE_LINK_401K` row a **stale vintage of the same account**. It is not. **It is the
> PARKED SUM under a misleading name** — `$11,642.35`, exactly 401A + 403B. **A
> different pot, not an older reading of the same pot.**
>
> **Same action, different reason, and the reason is what the build encodes.** Retire it
> from every aggregate — **because it is other money, not because it is old.** A
> staleness-based fix would have been *refreshed* by a diligent future maintainer; a
> scope-based one cannot be, because there is nothing to refresh it to.
>
> **ALIAS MAP, corrected (R-IV.284(c)):** aliases of `FIDELITY_ROTH` = `{FIDELITY}`.
> **OUT-OF-SCOPE retired labels** = `{FIDELITY_401A, FIDELITY_403B, BROKERAGE_LINK_401K, Interactive Brokers}`. **These are
> not aliases of anything.** Rows carrying them are tagged `OUT_OF_SCOPE` and preserved
> under the retention law — **never deleted, never summed, never charted with the trading
> account.**

**A second defect found in the same read, not previously registered.**
`_match_account_balance` (`unified_positions.py:71-78`) matches by **`startswith`**, and
the legacy `FIDELITY` filter normalises to the prefix `fidelity` — which matches
**`Fidelity Roth`, `Fidelity 401A`, and `Fidelity 403B` alike**. A filter that silently
matches three accounts when asked for one is the vacuous-predicate family, and it is
load-bearing on a money surface. **Register it before T2 touches this function.**

### P0.2 — The trades case-split

**POSITIONS supplies.** Pairs with the lowercase-on-output facet already filed on
`DEF-ACCOUNT-LABEL-DUP`: the hub renders account strings lower-case while the stored values
are UPPER-CASE, so a predicate copied from a tool rendering matches **zero rows, silently**.
The census must state, per surface, **which case is stored and which is displayed** —
these are different questions and conflating them is how the trap was built.

### P0.3 — `balance_snapshots`: three-series history and its merge rule

**POSITIONS supplies the history. R-IV.284(d) RULES THE HISTORY RULE: NO MERGE.**

`balance_snapshots` keeps the **Fidelity Roth series as the trading account's history.** The
401A, 403B and IB series are **flagged out-of-scope and excluded from every chart and every
aggregate** — not merged into it, not reconciled against it.

**This supersedes the merge rule as the CROSS-ACCOUNT question**, and it supersedes it in
the strongest way: the question does not arise. Two series belonging to different pots were
never candidates for merging, and the earlier rule was answering a question about one pot
read twice.

**The R-IV.271(e) rule still governs WITHIN a series**, where two readings of the same
account on the same date genuinely can disagree:

- **same date + same value → dedupe.**
- **same date + DIFFERING values → NEVER the same measurement. Investigate; do not merge,
  do not average, do not pick the later one.**

**Averaging two disagreeing readings is the defect this rule exists to prevent** — it
manufactures a number that was never measured and destroys the evidence that they
disagreed. Two readings that disagree are a finding, not noise.

### P0.4 — IB's 90 orphan snapshot rows

**MARK RETIRED. NEVER HARD-DELETE** (R-IV.271(e)). The seed still creates an
`Interactive Brokers` row (P0.1), and `account_balances`' IBKR row was deleted once already
on 2026-07-23 — after which `DEF-SEED-RESURRECTION` showed the startup seed **re-created
deleted rows on every deploy** until an empty-table guard was added. **Retirement must be a
column, not an absence**, or the next fresh boot resurrects what this build retires.

### P0.5 — Hub vs broker, per position

**The acceptance baseline, captured BEFORE any change.** Without a pre-state there is
nothing to compare the post-state against, and the acceptance in D-final becomes
unfalsifiable — the null-verifier this board keeps removing.

## Tasks

### T1 — Guard the mark write. FIRST, before anything else.

**R-IV.271(e) orders this first and the order is load-bearing.**
`unified_positions.py:1486` executes

```
UPDATE unified_positions SET unrealized_pnl = $1 WHERE position_id = $2
```

with a value computed from `current_price` — **the mark — with no validation that the mark
is fresh, sane, or present.** Every later task in this brief reads numbers this line
writes. **Fixing the vocabulary while the marks are still unguarded produces a
well-named wrong answer**, which is harder to detect than an obviously wrong one.

Scope: `DEF-MARK-INTEGRITY` (filed at `docs/incidents/DEF-MARK-INTEGRITY.md` — **note the
directory: `incidents/`, not `defects/`**), both held facets per R-IV.252(d). Facet B arms
when the mark path restarts.

### T2 — Collapse the account vocabulary to ONE

Two canonical accounts. One name each. Every surface in the P0.1 table reads the same
constant from **one module** — not five copies that agree today.

**Case is settled once, at the boundary**, not defended at each call site: DB predicates use
the stored form or are explicitly case-insensitive, and **no account string is ever copied
out of a tool rendering into a query.**

### T3 — The CHECK constraint — and the trap it walks into

R-IV.268(c) orders a CHECK constraint on `account_balances`. **It cannot ship alone.**

**The seed inserts labels the constraint would reject.** `init_database()` inserts
`Robinhood`, `Fidelity 401A`, `Fidelity 403B`, `Fidelity Roth`, `Interactive Brokers` —
Title Case with spaces. A CHECK enumerating the canonical UPPER_SNAKE labels **rejects every
one of them.**

**Why this is latent rather than live, and why that is worse.** The seed is empty-table
guarded (`postgres_client.py:970`, the `DEF-SEED-RESURRECTION` fix), so it does not fire
against the populated production table. **It fires on a FRESH database** — a new
environment, a restore, a disaster-recovery boot — where `init_database()` would raise and
**the app would fail to start.** The failure is invisible in every normal deploy and
certain in the one case where recovery matters.

**RULED — R-IV.275(e)(1): the CHECK constraint and the seed land in ONE commit, and the
seed is rewritten to the two canonical accounts.** Spine's words: *a constraint that fails
only on recovery day is the worst possible latency.*

**AND THE CONSTRAINT ADMITS A THIRD VALUE (R-IV.286(b)): `OUT_OF_SCOPE`.**

```
account IN ('ROBINHOOD', 'FIDELITY_ROTH', 'OUT_OF_SCOPE')
```

**Two canonical accounts, one explicit not-an-account.** `OUT_OF_SCOPE` is how the parked
401A/403B/IB money is carried under the retention law — preserved, never summed, never
charted with the trading account.

**It is not a hypothetical value: `cash_flows` id 15 already carries it** (spine's fact of
record). **So a two-value constraint would fail on data that exists today**, which is the
same failure mode as the seed trap one paragraph up — a constraint written from the
vocabulary someone intends rather than the vocabulary the table holds. **Both instances
have the same cure: enumerate against the data, not against the plan.**

**The third value is what makes the retirement expressible.** Without it the only ways to
retire a row are deletion (forbidden) or a nullable side-flag that every aggregate must
remember to check — **and an aggregate that must remember is the defect this build is
closing.** A row whose account is `OUT_OF_SCOPE` cannot be summed into a tracked total by
accident, because it does not name a tracked account at all.

**Therefore: the constraint and the seed change land in the SAME COMMIT.** A constraint that
contradicts the seed is not a half-done migration; it is a boot failure waiting for the
worst possible day.

### T4 — The aggregate double-count

`portfolio_balances.py:119` sums **every** row in `account_balances`, so the duplicate
account is counted as a third. Measured live 2026-09-05: `total_balance` 21,320.13 against
9,677.78 true (**+120%**), `total_cash` 16,862.47 against 5,220.12 (**+223%**).

**Fix the aggregate AND the vocabulary.** Retiring the duplicate row alone leaves the sum
correct-by-accident and the constraint absent — which is the state it was already in for
the eighty-eight days nobody noticed.

### T5 — Column-level vintage

A cash-only write stamps `updated_at` on the **whole row**, so a hand-typed balance untouched
for 88 days reads as fresh. **No hand-typed balance wears a write timestamp.**

Two aggravations, both to be fixed with it: `is_stale` returns true for the 1.2-day rows and
the 88-day row alike, so it **cannot discriminate**; and the summary prints *"Some balances
>24h old"* for a row 88 days stale. **A phrase that stays true as the magnitude grows is a
floor, not a warning** — third instance of that family.

**AND the snapshot writer, per R-IV.275(f) — in scope here, not a separate task.**
POSITIONS measured that `balance_snapshots` **re-writes stale hand-typed values as fresh daily
points** (7 × 835.69). **Fixing column vintage without fixing the writer leaves false
history**: the row would finally admit its age while the snapshot series continues to
assert, once a day, that the value was observed that day. **A corrected present over a
fabricated past is not a fix** — and the snapshot series is what any trend, chart or
reconciliation reads.

### T6 — `max_loss` from basis, never from mark

`DEF-HUB-MAXLOSS-OPTIONS`, **widened to stock rows** (R-IV.265(e)).

> ### THE CITED INSTANCE IS **UNRESOLVED PENDING LOT HISTORY** — R-IV.309(b)
>
> **Reframed from "corrupt" on spine's ruling, and the counter-hypothesis now has an
> exact arithmetic and code confirmation. This lane's earlier "corrupt" reading is
> WITHDRAWN as the leading explanation.**
>
> **THE TWO-LOT DECOMPOSITION.** TA-003 read qty 20 @ 49.12 from the broker. The hub row
> holds 30 @ 49.9433. Those are consistent if the position is **two lots**:
>
> ```
lot 1    10 @ 51.5899  =   515.90     (earlier, higher)
lot 2    20 @ 49.1200  =   982.40     (what TA read in Activity & Orders)
blend    30 @ 49.9433  = 1,498.30     exact
> ```
>
> **THE MECHANISM, CONFIRMED IN CODE AND TO THE CENT.** `unified_positions.py:440-447` — the
> ADD-TO-EXISTING branch of `POST /v2/positions` (`create_position`, :382) — recomputes the entry as a proper weighted
> average and recomputes cost basis from it, **but scales `max_loss` BY QUANTITY ALONE:**
>
> ```
scale        = new_qty / old_qty
new_max_loss = old_max_loss * scale        # never recomputed from the new entry
> ```
>
> **So max_loss carries the FIRST LOT'S PRICE forward at the FINAL quantity.** Test:
>
> ```
first-lot max_loss 515.90  x (30/10) = 1,547.70
observed max_loss                    = 1,547.70     EXACT
equivalently  51.5899 x 30           = 1,547.70
(the other ordering, 982.40 x 30/20, gives 1,473.60 -- it does NOT match)
> ```
>
> **The match also fixes the lot ORDER**: the 10-share lot came first, the 20-share lot
> second. Only that ordering reproduces the observed number.
>
> **MECHANISM OF RECORD for stock rows, replacing the mark-derived hypothesis
> (R-IV.309(b)):** *max_loss is frozen at the first lot's price × the final quantity, and
> is never recomputed on scale-in.* `update_position` does not recompute it either — it writes
> `max_loss` only when a caller supplies one (`unified_positions.py:1407-1409`), so nothing anywhere revisits it.
>
> **DISCRIMINATOR, still owed:** the principal's **Activity & Orders** view (Trade Analysis
> holds the ask). **The prediction is specific and falsifiable: two SOXS buys, 10 @ ~51.59
> EARLIER and 20 @ 49.12 LATER.** If the view shows a single 20-share order, the two-lot
> reading fails and the corrupt reading returns.
>
> **STATE OF RECORD (R-IV.310(a)): "two lots entered, one no longer held"**, pending
> Activity & Orders. **"Corrupt row" is withdrawn.**
>
> **THE FIX (R-IV.310(a)): RECOMPUTE `max_loss` ON EVERY WRITE** — `entry x qty` for stock rows,
> the option math for option rows. **Not "scale it correctly"**: any rule that carries a
> previous value forward re-creates this defect the next time an input moves. The defect is
> not that the scaling factor was wrong — it was arithmetically right — **it is that a
> derived quantity was stored and then maintained.**
>
> **What does NOT change either way:** the row and the broker order **can both be right and
> still disagree**, because the hub holds a blended position and not its lots. That is the
> finding, and it is bigger than this row.

**A mark-derived maximum loss moves with the market, and a bound that drifts with price is
not a bound.** The error errs *safe*, which is why nobody filed it — the same asymmetry that
let the flattering half of `DEF-MARK-INTEGRITY`'s pair suppress the report the alarming half
would have caused. **An error that only ever errs safe is an error nobody files.**

### T6b — A NUMERIC STOP COLUMN HOLDS A LEVEL, NOT A RULE (R-IV.295(e))

**POSITIONS' second instance of the schema gap.** A numeric stop column can hold
`480.00`. It cannot hold *"close below 480 on a daily bar"* or *"exit by Friday if
unresolved"* — so **conditional close-stops and time stops live only in free-text notes.**

**The consequence is not that the rule is missing. It is that the rule is INVISIBLE TO
EVERY CONSUMER.** Risk math reads the number and computes a bound that the actual exit
discipline does not match; nothing errors, and the mismatch is discoverable only by a human
reading notes. **A stop that only a person can see is not a stop the system has.**

**Same family as `DEF-HUB-MAXLOSS-OPTIONS`**, where a bound is computed off a mark instead of basis: in
both cases a **risk quantity is represented by a number that cannot express the thing it
stands for.** The fix is not a bigger number — it is a stop that carries its **type** and
its **trigger**, with the numeric level as one field of several.

**Scoped here, not built here.** It rides the ledger build because it is the same table and
the same migration wave; **the exit-rule vocabulary is a decision for the Trade Analysis
lane**, which is where the discipline is authored.

### T6c — GUARDED MANUAL-ENTRY PATH (R-IV.308(a))

**TA-003's instance: one write path, four wrong fields, one money row.** id 409 carried a
wrong qty, a wrong entry, a wrong trade date **and** the unmapped account label. **They are
not four defects. They are one unguarded write.**

**The account-string write-path trace MOVES FROM HELD INTO THIS BUILD'S SCOPE** — it was
parked as a read-only investigation, and the instance shows the same path producing
numeric corruption, not just a label problem.

**The guard, three parts:** the account must be a **canonical label** (T2's enum, not free
text); **required fields are required** — qty, entry, trade date, account — with no
silent defaults; and **a rejected write says which field failed**, because a manual-entry
form that fails silently is how four fields go wrong at once without anyone noticing.

**No silent defaults is the load-bearing clause.** A default is indistinguishable from a
value the principal typed, and **once written, nothing downstream can tell them apart.**

### T6d — ROW-LEVEL PROVENANCE (R-IV.308(b))

**A new column on every money row**, one of:

| value | meaning |
|---|---|
| `PRINCIPAL_REPORTED` | the principal said so; **not verified against anything** |
| `BROKER_VERIFIED` | matched to a broker record; the **verifying event and its timestamp are stamped on transition** |
| `IMPORTED` | landed via an import path, carrying that import's identity |

**Every manual entry starts `PRINCIPAL_REPORTED`. NOTHING SIZES OFF A ROW AS VERIFIED UNTIL IT FLIPS.**

**This retires the notes-only `APPROXIMATE` / `PENDING-CSV` convention into the column**, and the
reason is exactly the reason free-text notes fail everywhere else in this register: **a
caveat a human must read is invisible to every consumer that computes.** id 409 is the
instance — it was reported, not verified, and nothing in the schema said so, so a risk
figure was computed from it as if it were fact.

**Provenance is not a status field.** It answers *"how do we know this?"*, which is a
different question from *"is it open?"* and must not be folded into one.

### T6e — LOT HISTORY (R-IV.309(d)) — A REQUIREMENT, NOT A FEATURE

**The hub can hold a blended position but not its lots.** So a hub row and a broker order
**can both be correct and disagree**, and no amount of care at the reconciliation step
resolves it — the information needed is not in the schema.

**id 409 is the whole problem in one row.** Three lanes spent a day on a discrepancy that
is not a discrepancy: TA read one lot, the hub held the blend, and `max_loss` carried the
first lot's price at the final quantity. **Every one of those three numbers is internally
defensible. The row still cannot be checked**, because the thing that would settle it —
which lots, in what order, at what prices — was never stored.

**It rides the positions-screen brief as a REQUIREMENT.** A screen that renders a blended
row without its lots reproduces this exact ambiguity on every scaled position, and renders
it attractively.

**SCHEMA RULED — R-IV.310(b). PROVENANCE IS PER LOT.**

```
position_lots (position_id, qty, price, fill_time, provenance, source)
```

**The position row becomes the AGGREGATE. Entry, cost basis and `max_loss` DERIVE from the
lots and are never stored independently of them.**

**That single sentence closes the whole family.** T6's defect was a derived quantity being
stored and separately maintained; T6d's was provenance being collapsed to a row that has
more than one origin; T6e's was lots not existing at all. **They are one defect in three
places, and derivation-from-lots is one fix for all three** — a stored aggregate cannot
drift from lots it is computed from on read.

**The ledger build creates the table and the derivation. The positions-screen brief consumes
it** for scale-in, edit, and multi-leg. **It is id 409's whole problem in schema form.**

**EVIDENCE — three live instances (R-IV.310, closing note): ids 409, 332, 367.**
**Three rows, three lot events, zero columns.** The count is the argument: this is not one
row's accident but the normal outcome of scaling any position, and **nothing needs building
beyond what the schema above already orders.**

### T6f — IMPORT CADENCE (`DEF-EXPORT-COVERAGE-GAP`) — A REQUIREMENT

**The lots table needs a source.** `position_lots` can be created empty; it cannot be
**populated** by anything this build otherwise contains. An import cadence — a scheduled
job, or a defined manual rhythm with a liveness check — **is the source.**

#### Why this is a requirement and not a later convenience

**Without it, T6d's provenance column is a constant, and a constant provenance is a NULL
PROVENANCE.**

Every row starts `PRINCIPAL_REPORTED`. **`BROKER_VERIFIED` is reachable only through a broker record arriving.** If
no import path exists, nothing ever transitions, the column reads `PRINCIPAL_REPORTED` on every row
forever, and **it can never be observed to be wrong** — which is precisely the defect
already registered on `indicators_source`, where a hardcoded `uw_computed` named a server that served
nothing.

**Third instance of that law in this register**, and the first one that would be built
*after* the law was written:

| instance | the constant | why it could not fail |
|---|---|---|
| `indicators_source` | `uw_computed` literal | not derived from which server answered |
| notes-only `APPROXIMATE` | free text | invisible to every consumer that computes |
| **T6d without T6f** | **`PRINCIPAL_REPORTED` on every row** | **no event exists that could flip it** |

**So T6f is not "how the lots get filled." It is what makes T6d falsifiable.** A provenance
column whose second value is unreachable is worse than no column, because it *looks* like
evidence.

#### The same requirement answers the balance-vintage half

**T5's 88-day hand-typed balance and T6e's missing lots have ONE cause between them: no
broker data arrives on a cadence.** The balance is stale because nothing refreshes it; the
lots are absent because nothing delivers them. **One import path closes both**, which is
why it belongs in this build rather than in a later one.

> **CC-BUILD flag — the instruction was truncated.** The ruling reads *"the same requirement
> that answers 'live balances"* and ends there. **The reading above — that it points at
> T5's column-vintage defect — is this lane's INFERENCE, not the ruling's words.** It is
> written as the obvious completion and marked so it can be corrected in one edit if the
> intended clause was different.

#### Registration status — the name does not resolve

**`DEF-EXPORT-COVERAGE-GAP` is a PHANTOM as of 2026-09-07.** Searched `C:\th-build\docs` and `C:\trading-hub\docs`,
every markdown file, by name and by citation: **no artifact, and no other document cites
it.** This brief is currently its only mention.

**Not a claim about the defect — a bookkeeping fact**, exactly as the R-IV.263 sweep
defined it. The requirement above stands on its own reasoning; **what is missing is the
artifact the name points at**, and the brief should not be the only thing carrying it.

### T7 — Positions tab — **MOCKUP GATE**

**No UI code until a mockup is approved.** Last in sequence deliberately: a tab built over an
unreconciled ledger renders wrong numbers attractively, and a number is more believed for
being well presented.

## Done definition

- **D1** — Phase 0 complete and filed; P0.1's census states which name survives.
- **D2** — T1 shipped and verified **before** T2 begins. Ordering is a done-criterion, not a
  preference.
- **D3** — one account-vocabulary module; every P0.1 surface reads it. Demonstrated by
  changing the constant and observing all surfaces move.
- **D4** — **CHECK constraint and seed in the same commit**, proven against a **fresh
  database that boots**. A migration that only works on the populated table fails this.
- **D5** — `total_balance` and `total_cash` match the broker; the +120% / +223% deltas are
  closed and re-measured live, not asserted.
- **D6** — column-level vintage: a cash-only write does not refresh the balance's age, shown
  on a real row.
- **D7** — `max_loss` computed from basis on both stock and option rows. **The old form of
  this criterion said "id 409 reads 1,498.30" and is WITHDRAWN: that figure is
  30 × 49.9433, the corrupt qty times the corrupt entry** (R-IV.308(a)). Accepting it
  would have baked a data-entry error into a done-criterion and called the build finished
  when it reproduced one. **The criterion is now: on a row whose provenance is
  BROKER_VERIFIED, max_loss equals qty × entry.**
- **D8** — IB's 90 rows **retired and still present.** A count proving they exist is part of
  this criterion.
- **D-final — ACCEPTANCE: the Trade Analysis lane confirms hub against broker, per
  position.** Until this passes, R-IV.268(d)'s sizing restriction stands.

## THE 1.52 LEAD — RETIRED ON ARITHMETIC (R-IV.309(c))

**Recorded so the next reader does not rediscover the coincidence and act on it.**

The lead was: id 409's corrupt-to-true notional ratio is **1.5251**, against the pinned
SOXS trap's **~1.52x**. Same ticker, three significant digits.

**It is empty, and the arithmetic says why in one line:**

```
1.5251  =  1.5000  x  1.0168
           qty ratio  entry ratio
           (30/20)    (49.9433/49.12)
```

**The notional ratio is the product of the quantity ratio and the price ratio, BY
CONSTRUCTION** — that is true of any two positions whatsoever. Neither input has anything
to do with a split. **1.5 x 1.0168 landing near 1.52 is a coincidence between an arbitrary
product and an unrelated price break.**

**This retires the lead on arithmetic alone**, independently of how the lot question
resolves: the identity holds whether id 409 is one corrupt lot or two correct ones.

**DO NOT ACT stands** on the pinned trap itself, which is a separate matter and remains
live.

## Gates / what NOT to do

- **NO hard deletes.** Retirement is a column.
- **NO manual SQL against prod.**
- **NO UI before the mockup gate.**
- **NO constraint without the seed change in the same commit.**
- **NO lifting the broker-figures-only sizing rule before D-final.**
- **NO account string copied from a tool rendering into a query.**
- **NO averaging of same-date disagreeing snapshots** (P0.3).

## Open questions for the review

**Q1 — Which name survives, `BROKERAGE_LINK_401K` or `FIDELITY_401A`?** Two code surfaces
each. R-IV.268(a) settles that they are ONE account; it does not settle what to call it.
**And the label is separately DISPUTED** — `DEF-ACCOUNT-LABEL-DUP` records that one of the
two enum labels is factually wrong (401k vs 403b). **Naming a canonical account after a
label known to be wrong would freeze the error into a constraint.**

**ANSWERED — R-IV.275(e)(3), CORRECTED BY R-IV.284: neither, and the question was
malformed.** The canonical set is `{ROBINHOOD, FIDELITY_ROTH}`. **Neither candidate names a
tracked account**, because the pot they refer to is **parked, untraded, out of scope** —
so the question *"which name survives"* presupposed a third account that does not exist.

**The dispute is dissolved rather than settled**: a label that names no canonical account
cannot be the wrong name for one. It survives as an out-of-scope tag, where being
misleading is a recorded fact instead of a live constraint.

**Q2 — Does the retired-IB row keep a balance?** A retired row with a live number can still
be summed by something that does not check the flag; a retired row with a null balance loses
the historical value. **This lane recommends: keep the value, and make the aggregate
filter explicit** — the aggregate is the thing that was wrong, so it is the thing that
should have to say what it includes.

**Q3 — Is the `startswith` prefix collision in scope here or its own defect?** It was found
during this draft (P0.1), it is on a money path, and it is not any of the six registered
items. **ANSWERED — R-IV.275(e)(2): registered as `DEF-ACCOUNT-MATCH-PREFIX`, P1, money path.
Fix is EXACT MATCH on canonical labels** — not a narrowed prefix and not a longer alias
list. **Scoped into T2**, which rewrites that function anyway.
