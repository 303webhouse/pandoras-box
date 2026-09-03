# RH FACE (1c) + CASH-EVENT INSTRUMENT (1d)

**R-IV.97 Part 1 items. READ-ONLY. No DB writes.** New material only — per (g), already-ruled
work is cited, not re-executed.

| provenance | value |
|---|---|
| **Tree SHA** | `8b2d767` |
| **DB read** | 2026-08-25 **17:36–17:40 UTC** (11:36–11:40 MT) |
| **Clock adjudicated** | shell `17:40:08Z` vs DB `now() 17:40:09Z` — agree. Earlier stamps in this session (01:38 MT) were accurate; ~10h elapsed between relays. |
| **Mark vintage** | RH open marks refreshed **17:32:10Z**, ~8 min before this read |

---

## (1c) — downgrade ACCEPTED. The offered rescue also fails. Here is what survives.

**Accepting the correction.** "Structurally impossible" was mechanism-from-symptom and
overreached. `balance` has undefined semantics — that is the registered defect — and you
cannot call a value of an undefined quantity impossible. Withdrawn as phrased.

**But short-leg subtraction is not the explanation either.** The discrimination (1c) asks
for, run against the current book:

```
 RH open rows ................... 21   (19 priced, 2 null-marked)
 credit structures .............. 0
 negative marks ................. 0    (min mark +0.005)
 structures present ............. call_debit_spread · long_put · put_debit_spread
 RH open position value ......... +$478.50
```

Every RH open position is a **net-long debit structure**. In a debit spread the short leg
subtracts from the long leg, but the pair cannot net below zero — you paid a debit to open
it. There are no credit structures and no naked shorts in the book. Position value is
**positive $478.50**, not a liability.

So against the two candidate readings:

| if `balance` means… | expected | actual | verdict |
|---|---|---|---|
| account value | ≥ cash, ≈ 1070.00 + 478.50 = **1548.50** | 835.69 | inconsistent |
| cash | **1070.00** | 835.69 | inconsistent |

**835.69 is inconsistent with both candidate semantics**, and short-leg subtraction moves it
in the wrong direction from the first and not at all from the second.

**The decisive structural point — `balance` never sees positions.** Its complete write path
(inventoried in Phase 0b §8.1, cited not re-derived) is:

1. `POST /balances/update` — a human typing a screenshot figure (`updated_by='pivot_screenshot'`)
2. `cash_flows` — `balance = balance + amount` (`updated_by='cash_flow'`)

Three other writers move `cash` and never touch `balance`. **No position-derived quantity
enters `balance` inside the DB at all** — so short legs, long legs, and marks are all
incapable of subtracting from it here. The rescue would require `balance` to be
position-aware, and it is not.

**What actually survives, and it is weaker than my original claim:** the two columns have
**uncoordinated provenance and different vintages**, so comparing them licenses no inference
in either direction. (1b) supplies the concrete vintage gap — `updated_at 2026-08-24T17:01:35Z`,
24.5h stale, with a $250 withdrawal and further transactions unrecorded across the interval.
A stale hand-typed `balance` against an auto-drifted `cash` is not evidence of a semantics
defect; it is evidence that the comparison is not a test.

**DEF-BALANCE-COLUMN-SEMANTICS stands OPEN and its RH face stays undiagnosed.** I am not
substituting a new mechanism.

### Correction to my own prior read, worth recording

At 2026-08-25 **07:0x UTC** I observed `POS_PLTR_20260609_233704` (put_debit_spread) carrying
`current_price = -0.035` — a **negative mark on a debit spread**, which is not a real state.
The 17:32Z mark run has since rewritten it to `+0.005`.

So negative marks **do** occur on this book and can transiently produce negative position
value; they are simply not present right now. That is a DEF-MARK-INTEGRITY artifact rather
than short-leg economics, and it is the one mechanism that *could* have produced a
below-cash account value — via corrupted marks, not via legitimate liabilities. Flagging
because a diagnosis run at a different hour would have seen a different book.

---

## (1d) — the named instrument is much weaker than assumed. Report before it is relied on.

(1d) states: *"the Fidelity export's cash-event rows are the available instrument."* Checked
against both export forms on disk:

| export form | cash-event rows |
|---|---|
| 60-day, single-account (`History_for_Account_ACCT-ROTH.csv`) | **11** |
| **90-day, multi-account** (`90-day Accounts_History.csv`) | **0** — header only |

**The 90-day export carries no cash events at all.** It is the multi-account form, which
omits `Cash Balance` and ships no cash rows. Since the 90-day artifact is now Phase 1a's
input and the broker-validated half, the instrument named in (1d) is **absent from the
artifact that matters** and present only in the superseded 60-day file.

**Worse — the 11 rows are the wrong event class.** All of them, verbatim:

```
 08/17  TRANSFERRED FROM TO BROKERAGE OPTION (Cash)          88.15
 08/04  TRANSFERRED FROM TO BROKERAGE OPTION (Cash)          60.93
 08/03  TRANSFERRED FROM TO BROKERAGE OPTION (Cash)          88.15
 07/31  REINVESTMENT FIDELITY GOVERNMENT CASH RESERVES      -21.21
 07/31  DIVIDEND RECEIVED FIDELITY GOVERNMENT CASH RESERVES  21.21
 07/20  TRANSFERRED FROM TO BROKERAGE OPTION (Cash)          88.15
 07/10  TRANSFERRED FROM TO BROKERAGE OPTION (Cash)          88.15
 07/07  TRANSFERRED FROM TO BROKERAGE OPTION (Cash)          60.92
 06/30  REINVESTMENT FIDELITY GOVERNMENT CASH RESERVES      -17.03
 06/30  DIVIDEND RECEIVED FIDELITY GOVERNMENT CASH RESERVES  17.03
 06/30  DIVIDEND RECEIVED DIREXION SHARES ETF TRUST (SOXS)   16.88
```

Six are **internal transfers** between the core and option sub-accounts of the same account.
Four are **dividend/reinvestment pairs that net to zero** (±21.21, ±17.03). One is a **$16.88
SOXS dividend**.

**Zero external deposits. Zero external withdrawals.** The event class DEF-CASH-EVENTS-UNTRACKED
is about does not appear in this artifact.

**And no Fidelity export can ever contain the $250 event** — that is a **Robinhood**
withdrawal. The instrument is the wrong broker for the reported incident.

### What would actually serve the defect

Stating the gap, not proposing a build (CC-BUILD's lane):

- The $250 withdrawal needs a **Robinhood** activity export; no Fidelity artifact reaches it.
- `cash_flows` already exists as a table with an account-aware dedup key
  (`UNIQUE NULLS NOT DISTINCT (account_name, flow_type, amount, description, activity_date, imported_from)`)
  and holds 23 rows — it is the right shape for external flows and is **not** currently fed
  by any broker export path.
- The Fidelity 11 rows are still worth loading for completeness (the $16.88 dividend is real
  income), but they will not close the defect.

**(1d)'s binding consequence is unaffected and I concur:** any return percentage against
account value is UNVERIFIED absent a cash-flow ledger, and the ~10.8% Fidelity figure is
correctly caveated. PR-106's insulation by method (realized P&L per trade from broker cash
flows, §0-R4) holds — my overlap validation tested exactly that path and it passed at 0.46%.

---

## Noted, no action

- **(1e)** TGT Friday 08-28 stamp: realized −$40.18, mark fields **NULLED not zeroed**. id 381
  census and preimage already filed; unchanged.
- **(1f)** The aggregate phantom is live. Consistent with Phase 0b §1 — the row-level seam is
  honest (`is_stale` per row, breakout_prop honest-absence) and the aggregate is not. Cited,
  not re-derived.
- **(f)/(c) prior** 1.52× verified independently by CC-BUILD across the factor plateau; my
  magnitude correction stands confirmed. No further action from me.
- **(d) law + corollary** adopted — an error equal to a known constant in the problem (×10,
  the split factor) is a unit error until proven otherwise. That is precisely the 6.57×
  case, and I will apply it as a standing check.

**No DB writes. Nothing staged.**
