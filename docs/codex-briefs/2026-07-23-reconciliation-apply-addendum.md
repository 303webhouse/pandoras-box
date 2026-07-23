# RECONCILIATION APPLY — ADDENDUM (shrunk scope, ratified 2026-07-23)

**Date:** 2026-07-23 · **Lane:** main (CC) · **Priority:** P1 · **Unlocks:** Tier B eligibility this week (§5b)
**Parent:** `docs/codex-briefs/2026-07-16-soxs-xlf-breakout-prop-reconciliation-micro-brief.md` + dry-run `c7df849` (`scripts/reconcile_soxs_xlf_dry_run.py`, read-only)
**Ruling basis (Nick, 2026-07-23, on the parent's Finding 2 + Breakout DESCOPE):** Interactive Brokers row = **DELETE**. Fidelity 401A + 403B = **consolidate under the single documented `brokerage_link_401k` identity**. Fidelity Roth untouched. breakout_prop gets **no balance row** — instead `hub_get_portfolio_balances` lists it explicitly as **untracked** rather than omitting it silently (honest-absence; committee declining to size crypto is designed behavior, not a gap).

Superseded by events, not in scope here: the parent's SOXS/XLF unit questions closed via DEF-POSITION-INTEGRITY (`076039b`); broker-parity CSV reconciliation and BREAKOUT-TRADE-IMPORT remain separately blocked on Nick's exports.

---

## SCOPE

- **T1 (data):** DELETE the stale Interactive Brokers row from `account_balances` ($0.00, last updated 2026-02-25, `updated_by='manual'`).
- **T2 (data):** Merge the `Fidelity 401A` and `Fidelity 403B` rows into ONE surviving row under the exact DB key that `_DB_TO_NORMAL` in `backend/hub_mcp/tools/portfolio_balances.py` maps to `brokerage_link_401k` (read the map — do not guess casing). Surviving balance = **sum of both rows**. Annotate `updated_by`/notes: `consolidated 401A+403B 2026-07-23`. Delete the non-surviving row.
- **T3 (code + deploy):** `portfolio_balances.py` — add an explicit `breakout_prop` entry to the payload: `balance: null`, `tracked: false`, `status: "untracked"`, note referencing the Breakout DESCOPE ruling (2026-07-23). Must be unmistakably non-sizable to committee readers. Additive payload change only; no scoring/sizing logic anywhere.

**Do NOT touch:** `fidelity_roth` or `robinhood` rows (byte-identical invariant), `unified_positions`, any signal table, the parent's SOXS/XLF items, `scripts/reconcile_rh.py` (see Task 0 rider).

**Mechanics:** all DB access via `get_postgres_client()`; `::text`-cast naive timestamps in displayed output; pathspec-only commits, msgs via `C:\temp\commitmsg.txt` + `git commit -F`. New maintenance script `scripts/reconcile_accounts_apply.py` mirroring `scripts/def_position_integrity.py` (--dry-run default / --apply --i-have-go / --restore).

---

## TASK 0 · SYNC + FILE (gate)

1. `git fetch origin`; `git status --porcelain`. Expected dirt: `M data/watchlist.json`, two untracked archive pre-images, and possibly a root `*bias-factor*` leftover (pre-cleared class — ignore/delete per standing ruling, never stage). Any other dirt → STOP, report.
2. **Credential rider:** confirm `scripts/reconcile_rh.py` is ABSENT from the working tree. If present → STOP, report to Fable, never stage (parent brief flagged a hardcoded plaintext Postgres password in it, 2026-07-16; it feeds the AEGIS rotation pass, not this lane).
3. `git pull --ff-only` (expect ≥ `49f702e`). `git mv` this addendum root → `docs/codex-briefs/2026-07-23-reconciliation-apply-addendum.md`; commit, push, confirm on origin before proceeding.

## PHASE 0 · READ-ONLY (stop-gate G0)

- Full `account_balances` dump, all columns, `::text` timestamps → completion doc.
- Read `_VALID_ACCOUNTS` / `_DB_TO_NORMAL` from `portfolio_balances.py`; name the exact surviving-row key for T2 in the report.
- **G0 expectations:** exactly one Interactive Brokers row ($0.00, 2026-02-25-stale); exactly one 401A and one 403B row; `fidelity_roth` + `robinhood` rows present; zero `breakout_prop` rows. Any deviation → STOP, hand back.

## PHASE 1 · MUTATION (dry-run → G1 → apply)

- Dry-run prints: T1 row to delete (full row), T2 before-rows → merged surviving row (name, summed balance, annotation) + row to delete, and the invariant preview.
- **Invariants (hard, in-txn):** Σ(`balance`) across the table **identical before/after** (IBKR contributes $0; the merge preserves sum) · row count N → N−2 · `fidelity_roth` and `robinhood` rows byte-identical · no other row touched.
- **GATE G1 (hard stop):** dry-run output to Fable-visible completion-doc draft; expected shape exactly as above. Any delta → ABORT, hand back.
- Pre-image: full-table JSONL → `backend/database/archive/2026-07-23-reconciliation-preimage.jsonl` + `C:\temp\` copy, uncommitted. Reversal rehearsal (apply → restore → verify → ROLLBACK) before real apply. Apply = single txn, explicit-key predicates, COMMIT only on all-pass.

## PHASE 2 · T3 CODE + DEPLOY + VERIFY

1. T3 change in `portfolio_balances.py`; suite must be byte-identical known-red (17f/517p/1s/200e) — this path has no tests; any new failure → STOP.
2. Commit (pathspec-only) + deploy. Four-step deploy verification; expect the ~2-min crypto transient-stale, don't chase it.
3. Post-deploy live check: `hub_get_portfolio_balances` shows — no Interactive Brokers entry; one `brokerage_link_401k` at the summed balance; `breakout_prop` present and explicitly untracked/null; roth + robinhood unchanged.
4. Completion doc `docs/codex-briefs/2026-07-23-reconciliation-apply-completion.md` (Phase 0 dump, dry-run paste, invariants, pre-image paths, restore cmd, deploy verification). Commit script + doc, push. **Handback = SHA. Independent verification is Fable's live pull — Tier B eligibility opens on that grade, not on this apply.**

## ROLLBACK

T1/T2: `--restore <preimage>` (full-table, tiny; rehearsed). T3: `git revert` + redeploy. No vacation-window conflict — ships now, soaks 11+ days.
