# DEF-ACCOUNT-MATCH-PREFIX · P1

**Registered** 2026-09-05 by R-IV.275(e)(2). **Found** by CC-BUILD while drafting the
ledger-integrity brief's Phase 0 — it is not one of the six items that brief was scoped
around. **Status:** OPEN. **P1: money path.**

---

## The defect

`_match_account_balance` (`backend/api/unified_positions.py:71-78`) matches account names by **prefix**, not by identity:

```
filter_normalized = filter_upper.lower().replace("_", " ")
return name_lower in aliases or name_lower.startswith(filter_normalized)
```

The legacy `FIDELITY` entry in `ACCOUNT_DISPLAY_MAP` (`unified_positions.py:63`) normalises to the prefix `fidelity` — which
matches **Fidelity Roth**, **Fidelity 401A** and **Fidelity 403B** alike.

**A filter asked for one account returns three, and returns them silently.** There is no
error, no warning, and the result is shaped exactly like a correct answer.

## Why P1

It is a **money path**. A balance filter that over-matches sums accounts the caller did not
ask for, and the caller cannot tell from the response that it happened. Same family as
`DEF-BALANCE-AGGREGATE-DOUBLE-COUNT` — an aggregate over rows that should not have been in scope — arriving by a
different route: there the wrong row was in the table, here the wrong row is in the
predicate.

**And it compounds the account collapse.** Per R-IV.275(e)(3) the canonical set is exactly
`{ROBINHOOD, FIDELITY_ROTH}`, with `BROKERAGE_LINK_401K` / `FIDELITY_401A` / `FIDELITY_403B` as **historical aliases of the same account**. A prefix matcher
over aliases of one account is how two vintages of one account get summed as two accounts.

## Fix (ruled)

**Exact match on canonical labels.** Not a narrowed prefix, not a longer alias list —
identity. Aliases resolve to a canonical label first, then the predicate compares equal.

**Scoped into the ledger-integrity build's T2**, which rewrites this function anyway.
Fixing it separately would mean touching the same function twice and defending the same
invariant in two places.

## Not measured here

How many live callers pass `FIDELITY` as a filter, and whether any consumer is over-matching
today. **The defect is in the predicate; the exposure is unread**, and this file does not
claim otherwise.
