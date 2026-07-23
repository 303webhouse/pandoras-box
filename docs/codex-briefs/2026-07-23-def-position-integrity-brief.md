# DEF-POSITION-INTEGRITY — SOXS split correction + XLF third-leg backfill

**Date:** 2026-07-23 · **Lane:** main (CC) · **Priority:** P0 · **Lifts:** ATLAS departure veto (W1-1)
**Class:** fake-healthy (confident wrong values served as valid) · **Type:** data-only maintenance op on `unified_positions`
**No product/hot-path code. No schema DDL. No deploy. No suite run required** (zero code paths touched; one phase-gated maintenance script only).

---

## 0 · WHY

The book is lying to everyone who reads it. One SOXS row serves a phantom **+$18,927** unrealized gain (true ≈ +$257) because a reverse split was never applied to its quantity/entry fields. One XLF row has a NULL strike and cannot price itself at all. Every committee pass that pulls positions — URSA's coherence check, THALES's concentration math, PIVOT's book context — inherits both lies. ATLAS's departure veto stands until this is applied **and independently verified**. Departure is Aug 4.

---

## 1 · GROUND TRUTH (verified 2026-07-23 — do not re-derive externally; DO verify against the DB)

**SOXS 1-for-10 reverse split.** Effective after the close **Tue 2026-07-14**; split-adjusted trading from **Wed 2026-07-15**. Verified from primary sources: Direxion press release "Direxion to Split Nine ETFs" (direxion.com), OCC info memo #59294 (each old share → 0.1 new shares), MIAX corporate-action alert dated 2026-07-14.

**Classification boundary (UTC):**
- `opened_at`/`closed_at` **< 2026-07-14T20:00:00Z** → timestamp is in **PRE**-split price units
- `opened_at`/`closed_at` **≥ 2026-07-15T08:00:00Z** → **POST**-split units (pre-market opens 08:00Z at post-split prices)
- Timestamps **between** those two instants: no trading occurs in that window — any such row is anomalous → flag for human ruling regardless of other classification.

**STRADDLING** = opened PRE **and** (status OPEN, or closed POST). Straddlers carry pre-split entry fields marked/exited against post-split prices → phantom PnL.

**Known defective row (live hub pull, 2026-07-23):**
`POS_SOXS_20260610_154556` · fidelity_roth · stock · qty **450** · entry **4.0395** · max_loss **598.50** · stop_loss NULL · target NULL · opened 2026-06-10T15:45:56Z · OPEN. Served unrealized_pnl **+18,927.22** at current 46.10 — reproduces exactly as 450 × (46.10 − 4.0395), proving the engine computes qty × (current − entry) across mismatched units.

**Correct transform for STRADDLING rows only:** `quantity ÷ 10`; `entry_price × 10`; `stop_loss × 10` (NULL-safe); `target × 10` (NULL-safe). **Do not touch:** `max_loss` (dollar-denominated → split-invariant), `current_price` (already post-split, pipeline-owned), `unrealized_pnl` (let the engine recompute — hand-setting it would mask whether downstream recompute works).

**Invariants (hard):** per-row cost basis `quantity × entry_price` identical before/after (|Δ| < $0.01); `max_loss` byte-identical; post-transform entry lands in plausible post-split band (~$35–55 for June entries).

**Nick ruling (2026-07-23, XLF):** the Oct-16 XLF book is **one 3-leg structure entered as two rows** (entry system caps at 2 legs): the 45/40 put debit spread (`POS_XLF_20260609_233055`) **plus** a third long put — `POS_XLF_20260609_233128` (long_put ×2 @ 0.07, expiry 2026-10-16, strike NULL). **The third leg's strike is 30.0.** Fix = backfill only. Do NOT merge rows; multi-leg representation is a separate post-vacation register item.

**Negative-price artifact:** historically reported on XLF; absent from the 2026-07-23 OPEN pull → hunt in CLOSED rows. **Report-only — no mutation authorized in this brief.**

---

## 2 · SCOPE FENCE

**Touch:** `unified_positions` rows explicitly listed by Phase 0 output and confirmed by the G1 dry-run; one new phase-gated maintenance script (same location/pattern as the Tier A quarantine scripts — see `ccfbffb`); this brief file; one completion doc.
**Do NOT touch:** hot-path code, schema/DDL, hub MCP tools, frontend, tests, `signals`/`signal_outcomes`, the Tier A quarantine state, `data/watchlist.json`.
**Mechanics:** pathspec-only commits; commit messages via `C:\temp\commitmsg.txt` + `git commit -F`; all DB access via `get_postgres_client()` — no ad-hoc connection strings; `::text`-cast naive timestamp columns in every displayed query result.

---

## TASK 0 · SYNC + FILE (gate)

1. `git fetch origin` then `git status --porcelain`. **Expected dirt:** modified `data/watchlist.json` + the untracked Tier A pre-image under `backend/database/archive/`. **Leave both untouched.** Any *other* dirt → STOP, report.
2. `git pull --ff-only` — local main is expected at `c9de689` and must land at `b35e10f` or later. Not fast-forwardable → STOP, report.
3. `git mv` this brief from repo root → `docs/codex-briefs/2026-07-23-def-position-integrity-brief.md`; commit (pathspec-only); push; confirm present on origin/main before proceeding.

---

## PHASE 0 · READ-ONLY INVENTORY (stop-gate G0)

- **P0.1 Schema read.** Column list + types for `unified_positions`. Confirm which columns are price-denominated (candidates: entry_price, stop_loss, target, current_price, exit/close price fields) and the `quantity` type. The transform list in §1 extends to any additional per-share price columns found — name them in the report.
- **P0.2 SOXS full inventory.** Every SOXS row, all statuses; select all qty/price fields + `opened_at::text` + `closed_at::text`. Classify each FULLY-PRE / FULLY-POST / STRADDLING per §1. **Expected: exactly one STRADDLING row = `POS_SOXS_20260610_154556`; all others fully one side of the boundary.**
- **P0.3 Split-exposure sweep (report-only).** Every OPEN row opened < 2026-07-15 with non-null entry and current price: compute `current_price / entry_price`. Flag ratios in **[7, 13]** (unadjusted 1:10 reverse signature) or **[0.04, 0.06]** (unadjusted 20:1 forward signature). **Expected: SOXS only.** Direxion's 2026-07-15 action covered nine ETFs — this catches any other unadjusted holding without needing the list.
- **P0.4 XLF inventory + negative-value hunt.** All XLF rows, all statuses. Confirm `POS_XLF_20260609_233128` has `long_strike IS NULL`. Then across **all tickers, all statuses**: any row where any price column < 0 → report position_id + fields. Report-only.
- **P0.5 Null-strike sweep (report-only).** Options-structure rows with NULL strikes where the structure requires them, other than the known XLF leg.

**GATE G0 — STOP and hand back a Phase-0 report (no mutation, no script apply) if ANY of:** extra or missing straddlers vs P0.2 expectation · any CLOSED straddler found (its realized PnL is phantom too — transform + regrade needs a ruling) · any straddler with `quantity % 10 ≠ 0` (fractional-share redemption case) · any non-SOXS flag in P0.3 · anything anomalous in P0.1's schema vs this brief's field assumptions. **If everything matches expectations exactly → proceed to Phase 1 in the same session.**

---

## PHASE 1 · MUTATION (dry-run → gate → apply; Tier A discipline)

- **P1.1 Script.** One maintenance script (Tier A location/pattern), `--dry-run` default and `--apply`, all DB access via `get_postgres_client()`.
- **P1.2 Dry-run.** Print per-row before→after for (a) the SOXS straddler transform per §1 and (b) the XLF backfill: `long_strike NULL → 30.0` on `POS_XLF_20260609_233128`, predicate `AND long_strike IS NULL` (idempotent-safe). Print invariant preview: per-row cost-basis Δ and confirmation `max_loss` is absent from the SET list.
- **GATE G1 (hard stop).** Dry-run output goes into the completion doc verbatim and must show **exactly**: qty 450→45 · entry 4.0395→40.395 · cost basis 1,817.78 unchanged · max_loss 598.50 untouched · XLF strike →30.0 · no other rows. Any delta → ABORT, hand back.
- **P1.3 Pre-image.** JSONL of every row to be touched **plus** the full P0.2/P0.4 inventories → `backend/database/archive/2026-07-23-def-position-integrity-preimage.jsonl` **and** a copy in `C:\temp\`. Do not commit the pre-image.
- **P1.4 Apply.** Single transaction. UPDATEs keyed by the **explicit position_id list** from the dry-run — never open predicates. In-transaction invariant SELECTs (cost-basis equality ±$0.01 per row; max_loss identical) — any failure → ROLLBACK + report. Rehearse the reversal once (BEGIN → restore-from-pre-image → ROLLBACK) **before** the real apply, per Tier A discipline.

---

## PHASE 2 · VERIFY + HANDBACK

1. Post-apply SELECT of all touched rows (`::text` timestamps) into the completion doc.
2. Expected steady state within one pricing cycle: SOXS unrealized ≈ 45 × (spot − 40.395); the XLF third-leg row prices with non-null current_price/PnL.
3. **Independent verification is not CC's to claim.** Fable pulls `hub_get_positions` live and grades against §1. CC never grades its own work — the veto lifts on Fable's pull, not this handback.
4. Completion doc: `docs/codex-briefs/2026-07-23-def-position-integrity-completion.md` (Phase-0 tables, dry-run paste, apply output, invariant results, pre-image paths, rollback command). Commit script + completion doc, pathspec-only, push. **Handback = SHA + completion doc path.**

---

## ROLLBACK

Restore touched rows from the pre-image JSONL (script `--restore <path>` or documented psql equivalent in the completion doc). Pre-image exists in two locations (repo archive dir, uncommitted + `C:\temp`). Reversal rehearsed in P1.4 before apply. Recovery requires **no code change and no deploy** — vacation-constraint compliant.

---

## OLYMPUS IMPACT

Until applied: URSA's portfolio-coherence check and THALES's concentration math carry a fake five-figure SOXS winner, and the XLF book undercounts a leg that cannot price. After: the book reads true; no committee logic, skill, or tool changes. `hub_get_positions` output shape is unchanged.

---

## OUT OF SCOPE (ruled 2026-07-23 — do not build here)

- **Multi-leg (3/4/5-leg) structure support** → new register item, post-vacation. ATLAS schema pass + HELIOS entry-UI pass + mockup gate. Interim = decomposed component rows (current practice).
- **Preventive PnL sanity-bound guard** (e.g., |unrealized| vs max_loss multiple alert) → follow-up candidate alongside the LAZR Part-2 metrics bounds.
- **Broker-parity reconciliation** of the current SOXS aggregate vs Fidelity (Nick has traded SOXS since 6/10) → separate concern; this op fixes **unit consistency** of recorded rows only.
- Anything surfaced by P0.4/P0.5 → report for ruling; mutate nothing beyond the G1 list.
