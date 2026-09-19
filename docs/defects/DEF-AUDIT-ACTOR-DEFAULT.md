# DEF-AUDIT-ACTOR-DEFAULT — the audit could not tell a person from a job

**Registered:** R-IV.462(b). **Found:** CC-BUILD, 2026-09-19 (R-IV.458 relay, F4). **Status:**
FIXED FORWARD (R-IV.462 commit). **Historical rows are not rewritten. They stay ambiguous, and
they say so.**

> The actor column has one purpose: who made this change. A column where the mark job and a
> person's edit carry the same name cannot serve that purpose for either of them.

---

## WHAT WAS MEASURED (2026-09-19 05:30 UTC)

The audit trigger records `COALESCE(app.actor, 'legacy-ui')`. That default was R-IV.116's label
for the legacy PATCH caller. Machine writers never set `app.actor`, so every write they made took
the default.

| actor | UPDATE rows | touching mark fields | changing anything else | first |
|---|---|---|---|---|
| `legacy-ui` | **6,271** | **3,239** | 496 | 2026-08-27 |
| *(none)* | 401 | 182 | 12 | 2026-05-26: before the actor column |
| `positions-lane` | 30 | 0 | 30 | 2026-09-18 |
| `principal` | 5 | 0 | 5 | 2026-09-17 |

The `legacy-ui` rows grouped by the fields they changed identify the writers:
- **The mark job:** `price_updated_at` alone (2,541), the price, P&L and leg prices together (about
  3,200).
- **Boot backfills:** `provenance` on 383 rows in one instant at 2026-09-18 04:31, and
  `backfill_exempt_reason` on 4 rows at 17:38:56.
- **A batch script:** 20 rows given exit prices and results within three seconds at 2026-08-28 21:42, with no status change.

The edits that look like a person's (quantity, basis, stops, notes) number in the dozens.

## THE WRITERS (census of every UPDATE / DELETE on `unified_positions`)

| writer | now names itself as |
|---|---|
| mark job, legs path, two-strike path, legs-from-notes persist | `mark-to-market` |
| boot DDL: provenance backfill, the guarded statement loop, the entry-sign fix | `boot-migration`, with the statement's label as reason |
| PATCH follow-up recompute (ran after the edit's transaction had closed) | the request's own actor |
| `sync_rh_csv.py`, `migrate_unified_vocab.py`, `def_position_integrity.py`, `reconcile_window_2026-06-17.py`, `fix_ibit_call_roundtrip.py` | the script's file name |
| expiry sweep, lots, reduce, with-legs, correction, retire, verify, PATCH | already named (unchanged) |

Each name is set with `set_config(..., true)` **inside the transaction that carries the write**. A
name set outside one reaches nothing. A name set at session level would ride a pooled connection
into the next caller's write.

## THE CUTOVER, AND WHAT IT MEANS

`audit_actor_epochs` row `machine-writers-named`: `began_at` is written by the first boot of the
build that names its writers, so the cutover is a measured instant, not a remembered date. The
comment on `position_sync_audit.actor` says what it means:

- **Before `began_at`, `legacy-ui` is AMBIGUOUS.** It may be a person or a job, and it cannot be
  counted as either. Rows before 2026-08-27 carry no actor at all.
- **After it, `legacy-ui` means** a request to an endpoint whose caller named no actor (R-IV.116).
- A deploy runs the old and new builds side by side for a few minutes, so old-build `legacy-ui`
  mark writes can appear shortly after `began_at`.

**Consequence for reads already made:** any count of hand edits taken by actor from before the
cutover overcounts. R-IV.458(e)'s "three not five" should be confirmed as a count by the fields
that changed.

## WHAT STAYS OPEN

Four request-driven endpoints (create, close, delete, reconcile) still record `legacy-ui` for a
caller that names no one. After the cutover that is the label's meaning, not a mislabel. PATCH
accepts an actor from its caller; those four do not yet. Giving them the same field is a
follow-up and is not built here.

## THE GUARD

`backend/tests/test_audit_actor.py` reads the source: every UPDATE or DELETE on
`unified_positions` in `backend/` must sit inside a transaction that names its actor, and every
script that makes one must set `app.actor`. The only exceptions are the four endpoints and the
phase-1 trigger probe, which is rolled back and never reaches the audit, each exemption with its
reason. Tested fail-first: on the pre-fix tree it names the eleven unnamed writes (five in the
mark job, four boot writes, two in the PATCH recompute).
