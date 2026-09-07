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

`DEF-HUB-MAXLOSS-OPTIONS`, **widened to stock rows** (R-IV.265(e)). Cited instance, id 409:
1,547.70 where basis gives 1,498.30.

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
- **D7** — `max_loss` computed from basis on both stock and option rows; id 409 reads
  1,498.30.
- **D8** — IB's 90 rows **retired and still present.** A count proving they exist is part of
  this criterion.
- **D-final — ACCEPTANCE: the Trade Analysis lane confirms hub against broker, per
  position.** Until this passes, R-IV.268(d)'s sizing restriction stands.

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
