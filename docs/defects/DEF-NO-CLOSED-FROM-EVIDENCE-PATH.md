# DEF-NO-CLOSED-FROM-EVIDENCE-PATH — a real event could be recorded only by bypassing every guard

**Registered:** R-IV.463(g). **Instance:** ids 512 and 513, written by direct SQL on 2026-09-19.
That was accepted as necessary and registered as a gap. **Status:** CAPABILITY BUILT (R-IV.463
commit): `POST /v2/positions/closed-from-evidence`.

> A reconciliation that must bypass every guarded path to record a real event is a missing
> capability, not a workaround.

## THE GAP

POSITIONS found two partial closes (XLE, 2026-07-08 and 2026-07-17) that existed only in the
notes of the rows they were split from. Every path into the book refused them:

| path | why it could not record them |
|---|---|
| `POST /v2/positions`, `/with-legs`, `/bulk` | open a row and move cash; the cash already moved when the trade happened |
| `POST /{id}/close`, `/reduce` | need an OPEN row; these trades had ended months earlier |
| `POST /{id}/correct-realized` | corrects a row that exists; these had no row |

So the only route was SQL straight into the table. That route skips the terminal-status trigger's
purpose, the audit (INSERTs were not audited then), provenance, and the evidence rule.

## THE CAPABILITY

`POST /v2/positions/closed-from-evidence` is the shape the import will need. In one transaction,
with its actor named:
- the row, CLOSED or EXPIRED, with source from the import vocabulary and provenance IMPORTED
  (never BROKER_VERIFIED; verification is its own path);
- its legs when given, stamped IMPORTED;
- its opening fill, as an IMPORT lot;
- the exit on the row, as the close path leaves it.

**No cash moves.** `max_loss` and `cost_basis` derive. Realized is the record's figure, or the
gross from entry and exit when the record gives none, and the row says which. Evidence, reason
and ruling are required and written onto the row. A broker reference or a `trades` link already
in the book is refused with 409, naming the row that holds it.

Tested by rebuilding ids 512 and 513 through the path. It gives the same realized (+27.00,
+29.00) and max_loss (18.00, 29.00) that were written by hand.

## NOT DONE

Rows 512 and 513 themselves are unchanged. They are real, and their only defect is how they were
written. The INSERT that created them is not in the audit, because INSERTs were audited only from
R-IV.463(e) onward; this register is their trail.
