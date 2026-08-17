# W1-4 — AEGIS COORDINATED PASS: dual secret rotation + Pythia v2.4 clamp + committed-secret remediation

**Date:** 2026-07-24 · **Lane:** CC in the `th-security` worktree · **Priority:** P0 · **Lifts:** AEGIS departure veto (the last one)
**Prime directive:** secret VALUES never enter AI context, logs, commits, or completion docs. Nick generates and holds every new secret; lanes verify BEHAVIOR (pass/fail, rejected/accepted) only. Any step that would require displaying a secret is mis-designed — stop and report.
**Out of scope, explicitly:** broker credentials (none touched — absolute-veto class stays untouched), UW_API_KEY, MCP_BEARER_TOKEN, Anthropic API key (no exposure evidence), git history rewrite (ruled OUT: private repo + rotation renders the committed string worthless; filter-repo risk > value — decision logged here).

---

## SCOPE (five items, one pass)

- **R-PG** — rotate the Postgres password (committed to origin in `scripts/reconcile_rh.py` via `66fb98c`, exposed since 2026-07-19).
- **R-PY** — rotate the PYTHIA TradingView webhook secret (compromised; known) + deploy the Pythia v2.4 clamp + re-arm the three single-symbol alerts (SPY/QQQ/IWM).
- **N-FILE** — neutralize `reconcile_rh.py` in HEAD (replace hardcoded URL with the `get_postgres_client()`/env pattern; file deletion deferred to the untracked-file triage) + untrack `.claude/settings.local.json` (`git rm --cached` + `.gitignore` entry).
- **SWEEP** — secret-pattern scan of the full `66fb98c` file inventory (~30 files): grep -c for `postgres://`, `password`, `secret`, `token`, `BEARER`, `API_KEY`, `X-API-Key`. **Counts per file only — values never displayed.** Any nonzero hit beyond reconcile_rh.py → list file+pattern+count in the report for ruling; do not open the match.
- **RULES** — PROJECT_RULES.md additions: (a) BULK-CHECKPOINT BAN (insert the exact text from the coordination lane's 2026-07-23 proposal; mark RATIFIED or PENDING-RATIFICATION per Nick's current answer, relayed at launch); (b) writer-ownership sync per audit R6 — but only after the Phase-0 VPS check below.

---

## TASK 0 · SETUP (gate)

1. Work exclusively in the `th-security` worktree. `git fetch origin`; branch from `origin/main` (≥ `2e14af9`). Never touch the tangled local `main` checkout or other lanes' worktrees.
2. Read `docs/operations/mcp-token-rotation.md` (canonical rotation procedure). If absent or stale vs. this brief → surface as Finding #1, proceed with this brief as the procedure, and the completion doc updates the rotation doc.
3. Locate the Pythia v2.4 clamp spec (search docs/ + workstreams for "v2.4"/"clamp"). If no spec exists → STOP, report to Fable; the clamp gets specced before this pass deploys code.
4. File this brief: `git mv` root → `docs/codex-briefs/2026-07-24-aegis-coordinated-pass-brief.md`, commit (pathspec-only, `C:\temp\commitmsg.txt`, `git commit -F`), push.

## PHASE 0 · CONSUMER MAP + SWEEP (read-only, stop-gate G0)

- **P0.1 DATABASE_URL consumer inventory.** Every consumer of the Postgres credential: Railway backend service (is `DATABASE_URL` a `${{Postgres.*}}` reference or a literal?), VPS OpenClaw bridge (name the exact env file path under `/opt/openclaw`), local `.mcp.json`, Claude Desktop config, any script/config with a literal (the sweep finds these). Output: a consumer table with update-method per consumer.
- **P0.2 Webhook consumer inventory.** The endpoint's secret env var name on Railway; HMAC validation location in code (confirm the clamp does not weaken signature validation — AEGIS veto trigger if it does); TradingView alert count (expect exactly 3: SPY/QQQ/IWM; the repo Pine script is KNOWN-stale with the secret already redacted to a placeholder — confirm, don't "fix" the Pine file in this pass).
- **P0.3 SWEEP** per scope above. Counts table into the report.
- **P0.4 R6 rider (report-only):** VPS pivot-collector service state (`cron_runner.py` jobs for credit_spreads / market_breadth / sector_rotation). Running or not → report; disable ruling comes from Nick in-session.
- **G0:** consumer map + sweep table to Fable-visible report. Proceed on Fable/Nick "map confirmed."

## PHASE 1 · CHOREOGRAPHED EXECUTION (order is load-bearing)

- **S1 · CC preps code on the worktree branch (no deploy yet):** N-FILE neutralization, settings.local.json untrack, Pythia v2.4 clamp per spec, RULES additions, and a rejection-test helper (takes a connection string via stdin, attempts connect, prints REJECTED/ACCEPTED only).
- **S2 · NICK RUNBOOK A — Postgres (CC relays verbatim, then waits):**
  1. Password manager → generate 32 chars, letters+digits only (symbols break URLs).
  2. Railway → Postgres service → Query console → `ALTER USER postgres WITH PASSWORD '<new>';`
  3. Railway → Postgres service Variables → update `POSTGRES_PASSWORD` / any literal `DATABASE_URL`/`PGPASSWORD` to match.
  4. Railway → backend service → if `DATABASE_URL` is a reference: redeploy backend. If literal: edit the password segment (save triggers redeploy).
  5. VPS → edit the env file from P0.1 → restart the bridge service.
  6. Local → edit `C:\trading-hub\.mcp.json` password segment → restart Claude Desktop.
  Keep the OLD password retrievable until S3 passes (rollback = re-ALTER to old value).
- **S3 · CC verifies Postgres rotation (pass/fail only):** (a) OLD string — quarantine amendment: CC may read `reconcile_rh.py` solely to extract the old committed string into the rejection-test helper, never displaying it → expect **REJECTED**; (b) new-cred connection via updated `.mcp.json` → **ACCEPTED**; (c) hub MCP tools live (expect the ~2-min crypto transient after backend restart — don't chase); (d) VPS bridge writes clean on its next tick. The REJECTED result is the kill-proof: the string sitting on origin is now worthless.
- **S4 · NICK RUNBOOK B — webhook secret:** generate second secret (32 alnum) → update the Railway env var from P0.2 → update all 3 TradingView alerts' webhook payload/secret field. Old alerts stay disarmed until updated — expected gap, minutes long.
- **S5 · CC deploys the branch** (clamp + N-FILE + untrack + RULES): suite byte-identical known-red; four-step deploy verification.
- **S6 · Webhook verification (pass/fail only):** CC gives Nick a curl template (Nick fills the new secret locally): new-secret POST → accepted (200/expected response); old/absent secret POST → rejected (401/403). Real-alert round-trip during RTH is confirmatory, non-blocking (Monday if market's closed).
- **S7 · SOXS convergence rider (if RTH):** two `hub_get_positions` pulls ≥5 min apart — price moves + PnL recomputes on new fields → CLOSED; price moves + PnL stays 450-math → name DEF-PNL-RECOMPUTE-STALE, report; price frozen during RTH → name DEF-PRICING-FREEZE, report.

## PHASE 2 · EVIDENCE + HANDBACK

Completion doc `docs/codex-briefs/2026-07-24-aegis-coordinated-pass-completion.md`: consumer map, sweep counts table, rotation timestamps, all verification results as pass/fail (never values), audit-log note (rotation events recorded — the security-relevant-action logging requirement), pre-production override-log entry CLOSING the 2026-07-16 reconcile_rh.py flag, R6 service-state finding + Nick's ruling, S7 result. Merge worktree branch → main (pathspec-only), push. **Handback = SHA(s).**

**Veto lift:** Fable grades independently — live hub pulls on new creds + the REJECTED/ACCEPTED attestations + origin state. The AEGIS departure veto lifts on that grade. Monday's real-alert round-trip is logged as confirmatory follow-up, not a lift condition.

## ROLLBACK

R-PG: re-`ALTER USER` to the old value (Nick holds it until S3 passes) + revert consumer edits. R-PY: revert env var + re-point the 3 alerts. Code: `git revert` + redeploy. All recoverable without history surgery.
