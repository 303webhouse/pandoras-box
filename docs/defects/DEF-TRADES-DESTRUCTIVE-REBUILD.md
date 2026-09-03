# DEF-TRADES-DESTRUCTIVE-REBUILD · P1

**Registered:** 2026-09-03 (R-IV.210(c)).
**Diagnosis of record:** `docs/edge/results/2026-09-03-trades-rekey-diagnosis.md` (CC-QUERY).
**Fix:** HELD. **Interim control:** the DO-NOT-RUN on `scripts/reconcile_rh.py` in
PROJECT_RULES.md — that order is the whole mitigation and must not lapse before the fix.

One defect, four facets. Every code claim below was verified by CC-BUILD directly against
the file before registration; the DB-side counts are cited from the diagnosis.

---

## Facet 1 — destructive delete/re-insert: ids rotate, content survives

`scripts/reconcile_rh.py` line 303:

```
DELETE FROM trades WHERE origin = 'csv_reconciliation'
```

followed by a re-INSERT. Re-inserted rows draw fresh `nextval()` values, so **every id in the
rebuilt set changes while `(ticker, opened_at)` survives.** That is the mechanism behind the
observed re-key: captured ids 69-383 became 153-609 between 2026-08-27 and 2026-09-02.

The consequence reaches every artifact that stored an id. It is why the 66-unit manifest's
`src=B` half had to be re-resolved by content key, and why a numeric id match across the two
keyspaces is, in the manifest's own words, a coincidence of integers.

## Facet 2 — 19 hard-coded ids the script itself invalidates

Lines 306-333 carry a literal `pnl_reverts` list of **nineteen** trade ids:

```
163 165 178 227 237 181 182 184 191 192 194 197 196 216 218 220 221 219 259
```

each applied as `UPDATE trades SET pnl_dollars = $1 WHERE id = $2`.

**The DELETE at 303 runs BEFORE these reverts, in the same execution.** The script rotates
the keyspace and then writes nineteen P&L values into whatever rows now occupy those id
slots. Nothing checks that the target row is the intended one — no ticker assertion, no
content key, no row count guard.

**This is a self-invalidating literal**: the ids were correct against exactly one keyspace,
and the script's own first action is what destroys that keyspace.

## Facet 3 — `trades` cannot date its own rebuilds

The table carries **no `created_at` and no `updated_at`**. A rebuild-capable table with no write
timestamp cannot say when it was last rebuilt. The rotation could only be *bounded* by two
external observations, 08-27 and 09-02, never dated.

This is what turns facet 1 from a recoverable event into an undatable one. Had the reverts
misfired, the damage would be silent **and** undatable — no column would show which rows
were touched or when.

## Facet 4 — origin spelling split: half the synthetics are immune to the cleanup

Per the diagnosis, `trades` carries two spellings of the same origin:

| origin | n | id range |
|---|---|---|
| `csv_reconciliation` | 28 | 332-359 |
| `csv_reconcile` | 22 | 519-541 |

**The delete predicate matches only the first.** Verified in the script: four occurrences
of `csv_reconciliation`, zero of `csv_reconcile`. So 22 of the 50 synthetic rows are
**structurally immune** to the cleanup that is supposed to remove them, and a rebuild
leaves them behind while removing their siblings.

A cleanup that silently covers 56% of its target is worse than none: it produces a table
that looks rebuilt and is half stale.

---

## Why P1

Facets 1 and 2 together are a **live path to silent, undatable corruption of realized P&L
figures** — the numbers the book is adjudicated on. It requires no unusual input; it needs
only for someone to run the reconciliation script a second time, which is what a
reconciliation script exists for.

The script is not currently scheduled and there is no evidence of a second run. The DO-NOT-RUN
is what keeps it that way.

## Fix, when commissioned

Not chosen here. Four things any fix must satisfy, stated so the commission is scopeable:

1. Reconcile **in place** by content key, or delete and re-insert **within one transaction**
   that re-resolves dependent literals afterwards. Never both halves keyed by serial.
2. **No literal id lists.** Reverts key on `(ticker, opened_at)` or carry an assertion that the
   target row matches an expected ticker before writing.
3. Add `created_at` / `updated_at` to `trades` so a rebuild is datable.
4. Resolve the origin spelling split **before** any delete predicate is trusted, and make
   the predicate cover both spellings or neither.
