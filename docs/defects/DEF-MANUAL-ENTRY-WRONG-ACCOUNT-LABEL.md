# DEF-MANUAL-ENTRY-WRONG-ACCOUNT-LABEL

**Severity:** P1 — **live write path** · **Filed:** 2026-09-17 (R-IV.445(a)) · **Status:** FIXED — write path f92bd16
(2026-09-17 20:39 UTC); remap complete, measured 2026-09-18
**Author:** CC-POSITIONS — sole author under convention #9.
**Surface:** the hub's manual position-entry path → `unified_positions.account`
**Sibling:** `DEF-ACCOUNT-LABEL-DUP` — that defect's dispute is resolved; **this is the path
that keeps re-creating it.**

## THE DEFECT

**The manual-entry path mints the retired `FIDELITY` alias.** Four positions entered by the
principal on 2026-09-16 landed under it — **eleven days after the last row carrying that label
was remapped** and the canonical set was ruled `ROBINHOOD` / `FIDELITY_ROTH` (R-IV.268(a)).

```
 id 432  SOXS 25 @ 49.74    2026-09-16 19:04:34   account = FIDELITY
 id 433  SOXS 16 @ 49.87    2026-09-16 19:08:22   account = ROBINHOOD   (correct)
 id 434  SQQQ 30 @ 40.55    2026-09-16 19:11:30   account = FIDELITY
 id 436  SBIT 20 @ 38.40    2026-09-16 19:29:42   account = FIDELITY
 id 437  PDBC 50 @ 19.79    2026-09-16 19:37:12   account = FIDELITY
```

**This is not residue. The path minted it**, in a single 33-minute session, ten days after the
remap. `DEF-ACCOUNT-LABEL-DUP` recorded the breach of R-IV.80d condition 3 — *"one account
label, canonical; do not write under both"* — as a **past** event. It is a standing one.

## THE SHARPER FINDING — the label path failed while the human input succeeded

**Every one of those four rows was substantively correct.** Checked against the Fidelity
confirmations that arrived the next day:

| principal entered | confirmation | ref |
|---|---|---|
| SOXS 25 @ 49.74 | 25 @ **49.7430** | 26258-Q4ZDR8 + 26259-PM8MYF + 26259-QKPYQL |
| SQQQ 30 @ 40.55 | 30 @ **40.5450** | 26259-MCQG7Y |
| PDBC 50 @ 19.79 | 50 @ **19.7876** | 26259-PQD5RV |
| SBIT 20 @ 38.40 | 20 @ **38.4000** | 26259-N4L0JB |

Right to within seven cents on the largest, exact on one. **And at the moment they were
written they were the ONLY accurate Fidelity equity in the book** — the six `FIDELITY_ROTH`
rows beside them were all stale, carrying positions the broker had closed on 09-11 and 09-14
that nobody had recorded (corrected at R-IV.447(b)).

**So the defect is precisely inverted from how it looks.** A reviewer seeing four rows under a
retired label would reasonably assume careless entry. The opposite is true: **the human supplied
good data and the system attached a bad label to it.** The automated side was the wrong half.

## WHY P1

- **It splits the account.** Any per-account view returns four positions in one bucket and six
  in another, and neither is the book. A sleeve or exposure sum keyed on `FIDELITY_ROTH`
  silently omits $4,217.35 of live basis.
- **It recurs on every entry.** This is not one row to repair; it is the next row, and the one
  after.
- **It defeats the remedy already applied.** id 409 was remapped on 09-05 under R-IV.268(b).
  The path refilled the hole in under two weeks.

## CONSEQUENCE CLASS — A MISFILED ROW IS INVISIBLE, AND INVISIBLE READS AS ABSENT

**Instance: BITX, 2026-09-16.** The principal recorded a same-day round trip as **id 435**
(50 @ 16.39 → 16.06, realized −16.50) with the reason on its face: *"Mistakenly bought a bull
ETF instead of a bear ETF. Closed as soon as I realized my error."* The 09-17 reconciliation
did not see it, concluded the trip was unrecorded, and created **id 440** from the
confirmations. Two rows, one event. id 435 is now `DUPLICATE_OF` id 440.

### The cause, corrected on measurement

**R-IV.449(a) attributes this to the retired alias hiding the row from an account-scoped read.
That is not what happened**, and the distinction changes the remedy.

The reconciliation's scope was:

```sql
WHERE status='OPEN' AND (asset_type='EQUITY' OR structure='stock')
  AND account LIKE 'FIDELITY%'
```

`LIKE 'FIDELITY%'` matches **both** `FIDELITY` and `FIDELITY_ROTH`. The alias could not have
hidden it. **The row was invisible because the inventory was scoped to `status='OPEN'`, and a
same-day round trip is never open at the moment it is counted.**

> **AN INVENTORY SCOPED TO OPEN ROWS CANNOT SEE A POSITION THAT OPENED AND CLOSED INSIDE ITS
> WINDOW.**

That is the same blind spot as the whole-lifecycle-absent class — and it is why a *duplicate*
was misread as an *absence*. Both look identical from a reconciliation: the broker has
something the book appears not to. **One remedy inserts a row; the other retires one.**

**So R-IV.449(b)'s standing rule is right and insufficient.** Scoping to the canonical
vocabulary *plus every known alias* is necessary — an alias genuinely can hide a row from a
strict `account = 'FIDELITY_ROTH'` read. But it would not have caught this one. **The status
scope has to widen too:** a reconciliation over a date window reads every row *touching* that
window, in any status, under any label.

**The label defect still owns the general class** — a row under a retired label is unreachable
from a canonical read, and the four 09-16 rows were exactly that until BUILD's remap. This
instance is filed here because it is that class's shape, while recording honestly that its
proximate cause was the status filter, not the label.

## MECHANISM — a free string uppercased accepts anything spelled in capitals

`account` is `text`, nullable, with **no CHECK constraint and no foreign key** (42 columns on
the table; the canonical vocabulary lives only in `docs/feat-position-lifecycle.md` and in
prose). Any value that survives an `.upper()` is accepted, so `FIDELITY` is as valid to the
database as `FIDELITY_ROTH`.

**The vocabulary is documentary, not enforced.** That is the defect's root: a rule recorded in
a document cannot reject a write.

## REMEDY (BUILD, R-IV.445(a))

1. **The write path takes the account from the canonical module** — not from free text.
2. **A non-canonical value is rejected**, loudly, at the write.
3. **The five existing rows remap** to `FIDELITY_ROTH` on the principal's confirmation —
   including the **CLOSED** BITX row, because a retired label in history is equally unreachable
   (R-IV.445(d)).

**A CHECK constraint alone is not the fix** and should not be mistaken for it: it would reject
the bad write, but the entry path would still be *offering* free text for a value that has
exactly two legal answers.

## WHAT IS NOT ESTABLISHED

- **Where the string originates** — a form default, a remembered value, a dropdown with a stale
  option, or free typing. Untraced; that is BUILD's.
- **Whether other fields share the pattern.** `account` was measured because it broke visibly.
  `structure` already shows the same shape — `call_spread` and `call_debit_spread` both in use
  for one thing. **Since run:** `docs/incidents/FREE_TEXT_VOCABULARY_CENSUS.md` (R-IV.450(g)) —
  the `structure` and `direction` variants all trace to `CSV_RECONCILE`, not to this path.

## STATUS

Registration only. **No row relabelled by this filing.** The remap is BUILD's under
R-IV.445(d); CC-POSITIONS touched no account labels in the R-IV.447 correction set.

**Update 2026-09-18 (R-IV.457 pass): FIXED.** f92bd16 moved the vocabulary into
`models/accounts.py`, and every write path reads it: position creation, cash events, and both
legacy signal-entry paths. An alias normalises; anything else is refused with the vocabulary
and the value received. **Measured after the remap: the book carries exactly two labels —
`ROBINHOOD` 374 rows, `FIDELITY_ROTH` 80 — and none under `FIDELITY`.** Not tested by this
lane: a live write under the alias, which would be a production write.
