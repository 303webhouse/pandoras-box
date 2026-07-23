# DEF-POSITION-INTEGRITY — COMPLETION

**Date:** 2026-07-23 · **Lane:** main (CC) · **Status:** ✅ APPLIED & COMMITTED (CC self-verify only) · **Class:** fake-healthy
**Type:** data-only maintenance on `unified_positions` — no product/hot-path code, no schema DDL, no deploy, no suite run.
**Script:** `scripts/def_position_integrity.py` (Tier A pattern; `get_postgres_client()`; `--inventory`/`--dry-run`/`--apply`/`--restore`).
**Independent verification is NOT claimed here.** The ATLAS departure veto (W1-1) lifts on **Fable's** live `hub_get_positions` grade after this SHA lands — not on this apply.

---

## 1 · What was corrected

Two rows in `unified_positions`, keyed by explicit `position_id`, single transaction, in-txn invariants, COMMIT only on all-pass:

| position_id | before | after |
|---|---|---|
| `POS_SOXS_20260610_154556` (SOXS, EQUITY, OPEN, fidelity_roth) | qty **450**, entry **4.0395**, breakeven **[5.985]** | qty **45**, entry **40.395**, breakeven **[59.85]** |
| `POS_XLF_20260609_233128` (XLF, OPTION long_put, OPEN) | long_strike **NULL** | long_strike **30.0** |

**SOXS transform** (1-for-10 reverse split, effective after close 2026-07-14): `quantity ÷10`, `entry_price ×10`, `stop_loss ×10` (NULL→NULL), `target_1 ×10` (NULL→NULL), `target_2 ×10` (NULL→NULL), `breakeven[] ×10`.
**Untouched (by design):** `current_price` (pipeline-owned), `max_loss` 598.50 (dollar-denominated → split-invariant), `cost_basis` 1817.78 (stored, split-invariant), `unrealized_pnl` (engine recomputes — hand-setting would mask whether downstream recompute works).
**XLF:** strike backfill only, idempotent predicate `AND long_strike IS NULL`. Rows NOT merged (multi-leg representation is a separate post-vacation register item).

### PnL reconciliation — Rider 1 (one price instant, spot **$45.61**)
- **Phantom** (what the book served, engine computing across mismatched units): `450 × (45.61 − 4.0395)` = **+$18,706.73**
- **True** (post-fix, engine recomputes): `45 × (45.61 − 40.395)` = **+$234.68**

Immediately post-apply the stored `unrealized_pnl` is still the stale phantom (18,706.73, last pipeline write 2026-07-23 20:47:06Z); it converges to ~+$234.68 within one pricing cycle. The XLF third leg (`current_price`/`unrealized_pnl` = NULL pre-fix) can now price with a non-null strike. Both are engine-owned steady states for **Fable** to confirm on the live pull.

---

## 2 · Per-share price-column map — Rider 2 (checklist for the next split event)

From the P0.1 `unified_positions` schema read. On a 1-for-N reverse split (`quantity ÷N`), scale each **per-share** price column `×N`; leave dollar-denominated and pipeline/engine columns alone.

| Column | Type | Split treatment |
|---|---|---|
| `entry_price` | numeric | **×N** (per-share) |
| `stop_loss` | numeric | **×N** (NULL-safe) |
| `target_1` | numeric | **×N** (NULL-safe) |
| `target_2` | numeric | **×N** (NULL-safe) |
| `breakeven` | numeric[] | **×N per element** (NULL-safe) — *not in the brief's original §1 list; caught by the §1 extension clause, ratified by Nick+Fable 2026-07-23* |
| `long_strike` / `short_strike` | numeric | **×N** if present (options; NULL for equities) |
| `long_leg_price` / `short_leg_price` | numeric | **×N** if present (options; NULL for equities) |
| `exit_price` | numeric | **×N** if present (NULL while OPEN) |
| `quantity` | integer | **÷N** (guard `quantity % N = 0`; fractional → human ruling) |
| `current_price` | numeric | **DO NOT TOUCH** — pipeline-owned (already post-split) |
| `unrealized_pnl` | numeric | **DO NOT TOUCH** — engine recomputes |
| `cost_basis` | numeric | **DO NOT TOUCH** — = qty×entry, split-invariant |
| `max_loss` / `max_profit` / `realized_pnl` | numeric | **DO NOT TOUCH** — dollar-denominated, split-invariant |

Classification (columns): `entry_date`/`exit_date` are `timestamptz` (not `opened_at`/`closed_at`); asset type is `asset_type`. Split boundary (UTC): entry/exit `< 2026-07-14T20:00Z` = PRE, `>= 2026-07-15T08:00Z` = POST, between = anomalous (human ruling). STRADDLING = opened PRE AND (OPEN or closed POST).

---

## 3 · G1 dry-run (verbatim — apply-in-rolled-back-transaction)

```
  rows affected: SOXS=1 (expect 1)  XLF=1 (expect 1)
  SOXS POS_SOXS_20260610_154556:
      quantity       450  ->  45   <-- CHANGED
      entry_price    4.0395...  ->  40.395...   <-- CHANGED
      breakeven      [5.985...]  ->  [59.85...]   <-- CHANGED
      stop_loss      None  ->  None
      target_1       None  ->  None
      target_2       None  ->  None
      current_price  45.6100006103515625  ->  45.6100006103515625   (untouched)
      max_loss       598.5  ->  598.5   (untouched)
      cost_basis     1817.78...  ->  1817.78...   (untouched)
  XLF  POS_XLF_20260609_233128:
      long_strike    None  ->  30.0   <-- CHANGED

  invariant cost-basis qty*entry: 1817.775000...140687461680 -> 1817.775000...140687461680 (delta=0E-24)
  SET-list guard: max_loss / cost_basis / current_price NOT in any SET clause [ok]
  INVARIANTS: ALL OK
```

**Fable G1 grade: PASS** — transform exact-match confirmed; breakeven ×10 ratified (§1 extension clause); XLF guarded predicate confirmed; pre-image independently read (22 rows, `_touched` flags correct), C:\temp copy present, rollback path physically verified at both locations.

## 4 · Apply (verbatim)

```
  --- reversal rehearsal (apply -> restore -> verify -> rollback) ---
    rehearsal restore fidelity: OK (restore path verified)
  --- real apply (single transaction) ---
    applied: SOXS=1 XLF=1; cost-basis 1817.775000...->1817.775000... (delta=0E-24);
             row-count 302==302; invariants OK  COMMITTED
  POST-APPLY SOXS: qty=45 entry=40.395... breakeven=[59.85...] cost_basis=1817.78...
                   max_loss=598.5 cur=45.6100006103515625 uPnL=18706.73(stale-phantom, engine recomputes)
  POST-APPLY XLF : long_strike=30.0
```

**In-txn invariants (all passed → COMMIT):** cost-basis `qty×entry` Δ = 0 (<$0.01); `max_loss` identical; stored `cost_basis` identical; `current_price` untouched; post entry 40.395 in band $35–55; SOXS rowcount 1, XLF rowcount 1; total row-count 302→302 invariant.

## 5 · Post-apply verification (read-only)

- SOXS `POS_SOXS_20260610_154556`: qty 45, entry 40.395, breakeven [59.85], cost_basis 1817.78, max_loss 598.5, long_strike NULL. ✓
- XLF `POS_XLF_20260609_233128`: long_strike 30.0. ✓
- **P0.3 split-exposure sweep: swept=14, flagged=0** (was 1 pre-apply) — SOXS 1:10 signature eliminated (ratio now 45.61/40.395 = 1.13). ✓
- Total `unified_positions` rows: 302 (unchanged). ✓

---

## 6 · Pre-image & rollback

**Pre-image** (22 rows = full P0.2 SOXS + P0.4 XLF inventories; 2 `_touched`; NOT committed):
- `backend/database/archive/2026-07-23-def-position-integrity-preimage.jsonl`
- copy: `C:\temp\2026-07-23-def-position-integrity-preimage.jsonl`

**Rollback** (no code change, no deploy — vacation-compliant; rehearsed in a throwaway txn before apply):
```
python scripts/def_position_integrity.py --restore backend/database/archive/2026-07-23-def-position-integrity-preimage.jsonl
```
Restores the 2 touched rows' mutated columns (SOXS: quantity/entry_price/stop_loss/target_1/target_2/breakeven; XLF: long_strike) to pre-image values, single txn.

---

## 7 · Report-only findings (mutate nothing beyond the G1 list — per brief)

- **Anomalous-window SOXS row** `POS_SOXS_20260715_060000` (qty 6, entry 46.208 already post-split, opened 2026-07-15T00:00Z midnight in the no-trade gap): Nick-ruled benign date-granularity CSV import — **no transform**.
- **Fully-pre closed SOXS row** `POS_SOXS_20260707_06000003`: carries a stale post-split `current_price` 54.85 (cosmetic; realized side correct as both legs are pre-split). Out of scope.
- **Negative-price hunt (P0.4):** 8 rows with negative `current_price`, all CLOSED/EXPIRED, tiny (−0.01…−0.84), **none XLF** (META, BBBY, CF, STUB, HYG, IBIT, XLY, GME). The historically-reported XLF negative artifact is absent from the OPEN pull. Report-only.
- **Null-strike sweep (P0.5):** ~30 options rows; most are single-leg `long_*` where `short_strike` is correctly NULL. Genuinely un-priceable (both strikes NULL): NVDA `…222714`, JPM `…180544`, IWM `…231345`, IBIT `…221913`, SMH `…231338`, ONON `…231342`, WEAT `…062328`, COUR `…210121`. Report-only.

## 8 · Out of scope (ruled 2026-07-23)

Multi-leg structure support (post-vacation register item); preventive PnL sanity-bound guard (follow-up with LAZR Part-2); broker-parity reconciliation of the SOXS aggregate vs Fidelity (this op fixed unit consistency of recorded rows only); anything in §7.

## 9 · Handback

`hub_get_positions` output shape unchanged; no committee logic / skill / tool changes. **Independent verification = Fable** (live `hub_get_positions` grade against §1 after this SHA lands). The veto lifts on that pull, not on this apply.
