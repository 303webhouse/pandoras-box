# FEAT-POSITION-LIFECYCLE

Principal-commissioned 2026-08-26. Lots, an audit trail, and a cash-event write path for
`unified_positions`.

## Shipped

**Phase 1 — schema** (`scripts/feat_position_lifecycle_phase1.py`, applied 2026-08-26)

- `position_lots` — one row per fill; 330 rows backfilled `LEGACY-SINGLE-LOT` at entry
  vintage, verified 0 drift against their parent positions.
- `position_sync_audit` widened with `field`, `reason`, `actor` (D2 — one timeline per
  position, no second audit table). Its sync-only columns had their `NOT NULL` dropped,
  which is what "manual edits leave sync columns null" actually requires.
- `AFTER UPDATE OR DELETE` row-level audit trigger on `unified_positions`, guarded by
  `IS DISTINCT FROM` so a no-op write records nothing. **Unbypassable by all 19 write
  sites and any future one** — the reason it is a trigger rather than 19 call-site edits.
- Canonical account vocabulary `ROBINHOOD | FIDELITY_ROTH | FIDELITY_401A`;
  `BROKERAGE_LINK_401K` deliberately untouched (frozen dispute, DEF-ACCOUNT-LABEL-DUP).
- `cash_flows.occurrence` added to the dedup key.

**Phase 3 — the ruled shape** (migration `037`, 2026-09-17, R-IV.441(a))

- `position_lots` moved INTO `migrations/` and reached the ruled schema by ALTER, not by
  CREATE: `quantity` -> `qty`, `fill_date` -> `fill_time` (a pure rename — the live column was
  already `TIMESTAMPTZ`), `fees` KEPT for the gross/net delta, `provenance` and `broker_ref`
  added. Renames are guarded on both names; boot mirrors the migration.
- **Provenance is inherited, never defaulted.** Existing lots take it from the parent
  position's `source`; new ones from how they arrived. `BROKER_VERIFIED` is unreachable from
  any path here, and the table refuses it without a `broker_ref` to check it against.
- **No lot is invented.** 50 of 380 positions have none — 20 of 34 OPEN — so the lots
  invariant is FALSE today and is reported rather than backfilled away:
  `GET /v2/positions/lots/coverage`, by status, with the open rows named.
- The add path stopped folding fees into the per-unit price, stopped dropping the 100x
  contract multiplier on option rows, stopped extrapolating a basis across an unpriced lot
  (it now stores NULL and says why), and refuses a lot sum an INTEGER quantity cannot hold.
- Request fields are `fill_time` and `qty`; the old names are refused, not aliased.

**Phase 2 — endpoints** (`5a3da53`)

- `POST /v2/positions/{id}/lots`, `GET .../lots` — basis recomputed from the lot set over
  **priced lots only** (superseded in part by Phase 3 above: gross, with the asset's
  multiplier, and UNKNOWN rather than extrapolated when a lot has no price).
- `POST /v2/cash-events` — DEPOSIT/WITHDRAWAL, account-scoped, touches no position row
  and no realized field.
- ETF-only invariant (R-IV.75(d)) at both entry points.
- `reason` / `actor` optional on PATCH, bound via `set_config` **inside a transaction**;
  absent → `legacy-ui`.
- `strategy_tag` (R-IV.143(2)) — documentary vocabulary, no CHECK constraint.

## cash_flows vocabulary (R-IV.143(3))

`flow_type` is **documentary, not enforced**. Two encodings coexist in the table and
consumers must handle both:

- **Legacy rows are SIGN-ENCODED.** Every `flow_type = 'ACH'` row carries the direction in
  the sign of `amount`: 17 negative rows all described "…Withdrawal", 6 positive all
  "…Deposit", zero exceptions across the full history. The type says `ACH` and tells you
  nothing about direction.
- **Typed rows are TYPE-ENCODED.** Rows written by the lifecycle UI carry
  `flow_type IN ('DEPOSIT','WITHDRAWAL')` with `amount` **positive**; direction lives in
  the type. A negative amount on a typed row would double-negate.

A cash-delta computation must therefore branch on provenance, not on sign alone. The
compatibility rule: **read the sign for `imported_from = 'csv'`, read the type otherwise.**

**Provenance is `imported_from` + `description`, pending a dedicated source column.** That
is the honest statement of where a row came from today — `imported_from` distinguishes
`csv` from `MANUAL_UI`, and `description` carries whatever the importer or operator wrote.
Neither is a designed provenance field, and a source column is the eventual fix.

**No CHECK constraint on `flow_type`, deliberately** — the same documentary-vocabulary
precedent as `strategy_tag`. A constraint here would reject a legitimate row under a
vocabulary the code had not caught up to, and surface it as a 500 rather than a prompt.

## Open

- **Phase 3** — Agora UI (add-to-position, edit, cash panel, mark vintage on every row).
  `price_updated_at` appears 0 times in `v2.js` today; the mark-vintage display is net-new.
- **Phase 4** — fail-first P&L insulation test: a $100 test withdrawal must leave
  `SUM(realized_pnl)` unchanged to the cent and touch zero position rows, then reverse.
- **`cash_flows` has no audit trigger.** D1 is scoped to `unified_positions`, so cash
  events are the one lifecycle mutation with no audit trail. Raised, unruled.
- **Audit timeline is 96.5% mark noise** (389 of 403 captured UPDATEs changed only mark
  fields). Trigger stays capture-everything for now — the mark rows are live R-IV.114
  evidence. The one-line guard flip is pre-approved for when R-IV.114 ships; Phase 3
  filters mark-only rows at the read layer regardless.
