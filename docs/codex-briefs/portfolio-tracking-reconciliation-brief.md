# BRIEF: Portfolio Tracking Pipeline — Reconciliation & Canonical Source

**Owner:** Nick **Builder:** Claude Code **Review:** ATLAS (lead), ATHENA (sequencing), AEGIS (light), HELIOS (light)
**Priority:** P1 — Olympus must run on an accurate, always-current book.
**Status:** DRAFT — Phase 0 is gated. No code/schema changes until Nick approves Phase 0 findings.

---

## Problem (verified live against Railway Postgres, 2026-06-02)

Trade data is fragmented across multiple populated tables that disagree with each other:

| Table | Rows | Notes |
|---|---|---|
| `rh_trade_history` | 363 | Raw RH activity (transaction-level, not trade-level) |
| `trades` | 253 | Trade-level. Origins: imported (70), position_ledger (155), csv_reconciliation (28) |
| `unified_positions` | 170 | What Olympus + analytics currently read |
| `closed_positions` | 119 | Separate closed-trade record |
| `open_positions` | 56 | Disagrees with `unified_positions` OPEN count (14) |
| `positions`, `options_positions`, `pending_trades`, `trade_legs` | 0 | Legacy / empty |

**Net realized P&L depends entirely on which table you believe:**
- `trades`: **+$3,793.55** (253 trades, 138W / 113L)
- `closed_positions`: **+$1,011.55** (119)
- `unified_positions` (CLOSED): **+$980.34** (133 graded, 17 ungraded)

These disagree even for overlapping periods: `trades` origin `position_ledger` shows +$1,867 over roughly the same era `unified_positions` shows +$980. **No table is currently authoritative.**

**Concrete example:** the EXC winner (+$841.16, closed 2026-02-13, Robinhood) exists *only* in `trades` (origin `imported`). It predates `unified_positions` (earliest row 2026-02-26) and never propagated. It is also absent from `rh_trade_history` — so even the "raw broker" table is incomplete.

**Open-book impact:** current exposure is ambiguous (`unified_positions` 14 OPEN vs `open_positions` 56). Nick cannot trust his live book, which directly affects risk decisions (e.g., short positions clearing 2026-06-18).

---

## Goal

ONE canonical representation of the book (open + closed), reconciled to broker truth, that Olympus and all analytics read. Manual entry + broker reconciliation feed it; divergent paths are retired. Always-current, with drift alerting.

---

## Phase 0 — INVESTIGATION (HARD STOP — read-only, no code/schema changes)

**Deliverable:** findings doc + recommended canonical-source design. Nick approves before Phase 1.

1. For each populated table: schema, row count, min/max date, and **what writes to it** — grep `backend/` for INSERT/UPDATE and list every ingest path (MANUAL, SCREENSHOT_SYNC, CSV_IMPORT, csv_reconciliation, position_ledger, imported, RH sync).
2. Identify the join/dedupe key across tables (position_id, trade_id, signal_id, RH order id).
3. Quantify overlap and divergence; produce a single reconciled trade list + net P&L with a confidence note.
4. Determine why early `imported` trades (EXC etc.) never reached `unified_positions`.
5. Recommend the authoritative source (candidate: `rh_trade_history` for RH truth, merged with a vetted historical import; Fidelity path TBD — see Open Decisions).
6. No writes. Output findings to `docs/` for review.

---

## Phase 1 — CANONICAL MODEL (after Phase 0 approval)

1. Define the one canonical table/view Olympus reads + the merge/dedupe logic. Dry-run on a copy first; show before/after row + P&L counts.
2. Backfill from the authoritative source; reconcile open positions to the broker.
3. Normalize `structure` and `direction` labels (fix casing / duplicate vocab: `put_spread` vs `put_debit_spread`; `BEARISH` / `bearish` / `SHORT`).

---

## Phase 2 — INGEST CONSOLIDATION

1. Single ingest pipeline (manual entry + RH reconciliation, + Fidelity path) writing only to the canonical table.
2. Retire divergent writers and drop empty legacy tables (also reclaims the 94%-full Postgres volume).
3. Validation gate: canonical net P&L reconciles to broker statements within tolerance before old paths are removed.

---

## Phase 3 — OLYMPUS WIRING + AUTOMATION

1. Point `hub_get_positions` / committee data at the canonical source.
2. Daily automated reconciliation + drift alert → "current book at all times" without manual toil.

---

## Open Decisions (Nick, before Phase 1)

1. **Authoritative source** — anchor on `rh_trade_history` (broker truth) and rebuild, accepting some early imports need manual confirmation? (Phase 0 will recommend.)
2. **Fidelity Roth ingest** — RH reconciliation is RH-only. How does Fidelity data enter — manual, CSV, or out of scope for v1?
3. **Historical scope** — full historical rebuild, or forward-only canonical with a frozen historical snapshot?

---

## Guardrails (house rules)

- Phase 0 is read-only; hard stop for Nick before any migration.
- All migrations dry-run on a copy with before/after row + P&L counts shown.
- CC finalizes exact find/replace anchors via grep; no blind edits.
- Nothing pushed to `main` without Nick (auto-deploy).
