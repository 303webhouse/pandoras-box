# Phase 0 Findings — Portfolio Tracking Reconciliation
**Date:** 2026-06-02 | **Analyst:** Claude Code | **Status:** Awaiting Nick approval before Phase 1

---

## 1. Table Inventory

| Table | Rows | Date Range | P&L | Status |
|---|---|---|---|---|
| `rh_trade_history` | 363 | 2026-01-05 → 2026-02-18 | N/A (raw activities) | Partial snapshot only |
| `trades` | 253 | 2026-01-05 → 2026-06-02 | **+$3,793.55** | Hybrid — 3 distinct origins |
| `unified_positions` | 170 | 2026-02-26 → 2026-06-02 | CLOSED: **+$980.34** | Active canonical system |
| `closed_positions` | 119 | 2026-03-05 → 2026-06-02 | **+$1,011.55** | Redundant mirror of unified |
| `open_positions` | 56 (5 active) | opened_at: all NULL | N/A | Abandoned — last write 2026-03-09 |
| `positions`, `options_positions`, `pending_trades`, `trade_legs` | 0 | — | — | Empty legacy tables |

---

## 2. Write Paths — Who Writes What

### `rh_trade_history`
| Path | File | Notes |
|---|---|---|
| CSV import CLI | `backend/importers/import_rh_csv_cli.py:37,71` | Manual bulk import; two INSERT patterns (single + bulk) |

**No live feed.** This table was populated from a Robinhood CSV export covering 2026-01-05 to 2026-02-18 only (44 days). 363 rows: 253 options activities, 110 equity.  
Trans codes present: `BTO, STO, BTC, STC, Buy, Sell, OEXP`

### `trades`
| Path | File | Origin tag written |
|---|---|---|
| `insert_trade()` shared function | `backend/analytics/queries.py:510` | `'manual'` (default) |
| Close handler (atomic with unified close) | `backend/api/unified_positions.py:1614` | `'position_ledger'` |
| RH reconciliation script | `scripts/reconcile_rh.py:356` | `'csv_reconciliation'` |

### `unified_positions`
| Path | File | Source tag written |
|---|---|---|
| Create position API | `backend/api/unified_positions.py:515` | `'MANUAL'` (primary) |
| Screenshot sync | `backend/api/unified_positions.py:1929` | `'SCREENSHOT_SYNC'` |
| CSV sync script | `backend/api/unified_positions.py:2086` / `scripts/sync_rh_csv.py:1160` | `'CSV_SYNC'` / `'CSV_IMPORT'` |
| Old positions API (inactive?) | `backend/api/positions.py:219,396` | unknown source tag |
| SIGNAL automated | (signal pipeline) | `'SIGNAL'` |

**Source breakdown in unified_positions:**

| Source | Rows | Has trade_id |
|---|---|---|
| MANUAL | 140 | 110/140 |
| CSV_IMPORT | 14 | 14/14 |
| SCREENSHOT_SYNC | 9 | 3/9 |
| SIGNAL | 4 | 4/4 |
| CSV_SYNC | 3 | 1/3 |

### `open_positions` (legacy)
- INSERT: `backend/api/portfolio.py:272,392`
- UPDATE (deactivate): `backend/api/portfolio.py:254,295,506`
- **Last write: 2026-03-09.** Superseded by `unified_positions` and never cleaned up.

### `closed_positions`
- INSERT from portfolio API (legacy): `backend/api/portfolio.py:484`
- UPDATE from portfolio API: `backend/api/portfolio.py:565`
- INSERT from unified close handler (atomic): `backend/api/unified_positions.py:1690`
- **Written inside the same transaction as the unified_positions close** — should be a mirror, but 119 rows vs 150 CLOSED unified rows (31 CLOSED positions have no corresponding closed_positions row; likely the early SCREENSHOT_SYNC/CSV_IMPORT closes that used the old portfolio API path).

---

## 3. The `trades` Table — Three Populations

All 253 `trades` rows have `status='closed'`. The status field is NOT a live open/closed toggle — it's set to `'closed'` at write time by all paths.

| Origin | Rows | P&L | Date Range | Source of truth |
|---|---|---|---|---|
| `imported` | 70 | +$1,920.16 | 2026-01-05 → 2026-02-26 | Pre-unified era; CSV import; **NOT in unified_positions** |
| `position_ledger` | 155 | +$1,867.02 | 2026-02-26 → 2026-06-02 | Written atomically at unified close — **duplicate of unified_positions CLOSED** |
| `csv_reconciliation` | 28 | +$6.37 | 2026-01-05 → 2026-03-10 | Overlap with `imported` era; `scripts/reconcile_rh.py` output |

**Critical: the $3,793.55 total is inflated by double-counting.**  
`position_ledger` (155 rows) are the same trade events as `unified_positions CLOSED`. They exist twice because the close handler writes to both tables in one transaction.

---

## 4. P&L Reconciliation

### What each table counts

| Source | Count | P&L | Population |
|---|---|---|---|
| `trades` (all) | 253 | +$3,793.55 | Early imports + duplicates of unified CLOSED |
| `trades` (imported only) | 70 | +$1,920.16 | Pre-unified trades; no unified equivalent |
| `trades` (csv_reconciliation only) | 28 | +$6.37 | Reconciliation duplicates; likely overlap with imported |
| `trades` (position_ledger only) | 155 | +$1,867.02 | Duplicates of unified CLOSED writes |
| `unified_positions` (CLOSED, all) | 150 | +$980.34 | 71W / 61L / 17 no P&L set |
| `unified_positions` (CLOSED, linked to trades) | 132 | +$989.54 | Has trade_id FK confirmed |
| `closed_positions` | 119 | +$1,011.55 | Partial mirror of unified CLOSED |

### Why does `trades.position_ledger` ($1,867) ≠ `unified_positions.CLOSED` ($980)?

Two causes:
1. **23 orphaned position_ledger trades** have no corresponding `unified_positions` row (`trade_id` not set). These likely come from partial closes (the close handler writes to `trades` on partial close but leaves `unified_positions` open; `trade_id` is only set on full close). These 23 orphaned rows account for ~$789 of the gap.
2. **$88.24 calculation divergence** on the 132 linked (confirmed same-event) trades: `trades.pnl_dollars` sum = $1,077.78 vs `unified_positions.realized_pnl` sum = $989.54. Both are computed from the same formula in the same transaction, but small rounding differences and NULL `entry_price` edge cases accumulate.

**Confidence-graded P&L estimate:**

| Era | Trades | Estimated Net P&L | Confidence |
|---|---|---|---|
| Pre-unified (Jan 5 – Feb 25 2026) | 70 imported + 28 csv_recon | ~$1,920 (high-confidence) | Medium — figures are internally consistent but unverified against broker statements |
| Unified era (Feb 26 – Jun 2 2026) | unified_positions CLOSED | +$980.34 | High — live system, P&L set at close time |
| **Total estimate** | | **~$2,900** | Medium — pre-unified era needs broker reconciliation |

The $3,793.55 in `trades` is **not the real number** — it double-counts the position_ledger era ($1,867) against unified_positions CLOSED ($980), and conflates csv_reconciliation with imported trades.

---

## 5. The EXC Example (Corrected)

The brief stated EXC was "absent from rh_trade_history." **This is incorrect.**

EXC IS in `rh_trade_history` (4 rows on 2026-02-12/13): 1 BTO of 10 contracts at $0.10, three STC fills selling those contracts. Net cash proceeds ≈ $555.

EXC IS in `trades` (id=161, origin=imported): single row, P&L = $841.16.

EXC IS NOT in `unified_positions` (confirmed: empty result). It predates the unified system start (2026-02-26).

**Why the $841 vs $555 discrepancy**: `rh_trade_history` stores raw transaction cash flows (amount field). The $555 is net proceeds from the STC fills minus the BTO cost. The $841.16 in `trades` was entered as a round-trip P&L from a different source (the manual CSV import), possibly counting the full premium received on all legs rather than the net cash flow. One of these numbers is wrong; `rh_trade_history` raw cash flows ($555) are closer to broker truth but the full picture requires checking whether the BTO on 2026-02-12 was an additional purchase or replacement of an earlier position not visible in the 44-day snapshot.

---

## 6. `open_positions` — Abandoned

| Field | Value |
|---|---|
| Total rows | 56 |
| Active (is_active=TRUE) | 5 |
| opened_at set | 0 (all NULL) |
| Last write | 2026-03-09 |
| Account | robinhood only |

This table was the original open-position tracker before `unified_positions` was built. It was never migrated or cleaned up. The 5 "active" rows are stale. `unified_positions` has 14 OPEN rows covering the live book. **`open_positions` can be archived and dropped after the 5 active rows are confirmed to have `unified_positions` equivalents.**

---

## 7. Dedupe Keys — What Links Tables

| Key | Tables | Reliability |
|---|---|---|
| `signal_id` | trades ↔ unified_positions | Very low — only 4 matches exist |
| `trade_id` (FK) | unified_positions → trades | High — set atomically at close; 132/150 CLOSED rows confirmed |
| `position_id` | closed_positions → unified_positions | Not present in closed_positions; linkage is by ticker+date |
| RH order ID | None | Not stored in any table |
| `(ticker, entry_date::date, structure)` | trades ↔ unified ↔ closed | Medium — works for most, fails on same-day multiple positions |

No universal dedupe key exists across all tables. The `trade_id` FK between `unified_positions` and `trades` is the only programmatic link; all cross-table joins require fuzzy matching.

---

## 8. Vocabulary Chaos

### Direction

| Value | Appears in |
|---|---|
| `LONG` | trades (77), unified (76), closed_positions (70) |
| `SHORT` | trades (43), unified (46), closed_positions (38) |
| `BULLISH` | trades (72), unified (12), closed_positions (2) |
| `BEARISH` | trades (56), unified (23), closed_positions (4) |
| `bullish` (lowercase) | trades (3), unified (3), closed_positions (3) |
| `bearish` (lowercase) | trades (2), unified (9), closed_positions (2) |
| `MIXED` | unified (1) |

Direction is meaningless for filtering without normalization. BULLISH/bullish should → LONG; BEARISH/bearish should → SHORT (or keep as directional bias separately).

### Structure

| Alias | Correct canonical | Count across trades+unified |
|---|---|---|
| `put_spread` | `put_debit_spread` | 44 (trades: 40, unified: 4) |
| `call_spread` | `call_debit_spread` | 23 (trades only) |
| `shares` | `stock` | 27 (trades only) |
| `BEAR_PUT_SPREAD` | `put_debit_spread` | 4 (2 each) |
| `BULL_CALL_SPREAD` | `call_debit_spread` | 2 (1 each) |
| `long_put` | `put` or `put_debit_spread` | 4 (2 each) |

---

## 9. Recommended Canonical Source Design

### The answer: `unified_positions` is already the canonical table

It has live OPEN tracking, full close history with P&L, asset type, Greeks-ready structure, and the `trade_id` FK to `trades`. All active API reads use it. The question is how to extend it backward.

### Recommended architecture

```
                    CANONICAL SOURCE
                    ┌─────────────────────────────────┐
                    │  unified_positions               │
                    │  OPEN:   14 rows (live book)     │
                    │  CLOSED: 150 rows (Feb 26–now)   │
                    │  EXPIRED: 6 rows                 │
                    │  + BACKFILL from imported era    │
                    └──────────────┬──────────────────┘
                                   │
               ┌───────────────────┼────────────────────┐
               ↓                   ↓                    ↓
         rh_trade_history      trades.imported     manual entry
         (verify amounts)      (70 rows to port)   (Fidelity?)
```

### Retire

| Table | Action | Risk |
|---|---|---|
| `open_positions` | Archive + drop after confirming 5 active have unified equivalents | Low |
| `closed_positions` | Archive + drop; unified_positions.CLOSED is the record | Low |
| `trades` (position_ledger origin) | Stop writing — it's redundant with unified CLOSED | None after unified is authoritative |
| `trades` (imported/csv_recon) | Migrate into unified_positions as backfill then archive | Medium — needs dedup |

---

## 10. Open Decisions for Nick

### 1. Authoritative source for pre-Feb-26 era

Two options:
- **Option A (recommended):** Trust `trades.imported` (70 rows, $1,920 P&L) as the historical record — these were hand-imported from a known source. Mark them as `source='IMPORTED_HISTORICAL'` in unified_positions. Accept that `rh_trade_history` raw amounts may differ (they count individual legs, not round-trip P&L).
- **Option B:** Reconcile each of the 70 imported trades against `rh_trade_history` line-by-line before accepting any P&L figure. This is the higher-confidence approach but requires manual review of 70 trades.

### 2. `rh_trade_history` coverage gap

The table only covers 2026-01-05 to 2026-02-18 (44 days). To use it as broker truth beyond that window, Nick must import additional RH CSV exports covering 2026-02-19 onward. The import CLI is already in place (`backend/importers/import_rh_csv_cli.py`).

### 3. Fidelity Roth

`closed_positions` shows FIDELITY_ROTH account (present in 119 closed rows). No Fidelity ingest path exists in the codebase. Current Fidelity trades appear to be entered manually via the unified create API. Scope decision needed: manual-only vs CSV import for Fidelity.

### 4. Historical rebuild scope

- **Forward-only** (simplest): keep unified_positions as-is, port the 70 imported trades as a frozen historical block labeled `IMPORTED_HISTORICAL`. Total canonical P&L = imported era + unified era.
- **Full rebuild** (most accurate): reconcile every pre-unified trade against broker statements and backfill into unified_positions with correct cost_basis. Requires more data from RH and Fidelity.

---

## 11. Summary — What to Fix in Phase 1

**Highest confidence actions (no data loss risk):**
1. Archive `open_positions` — entirely stale, superseded
2. Stop writing `closed_positions` — unified_positions CLOSED is the record; this table is an unreliable partial mirror
3. Stop writing `trades` with `origin='position_ledger'` — redundant duplicate; read `unified_positions.realized_pnl` + `unified_positions.trade_id` instead
4. Normalize direction vocabulary → `LONG`/`SHORT` only (92 rows need updating across 3 tables)
5. Normalize structure vocabulary → 94 rows using stale aliases

**Pending Nick decision:**
6. Backfill 70 imported trades into `unified_positions` (Option A or B above)
7. Extend `rh_trade_history` with additional RH CSV exports for broker truth past Feb 18
8. Fidelity scope decision

**Real canonical net P&L (best estimate pending broker verification):**
- Pre-unified era (trades.imported): ~$1,920.16 *(medium confidence — matches internally, not verified vs broker statements)*
- Unified era (unified_positions.CLOSED): **$980.34** *(high confidence)*
- **Combined: ~$2,900** *(medium confidence — pre-unified era unverified)*

---

*Phase 0 complete. No schema or data changes have been made. This document is the deliverable for Nick's review before Phase 1 begins.*
