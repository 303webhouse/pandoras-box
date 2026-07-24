# RECONCILIATION APPLY — COMPLETION DOC

**Status:** ✅ **COMPLETE — T1/T2 applied · T3 deployed · DEF-SEED-RESURRECTION remediated + durability-proven.** Awaiting Fable's live `hub_get_portfolio_balances` grade (Tier B eligibility opens on that grade).
**Lane:** main (CC) · **Priority:** P1 · **Brief:** `docs/codex-briefs/2026-07-23-reconciliation-apply-addendum.md`
**Commits:** addendum `d7092c3` · T3 code `447318b` · seed fix `2cddf49` · script+doc `<this commit>`

---

## TASK 0 · SYNC + FILE — DONE

- Addendum filed at `docs/codex-briefs/2026-07-23-reconciliation-apply-addendum.md`, commit **`d7092c3`**, pushed, confirmed on origin.
- **Credential rider:** `scripts/reconcile_rh.py` found present + TRACKED + in `origin/main` with the flagged plaintext `postgres://` still live in HEAD (presence-count only; contents never opened). **Fable ruling: Option 2 — rider amended, quarantine-by-discipline.** Never staged/modified/committed; AEGIS (W1-4) owns the file + commit `66fb98c` + rotation. Verified none of my commits touch it.

## PHASE 0 · READ-ONLY (G0) — ALL EXPECTATIONS MET (0 deviation)

Pre-apply `account_balances` (5 rows, Σ = 21320.13): Robinhood 835.69 · Fidelity 401A 11075.62 · Fidelity 403B 566.73 · Fidelity Roth 8842.09 · Interactive Brokers 0.00.
Surviving key from `_DB_TO_NORMAL` (read, not guessed) = **`BROKERAGE_LINK_401K`**. Verified: no triggers, no FKs, serial `id`, UNIQUE(account_name), no `notes` column.

## RULING-3 PRE-APPLY CHECK (updated_by consumers) — NONE PARSE

Repo-wide grep for any consumer that parses/string-matches `updated_by` → **no matches** (backend + frontend). Every hit is a writer or a pure passthrough SELECT (`portfolio.py GET /balances`; `balances.py`→MCP `_build_account` drops it). → Fable amendment applied: `updated_by = 'pivot_screenshot; consolidated 401A+403B 2026-07-23'`.

## PHASE 1 · APPLY — COMMITTED (rehearsal passed; single txn; in-txn invariants)

Concurrency-safe: merge sum computed **in-SQL under `FOR UPDATE` locks**. Actual applied state (post-commit read-back + independent postgres-MCP re-verify):

| id | account_name | balance | updated_at (UTC) | updated_by |
|----|--------------|---------|------------------|------------|
| 1 | Robinhood | 835.69 | 2026-07-21 17:05:55 | auto *(untouched)* |
| 2 | **BROKERAGE_LINK_401K** | **11642.35** | 2026-06-09 23:46:03 *(PRESERVED)* | `pivot_screenshot; consolidated 401A+403B 2026-07-23` |
| 4 | Fidelity Roth | 8842.09 | 2026-06-22 18:23:24 | auto *(untouched)* |

Interactive Brokers + Fidelity 403B deleted. Invariants: Σ 21320.13→21320.13 · rows 5→3 · survivors byte-identical.
Apply-script adversarially reviewed pre-G1 (3 findings fixed: in-SQL merge under FOR UPDATE; commit-misreport gate; safe restore).
Pre-image: `backend/database/archive/2026-07-23-reconciliation-preimage.jsonl` + `C:\temp\...` (round-trip verified).

## PHASE 2 · T3 CODE + DEPLOY — DONE

- `447318b` (`portfolio_balances.py`): `hub_get_portfolio_balances` adds a dedicated `untracked_accounts` entry for **breakout_prop** (`tracked:false`, `status:"untracked"`, `balance:null`, DESCOPE note), kept OUT of `accounts` and every total — additive only, no scoring/sizing logic.
- Suite byte-identical known-red **proven** (empty diff of the failing set with/without the edit; absolute counts drifted from the brief's `17f/517p` only because the Task-0 pull pulled in concurrent-lane tests). Deployed; `untracked_accounts` confirmed live.

---

## 🛑 INCIDENT — DEF-SEED-RESURRECTION (caught by the four-step deploy verify)

**Symptom:** the live functional check after the T3 deploy showed `account_balances` back to **6 rows** — the deleted `Fidelity 401A`/`Fidelity 403B`/`Interactive Brokers` reappeared (ids 6/7/8, `updated_at=2026-07-24 00:21:10Z`, seed values), coexisting with the merged `BROKERAGE_LINK_401K` → **double-count, total inflated $21,320 → $31,661.**

| id | account_name | balance | updated_at (UTC) | note |
|----|--------------|---------|------------------|------|
| 1 | Robinhood | 835.69 | 2026-07-21 | untouched ✓ |
| 2 | BROKERAGE_LINK_401K | 11642.35 | 2026-06-09 | my merge ✓ (survived) |
| 4 | Fidelity Roth | 8842.09 | 2026-06-22 | untouched ✓ |
| 6 | Fidelity 401A | 10107.90 | 2026-07-24 00:21:10 | 🛑 RE-SEEDED |
| 7 | Fidelity 403B | 233.15 | 2026-07-24 00:21:10 | 🛑 RE-SEEDED |
| 8 | Interactive Brokers | 0.00 | 2026-07-24 00:21:10 | 🛑 RE-SEEDED |

**Root cause:** `init_database()` (`postgres_client.py`) runs on every app startup; its balance seed (comment said "only if table is empty" but the code was per-account `WHERE NOT EXISTS (... account_name=X)`) re-created any missing seed account on every deploy. Deleting/renaming those account_names + any deploy ⇒ resurrection. **New defect class: DEF-SEED-RESURRECTION.**

### Remediation (Fable-approved; order: seed-fix deploy → cleanup → durability rehearsal)

**Step 1 — Seed fix (`2cddf49`):** wrapped the whole seed block behind a single truly-empty-table guard (`if not EXISTS(SELECT 1 FROM account_balances)`, evaluated once — a per-statement guard would self-defeat after the first insert). Seed VALUES untouched (stale placeholders, acceptable on a genuine fresh bootstrap only — flagged for the record). Suite byte-identical known-red. Committed pathspec-only; landed on `origin/main` via explicit refspec after a concurrent session switched the shared working tree's branch (see note). Railway deploy **SUCCESS**, `commitHash=2cddf49`. Rider #1 confirmed: post-deploy count still **6** (fixed seed added no rows).

**Step 2 — Cleanup (guarded one-shot):** `reconcile_accounts_apply.py --cleanup-reseed`. Full-match predicate on every target row — **id AND account_name AND balance AND updated_at (the 00:21:10Z signature)** — any mismatch aborts the whole txn. Pre-image (all 6 rows) → `backend/database/archive/2026-07-24-reseed-cleanup-preimage.jsonl` + `C:\temp\...`. In-txn invariants: post-state exactly {Robinhood 835.69, BROKERAGE_LINK_401K 11642.35, Fidelity Roth 8842.09}, Σ=21320.13, survivors' `updated_at` preserved, row count 3. **COMMITTED**; independently MCP-verified (3 rows, Σ 21320.13).

**Step 3 — Durability rehearsal (mandatory) — PASSED:** restarted the service once via `railway redeploy` (restart transient observed: HTTP 000→502→200 at ~02:28Z; `mcp_ping` uptime reset to 81s confirming `init_database()` re-ran). **Row count after restart: 3** — exactly {Robinhood 835.69, BROKERAGE_LINK_401K 11642.35, Fidelity Roth 8842.09}, Σ=21320.13. The deleted accounts did **NOT** resurrect ⇒ the seed fix is durably live.

**End-to-end functional check (`hub_get_portfolio_balances`, post-remediation):** 3 accounts, `total_balance=21320.13` (no longer the inflated $31,661), no Interactive Brokers / 401A / 403B duplicates, `brokerage_link_401k` at 11642.35, and `breakout_prop` in `untracked_accounts` (`tracked:false`, `balance:null`). Summary: *"Total $21,320 across 3 accounts … breakout_prop: untracked (no balance row — not sizable)."*

**Concurrency note:** mid-remediation a concurrent local session switched the shared `C:\trading-hub` working tree from `main` to `s6-stater-build`; my seed-fix commit initially landed there. It was recovered non-destructively by pushing the commit to `origin/main` via explicit refspec (`git push origin 2cddf49:main`, fast-forward — parent was the current origin tip). T3 (`447318b`) was already safely in origin/main. No history rewrite, no dropped work.

## ROLLBACK

- T1/T2: `--restore backend/database/archive/2026-07-23-reconciliation-preimage.jsonl`.
- Reseed cleanup: `--restore backend/database/archive/2026-07-24-reseed-cleanup-preimage.jsonl` (re-INSERTs ids 6/7/8).
- T3 / seed fix: `git revert 447318b` / `git revert 2cddf49` + redeploy.

---

**Handback = SHAs `447318b` (T3) + `2cddf49` (seed fix) + `<this>` (script+doc). Fable's live `hub_get_portfolio_balances` grade follows.**
