# DEF-BALANCE-AGGREGATE-DOUBLE-COUNT · P1

**Found:** 2026-09-05 by CC-BUILD, verifying R-IV.268(c)'s double-counting claim rather
than restating it. **Confirmed live** through the hub, not inferred from code.
**Status:** OPEN. Scoped into the ledger-integrity build, position 1b.

**Distinct from `DEF-BALANCE-COLUMN-SEMANTICS`**, which is column-level vintage. This one is an **aggregate
computed over a duplicate row**, and the two fix in different places.

---

## Measured, live

```
hub_get_portfolio_balances, 2026-09-05

  total_balance   21,320.13     true tracked   9,677.78     +120%
  total_cash      16,862.47     true tracked   5,220.12     +223%
```

**Cash is the worse half by proportion, and cash is what sizing reads most directly.**

## Mechanism, one line

`backend/hub_mcp/tools/portfolio_balances.py:119`:

```
total_balance = sum(a["balance"] for a in accounts)
```

It sums **every** row in `account_balances`. Per R-IV.268(a) the Roth IRA and the
"401k BrokerageLink" are **ONE account**, so BROKERAGE_LINK_401K is a duplicate of
FIDELITY_ROTH — and it is summed as a third account.

The service layer is **not** at fault: `services/read_only/balances.py::get_account_balances` returns per-account rows and does
not aggregate. The defect is entirely in the tool's summation.

## Why P1

The tool's own description says it exists so sizing stops hardcoding dollar amounts, and
names TORO, URSA, DAEDALUS, PIVOT, PYTHAGORAS, PYTHIA and THALES as callers. **Every one
of them sizing off this reads an account 120% larger than it is, and cash 223% larger.**

**Contained today by R-IV.268(d)** — committee sizing uses broker figures until
acceptance. That ruling is the mitigation; without it this is live exposure to
oversizing.

## Two aggravating findings, both mine, both beyond the ruling

**1 — The summary understates by an order of magnitude.** For a row **88 days** stale it
prints *"Some balances >24h old."* True, and useless. Third instance of this phrasing
family after MP's *"feed quiet this session"* on a 38-day-dead feed and the watermark's
superseded *"up to 8"*. **A phrase that stays true as the magnitude grows is a floor, not
a warning.**

**2 — `is_stale` cannot discriminate.** It returns true for all three rows — the two that
are 1.2 days old and the one that is 88. A consumer checking it learns nothing it did not
already assume.

## Fix, when built — not chosen here

Retiring the duplicate row corrects the sum, but **the sum would still be wrong the next
time a duplicate appears**, which is what the account-enum collapse and the CHECK
constraint in R-IV.268(c) are for. **Fix the aggregate AND the vocabulary**, or the same
defect returns under a new alias.

**Sequencing, stated because it is a trap:** retiring the row before collapsing the enum
leaves the sum correct and the constraint absent — correct-by-accident, which is the
state this defect was already in for the eighty-eight days the row sat unnoticed.
